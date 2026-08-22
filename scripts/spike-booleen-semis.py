"""Sonde P040 — une variable à la fois, dans le régime d'une bague.

Usage :  freecadcmd scripts/spike-booleen-semis.py

P039 tenait l'entraxe et faisait donc grandir le jonc avec le nombre :
rayon et effectif bougeaient ensemble, et la courbe était illisible.
Ici chaque campagne n'en bouge qu'une :

  A — rayon 9 mm (bague), 10 / 20 / 30 / 40 pierres
  B — 30 pierres, rayon 8 / 12 / 24 / 48 mm
  C — rayon 9 mm, 30 pierres, le diamètre (donc l'écart entre sièges)
      ne se lance que si A et B ne désignent pas une cause.

Chaque ligne porte rayon, entraxe, diamètre, temps et RSS pic. Un
plafond mémoire et un plafond temps arrêtent proprement. Chaque point
tourne dans un processus fils — ``ru_maxrss`` est un maximum de
processus, et un point qui s'étouffe ne doit pas emporter les autres.
"""

from __future__ import annotations

import json
import math
import os
import resource
import subprocess
import sys
import tempfile
import threading
import time

os.environ["FREESOLID_NO_SERVE"] = "1"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001 — stdout ASCII, sans importance ici
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

DIAMETRE_MM = 1.5
LIFT_MM = -0.25
PAD_HEIGHT_MM = 6.0

#: Plafond RSS — en dessous des ~13 Go où P037 a vu le processus mourir
#: sur une VM de 15 Go, avec une marge pour le système.
CEILING_RSS_KIB = 8 * 1024 * 1024  # 8 GiB
CEILING_SECONDS = 360  # 6 min par point

_MARKER = "SPIKE_N_JSON:"
_SPEC_ENV = "FREESOLID_SPIKE_SPEC"
_RESULT_ENV = "FREESOLID_SPIKE_RESULT"

#: Un effet « fort » : le coût (ou le plafond) d'un bout à l'autre de la
#: campagne au moins double, ou un point avorte. En dessous, la variable
#: ne désigne pas une explosion.
_EFFECT_RATIO = 2.0


def rss_kib():
    """RSS courant en KiB. ``ru_maxrss`` n'est qu'un maximum, pas un instantané."""
    try:
        with open("/proc/self/status", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        pass
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(usage)


def maxrss_kib():
    """Maximum RSS du processus, en KiB (Linux)."""
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)


def mem_total_kib():
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        pass
    return None


def cpu_model():
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return os.uname().machine


def machine_info(freecad):
    mem = mem_total_kib()
    return {
        "freecad": freecad,
        "sysname": os.uname().sysname,
        "release": os.uname().release,
        "machine": os.uname().machine,
        "cpu": cpu_model(),
        "mem_total_kib": mem,
        "mem_total_gi": round(mem / (1024 * 1024), 2) if mem else None,
        "nproc": os.cpu_count(),
    }


def entraxe_mm(rayon, pierres):
    """Entraxe d'arc : circonférence du jonc divisée par l'effectif."""
    if pierres <= 0:
        return None
    return 2.0 * math.pi * float(rayon) / float(pierres)


def regime_of(rayon):
    """Une bague fait 8 à 10 mm de rayon. Le dire si on sort de là."""
    r = float(rayon)
    if 8.0 <= r <= 10.0:
        return "bague"
    if r < 8.0:
        return "plus petit qu'une bague"
    if r <= 12.0:
        return "proche d'une bague"
    return "bracelet — hors régime d'une bague"


def geometry_of(pierres, rayon_mm, diametre_mm):
    """Rayon, entraxe, diamètre — les trois sur chaque ligne."""
    arc = entraxe_mm(rayon_mm, pierres)
    return {
        "pierres": int(pierres),
        "rayon_mm": round(float(rayon_mm), 3),
        "diametre_mm": round(float(diametre_mm), 3),
        "entraxe_mm": round(arc, 3) if arc is not None else None,
        "ecart_sieges_mm": (
            round(arc - float(diametre_mm), 3) if arc is not None else None),
        "chevauchement": bool(arc is not None and arc < float(diametre_mm)),
        "regime": regime_of(rayon_mm),
    }


def _point(campagne, pierres, rayon_mm, diametre_mm=DIAMETRE_MM):
    spec = geometry_of(pierres, rayon_mm, diametre_mm)
    spec["campagne"] = campagne
    return spec


#: Une variable par campagne. Le diamètre reste 1,5 mm en A et B : le
#: faire bouger là serait exactement le confond que P039 a commis, inversé.
CAMPAIGNS = {
    "A": {
        "id": "A",
        "fixe": "rayon 9 mm (bague)",
        "varie": "nombre de pierres",
        "question": "le coût croît-il avec le nombre ?",
        "points": [
            _point("A", 10, 9.0),
            _point("A", 20, 9.0),
            _point("A", 30, 9.0),
            _point("A", 40, 9.0),
        ],
    },
    "B": {
        "id": "B",
        "fixe": "30 pierres",
        "varie": "rayon du jonc",
        "question": "la courbure est-elle le facteur ?",
        "points": [
            _point("B", 30, 8.0),
            _point("B", 30, 12.0),
            _point("B", 30, 24.0),
            _point("B", 30, 48.0),
        ],
    },
    "C": {
        "id": "C",
        "fixe": "rayon 9 mm, 30 pierres",
        "varie": "diamètre de pierre (écart entre sièges)",
        "question": "l'écart entre sièges décide-t-il ?",
        # Rayon et effectif figés → l'entraxe d'arc est figé (1,885 mm).
        # Seul le diamètre bouge, donc l'écart entre sièges.
        "points": [
            _point("C", 30, 9.0, 0.80),
            _point("C", 30, 9.0, 1.15),
            _point("C", 30, 9.0, 1.50),
            _point("C", 30, 9.0, 1.80),
        ],
    },
}


def write_result(path, payload):
    text = json.dumps(payload, ensure_ascii=False)
    if path:
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
                fh.write("\n")
        except OSError:
            pass
    print(_MARKER + text, flush=True)


def _entraxe_corde_mm(stones):
    """Distance 3D moyenne entre voisins, dans l'ordre du semis."""
    pts = []
    for stone in stones or []:
        if "x" not in stone or "y" not in stone or "z" not in stone:
            continue
        pts.append((float(stone["x"]), float(stone["y"]), float(stone["z"])))
    n = len(pts)
    if n < 2:
        return None
    total = 0.0
    for i in range(n):
        ax, ay, az = pts[i]
        bx, by, bz = pts[(i + 1) % n]
        total += math.sqrt((ax - bx) ** 2 + (ay - by) ** 2 + (az - bz) ** 2)
    return round(total / n, 3)


def measure_one(spec):
    """Un point, un document, le geste ``add_boolean`` réel."""
    from engine.kernel import Kernel
    from engine.platform import allow_from_environ, version_status

    count = int(spec["pierres"])
    radius = float(spec["rayon_mm"])
    diametre = float(spec["diametre_mm"])
    result_path = os.environ.get(_RESULT_ENV) or ""
    kernel = Kernel()
    plateforme = version_status(
        kernel.ping()["freecad"], allow=allow_from_environ())
    out = dict(spec)
    out["plateforme"] = plateforme
    out["machine"] = machine_info(plateforme["running"])
    out["rss_avant_kib"] = rss_kib()
    out["aborted"] = None
    if not plateforme["match"] and not plateforme["override"]:
        out["aborted"] = "plateforme"
        out["erreur"] = plateforme["message"]
        write_result(result_path, out)
        return out

    stop = threading.Event()
    peak = [rss_kib()]

    def watch():
        while not stop.wait(0.2):
            now = rss_kib()
            if now > peak[0]:
                peak[0] = now
            if now >= CEILING_RSS_KIB:
                out["aborted"] = "rss"
                out["rss_pic_kib"] = now
                out["rss_pic_gi"] = round(now / (1024 * 1024), 2)
                out["maxrss_kib"] = maxrss_kib()
                write_result(result_path, out)
                os._exit(2)

    watcher = threading.Thread(target=watch, name="rss-watch", daemon=True)
    watcher.start()

    phases = []

    def feed(phase, fait=0, total=0):
        phases.append({
            "t": time.perf_counter(),
            "phase": str(phase or ""),
            "fait": int(fait or 0),
            "total": int(total or 0),
        })

    try:
        t_pose0 = time.perf_counter()
        kernel.new_part("Sonde {} pierres r={}".format(count, radius))
        state = kernel.sketch_start()
        sketch = state["sketch"]
        kernel.sketch_add_circle(sketch, 0, 0, radius)
        kernel.sketch_constrain(
            sketch, "coincident", 0, point1=3, geo2=-1, point2=1)
        kernel.sketch_finish(sketch)
        kernel.add_pad(PAD_HEIGHT_MM, sketch=sketch)
        side = kernel._side_face_id()
        face = kernel._require_body().Shape.Faces[side]
        u0, u1, v0, v1 = face.ParameterRange
        v_mid = (v0 + v1) / 2.0
        first = face.valueAt(u0 + (u1 - u0) * 0.5 / count, v_mid)
        placed = kernel.place_gem(
            face=side, x=first.x, y=first.y, z=first.z,
            diametre=diametre, lift=LIFT_MM)
        gems = placed.get("gems") or []
        if not gems:
            raise RuntimeError("semis absent après la première pose")
        semis = gems[0]["name"]
        link = kernel._require_gem_link(semis)
        us, vs, spins, lifts = [], [], [], []
        for index in range(count):
            u = u0 + (u1 - u0) * (index + 0.5) / count
            us.append(u)
            vs.append(v_mid)
            spins.append(0.0)
            lifts.append(LIFT_MM)
        kernel._write_stone_lists(link, us, vs, spins, lifts)
        kernel._recompute()
        listed = kernel.list_gems().get("gems") or []
        held = int((listed or [{}])[0].get("count") or 0)
        pose_s = time.perf_counter() - t_pose0
        out["pose_s"] = round(pose_s, 3)
        out["posees"] = held
        out["entraxe_corde_mm"] = _entraxe_corde_mm(
            (listed or [{}])[0].get("stones"))
        out["rss_apres_pose_kib"] = rss_kib()
        if held != count:
            out["aborted"] = "pose"
            out["erreur"] = "semis à {} pierre(s), attendu {}".format(
                held, count)
            write_result(result_path, out)
            return out

        kernel._progress = feed
        rss_before = rss_kib()
        t0 = time.perf_counter()
        tree = kernel.add_boolean(tool=semis, type="cut")
        total_s = time.perf_counter() - t0
        shape = kernel._require_body().Shape
        solids = list(getattr(shape, "Solids", ()) or ())
        out["ok"] = True
        out["total_s"] = round(total_s, 3)
        out["ms_par_pierre"] = round(total_s * 1000.0 / count, 1)
        out["solides"] = len(solids)
        out["volume_mm3"] = round(float(getattr(shape, "Volume", 0.0) or 0.0), 3)
        out["booléen_dans_arbre"] = any(
            str(f.get("type") or "") == "PartDesign::Boolean"
            for f in (tree.get("features") or []))
        compound_s, boolean_s, rebuild_s = _split_phases(phases, t0, total_s)
        out["compound_s"] = round(compound_s, 3)
        out["booleen_s"] = round(boolean_s, 3)
        out["reconstruction_s"] = round(rebuild_s, 3)
        if compound_s > 1e-6:
            out["facteur_booleen_sur_compound"] = round(
                boolean_s / compound_s, 1)
        out["rss_avant_booleen_kib"] = rss_before
        out["rss_apres_kib"] = rss_kib()
        out["rss_pic_kib"] = max(peak[0], rss_kib(), maxrss_kib())
        out["rss_pic_gi"] = round(out["rss_pic_kib"] / (1024 * 1024), 2)
        out["maxrss_kib"] = maxrss_kib()
        out["maxrss_gi"] = round(out["maxrss_kib"] / (1024 * 1024), 2)
        write_result(result_path, out)
        return out
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — un échec est un résultat
        out["ok"] = False
        out["aborted"] = out.get("aborted") or "erreur"
        out["erreur"] = "{}: {}".format(type(exc).__name__, str(exc)[:240])
        out["rss_pic_kib"] = max(peak[0], rss_kib(), maxrss_kib())
        out["rss_pic_gi"] = round(out["rss_pic_kib"] / (1024 * 1024), 2)
        out["maxrss_kib"] = maxrss_kib()
        write_result(result_path, out)
        return out
    finally:
        stop.set()
        kernel._progress = None


def _split_phases(phases, t0, total_s):
    """Découpe compound (derive) / premier recompute / le reste.

    Un second ``Construction du compound`` arrive pendant
    ``_refresh_gem_boolean_tools`` : on ne le recompte pas, sinon le
    recompute suivant — le vrai coût — serait attribué au compound.
    """
    if not phases:
        return 0.0, total_s, 0.0
    t_cut = None
    t_rebuild = None
    for item in phases:
        elapsed = item["t"] - t0
        phase = item["phase"]
        if t_cut is None and phase in ("Soustraire", "Ajouter", "Intersection"):
            t_cut = elapsed
        if t_rebuild is None and phase.startswith("Reconstruction"):
            t_rebuild = elapsed
    compound = max(0.0, t_cut) if t_cut is not None else 0.0
    if t_rebuild is not None:
        boolean = max(0.0, t_rebuild - compound)
        rebuild = max(0.0, total_s - t_rebuild)
    else:
        boolean = max(0.0, total_s - compound)
        rebuild = 0.0
    return compound, boolean, rebuild


def _parse_child_payload(stdout, result_path):
    if result_path and os.path.isfile(result_path):
        try:
            with open(result_path, encoding="utf-8") as fh:
                return json.loads(fh.read())
        except (OSError, ValueError):
            pass
    text = stdout or ""
    for line in text.splitlines():
        if line.startswith(_MARKER):
            try:
                return json.loads(line[len(_MARKER):])
            except ValueError:
                continue
    return None


def _child_command():
    """Relance via ``freecadcmd`` : le python de l'env n'importe pas FreeCAD."""
    import shutil
    script = os.path.abspath(__file__)
    candidates = []
    argv0 = os.path.abspath(sys.argv[0]) if sys.argv else ""
    if os.path.basename(argv0).startswith("freecadcmd") and os.path.isfile(argv0):
        candidates.append(argv0)
    found = shutil.which("freecadcmd")
    if found:
        candidates.append(found)
    fallback = os.path.expanduser(
        "~/micromamba/envs/freecad/bin/freecadcmd")
    if os.path.isfile(fallback):
        candidates.append(fallback)
    if not candidates:
        raise RuntimeError(
            "freecadcmd introuvable — lancez via "
            "micromamba run -n freecad freecadcmd")
    return [candidates[0], script]


def _child_rss_kib(pid):
    """RSS du fils — le thread Python du fils ne tourne pas pendant OCCT."""
    try:
        with open("/proc/{}/status".format(pid), encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        return None
    return None


def _spec_tag(spec):
    return "{}-n{}-r{}-d{}".format(
        spec.get("campagne") or "x",
        spec["pierres"],
        spec["rayon_mm"],
        spec["diametre_mm"],
    )


def run_child(spec):
    tag = _spec_tag(spec)
    result_path = os.path.join(
        tempfile.gettempdir(), "spike-booleen-semis-{}.json".format(tag))
    try:
        os.remove(result_path)
    except OSError:
        pass
    env = os.environ.copy()
    env[_SPEC_ENV] = json.dumps(spec, ensure_ascii=False)
    env[_RESULT_ENV] = result_path
    env["FREESOLID_NO_SERVE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    print("spike> {} — {} pierres, rayon {} mm, Ø {} mm, entraxe {} mm "
          "({} ; plafond {} GiB, {} s)".format(
              spec.get("campagne"),
              spec["pierres"], spec["rayon_mm"], spec["diametre_mm"],
              spec["entraxe_mm"], spec["regime"],
              CEILING_RSS_KIB / (1024 * 1024), CEILING_SECONDS), flush=True)
    proc = subprocess.Popen(
        _child_command(),
        cwd=_REPO,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    deadline = time.time() + CEILING_SECONDS
    aborted = None
    last_rss = None
    while proc.poll() is None:
        if time.time() >= deadline:
            aborted = "temps"
            proc.kill()
            break
        last_rss = _child_rss_kib(proc.pid)
        if last_rss is not None and last_rss >= CEILING_RSS_KIB:
            aborted = "rss"
            proc.kill()
            break
        time.sleep(0.25)
    stdout, stderr = proc.communicate()
    payload = _parse_child_payload(stdout, result_path)
    if payload is not None:
        for key, value in spec.items():
            payload.setdefault(key, value)
        if aborted and not payload.get("aborted"):
            payload["aborted"] = aborted
            payload["ok"] = False
            if last_rss is not None:
                payload["rss_pic_kib"] = last_rss
                payload["rss_pic_gi"] = round(last_rss / (1024 * 1024), 2)
        return payload
    out = dict(spec)
    if aborted:
        out["ok"] = False
        out["aborted"] = aborted
        out["erreur"] = (
            "plafond mémoire {} GiB".format(CEILING_RSS_KIB / (1024 * 1024))
            if aborted == "rss"
            else "plafond {} s dépassé".format(CEILING_SECONDS)
        )
        if last_rss is not None:
            out["rss_pic_kib"] = last_rss
            out["rss_pic_gi"] = round(last_rss / (1024 * 1024), 2)
        return out
    out.update({
        "ok": False,
        "aborted": "fils",
        "code": proc.returncode,
        "erreur": "pas de JSON (code {})".format(proc.returncode),
        "stderr": (stderr or "")[-400:],
        "stdout": (stdout or "")[-400:],
    })
    return out


def run_campaign(campaign_id):
    campaign = CAMPAIGNS[campaign_id]
    rows = [run_child(point) for point in campaign["points"]]
    return {
        "id": campaign["id"],
        "fixe": campaign["fixe"],
        "varie": campaign["varie"],
        "question": campaign["question"],
        "mesures": rows,
        "effet": _effect(rows),
    }


def _ms_par_pierre(row):
    """Coût unitaire. Un avortement compte comme infini — c'est une explosion."""
    n = int(row.get("pierres") or 0)
    if row.get("ok") and isinstance(row.get("total_s"), (int, float)) and n > 0:
        return 1000.0 * float(row["total_s"]) / n
    if row.get("aborted") in ("rss", "temps"):
        return float("inf")
    return None


def _rss_gi(row):
    if isinstance(row.get("rss_pic_gi"), (int, float)):
        return float(row["rss_pic_gi"])
    if row.get("aborted") == "rss":
        return float(CEILING_RSS_KIB) / (1024 * 1024)
    return None


def _ratio(values):
    finite = [v for v in values if v is not None and math.isfinite(v)]
    if any(v is not None and not math.isfinite(v) for v in values):
        return float("inf") if finite else None
    if len(finite) < 2:
        return None
    lo = min(finite)
    hi = max(finite)
    if lo < 1e-9:
        return None
    return round(hi / lo, 2)


def _effect(rows):
    """Amplitude unitaire le long d'une campagne — une seule variable.

    Le temps total d'A croîtra toujours avec l'effectif si chaque pierre
    coûte quelque chose : ce n'est pas une explosion. On compare le
    milliseconde par pierre, et le RSS. Seuls les plafonds mémoire et
    temps comptent comme explosion — un refus de plateforme n'en est pas
    une.
    """
    aborted = [
        {"pierres": r.get("pierres"), "rayon_mm": r.get("rayon_mm"),
         "diametre_mm": r.get("diametre_mm"), "entraxe_mm": r.get("entraxe_mm"),
         "cause": r.get("aborted")}
        for r in rows if r.get("aborted")
    ]
    exploded = [item for item in aborted if item.get("cause") in ("rss", "temps")]
    ms_ratio = _ratio([_ms_par_pierre(r) for r in rows])
    rss_ratio = _ratio([_rss_gi(r) for r in rows])
    known_s = [
        float(r["total_s"]) for r in rows
        if r.get("ok") and isinstance(r.get("total_s"), (int, float))
    ]
    strong = bool(exploded) or (
        ms_ratio is not None and ms_ratio >= _EFFECT_RATIO
    ) or (
        rss_ratio is not None and rss_ratio >= _EFFECT_RATIO
    )
    return {
        "fort": strong,
        "ratio_ms_par_pierre": ms_ratio,
        "ratio_rss": rss_ratio,
        "ratio": ms_ratio,
        "min_s": round(min(known_s), 3) if known_s else None,
        "max_s": round(max(known_s), 3) if known_s else None,
        "avortés": aborted,
    }


def _c_needed_reason(camp_a, camp_b):
    """C si A et B ne désignent pas une cause à elles seules."""
    a_strong = bool((camp_a.get("effet") or {}).get("fort"))
    b_strong = bool((camp_b.get("effet") or {}).get("fort"))
    if a_strong and not b_strong:
        return None
    if b_strong and not a_strong:
        return None
    if not a_strong and not b_strong:
        return None
    return (
        "A et B varient toutes les deux : nombre et courbure restent "
        "liés à l'écart entre sièges — seule C les sépare"
    )


def _all_aborted(campaign, cause=None):
    rows = campaign.get("mesures") or []
    if not rows:
        return False
    if cause is None:
        return all(r.get("aborted") for r in rows)
    return all(r.get("aborted") == cause for r in rows)


def _verdict(camp_a, camp_b, camp_c):
    """Quelle variable décide — ou le constat qu'aucune ne tranche."""
    if _all_aborted(camp_a, "plateforme") or _all_aborted(camp_b, "plateforme"):
        return {
            "variable": "aucune nette",
            "detail": (
                "La sonde a refusé de mesurer : FreeCAD n'est pas la "
                "plateforme de référence. Aucune variable ne décide tant "
                "que la courbe n'existe pas."
            ),
            "campagne_c_lancee": bool((camp_c or {}).get("mesures")),
            "A_fort": False,
            "B_fort": False,
            "C_fort": None,
            "ratio_A": None,
            "ratio_B": None,
            "ratio_C": None,
        }
    a_strong = bool((camp_a.get("effet") or {}).get("fort"))
    b_strong = bool((camp_b.get("effet") or {}).get("fort"))
    c_rows = (camp_c or {}).get("mesures") or []
    c_strong = bool(((camp_c or {}).get("effet") or {}).get("fort"))
    c_ran = bool(c_rows)

    if c_ran and c_strong and a_strong and b_strong:
        variable = "écart entre sièges"
        detail = (
            "A croît avec le nombre (donc avec le serrage), B croît quand "
            "le jonc se referme (donc avec le serrage), C isolée — rayon "
            "et effectif figés — croît quand le diamètre rapproche les "
            "sièges. C'est l'écart, pas le nombre ni la courbure à elle "
            "seule."
        )
    elif c_ran and not c_strong and a_strong and b_strong:
        variable = "aucune nette"
        detail = (
            "A et B bougent, mais C — le seul levier d'écart à rayon et "
            "nombre figés — ne tranche pas. Un résultat qui ne tranche "
            "pas est un résultat."
        )
    elif a_strong and not b_strong:
        variable = "nombre"
        detail = (
            "À rayon de bague figé, le coût suit l'effectif. À effectif "
            "figé, changer le rayon ne suffit pas à exploser. C n'a pas "
            "été lancée."
        )
    elif b_strong and not a_strong:
        variable = "courbure"
        detail = (
            "À effectif figé, le coût explose sur le jonc serré et passe "
            "sur le bracelet. À rayon de bague figé, l'effectif ne "
            "suffit pas à exploser. C n'a pas été lancée."
        )
    elif not a_strong and not b_strong:
        variable = "aucune nette"
        detail = (
            "Ni le nombre (A) ni la courbure (B) n'ont fait exploser le "
            "coût dans la plage mesurée. C n'a pas été lancée : A et B "
            "suffisent à dire qu'aucune des deux ne décide ici."
        )
    else:
        variable = "aucune nette"
        detail = (
            "A et B varient toutes les deux ; C n'a pas tranché plus "
            "nettement. Pas de conclusion arrangée."
        )
    return {
        "variable": variable,
        "detail": detail,
        "campagne_c_lancee": c_ran,
        "A_fort": a_strong,
        "B_fort": b_strong,
        "C_fort": c_strong if c_ran else None,
        "ratio_A": (camp_a.get("effet") or {}).get("ratio"),
        "ratio_B": (camp_b.get("effet") or {}).get("ratio"),
        "ratio_C": (camp_c.get("effet") or {}).get("ratio") if c_ran else None,
    }


def _fmt(value, digits=2):
    if value is None:
        return "—"
    text = "{:.{digits}f}".format(float(value), digits=digits)
    return text.replace(".", ",")


def _print_table(campaign):
    print("\nCampagne {} — fixe : {} ; varie : {} — {}".format(
        campaign["id"], campaign["fixe"], campaign["varie"],
        campaign["question"]), flush=True)
    header = (
        " pierres  rayon  entraxe     Ø   écart  régime                      "
        "t(s)   RSS    statut")
    print(header, flush=True)
    for row in campaign.get("mesures") or []:
        if row.get("ok") and row.get("total_s") is not None:
            statut = "ok"
            t_s = _fmt(row.get("total_s"), 2)
        elif row.get("aborted"):
            statut = str(row.get("aborted"))
            t_s = "plafond" if row.get("aborted") in ("rss", "temps") else "—"
        else:
            statut = "échec"
            t_s = "—"
        rss = _fmt(row.get("rss_pic_gi"), 2)
        print(" {:>7}  {:>5}  {:>7}  {:>4}  {:>6}  {:<28} {:>6}  {:>5}  {}".format(
            row.get("pierres"),
            _fmt(row.get("rayon_mm"), 2),
            _fmt(row.get("entraxe_mm"), 3),
            _fmt(row.get("diametre_mm"), 2),
            _fmt(row.get("ecart_sieges_mm"), 3),
            (row.get("regime") or "")[:28],
            t_s,
            rss,
            statut,
        ), flush=True)


def orchestrate():
    camp_a = run_campaign("A")
    camp_b = run_campaign("B")
    why_c = _c_needed_reason(camp_a, camp_b)
    if why_c:
        camp_c = run_campaign("C")
        camp_c["lancee"] = True
        camp_c["raison"] = why_c
    else:
        camp_c = {
            "id": "C",
            "lancee": False,
            "raison": (
                "A et B suffisent à désigner une cause — C n'est pas lancée"
            ),
            "fixe": CAMPAIGNS["C"]["fixe"],
            "varie": CAMPAIGNS["C"]["varie"],
            "question": CAMPAIGNS["C"]["question"],
            "mesures": [],
            "effet": None,
        }
    verdict = _verdict(camp_a, camp_b, camp_c)
    report = {
        "sonde": "P040 une variable à la fois",
        "plafond_rss_gi": CEILING_RSS_KIB / (1024 * 1024),
        "plafond_s": CEILING_SECONDS,
        "campagnes": {"A": camp_a, "B": camp_b, "C": camp_c},
        "verdict": verdict,
    }
    first_rows = camp_a.get("mesures") or camp_b.get("mesures") or []
    if first_rows:
        report["machine"] = first_rows[0].get("machine")
        report["plateforme"] = first_rows[0].get("plateforme")
    print(json.dumps(report, ensure_ascii=False, indent=1), flush=True)
    _print_table(camp_a)
    _print_table(camp_b)
    if camp_c.get("lancee"):
        _print_table(camp_c)
    else:
        print("\nCampagne C — non lancée : {}".format(
            camp_c.get("raison")), flush=True)
    print("\nVERDICT : {} — {}".format(
        verdict.get("variable"), verdict.get("detail")), flush=True)
    return report


def _load_spec():
    raw = (os.environ.get(_SPEC_ENV) or "").strip()
    if not raw:
        return None
    spec = json.loads(raw)
    geom = geometry_of(spec["pierres"], spec["rayon_mm"], spec["diametre_mm"])
    geom["campagne"] = spec.get("campagne")
    return geom


def main():
    spec = _load_spec()
    if spec is not None:
        measure_one(spec)
        return
    orchestrate()


main()

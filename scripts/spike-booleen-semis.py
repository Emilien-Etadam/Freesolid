"""Sonde P039 — le booléen d'un semis : courbe temps + mémoire.

Usage :  freecadcmd scripts/spike-booleen-semis.py

Mesure le geste réel (``Kernel.add_boolean`` sur un ``App::Link``), pas un
``Part.cut`` de cônes. Pour 25, 50, 100 et 200 pierres : durée du compound,
durée du booléen, RSS de pic. Un plafond mémoire et un plafond temps
arrêtent proprement plutôt que de faire ramer la machine.

Chaque effectif tourne dans un processus fils — ``ru_maxrss`` est un
maximum de processus, et un 200 qui s'étouffe ne doit pas emporter les
mesures déjà prises.
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

COUNTS = (25, 50, 100, 200)
PAS_MM = 1.5
DIAMETRE_MM = 1.5
LIFT_MM = -0.25
PAD_HEIGHT_MM = 6.0

#: Plafond RSS — en dessous des ~13 Go où P037 a vu le processus mourir
#: sur une VM de 15 Go, avec une marge pour le système.
CEILING_RSS_KIB = 8 * 1024 * 1024  # 8 GiB
CEILING_SECONDS = 360  # 6 min par effectif

_MARKER = "SPIKE_N_JSON:"
_COUNT_ENV = "FREESOLID_SPIKE_N"
_RESULT_ENV = "FREESOLID_SPIKE_RESULT"


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


def ring_radius_mm(count):
    """Rayon du jonc à entraxe constant — seul le nombre de sièges varie."""
    return max(10.0, count * PAS_MM / (2.0 * math.pi))


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


def measure_one(count):
    """Un effectif, un document, le geste ``add_boolean`` réel."""
    from engine.kernel import Kernel
    from engine.platform import allow_from_environ, version_status

    result_path = os.environ.get(_RESULT_ENV) or ""
    kernel = Kernel()
    plateforme = version_status(
        kernel.ping()["freecad"], allow=allow_from_environ())
    out = {
        "pierres": count,
        "plateforme": plateforme,
        "machine": machine_info(plateforme["running"]),
        "rss_avant_kib": rss_kib(),
        "aborted": None,
    }
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
        radius = ring_radius_mm(count)
        t_pose0 = time.perf_counter()
        kernel.new_part("Sonde {} pierres".format(count))
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
            diametre=DIAMETRE_MM, lift=LIFT_MM)
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
        out["rayon_mm"] = round(radius, 3)
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


def run_child(count):
    result_path = os.path.join(
        tempfile.gettempdir(), "spike-booleen-semis-n{}.json".format(count))
    try:
        os.remove(result_path)
    except OSError:
        pass
    env = os.environ.copy()
    env[_COUNT_ENV] = str(count)
    env[_RESULT_ENV] = result_path
    env["FREESOLID_NO_SERVE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    print("spike> lancement N={} (plafond {} GiB, {} s)".format(
        count, CEILING_RSS_KIB / (1024 * 1024), CEILING_SECONDS), flush=True)
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
        if aborted and not payload.get("aborted"):
            payload["aborted"] = aborted
            payload["ok"] = False
            if last_rss is not None:
                payload["rss_pic_kib"] = last_rss
                payload["rss_pic_gi"] = round(last_rss / (1024 * 1024), 2)
        return payload
    if aborted:
        out = {
            "pierres": count,
            "aborted": aborted,
            "ok": False,
            "erreur": (
                "plafond mémoire {} GiB".format(CEILING_RSS_KIB / (1024 * 1024))
                if aborted == "rss"
                else "plafond {} s dépassé".format(CEILING_SECONDS)
            ),
        }
        if last_rss is not None:
            out["rss_pic_kib"] = last_rss
            out["rss_pic_gi"] = round(last_rss / (1024 * 1024), 2)
        return out
    return {
        "pierres": count,
        "ok": False,
        "aborted": "fils",
        "code": proc.returncode,
        "erreur": "pas de JSON (code {})".format(proc.returncode),
        "stderr": (stderr or "")[-400:],
        "stdout": (stdout or "")[-400:],
    }


def _verdict(rows):
    """Le coût est-il linéaire, ou explose-t-il ?"""
    measured = [
        r for r in rows
        if r.get("ok") and isinstance(r.get("total_s"), (int, float))
    ]
    if len(measured) < 2:
        return {
            "courbe": "insuffisant",
            "detail": "moins de deux points aboutis — pas de pente",
        }
    rates = [
        (r["pierres"], r["total_s"] / r["pierres"], r.get("rss_pic_gi"))
        for r in measured
    ]
    first_n, first_rate, _ = rates[0]
    last_n, last_rate, last_rss = rates[-1]
    ratio = last_rate / first_rate if first_rate > 1e-9 else None
    exploding = bool(ratio is not None and ratio >= 2.0)
    aborted = [r for r in rows if r.get("aborted")]
    if aborted and not exploding:
        exploding = True
    return {
        "courbe": "explose" if exploding else "quasi-linéaire",
        "ms_par_pierre": {
            str(n): round(rate * 1000.0, 1) for n, rate, _ in rates
        },
        "ratio_dernier_sur_premier": (
            round(ratio, 2) if ratio is not None else None),
        "premier": first_n,
        "dernier_abouti": last_n,
        "rss_pic_gi_dernier": last_rss,
        "avortés": [
            {"pierres": r.get("pierres"), "cause": r.get("aborted")}
            for r in aborted
        ],
    }


def orchestrate():
    rows = [run_child(n) for n in COUNTS]
    report = {
        "sonde": "P039 booléen d'un semis",
        "counts": list(COUNTS),
        "plafond_rss_gi": CEILING_RSS_KIB / (1024 * 1024),
        "plafond_s": CEILING_SECONDS,
        "mesures": rows,
        "verdict": _verdict(rows),
    }
    if rows:
        report["machine"] = rows[0].get("machine")
        report["plateforme"] = rows[0].get("plateforme")
    print(json.dumps(report, ensure_ascii=False, indent=1), flush=True)
    verdict = report["verdict"]
    print("\nSONDE {} — {} (ratio ×{})".format(
        "VERTE" if verdict.get("courbe") in ("quasi-linéaire", "explose")
        and any(r.get("ok") for r in rows) else "ROUGE",
        verdict.get("courbe"),
        verdict.get("ratio_dernier_sur_premier")), flush=True)
    return report


def main():
    raw = (os.environ.get(_COUNT_ENV) or "").strip()
    if raw:
        measure_one(int(raw))
        return
    orchestrate()


main()

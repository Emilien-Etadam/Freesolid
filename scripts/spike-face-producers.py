"""Sonde P038 — `_face_producers` apparie-t-il les faces d'un bossage ?

Usage :  freecadcmd scripts/spike-face-producers.py

Mesure avant correction : hashCode lève-t-il, l'index est-il vide, et
combien de faces sur combien trouvent leur fonction ?  ``isSame`` est
chronométré en repli, pas comme pari.
"""

import json
import os
import sys
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

from engine.kernel import Kernel  # noqa: E402

R = {}


def note(key, fn):
    try:
        R[key] = fn()
    except Exception as exc:  # noqa: BLE001 — un échec est un résultat
        R[key] = None
        R[key + "_error"] = "{}: {}".format(type(exc).__name__, str(exc)[:200])


def call_bool(face, name, other):
    method = getattr(face, name, None)
    if not callable(method):
        return "absent"
    try:
        return bool(method(other))
    except Exception as exc:  # noqa: BLE001
        return "{}: {}".format(type(exc).__name__, str(exc)[:80])


def geo_key(face):
    com = face.CenterOfMass
    return (round(float(face.Area), 6),
            round(float(com.x), 4),
            round(float(com.y), 4),
            round(float(com.z), 4))


def count_pairs(tip_faces, feat_faces, pred):
    matched = 0
    errors = 0
    used = set()
    for tip in tip_faces:
        for i, feat in enumerate(feat_faces):
            if i in used:
                continue
            try:
                if pred(tip, feat):
                    matched += 1
                    used.add(i)
                    break
            except Exception:  # noqa: BLE001
                errors += 1
                break
    return matched, errors


def main():
    kernel = Kernel()
    R["freecad"] = kernel.ping()["freecad"]
    kernel.new_part("Sonde P038")
    kernel.add_rect_sketch(40, 30)
    kernel.add_pad(10)

    body = kernel._require_body()
    faces = list(body.Shape.Faces)
    R["faces"] = len(faces)
    R["tip"] = body.Tip.Name if getattr(body, "Tip", None) else None

    def probe_hash(face):
        hasher = getattr(face, "hashCode", None)
        if hasher is None:
            return {"absent": True}
        try:
            digest = hasher()
            return {"digest": digest, "type": type(digest).__name__}
        except TypeError:
            try:
                digest = hasher(2 ** 31 - 1)
                return {"digest": digest, "type": type(digest).__name__,
                        "arity": 1}
            except Exception as exc:  # noqa: BLE001
                return {"error": "{}: {}".format(
                    type(exc).__name__, str(exc)[:160])}
        except Exception as exc:  # noqa: BLE001
            return {"error": "{}: {}".format(type(exc).__name__, str(exc)[:160])}

    R["hash_tip"] = [probe_hash(f) for f in faces]
    R["hash_self_ok"] = all(
        f.hashCode() == f.hashCode() for f in faces)

    pad = next(o for o in body.Group if o.TypeId == "PartDesign::Pad")
    pad_faces = list(getattr(pad.Shape, "Faces", ()) or ())
    R["pad_faces"] = len(pad_faces)
    R["hash_pad"] = [probe_hash(f) for f in pad_faces[:8]]

    tip_digests = [h.get("digest") for h in R["hash_tip"] if "digest" in h]
    pad_digests = [h.get("digest") for h in R["hash_pad"] if "digest" in h]
    R["hash_overlap"] = len(set(tip_digests) & set(pad_digests))

    R["isSame_self"] = call_bool(faces[0], "isSame", faces[0])
    R["isEqual_self"] = call_bool(faces[0], "isEqual", faces[0])
    R["isPartner_self"] = call_bool(faces[0], "isPartner", faces[0])
    R["shape_isSame"] = call_bool(body.Shape, "isSame", pad.Shape)
    R["shape_isEqual"] = call_bool(body.Shape, "isEqual", pad.Shape)

    t0 = time.perf_counter()
    same, same_err = count_pairs(
        faces, pad_faces, lambda a, b: a.isSame(b))
    R["isSame_matched"] = same
    R["isSame_errors"] = same_err
    R["isSame_ms"] = round((time.perf_counter() - t0) * 1000, 3)

    t0 = time.perf_counter()
    equal, equal_err = count_pairs(
        faces, pad_faces, lambda a, b: a.isEqual(b))
    R["isEqual_matched"] = equal
    R["isEqual_errors"] = equal_err
    R["isEqual_ms"] = round((time.perf_counter() - t0) * 1000, 3)

    t0 = time.perf_counter()
    partner, partner_err = count_pairs(
        faces, pad_faces, lambda a, b: a.isPartner(b))
    R["isPartner_matched"] = partner
    R["isPartner_errors"] = partner_err
    R["isPartner_ms"] = round((time.perf_counter() - t0) * 1000, 3)

    t0 = time.perf_counter()
    geo, geo_err = count_pairs(
        faces, pad_faces, lambda a, b: geo_key(a) == geo_key(b))
    R["geo_matched"] = geo
    R["geo_errors"] = geo_err
    R["geo_ms"] = round((time.perf_counter() - t0) * 1000, 3)
    R["geo_keys_tip"] = [list(geo_key(f)) for f in faces]
    R["geo_keys_pad"] = [list(geo_key(f)) for f in pad_faces]

    producers = kernel._face_producers()
    R["producers"] = {str(k): v for k, v in sorted(producers.items())}
    R["matched"] = len(producers)
    R["matched_over_faces"] = "{}/{}".format(len(producers), len(faces))
    R["face_match"] = dict(kernel._face_match)

    mesh = kernel.tessellate()
    groups = mesh.get("groups") or []
    with_feature = sum(1 for g in groups if g.get("feature"))
    R["mesh_groups"] = len(groups)
    R["mesh_with_feature"] = with_feature
    R["mesh_over_groups"] = "{}/{}".format(with_feature, len(groups))

    # Pièce à deux fonctions : le repli Tip masquerait un échec d'appariement.
    kernel.add_rect_sketch(10, 10, face=kernel._top_face_id())
    kernel.add_pocket(through=True)
    producers2 = kernel._face_producers()
    body2 = kernel._require_body()
    R["after_pocket_faces"] = len(body2.Shape.Faces)
    R["after_pocket_producers"] = {
        str(k): v for k, v in sorted(producers2.items())
    }
    R["after_pocket_unique"] = sorted(set(producers2.values()))

    print(json.dumps(R, ensure_ascii=False, indent=2), flush=True)


main()

"""Esquisse 3D : définition et solveur.

Une esquisse 3D est un ensemble de points (partagés : deux lignes qui se
touchent ont le même point) et d'entités qui s'appuient dessus — lignes,
splines par points de passage, points seuls — plus des cotes (longueur
d'une ligne, distance entre deux points, angle entre deux lignes) et des
relations (ligne le long de l'axe X, Y ou Z). Un point peut être lié à un
sommet ou un centre de la pièce : il la suit et ne bouge pas au solveur.

Le solveur cherche les positions qui tiennent toutes les cotes et
relations en bougeant le moins possible les points (pas de Gauss-Newton
de norme minimale, jacobien par différences finies). Même calcul côté
client (``app/sketch3dmath.js``) : l'aperçu pendant un glisser est ce que
le moteur enregistrera. Module pur, testé en CI.
"""

import math

AXES = "XYZ"
TOL = 1e-9          # résidu visé (mm)
TOL_OK = 1e-6       # au-delà : cotes ou relations en conflit


def _num(value, default=None):
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def _index(value, count):
    try:
        i = int(value)
    except (TypeError, ValueError):
        return None
    return i if 0 <= i < count else None


def clean_spec(spec):
    """Définition nettoyée : indices valides, valeurs numériques, entrées
    inconnues retirées. Ne renvoie jamais d'erreur : ce qui ne tient pas
    tombe."""
    spec = spec if isinstance(spec, dict) else {}
    points = []
    for p in spec.get("points") or ():
        try:
            xyz = [float(v) for v in list(p)[:3]]
        except (TypeError, ValueError):
            xyz = [0.0, 0.0, 0.0]
        while len(xyz) < 3:
            xyz.append(0.0)
        points.append(xyz)
    n = len(points)
    raw_links = list(spec.get("links") or ())
    links = [raw_links[i] if i < len(raw_links)
             and (raw_links[i] is True or isinstance(raw_links[i], dict))
             else None for i in range(n)]
    entities = []
    for e in spec.get("entities") or ():
        if not isinstance(e, dict):
            continue
        kind = e.get("type")
        construction = bool(e.get("construction"))
        if kind == "line":
            a, b = _index(e.get("a"), n), _index(e.get("b"), n)
            if a is not None and b is not None and a != b:
                entities.append({"type": "line", "a": a, "b": b,
                                 "construction": construction})
        elif kind == "spline":
            pts = [_index(i, n) for i in e.get("pts") or ()]
            if len(pts) >= 2 and None not in pts:
                tangents = list(e.get("tangents") or ())
                tangents = [t if isinstance(t, dict) else None
                            for t in tangents[:len(pts)]]
                tangents += [None] * (len(pts) - len(tangents))
                entities.append({"type": "spline", "pts": pts,
                                 "closed": bool(e.get("closed")),
                                 "tangents": tangents,
                                 "construction": construction})
        elif kind == "point":
            p = _index(e.get("p"), n)
            if p is not None:
                entities.append({"type": "point", "p": p})
    m = len(entities)
    lines = {i for i, e in enumerate(entities) if e["type"] == "line"}
    dims = []
    for d in spec.get("dims") or ():
        if not isinstance(d, dict):
            continue
        value = _num(d.get("value"))
        if value is None:
            continue
        kind = d.get("type")
        if kind == "length":
            e = _index(d.get("entity"), m)
            if e in lines and value > 0:
                dims.append({"type": "length", "entity": e, "value": value})
        elif kind == "distance":
            p1, p2 = _index(d.get("p1"), n), _index(d.get("p2"), n)
            if p1 is not None and p2 is not None and p1 != p2 and value > 0:
                dims.append({"type": "distance", "p1": p1, "p2": p2,
                             "value": value})
        elif kind == "angle":
            e1, e2 = _index(d.get("e1"), m), _index(d.get("e2"), m)
            if e1 in lines and e2 in lines and e1 != e2 \
                    and 0 <= value <= 180:
                dims.append({"type": "angle", "e1": e1, "e2": e2,
                             "value": value})
    relations = []
    for r in spec.get("relations") or ():
        if not isinstance(r, dict):
            continue
        if r.get("type") == "axis":
            e = _index(r.get("entity"), m)
            axis = str(r.get("axis") or "")
            if e in lines and axis in ("X", "Y", "Z"):
                relations.append({"type": "axis", "entity": e,
                                  "axis": axis})
    return {"points": points, "links": links, "entities": entities,
            "dims": dims, "relations": relations}


def _sub(a, b):
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def _norm(a):
    return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])


def _angle(spec, points, e1, e2):
    """Angle (radians) entre deux lignes, et une longueur d'échelle. Si
    elles partagent un point, angle entre les deux branches qui en
    partent ; sinon, entre leurs directions."""
    l1, l2 = spec["entities"][e1], spec["entities"][e2]
    ends1, ends2 = (l1["a"], l1["b"]), (l2["a"], l2["b"])
    shared = [p for p in ends1 if p in ends2]
    if shared:
        c = shared[0]
        o1 = ends1[1] if ends1[0] == c else ends1[0]
        o2 = ends2[1] if ends2[0] == c else ends2[0]
        u, v = _sub(points[o1], points[c]), _sub(points[o2], points[c])
    else:
        u = _sub(points[l1["b"]], points[l1["a"]])
        v = _sub(points[l2["b"]], points[l2["a"]])
    cross = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2],
             u[0] * v[1] - u[1] * v[0]]
    dot = u[0] * v[0] + u[1] * v[1] + u[2] * v[2]
    return math.atan2(_norm(cross), dot), (_norm(u) + _norm(v)) / 2.0


def measure(spec, points, dim):
    """Valeur actuelle d'une cote (mm ou degrés)."""
    kind = dim["type"]
    if kind == "length":
        line = spec["entities"][dim["entity"]]
        return _norm(_sub(points[line["b"]], points[line["a"]]))
    if kind == "distance":
        return _norm(_sub(points[dim["p2"]], points[dim["p1"]]))
    angle, _ = _angle(spec, points, dim["e1"], dim["e2"])
    return math.degrees(angle)


def residuals(spec, points):
    """Écarts de chaque cote et relation (mm ; un angle est ramené à des
    mm par la longueur des branches)."""
    out = []
    for rel in spec["relations"]:
        line = spec["entities"][rel["entity"]]
        a, b = points[line["a"]], points[line["b"]]
        k = AXES.index(rel["axis"])
        out.extend(b[j] - a[j] for j in range(3) if j != k)
    for dim in spec["dims"]:
        if dim["type"] == "angle":
            angle, scale = _angle(spec, points, dim["e1"], dim["e2"])
            out.append((angle - math.radians(dim["value"])) * max(scale, 1.0))
        else:
            out.append(measure(spec, points, dim) - dim["value"])
    return out


def constrained_points(spec):
    """Points touchés par une cote ou une relation (les seuls que le
    solveur déplace)."""
    used = set()
    ents = spec["entities"]
    for rel in spec["relations"]:
        used.update((ents[rel["entity"]]["a"], ents[rel["entity"]]["b"]))
    for dim in spec["dims"]:
        if dim["type"] == "length":
            used.update((ents[dim["entity"]]["a"], ents[dim["entity"]]["b"]))
        elif dim["type"] == "distance":
            used.update((dim["p1"], dim["p2"]))
        else:
            for e in (dim["e1"], dim["e2"]):
                used.update((ents[e]["a"], ents[e]["b"]))
    return sorted(used)


def _solve_linear(matrix, rhs):
    size = len(matrix)
    a = [row[:] + [rhs[i]] for i, row in enumerate(matrix)]
    for col in range(size):
        pivot = max(range(col, size), key=lambda r: abs(a[r][col]))
        if abs(a[pivot][col]) < 1e-300:
            raise ValueError("système singulier")
        a[col], a[pivot] = a[pivot], a[col]
        for row in range(col + 1, size):
            factor = a[row][col] / a[col][col]
            if factor:
                for k in range(col, size + 1):
                    a[row][k] -= factor * a[col][k]
    out = [0.0] * size
    for row in range(size - 1, -1, -1):
        acc = a[row][size] - sum(a[row][k] * out[k]
                                 for k in range(row + 1, size))
        out[row] = acc / a[row][row]
    return out


def solve(spec, fixed=(), max_iter=60):
    """Positions qui tiennent cotes et relations. ``fixed`` : points qui ne
    bougent pas (en plus des points liés à la pièce). Rend
    ``{"points", "ok", "residual"}`` — ``ok`` faux : conflit (le résultat
    est alors le meilleur trouvé)."""
    spec = clean_spec(spec)
    points = [p[:] for p in spec["points"]]
    locked = set(int(i) for i in fixed or ())
    locked.update(i for i, link in enumerate(spec["links"]) if link)
    free = [i for i in constrained_points(spec) if i not in locked]
    variables = [(i, k) for i in free for k in range(3)]

    def cost(r):
        return sum(v * v for v in r)

    r = residuals(spec, points)
    for _ in range(max_iter):
        if not r or max(abs(v) for v in r) < TOL or not variables:
            break
        jac = []
        for i, k in variables:
            keep = points[i][k]
            h = 1e-7 * max(1.0, abs(keep))
            points[i][k] = keep + h
            shifted = residuals(spec, points)
            points[i][k] = keep
            jac.append([(s - v) / h for s, v in zip(shifted, r)])
        m = len(r)
        # Pas de norme minimale : (J Jᵀ + μ I) y = r, δ = -Jᵀ y.
        normal = [[sum(col[a] * col[b] for col in jac) for b in range(m)]
                  for a in range(m)]
        mu = 1e-12 * (1.0 + max(normal[a][a] for a in range(m)))
        for a in range(m):
            normal[a][a] += mu
        try:
            y = _solve_linear(normal, r)
        except ValueError:
            break
        step = [-sum(col[a] * y[a] for a in range(m)) for col in jac]
        base = cost(r)
        t = 1.0
        accepted = False
        while t > 1e-4:
            trial = [p[:] for p in points]
            for (i, k), d in zip(variables, step):
                trial[i][k] += t * d
            r_trial = residuals(spec, trial)
            if cost(r_trial) < base:
                points, r, accepted = trial, r_trial, True
                break
            t /= 2.0
        if not accepted:
            break
    worst = max((abs(v) for v in r), default=0.0)
    return {"points": points, "ok": worst < TOL_OK, "residual": worst}


def chains(spec):
    """Entités tracées (hors construction et points seuls) — pour le
    moteur : chacune devient une arête."""
    return [i for i, e in enumerate(spec["entities"])
            if e["type"] in ("line", "spline") and not e["construction"]]

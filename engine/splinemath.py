"""Spline par points de passage, avec poignées de tangente.

Une spline FreeSolid est une suite de points de passage ; entre deux
points, un arc cubique (forme d'Hermite). La pente en chaque point est
soit libre (la courbe y reste lisse, de classe C2, et les bouts suivent
la règle « pas de nœud » : les deux premiers arcs, comme les deux
derniers, forment une seule cubique), soit pilotée : une direction et
deux longueurs, entrée et sortie, qui peuvent différer (poignée
asymétrique). Le paramètre est la longueur des cordes : une pente de
longueur 1 est la vitesse « naturelle ».

Même calcul côté client (``app/splinemath.js``) : l'aperçu pendant un
glisser est exactement la courbe que le moteur construira. Module pur,
testé en CI ; la construction de la B-spline FreeCAD est dans
``splineedit.py``.
"""

import math

TOL = 1e-9


def _sub(a, b):
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def _add(a, b):
    return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]


def _mul(a, k):
    return [a[0] * k, a[1] * k, a[2] * k]


def _norm(a):
    return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])


def as_points(points):
    """Points en triplets de flottants (z = 0 pour un point 2D)."""
    out = []
    for p in points or ():
        values = [float(v) for v in p][:3]
        while len(values) < 3:
            values.append(0.0)
        out.append(values)
    return out


def clean_tangents(tangents, count):
    """Une entrée par point : None (pente libre) ou
    ``{"dir": [x, y, z], "in": l, "out": l}`` — direction unitaire,
    longueurs positives. Les entrées invalides deviennent libres."""
    out = []
    source = list(tangents or ())
    for i in range(count):
        spec = source[i] if i < len(source) else None
        if not isinstance(spec, dict):
            out.append(None)
            continue
        try:
            direction = as_points([spec.get("dir")])[0]
            length_in = float(spec.get("in", 1.0))
            length_out = float(spec.get("out", 1.0))
        except (TypeError, ValueError, IndexError):
            out.append(None)
            continue
        size = _norm(direction)
        if size < TOL or not (length_in > 0 and length_out > 0):
            out.append(None)
            continue
        out.append({"dir": _mul(direction, 1.0 / size),
                    "in": length_in, "out": length_out})
    return out


def chords(points, closed):
    """Longueur de corde de chaque arc (n - 1 arcs ouverte, n fermée)."""
    n = len(points)
    count = n if closed else n - 1
    return [_norm(_sub(points[(i + 1) % n], points[i]))
            for i in range(count)]


def _solve_dense(matrix, rhs):
    """Élimination de Gauss avec pivot partiel ; ``rhs`` : une colonne
    de vecteurs 3D par ligne."""
    size = len(matrix)
    a = [row[:] for row in matrix]
    b = [r[:] for r in rhs]
    for col in range(size):
        pivot = max(range(col, size), key=lambda r: abs(a[r][col]))
        if abs(a[pivot][col]) < 1e-14:
            raise ValueError("système singulier")
        a[col], a[pivot] = a[pivot], a[col]
        b[col], b[pivot] = b[pivot], b[col]
        for row in range(col + 1, size):
            factor = a[row][col] / a[col][col]
            if factor == 0.0:
                continue
            for k in range(col, size):
                a[row][k] -= factor * a[col][k]
            b[row] = _sub(b[row], _mul(b[col], factor))
    out = [None] * size
    for row in range(size - 1, -1, -1):
        acc = b[row]
        for k in range(row + 1, size):
            acc = _sub(acc, _mul(out[k], a[row][k]))
        out[row] = _mul(acc, 1.0 / a[row][row])
    return out


def solve(points, closed=False, tangents=None):
    """Pentes (entrée, sortie) en chaque point : ``(m_in, m_out)``.

    Les points pilotés imposent leur pente ; les autres la reçoivent du
    raccord C2 (continuité de la dérivée seconde) et, aux bouts d'une
    courbe ouverte, de la règle « pas de nœud » (deux points libres après
    le bout) ou de la courbure nulle (sinon). Trois points libres : une
    parabole ; deux : un segment."""
    pts = as_points(points)
    n = len(pts)
    tans = clean_tangents(tangents, n)
    if n < 2:
        return [], []
    h = chords(pts, closed)
    if any(length < TOL for length in h):
        raise ValueError("deux points consécutifs sont confondus")
    spans = len(h)

    def nxt(i):
        return (i + 1) % n

    def prv(i):
        return (i - 1) % n

    slope = [_mul(_sub(pts[nxt(i)], pts[i]), 1.0 / h[i])
             for i in range(spans)]
    fixed_in = [None] * n
    fixed_out = [None] * n
    for i, spec in enumerate(tans):
        if spec is not None:
            fixed_in[i] = _mul(spec["dir"], spec["in"])
            fixed_out[i] = _mul(spec["dir"], spec["out"])
    free = [i for i in range(n) if tans[i] is None]
    index = {p: k for k, p in enumerate(free)}
    m_in = list(fixed_in)
    m_out = list(fixed_out)
    if free:
        size = len(free)
        matrix = [[0.0] * size for _ in range(size)]
        rhs = [[0.0, 0.0, 0.0] for _ in range(size)]

        def term(row, point, coeff, side):
            """coeff × pente (côté ``side``) du point ``point``."""
            if point in index:
                matrix[row][index[point]] += coeff
            else:
                known = fixed_in[point] if side == "in" else fixed_out[point]
                rhs[row] = _sub(rhs[row], _mul(known, coeff))

        def third(row, span, sign):
            """sign × D3 de l'arc ``span`` (à un facteur 6 près) :
            (m_début + m_fin - 2 pente) / h²."""
            k = sign / (h[span] * h[span])
            term(row, span, k, "out")
            term(row, nxt(span), k, "in")
            rhs[row] = _add(rhs[row], _mul(slope[span], 2.0 * k))

        def first_free(i):
            return i in index

        for row, i in enumerate(free):
            interior = closed or 0 < i < n - 1
            if interior:
                a, b = prv(i), i  # arcs avant / après le point
                term(row, a, h[b], "out")
                matrix[row][row] += 2.0 * (h[a] + h[b])
                term(row, nxt(i), h[a], "in")
                rhs[row] = _add(rhs[row], _mul(
                    _add(_mul(slope[a], h[b]), _mul(slope[b], h[a])), 3.0))
            elif i == 0:
                if n >= 4 and first_free(1):
                    third(row, 0, 1.0)
                    third(row, 1, -1.0)
                elif n == 3 and first_free(1):
                    third(row, 0, 1.0)
                else:
                    # Courbure nulle au départ : 2 m0 + m1 = 3 pente.
                    matrix[row][row] += 2.0
                    term(row, 1, 1.0, "in")
                    rhs[row] = _add(rhs[row], _mul(slope[0], 3.0))
            else:
                last = spans - 1
                if n >= 4 and first_free(n - 2):
                    third(row, last, 1.0)
                    third(row, last - 1, -1.0)
                elif n == 3 and first_free(1):
                    third(row, last, 1.0)
                else:
                    term(row, n - 2, 1.0, "out")
                    matrix[row][row] += 2.0
                    rhs[row] = _add(rhs[row], _mul(slope[last], 3.0))
        values = _solve_dense(matrix, rhs)
        for i in free:
            m_in[i] = values[index[i]]
            m_out[i] = values[index[i]]
    return m_in, m_out


def controls(points, closed=False, tangents=None):
    """Pôles de Bézier de chaque arc : ``[[B0, B1, B2, B3], …]``."""
    pts = as_points(points)
    m_in, m_out = solve(pts, closed, tangents)
    n = len(pts)
    out = []
    for i, length in enumerate(chords(pts, closed)):
        a, b = pts[i], pts[(i + 1) % n]
        out.append([a, _add(a, _mul(m_out[i], length / 3.0)),
                    _sub(b, _mul(m_in[(i + 1) % n], length / 3.0)), b])
    return out


def knots(points, closed=False):
    """Paramètres des points : longueurs de corde cumulées."""
    pts = as_points(points)
    out = [0.0]
    for length in chords(pts, closed):
        out.append(out[-1] + length)
    return out


def tangent_spec(m_in, m_out):
    """Pente pilotée tirée de deux dérivées (même direction)."""
    size_in, size_out = _norm(m_in), _norm(m_out)
    direction = m_out if size_out > TOL else m_in
    size = _norm(direction)
    if size < TOL:
        return None
    return {"dir": _mul(direction, 1.0 / size),
            "in": max(size_in, 1e-6), "out": max(size_out, 1e-6)}


def _close(a, b, tol):
    return _norm(_sub(a, b)) <= tol * max(1.0, _norm(a), _norm(b))


def classify(points, closed, m_in, m_out, tol=1e-6):
    """Tangentes minimales qui redonnent les pentes ``m_in``/``m_out`` :
    on part de tout piloté, puis chaque point redevient libre si la
    courbe n'en change pas."""
    pts = as_points(points)
    n = len(pts)
    tangents = [tangent_spec(m_in[i], m_out[i]) for i in range(n)]
    # Les bouts en dernier : leur règle dépend des points voisins libres.
    order = list(range(1, n - 1)) + [0, n - 1] if n > 2 else list(range(n))
    changed = True
    while changed:
        changed = False
        for i in order:
            if tangents[i] is None:
                continue
            trial = list(tangents)
            trial[i] = None
            try:
                got_in, got_out = solve(pts, closed, trial)
            except ValueError:
                continue
            if all(_close(got_in[j], m_in[j], tol)
                   and _close(got_out[j], m_out[j], tol) for j in range(n)):
                tangents = trial
                changed = True
    return tangents


def from_beziers(spans, closed=False, tol=1e-6):
    """Points et tangentes d'une suite d'arcs de Bézier cubiques bout à
    bout (dernier pôle d'un arc = premier du suivant)."""
    if not spans:
        return [], []
    pts = [as_points([s[0]])[0] for s in spans]
    if not closed:
        pts.append(as_points([spans[-1][3]])[0])
    n = len(pts)
    m_in = [[0.0, 0.0, 0.0] for _ in range(n)]
    m_out = [[0.0, 0.0, 0.0] for _ in range(n)]
    for i, span in enumerate(spans):
        b0, b1, b2, b3 = as_points(span)
        length = _norm(_sub(b3, b0))
        if length < TOL:
            raise ValueError("deux points consécutifs sont confondus")
        m_out[i] = _mul(_sub(b1, b0), 3.0 / length)
        m_in[(i + 1) % n] = _mul(_sub(b3, b2), 3.0 / length)
    if not closed:
        m_in[0] = m_out[0]
        m_out[-1] = m_in[-1]
    return pts, classify(pts, closed, m_in, m_out, tol)


def handle_tips(points, closed, tangents, i):
    """Bouts des poignées du point i : ``(entrée, sortie)`` — les pôles de
    Bézier voisins, None au bout d'une courbe ouverte."""
    pts = as_points(points)
    n = len(pts)
    spans = controls(pts, closed, tangents)
    tip_out = spans[i][1] if closed or i < n - 1 else None
    tip_in = spans[(i - 1) % n][2] if closed or i > 0 else None
    return tip_in, tip_out


def drag_tip(points, closed, tangents, i, side, target, alone=False):
    """Tangentes après avoir tiré le bout ``side`` ("in"/"out") de la
    poignée du point i en ``target`` (même règle que le client : la
    direction est commune, ``alone`` ne change que la longueur tirée)."""
    pts = as_points(points)
    n = len(pts)
    m_in, m_out = solve(pts, closed, tangents)
    h = chords(pts, closed)
    span = i if side == "out" else (i - 1) % n
    vec = _sub(as_points([target])[0], pts[i])
    if side == "in":
        vec = _mul(vec, -1.0)
    size = _norm(vec)
    out = clean_tangents(tangents, n)
    if size < TOL:
        return out
    length = size * 3.0 / h[span]
    old_in = _norm(m_in[i]) or 1.0
    old_out = _norm(m_out[i]) or 1.0
    l_in, l_out = old_in, old_out
    if side == "out":
        l_out = length
        if not alone:
            l_in = old_in / old_out * length
    else:
        l_in = length
        if not alone:
            l_out = old_out / old_in * length
    out[i] = {"dir": _mul(vec, 1.0 / size), "in": l_in, "out": l_out}
    return out

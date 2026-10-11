"""Icônes FreeSolid, version rapide, dans le style des icônes de Nodes :
volumes en dégradé bleu, points rouges, traits d'esquisse blancs, outils
gris métal. 32 x 32. L'utilisateur les redessinera proprement."""
import math
import os
import sys

OUT = sys.argv[1] if len(sys.argv) > 1 else "app/icons"

DEFS = """<defs>
<linearGradient id="gT" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#e4f0fc"/><stop offset="1" stop-color="#a9c3ee"/></linearGradient>
<linearGradient id="gL" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#a7c0f0"/><stop offset="1" stop-color="#6380cf"/></linearGradient>
<linearGradient id="gR" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#7d97dc"/><stop offset="1" stop-color="#3e58a8"/></linearGradient>
<linearGradient id="gC" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#6c88d4"/><stop offset=".35" stop-color="#c8e0f9"/><stop offset="1" stop-color="#4560b0"/></linearGradient>
<linearGradient id="gM" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#f4f5f7"/><stop offset="1" stop-color="#8d939b"/></linearGradient>
<linearGradient id="gP" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#c8e0f9" stop-opacity=".85"/><stop offset="1" stop-color="#637dca" stop-opacity=".55"/></linearGradient>
<linearGradient id="gG" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#b5ecc9"/><stop offset="1" stop-color="#2f9a5a"/></linearGradient>
<radialGradient id="gRed" cx=".35" cy=".35" r=".7"><stop offset="0" stop-color="#ff8a7d"/><stop offset="1" stop-color="#c40f08"/></radialGradient>
</defs>"""

EDGE = "#1f3570"
DARK = "#1b2230"
WHITE = "#f4f7fb"
RED = "#e0261d"


def svg(body):
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" '
            'viewBox="0 0 32 32">' + DEFS + body + "</svg>\n")


def f(v):
    return f"{v:.2f}".rstrip("0").rstrip(".")


def pts(points):
    return " ".join(f"{f(x)},{f(y)}" for x, y in points)


def poly(points, fill, stroke=EDGE, sw=0.8, extra=""):
    return (f'<polygon points="{pts(points)}" fill="{fill}" stroke="{stroke}" '
            f'stroke-width="{sw}" stroke-linejoin="round" {extra}/>')


def line(points, color=WHITE, sw=1.6, outline=True, dash=None, cap="round"):
    d = "M" + " L".join(f"{f(x)},{f(y)}" for x, y in points)
    return path(d, color, sw, outline, dash, cap)


def path(d, color=WHITE, sw=1.6, outline=True, dash=None, cap="round", fill="none"):
    da = f' stroke-dasharray="{dash}"' if dash else ""
    out = ""
    if outline:
        out += (f'<path d="{d}" fill="none" stroke="{DARK}" stroke-width="{sw + 1.6}" '
                f'stroke-linecap="{cap}" stroke-linejoin="round" stroke-opacity=".75"/>')
    out += (f'<path d="{d}" fill="{fill}" stroke="{color}" stroke-width="{sw}" '
            f'stroke-linecap="{cap}" stroke-linejoin="round"{da}/>')
    return out


def dot(x, y, r=2.3):
    return (f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(r)}" fill="url(#gRed)" '
            f'stroke="#6d0a05" stroke-width=".6"/>')


def text(x, y, s, size=9, color=WHITE, weight=700, anchor="middle"):
    return (f'<text x="{f(x)}" y="{f(y)}" font-family="Segoe UI, Arial, sans-serif" '
            f'font-size="{size}" font-weight="{weight}" fill="{color}" '
            f'text-anchor="{anchor}" stroke="{DARK}" stroke-width=".6" '
            f'paint-order="stroke">{s}</text>')


# -- projection isométrique ------------------------------------------------

def P(x, y, z, ox=16, oy=17, k=1.0):
    return (ox + (x - y) * 0.87 * k, oy + (x + y) * 0.5 * k - z * k)


def box(x, y, z, w, d, h, ox=16, oy=17, k=1.0, top="url(#gT)",
        left="url(#gL)", right="url(#gR)"):
    p = lambda a, b, c: P(a, b, c, ox, oy, k)
    x1, y1, z1 = x + w, y + d, z + h
    return (poly([p(x, y1, z), p(x1, y1, z), p(x1, y1, z1), p(x, y1, z1)], left)
            + poly([p(x1, y, z), p(x1, y1, z), p(x1, y1, z1), p(x1, y, z1)], right)
            + poly([p(x, y, z1), p(x1, y, z1), p(x1, y1, z1), p(x, y1, z1)], top))


def cylinder(cx, top, bottom, rx, ry, fill="url(#gC)", cap="url(#gT)"):
    body = (f'<path d="M{f(cx - rx)},{f(top)} L{f(cx - rx)},{f(bottom)} '
            f'A{f(rx)},{f(ry)} 0 0 0 {f(cx + rx)},{f(bottom)} L{f(cx + rx)},{f(top)} Z" '
            f'fill="{fill}" stroke="{EDGE}" stroke-width=".8"/>')
    return body + (f'<ellipse cx="{f(cx)}" cy="{f(top)}" rx="{f(rx)}" ry="{f(ry)}" '
                   f'fill="{cap}" stroke="{EDGE}" stroke-width=".8"/>')


def arrow_head(x, y, angle, size=4.5, color=WHITE):
    a = math.radians(angle)
    tip = (x, y)
    l = (x - size * math.cos(a - 0.5), y - size * math.sin(a - 0.5))
    r = (x - size * math.cos(a + 0.5), y - size * math.sin(a + 0.5))
    return poly([tip, l, r], color, DARK, 0.7)


def arc_arrow(cx, cy, r, a0, a1, color="#4f8fdb", sw=2.2, head=True):
    """Arc de a0 à a1 (degrés, sens horaire à l'écran), flèche au bout."""
    x0, y0 = cx + r * math.cos(math.radians(a0)), cy + r * math.sin(math.radians(a0))
    x1, y1 = cx + r * math.cos(math.radians(a1)), cy + r * math.sin(math.radians(a1))
    large = 1 if (a1 - a0) % 360 > 180 else 0
    sweep = 1 if a1 > a0 else 0
    out = path(f"M{f(x0)},{f(y0)} A{f(r)},{f(r)} 0 {large} {sweep} {f(x1)},{f(y1)}",
               color, sw, True)
    if head:
        tangent = a1 + (90 if sweep else -90)
        out += arrow_head(x1 + 1.5 * math.cos(math.radians(tangent)),
                          y1 + 1.5 * math.sin(math.radians(tangent)), tangent, 5, color)
    return out


def plane(points, fill="url(#gP)"):
    return poly(points, fill, "#3d5fb8", 1)


def page(x=6, y=3, w=18, h=24, fold=6):
    return poly([(x, y), (x + w - fold, y), (x + w, y + fold), (x + w, y + h), (x, y + h)],
                "url(#gM)", "#4b5058", 0.9) + poly(
        [(x + w - fold, y), (x + w - fold, y + fold), (x + w, y + fold)], "#c9cdd3", "#4b5058", 0.7)


ICONS = {}


def icon(name):
    def deco(fn):
        ICONS[name] = fn
        return fn
    return deco


# -- Fonctions ---------------------------------------------------------------

@icon("sketch")
def _():
    return (plane([(2, 20), (16, 12), (30, 20), (16, 28)])
            + line([(9, 20), (16, 16), (23, 20), (16, 24), (9, 20)])
            + dot(9, 20, 1.9) + dot(16, 16, 1.9) + dot(23, 20, 1.9) + dot(16, 24, 1.9)
            + poly([(19, 3), (24, 8), (14, 18), (11, 19), (12, 16)], "url(#gM)", "#4b5058", .8)
            + poly([(11, 19), (12, 16), (14, 18)], "#e9c46a", "#4b5058", .6))


@icon("body")
def _():
    return box(-7, -7, 0, 14, 14, 12, oy=15)


@icon("plane")
def _():
    return plane([(2, 18), (14, 8), (30, 14), (18, 24)]) + line(
        [(16, 16), (16, 4)], "#4f8fdb", 1.6) + arrow_head(16, 3, -90, 4.5, "#4f8fdb")


@icon("revolve")
def _():
    return cylinder(16, 11, 24, 9, 3.5) + arc_arrow(16, 11, 12, 200, 340, "#e9eef5", 1.8)


@icon("pocket")
def _():
    p = lambda a, b, c: P(a, b, c, 16, 14)
    return (box(-8, -8, 0, 16, 16, 9, oy=14)
            + poly([p(-4, -4, 9), p(4, -4, 9), p(4, 4, 9), p(-4, 4, 9)], "#25325a")
            + poly([p(-4, -4, 9), p(4, -4, 9), p(4, -4, 5), p(-4, -4, 5)], "#3a4f8c", EDGE, .6)
            + poly([p(-4, -4, 9), p(-4, 4, 9), p(-4, 4, 5), p(-4, -4, 5)], "#4d66ad", EDGE, .6))


@icon("groove")
def _():
    return (cylinder(16, 7, 26, 9, 3.5)
            + '<path d="M7,15 A9,3.5 0 0 0 25,15 L25,18 A9,3.5 0 0 1 7,18 Z" fill="#25325a" stroke="#1f3570" stroke-width=".6"/>'
            + path("M7,15 A9,3.5 0 0 0 25,15", RED, 1.2, False))


@icon("hole")
def _():
    return (box(-8, -8, 0, 16, 16, 8, oy=15)
            + '<ellipse cx="16" cy="7" rx="5.2" ry="3" fill="#1d2747" stroke="#1f3570" stroke-width=".8"/>'
            + '<path d="M11,7 A5.2,3 0 0 1 21,7" fill="none" stroke="#5a74bf" stroke-width="1.2"/>')


@icon("loft")
def _():
    return (poly([(5, 25), (16, 30), (27, 25), (16, 20)], "url(#gR)")
            + poly([(5, 25), (16, 20), (18, 6), (12, 9)], "url(#gL)")
            + poly([(16, 20), (27, 25), (21, 9), (18, 6)], "url(#gR)")
            + '<ellipse cx="16.5" cy="7.5" rx="4.6" ry="2.3" fill="url(#gT)" stroke="#1f3570" stroke-width=".8"/>')


@icon("sweep")
def _():
    d = "M6,26 C6,12 26,20 26,6"
    return (path(d, "#4b66b5", 7.5, True, cap="butt") + path(d, "#a9c3ee", 4, False, cap="butt")
            + path(d, WHITE, 1, False, dash="2 2")
            + '<ellipse cx="6" cy="26.5" rx="4" ry="1.8" fill="url(#gT)" stroke="#1f3570" stroke-width=".8"/>')


@icon("boolean")
def _():
    return (box(-9, -3, 0, 10, 10, 9, ox=13, oy=16)
            + box(-2, -9, 0, 10, 10, 13, ox=19, oy=17)
            + text(25, 30, "+", 11, "#6fbf8f"))


@icon("fillet")
def _():
    p = lambda a, b, c: P(a, b, c, 16, 15)
    r = 4
    arc = [p(8, -8 + 0, 10 - r + r * math.sin(math.radians(t))) for t in []]
    # Bloc dont l'arête avant droite du dessus est arrondie.
    pts_r = [p(8, -8, 0), p(8, 8, 0)]
    curve_front = [p(8 - r + r * math.sin(math.radians(t)), 8, 10 - r + r * math.cos(math.radians(t))) for t in range(0, 91, 15)]
    curve_back = [p(8 - r + r * math.sin(math.radians(t)), -8, 10 - r + r * math.cos(math.radians(t))) for t in range(0, 91, 15)]
    left = [p(-8, 8, 0), p(8, 8, 0), p(8, 8, 10 - r)] + curve_front[::-1] + [p(-8, 8, 10)]
    right = [p(8, -8, 0), p(8, 8, 0), p(8, 8, 10 - r), p(8, -8, 10 - r)]
    roundf = curve_front + curve_back[::-1]
    top = [p(-8, -8, 10), p(8 - r, -8, 10), p(8 - r, 8, 10), p(-8, 8, 10)]
    return (poly(left, "url(#gL)") + poly(right, "url(#gR)") + poly(roundf, "url(#gC)")
            + poly(top, "url(#gT)") + line(curve_front, RED, 1.6, False))


@icon("chamfer")
def _():
    p = lambda a, b, c: P(a, b, c, 16, 15)
    c = 4
    left = [p(-8, 8, 0), p(8, 8, 0), p(8, 8, 10 - c), p(8 - c, 8, 10), p(-8, 8, 10)]
    right = [p(8, -8, 0), p(8, 8, 0), p(8, 8, 10 - c), p(8, -8, 10 - c)]
    bevel = [p(8, -8, 10 - c), p(8, 8, 10 - c), p(8 - c, 8, 10), p(8 - c, -8, 10)]
    top = [p(-8, -8, 10), p(8 - c, -8, 10), p(8 - c, 8, 10), p(-8, 8, 10)]
    return (poly(left, "url(#gL)") + poly(right, "url(#gR)") + poly(bevel, "#b9cff3")
            + poly(top, "url(#gT)") + line([p(8, 8, 10 - c), p(8 - c, 8, 10)], RED, 1.6, False))


@icon("shell")
def _():
    p = lambda a, b, c: P(a, b, c, 16, 14)
    t = 2.2
    return (box(-8, -8, 0, 16, 16, 10, oy=14)
            + poly([p(-8 + t, -8 + t, 10), p(8 - t, -8 + t, 10), p(8 - t, 8 - t, 10), p(-8 + t, 8 - t, 10)], "#25325a")
            + poly([p(-8 + t, -8 + t, 10), p(8 - t, -8 + t, 10), p(8 - t, -8 + t, 3), p(-8 + t, -8 + t, 3)], "#3a4f8c", EDGE, .5)
            + poly([p(-8 + t, -8 + t, 10), p(-8 + t, 8 - t, 10), p(-8 + t, 8 - t, 3), p(-8 + t, -8 + t, 3)], "#4d66ad", EDGE, .5))


@icon("draft")
def _():
    p = lambda a, b, c: P(a, b, c, 16, 17)
    s = 3
    left = [p(-8, 8, 0), p(8, 8, 0), p(8 - s, 8 - s, 11), p(-8 + s, 8 - s, 11)]
    right = [p(8, -8, 0), p(8, 8, 0), p(8 - s, 8 - s, 11), p(8 - s, -8 + s, 11)]
    top = [p(-8 + s, -8 + s, 11), p(8 - s, -8 + s, 11), p(8 - s, 8 - s, 11), p(-8 + s, 8 - s, 11)]
    return (poly(left, "url(#gL)") + poly(right, "url(#gR)") + poly(top, "url(#gT)")
            + line([p(8, 8, 0), p(8, 8, 11)], WHITE, 1, False, dash="1.5 1.5")
            + line([p(8, 8, 0), p(8 - s, 8 - s, 11)], RED, 1.6, False))


def small_box(ox, oy, k=0.5):
    return box(-6, -6, 0, 12, 12, 9, ox=ox, oy=oy, k=k)


@icon("linear_pattern")
def _():
    return small_box(7, 12) + small_box(16, 17) + small_box(25, 22) + line(
        [(4, 25), (22, 30)], "#4f8fdb", 1.4, True) + arrow_head(24, 30.5, 16, 4, "#4f8fdb")


@icon("polar_pattern")
def _():
    out = '<circle cx="16" cy="17" r="9" fill="none" stroke="#4f8fdb" stroke-width="1.2" stroke-dasharray="2 2"/>'
    for a in (-90, 30, 150):
        x = 16 + 9 * math.cos(math.radians(a))
        y = 17 + 9 * math.sin(math.radians(a)) + 3
        out += small_box(x, y, 0.45)
    return out + dot(16, 17, 1.8)


@icon("mirror")
def _():
    return (small_box(9, 17, 0.6) + small_box(23, 17, 0.6)
            + line([(16, 3), (16, 29)], "#4f8fdb", 1.4, True, dash="3 2"))


@icon("variable_pattern")
def _():
    return (box(-6, -6, 0, 12, 12, 6, ox=6, oy=17, k=0.4)
            + box(-6, -6, 0, 12, 12, 10, ox=14, oy=20, k=0.55)
            + box(-6, -6, 0, 12, 12, 14, ox=24, oy=23, k=0.7))


# -- Accès rapide ------------------------------------------------------------

@icon("new")
def _():
    return page() + text(15, 21, "+", 14, "#4f8fdb")


@icon("open")
def _():
    return (poly([(3, 8), (11, 8), (13, 10), (27, 10), (27, 26), (3, 26)], "#4560b0", "#1f3570", .9)
            + poly([(3, 26), (7, 14), (31, 14), (27, 26)], "url(#gT)", "#1f3570", .9))


@icon("save")
def _():
    return (poly([(5, 4), (24, 4), (28, 8), (28, 28), (5, 28)], "url(#gL)", "#1f3570", .9)
            + poly([(9, 4), (22, 4), (22, 12), (9, 12)], "url(#gM)", "#4b5058", .7)
            + poly([(9, 17), (24, 17), (24, 28), (9, 28)], WHITE, "#4b5058", .7)
            + '<rect x="18" y="5.5" width="2.5" height="5" fill="#4b5058"/>')


def curved(direction):
    """Flèche courbe épaisse ; direction -1 : vers la gauche (annuler)."""
    d = "M25,26 C25,14 18,10 11,13"
    head = arrow_head(4.5, 16, 158, 9, "#4f8fdb")
    body = path(d, "#4f8fdb", 3.4)
    if direction < 0:
        return body + head
    return f'<g transform="translate(32,0) scale(-1,1)">{body + head}</g>'


@icon("undo")
def _():
    return curved(-1)


@icon("redo")
def _():
    return curved(1)


@icon("rebuild")
def _():
    return (arc_arrow(16, 16, 9, 200, 340, "#4f8fdb", 2.4)
            + arc_arrow(16, 16, 9, 20, 160, "#6fbf8f", 2.4))


@icon("settings")
def _():
    teeth = []
    for i in range(16):
        a = math.radians(i * 22.5)
        r = 13 if i % 2 == 0 else 10
        teeth.append((16 + r * math.cos(a), 16 + r * math.sin(a)))
    return (poly(teeth, "url(#gM)", "#4b5058", .9)
            + '<circle cx="16" cy="16" r="4" fill="#2a3040" stroke="#4b5058" stroke-width=".9"/>')


# -- Esquisse ----------------------------------------------------------------

@icon("select")
def _():
    return poly([(9, 4), (9, 25), (14, 20), (18, 28), (21, 26.5), (17, 18.5), (24, 18.5)],
                WHITE, DARK, 1.2)


@icon("rect")
def _():
    pts4 = [(6, 9), (26, 9), (26, 24), (6, 24)]
    return line(pts4 + [pts4[0]]) + "".join(dot(x, y) for x, y in pts4)


@icon("rect_center")
def _():
    pts4 = [(6, 9), (26, 9), (26, 24), (6, 24)]
    return (line(pts4 + [pts4[0]]) + line([(6, 9), (26, 24)], WHITE, 1, False, dash="2 2")
            + dot(16, 16.5, 2.6) + dot(26, 24))


@icon("ellipse")
def _():
    return (path("M4,16 A12,7.5 0 1 0 28,16 A12,7.5 0 1 0 4,16 Z") + dot(16, 16)
            + line([(16, 16), (28, 16)], WHITE, 1, False, dash="2 2"))


@icon("slot")
def _():
    return path("M10,10 L22,10 A6,6 0 0 1 22,22 L10,22 A6,6 0 0 1 10,10 Z") + dot(10, 16) + dot(22, 16)


@icon("polygon")
def _():
    hexa = [(16 + 11 * math.cos(math.radians(a)), 16 + 11 * math.sin(math.radians(a)))
            for a in range(-90, 270, 60)]
    return line(hexa + [hexa[0]]) + "".join(dot(x, y, 2) for x, y in hexa)


@icon("sketch_fillet")
def _():
    return (line([(5, 6), (5, 18)]) + path("M5,18 A8,8 0 0 0 13,26", RED, 2)
            + line([(13, 26), (27, 26)]) + line([(5, 26), (5, 18)], WHITE, 1, False, dash="1.5 1.5")
            + line([(5, 26), (13, 26)], WHITE, 1, False, dash="1.5 1.5") + dot(5, 6) + dot(27, 26))


@icon("trim")
def _():
    return (line([(4, 20), (12, 20)]) + line([(12, 20), (28, 20)], RED, 1.6, True, dash="2.5 2")
            + line([(12, 6), (12, 28)]) + dot(12, 20)
            + text(22, 14, "✂", 11, "#c9cdd3", 400))


@icon("construction")
def _():
    return line([(4, 26), (28, 6)], "#7fc4ff", 1.8, True, dash="3 2.5") + dot(4, 26) + dot(28, 6)


@icon("project")
def _():
    p = lambda a, b, c: P(a, b, c, 16, 18)
    top = [p(-8, -8, 6), p(8, -8, 6), p(8, 8, 6), p(-8, 8, 6)]
    return (box(-8, -8, 0, 16, 16, 6, oy=18)
            + line([(x, y - 8) for x, y in top] + [(top[0][0], top[0][1] - 8)], WHITE, 1.4)
            + line([(16, 20), (16, 10)], "#4f8fdb", 1.3, False) + arrow_head(16, 9, -90, 4, "#4f8fdb"))


@icon("dimension")
def _():
    return (line([(5, 24), (27, 24)]) + dot(5, 24, 2) + dot(27, 24, 2)
            + line([(5, 14), (27, 14)], "#7fc4ff", 1.1, False)
            + line([(5, 11), (5, 20)], "#7fc4ff", 1, False) + line([(27, 11), (27, 20)], "#7fc4ff", 1, False)
            + arrow_head(6, 14, 180, 4, "#7fc4ff") + arrow_head(26, 14, 0, 4, "#7fc4ff")
            + text(16, 11, "10", 8, "#7fc4ff"))


@icon("sketch_mirror")
def _():
    return (line([(13, 8), (4, 24), (13, 24), (13, 8)]) + line([(19, 8), (28, 24), (19, 24), (19, 8)])
            + line([(16, 3), (16, 29)], "#4f8fdb", 1.2, False, dash="3 2"))


@icon("sketch_array")
def _():
    out = ""
    for x in (5, 18):
        for y in (5, 18):
            out += line([(x, y), (x + 9, y), (x + 9, y + 9), (x, y + 9), (x, y)], WHITE, 1.4)
    return out + dot(5, 5, 1.8)


@icon("offset")
def _():
    return (path("M5,24 C9,8 23,8 27,24") + path("M10,25 C13,14 19,14 22,25", "#7fc4ff", 1.4, True, dash="2 2")
            + line([(16, 12), (16, 17.5)], RED, 1.2, False))


@icon("sketch_image")
def _():
    return (poly([(3, 6), (29, 6), (29, 26), (3, 26)], "#2a3346", "url(#gM)", 1.6)
            + poly([(5, 24), (13, 13), (19, 20), (22, 16), (27, 24)], "url(#gL)", "#1f3570", .7)
            + '<circle cx="22" cy="11" r="2.4" fill="#f2c94c"/>')


@icon("sketch_ok")
def _():
    return poly([(5, 16), (9, 12), (14, 17), (25, 6), (29, 10), (14, 25)], "url(#gG)", "#1d6b3c", .9)


@icon("sketch_cancel")
def _():
    return (line([(8, 8), (24, 24)], "#ff6b5e", 4.2, True) + line([(24, 8), (8, 24)], "#ff6b5e", 4.2, True))


# -- Relations d'esquisse ------------------------------------------------------

def rel_badge(symbol, size=10):
    return ('<rect x="17" y="17" width="13" height="13" rx="3" fill="#4f8fdb" stroke="#1f3570" stroke-width=".8"/>'
            + text(23.5, 27, symbol, size, WHITE))


@icon("rel_horizontal")
def _():
    return line([(3, 12), (25, 12)]) + dot(3, 12, 2) + dot(25, 12, 2) + rel_badge("H", 9)


@icon("rel_vertical")
def _():
    return line([(10, 3), (10, 27)]) + dot(10, 3, 2) + dot(10, 27, 2) + rel_badge("V", 9)


@icon("rel_coincident")
def _():
    return line([(3, 22), (14, 12)]) + line([(14, 12), (27, 6)]) + dot(14, 12, 3.2)


@icon("rel_parallel")
def _():
    return line([(4, 18), (16, 4)]) + line([(10, 26), (24, 10)]) + rel_badge("//", 8)


@icon("rel_perpendicular")
def _():
    return (line([(6, 4), (6, 26), (28, 26)])
            + line([(6, 20), (12, 20), (12, 26)], "#7fc4ff", 1.2, False))


@icon("rel_tangent")
def _():
    return ('<circle cx="14" cy="18" r="8" fill="none" stroke="#1b2230" stroke-width="3.2" stroke-opacity=".75"/>'
            '<circle cx="14" cy="18" r="8" fill="none" stroke="#f4f7fb" stroke-width="1.6"/>'
            + line([(3, 10), (28, 10)], "#7fc4ff") + dot(14, 10, 2.2))


@icon("rel_equal")
def _():
    return line([(3, 8), (17, 4)]) + line([(3, 16), (17, 12)]) + rel_badge("=", 11)


@icon("rel_concentric")
def _():
    return ('<circle cx="16" cy="16" r="11" fill="none" stroke="#1b2230" stroke-width="3.2" stroke-opacity=".75"/>'
            '<circle cx="16" cy="16" r="11" fill="none" stroke="#f4f7fb" stroke-width="1.6"/>'
            '<circle cx="16" cy="16" r="6" fill="none" stroke="#1b2230" stroke-width="3.2" stroke-opacity=".75"/>'
            '<circle cx="16" cy="16" r="6" fill="none" stroke="#f4f7fb" stroke-width="1.6"/>' + dot(16, 16, 2.2))


@icon("rel_collinear")
def _():
    return (line([(2, 26), (30, 6)], "#7fc4ff", 1, False, dash="2 2") + line([(4, 24.5), (12, 19)])
            + line([(19, 14), (28, 7.5)]) + dot(4, 24.5, 1.8) + dot(12, 19, 1.8) + dot(19, 14, 1.8) + dot(28, 7.5, 1.8))


@icon("rel_midpoint")
def _():
    return line([(3, 24), (29, 8)]) + dot(3, 24, 1.8) + dot(29, 8, 1.8) + dot(16, 16, 3.2)


@icon("rel_symmetric")
def _():
    return (line([(16, 3), (16, 29)], "#7fc4ff", 1.2, False, dash="3 2")
            + line([(7, 16), (25, 16)], WHITE, 1, False, dash="1.5 1.5") + dot(7, 16, 2.8) + dot(25, 16, 2.8))


@icon("rel_fixed")
def _():
    return (path("M10,15 L10,10 A6,6 0 0 1 22,10 L22,15", "#c9cdd3", 2.6)
            + poly([(7, 15), (25, 15), (25, 28), (7, 28)], "url(#gM)", "#4b5058", .9)
            + '<circle cx="16" cy="21" r="2" fill="#4b5058"/>')


@icon("relations")
def _():
    out = ""
    for i, y in enumerate((7, 16, 25)):
        out += ('<rect x="3" y="%s" width="7" height="7" rx="1.5" fill="#4f8fdb" stroke="#1f3570" stroke-width=".7"/>' % (y - 3.5))
        out += line([(13, y), (28, y)], WHITE, 1.6)
    return out


# -- Arbre -------------------------------------------------------------------

@icon("origin_plane")
def _():
    return plane([(3, 18), (14, 9), (29, 14), (18, 23)])


@icon("origin")
def _():
    o = (13, 19)
    return (line([o, (28, 25)], "#e06666", 2) + line([o, (5, 25)], "#6aa84f", 2)
            + line([o, (13, 4)], "#4b9bd5", 2) + dot(*o, 2.4))


@icon("equations")
def _():
    return page(5, 3, 20, 26) + text(15, 21, "f(x)", 8, "#3e58a8") if False else (
        page(5, 3, 20, 26) + '<text x="15" y="20" font-family="Segoe UI, Arial, sans-serif" '
        'font-size="9" font-style="italic" font-weight="700" fill="#3e58a8" text-anchor="middle">f(x)</text>')


@icon("surface_body")
def _():
    return path("M3,22 C9,12 15,26 21,14 L29,10 C23,22 17,8 11,20 Z", "#1f3570", .9, False,
                fill="url(#gP)")


# -- Surfaces ------------------------------------------------------------------

@icon("surface_extrude")
def _():
    return (path("M4,26 C9,20 13,30 18,24 L18,10 C13,16 9,6 4,12 Z", "#3d5fb8", .9, False, fill="url(#gP)")
            + path("M4,26 C9,20 13,30 18,24") + line([(20, 22), (26, 10)], "#4f8fdb", 1.3, False)
            + arrow_head(26.5, 9, -64, 4, "#4f8fdb"))


@icon("surface_revolve")
def _():
    return ('<path d="M7,8 A9,3 0 0 0 25,8 L22,25 A6,2.2 0 0 1 10,25 Z" fill="url(#gP)" stroke="#3d5fb8" stroke-width=".9"/>'
            '<ellipse cx="16" cy="8" rx="9" ry="3" fill="none" stroke="#3d5fb8" stroke-width=".9"/>'
            + line([(16, 3), (16, 30)], "#7fc4ff", 1, False, dash="2 2"))


@icon("surface_loft")
def _():
    return (path("M4,24 C10,18 16,28 22,22 L28,10 C22,16 16,6 10,12 Z", "#3d5fb8", .9, False, fill="url(#gP)")
            + path("M4,24 C10,18 16,28 22,22") + path("M10,12 C16,6 22,16 28,10"))


@icon("sew")
def _():
    return (poly([(3, 8), (15, 6), (15, 26), (3, 24)], "url(#gP)", "#3d5fb8", .9)
            + poly([(17, 6), (29, 8), (29, 24), (17, 26)], "url(#gP)", "#3d5fb8", .9)
            + "".join(line([(13, y), (19, y + 2)], RED, 1.4, False) for y in (8, 13, 18, 23)))


@icon("thicken")
def _():
    return (path("M3,20 C9,14 15,24 22,16 L29,13 L29,17 C22,20 15,28 9,18 L3,24 Z", "#1f3570", .9, False, fill="url(#gR)")
            + path("M3,20 C9,14 15,24 22,16 L29,13", "#1f3570", .9, False)
            + path("M3,20 C9,14 15,24 22,16 L29,13 L29,13", WHITE, 1.2, False))


# -- Évaluer -------------------------------------------------------------------

@icon("measure")
def _():
    out = poly([(3, 20), (22, 4), (29, 12), (10, 28)], "url(#gM)", "#4b5058", .9)
    for i in range(1, 8):
        x0, y0 = 3 + i * 2.4, 20 - i * 2.0
        L = 3.5 if i % 2 == 0 else 2.2
        out += line([(x0, y0), (x0 + L * 0.75, y0 + L * 0.9)], "#4b5058", .9, False)
    return out


@icon("mass")
def _():
    return (poly([(10, 10), (22, 10), (27, 28), (5, 28)], "url(#gM)", "#4b5058", .9)
            + '<circle cx="16" cy="8" r="3.5" fill="none" stroke="#8d939b" stroke-width="2"/>'
            + text(16, 24, "kg", 8, "#2a3040"))


@icon("drawing")
def _():
    return (page(4, 3, 24, 26, 6) + line([(8, 9), (14, 9), (14, 15), (8, 15), (8, 9)], "#3e58a8", 1, False)
            + line([(17, 9), (23, 9), (23, 15), (17, 15), (17, 9)], "#3e58a8", 1, False)
            + line([(8, 19), (14, 19), (14, 25), (8, 25), (8, 19)], "#3e58a8", 1, False)
            + line([(17, 22), (20, 19), (23, 22), (20, 25), (17, 22)], "#3e58a8", 1, False))


@icon("interference")
def _():
    return (box(-6, -6, 0, 12, 12, 10, ox=11, oy=16, k=0.9)
            + box(-6, -6, 0, 12, 12, 10, ox=20, oy=19, k=0.9, top="#f3a9a3", left="#e26a60", right="#b5372e"))


# -- Assemblage ------------------------------------------------------------------

@icon("assembly")
def _():
    return (box(-8, -8, 0, 16, 16, 6, oy=22)
            + box(-4, -4, 0, 8, 8, 8, oy=13, top="#e4e7ec", left="#b5bcc6", right="#7c8592"))


@icon("solve")
def _():
    return (box(-5, -5, 0, 10, 10, 8, oy=17, k=0.9)
            + arc_arrow(16, 16, 12, 200, 330, "#6fbf8f", 2) + arc_arrow(16, 16, 12, 20, 150, "#6fbf8f", 2))


@icon("insert")
def _():
    return box(-6, -6, 0, 12, 12, 9, ox=13, oy=19) + text(25, 12, "+", 14, "#6fbf8f")


@icon("component_array")
def _():
    return (small_box(7, 14) + small_box(16, 19) + small_box(25, 24)
            + path("M5,5 L11,5", "#7fc4ff", 1.2) + path("M14,5 L20,5", "#7fc4ff", 1.2))


@icon("explode")
def _():
    return (box(-5, -5, 0, 10, 10, 5, oy=25, k=0.9) + box(-5, -5, 0, 10, 10, 5, oy=11, k=0.9)
            + line([(16, 18), (16, 14)], "#4f8fdb", 1.4, False) + arrow_head(16, 12, -90, 4, "#4f8fdb")
            + line([(27, 18), (27, 24)], "#4f8fdb", 1.4, False) + arrow_head(27, 26, 90, 4, "#4f8fdb"))


@icon("mate")
def _():
    return (box(-6, -6, 0, 12, 12, 6, ox=11, oy=26, k=0.85)
            + box(-6, -6, 0, 12, 12, 6, ox=21, oy=10, k=0.85, top="#e4e7ec", left="#b5bcc6", right="#7c8592")
            + line([(13, 18), (19, 14)], RED, 1.4, False, dash="2 1.5") + dot(13, 18, 1.8) + dot(19, 14, 1.8))


@icon("graph_feature")
def _():
    return ('<rect x="2" y="5" width="10" height="8" rx="2" fill="url(#gL)" stroke="#1f3570" stroke-width=".8"/>'
            '<rect x="2" y="19" width="10" height="8" rx="2" fill="url(#gL)" stroke="#1f3570" stroke-width=".8"/>'
            '<rect x="20" y="12" width="10" height="8" rx="2" fill="url(#gT)" stroke="#1f3570" stroke-width=".8"/>'
            + path("M12,9 C16,9 16,16 20,16", WHITE, 1.3) + path("M12,23 C16,23 16,16 20,16", WHITE, 1.3)
            + dot(12, 9, 1.6) + dot(12, 23, 1.6) + dot(20, 16, 1.6))



# -- Menu contextuel -----------------------------------------------------------

@icon("normal_to")
def _():
    return (poly([(6, 6), (26, 6), (26, 26), (6, 26)], "url(#gP)", "#3d5fb8", 1.2)
            + '<circle cx="16" cy="16" r="5" fill="none" stroke="#f4f7fb" stroke-width="1.6"/>'
            + dot(16, 16, 2.2))


@icon("edit")
def _():
    return (box(-7, -7, 0, 14, 14, 8, ox=13, oy=19, k=0.9)
            + poly([(22, 3), (28, 9), (17, 20), (13, 21), (14, 17)], "url(#gM)", "#4b5058", .8)
            + poly([(13, 21), (14, 17), (17, 20)], "#e9c46a", "#4b5058", .6))


@icon("zoom_fit")
def _():
    corners = ""
    for x, y, dx, dy in ((4, 4, 1, 1), (28, 4, -1, 1), (4, 28, 1, -1), (28, 28, -1, -1)):
        corners += line([(x, y + 6 * dy), (x, y), (x + 6 * dx, y)], WHITE, 1.8)
    return corners + box(-5, -5, 0, 10, 10, 7, oy=18, k=0.9)


@icon("orient")
def _():
    return (box(-7, -7, 0, 14, 14, 14, oy=17, k=0.9)
            + text(12, 23, "F", 7, "#1f3570", 700) + text(21, 23, "D", 7, "#1f3570", 700))


@icon("rollback")
def _():
    out = ""
    for y in (6, 12, 18):
        out += ('<rect x="5" y="%s" width="5" height="4" rx="1" fill="url(#gL)" stroke="#1f3570" stroke-width=".6"/>' % (y - 2))
        out += line([(13, y), (27, y)], WHITE, 1.4, False)
    out += line([(4, 23), (28, 23)], "#4f8fdb", 2.4)
    out += arrow_head(16, 19, -90, 5, "#4f8fdb")
    return out + line([(16, 26), (16, 20)], "#4f8fdb", 1.6, False)


@icon("delete")
def _():
    return (poly([(9, 10), (23, 10), (21, 28), (11, 28)], "url(#gM)", "#4b5058", .9)
            + poly([(7, 7), (25, 7), (25, 10), (7, 10)], "#c9cdd3", "#4b5058", .8)
            + '<rect x="13" y="4" width="6" height="3" fill="#c9cdd3" stroke="#4b5058" stroke-width=".7"/>'
            + line([(13, 13), (13.5, 25)], "#4b5058", 1, False) + line([(16, 13), (16, 25)], "#4b5058", 1, False)
            + line([(19, 13), (18.5, 25)], "#4b5058", 1, False))

os.makedirs(OUT, exist_ok=True)
for name, fn in ICONS.items():
    with open(os.path.join(OUT, f"fs_{name}.svg"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(svg(fn()))
print(len(ICONS))

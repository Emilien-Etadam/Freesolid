"""SolidWorks <-> FreeCAD vocabulary.

Single source of truth for the terminology mapping. Consumed by the
headless engine to label rows in the feature tree.

Pure Python on purpose: no FreeCAD import, so it is unit-testable in CI.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Term:
    """One entry of the mapping.

    Attributes:
        command: the FreeCAD command name, as passed to ``Gui.runCommand``.
        obj_type: the document object type the command produces, used to
            label existing features in the tree. ``""`` when the command
            creates nothing (view commands, for instance).
        fr: the French term a SolidWorks user expects.
        en: the English term a SolidWorks user expects.
        note: a short hint shown as a tooltip, used to flag the places where
            FreeCAD genuinely diverges rather than merely renaming things.
    """

    command: str
    obj_type: str
    fr: str
    en: str
    note: str = ""


#: Ordered so a ribbon/toolbar built from this table reads like a
#: CommandManager "Features" tab rather than an alphabetical dump.
#: Audited against the SolidWorks 2025 French help (Fonctions tab) on
#: 2026-08-03 — labels match the shipping product's terminology.
TERMS: tuple[Term, ...] = (
    Term("PartDesign_Pad", "PartDesign::Pad",
         "Bossage/Base extrudé", "Extruded Boss/Base"),
    Term("PartDesign_Pocket", "PartDesign::Pocket",
         "Enlèvement de matière extrudé", "Extruded Cut"),
    Term("PartDesign_Revolution", "PartDesign::Revolution",
         "Bossage/Base avec révolution", "Revolved Boss/Base"),
    Term("PartDesign_Groove", "PartDesign::Groove",
         "Enlèvement de matière avec révolution", "Revolved Cut"),
    Term("PartDesign_AdditivePipe", "PartDesign::AdditivePipe",
         "Bossage/Base balayé", "Swept Boss/Base"),
    Term("PartDesign_SubtractivePipe", "PartDesign::SubtractivePipe",
         "Enlèvement de matière balayé", "Swept Cut"),
    Term("PartDesign_AdditiveLoft", "PartDesign::AdditiveLoft",
         "Bossage/Base lissé", "Lofted Boss/Base"),
    Term("PartDesign_SubtractiveLoft", "PartDesign::SubtractiveLoft",
         "Enlèvement de matière lissé", "Lofted Cut"),
    Term("PartDesign_Hole", "PartDesign::Hole",
         "Assistant de perçage", "Hole Wizard",
         "Filetages normalisés ISO/ANSI intégrés, comme l'assistant SW."),
    Term("PartDesign_Fillet", "PartDesign::Fillet",
         "Congé", "Fillet"),
    Term("PartDesign_Chamfer", "PartDesign::Chamfer",
         "Chanfrein", "Chamfer"),
    Term("PartDesign_Draft", "PartDesign::Draft",
         "Dépouille", "Draft"),
    Term("PartDesign_Thickness", "PartDesign::Thickness",
         "Coque", "Shell"),
    Term("PartDesign_LinearPattern", "PartDesign::LinearPattern",
         "Répétition linéaire", "Linear Pattern"),
    Term("PartDesign_PolarPattern", "PartDesign::PolarPattern",
         "Répétition circulaire", "Circular Pattern"),
    Term("PartDesign_Mirrored", "PartDesign::Mirrored",
         "Symétrie", "Mirror"),
    Term("PartDesign_NewSketch", "Sketcher::SketchObject",
         "Esquisse", "Sketch"),
    Term("PartDesign_Body", "PartDesign::Body",
         "Pièce", "Part",
         "Un Body = un fichier .sldprt. Un document FreeCAD peut en "
         "contenir plusieurs."),
)

#: FreeCAD Origin plane internal names -> the SolidWorks reference planes.
#: FreeCAD is Z-up, SolidWorks is Y-up, hence XY->Dessus and XZ->Face.
ORIGIN_PLANES: dict[str, tuple[str, str]] = {
    "XY_Plane": ("Plan de dessus", "Top Plane"),
    "XZ_Plane": ("Plan de face", "Front Plane"),
    "YZ_Plane": ("Plan de droite", "Right Plane"),
}

ORIGIN_AXES: dict[str, tuple[str, str]] = {
    "X_Axis": ("Axe X", "X Axis"),
    "Y_Axis": ("Axe Y", "Y Axis"),
    "Z_Axis": ("Axe Z", "Z Axis"),
}


def _by(attr: str) -> dict[str, Term]:
    return {getattr(t, attr): t for t in TERMS if getattr(t, attr)}


BY_COMMAND: dict[str, Term] = _by("command")
BY_TYPE: dict[str, Term] = _by("obj_type")


def label_for_type(obj_type: str, lang: str = "fr") -> str:
    """Return the designer-facing name for a document object type.

    Falls back to the raw FreeCAD type stripped of its namespace, so an
    unmapped feature still shows something readable instead of nothing.
    """
    term = BY_TYPE.get(obj_type)
    if term is not None:
        return term.fr if lang == "fr" else term.en
    return obj_type.split("::")[-1]


#: Catalogue de la fonction graphe (N006) — taxonomie reprise de
#: ``j8sr0230/Nodes`` (LGPL-2.1). Source unique : type, libellé, catégorie,
#: icône, ports, et l'état implémenté / pas encore. ``graph_vocabulary``
#: le sert tel quel ; un type sans entrée ici casse la CI exprès.
#:
#: Écartés, et pourquoi : ``scene`` (objets du document FreeCAD), ``viz``
#: (visionneuses Qt), ``group`` (bus send/receive de l'éditeur Qt),
#: ``alpha`` (nœud de test). ``script`` n'est plus écarté : c'est un nœud
#: du graphe, exécuté par le kernel après consentement explicite, jamais
#: par l'évaluateur pur (N008).

_REASON_PART = "appelle l'API Part — pas encore dans l'évaluateur pur"
_REASON_MESH = "maillage — pas encore dans l'évaluateur pur"
_REASON_SLIDER = "curseur d'interface Qt — saisissez un Nombre"
_REASON_STATE = "l'évaluateur est pur, sans état ni horloge de scène"
_REASON_VERTEX = "attend un sommet géométrique — pas encore"
_REASON_TEXT = "affichage — hors de l'évaluateur de forme"


@dataclass(frozen=True)
class GraphPort:
    """Port d'entrée d'un nœud de fonction graphe."""

    key: str
    kind: str = "number"  # number | point | list | shape | any
    optional: bool = False


@dataclass(frozen=True)
class GraphField:
    """Champ propre au nœud, pas un port (valeur, nom, opération)."""

    key: str
    kind: str  # number | text | op | list_op


@dataclass(frozen=True)
class GraphNode:
    """Une entrée du catalogue — déclarée même si pas encore évaluable."""

    type: str
    fr: str
    en: str
    category: str
    icon: str
    inputs: tuple[GraphPort, ...] = ()
    fields: tuple[GraphField, ...] = ()
    implemented: bool = False
    reason: str = ""
    shape: bool = False


def _num(*keys: str) -> tuple[GraphPort, ...]:
    return tuple(GraphPort(key) for key in keys)


def _pts(*keys: str) -> tuple[GraphPort, ...]:
    return tuple(GraphPort(key, "point") for key in keys)


def _gn(kind: str, fr: str, en: str, category: str, icon: str, *,
        inputs: tuple[GraphPort, ...] = (),
        fields: tuple[GraphField, ...] = (),
        implemented: bool = False, reason: str = "",
        shape: bool = False) -> GraphNode:
    return GraphNode(
        type=kind, fr=fr, en=en, category=category, icon=icon,
        inputs=inputs, fields=fields, implemented=implemented,
        reason=reason, shape=shape,
    )


GRAPH_CATEGORY_LABELS: dict[str, tuple[str, str]] = {
    "number": ("Nombre", "Number"),
    "vector": ("Vecteur", "Vector"),
    "list": ("Liste", "List"),
    "generators": ("Générateurs", "Generators"),
    "curves": ("Courbes", "Curves"),
    "surfaces": ("Surfaces", "Surfaces"),
    "modifiers": ("Modificateurs", "Modifiers"),
    "spatial": ("Spatial", "Spatial"),
    "analyzers": ("Analyseurs", "Analyzers"),
    "transforms": ("Transformations", "Transforms"),
    "text": ("Texte", "Text"),
    "script": ("Python", "Python"),
    "repeat": ("Répétition", "Repeat"),
}

_F_VALUE = (GraphField("value", "number"),)
_F_NAME = (GraphField("name", "text"),)
_F_LIST_OP = (GraphField("op", "list_op"),)

GRAPH_NODES: tuple[GraphNode, ...] = (
    # --- Nombre : constantes et opérations, évaluateur pur. ---
    _gn("nombre", "Nombre", "Number", "number", "nodes_number.svg",
        fields=_F_VALUE, implemented=True),
    _gn("variable", "Variable", "Variable", "number", "VarSet.svg",
        fields=_F_NAME, implemented=True),
    _gn("addition", "Addition", "Add", "number", "nodes_add.svg",
        inputs=_num("a", "b"), implemented=True),
    _gn("soustraction", "Soustraction", "Sub", "number", "nodes_sub.svg",
        inputs=_num("a", "b"), implemented=True),
    _gn("multiplication", "Multiplication", "Mult", "number",
        "nodes_multiply.svg", inputs=_num("a", "b"), implemented=True),
    _gn("division", "Division", "Div", "number", "nodes_divide.svg",
        inputs=_num("a", "b"), implemented=True),
    _gn("puissance", "Puissance", "Pow", "number", "nodes_pow.svg",
        inputs=_num("a", "b"), implemented=True),
    _gn("sinus", "Sinus", "Sin", "number", "nodes_math.svg",
        inputs=_num("a"), implemented=True),
    _gn("cosinus", "Cosinus", "Cos", "number", "nodes_math.svg",
        inputs=_num("a"), implemented=True),
    _gn("tangente", "Tangente", "Tan", "number", "nodes_math.svg",
        inputs=_num("a"), implemented=True),
    _gn("plage", "Plage", "Number Range", "number", "nodes_number_range.svg",
        inputs=_num("depart", "fin", "pas"), implemented=True),
    _gn("curseur", "Curseur", "Number Slider", "number",
        "nodes_number_slider.svg", reason=_REASON_SLIDER),
    # --- Vecteur : composition, décomposition, algèbre. ---
    _gn("vecteur", "Vecteur", "Vector", "vector", "nodes_vect.svg",
        inputs=_num("x", "y", "z"), implemented=True),
    _gn("addition_vecteur", "Addition (vecteur)", "Add (Vec)", "vector",
        "nodes_vect_add.svg", inputs=_pts("a", "b"), implemented=True),
    _gn("soustraction_vecteur", "Soustraction (vecteur)", "Sub (Vec)",
        "vector", "nodes_vect_sub.svg", inputs=_pts("a", "b"),
        implemented=True),
    _gn("echelle_vecteur", "Échelle (vecteur)", "Scale (Vec)", "vector",
        "nodes_vect_scale.svg",
        inputs=(GraphPort("vecteur", "point"), GraphPort("facteur")),
        implemented=True),
    _gn("longueur_vecteur", "Longueur (vecteur)", "Length", "vector",
        "nodes_vect_length.svg", inputs=_pts("vecteur"), implemented=True),
    _gn("produit_vectoriel", "Produit vectoriel", "Cross", "vector",
        "nodes_wb_icon.svg", inputs=_pts("a", "b"), implemented=True),
    _gn("vecteur_x", "Vecteur X", "X Vector", "vector", "nodes_vect_x.svg",
        implemented=True),
    _gn("vecteur_y", "Vecteur Y", "Y Vector", "vector", "nodes_vect_y.svg",
        implemented=True),
    _gn("vecteur_z", "Vecteur Z", "Z Vector", "vector", "nodes_vect_z.svg",
        implemented=True),
    _gn("depuis_sommet", "Depuis un sommet", "From Vertex", "vector",
        "nodes_vect_edges.svg", inputs=(GraphPort("sommet", "point"),),
        reason=_REASON_VERTEX),
    # --- Liste : génération, longueur, aplatissement, décalage. ---
    _gn("serie", "Série", "Series", "list", "nodes_number_range.svg",
        inputs=_num("depart", "pas", "nombre"), implemented=True),
    _gn("longueur_liste", "Longueur (liste)", "List Length", "list",
        "nodes_wb_icon.svg", inputs=(GraphPort("liste", "list"),),
        implemented=True),
    _gn("decalage", "Décalage", "Shift", "list", "nodes_wb_icon.svg",
        inputs=(GraphPort("liste", "list"), GraphPort("decalage")),
        implemented=True),
    _gn("option_liste", "Option de liste", "Socket Option", "list",
        "nodes_wb_icon.svg", inputs=(GraphPort("liste", "list"),),
        fields=_F_LIST_OP, implemented=True),
    _gn("suivant", "Suivant", "Next", "list", "nodes_wb_icon.svg",
        inputs=(GraphPort("liste", "list"), GraphPort("tick")),
        reason=_REASON_STATE),
    # --- Générateurs : boîte et cylindre déjà là ; le reste appelle Part. ---
    _gn("boite", "Boîte", "Box", "generators", "nodes_box.svg",
        inputs=_num("longueur", "largeur", "hauteur") + _pts("ancrage"),
        implemented=True, shape=True),
    _gn("cylindre", "Cylindre", "Cylinder", "generators",
        "nodes_cylinder.svg",
        inputs=_num("rayon", "hauteur") + _pts("ancrage"),
        implemented=True, shape=True),
    _gn("cone", "Cône", "Cone", "generators", "nodes_cone.svg",
        inputs=_num("rayon1", "rayon2", "hauteur") + _pts("point", "direction")
        + _num("angle"), reason=_REASON_PART, shape=True),
    _gn("sphere", "Sphère", "Sphere", "generators", "nodes_sphere.svg",
        inputs=_num("rayon") + _pts("point"), reason=_REASON_PART, shape=True),
    _gn("tore", "Tore", "Torus", "generators", "nodes_torus.svg",
        inputs=_num("rayon1", "rayon2") + _pts("point", "direction")
        + _num("angle_v1", "angle_v2", "angle_u"),
        reason=_REASON_PART, shape=True),
    _gn("point", "Point", "Point", "generators", "nodes_point.svg",
        inputs=_pts("point"), reason=_REASON_PART, shape=True),
    _gn("boite_maillage", "Boîte maillée", "MBox", "generators",
        "nodes_mesh_cube.svg",
        inputs=_num("largeur", "longueur", "hauteur") + _pts("point"),
        reason=_REASON_MESH, shape=True),
    # --- Courbes / surfaces / modificateurs / spatial / analyseurs /
    #     transformations : déclarés, pas évalués (API Part). ---
    _gn("arc_3pts", "Arc (3 points)", "Arc (3 Pts)", "curves",
        "nodes_arc_3_pt.svg", inputs=_pts("point1", "point2", "point3"),
        reason=_REASON_PART, shape=True),
    _gn("arc", "Arc", "Arc (Deg)", "curves", "nodes_arc.svg",
        inputs=_num("rayon") + _pts("point", "direction")
        + _num("angle1", "angle2"), reason=_REASON_PART, shape=True),
    _gn("bspline", "B-spline", "BSpline Crv", "curves", "nodes_bspline.svg",
        inputs=(GraphPort("centres", "list"), GraphPort("ferme")),
        reason=_REASON_PART, shape=True),
    _gn("cercle", "Cercle", "Circle", "curves", "nodes_circle.svg",
        inputs=_num("rayon") + _pts("point", "direction"),
        reason=_REASON_PART, shape=True),
    _gn("discretiser", "Discrétiser", "Discretize", "curves",
        "nodes_wb_icon.svg",
        inputs=(GraphPort("courbe", "shape"), GraphPort("distance")),
        reason=_REASON_PART),
    _gn("evaluer_courbe", "Évaluer une courbe", "Evaluate Crv", "curves",
        "nodes_wb_icon.svg",
        inputs=(GraphPort("parametre"), GraphPort("courbe", "shape")),
        reason=_REASON_PART),
    _gn("helice", "Hélice", "Helix", "curves", "nodes_helix.svg",
        inputs=_num("pas_helice", "hauteur", "rayon", "angle", "gauche"),
        reason=_REASON_PART, shape=True),
    _gn("ligne", "Ligne", "Line (2 Pts)", "curves", "nodes_line.svg",
        inputs=_pts("point1", "point2"), reason=_REASON_PART, shape=True),
    _gn("polyligne", "Polyligne", "Polyline", "curves", "nodes_polyline.svg",
        inputs=(GraphPort("point", "point"), GraphPort("ferme")),
        reason=_REASON_PART, shape=True),
    _gn("bspline_surface", "Surface B-spline", "BSpline Srf", "surfaces",
        "nodes_bspline_surface.svg",
        inputs=(GraphPort("centres", "list"),),
        reason=_REASON_PART, shape=True),
    _gn("courbe_vers_surface", "Courbe vers surface", "Crv to Srf",
        "surfaces", "nodes_crv_srf.svg",
        inputs=(GraphPort("courbe", "shape"),),
        reason=_REASON_PART, shape=True),
    _gn("evaluer_surface", "Évaluer une surface", "Evaluate Srf",
        "surfaces", "nodes_wb_icon.svg",
        inputs=(GraphPort("u"), GraphPort("v"),
                GraphPort("surface", "shape")),
        reason=_REASON_PART),
    _gn("surface_remplie", "Surface remplie", "Filled Srf", "surfaces",
        "nodes_wb_icon.svg",
        inputs=(GraphPort("contour", "shape"), GraphPort("support", "shape")),
        reason=_REASON_PART, shape=True),
    _gn("plan", "Plan", "Plane", "surfaces", "nodes_wb_icon.svg",
        inputs=_num("longueur", "largeur") + _pts("point", "direction"),
        reason=_REASON_PART, shape=True),
    _gn("uv_sur_surface", "UV sur surface", "UV on Srf", "surfaces",
        "nodes_wb_icon.svg",
        inputs=(GraphPort("surface", "shape"), GraphPort("point", "point")),
        reason=_REASON_PART),
    _gn("extrusion", "Extrusion", "Extrude", "modifiers", "nodes_extrude.svg",
        inputs=(GraphPort("forme", "shape"), GraphPort("direction", "point")),
        reason=_REASON_PART, shape=True),
    _gn("lisse", "Lissé", "Loft", "modifiers", "nodes_wb_icon.svg",
        inputs=(GraphPort("forme", "shape"), GraphPort("solide"),
                GraphPort("raye")),
        reason=_REASON_PART, shape=True),
    _gn("definir_forme", "Définir la forme", "Set Shape", "modifiers",
        "nodes_wb_icon.svg",
        inputs=(GraphPort("objet", "any"), GraphPort("forme", "shape")),
        reason=_REASON_PART),
    _gn("trianguler", "Trianguler", "Triangulate", "modifiers",
        "nodes_triangulate.svg",
        inputs=(GraphPort("forme", "shape"), GraphPort("qualite")),
        reason=_REASON_MESH),
    _gn("maillage_dual", "Maillage dual", "Dual Mesh", "spatial",
        "nodes_wb_icon.svg",
        inputs=(GraphPort("maillage", "any"), GraphPort("echelle")),
        reason=_REASON_MESH),
    _gn("peupler_face", "Peupler une face", "Populate Face", "spatial",
        "nodes_populate_2d.svg",
        inputs=(GraphPort("forme", "shape"), GraphPort("compte"),
                GraphPort("distance"), GraphPort("graine")),
        reason=_REASON_PART),
    _gn("peupler_solide", "Peupler un solide", "Populate Solid", "spatial",
        "nodes_wb_icon.svg",
        inputs=(GraphPort("forme", "shape"), GraphPort("compte"),
                GraphPort("distance"), GraphPort("graine")),
        reason=_REASON_PART),
    _gn("voronoi_solide", "Voronoï sur solide", "Voronoi on Sld", "spatial",
        "nodes_voronoi_on_sld.svg",
        inputs=(GraphPort("forme", "shape"), GraphPort("point", "point"),
                GraphPort("mode"), GraphPort("echelle")),
        reason=_REASON_PART, shape=True),
    _gn("voronoi_surface", "Voronoï sur surface", "Voronoi on Srf",
        "spatial", "nodes_voronoi_on_srf.svg",
        inputs=(GraphPort("face", "shape"), GraphPort("point", "point")),
        reason=_REASON_PART),
    _gn("centre", "Centre", "Center", "analyzers", "nodes_center.svg",
        inputs=(GraphPort("forme", "shape"),), reason=_REASON_PART),
    _gn("contenu_forme", "Contenu de la forme", "Shape Content",
        "analyzers", "nodes_shape_content.svg",
        inputs=(GraphPort("forme", "shape"),), reason=_REASON_PART),
    _gn("placement_forme", "Placement de la forme", "Shape Placement",
        "analyzers", "nodes_wb_icon.svg",
        inputs=(GraphPort("forme", "shape"),), reason=_REASON_PART),
    _gn("aligner", "Aligner", "Align", "transforms", "nodes_wb_icon.svg",
        inputs=(GraphPort("forme", "shape"), GraphPort("axe_forme", "point"),
                GraphPort("axe_cible", "point"), GraphPort("pivot", "point")),
        reason=_REASON_PART, shape=True),
    _gn("rotation", "Rotation", "Rotate", "transforms", "nodes_rotate.svg",
        inputs=(GraphPort("forme", "shape"), GraphPort("axe", "point"),
                GraphPort("degre"), GraphPort("pivot", "point")),
        reason=_REASON_PART, shape=True),
    _gn("translation", "Translation", "Translate", "transforms",
        "nodes_translate.svg",
        inputs=(GraphPort("forme", "shape"), GraphPort("direction", "point")),
        reason=_REASON_PART, shape=True),
    _gn("echelle", "Échelle", "Uniform Scale", "transforms", "nodes_scale.svg",
        inputs=(GraphPort("forme", "shape"), GraphPort("facteur")),
        reason=_REASON_PART, shape=True),
    _gn("texte", "Texte", "Text", "text", "nodes_text.svg",
        fields=(GraphField("value", "text"),), reason=_REASON_TEXT),
    _gn("debug", "Impression de débogage", "Debug Print", "text",
        "nodes_wb_icon.svg", inputs=(GraphPort("donnees", "any"),),
        reason=_REASON_TEXT),
    # --- Python : l'évaluateur émet une instruction inerte ; le kernel
    #     exécute, et seulement si le document est autorisé (session). ---
    _gn("script", "Python", "Python", "script", "nodes_python.svg",
        inputs=(GraphPort("a", "any"), GraphPort("b", "any"),
                GraphPort("c", "any")),
        fields=(GraphField("code", "code"),),
        implemented=True),
    # --- Répétition variable : le graphe produit les instances, pas une
    #     forme. ``evaluate_instances`` les évalue ; ``evaluate`` refuse.
    _gn("cote", "Cote", "Dimension", "repeat", "Constraint_Dimension.svg",
        inputs=(GraphPort("valeur"),
                GraphPort("suite", "any", optional=True)),
        fields=(GraphField("feature", "text"), GraphField("prop", "text")),
        implemented=True),
    _gn("instance", "Instance", "Instance", "repeat",
        "PartDesign_LinearPattern.svg",
        inputs=(GraphPort("decalage", "point"),
                GraphPort("cotes", "any", optional=True)),
        implemented=True),
)

GRAPH_NODE_BY_TYPE: dict[str, GraphNode] = {n.type: n for n in GRAPH_NODES}
GRAPH_NODE_LABELS: dict[str, tuple[str, str]] = {
    n.type: (n.fr, n.en) for n in GRAPH_NODES
}

GRAPH_INPUT_LABELS: dict[str, tuple[str, str]] = {
    "depart": ("Départ", "Start"),
    "fin": ("Fin", "Stop"),
    "pas": ("Pas", "Step"),
    "nombre": ("Nombre", "Count"),
    "a": ("A", "A"),
    "b": ("B", "B"),
    "c": ("C", "C"),
    "x": ("X", "X"),
    "y": ("Y", "Y"),
    "z": ("Z", "Z"),
    "u": ("U", "U"),
    "v": ("V", "V"),
    "rayon": ("Rayon", "Radius"),
    "rayon1": ("Rayon 1", "Radius 1"),
    "rayon2": ("Rayon 2", "Radius 2"),
    "hauteur": ("Hauteur", "Height"),
    "ancrage": ("Ancrage", "Anchor"),
    "longueur": ("Longueur", "Length"),
    "largeur": ("Largeur", "Width"),
    "vecteur": ("Vecteur", "Vector"),
    "facteur": ("Facteur", "Factor"),
    "liste": ("Liste", "List"),
    "decalage": ("Décalage", "Offset"),
    "tick": ("Tick", "Tick"),
    "forme": ("Forme", "Shape"),
    "point": ("Point", "Point"),
    "point1": ("Point 1", "Point 1"),
    "point2": ("Point 2", "Point 2"),
    "point3": ("Point 3", "Point 3"),
    "direction": ("Direction", "Direction"),
    "angle": ("Angle", "Angle"),
    "angle1": ("Angle 1", "Angle 1"),
    "angle2": ("Angle 2", "Angle 2"),
    "angle_v1": ("Angle V1", "V1 Angle"),
    "angle_v2": ("Angle V2", "V2 Angle"),
    "angle_u": ("Angle U", "U Angle"),
    "ferme": ("Fermé", "Closed"),
    "centres": ("Centres", "Control Points"),
    "courbe": ("Courbe", "Curve"),
    "distance": ("Distance", "Distance"),
    "parametre": ("Paramètre", "Parameter"),
    "pas_helice": ("Pas d'hélice", "Pitch"),
    "gauche": ("Gauche", "Left"),
    "surface": ("Surface", "Surface"),
    "contour": ("Contour", "Bound"),
    "support": ("Support", "Support"),
    "objet": ("Objet", "Object"),
    "qualite": ("Qualité", "Quality"),
    "axe": ("Axe", "Axis"),
    "degre": ("Degré", "Degree"),
    "pivot": ("Pivot", "Pivot"),
    "axe_forme": ("Axe de la forme", "Shape Axis"),
    "axe_cible": ("Axe cible", "Target Axis"),
    "compte": ("Compte", "Count"),
    "graine": ("Graine", "Seed"),
    "mode": ("Mode", "Mode"),
    "echelle": ("Échelle", "Scale"),
    "sommet": ("Sommet", "Vertex"),
    "maillage": ("Maillage", "Mesh"),
    "face": ("Face", "Face"),
    "solide": ("Solide", "Solid"),
    "raye": ("Réglé", "Ruled"),
    "donnees": ("Données", "Data"),
    "valeur": ("Valeur", "Value"),
    "suite": ("Suite", "Next"),
    "cotes": ("Cotes", "Dimensions"),
}

GRAPH_FIELD_LABELS: dict[str, tuple[str, str]] = {
    "value": ("Valeur", "Value"),
    "name": ("Nom", "Name"),
    "op": ("Opération", "Operation"),
    "code": ("Code", "Code"),
    "feature": ("Fonction", "Feature"),
    "prop": ("Cote", "Property"),
}


def _graph_label(table: dict[str, tuple[str, str]], key: str,
                 lang: str = "fr") -> str:
    pair = table.get(key)
    if pair is None:
        return key
    return pair[0] if lang == "fr" else pair[1]


def graph_node_label(kind: str, lang: str = "fr") -> str:
    """Libellé d'un type de nœud de fonction graphe."""
    return _graph_label(GRAPH_NODE_LABELS, kind, lang)


def graph_input_label(key: str, lang: str = "fr") -> str:
    """Libellé d'un port d'entrée de fonction graphe."""
    return _graph_label(GRAPH_INPUT_LABELS, key, lang)


def graph_field_label(key: str, lang: str = "fr") -> str:
    """Libellé d'un champ propre au nœud (valeur, nom, opération)."""
    return _graph_label(GRAPH_FIELD_LABELS, key, lang)


def graph_category_label(category: str, lang: str = "fr") -> str:
    """Libellé d'une catégorie du catalogue de nœuds."""
    return _graph_label(GRAPH_CATEGORY_LABELS, category, lang)


def label_for_origin(internal_name: str, lang: str = "fr") -> str:
    """Return the SolidWorks name of an Origin plane or axis.

    ``internal_name`` is matched on a suffix basis because FreeCAD appends a
    numeric suffix (``XY_Plane001``) once a document holds several Bodies.
    """
    for table in (ORIGIN_PLANES, ORIGIN_AXES):
        for key, (fr, en) in table.items():
            if internal_name.startswith(key):
                return fr if lang == "fr" else en
    return internal_name

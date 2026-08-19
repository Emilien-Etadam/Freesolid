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


#: Libellés des nœuds de la fonction graphe (N004b). Les *ports* et les
#: types vivent dans ``engine/nodegraph._NODE_INPUTS`` — ici seulement
#: les mots que l'utilisateur lit. Ajouter un type sans entrée ici
#: casse ``graph_vocabulary`` exprès.
GRAPH_NODE_LABELS: dict[str, tuple[str, str]] = {
    "nombre": ("Nombre", "Number"),
    "variable": ("Variable", "Variable"),
    "serie": ("Série", "Series"),
    "calcul": ("Calcul", "Expression"),
    "point": ("Point", "Point"),
    "cylindre": ("Cylindre", "Cylinder"),
    "boite": ("Boîte", "Box"),
}

GRAPH_INPUT_LABELS: dict[str, tuple[str, str]] = {
    "depart": ("Départ", "Start"),
    "pas": ("Pas", "Step"),
    "nombre": ("Nombre", "Count"),
    "a": ("A", "A"),
    "b": ("B", "B"),
    "x": ("X", "X"),
    "y": ("Y", "Y"),
    "z": ("Z", "Z"),
    "rayon": ("Rayon", "Radius"),
    "hauteur": ("Hauteur", "Height"),
    "ancrage": ("Ancrage", "Anchor"),
    "longueur": ("Longueur", "Length"),
    "largeur": ("Largeur", "Width"),
}

GRAPH_FIELD_LABELS: dict[str, tuple[str, str]] = {
    "value": ("Valeur", "Value"),
    "name": ("Nom", "Name"),
    "op": ("Opération", "Operation"),
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

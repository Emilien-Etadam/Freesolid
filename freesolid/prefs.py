"""The preference table applied by the Setup command.

Declarative on purpose: every setting is a row, so the Setup command can
*report* what it changed instead of silently mutating the user's config, and
so the table can be unit-tested without FreeCAD.

About ``verified``
------------------
FreeCAD's parameter paths are not a public API and some have moved between
releases. Rows marked ``verified=False`` are written from documentation
rather than from a run against a real FreeCAD build; the Setup command lists
them separately so a wrong key surfaces as "not applied" instead of as a
silent no-op. Flip them to ``True`` once checked against Tools -> Edit
parameters on a real install.
"""

from dataclasses import dataclass, field

#: Kept out of the table because it is applied through a dedicated code path
#: (the workbench list is a comma-separated blob, not a scalar).
#: FreeSolidWorkbench MUST stay in this list: Setup once hid the plugin's own
#: workbench, wiping its toolbars from the selector (seen on 1.1.3).
KEEP_WORKBENCHES: tuple[str, ...] = (
    "FreeSolidWorkbench",
    "PartDesignWorkbench",
    "SketcherWorkbench",
    "AssemblyWorkbench",
    "TechDrawWorkbench",
    "PartWorkbench",
    "DraftWorkbench",
    "SpreadsheetWorkbench",
)


@dataclass(frozen=True)
class Pref:
    """One parameter to write.

    Attributes:
        path: parameter group, without the ``User parameter:`` prefix.
        key: parameter name inside that group.
        kind: one of ``bool``, ``int``, ``float``, ``str`` — selects the
            ``ParamGet`` setter.
        value: the value to write.
        why: user-facing justification, shown in the Setup report.
        verified: whether the path/key pair was checked on a real install.
    """

    path: str
    key: str
    kind: str
    value: object
    why: str
    verified: bool = True
    tags: tuple[str, ...] = field(default_factory=tuple)


PREFS: tuple[Pref, ...] = (
    # verified: après Setup sur 1.1.3, la barre d'état affiche « Blender » —
    # FreeCAD consomme bien la clé (capture utilisateur, 2026-08-02).
    Pref("BaseApp/Preferences/View", "NavigationStyle", "str",
         "Gui::BlenderNavigationStyle",
         "Molette = rotation, comme SolidWorks. FreeCAD n'a pas de style "
         "SolidWorks natif ; Blender en est le plus proche (le pan est sur "
         "Maj+milieu au lieu de Ctrl+milieu).",
         tags=("navigation",)),

    # verified: 1.1.3 démarre effectivement dans PartDesign après Setup
    # (observation utilisateur, 2026-08-02).
    Pref("BaseApp/Preferences/General", "AutoloadModule", "str",
         "PartDesignWorkbench",
         "Démarrer directement dans l'atelier de modélisation de pièces, "
         "sans passer par l'écran de démarrage.",
         tags=("workbench",)),

    # The three rows below split the tree out of the Combo View, so the Tasks
    # panel no longer *replaces* the model tree mid-command. This is the fix
    # for the single most disorienting behaviour for a SolidWorks user.
    # verified: diagnostic 1.1.3 du 2026-08-02 — les clés existent ET le
    # recensement des panneaux montre l'effet (Tree view, Property view et
    # Tasks en docks séparés, aucune Combo View).
    Pref("BaseApp/Preferences/DockWindows/ComboView", "Enabled", "bool", False,
         "Sortir l'arbre du panneau combiné : il ne disparaît plus quand une "
         "fonction s'ouvre.",
         tags=("layout",)),
    Pref("BaseApp/Preferences/DockWindows/TreeView", "Enabled", "bool", True,
         "L'arbre du modèle vit dans son propre panneau.",
         tags=("layout",)),
    Pref("BaseApp/Preferences/DockWindows/PropertyView", "Enabled", "bool", True,
         "L'éditeur de propriétés vit dans son propre panneau, à côté de "
         "l'arbre — disposition PropertyManager.",
         tags=("layout",)),

    # verified: rotation observée autour du point sous le curseur sur 1.1.3
    # (observation utilisateur, 2026-08-02).
    Pref("BaseApp/Preferences/View", "UseNewRotationCenter", "bool", True,
         "Rotation autour du point sous le curseur, comportement attendu en "
         "CAO mécanique.",
         tags=("navigation",)),

    # Clé présente avec notre valeur sur 1.1.3, mais l'effet n'a pas encore
    # de scénario d'observation (il faut deux solides qui se croisent dans
    # l'atelier Part) : reste non vérifié tant qu'il n'est pas observé.
    Pref("BaseApp/Preferences/Mod/PartDesign", "AutoGroupSolids", "bool", False,
         "Ne pas regrouper automatiquement les solides : garder un Body = "
         "une pièce.",
         verified=False, tags=("partdesign",)),

    # --- Apparence SolidWorks : viewport clair, pas de page de démarrage ---
    # Vérification à l'œil : le fond doit devenir un dégradé gris clair.
    Pref("BaseApp/Preferences/Mod/Start", "ShowOnStartup", "bool", False,
         "Ouvrir directement sur l'espace de modélisation, sans page de "
         "démarrage — FreeCAD s'ouvre prêt à travailler.",
         verified=False, tags=("appearance",)),
    Pref("BaseApp/Preferences/View", "Simple", "bool", False,
         "Fond de la vue 3D en dégradé plutôt qu'en couleur unie.",
         verified=False, tags=("appearance",)),
    Pref("BaseApp/Preferences/View", "Gradient", "bool", True,
         "Active le dégradé de fond.",
         verified=False, tags=("appearance",)),
    Pref("BaseApp/Preferences/View", "BackgroundColor2", "uint", 0xE8ECEF00,
         "Fond clair type SolidWorks (borne 1 du dégradé — haut ou bas à "
         "confirmer à l'œil).",
         verified=False, tags=("appearance",)),
    Pref("BaseApp/Preferences/View", "BackgroundColor3", "uint", 0xF7F8F900,
         "Fond clair type SolidWorks (borne 2 du dégradé).",
         verified=False, tags=("appearance",)),
)


def unverified() -> tuple[Pref, ...]:
    """Rows whose parameter path still needs checking on a real install."""
    return tuple(p for p in PREFS if not p.verified)


def by_tag(tag: str) -> tuple[Pref, ...]:
    return tuple(p for p in PREFS if tag in p.tags)


def apply_all(param_get):
    """Write every row, returning ``(applied, failed)``.

    Args:
        param_get: a callable behaving like ``FreeCAD.ParamGet`` — injected
            rather than imported so the logic is testable with a fake.

    Returns:
        A tuple of two lists: the ``Pref`` rows written without raising, and
        ``(Pref, exception)`` pairs for the rows that failed.
    """
    applied, failed = [], []
    setters = {
        "bool": "SetBool",
        "int": "SetInt",
        "float": "SetFloat",
        "str": "SetString",
        # Colours are packed RGBA in unsigned 32-bit; SetInt would overflow.
        "uint": "SetUnsigned",
    }
    for pref in PREFS:
        try:
            group = param_get("User parameter:" + pref.path)
            getattr(group, setters[pref.kind])(pref.key, pref.value)
            applied.append(pref)
        except Exception as exc:  # noqa: BLE001 - reported, not swallowed
            failed.append((pref, exc))
    return applied, failed

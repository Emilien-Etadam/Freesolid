"""Document, fichiers, historique, paramètres et lectures.

Méthodes : kernel.py et les mixins files, equations, configs,
templates, docprops, materials, treeorg, tree, clipboard, drawing,
selectchain, selftest.
"""

from engine.ops._base import Op, Req


OPS = (
    Op("ping"),
    Op("document_status"),             # ouvert, modifié depuis l'enregistrement
    Op("list_plugins"),            # nom + point d'entrée JS de chaque plugin chargé
    # Runs the full flow headless and returns stats — the same
    # paste-me-the-report loop that debugged the Qt addon.
    Op("selftest"),
    Op("new_part"),                    # optional: name
    # Phase E — évaluer + mise en plan.
    Op("mass_properties"),             # optional: density (g/cm³)
    Op("material_library"),            # lecture : matières proposées
    Op("list_templates"),              # lecture : gabarits de pièce
    Op("set_folder", Req(("features", list), optional={"folder": str}),
       undo=True),
    Op("rename_folder", Req(("folder", str), optional={"name": str}),
       undo=True),
    Op("feature_relations", Req(("feature", str))),
                                       # lecture : parents, enfants
    Op("list_configurations"),         # lecture : noms, active
    Op("add_configuration", Req(("name", str)), undo=True,
       no_replay="pas une fonction du groupe"),
    Op("activate_configuration", Req(("name", str)), undo=True),
    Op("rename_configuration", Req(("name", str), ("new_name", str)),
       undo=True),
    Op("delete_configuration", Req(("name", str)), undo=True),
    Op("configuration_table"),         # lecture : cotes par configuration
    Op("set_configuration_values", Req(("values", dict)), undo=True),
    Op("save_template", Req(("name", str))),
    Op("new_from_template", Req(("name", str))),
    Op("paste_feature", Req(("feature", str), optional={
        "face": int, "plane": str, "datum": str}), undo=True),
    Op("set_body_material", Req(("body", str), optional={
        "material": str, "density": float}), undo=True),
    Op("set_face_color", Req(("faces", list), "color"), undo=True),
    Op("measure", Req(("a_kind", str), ("a_id", int),
                      ("b_kind", str), ("b_id", int))),  # face|edge + id
    Op("make_drawing", Req(("path", str)), undo=True),
                                       # optional: scale, dims (bool, défaut True),
                                       # section ("X"|"Y"|"Z") — 3 vues + cotes + coupe, export DXF
    Op("undo", Req(optional={"steps": int, "sketch": str})),
                                       # une transaction = un Ctrl+Z ;
                                       # sketch : depuis l'esquisse ouverte,
                                       # ses pas seulement
    Op("redo", Req(optional={"steps": int, "sketch": str})),
    Op("undo_history", Req(optional={"sketch": str})),
                                       # lecture : pas à défaire / refaire
    Op("rebuild_errors"),              # lecture : fonctions en erreur
    Op("set_comment", Req(("feature", str), optional={"text": str}),
       undo=True),
    Op("set_hidden", Req(("objects", list), optional={"hidden": bool})),
    Op("edge_chain", Req(("edge", int), optional={"mode": str, "face": int})),
    Op("set_suppressed", Req(("features", list),
                             optional={"suppressed": bool}), undo=True),
    Op("document_properties"),         # lecture : auteur, société, libres
    Op("set_document_properties", Req(("values", dict))),
    Op("export_part", Req(("path", str))),  # .stl ou .step selon l'extension
    Op("preview", Req(("op", str), ("params", dict))),
                                       # aperçu jaune : op exécutée puis annulée
    Op("progress"),                    # avancement hors noyau — jamais de verrou
    Op("set_param", Req(("feature", str), ("prop", str), "value"), undo=True),
    Op("set_params", Req(("feature", str), ("values", dict)),
       undo=True, preview=True),
                                       # valeur numérique OU expression
    # Paramétrique — variables globales (App::VarSet) et équations.
    Op("list_variables"),
    Op("set_variable", Req(("name", str), "value"), undo=True),
    Op("delete_variable", Req(("name", str)), undo=True),
    Op("rename", Req(("feature", str), ("label", str)), undo=True),
    Op("get_params", Req(("feature", str))),  # editable numeric properties
    Op("set_tip", undo=True),          # optional: feature — nom d'une
                                       # ligne d'historique (fonction,
                                       # esquisse libre, surface).
                                       # Absent = barre avant la première
    Op("tip_to_end", undo=True),       # back to the final state
    Op("delete_rolled_back", undo=True),  # tout ce qui est sous la barre
    Op("delete_feature", Req(("feature", str)), undo=True),
    Op("reorder_feature", Req(("feature", str), ("target", str),
                              optional={"after": bool}), undo=True),
    Op("save_part", Req(("path", str))),
    Op("open_part", Req(("path", str))),
    Op("list_dir", Req(optional={"path": str})),
                                       # dossier ; absent = dossier personnel
    Op("get_tree"),
    Op("rebuild"),                     # recalcul forcé de tout l'arbre
    Op("tessellate"),                  # optional: deviation
    Op("tessellate_edges"),            # optional: deviation — picking d'arêtes
)

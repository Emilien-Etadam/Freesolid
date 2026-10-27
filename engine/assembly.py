"""Assemblage : composants, liaisons, solveur, interférences.

Mixin de ``Kernel``. Pas d'import FreeCAD au niveau du module :
les méthodes importent le noyau à l'appel, pour éviter un cycle.
"""

class AssemblyMixin:
    # -- assemblage -------------------------------------------------------

    _JOINT_TYPES = {
        # Contraintes standard d'un modeleur de bureau, traduites en
        # liaisons natives : coïncidente et tangente = distance nulle entre
        # les éléments, concentrique = cylindrique (même axe).
        "coincidente": "Distance", "tangente": "Distance",
        "concentrique": "Cylindrical", "parallele": "Parallel",
        "perpendiculaire": "Perpendicular", "angle": "Angle",
        "verrouillage": "Fixed",
        "fixe": "Fixed", "fixed": "Fixed",
        "pivot": "Revolute",
        "cylindrique": "Cylindrical",
        "glissiere": "Slider",
        "rotule": "Ball",
        "distance": "Distance",
        "engrenages": "Gears",
        "cremaillere": "RackPinion",
        "vis": "Screw",
        "courroie": "Belt",
    }

    #: Contraintes à distance nulle par construction.
    _ZERO_DISTANCE_MATES = frozenset({"coincidente", "tangente"})

    def _require_assembly(self):
        from engine.kernel import KernelError
        if self._doc is None or not self._assembly:
            raise KernelError(
                "aucun assemblage ouvert — commencez par new_assembly")
        return self._doc

    def new_assembly(self, name="Assemblage"):
        """Nouveau document d'assemblage : des pièces .FCStd insérées par
        référence (App::Link) dans un Assembly::AssemblyObject, avec le
        groupe de joints du solveur natif (plateforme de référence 1.1.3,
        repli 1.0.2)."""
        App = self._app()
        self._close_current()
        self._doc = App.newDocument("FreeSolidAsm")
        self._setup_doc(self._doc)
        self._assembly = True
        asm = self._doc.addObject("Assembly::AssemblyObject", "Assembly")
        asm.Label = str(name) if name else self._t("Assemblage")
        joints = self._doc.addObject("Assembly::JointGroup", "Joints")
        asm.addObject(joints)
        return self.assembly_tree()

    def _assembly_object(self):
        from engine.kernel import KernelError
        doc = self._require_assembly()
        for obj in doc.Objects:
            if obj.TypeId == "Assembly::AssemblyObject":
                return obj
        raise KernelError("assemblage sans Assembly::AssemblyObject — "
                          "recréez-le (ancien format)")

    def _joint_group(self):
        doc = self._require_assembly()
        for obj in doc.Objects:
            if obj.TypeId == "Assembly::JointGroup":
                return obj
        asm = self._assembly_object()
        joints = doc.addObject("Assembly::JointGroup", "Joints")
        asm.addObject(joints)
        return joints

    def _solve_assembly(self):
        from engine.kernel import (
            KernelError,
            _explain,
        )
        asm = self._assembly_object()
        try:
            asm.solve()
        except Exception as exc:  # noqa: BLE001 - sur-contraint, surtout
            raise KernelError(
                "le solveur d'assemblage a échoué : {}".format(
                    _explain(exc)))

    def insert_component(self, path):
        """Insérer une pièce : lien vers le premier corps de son fichier.

        La pièce reste un fichier séparé — la modifier puis rouvrir
        l'assemblage met à jour toutes ses instances, comme dans
        les modeleurs courants.
        """
        import os
        from engine.kernel import KernelError
        doc = self._require_assembly()
        App = self._app()
        path = self._user_path(path, (".FCStd",), must_exist=True)
        if not getattr(doc, "FileName", ""):
            # Un App::Link externe exige un document propriétaire déjà
            # enregistré (« Owner document not saved » sinon) : première
            # insertion = enregistrement temporaire ; « Enregistrer »
            # le déplacera où l'utilisateur veut, FreeCAD réécrit les
            # chemins relatifs au saveAs.
            import tempfile
            doc.saveAs(os.path.join(tempfile.gettempdir(),
                                    "freesolid-assemblage.FCStd"))
        part_doc = None
        opened_here = False
        for open_doc in App.listDocuments().values():
            if getattr(open_doc, "FileName", "") == path:
                part_doc = open_doc
                break
        if part_doc is None:
            try:
                part_doc = App.openDocument(path, True)  # hidden
            except TypeError:
                part_doc = App.openDocument(path)
            opened_here = True
            self._setup_doc(part_doc)
        bodies = [o for o in part_doc.Objects
                  if o.TypeId == "PartDesign::Body"]
        if not bodies:
            if opened_here:
                try:
                    App.closeDocument(part_doc.Name)
                except Exception:
                    pass
            raise KernelError(
                "aucun corps PartDesign dans {}".format(path))
        try:
            asm = self._assembly_object()
        except KernelError:
            asm = None  # assemblage ancien format : lien à la racine
        if asm is not None:
            # 1.1.3 : newObject évite « The graph must be a DAG ».
            link = asm.newObject("App::Link", "Component")
        else:
            link = doc.addObject("App::Link", "Component")
        link.LinkedObject = bodies[0]
        link.Label = os.path.splitext(os.path.basename(path))[0]
        existing = [o for o in doc.Objects
                    if o.TypeId == "App::Link" and o is not link]
        if not existing:
            # Le premier composant est fixé, comme dans les modeleurs courants.
            try:
                self._ground(link)
            except Exception:
                pass  # sans ancrage, le solveur bougera tout — non fatal
        doc.recompute()
        return self.assembly_tree()

    def _ground(self, link):
        """Fixer un composant (GroundedJoint du module natif)."""
        import JointObject
        doc = self._require_assembly()
        joint = doc.addObject("App::FeaturePython", "GroundedJoint")
        self._joint_group().addObject(joint)
        try:
            JointObject.GroundedJoint(joint, link)
        except TypeError:
            JointObject.GroundedJoint(joint)
            if hasattr(joint, "ObjectToGround"):
                joint.ObjectToGround = link
        joint.Label = self._t("Fixé — {}").format(link.Label)

    def set_component_grounded(self, component, grounded=True):
        """Fixer ou libérer un composant (menu du composant)."""
        from engine.kernel import KernelError
        doc = self._require_assembly()
        link = doc.getObject(str(component))
        if link is None or link.TypeId != "App::Link":
            raise KernelError("composant inconnu : {}".format(component))
        anchors = [o for o in self._joint_group().Group
                   if getattr(o, "ObjectToGround", None) is link]
        if grounded and not anchors:
            self._ground(link)
        elif not grounded:
            for anchor in anchors:
                doc.removeObject(anchor.Name)
        doc.recompute()
        try:
            self._solve_assembly()
            doc.recompute()
        except KernelError:
            pass  # rien à résoudre ou sur-contraint : l'état reste lisible
        return self.assembly_tree()

    #: nos noms -> l'énumération JointType du module natif. Les quatre
    #: derniers sont les contraintes mécaniques (vues dans le spike).

    def add_joint(self, component1, component2, type="fixe",
                  sub1=None, sub2=None, distance=None, distance2=None,
                  angle_min=None, angle_max=None,
                  length_min=None, length_max=None, angle=None,
                  flip=False):
        """Contrainte d'assemblage entre deux composants, résolue par le
        solveur natif (MbD). ``sub1``/``sub2`` : sous-élément visé
        (« Face3 », « Edge5 ») — la face cliquée dans la zone graphique.
        """
        from engine.kernel import (
            KernelError,
            _explain,
        )
        import JointObject
        doc = self._require_assembly()
        asm = self._assembly_object()
        if str(type).lower() == "auto":
            # Contrainte rapide (Alt+glisser une face sur une autre) : deux
            # cylindres se centrent, le reste se plaque.
            type = self._auto_joint_type(doc, component1, sub1,
                                         component2, sub2)
        target = self._JOINT_TYPES.get(str(type).lower())
        if target is None:
            raise KernelError(
                "contrainte inconnue « {} » — attendu : {}".format(
                    type, ", ".join(sorted(set(self._JOINT_TYPES)
                                           - {"fixed"}))))
        links = {}
        for name in (component1, component2):
            obj = doc.getObject(str(name))
            if obj is None or obj.TypeId != "App::Link":
                raise KernelError("composant inconnu : {}".format(name))
            links[name] = obj
        if str(component1) == str(component2):
            raise KernelError("choisissez deux composants différents")

        joint = doc.addObject("App::FeaturePython", "Joint")
        self._joint_group().addObject(joint)
        try:
            JointObject.Joint(joint, 0)
        except Exception as exc:  # noqa: BLE001
            doc.removeObject(joint.Name)
            raise KernelError(_explain(exc))
        allowed = list(joint.getEnumerationsOfProperty("JointType"))
        if target not in allowed:
            doc.removeObject(joint.Name)
            raise KernelError(
                "cette version ne propose pas « {} » — disponibles : "
                "{}".format(target, ", ".join(allowed)))
        joint.JointType = target
        # 1.1.3 : forme directe doublée via setJointConnectors. Un sub vide
        # se double aussi (["", ""]) — banc natif : Face2+Face2 → centre.
        # 1.0.2 lève AttributeError ('NoneType' … 'Placement') : repli.
        refs = []
        for name, sub in ((component1, sub1), (component2, sub2)):
            sub_name = str(sub) if sub else ""
            refs.append((links[name], [sub_name, sub_name]))
        try:
            joint.Proxy.setJointConnectors(joint, refs)
        except Exception:  # noqa: BLE001 - 1.0.2 n'a pas l'API
            # Références : la propriété attend LE couple
            # (objet, [sous-éléments]) — « Expect input sequence of size 2 »
            # si on l'emballe dans une liste (vu sur 1.1.3). Forme UI ancrée
            # à l'assemblage d'abord, repli sur la forme directe.
            for ref_prop, name, sub in (
                    ("Reference1", component1, sub1),
                    ("Reference2", component2, sub2)):
                link = links[name]
                sub_name = str(sub) if sub else ""
                forms = [
                    (asm, ["{}.{}".format(link.Name, sub_name)
                           if sub_name else "{}.".format(link.Name)]),
                    (link, [sub_name] if sub_name else [""]),
                ]
                assigned = False
                last_error = None
                for form in forms:
                    try:
                        setattr(joint, ref_prop, form)
                        assigned = True
                        break
                    except Exception as exc:  # noqa: BLE001
                        last_error = exc
                if not assigned:
                    doc.removeObject(joint.Name)
                    raise KernelError(_explain(last_error))
        if str(type).lower() in self._ZERO_DISTANCE_MATES:
            distance = 0.0
        if distance is not None and hasattr(joint, "Distance"):
            joint.Distance = float(distance)
        if angle is not None and hasattr(joint, "Angle"):
            joint.Angle = float(angle)
        if flip:
            # Aligné / opposé : retourne un des deux repères de liaison.
            try:
                joint.Proxy.flipOnePart(joint)
            except Exception as exc:  # noqa: BLE001
                doc.removeObject(joint.Name)
                raise KernelError(_explain(exc))
        if distance2 is not None and hasattr(joint, "Distance2"):
            joint.Distance2 = float(distance2)
        # Limites de mouvement (contraintes avancées).
        for value, prop, enable in (
                (angle_min, "AngleMin", "EnableAngleMin"),
                (angle_max, "AngleMax", "EnableAngleMax"),
                (length_min, "LengthMin", "EnableLengthMin"),
                (length_max, "LengthMax", "EnableLengthMax")):
            if value is not None and hasattr(joint, prop):
                setattr(joint, enable, True)
                setattr(joint, prop, float(value))
        mate_labels = {"coincidente": "Coïncidente", "tangente": "Tangente",
                       "concentrique": "Concentrique",
                       "parallele": "Parallèle",
                       "perpendiculaire": "Perpendiculaire",
                       "angle": "Angle", "verrouillage": "Verrouillage"}
        labels = {"Fixed": "Fixe", "Revolute": "Pivot",
                  "Cylindrical": "Cylindrique", "Slider": "Glissière",
                  "Ball": "Rotule", "Distance": "Distance",
                  "Gears": "Engrenages", "RackPinion": "Crémaillère",
                  "Screw": "Vis", "Belt": "Courroie"}
        joint.Label = self._t("{} — {} / {}").format(
            self._t(mate_labels.get(str(type).lower(),
                                    labels.get(target, target))),
            links[component1].Label, links[component2].Label)
        doc.recompute()
        try:
            self._solve_assembly()
        except KernelError:
            doc.removeObject(joint.Name)
            doc.recompute()
            raise
        return self.assembly_tree()

    def solve_assembly(self):
        """Relancer le solveur — après un déplacement à la main."""
        self._solve_assembly()
        self._require_assembly().recompute()
        return self.assembly_tree()

    @staticmethod
    def _auto_joint_type(doc, component1, sub1, component2, sub2):
        """« concentrique » si les deux faces sont des cylindres (ou des
        cônes), sinon « coincidente »."""
        kinds = []
        for name, sub in ((component1, sub1), (component2, sub2)):
            obj = doc.getObject(str(name))
            try:
                face = obj.Shape.getElement(str(sub))
                kinds.append(face.Surface.TypeId)
            except Exception:  # noqa: BLE001
                kinds.append("")
        round_ = ("Part::GeomCylinder", "Part::GeomCone")
        return ("concentrique" if all(k in round_ for k in kinds)
                else "coincidente")

    def move_component(self, component, x=0.0, y=0.0, z=0.0,
                       yaw=0.0, pitch=0.0, roll=0.0):
        """Positionner un composant : translation + lacet/tangage/roulis."""
        from engine.kernel import KernelError
        doc = self._require_assembly()
        App = self._app()
        link = doc.getObject(str(component))
        if link is None or link.TypeId != "App::Link":
            raise KernelError("composant inconnu : {}".format(component))
        link.Placement = App.Placement(
            App.Vector(float(x), float(y), float(z)),
            App.Rotation(float(yaw), float(pitch), float(roll)))
        doc.recompute()
        # Avec des contraintes posées, le solveur reprend la main — le
        # déplacement manuel devient une suggestion, comme dans les
        # modeleurs courants.
        group = next((o for o in doc.Objects
                      if o.TypeId == "Assembly::JointGroup"), None)
        if group is not None and any(hasattr(o, "JointType")
                                     for o in group.Group):
            try:
                self._solve_assembly()
                doc.recompute()
            except KernelError:
                pass  # sur-contraint : la position saisie reste
        return self.assembly_tree()

    def array_component(self, component, count, dx=0.0, dy=0.0, dz=0.0):
        """Répétition de composants : n instances du même fichier, au pas
        donné — visserie, entretoises, séries à imprimer."""
        from engine.kernel import KernelError
        doc = self._require_assembly()
        App = self._app()
        link = doc.getObject(str(component))
        if link is None or link.TypeId != "App::Link":
            raise KernelError("composant inconnu : {}".format(component))
        total = int(count)
        if total < 2:
            raise KernelError("au moins 2 occurrences")
        base_placement = link.Placement
        for i in range(1, total):
            copy = doc.addObject("App::Link", "Component")
            copy.LinkedObject = link.LinkedObject
            copy.Label = self._t("{} ({})").format(link.Label, i + 1)
            offset = App.Vector(float(dx) * i, float(dy) * i,
                                float(dz) * i)
            copy.Placement = App.Placement(
                base_placement.Base + offset, base_placement.Rotation)
            try:
                self._assembly_object().addObject(copy)
            except KernelError:
                pass
        doc.recompute()
        return self.assembly_tree()

    def assembly_tree(self):
        from engine.vocab import type_key_for
        doc = self._require_assembly()
        joints = []
        grounded = set()
        group = next((o for o in doc.Objects
                      if o.TypeId == "Assembly::JointGroup"), None)
        for obj in (group.Group if group is not None else ()):
            if hasattr(obj, "ObjectToGround"):
                target = getattr(obj, "ObjectToGround", None)
                if target is not None:
                    grounded.add(target.Name)
                joints.append({"name": obj.Name, "label": obj.Label,
                               "type": "Fixé"})
            elif hasattr(obj, "JointType"):
                joints.append({"name": obj.Name, "label": obj.Label,
                               "type": str(obj.JointType)})
        components = []
        for obj in doc.Objects:
            if obj.TypeId != "App::Link":
                continue
            placement = obj.Placement
            components.append({
                "name": obj.Name,
                "label": obj.Label,
                "type_key": type_key_for(obj.TypeId),
                "grounded": obj.Name in grounded,
                "position": [placement.Base.x, placement.Base.y,
                             placement.Base.z],
                "rotation": [float(v)
                             for v in placement.Rotation.toEuler()],
            })
        return {"assembly": True, "components": components,
                "joints": joints, "options": self.document_options()}

    def tessellate_assembly(self, deviation=None):
        """Un maillage par composant — la sélection au clic est par
        composant, pas par face (v1). Sans ``deviation``, celle de la
        qualité d'image de l'assemblage."""
        from . import protocol
        doc = self._require_assembly()
        angle = None
        if deviation is None:
            deviation, angle, _edges = self._display_mesh()
        components = []
        for obj in doc.Objects:
            if obj.TypeId != "App::Link":
                continue
            linked = getattr(obj, "LinkedObject", None)
            shape = getattr(linked, "Shape", None)
            if shape is None or not shape.Faces:
                continue
            moved = shape.copy()
            moved.Placement = obj.Placement.multiply(moved.Placement)
            faces = []
            for i, face in enumerate(self._meshed(moved, deviation, angle).Faces):
                vertices, triangles = face.tessellate(float(deviation))
                faces.append(
                    (i, [(v.x, v.y, v.z) for v in vertices], triangles))
            components.append({"name": obj.Name, "label": obj.Label,
                               "mesh": protocol.pack_mesh(faces)})
        return {"components": components}

    def check_interference(self):
        """Détection d'interférences : volume commun de chaque paire de
        composants — le contrôle avant impression d'un assemblage."""
        doc = self._require_assembly()
        shapes = []
        for obj in doc.Objects:
            if obj.TypeId != "App::Link":
                continue
            linked = getattr(obj, "LinkedObject", None)
            shape = getattr(linked, "Shape", None)
            if shape is None or not shape.Solids:
                continue
            moved = shape.copy()
            moved.Placement = obj.Placement.multiply(moved.Placement)
            shapes.append((obj.Label, moved))
        pairs = []
        for i in range(len(shapes)):
            for j in range(i + 1, len(shapes)):
                try:
                    volume = float(
                        shapes[i][1].common(shapes[j][1]).Volume)
                except Exception:
                    continue
                if volume > 1e-6:
                    pairs.append({"a": shapes[i][0], "b": shapes[j][0],
                                  "volume_mm3": volume})
        return {"interferences": pairs}

    def spike_assembly(self):
        """Rapport d'exploration : l'atelier Assembly 1.x est-il utilisable
        headless (objets, solveur, module des joints) ?

        Ne lève jamais — le verdict guide la phase C3 ; il ne casse pas
        le selftest. Chaque tentative note sa réussite ou son erreur.
        """
        App = self._app()
        result = {"freecad": ".".join(str(v) for v in App.Version()[:3])}
        doc = None
        try:
            doc = App.newDocument("FreeSolidSpike")
            try:
                asm = doc.addObject("Assembly::AssemblyObject", "Assembly")
                result["assembly_object"] = True
                result["has_solve"] = hasattr(asm, "solve")
                if result["has_solve"]:
                    try:
                        asm.solve()
                        result["solve_empty_ok"] = True
                    except Exception as exc:
                        result["solve_empty_error"] = str(exc)[:160]
            except Exception as exc:
                result["assembly_object"] = False
                result["assembly_object_error"] = str(exc)[:160]
            group = None
            try:
                group = doc.addObject("Assembly::JointGroup", "Joints")
                result["joint_group"] = True
                try:
                    # Le groupe de joints DANS l'assemblage — le proxy du
                    # joint remonte à son parent pour trouver l'assemblage
                    # (« 'NoneType' object has no attribute 'Type' » quand
                    # il est orphelin, vu sur 1.1.3).
                    asm.addObject(group)
                    result["joint_group_in_assembly"] = True
                except Exception as exc:
                    result["joint_group_in_assembly"] = False
                    result["joint_group_in_assembly_error"] = str(exc)[:120]
            except Exception as exc:
                result["joint_group"] = False
                result["joint_group_error"] = str(exc)[:160]
            try:
                import JointObject
                result["joint_module"] = True
                result["joint_symbols"] = [
                    n for n in dir(JointObject)
                    if not n.startswith("_")][:40]
                try:
                    # La vérité terrain : le constructeur réel de cette
                    # version, lu sur la machine de l'utilisateur.
                    import inspect
                    result["joint_init_source"] = inspect.getsource(
                        JointObject.Joint.__init__)[:1500]
                except Exception as exc:
                    result["joint_init_source_error"] = str(exc)[:120]
                joint = doc.addObject("App::FeaturePython", "SpikeJoint")
                if group is not None:
                    try:
                        group.addObject(joint)
                    except Exception as exc:
                        result["joint_into_group_error"] = str(exc)[:120]
                created = False
                for args in ((joint,), (joint, 0), (joint, "Fixed")):
                    try:
                        JointObject.Joint(*args)
                        created = True
                        break
                    except TypeError:
                        continue
                    except Exception as exc:
                        result["joint_proxy_error"] = str(exc)[:160]
                        break
                result["joint_proxy"] = created
                if created:
                    skip = {"Label", "Label2", "ExpressionEngine",
                            "Visibility"}
                    result["joint_properties"] = [
                        p for p in joint.PropertiesList
                        if p not in skip][:25]
            except Exception as exc:
                result["joint_module"] = False
                result["joint_module_error"] = str(exc)[:160]
        except Exception as exc:  # noqa: BLE001
            result["error"] = str(exc)[:160]
        finally:
            if doc is not None:
                try:
                    App.closeDocument(doc.Name)
                except Exception:
                    pass
        return result

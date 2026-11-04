"""Corps concernés : un enlèvement creuse aussi d'autres corps.

Deux sources, un seul mécanisme. Sans liste, comme les modeleurs
courants, elles creusent les corps qu'elles traversent (``_cut_others``) ;
sinon ceux qu'on leur donne :

- un enlèvement seul (extrudé, gorge, perçage…), ``bodies`` ;
- une répétition de fonctions, ``scope`` : ses occurrences creusent, la
  fonction répétée creusant elle-même à sa place (``_SCOPE_INSTANCES``).

La réédition de l'un comme de l'autre coche et décoche ses « Corps
creusés » (``_set_cut_bodies``).

Dans chaque corps concerné, un booléen Soustraire prend pour outil une
forme figée interne : les formes d'enlèvement, placées comme FreeCAD
place les occurrences. Ce booléen est une étape cachée
(``_scope_hidden``), qui compte au rang de sa source dans la barre de
retour, comme les étapes d'une suppression de corps. « À travers tout »
y traverse tous les corps, pas seulement celui de l'enlèvement
(``_through_extended``). Le moteur recalcule l'outil quand la source
change (``_refresh_scopes``).

Tout est en objets FreeCAD standard : le fichier s'ouvre dans FreeCAD.
Les fonctions du module se testent sans FreeCAD ; les méthodes du mixin
importent le noyau à l'appel.
"""

import json
import math

from engine.bodypattern import linear_steps, polar_angles

#: Fonctions qui enlèvent de la matière : les seules qui creusent les
#: corps concernés.
_SUBTRACTIVE_TYPES = frozenset({
    "PartDesign::Pocket", "PartDesign::Groove", "PartDesign::Hole",
})

#: Répétitions de fonctions dont les occurrences creusent les corps
#: concernés (``_occurrences``).
_PATTERN_TYPES = frozenset({
    "PartDesign::LinearPattern", "PartDesign::PolarPattern",
    "PartDesign::Mirrored",
})


def is_subtractive_type(type_id):
    """Vrai pour une fonction qui enlève de la matière."""
    return (type_id in _SUBTRACTIVE_TYPES
            or str(type_id).startswith("PartDesign::Subtractive"))


def scope_names(text):
    """Noms des corps concernés, rangés « Body001;Body002 »."""
    return [name for name in str(text or "").split(";") if name]


def format_scope(names):
    return ";".join(names)


class BodyScopeMixin:
    #: Posée sur chaque répétition neuve : l'outil de ses corps concernés
    #: ne prend que les occurrences — la fonction répétée creuse elle-même
    #: à sa place — et ses booléens sont des étapes cachées. Absente
    #: (répétition d'un fichier d'avant) : toutes les occurrences, et les
    #: booléens en lignes de l'arbre.
    _SCOPE_INSTANCES = "FreeSolidScopeInstances"

    # ---------- corps concernés ----------

    def _attach_scope(self, pattern, targets):
        """Les enlèvements de ``pattern`` (répétés, ou lui-même) creusent
        aussi les corps ``targets``."""
        self._refuse_unscoped(pattern)
        for target in targets:
            self._make_scope_cut(pattern, target)
        self._stamp_text(pattern, "FreeSolidScope",
                         format_scope(t.Name for t in targets))

    def _refuse_unscoped(self, pattern):
        """Refuse des corps concernés à ce qui n'y creuserait rien :
        désactivé, sans enlèvement, ou répétition sans autre occurrence."""
        from engine.kernel import KernelError
        if getattr(pattern, "Suppressed", False) or not self._scope_seeds(
                pattern):
            off = [f for f in [pattern] + self._scope_originals(pattern)
                   if getattr(f, "Suppressed", False)
                   and (f is pattern or is_subtractive_type(f.TypeId))]
            if off:
                raise KernelError(
                    "« {} » est désactivé : réactivez-le pour qu'il creuse "
                    "d'autres corps".format(off[0].Label))
            raise KernelError(
                "corps concernés : seuls les enlèvements de matière "
                "creusent les autres corps")
        if not self._scope_transforms(pattern):
            raise KernelError(
                "corps concernés : la répétition n'a pas d'autre "
                "occurrence")

    def _mark_scope_instances(self, pattern):
        """Une répétition neuve : voir ``_SCOPE_INSTANCES``."""
        if self._SCOPE_INSTANCES not in pattern.PropertiesList:
            pattern.addProperty("App::PropertyBool", self._SCOPE_INSTANCES,
                                "FreeSolid", "Corps concernés : les "
                                "occurrences seules, en étapes cachées")
        setattr(pattern, self._SCOPE_INSTANCES, True)

    def _scope_hidden(self, pattern):
        """Vrai quand les booléens de ``pattern`` sont des étapes cachées :
        un enlèvement seul, ou une répétition neuve."""
        return (self._is_cut_source(pattern)
                or bool(getattr(pattern, self._SCOPE_INSTANCES, False)))

    @staticmethod
    def _is_cut_source(obj):
        """Un enlèvement seul, et non une répétition."""
        return (is_subtractive_type(getattr(obj, "TypeId", ""))
                and "Originals" not in getattr(obj, "PropertiesList", ()))

    def _cuts_bodies(self, obj):
        """Un enlèvement seul ou une répétition : la réédition passe ses
        « Corps creusés » à ``_set_cut_bodies``."""
        return (self._is_cut_source(obj)
                or getattr(obj, "TypeId", "") in _PATTERN_TYPES)

    def _is_scope_pattern(self, obj):
        """Une répétition d'enlèvements dont la réédition coche les corps
        creusés. Pas celle d'un fichier d'avant qui en creuse déjà : ses
        booléens sont des lignes de l'arbre, à supprimer une à une."""
        if getattr(obj, "TypeId", "") not in _PATTERN_TYPES:
            return False
        if not any(is_subtractive_type(f.TypeId)
                   for f in self._scope_originals(obj)):
            return False
        return (bool(getattr(obj, self._SCOPE_INSTANCES, False))
                or not self._scope_cuts(obj))

    def _hidden_cut_source(self, obj):
        """Le nom de l'enlèvement ou de la répétition dont ``obj`` est
        l'étape cachée dans un autre corps, ou ""."""
        source = getattr(obj, "FreeSolidScopeOf", "")
        return source if source and self._is_thin_helper(obj) else ""

    def _scope_originals(self, pattern):
        """Les fonctions que ``pattern`` répète, ou lui-même : un enlèvement
        seul."""
        if self._is_cut_source(pattern):
            return [pattern]
        return list(getattr(pattern, "Originals", None) or ())

    def _scope_seeds(self, pattern, extend=False):
        """Formes d'enlèvement des fonctions répétées — ou de l'enlèvement
        seul —, dans le repère de leur corps. ``extend`` : celles « à
        travers tout » prolongées au-delà de tous les corps."""
        reach = self._through_reach() if extend else 0.0
        seeds = []
        for feature in self._scope_originals(pattern):
            if (not is_subtractive_type(feature.TypeId)
                    or getattr(feature, "Suppressed", False)):
                continue
            shape = feature.AddSubShape.copy()
            if shape.isNull():
                continue
            shape.Placement = feature.Placement.multiply(shape.Placement)
            if reach:
                shape = self._through_extended(feature, shape, reach)
            seeds.append(shape)
        return seeds

    def _through_reach(self):
        """De quoi traverser toute la pièce : la diagonale de l'encombrement
        de tous les corps, arrondie à la puissance de deux au-dessus (l'outil
        ne se refait pas à chaque retouche d'un corps)."""
        import FreeCAD as App
        box = App.BoundBox()
        for body in self._history_bodies():
            try:
                shape = body.Shape
                if not shape.isNull() and shape.Solids:
                    box.add(shape.BoundBox)
            except Exception:  # noqa: BLE001 — forme OCCT inaccessible
                continue
        if not box.isValid():
            return 0.0
        return 2.0 ** math.ceil(math.log2(box.DiagonalLength + 1.0))

    @staticmethod
    def _through_ends(feature):
        """Bouts « à travers tout » de ``feature`` : ``"far"`` (le plus loin
        de l'esquisse), ``"both"`` ou None."""
        if feature.TypeId == "PartDesign::Hole":
            through = getattr(feature, "DepthType", "") == "ThroughAll"
            return "far" if through else None
        if feature.TypeId != "PartDesign::Pocket":
            return None
        first = getattr(feature, "Type", "") == "ThroughAll"
        side = getattr(feature, "SideType", "One side")
        if side == "Two sides":
            second = getattr(feature, "Type2", "") == "ThroughAll"
            return "both" if first and second else None
        if not first:
            return None
        return "both" if (side == "Symmetric"
                          or getattr(feature, "Midplane", False)) else "far"

    def _through_extended(self, feature, seed, reach):
        """``seed`` prolongé au-delà de ses bouts « à travers tout » : FreeCAD
        ne traverse que l'encombrement du corps de l'enlèvement, les
        modeleurs courants tous les corps qu'il creuse. La section prise un
        peu en deçà du bout (au-dessus de la pointe d'un perçage) est
        extrudée de ``reach`` plus la taille de l'outil."""
        import Part
        ends = self._through_ends(feature)
        if ends is None:
            return seed
        try:
            plane = feature.Profile[0].Shape.findPlane()
            normal, origin = plane.Axis, plane.Position
            heights = [(v.Point - origin).dot(normal) for v in seed.Vertexes]
            low, high = min(heights), max(heights)
            if ends == "far":
                signs = [1.0 if abs(high) >= abs(low) else -1.0]
            else:
                signs = [1.0, -1.0]
            inset = (float(feature.Diameter) if feature.TypeId
                     == "PartDesign::Hole" else 0.01)
            length = reach + seed.BoundBox.DiagonalLength
            shape = seed
            for sign in signs:
                end = high if sign > 0 else low
                at = origin.dot(normal) + end - sign * inset
                wires = seed.slice(normal, at)
                if not wires:
                    continue
                face = Part.makeFace(wires, "Part::FaceMakerBullseye")
                shape = shape.fuse(face.extrude(normal * sign
                                                * (inset + length)))
            return shape.removeSplitter() if shape is not seed else seed
        except Exception:  # noqa: BLE001 — OCCT : l'outil tel quel
            return seed

    def _scope_transforms(self, pattern):
        """Placements des occurrences qui creusent, dans le repère du
        corps : ``("move", placement)`` ou ``("mirror", point,
        normale)``. La première, celle de la fonction répétée, n'y est
        que dans une répétition d'un fichier d'avant."""
        items = self._occurrences(pattern)
        if getattr(pattern, self._SCOPE_INSTANCES, False):
            return items[1:]
        return items

    def _occurrences(self, pattern):
        """Placements de toutes les occurrences, la première comprise."""
        import FreeCAD as App
        if self._is_cut_source(pattern):
            return [("move", App.Placement())]
        kind = pattern.TypeId
        if kind == "PartDesign::Mirrored":
            obj, subs = pattern.MirrorPlane
            base, normal = self._link_plane(obj, subs[0] if subs else "")
            return [("move", App.Placement()), ("mirror", base, normal)]
        if kind == "PartDesign::PolarPattern":
            obj, subs = pattern.Axis
            base, direction = self._link_line(obj, subs[0] if subs else "")
            if pattern.Reversed:
                direction = direction * -1
            angles = polar_angles(
                pattern.Mode, pattern.Occurrences, pattern.Angle.Value,
                pattern.Offset.Value, list(pattern.Spacings),
                list(getattr(pattern, "SpacingPattern", ()) or ()))
            return [("move", App.Placement(App.Vector(),
                                           App.Rotation(direction, a), base))
                    for a in angles]
        obj, subs = pattern.Direction
        _, first = self._link_line(obj, subs[0] if subs else "")
        if pattern.Reversed:
            first = first * -1
        steps = linear_steps(
            pattern.Mode, pattern.Occurrences, pattern.Length.Value,
            pattern.Offset.Value, list(pattern.Spacings),
            list(pattern.SpacingPattern))
        second, steps2 = App.Vector(), [0.0]
        if int(pattern.Occurrences2) > 1 and pattern.Direction2:
            obj2, subs2 = pattern.Direction2
            _, second = self._link_line(obj2, subs2[0] if subs2 else "")
            if pattern.Reversed2:
                second = second * -1
            steps2 = linear_steps(
                pattern.Mode2, pattern.Occurrences2, pattern.Length2.Value,
                pattern.Offset2.Value, list(pattern.Spacings2),
                list(pattern.SpacingPattern2))
        return [("move", App.Placement(first * a + second * b,
                                       App.Rotation()))
                for a in steps for b in steps2]

    def _scope_signature(self, pattern, target):
        """Empreinte de ce dont dépend l'outil : il n'est refait que si
        elle change."""
        source = pattern.getParentGeoFeatureGroup()
        data = []
        for seed in self._scope_seeds(pattern):
            box = seed.BoundBox
            data.append([round(v, 6) for v in (
                seed.Volume, seed.Area, box.XMin, box.YMin, box.ZMin,
                box.XMax, box.YMax, box.ZMax)])
        for item in self._scope_transforms(pattern):
            if item[0] == "move":
                data.append([round(v, 9) for v in item[1].Matrix.A])
            else:
                data.append([round(v, 9) for v in (*item[1], *item[2])])
        for body in (source, target):
            data.append([round(v, 9)
                         for v in body.getGlobalPlacement().Matrix.A])
        data.append(self._through_reach())
        return json.dumps(data)

    def _scope_shapes(self, pattern, outer):
        """Chaque forme d'enlèvement à chaque occurrence qui creuse, du
        repère du corps de ``pattern`` à celui que donne ``outer``."""
        shapes = []
        for seed in self._scope_seeds(pattern, extend=True):
            for item in self._scope_transforms(pattern):
                if item[0] == "move":
                    shape = seed.copy()
                    shape.Placement = item[1].multiply(shape.Placement)
                else:
                    shape = seed.mirror(item[1], item[2])
                shape.Placement = outer.multiply(shape.Placement)
                shapes.append(shape)
        return shapes

    def _scope_tool(self, pattern, target):
        """L'outil figé, dans le repère de ``target``."""
        import Part
        source = pattern.getParentGeoFeatureGroup()
        shapes = self._scope_shapes(
            pattern, target.getGlobalPlacement().inverse().multiply(
                source.getGlobalPlacement()))
        tool = (shapes[0].multiFuse(shapes[1:]) if len(shapes) > 1
                else shapes[0])
        if not tool.Placement.isIdentity():
            # La base d'un corps ignore la position de sa forme.
            tool = Part.makeCompound([tool])
        return tool

    def _make_scope_cut(self, pattern, target):
        """Dans ``target`` : Soustraire l'outil figé de ``pattern``."""
        doc = self._require_doc()
        shape = doc.addObject("Part::Feature", "ScopeShape")
        shape.Shape = self._scope_tool(pattern, target)
        self._stamp_text(shape, "FreeSolidScopeSig",
                         self._scope_signature(pattern, target))
        self._mark_body_pattern_tool(shape)
        shape.Visibility = False
        # L'outil va droit dans le booléen : un corps intermédiaire, rangé
        # dans le booléen, lierait hors de sa portée (avertissement FreeCAD
        # à chaque reconstruction).
        cut = target.newObject("PartDesign::Boolean", "Boolean")
        cut.Type = "Cut"
        try:
            cut.addObjects([shape])
        except AttributeError:
            cut.Group = [shape]
        source = pattern.getParentGeoFeatureGroup()
        cut.Label = self._t("{} — depuis {}".format(pattern.Label,
                                                    source.Label))
        self._stamp_text(cut, "FreeSolidScopeOf", pattern.Name)
        self._stamp_text(cut, "FreeSolidScopeParts", shape.Name)
        if self._scope_hidden(pattern):
            # Hors de l'arbre : sa source la représente, et le survol
            # d'une face qu'elle a creusée la désigne.
            cut.addProperty("App::PropertyBool", self._THIN_HELPER,
                            "FreeSolid", "Étape cachée d'un enlèvement")
            setattr(cut, self._THIN_HELPER, True)
            self._stamp_text(cut, "FreeSolidThinOwner", pattern.Name)
        return cut

    def _scope_cuts(self, pattern):
        return [o for o in self._require_doc().Objects
                if getattr(o, "FreeSolidScopeOf", "") == pattern.Name]

    def _remove_scope_cut(self, cut):
        """Retire un booléen de corps concerné et son outil ; la pointe de
        son corps recule d'abord s'il l'était, la fonction suivante se
        rebranche sur la précédente."""
        doc = self._require_doc()
        parts = self._scope_parts_of(cut)
        body = cut.getParentGeoFeatureGroup()
        base = getattr(cut, "BaseFeature", None)
        if body is not None and getattr(body, "Tip", None) is cut:
            body.Tip = base
        self._relink_chain(body, [cut], base)
        doc.removeObject(cut.Name)
        self._remove_named_parts(parts)

    def _drop_scope(self, pattern):
        for cut in self._scope_cuts(pattern):
            self._remove_scope_cut(cut)
        if "FreeSolidScope" in pattern.PropertiesList:
            pattern.FreeSolidScope = ""

    @staticmethod
    def _scope_parts_of(obj):
        """Objets internes qu'un booléen de corps concerné emporte."""
        return [n for n in str(getattr(obj, "FreeSolidScopeParts", "")
                               ).split(";") if n]

    def _refresh_scopes(self):
        """Refait l'outil des corps concernés dont l'empreinte a changé."""
        changed = False
        doc = self._require_doc()
        for pattern in doc.Objects:
            if not scope_names(getattr(pattern, "FreeSolidScope", "")):
                continue
            off = self._scope_off(pattern)
            for cut in self._scope_cuts(pattern):
                if bool(getattr(cut, "Suppressed", False)) != off:
                    cut.Suppressed = off
                    changed = True
                if off:
                    continue
                target = cut.getParentGeoFeatureGroup()
                parts = self._scope_parts_of(cut)
                shape = doc.getObject(parts[-1]) if parts else None
                if target is None or shape is None:
                    continue
                try:
                    signature = self._scope_signature(pattern, target)
                    if getattr(shape, "FreeSolidScopeSig", "") == signature:
                        continue
                    shape.Shape = self._scope_tool(pattern, target)
                except Exception:  # noqa: BLE001 — l'outil d'avant reste
                    continue
                shape.FreeSolidScopeSig = signature
                changed = True
        return changed

    def _scope_off(self, pattern):
        """Vrai quand les booléens de ``pattern`` ne creusent rien :
        désactivé, ou une répétition ramenée à la fonction répétée."""
        if getattr(pattern, "Suppressed", False):
            return True
        try:
            return not self._scope_transforms(pattern)
        except Exception:  # noqa: BLE001 — lien cassé : l'outil d'avant reste
            return False

    def _scope_before_delete(self, obj):
        """Avant une suppression ordinaire : les corps concernés de ce qui
        part. Rend les objets internes à retirer après."""
        doc = self._require_doc()
        doomed = [obj] + (list(obj.Group)
                          if obj.TypeId == "PartDesign::Body" else [])
        later = []
        for item in doomed:
            if scope_names(getattr(item, "FreeSolidScope", "")):
                self._drop_scope(item)
            pattern = doc.getObject(getattr(item, "FreeSolidScopeOf", "")
                                    or "")
            if pattern is not None:
                body = item.getParentGeoFeatureGroup()
                names = [n for n in scope_names(
                    getattr(pattern, "FreeSolidScope", ""))
                    if body is None or n != body.Name]
                pattern.FreeSolidScope = format_scope(names)
            later += self._scope_parts_of(item)
        return later

    # ---------- creuser d'autres corps, à la création ----------

    def _cut_others(self, body, feature, bodies):
        """L'enlèvement ``feature`` — ou la répétition d'enlèvements —
        creuse aussi d'autres corps : ``bodies``, ou sans liste ceux qu'il
        traverse, comme les modeleurs courants (``_attach_scope``). Appelé
        sa forme calculée ; recalcule s'il en creuse un."""
        if bodies is None:
            others = self._crossed_bodies(body, feature,
                                          self._other_bodies(body))
        else:
            others = self._listed_bodies(bodies, body)
        if not others:
            return
        self._attach_scope(feature, others)
        self._recompute()

    def _crossed_bodies(self, body, feature, candidates):
        """Parmi ``candidates``, les corps où les occurrences de ``feature``
        ôtent de la matière."""
        try:
            removed = self._scope_shapes(feature, body.Placement)
            boxes = [shape.BoundBox for shape in removed]
        except Exception:  # noqa: BLE001 — OCCT : rien de sûr, rien de creusé
            return []
        crossed = []
        for other in candidates:
            try:
                shape = other.Shape
                if shape.isNull() or not shape.Solids:
                    continue
                if any(box.intersect(shape.BoundBox)
                       and tool.common(shape).Volume > 1e-6
                       for tool, box in zip(removed, boxes)):
                    crossed.append(other)
            except Exception:  # noqa: BLE001 — OCCT : pas de creux sûr
                continue
        return crossed

    def _undo_cut_others(self, feature):
        """Retire les étapes cachées d'un enlèvement refusé."""
        try:
            self._drop_scope(feature)
        except Exception:  # noqa: BLE001 — la transaction défait le reste
            pass

    # ---------- les corps creusés, à la réédition ----------

    def _cut_bodies_of(self, feature):
        """Les autres corps que l'enlèvement ``feature`` — ou la répétition
        d'enlèvements — creuse."""
        if not (self._is_cut_source(feature)
                or self._is_scope_pattern(feature)):
            return []
        return [target for target in (cut.getParentGeoFeatureGroup()
                                      for cut in self._scope_cuts(feature))
                if target is not None]

    def _set_cut_bodies(self, feature, names):
        """Réédition : les autres corps que l'enlèvement ``feature`` — ou la
        répétition — creuse. Un corps décoché perd son étape cachée ; un
        corps coché en reçoit une, à son rang dans le corps
        (``_insert_scope_cut``)."""
        from engine.kernel import KernelError
        body = feature.getParentGeoFeatureGroup()
        current = {cut.getParentGeoFeatureGroup(): cut
                   for cut in self._scope_cuts(feature)}
        wanted = self._listed_bodies(names, body, list(current))
        added = [target for target in wanted if target not in current]
        if (current and not self._scope_hidden(feature)
                and set(wanted) != set(current)):
            raise KernelError(
                "« {} » vient d'un fichier d'avant : ses corps creusés "
                "sont des lignes de l'arbre".format(feature.Label))
        if added:
            if not self._scope_hidden(feature):
                # Une répétition d'un fichier d'avant qui ne creusait rien :
                # elle devient une répétition neuve.
                self._mark_scope_instances(feature)
            self._refuse_unscoped(feature)
        for target, cut in current.items():
            if target not in wanted:
                self._remove_scope_cut(cut)
        for target in added:
            self._insert_scope_cut(feature, target)
        scope = format_scope(t.Name for t in wanted)
        if getattr(feature, "FreeSolidScope", "") != scope:
            self._stamp_text(feature, "FreeSolidScope", scope)

    def _insert_scope_cut(self, feature, target):
        """L'étape cachée de ``feature`` dans ``target``, juste après
        ``_scope_anchor`` : la pointe y passe le temps de l'insertion,
        puis revient — ou reste sur l'étape si elle était sur cette
        fonction et que ``feature`` est au-dessus de la barre (reculé, il
        fait naître l'étape reculée aussi)."""
        anchor = self._scope_anchor(feature, target)
        tip = target.Tip
        rolled = feature.Name in self._features_after_tips()
        target.Tip = anchor
        try:
            self._make_scope_cut(feature, target)
        finally:
            if tip is not anchor or rolled:
                target.Tip = tip

    def _scope_anchor(self, feature, target):
        """La dernière fonction de ``target`` plus ancienne que ``feature``
        (une étape cachée compte au rang de sa source), avec ses objets
        cachés."""
        from engine.kernel import KernelError
        order_of = self._tree_order()
        rank = order_of.get(feature.Name, -1)
        anchor = None
        for obj in target.Group:
            if (obj.isDerivedFrom("PartDesign::Feature") and order_of.get(
                    self._hidden_cut_source(obj) or obj.Name, -1) < rank):
                anchor = obj
        if anchor is None:
            raise KernelError(
                "« {} » n'existe pas encore au rang de « {} »".format(
                    self._body_title(target), feature.Label))
        return self._tip_with_helpers(anchor)

    def _place_scope_cuts(self):
        """Range chaque étape cachée au rang de sa source, dans son corps :
        juste après ``_scope_anchor``. Un enlèvement remonté au-dessus de
        fonctions d'un corps qu'il creuse le creuse avant elles ; descendu
        sous elles, après. Refusé si le corps n'existe pas encore au rang
        de l'enlèvement.

        Les étapes se rangent de la plus ancienne à la plus récente : celles
        d'avant sont à leur place quand vient la suivante. Un corps dont la
        pointe était en bout de chaîne l'y garde."""
        doc = self._require_doc()
        order_of = self._tree_order()
        steps = []
        for cut in doc.Objects:
            source = doc.getObject(self._hidden_cut_source(cut) or "")
            body = cut.getParentGeoFeatureGroup() if source else None
            if getattr(body, "TypeId", "") == "PartDesign::Body":
                steps.append((order_of.get(source.Name, -1), cut, source,
                              body))
        steps.sort(key=lambda step: step[0])
        for _rank, cut, source, body in steps:
            anchor = self._scope_anchor(source, body)
            group = list(body.Group)
            before = [o for o in group[:group.index(cut)]
                      if o.isDerivedFrom("PartDesign::Feature")]
            if before and before[-1] is anchor:
                continue
            tip = body.Tip
            at_end = tip is not None and tip is self._last_body_feature(body)
            body.removeObject(cut)
            body.insertObject(cut, anchor, True)
            body.Tip = self._last_body_feature(body) if at_end else tip

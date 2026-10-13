"""Gabarits de pièce : une pièce enregistrée comme point de départ
(matière, propriétés du fichier, équations, esquisses de base…), proposée
par « Nouveau ».

Rangés dans ``FREESOLID_DATA_DIR/Gabarits`` s'il est défini, sinon
``~/FreeSolid/Gabarits`` — sous la racine autorisée des fichiers de
l'utilisateur. Les imports FreeCAD restent dans les méthodes ;
``template_dir`` et ``clean_template_name`` sont testées en CI.
"""

import os
import re

_NAME = re.compile(r"^[\w][\w \-]{0,59}$", re.UNICODE)


def template_dir(environ=None, home=None):
    """Dossier des gabarits (pas forcément créé)."""
    environ = os.environ if environ is None else environ
    base = environ.get("FREESOLID_DATA_DIR") or os.path.join(
        home or os.path.expanduser("~"), "FreeSolid")
    return os.path.join(base, "Gabarits")


def clean_template_name(name):
    """Nom de gabarit accepté (lettres, chiffres, espaces, tirets), ou
    None."""
    text = str(name or "").strip()
    return text if _NAME.match(text) else None


class TemplatesMixin:
    """Ops : list_templates, save_template, new_from_template."""

    def list_templates(self):
        folder = template_dir()
        names = []
        if os.path.isdir(folder):
            names = sorted(f[:-len(".FCStd")] for f in os.listdir(folder)
                           if f.endswith(".FCStd"))
        return {"templates": names, "folder": folder}

    def _template_path(self, name):
        from engine.kernel import KernelError
        clean = clean_template_name(name)
        if clean is None:
            raise KernelError("nom de gabarit invalide — lettres, chiffres, "
                              "espaces et tirets")
        return os.path.join(template_dir(), clean + ".FCStd")

    def save_template(self, name):
        """Copie de la pièce en cours comme gabarit ``name`` (remplacé s'il
        existe). Le document en cours garde son propre fichier."""
        from engine.kernel import KernelError
        doc = self._require_doc()
        if self._assembly:
            raise KernelError("un gabarit se fait depuis une pièce")
        path = self._template_path(name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        path = self._user_path(path, (".FCStd",), must_exist=False)
        doc.saveCopy(path)
        return self.list_templates()

    def new_from_template(self, name):
        """Nouvelle pièce à partir d'un gabarit : son contenu, sans son
        fichier — « Enregistrer » demandera où ranger la pièce."""
        from engine.kernel import KernelError
        path = self._template_path(name)
        if not os.path.isfile(path):
            raise KernelError("gabarit introuvable : {}".format(name))
        tree = self.open_part(path)
        # Le document ne pointe plus sur le gabarit : un enregistrement
        # sans chemin ne doit jamais l'écraser.
        try:
            self._doc.FileName = ""
        except Exception:  # noqa: BLE001 — propriété en lecture seule
            pass
        return tree

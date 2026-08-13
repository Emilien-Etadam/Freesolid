# P004 — Écriture des propriétés : whitelist + allowlist d'expressions

Couvre les constats **3.5** (écriture de propriétés hors whitelist) et
**3.4** (`setExpression` sans allowlist) de
`docs/audit/2026-08-audit.md`. Périmètre : `engine/kernel.py`,
`engine/protocol.py`, `tests/test_security.py`. Aucune modification
client (l'UI n'envoie déjà que des propriétés issues de `get_params`).

## 1. Whitelist en écriture (3.5)

`set_param` et `set_params` acceptent aujourd'hui n'importe quelle
propriété sur simple `hasattr` — alors que `get_params` est limité à
`_EDITABLE_PROPS`. Symétriser :

- Dans les deux ops, refuser toute propriété absente de
  `_EDITABLE_PROPS` avec
  `KernelError("propriété non éditable : {prop}")`.
- Ne pas élargir `_EDITABLE_PROPS` — la liste actuelle couvre tout ce
  que le panneau d'édition envoie (il construit ses champs depuis
  `get_params`).

## 2. Allowlist d'expressions (3.4)

Toute chaîne non numérique passée à `set_params` / `sketch_set_dim` /
`set_variable` part telle quelle dans `setExpression` — le moteur
d'expressions FreeCAD sait référencer d'autres objets et documents
(syntaxe `<<Label>>`, etc.). Fermer cette surface :

Nouvelle fonction **pure** dans `engine/protocol.py` :

```python
def validate_expression(text):
    """Expression paramétrique client — retourne le texte épuré,
    ou lève ProtocolError."""
```

Règles :

- `strip()` ; vide ou > 256 caractères → refus.
- Caractères autorisés uniquement :
  lettres (accents français inclus), chiffres, `_`, espace, `.`,
  `,`, `+`, `-`, `*`, `/`, `%`, `^`, `(`, `)`.
  Tout le reste (`<`, `>`, `"`, `'`, `;`, `[`, `]`, `{`, `}`, `=`,
  `\`, `#`, `@`, `$`, `!`, `?`, `:`…) → refus.
- Message d'erreur en français qui cite le caractère fautif, ex.
  `expression refusée — caractère non autorisé : «<»`.

Ça laisse passer tout l'usage réel — `2*Largeur + 5`,
`Variables.epaisseur / 2`, `sin(30 deg)`, `largeur % 3` — et ferme les
références par label `<<…>>`, les chaînes, l'indexation et tout
caractère de contrôle.

Brancher dans `engine/kernel.py` sur **tous** les sites qui font
`setExpression` avec du texte venant du client (au minimum :
`set_params`, `set_param` si concerné, `sketch_set_dim`,
`set_variable` si sa valeur peut être une expression — vérifier en
grepant `setExpression`). Convertir `ProtocolError` en `KernelError`
comme le fait déjà `_user_path`. Les `setExpression(prop, None)`
(effacement) ne passent évidemment pas par la validation.

## 3. Tests (dans `tests/test_security.py`)

- `validate_expression` accepte : `"2*Largeur + 5"`,
  `"Variables.epaisseur / 2"`, `"sin(30 deg)"`, `"(a + b) * 0,5"`.
- Refuse : `"<<Autre>>.Valeur"`, `"a; b"`, `"x = 3"`, `"\"txt\""`,
  `"a[0]"`, chaîne de 300 caractères, chaîne vide, `"  "`.
- Le refus cite le caractère fautif.

## Validation avant push

1. `python3 -m pytest tests/ -q` — 130 existants + nouveaux, tout vert.
2. Si FreeCAD dispo : `PYTHONIOENCODING=utf-8 freecadcmd
   scripts/run-selftest.py` — le selftest utilise déjà des expressions
   (équations, cotes pilotées par `Variables.*`) : il DOIT rester vert
   sans adaptation. S'il casse, c'est l'allowlist qui est trop stricte,
   pas le selftest.
3. Commit : `[P004] écriture propriétés — whitelist _EDITABLE_PROPS + allowlist expressions`.

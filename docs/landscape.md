# Veille — qui construit quoi autour d'une UI moderne pour FreeCAD

*Relevé du 2026-08-02, avant d'engager la piste « nouvelle UI sur moteur
headless ». Conclusion en bas.*

## Les projets existants, un par un

| Projet | Ce que c'est | Verdict pour nous |
|---|---|---|
| [magik6k/freecad-web](https://github.com/magik6k/freecad-web) | Port WebAssembly de **tout** FreeCAD, **interface Qt comprise**, via Qt-for-WASM + JSPI (Chromium 137+ seulement) | Pas un concurrent : c'est l'interface actuelle dans un onglet. Mais une **preuve majeure** que le moteur tournera un jour côté client |
| [Salusoft89/planegcs](https://github.com/Salusoft89/planegcs) | Le **solveur d'esquisse de FreeCAD compilé en WASM**, utilisable en JS | Pas un concurrent : un **atout**. Le solveur peut tourner dans le navigateur pour le drag à 60 fps, le serveur restant la vérité |
| [Ondsel-Server / Lens](https://github.com/FreeCAD/Ondsel-Server) | Plateforme web de partage/visualisation de FCStd | Visionneuse, pas un éditeur |
| [SindriCAD](https://github.com/MakerViking/sindricad) | CAO paramétrique web (Tauri + Three.js) sur **build123d**, pas FreeCAD | Valide la stack UI ; moteur documentaire réinventé, reconstruction totale à chaque édition |
| freecad-mcp (plusieurs), freecad-ai | Pilotage de FreeCAD par API/LLM | De la tuyauterie voisine, pas une UI interactive |
| render-fcstd, freecad-web-visualization | Visionneuses Three.js de fichiers exportés | Affichage seul |
| Fil devtalk [« FreeCAD web frontend »](https://devtalk.freecad.org/t/freecad-web-frontend/55903) (2021) | Discussion récurrente depuis 2017 | Aucun projet n'en est sorti |
| [waffle-iron](https://github.com/sequoia-hope/waffle-iron) (SequoiaHope) | **Noyau** CAD from scratch, Rust/WASM, MIT, ~6 mois de travail assisté par IA, par un expert Onshape/SolidWorks | Le pari inverse du nôtre : noyau réécrit, UI « needs a lot of work ». Complémentaire, pas concurrent |
| [Onshape](https://www.onshape.com) | La CAO navigateur des fondateurs de SolidWorks, noyau Parasolid, gratuite en non-commercial | Le seul vrai « SW moderne dans un navigateur » existant. Cloud obligatoire, documents publics en gratuit, fermé — c'est exactement l'espace que « local + open source » laisse ouvert |

## Conclusion

**La voie est libre.** Tout le monde a fait soit l'inverse (la vieille UI
portée telle quelle en WASM), soit à côté (nouveau moteur documentaire), soit
en dessous (visionneuses, API). Personne n'a fait : *interface neuve +
moteur documentaire FreeCAD headless conservé* — c'est-à-dire garder les
documents paramétriques, PartDesign, le solveur, le fix toponaming et STEP,
et ne réécrire que la présentation et l'interaction.

Deux atouts inattendus ressortent de la veille :

1. **planegcs-wasm** existe déjà — le composant le plus risqué de notre
   futur éditeur d'esquisse (résolution de contraintes pendant le drag) a
   déjà été porté par quelqu'un d'autre.
2. **Le port WASM de magik6k** prouve que la dépendance à un serveur Python
   local n'est pas une impasse : le jour venu, le même moteur pourra tourner
   dans l'onglet. (Contexte, via la discussion Hacker News : ce port était un
   benchmark d'agent IA réalisé en ~4 jours, assumé bugué par son auteur —
   une démo de faisabilité, pas un produit.)

Et un avertissement d'expert, relevé dans la même discussion, qui fonde le
choix d'architecture : les noyaux géométriques regorgent de cas dégénérés et
de comptabilité de tolérances absents des données d'entraînement des LLM —
« pas vibe-codable », dixit un développeur qui en est à sa troisième
réécriture. Raison exacte pour laquelle ce projet ne réécrit **jamais** le
noyau : il garde celui qui a vingt ans de cas pourris derrière lui, et ne
refait que ce qui se voit.

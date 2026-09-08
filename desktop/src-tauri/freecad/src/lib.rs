//! FreeCAD headless pour FreeSolid : le trouver, l'installer, le lancer.
//!
//! Ce crate ne dépend pas de Tauri : tout ce qui est décision (chemins
//! candidats, nom d'archive, lecture de version) est une fonction pure et
//! testée ; tout ce qui touche le réseau ou le disque est isolé dans
//! `install` et `engine`.
//!
//! Disposition sur disque, sous le dossier de données de l'application :
//!
//! ```text
//! <data>/config.json                 chemin choisi par l'utilisateur
//! <data>/freecad/<version>/...       FreeCAD installé par FreeSolid
//! ```

pub mod assets;
pub mod config;
pub mod engine;
pub mod install;
pub mod locate;
pub mod version;

pub use assets::{asset_for, Asset, AssetKind};
pub use config::Config;
pub use engine::{command_for, free_port, Engine};
pub use install::{install, InstallError, Progress};
pub use locate::{candidates, find_freecadcmd_under, locate, Located, Source};
pub use version::{parse_version, reference_version, version_of};

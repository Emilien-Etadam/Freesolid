//! `config.json` : le seul réglage persistant, le chemin de `freecadcmd`
//! choisi par l'utilisateur.

use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

#[derive(Debug, Default, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Config {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub freecadcmd: Option<PathBuf>,
}

impl Config {
    /// Fichier absent ou illisible = configuration vide, jamais une erreur :
    /// l'écran de démarrage retombe alors sur la détection automatique.
    pub fn load(path: &Path) -> Config {
        std::fs::read_to_string(path)
            .ok()
            .and_then(|text| serde_json::from_str(&text).ok())
            .unwrap_or_default()
    }

    pub fn save(&self, path: &Path) -> std::io::Result<()> {
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)?;
        }
        let text = serde_json::to_string_pretty(self).expect("Config est sérialisable");
        std::fs::write(path, text)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn roundtrip_and_missing_file() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("sub").join("config.json");
        assert_eq!(Config::load(&path), Config::default());
        let cfg = Config {
            freecadcmd: Some(PathBuf::from("/opt/fc/bin/freecadcmd")),
        };
        cfg.save(&path).unwrap();
        assert_eq!(Config::load(&path), cfg);
        std::fs::write(&path, "{ not json").unwrap();
        assert_eq!(Config::load(&path), Config::default());
    }
}

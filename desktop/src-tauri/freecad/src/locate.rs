//! Où est `freecadcmd` ? Dans l'ordre : variable d'environnement, choix de
//! l'utilisateur, installation gérée par FreeSolid, `PATH`, emplacements
//! habituels de l'OS.

use crate::config::Config;
use crate::version::version_of;
use serde::Serialize;
use std::path::{Path, PathBuf};

/// Variable d'environnement qui force un binaire (dev, tests).
pub const ENV_FREECADCMD: &str = "FREESOLID_FREECADCMD";

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Source {
    Env,
    Config,
    Managed,
    Path,
    Standard,
}

#[derive(Debug, Clone, Serialize)]
pub struct Located {
    pub path: PathBuf,
    pub version: Option<String>,
    pub source: Source,
}

/// Noms possibles du binaire, selon l'OS.
pub fn binary_names() -> &'static [&'static str] {
    if cfg!(windows) {
        &["freecadcmd.exe", "FreeCADCmd.exe"]
    } else {
        &["freecadcmd", "FreeCADCmd"]
    }
}

/// Dossier où FreeSolid installe la version `version`.
pub fn managed_dir(data_dir: &Path, version: &str) -> PathBuf {
    data_dir.join("freecad").join(version)
}

/// Emplacements habituels d'une installation FreeCAD faite par
/// l'utilisateur. Fonction pure : `home` et `program_files` sont injectés.
pub fn candidates(os: &str, home: Option<&Path>, program_files: &[PathBuf]) -> Vec<PathBuf> {
    let mut out = Vec::new();
    match os {
        "linux" => {
            if let Some(home) = home {
                // Le tutoriel du README extrait l'AppImage dans ~/squashfs-root.
                out.push(home.join("squashfs-root/usr/bin/freecadcmd"));
                out.push(home.join(".local/bin/freecadcmd"));
            }
            for p in [
                "/usr/bin/freecadcmd",
                "/usr/local/bin/freecadcmd",
                "/usr/lib/freecad/bin/FreeCADCmd",
                "/usr/lib64/freecad/bin/FreeCADCmd",
                "/opt/freecad/bin/freecadcmd",
                "/snap/freecad/current/usr/bin/freecadcmd",
                "/var/lib/flatpak/app/org.freecad.FreeCAD/current/active/files/bin/freecadcmd",
            ] {
                out.push(PathBuf::from(p));
            }
        }
        "macos" => {
            out.push(PathBuf::from(
                "/Applications/FreeCAD.app/Contents/MacOS/FreeCADCmd",
            ));
            if let Some(home) = home {
                out.push(home.join("Applications/FreeCAD.app/Contents/MacOS/FreeCADCmd"));
            }
        }
        "windows" => {
            for base in program_files {
                // Le dossier s'appelle « FreeCAD 1.0 », « FreeCAD 1.1 »… :
                // on liste ce qui existe plutôt que de deviner.
                if let Ok(entries) = std::fs::read_dir(base) {
                    let mut names: Vec<PathBuf> = entries
                        .flatten()
                        .map(|e| e.path())
                        .filter(|p| {
                            p.file_name()
                                .and_then(|n| n.to_str())
                                .map(|n| n.to_ascii_lowercase().starts_with("freecad"))
                                .unwrap_or(false)
                        })
                        .collect();
                    names.sort();
                    names.reverse(); // la plus récente d'abord
                    for dir in names {
                        out.push(dir.join("bin").join("freecadcmd.exe"));
                    }
                }
            }
        }
        _ => {}
    }
    out
}

/// Cherche un binaire `freecadcmd` sous `dir`, à toute profondeur
/// (`squashfs-root/usr/bin`, `FreeCAD.app/Contents/MacOS`, `bin/`…).
pub fn find_freecadcmd_under(dir: &Path) -> Option<PathBuf> {
    fn walk(dir: &Path, depth: usize) -> Option<PathBuf> {
        if depth > 8 {
            return None;
        }
        let mut subdirs = Vec::new();
        for entry in std::fs::read_dir(dir).ok()?.flatten() {
            let path = entry.path();
            let name = entry.file_name();
            let name = name.to_string_lossy();
            if path.is_dir() {
                subdirs.push(path);
            } else if binary_names().iter().any(|n| n.eq_ignore_ascii_case(&name)) {
                return Some(path);
            }
        }
        // `bin` et `MacOS` d'abord : c'est là qu'il est presque toujours.
        subdirs.sort_by_key(|p| {
            let n = p
                .file_name()
                .map(|n| n.to_string_lossy().to_string())
                .unwrap_or_default();
            if n == "bin" || n == "MacOS" {
                0
            } else {
                1
            }
        });
        subdirs.into_iter().find_map(|d| walk(&d, depth + 1))
    }
    walk(dir, 0)
}

fn on_path(name: &str) -> Option<PathBuf> {
    let path = std::env::var_os("PATH")?;
    std::env::split_paths(&path)
        .map(|d| d.join(name))
        .find(|p| p.is_file())
}

fn program_files_dirs() -> Vec<PathBuf> {
    [
        "ProgramFiles",
        "ProgramW6432",
        "ProgramFiles(x86)",
        "LOCALAPPDATA",
    ]
    .iter()
    .filter_map(|k| std::env::var_os(k))
    .map(PathBuf::from)
    .collect()
}

fn home_dir() -> Option<PathBuf> {
    std::env::var_os("HOME")
        .or_else(|| std::env::var_os("USERPROFILE"))
        .map(PathBuf::from)
}

/// Le premier `freecadcmd` qui existe **et** répond à `--version`.
///
/// `reference` est la version que FreeSolid attend : l'installation gérée
/// de cette version passe avant les autres sources automatiques.
pub fn locate(data_dir: &Path, config_path: &Path, reference: &str) -> Option<Located> {
    let mut tries: Vec<(PathBuf, Source)> = Vec::new();

    if let Some(p) = std::env::var_os(ENV_FREECADCMD) {
        tries.push((PathBuf::from(p), Source::Env));
    }
    if let Some(p) = Config::load(config_path).freecadcmd {
        tries.push((p, Source::Config));
    }
    if let Some(p) = find_freecadcmd_under(&managed_dir(data_dir, reference)) {
        tries.push((p, Source::Managed));
    }
    for name in binary_names() {
        if let Some(p) = on_path(name) {
            tries.push((p, Source::Path));
        }
    }
    let home = home_dir();
    for p in candidates(std::env::consts::OS, home.as_deref(), &program_files_dirs()) {
        tries.push((p, Source::Standard));
    }

    for (path, source) in tries {
        if !path.is_file() {
            continue;
        }
        if let Some(version) = version_of(&path) {
            return Some(Located {
                path,
                version: Some(version),
                source,
            });
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn linux_candidates_start_with_readme_layout() {
        let c = candidates("linux", Some(Path::new("/home/x")), &[]);
        assert_eq!(
            c[0],
            PathBuf::from("/home/x/squashfs-root/usr/bin/freecadcmd")
        );
        assert!(c.contains(&PathBuf::from("/usr/bin/freecadcmd")));
    }

    #[test]
    fn windows_candidates_list_existing_freecad_dirs_newest_first() {
        let pf = tempfile::tempdir().unwrap();
        std::fs::create_dir_all(pf.path().join("FreeCAD 1.0").join("bin")).unwrap();
        std::fs::create_dir_all(pf.path().join("FreeCAD 1.1").join("bin")).unwrap();
        std::fs::create_dir_all(pf.path().join("Autre")).unwrap();
        let c = candidates("windows", None, &[pf.path().to_path_buf()]);
        assert_eq!(c.len(), 2);
        assert!(
            c[0].ends_with("FreeCAD 1.1/bin/freecadcmd.exe")
                || c[0].ends_with("FreeCAD 1.1\\bin\\freecadcmd.exe")
        );
    }

    #[test]
    fn macos_and_unknown() {
        let c = candidates("macos", None, &[]);
        assert_eq!(
            c[0],
            PathBuf::from("/Applications/FreeCAD.app/Contents/MacOS/FreeCADCmd")
        );
        assert!(candidates("plan9", None, &[]).is_empty());
    }

    #[test]
    fn find_under_prefers_bin_and_ignores_dirs_named_like_binary() {
        let root = tempfile::tempdir().unwrap();
        let bin = root.path().join("squashfs-root").join("usr").join("bin");
        std::fs::create_dir_all(&bin).unwrap();
        std::fs::create_dir_all(root.path().join("lib").join("freecadcmd")).unwrap();
        let name = binary_names()[0];
        std::fs::write(bin.join(name), "").unwrap();
        assert_eq!(find_freecadcmd_under(root.path()).unwrap(), bin.join(name));
        assert!(find_freecadcmd_under(&root.path().join("nope")).is_none());
    }

    #[test]
    fn managed_dir_is_per_version() {
        assert_eq!(
            managed_dir(Path::new("/d"), "1.1.3"),
            PathBuf::from("/d/freecad/1.1.3")
        );
    }
}

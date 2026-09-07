//! Quelle archive FreeCAD télécharger pour cette machine.
//!
//! Les noms suivent les releases GitHub de FreeCAD (série 1.1.x) :
//! `FreeCAD_<v>-<OS>-<arch>-py311.<ext>`, chacune accompagnée d'un
//! `<nom>-SHA256.txt`. Vérifié sur 1.1.3 pour les cinq combinaisons.

use serde::Serialize;

const RELEASES: &str = "https://github.com/FreeCAD/FreeCAD/releases/download";

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum AssetKind {
    AppImage,
    SevenZip,
    Dmg,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Asset {
    pub version: String,
    pub file_name: String,
    pub url: String,
    pub sha256_url: String,
    pub kind: AssetKind,
}

/// `os` et `arch` au sens de `std::env::consts` (« linux », « x86_64 »…).
pub fn asset_for(version: &str, os: &str, arch: &str) -> Option<Asset> {
    let (os_label, arch_label, ext, kind) = match (os, arch) {
        ("linux", "x86_64") => ("Linux", "x86_64", "AppImage", AssetKind::AppImage),
        ("linux", "aarch64") => ("Linux", "aarch64", "AppImage", AssetKind::AppImage),
        ("windows", "x86_64") => ("Windows", "x86_64", "7z", AssetKind::SevenZip),
        ("macos", "aarch64") => ("macOS", "arm64", "dmg", AssetKind::Dmg),
        ("macos", "x86_64") => ("macOS", "x86_64", "dmg", AssetKind::Dmg),
        _ => return None,
    };
    let file_name = format!("FreeCAD_{version}-{os_label}-{arch_label}-py311.{ext}");
    let url = format!("{RELEASES}/{version}/{file_name}");
    Some(Asset {
        version: version.to_string(),
        sha256_url: format!("{url}-SHA256.txt"),
        url,
        file_name,
        kind,
    })
}

/// L'archive pour la machine qui exécute ce code.
pub fn asset_for_host(version: &str) -> Option<Asset> {
    asset_for(version, std::env::consts::OS, std::env::consts::ARCH)
}

/// Première empreinte hex de 64 caractères d'un `*-SHA256.txt`
/// (format `sha256sum` : « <hex> *nom » ou « <hex>  nom »).
pub fn parse_sha256(text: &str) -> Option<String> {
    text.split_whitespace()
        .map(|w| w.trim_start_matches('*'))
        .find(|w| w.len() == 64 && w.chars().all(|c| c.is_ascii_hexdigit()))
        .map(|w| w.to_ascii_lowercase())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn linux_x86_64_matches_readme_url() {
        let a = asset_for("1.1.3", "linux", "x86_64").unwrap();
        assert_eq!(
            a.url,
            "https://github.com/FreeCAD/FreeCAD/releases/download/1.1.3/FreeCAD_1.1.3-Linux-x86_64-py311.AppImage"
        );
        assert_eq!(a.sha256_url, format!("{}-SHA256.txt", a.url));
        assert_eq!(a.kind, AssetKind::AppImage);
    }

    #[test]
    fn other_platforms() {
        assert_eq!(
            asset_for("1.1.3", "windows", "x86_64").unwrap().file_name,
            "FreeCAD_1.1.3-Windows-x86_64-py311.7z"
        );
        assert_eq!(
            asset_for("1.1.3", "macos", "aarch64").unwrap().file_name,
            "FreeCAD_1.1.3-macOS-arm64-py311.dmg"
        );
        assert_eq!(
            asset_for("1.1.3", "macos", "x86_64").unwrap().file_name,
            "FreeCAD_1.1.3-macOS-x86_64-py311.dmg"
        );
        assert_eq!(
            asset_for("1.1.3", "linux", "aarch64").unwrap().file_name,
            "FreeCAD_1.1.3-Linux-aarch64-py311.AppImage"
        );
        assert!(asset_for("1.1.3", "windows", "aarch64").is_none());
        assert!(asset_for("1.1.3", "freebsd", "x86_64").is_none());
    }

    #[test]
    fn sha256_formats() {
        let star = "9c6959dc9c4dba64dd818a62447e3dfedb4221d776fb044b239d462f150bcec4 *FreeCAD.7z\n";
        let plain =
            "3A853EB69EE595F779F2255DBF80A765926981D8FF68903CEFEE4DFB03A8F5EF  FreeCAD.AppImage";
        assert_eq!(
            parse_sha256(star).unwrap(),
            "9c6959dc9c4dba64dd818a62447e3dfedb4221d776fb044b239d462f150bcec4"
        );
        assert_eq!(
            parse_sha256(plain).unwrap(),
            "3a853eb69ee595f779f2255dbf80a765926981d8ff68903cefee4dfb03a8f5ef"
        );
        assert!(parse_sha256("garbage").is_none());
    }
}

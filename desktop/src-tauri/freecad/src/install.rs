//! Installation automatique de FreeCAD, quand la machine n'en a pas :
//! téléchargement de l'archive officielle, vérification SHA-256, extraction
//! dans le dossier de données de FreeSolid. Aucun droit administrateur.

use crate::assets::{asset_for_host, parse_sha256, Asset, AssetKind};
use crate::locate::{find_freecadcmd_under, managed_dir};
use serde::Serialize;
use sha2::{Digest, Sha256};
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Seek, Write};
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::Duration;

#[derive(Debug, Clone, Serialize)]
#[serde(tag = "phase", rename_all = "lowercase")]
pub enum Progress {
    Downloading { done: u64, total: Option<u64> },
    Verifying,
    Extracting,
    Done { freecadcmd: PathBuf },
}

#[derive(Debug, thiserror::Error)]
pub enum InstallError {
    #[error("pas d'archive FreeCAD {0} connue pour {1}/{2}")]
    Unsupported(String, &'static str, &'static str),
    #[error("réseau : {0}")]
    Network(#[from] reqwest::Error),
    #[error("téléchargement de {0} : HTTP {1}")]
    Http(String, u16),
    #[error("fichier SHA-256 illisible : {0}")]
    BadChecksumFile(String),
    #[error("empreinte SHA-256 incorrecte pour {0} (attendu {1}, obtenu {2})")]
    ChecksumMismatch(String, String, String),
    #[error("disque : {0}")]
    Io(#[from] std::io::Error),
    #[error("extraction : {0}")]
    Extract(String),
    #[error("archive extraite mais aucun freecadcmd trouvé sous {0}")]
    NoBinary(PathBuf),
}

fn client() -> Result<reqwest::blocking::Client, reqwest::Error> {
    reqwest::blocking::Client::builder()
        .user_agent("FreeSolid-desktop")
        .connect_timeout(Duration::from_secs(30))
        .timeout(Duration::from_secs(600))
        .build()
}

/// Installe FreeCAD `version` sous `<data_dir>/freecad/<version>` et
/// renvoie le chemin de `freecadcmd`. `progress` est appelé à chaque étape.
pub fn install(
    data_dir: &Path,
    version: &str,
    progress: &mut dyn FnMut(Progress),
) -> Result<PathBuf, InstallError> {
    let asset = asset_for_host(version).ok_or_else(|| {
        InstallError::Unsupported(
            version.to_string(),
            std::env::consts::OS,
            std::env::consts::ARCH,
        )
    })?;
    let target = managed_dir(data_dir, version);
    if let Some(existing) = find_freecadcmd_under(&target) {
        progress(Progress::Done {
            freecadcmd: existing.clone(),
        });
        return Ok(existing);
    }
    let downloads = data_dir.join("freecad").join("downloads");
    fs::create_dir_all(&downloads)?;
    let archive = downloads.join(&asset.file_name);

    let http = client()?;
    let expected = fetch_sha256(&http, &asset)?;
    let actual = download(&http, &asset, &archive, progress)?;
    progress(Progress::Verifying);
    if actual != expected {
        let _ = fs::remove_file(&archive);
        return Err(InstallError::ChecksumMismatch(
            asset.file_name.clone(),
            expected,
            actual,
        ));
    }

    progress(Progress::Extracting);
    let staging = data_dir.join("freecad").join(format!("{version}.partiel"));
    let _ = fs::remove_dir_all(&staging);
    fs::create_dir_all(&staging)?;
    extract(&asset, &archive, &staging)?;
    let _ = fs::remove_file(&archive);
    let _ = fs::remove_dir_all(&target);
    if let Some(parent) = target.parent() {
        fs::create_dir_all(parent)?;
    }
    fs::rename(&staging, &target)?;

    let freecadcmd =
        find_freecadcmd_under(&target).ok_or_else(|| InstallError::NoBinary(target.clone()))?;
    progress(Progress::Done {
        freecadcmd: freecadcmd.clone(),
    });
    Ok(freecadcmd)
}

fn fetch_sha256(http: &reqwest::blocking::Client, asset: &Asset) -> Result<String, InstallError> {
    let resp = http.get(&asset.sha256_url).send()?;
    if !resp.status().is_success() {
        return Err(InstallError::Http(
            asset.sha256_url.clone(),
            resp.status().as_u16(),
        ));
    }
    let text = resp.text()?;
    parse_sha256(&text)
        .ok_or_else(|| InstallError::BadChecksumFile(text.chars().take(200).collect()))
}

/// Télécharge dans `<archive>.part` (reprise si un morceau existe), puis
/// renomme. Renvoie l'empreinte SHA-256 hex du fichier complet.
fn download(
    http: &reqwest::blocking::Client,
    asset: &Asset,
    archive: &Path,
    progress: &mut dyn FnMut(Progress),
) -> Result<String, InstallError> {
    let part = archive.with_extension(format!(
        "{}.part",
        archive
            .extension()
            .and_then(|e| e.to_str())
            .unwrap_or("bin")
    ));
    let mut hasher = Sha256::new();
    let mut done: u64;

    if archive.is_file() {
        // Un téléchargement complet d'une session précédente : on le
        // re-vérifie plutôt que de le retélécharger.
        let mut f = File::open(archive)?;
        done = hash_into(&mut f, &mut hasher, None)?;
        progress(Progress::Downloading {
            done,
            total: Some(done),
        });
        return Ok(hex::encode(hasher.finalize()));
    }

    let mut file = OpenOptions::new()
        .create(true)
        .append(true)
        .read(true)
        .open(&part)?;
    file.seek(std::io::SeekFrom::Start(0))?;
    done = hash_into(&mut file, &mut hasher, None)?;
    file.seek(std::io::SeekFrom::End(0))?;

    let mut req = http.get(&asset.url);
    if done > 0 {
        req = req.header("Range", format!("bytes={done}-"));
    }
    let mut resp = req.send()?;
    let status = resp.status();
    if done > 0 && status.as_u16() != 206 {
        // Le serveur ignore la reprise : on repart de zéro.
        drop(file);
        fs::remove_file(&part)?;
        file = OpenOptions::new()
            .create(true)
            .write(true)
            .read(true)
            .truncate(true)
            .open(&part)?;
        hasher = Sha256::new();
        done = 0;
        if !status.is_success() {
            return Err(InstallError::Http(asset.url.clone(), status.as_u16()));
        }
    } else if !status.is_success() {
        return Err(InstallError::Http(asset.url.clone(), status.as_u16()));
    }
    let total = resp.content_length().map(|n| n + done);
    progress(Progress::Downloading { done, total });

    let mut buf = vec![0u8; 1 << 16];
    let mut last_report = std::time::Instant::now();
    loop {
        let n = resp.read(&mut buf)?;
        if n == 0 {
            break;
        }
        file.write_all(&buf[..n])?;
        hasher.update(&buf[..n]);
        done += n as u64;
        if last_report.elapsed() > Duration::from_millis(200) {
            progress(Progress::Downloading { done, total });
            last_report = std::time::Instant::now();
        }
    }
    file.flush()?;
    drop(file);
    progress(Progress::Downloading {
        done,
        total: Some(done),
    });
    fs::rename(&part, archive)?;
    Ok(hex::encode(hasher.finalize()))
}

fn hash_into(
    reader: &mut impl Read,
    hasher: &mut Sha256,
    limit: Option<u64>,
) -> std::io::Result<u64> {
    let mut buf = vec![0u8; 1 << 16];
    let mut n_total = 0u64;
    loop {
        let n = reader.read(&mut buf)?;
        if n == 0 {
            break;
        }
        hasher.update(&buf[..n]);
        n_total += n as u64;
        if limit.is_some_and(|l| n_total >= l) {
            break;
        }
    }
    Ok(n_total)
}

fn run(cmd: &mut Command, what: &str) -> Result<(), InstallError> {
    crate::engine::quiet(cmd);
    let out = cmd
        .output()
        .map_err(|e| InstallError::Extract(format!("{what} : {e}")))?;
    if !out.status.success() {
        return Err(InstallError::Extract(format!(
            "{what} : code {:?}\n{}",
            out.status.code(),
            String::from_utf8_lossy(&out.stderr)
                .chars()
                .take(2000)
                .collect::<String>()
        )));
    }
    Ok(())
}

fn extract(asset: &Asset, archive: &Path, dest: &Path) -> Result<(), InstallError> {
    match asset.kind {
        AssetKind::AppImage => extract_appimage(archive, dest),
        AssetKind::SevenZip => extract_7z(archive, dest),
        AssetKind::Dmg => extract_dmg(archive, dest),
    }
}

/// `./FreeCAD.AppImage --appimage-extract` — sans FUSE, comme le README.
fn extract_appimage(archive: &Path, dest: &Path) -> Result<(), InstallError> {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(archive, fs::Permissions::from_mode(0o755))?;
    }
    let mut cmd = Command::new(archive);
    cmd.arg("--appimage-extract").current_dir(dest);
    run(&mut cmd, "AppImage --appimage-extract")
}

/// 7-Zip : décompresseur Rust d'abord, `tar.exe` de Windows (libarchive,
/// qui lit le 7z) en secours.
fn extract_7z(archive: &Path, dest: &Path) -> Result<(), InstallError> {
    #[cfg(windows)]
    {
        if sevenz_rust::decompress_file(archive, dest).is_ok() {
            return Ok(());
        }
        let _ = fs::remove_dir_all(dest);
        fs::create_dir_all(dest)?;
    }
    let mut cmd = Command::new("tar");
    cmd.arg("-xf").arg(archive).arg("-C").arg(dest);
    run(&mut cmd, "tar -xf (7z)")
}

/// DMG : montage, copie de `FreeCAD.app`, démontage.
fn extract_dmg(archive: &Path, dest: &Path) -> Result<(), InstallError> {
    let mount = dest.join(".montage");
    fs::create_dir_all(&mount)?;
    let mut attach = Command::new("hdiutil");
    attach
        .args([
            "attach",
            "-nobrowse",
            "-readonly",
            "-noverify",
            "-mountpoint",
        ])
        .arg(&mount)
        .arg(archive);
    run(&mut attach, "hdiutil attach")?;
    let result = (|| -> Result<(), InstallError> {
        let app = fs::read_dir(&mount)?
            .flatten()
            .map(|e| e.path())
            .find(|p| p.extension().is_some_and(|e| e == "app"))
            .ok_or_else(|| InstallError::Extract("aucun .app dans l'image disque".into()))?;
        let mut cp = Command::new("cp");
        cp.arg("-R").arg(&app).arg(dest);
        run(&mut cp, "cp -R FreeCAD.app")
    })();
    let mut detach = Command::new("hdiutil");
    detach.args(["detach", "-force"]).arg(&mount);
    let _ = run(&mut detach, "hdiutil detach");
    let _ = fs::remove_dir(&mount);
    result
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn hash_matches_sha256sum() {
        let mut h = Sha256::new();
        let n = hash_into(&mut &b"abc"[..], &mut h, None).unwrap();
        assert_eq!(n, 3);
        assert_eq!(
            hex::encode(h.finalize()),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        );
    }

    #[test]
    fn unsupported_platform_is_reported_not_panicked() {
        // asset_for_host dépend de la machine ; on ne teste ici que la
        // branche « déjà installé », qui ne touche pas au réseau.
        let dir = tempfile::tempdir().unwrap();
        let bin = managed_dir(dir.path(), "9.9.9").join("bin");
        fs::create_dir_all(&bin).unwrap();
        let name = crate::locate::binary_names()[0];
        fs::write(bin.join(name), "").unwrap();
        let mut seen = Vec::new();
        let got = install(dir.path(), "9.9.9", &mut |p| seen.push(format!("{p:?}"))).unwrap();
        assert_eq!(got, bin.join(name));
        assert_eq!(seen.len(), 1);
        assert!(seen[0].starts_with("Done"));
    }
}

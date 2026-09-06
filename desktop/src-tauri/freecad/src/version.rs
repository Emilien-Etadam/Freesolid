//! Versions : celle que FreeCAD annonce, celle que FreeSolid attend.

use std::path::Path;
use std::process::Command;
use std::time::Duration;

/// Extrait « 1.1.3 » de la sortie de `freecadcmd --version`
/// (« FreeCAD 1.1.3 Revision: 12345 (Git) », bannières comprises).
pub fn parse_version(output: &str) -> Option<String> {
    for line in output.lines() {
        let line = line.trim();
        let Some(rest) = line.strip_prefix("FreeCAD ") else {
            continue;
        };
        let rest = rest.trim_start();
        let digits: String = rest
            .chars()
            .take_while(|c| c.is_ascii_digit() || *c == '.')
            .collect();
        let parts: Vec<&str> = digits
            .trim_matches('.')
            .split('.')
            .filter(|p| !p.is_empty())
            .collect();
        if parts.len() >= 2 {
            return Some(parts.iter().take(3).cloned().collect::<Vec<_>>().join("."));
        }
    }
    None
}

/// Version de référence lue dans `engine/platform.py` (`FREECAD = "1.1.3"`),
/// seule source de vérité du dépôt.
pub fn reference_version(platform_py: &str) -> Option<String> {
    for line in platform_py.lines() {
        let line = line.trim();
        if let Some(rest) = line.strip_prefix("FREECAD") {
            let rest = rest.trim_start();
            let rest = rest.strip_prefix('=')?.trim_start();
            let quoted = rest.strip_prefix('"').or_else(|| rest.strip_prefix('\''))?;
            let end = quoted.find(['"', '\''])?;
            let value = &quoted[..end];
            if !value.is_empty() {
                return Some(value.to_string());
            }
        }
    }
    None
}

/// Lance `freecadcmd --version` et renvoie la version, ou `None` si le
/// binaire ne répond pas (absent, cassé, ou pas FreeCAD du tout).
pub fn version_of(freecadcmd: &Path) -> Option<String> {
    let mut cmd = Command::new(freecadcmd);
    cmd.arg("--version");
    crate::engine::quiet(&mut cmd);
    let output = run_with_timeout(cmd, Duration::from_secs(60))?;
    let text = format!(
        "{}\n{}",
        String::from_utf8_lossy(&output.0),
        String::from_utf8_lossy(&output.1)
    );
    parse_version(&text)
}

/// `(stdout, stderr)` ou `None` si le processus dépasse `timeout`.
fn run_with_timeout(mut cmd: Command, timeout: Duration) -> Option<(Vec<u8>, Vec<u8>)> {
    use std::io::Read;
    use std::process::Stdio;

    cmd.stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .stdin(Stdio::null());
    let mut child = cmd.spawn().ok()?;
    let mut stdout = child.stdout.take()?;
    let mut stderr = child.stderr.take()?;
    let reader = std::thread::spawn(move || {
        let mut out = Vec::new();
        let mut err = Vec::new();
        let _ = stdout.read_to_end(&mut out);
        let _ = stderr.read_to_end(&mut err);
        (out, err)
    });
    let started = std::time::Instant::now();
    loop {
        match child.try_wait() {
            Ok(Some(_)) => break,
            Ok(None) => {
                if started.elapsed() > timeout {
                    let _ = child.kill();
                    let _ = child.wait();
                    return None;
                }
                std::thread::sleep(Duration::from_millis(50));
            }
            Err(_) => return None,
        }
    }
    reader.join().ok()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_plain() {
        assert_eq!(
            parse_version("FreeCAD 1.1.3 Revision: 42 (Git)"),
            Some("1.1.3".into())
        );
    }

    #[test]
    fn parse_with_banner_and_two_parts() {
        let out = "FreeCAD 1.0, Libs: 1.0.0RT\nSome banner\n";
        assert_eq!(parse_version(out), Some("1.0".into()));
    }

    #[test]
    fn parse_skips_noise_lines() {
        let out = "Qt: ignoring\nFreeCAD 1.1.3\n";
        assert_eq!(parse_version(out), Some("1.1.3".into()));
        assert_eq!(parse_version("nothing here"), None);
    }

    #[test]
    fn reference_from_platform_py() {
        let py = "import os\n\n#: Version\nFREECAD = \"1.1.3\"\n\nOVERRIDE_ENV = \"X\"\n";
        assert_eq!(reference_version(py), Some("1.1.3".into()));
        assert_eq!(reference_version("FREECAD = ''"), None);
        assert_eq!(reference_version("nope"), None);
    }
}

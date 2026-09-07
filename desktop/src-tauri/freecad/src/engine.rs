//! Le moteur : `freecadcmd engine/server.py`, lancé en processus enfant,
//! prêt quand il répond en HTTP sur son port.

use std::fs::File;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::time::{Duration, Instant};

/// Port du serveur, celui de `engine/server.py` (`PORT`).
pub const PORT: u16 = 8787;

pub fn url() -> String {
    format!("http://127.0.0.1:{PORT}/")
}

#[derive(Debug, thiserror::Error)]
pub enum EngineError {
    #[error("impossible de lancer {0} : {1}")]
    Spawn(PathBuf, std::io::Error),
    #[error("le moteur s'est arrêté (code {code:?}) — fin du journal :\n{log_tail}")]
    Exited { code: Option<i32>, log_tail: String },
    #[error("le moteur ne répond pas après {0} s — fin du journal :\n{1}")]
    Timeout(u64, String),
}

/// Sur Windows, pas de fenêtre console pour le processus enfant.
pub fn quiet(cmd: &mut Command) {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }
    #[cfg(not(windows))]
    {
        let _ = cmd;
    }
}

/// La commande exacte, avec l'environnement que `server.py` attend :
/// `FREESOLID_NO_SERVE` retiré (sinon le serveur quitte sans écouter, voir
/// AGENTS.md), sortie en UTF-8 sur toutes les plateformes.
pub fn command_for(freecadcmd: &Path, server_py: &Path) -> Command {
    let mut cmd = Command::new(freecadcmd);
    cmd.arg(server_py);
    if let Some(dir) = server_py.parent() {
        cmd.current_dir(dir);
    }
    cmd.env_remove("FREESOLID_NO_SERVE");
    cmd.env("PYTHONIOENCODING", "utf-8");
    cmd.env("PYTHONUNBUFFERED", "1");
    cmd.stdin(Stdio::null());
    quiet(&mut cmd);
    cmd
}

/// `true` si quelque chose répond déjà en HTTP sur le port du moteur.
pub fn ping() -> bool {
    let client = match reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(2))
        .no_proxy()
        .build()
    {
        Ok(c) => c,
        Err(_) => return false,
    };
    client
        .get(url())
        .send()
        .map(|r| r.status().is_success())
        .unwrap_or(false)
}

pub struct Engine {
    /// `None` quand un moteur tournait déjà avant nous (on l'adopte sans
    /// le posséder : on ne l'arrêtera pas).
    child: Option<Child>,
    log_path: PathBuf,
}

impl Engine {
    /// Lance le moteur et attend qu'il réponde. Journal (stdout+stderr du
    /// processus) dans `log_path`.
    pub fn start(
        freecadcmd: &Path,
        server_py: &Path,
        log_path: &Path,
        timeout: Duration,
    ) -> Result<Engine, EngineError> {
        if ping() {
            return Ok(Engine {
                child: None,
                log_path: log_path.to_path_buf(),
            });
        }
        if let Some(parent) = log_path.parent() {
            let _ = std::fs::create_dir_all(parent);
        }
        let mut cmd = command_for(freecadcmd, server_py);
        match File::create(log_path) {
            Ok(out) => {
                let err = out
                    .try_clone()
                    .map(Stdio::from)
                    .unwrap_or_else(|_| Stdio::null());
                cmd.stdout(Stdio::from(out)).stderr(err);
            }
            Err(_) => {
                cmd.stdout(Stdio::null()).stderr(Stdio::null());
            }
        }
        let mut child = cmd
            .spawn()
            .map_err(|e| EngineError::Spawn(freecadcmd.to_path_buf(), e))?;
        let started = Instant::now();
        loop {
            if let Ok(Some(status)) = child.try_wait() {
                return Err(EngineError::Exited {
                    code: status.code(),
                    log_tail: log_tail(log_path),
                });
            }
            if ping() {
                return Ok(Engine {
                    child: Some(child),
                    log_path: log_path.to_path_buf(),
                });
            }
            if started.elapsed() > timeout {
                let _ = child.kill();
                let _ = child.wait();
                return Err(EngineError::Timeout(timeout.as_secs(), log_tail(log_path)));
            }
            std::thread::sleep(Duration::from_millis(400));
        }
    }

    pub fn owned(&self) -> bool {
        self.child.is_some()
    }

    pub fn log_path(&self) -> &Path {
        &self.log_path
    }

    pub fn stop(&mut self) {
        if let Some(mut child) = self.child.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

impl Drop for Engine {
    fn drop(&mut self) {
        self.stop();
    }
}

/// Les ~40 dernières lignes du journal, pour un message d'erreur utile.
pub fn log_tail(path: &Path) -> String {
    let text = std::fs::read_to_string(path).unwrap_or_default();
    let lines: Vec<&str> = text.lines().collect();
    let start = lines.len().saturating_sub(40);
    lines[start..].join("\n")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn command_sets_cwd_and_env() {
        let cmd = command_for(Path::new("/x/freecadcmd"), Path::new("/r/engine/server.py"));
        assert_eq!(cmd.get_program(), Path::new("/x/freecadcmd").as_os_str());
        let args: Vec<_> = cmd.get_args().collect();
        assert_eq!(args, vec![Path::new("/r/engine/server.py").as_os_str()]);
        assert_eq!(cmd.get_current_dir(), Some(Path::new("/r/engine")));
        let envs: Vec<_> = cmd.get_envs().collect();
        assert!(envs
            .iter()
            .any(|(k, v)| *k == "PYTHONIOENCODING" && v.is_some()));
        assert!(envs
            .iter()
            .any(|(k, v)| *k == "FREESOLID_NO_SERVE" && v.is_none()));
    }

    #[test]
    fn log_tail_keeps_last_lines() {
        let dir = tempfile::tempdir().unwrap();
        let p = dir.path().join("engine.log");
        let text: Vec<String> = (0..100).map(|i| format!("l{i}")).collect();
        std::fs::write(&p, text.join("\n")).unwrap();
        let tail = log_tail(&p);
        assert!(tail.starts_with("l60\n"));
        assert!(tail.ends_with("l99"));
        assert_eq!(log_tail(&dir.path().join("absent")), "");
    }
}

//! FreeSolid de bureau : une fenêtre, un moteur FreeCAD local.
//!
//! Au démarrage la fenêtre affiche l'écran de lancement embarqué (`ui/`),
//! qui appelle les commandes ci-dessous : trouver FreeCAD, l'installer si
//! besoin, lancer le moteur. Quand le moteur répond, la fenêtre navigue
//! vers `http://127.0.0.1:8787/` — l'interface est alors exactement celle
//! du navigateur, servie par le moteur. Le moteur est arrêté avec l'app.

use freesolid_freecad as freecad;
use serde::Serialize;
use std::path::PathBuf;
use std::sync::Mutex;
use std::time::Duration;
use tauri::{path::BaseDirectory, AppHandle, Emitter, Manager, RunEvent, State};

/// Temps laissé à `freecadcmd` pour importer FreeCAD et écouter.
const ENGINE_TIMEOUT: Duration = Duration::from_secs(180);

#[derive(Default)]
struct EngineState(Mutex<Option<freecad::Engine>>);

#[derive(Debug, Clone, Serialize)]
struct Status {
    freecadcmd: Option<PathBuf>,
    version: Option<String>,
    source: Option<freecad::Source>,
    reference: String,
    matches_reference: bool,
    can_install: bool,
    install_dir: PathBuf,
    os: &'static str,
    arch: &'static str,
    app_version: String,
}

struct Paths {
    data_dir: PathBuf,
    config: PathBuf,
    engine_log: PathBuf,
    server_py: PathBuf,
    platform_py: PathBuf,
}

fn paths(app: &AppHandle) -> Result<Paths, String> {
    let data_dir = app.path().app_data_dir().map_err(|e| e.to_string())?;
    let log_dir = app.path().app_log_dir().map_err(|e| e.to_string())?;
    let resolve = |rel: &str| {
        app.path()
            .resolve(rel, BaseDirectory::Resource)
            .map_err(|e| format!("{rel} : {e}"))
    };
    Ok(Paths {
        config: data_dir.join("config.json"),
        engine_log: log_dir.join("engine.log"),
        server_py: resolve("engine/server.py")?,
        platform_py: resolve("engine/platform.py")?,
        data_dir,
    })
}

fn reference_version(p: &Paths) -> String {
    std::fs::read_to_string(&p.platform_py)
        .ok()
        .and_then(|t| freecad::reference_version(&t))
        .unwrap_or_else(|| "1.1.3".to_string())
}

fn status_for(app: &AppHandle) -> Result<Status, String> {
    let p = paths(app)?;
    let reference = reference_version(&p);
    let located = freecad::locate(&p.data_dir, &p.config, &reference);
    let version = located.as_ref().and_then(|l| l.version.clone());
    Ok(Status {
        matches_reference: version.as_deref() == Some(reference.as_str()),
        freecadcmd: located.as_ref().map(|l| l.path.clone()),
        source: located.as_ref().map(|l| l.source),
        version,
        can_install: freecad::assets::asset_for_host(&reference).is_some(),
        install_dir: freecad::locate::managed_dir(&p.data_dir, &reference),
        reference,
        os: std::env::consts::OS,
        arch: std::env::consts::ARCH,
        app_version: app.package_info().version.to_string(),
    })
}

/// Où en est FreeCAD sur cette machine.
#[tauri::command]
async fn status(app: AppHandle) -> Result<Status, String> {
    tauri::async_runtime::spawn_blocking(move || status_for(&app))
        .await
        .map_err(|e| e.to_string())?
}

/// L'utilisateur désigne lui-même son `freecadcmd`.
#[tauri::command]
async fn choose_freecadcmd(app: AppHandle, path: PathBuf) -> Result<Status, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let p = paths(&app)?;
        let candidate = if path.is_dir() {
            freecad::find_freecadcmd_under(&path)
                .ok_or_else(|| format!("aucun freecadcmd sous {}", path.display()))?
        } else {
            path
        };
        freecad::version_of(&candidate).ok_or_else(|| {
            format!(
                "{} ne répond pas à --version : est-ce bien FreeCAD ?",
                candidate.display()
            )
        })?;
        freecad::Config {
            freecadcmd: Some(candidate),
        }
        .save(&p.config)
        .map_err(|e| e.to_string())?;
        status_for(&app)
    })
    .await
    .map_err(|e| e.to_string())?
}

/// Télécharge et installe la version de référence ; progression par
/// événements `install-progress`.
#[tauri::command]
async fn install_freecad(app: AppHandle) -> Result<Status, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let p = paths(&app)?;
        let reference = reference_version(&p);
        let emitter = app.clone();
        freecad::install(&p.data_dir, &reference, &mut |progress| {
            let _ = emitter.emit("install-progress", &progress);
        })
        .map_err(|e| e.to_string())?;
        // L'installation gérée prime : on efface un éventuel choix manuel.
        let _ = freecad::Config::default().save(&p.config);
        status_for(&app)
    })
    .await
    .map_err(|e| e.to_string())?
}

/// Lance le moteur puis fait naviguer la fenêtre vers l'interface.
#[tauri::command]
async fn start_engine(app: AppHandle, state: State<'_, EngineState>) -> Result<String, String> {
    let handle = app.clone();
    let engine = tauri::async_runtime::spawn_blocking(move || {
        let p = paths(&handle)?;
        let reference = reference_version(&p);
        let located = freecad::locate(&p.data_dir, &p.config, &reference)
            .ok_or_else(|| "FreeCAD introuvable".to_string())?;
        freecad::Engine::start(&located.path, &p.server_py, &p.engine_log, ENGINE_TIMEOUT)
            .map_err(|e| e.to_string())
    })
    .await
    .map_err(|e| e.to_string())??;
    let url = freecad::engine::url();
    *state.0.lock().map_err(|e| e.to_string())? = Some(engine);
    open_cad_window(&app, &url)?;
    Ok(url)
}

/// Ouvre l'interface dans une fenêtre neuve, à la place de l'écran de
/// lancement, en reprenant sa taille et son état.
///
/// Naviguer la fenêtre de lancement vers l'URL du moteur laissait, sous
/// Windows, une webview plus grande que la fenêtre (barre d'état hors
/// écran, vue 3D décentrée). Une fenêtre créée directement sur l'URL passe
/// par le chemin standard de dimensionnement.
fn open_cad_window(app: &AppHandle, url: &str) -> Result<(), String> {
    use tauri::{WebviewUrl, WebviewWindowBuilder};

    let target: tauri::Url = url.parse().map_err(|e| format!("{e}"))?;
    let launcher = app.get_webview_window("main");
    let mut builder = WebviewWindowBuilder::new(app, "cad", WebviewUrl::External(target))
        .title("FreeSolid")
        .min_inner_size(900.0, 600.0);
    let mut maximized = false;
    if let Some(launcher) = &launcher {
        maximized = launcher.is_maximized().unwrap_or(false);
        if let (Ok(size), Ok(scale)) = (launcher.inner_size(), launcher.scale_factor()) {
            let logical = size.to_logical::<f64>(scale);
            builder = builder.inner_size(logical.width, logical.height);
        }
        if let (Ok(pos), Ok(scale)) = (launcher.outer_position(), launcher.scale_factor()) {
            let logical = pos.to_logical::<f64>(scale);
            builder = builder.position(logical.x, logical.y);
        }
    }
    let cad = builder.build().map_err(|e| e.to_string())?;
    if maximized {
        let _ = cad.maximize();
    }
    if let Some(launcher) = launcher {
        let _ = launcher.close();
    }
    Ok(())
}

/// Chemin du journal du moteur, pour l'écran d'erreur.
#[tauri::command]
fn engine_log_path(app: AppHandle) -> Result<PathBuf, String> {
    Ok(paths(&app)?.engine_log)
}

fn stop_engine(app: &AppHandle) {
    if let Some(state) = app.try_state::<EngineState>() {
        if let Ok(mut guard) = state.0.lock() {
            if let Some(engine) = guard.as_mut() {
                engine.stop();
            }
            *guard = None;
        }
    }
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_dialog::init())
        .manage(EngineState::default())
        .invoke_handler(tauri::generate_handler![
            status,
            choose_freecadcmd,
            install_freecad,
            start_engine,
            engine_log_path
        ])
        .build(tauri::generate_context!())
        .expect("FreeSolid : impossible de construire l'application")
        .run(|app, event| {
            if let RunEvent::Exit | RunEvent::ExitRequested { .. } = event {
                stop_engine(app);
            }
        });
}

// MYKO Tauri shell.
//
// Responsibilities:
//   * Spawn `python -m backend.bridge` as a child process on app launch.
//   * Track the child so we can signal it on shutdown.
//   * On app exit, send SIGTERM (unix) so the bridge cleans up its
//     session token + aiohttp session gracefully.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::process::{Child, Command};
use std::sync::Mutex;

use once_cell::sync::Lazy;
use tauri::RunEvent;

static BRIDGE_CHILD: Lazy<Mutex<Option<Child>>> = Lazy::new(|| Mutex::new(None));

fn spawn_bridge() {
    // Resolve the project root (../.. from src-tauri) so we invoke the backend module.
    let cwd = std::env::current_dir().unwrap_or_else(|_| std::path::PathBuf::from("."));
    let project_root = cwd
        .ancestors()
        .find(|p| p.join("backend").join("bridge.py").exists())
        .map(|p| p.to_path_buf())
        .unwrap_or(cwd.clone());

    let python = std::env::var("MYKO_PYTHON").unwrap_or_else(|_| "python3".to_string());
    let child = Command::new(python)
        .args(["-m", "backend.bridge"])
        .current_dir(&project_root)
        .spawn();

    match child {
        Ok(c) => {
            log::info!("Spawned bridge pid={}", c.id());
            *BRIDGE_CHILD.lock().unwrap() = Some(c);
        }
        Err(e) => {
            log::error!("Failed to spawn bridge: {}", e);
        }
    }
}

fn terminate_bridge() {
    let mut guard = BRIDGE_CHILD.lock().unwrap();
    if let Some(mut child) = guard.take() {
        #[cfg(unix)]
        {
            use nix::sys::signal::{kill, Signal};
            use nix::unistd::Pid;
            let pid = Pid::from_raw(child.id() as i32);
            let _ = kill(pid, Signal::SIGTERM);
        }
        #[cfg(not(unix))]
        {
            let _ = child.kill();
        }
        // Give it a moment, then force if needed.
        std::thread::sleep(std::time::Duration::from_millis(500));
        let _ = child.kill();
        let _ = child.wait();
    }
}

fn main() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_fs::init())
        .setup(|_app| {
            spawn_bridge();
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("failed to build tauri app");

    app.run(|_handle, event| {
        if let RunEvent::ExitRequested { .. } | RunEvent::Exit = event {
            terminate_bridge();
        }
    });
}

mod app;
mod config;
mod files;
mod input;
mod render;
mod ring;

use anyhow::Result;
use smithay_client_toolkit::reexports::calloop::EventLoop;
use smithay_client_toolkit::reexports::calloop_wayland_source::WaylandSource;
use wayland_client::{globals::registry_queue_init, Connection};

use app::App;

fn main() -> Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(tracing_subscriber::EnvFilter::from_default_env()
            .add_directive("voider=info".parse()?))
        .init();

    let conn   = Connection::connect_to_env()?;
    let (globals, event_queue) = registry_queue_init::<App>(&conn)?;
    let qh = event_queue.handle();

    let mut event_loop: EventLoop<App> = EventLoop::try_new()?;
    WaylandSource::new(conn.clone(), event_queue)
        .insert(event_loop.handle())?;

    let mut app = App::new(&globals, &qh)?;

    // Initial draw after the layer surface configure comes back
    loop {
        event_loop.dispatch(None, &mut app)?;
        if app.exit { break; }
    }

    Ok(())
}

// ── Font loading ──────────────────────────────────────────────────────────────

pub fn load_font(family: &str) -> Result<Vec<u8>> {
    // Use fc-match (fontconfig CLI) — no C library linkage required.
    for query in [family, "monospace"] {
        if let Ok(out) = std::process::Command::new("fc-match")
            .args(["--format=%{file}", query])
            .output()
        {
            if out.status.success() {
                let path = String::from_utf8_lossy(&out.stdout).trim().to_string();
                if !path.is_empty() {
                    if let Ok(bytes) = std::fs::read(&path) {
                        tracing::info!("font: {path}");
                        return Ok(bytes);
                    }
                }
            }
        }
    }
    anyhow::bail!("no font found — ensure fontconfig and a monospace font are installed")
}

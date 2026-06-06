// voider-shell: thin Wayland layer-shell host for VoiderOS
//
// Does exactly two things:
//   1. Creates a transparent Layer::Bottom surface — marks the floor of the
//      window stack so nothing can accidentally slip below Voider.
//   2. Spawns the Voider Python app (VOIDER_CMD env var, default "voider-py")
//      and keeps the surface alive while it runs.
//
// Renders nothing. Intercepts no input. All UI logic lives in Python.

use std::time::Duration;

use smithay_client_toolkit::{
    compositor::{CompositorHandler, CompositorState},
    delegate_compositor, delegate_layer, delegate_output, delegate_registry,
    delegate_seat, delegate_shm,
    output::{OutputHandler, OutputState},
    registry::{ProvidesRegistryState, RegistryState},
    registry_handlers,
    seat::{Capability, SeatHandler, SeatState},
    shell::wlr_layer::{
        Anchor, KeyboardInteractivity, Layer, LayerShell, LayerShellHandler,
        LayerSurface, LayerSurfaceConfigure,
    },
    shm::{Shm, ShmHandler, slot::SlotPool},
};
use wayland_client::{
    globals::{registry_queue_init, GlobalList},
    protocol::{wl_output, wl_seat, wl_shm, wl_surface},
    Connection, QueueHandle,
};
use smithay_client_toolkit::reexports::calloop::EventLoop;
use smithay_client_toolkit::reexports::calloop_wayland_source::WaylandSource;

// ── State ─────────────────────────────────────────────────────────────────────

struct Shell {
    registry_state: RegistryState,
    output_state:   OutputState,
    seat_state:     SeatState,
    shm:            Shm,
    pool:           SlotPool,
    layer_surface:  Option<LayerSurface>,
    ready:          bool, // true after first configure
}

impl Shell {
    fn new(globals: &GlobalList, qh: &QueueHandle<Self>) -> anyhow::Result<Self> {
        let compositor  = CompositorState::bind(globals, qh)?;
        let layer_shell = LayerShell::bind(globals, qh)?;
        let shm         = Shm::bind(globals, qh)?;
        let seat_state  = SeatState::new(globals, qh);

        let surface = compositor.create_surface(qh);
        let layer   = layer_shell.create_layer_surface(
            qh, surface, Layer::Bottom, Some("voider-shell"), None,
        );

        layer.set_anchor(Anchor::all());
        layer.set_exclusive_zone(-1);                         // fullscreen, no exclusion
        layer.set_keyboard_interactivity(KeyboardInteractivity::None); // Python owns input
        layer.commit();

        let pool = SlotPool::new(4, &shm)?; // minimal — surface is transparent

        Ok(Self {
            registry_state: RegistryState::new(globals),
            output_state:   OutputState::new(globals, qh),
            seat_state,
            shm,
            pool,
            layer_surface: Some(layer),
            ready: false,
        })
    }
}

// ── Entry point ───────────────────────────────────────────────────────────────

fn main() -> anyhow::Result<()> {
    let conn = Connection::connect_to_env()?;
    let (globals, event_queue) = registry_queue_init::<Shell>(&conn)?;
    let qh = event_queue.handle();

    let mut event_loop: EventLoop<Shell> = EventLoop::try_new()?;
    WaylandSource::new(conn, event_queue).insert(event_loop.handle())?;

    let mut shell = Shell::new(&globals, &qh)?;

    // Wait for compositor to configure the surface before spawning Python
    while !shell.ready {
        event_loop.dispatch(Some(Duration::from_millis(100)), &mut shell)?;
    }

    // Spawn Voider Python — VOIDER_CMD overrides the default binary name
    let cmd = std::env::var("VOIDER_CMD").unwrap_or_else(|_| "voider-py".into());
    let mut child = std::process::Command::new(&cmd)
        .env("QT_QPA_PLATFORM", "wayland")
        .spawn()
        .unwrap_or_else(|e| panic!("failed to spawn '{cmd}': {e}"));

    // Keep the layer surface alive for as long as Python runs
    loop {
        event_loop.dispatch(Some(Duration::from_millis(100)), &mut shell)?;
        match child.try_wait()? {
            Some(status) => {
                eprintln!("voider-py exited with {status}");
                break;
            }
            None => {}
        }
    }
    Ok(())
}

// ── Handler implementations ───────────────────────────────────────────────────

impl LayerShellHandler for Shell {
    fn closed(&mut self, _: &Connection, _: &QueueHandle<Self>, _: &LayerSurface) {
        std::process::exit(0);
    }

    fn configure(
        &mut self, _: &Connection, _: &QueueHandle<Self>,
        _: &LayerSurface, _: LayerSurfaceConfigure, _: u32,
    ) {
        if self.ready { return; }
        self.ready = true;

        // Commit a single fully-transparent pixel — satisfies the compositor,
        // renders nothing visible on screen.
        let Some(layer) = &self.layer_surface else { return };
        let Ok((buf, canvas)) = self.pool.create_buffer(1, 1, 4, wl_shm::Format::Argb8888) else { return };
        canvas.fill(0); // alpha = 0
        layer.wl_surface().attach(Some(buf.wl_buffer()), 0, 0);
        layer.wl_surface().damage_buffer(0, 0, 1, 1);
        layer.wl_surface().commit();
    }
}

impl CompositorHandler for Shell {
    fn scale_factor_changed(&mut self, _: &Connection, _: &QueueHandle<Self>, _: &wl_surface::WlSurface, _: i32) {}
    fn transform_changed(&mut self, _: &Connection, _: &QueueHandle<Self>, _: &wl_surface::WlSurface, _: wl_output::Transform) {}
    fn frame(&mut self, _: &Connection, _: &QueueHandle<Self>, _: &wl_surface::WlSurface, _: u32) {}
}

impl OutputHandler for Shell {
    fn output_state(&mut self) -> &mut OutputState { &mut self.output_state }
    fn new_output(&mut self, _: &Connection, _: &QueueHandle<Self>, _: wl_output::WlOutput) {}
    fn update_output(&mut self, _: &Connection, _: &QueueHandle<Self>, _: wl_output::WlOutput) {}
    fn output_destroyed(&mut self, _: &Connection, _: &QueueHandle<Self>, _: wl_output::WlOutput) {}
}

impl SeatHandler for Shell {
    fn seat_state(&mut self) -> &mut SeatState { &mut self.seat_state }
    fn new_seat(&mut self, _: &Connection, _: &QueueHandle<Self>, _: wl_seat::WlSeat) {}
    fn new_capability(&mut self, _: &Connection, _: &QueueHandle<Self>, _: wl_seat::WlSeat, _: Capability) {}
    fn remove_capability(&mut self, _: &Connection, _: &QueueHandle<Self>, _: wl_seat::WlSeat, _: Capability) {}
    fn remove_seat(&mut self, _: &Connection, _: &QueueHandle<Self>, _: wl_seat::WlSeat) {}
}

impl ShmHandler for Shell {
    fn shm_state(&mut self) -> &mut Shm { &mut self.shm }
}

impl ProvidesRegistryState for Shell {
    fn registry(&mut self) -> &mut RegistryState { &mut self.registry_state }
    registry_handlers![OutputState, SeatState];
}

delegate_compositor!(Shell);
delegate_output!(Shell);
delegate_layer!(Shell);
delegate_seat!(Shell);
delegate_shm!(Shell);
delegate_registry!(Shell);

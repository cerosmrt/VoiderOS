use std::path::PathBuf;

use smithay_client_toolkit::{
    compositor::{CompositorHandler, CompositorState},
    delegate_compositor, delegate_keyboard, delegate_layer, delegate_output,
    delegate_registry, delegate_seat, delegate_shm,
    output::{OutputHandler, OutputState},
    registry::{ProvidesRegistryState, RegistryState},
    registry_handlers,
    seat::{Capability, SeatHandler, SeatState},
    seat::keyboard::{KeyboardHandler, KeyEvent, Modifiers, RepeatInfo},
    shell::{
        WaylandSurface,
        wlr_layer::{
            Anchor, KeyboardInteractivity, Layer, LayerShell, LayerShellHandler,
            LayerSurface, LayerSurfaceConfigure,
        },
    },
    shm::{Shm, ShmHandler, slot::SlotPool},
};
use wayland_client::{
    globals::GlobalList,
    protocol::{wl_keyboard, wl_output, wl_seat, wl_shm, wl_surface},
    Connection, QueueHandle,
};

use crate::{
    config::Config,
    files::{append_line, read_file, save_file, FileIndex},
    input::{self, Action, View},
    render::{self, GlyphCache},
    ring::Ring,
};

// ── UI state ──────────────────────────────────────────────────────────────────

pub struct UiState {
    pub config:       Config,
    pub view:         View,
    pub input:        String,      // line being typed
    pub ring:         Ring,        // committed lines
    pub command_mode: bool,
    pub cmd_buffer:   String,
    pub active_file:  PathBuf,
    pub file_index:   FileIndex,
    pub nav_cursor:   usize,
    pub search_query: String,
    pub blink_tick:   u64,         // incremented per frame for cursor blink
    pub ring_nav_idx: Option<usize>, // Some(i) = navigating existing ring line i
}

impl UiState {
    pub fn apply(&mut self, action: Action) {
        match self.view {
            View::Write    => self.handle_write(action),
            View::Navigate => self.handle_navigate(action),
            View::Void     => match action {
                Action::SwitchView(v) => self.view = v,
                Action::Nothing       => {}
                _                     => self.view = View::Write,
            },
        }
    }

    fn handle_write(&mut self, action: Action) {
        match action {
            Action::SwitchView(v) => {
                self.ring_nav_idx = None;
                self.view = v;
            }

            Action::Char('!') if self.input.is_empty() && !self.command_mode => {
                self.command_mode = true;
            }

            Action::Char(c) if self.command_mode => { self.cmd_buffer.push(c); }
            Action::Char(c)                       => { self.input.push(c); }

            Action::Backspace if self.command_mode => {
                if self.cmd_buffer.is_empty() { self.command_mode = false; }
                else { self.cmd_buffer.pop(); }
            }
            Action::Backspace => { self.input.pop(); }

            Action::Escape if self.command_mode => {
                self.command_mode = false;
                self.cmd_buffer.clear();
            }
            Action::Escape => {
                self.ring_nav_idx = None;
                self.input.clear();
            }

            Action::Enter if self.command_mode => self.exec_command(),

            Action::Enter => {
                let line = std::mem::take(&mut self.input);
                if !line.is_empty() {
                    if let Some(idx) = self.ring_nav_idx.take() {
                        self.ring.replace(idx, line);
                        let _ = save_file(&self.active_file, self.ring.lines());
                    } else {
                        self.ring.push(line.clone());
                        let _ = append_line(&self.active_file, &line);
                    }
                } else {
                    self.ring_nav_idx = None;
                }
            }

            // Up: navigate backwards through ring lines, load into input
            Action::NavUp => {
                if self.ring.len() > 0 {
                    let new_idx = match self.ring_nav_idx {
                        None    => self.ring.head,
                        Some(i) => i.saturating_sub(1),
                    };
                    self.ring_nav_idx = Some(new_idx);
                    self.input = self.ring.lines()[new_idx].clone();
                }
            }

            // Down: navigate forward; past head exits navigation mode
            Action::NavDown => {
                if let Some(i) = self.ring_nav_idx {
                    if i >= self.ring.head {
                        self.ring_nav_idx = None;
                        self.input.clear();
                    } else {
                        let new_idx = i + 1;
                        self.ring_nav_idx = Some(new_idx);
                        self.input = self.ring.lines()[new_idx].clone();
                    }
                }
            }

            Action::NewFile => {
                self.ring_nav_idx = None;
                self.search_query.clear();
                self.nav_cursor = 0;
                self.view = View::Navigate;
            }

            _ => {}
        }
    }

    fn handle_navigate(&mut self, action: Action) {
        match action {
            Action::SwitchView(v) => self.view = v,
            Action::Escape        => { self.search_query.clear(); self.view = View::Write; }

            Action::NavUp   => { self.nav_cursor = self.nav_cursor.saturating_sub(1); }
            Action::NavDown => {
                let max = self.file_index.filter(&self.search_query).len().saturating_sub(1);
                self.nav_cursor = (self.nav_cursor + 1).min(max);
            }

            Action::Char(c) => {
                self.search_query.push(c);
                self.nav_cursor = 0;
            }
            Action::Backspace => {
                if self.search_query.is_empty() {
                    self.view = View::Write;
                } else {
                    self.search_query.pop();
                    self.nav_cursor = 0;
                }
            }

            Action::Enter => {
                let filtered = self.file_index.filter(&self.search_query);
                let sel = self.nav_cursor.min(filtered.len().saturating_sub(1));
                if let Some(path) = filtered.get(sel).map(|p| p.to_path_buf()) {
                    self.load_file(path);
                    self.search_query.clear();
                    self.nav_cursor = 0;
                    self.view = View::Write;
                }
            }

            _ => {}
        }
    }

    fn load_file(&mut self, path: PathBuf) {
        self.active_file = path.clone();
        self.ring = Ring::new();
        for line in read_file(&path) { self.ring.push(line); }
    }

    fn exec_command(&mut self) {
        let cmd  = std::mem::take(&mut self.cmd_buffer);
        self.command_mode = false;

        let mut parts = cmd.trim().splitn(2, ' ');
        let verb = parts.next().unwrap_or("");
        let args = parts.next().unwrap_or("");

        match verb {
            "q" | "quit" => std::process::exit(0),

            "new" => {
                let name = if args.is_empty() { "untitled" } else { args };
                if let Ok(path) = self.file_index.create_new(name) {
                    self.load_file(path);
                }
            }

            "open" => {
                self.search_query = args.to_owned();
                self.nav_cursor   = 0;
                self.view         = View::Navigate;
            }

            "rm" => {
                let path = self.active_file.clone();
                if self.file_index.delete(&path).is_ok() {
                    if let Some(next) = self.file_index.entries.first().cloned() {
                        self.load_file(next);
                    }
                }
            }

            // Unknown → launch as shell command
            app => {
                let full = if args.is_empty() { app.to_owned() } else { format!("{app} {args}") };
                let _ = std::process::Command::new("sh")
                    .arg("-c").arg(&full)
                    .stdin(std::process::Stdio::null())
                    .stdout(std::process::Stdio::null())
                    .stderr(std::process::Stdio::null())
                    .spawn();
            }
        }
    }
}

// ── App (sctk boilerplate) ────────────────────────────────────────────────────

pub struct App {
    pub registry_state:   RegistryState,
    pub compositor_state: CompositorState,
    pub output_state:     OutputState,
    pub shm_state:        Shm,
    pub seat_state:       SeatState,
    pub layer_shell:      LayerShell,

    pub layer_surface:    Option<LayerSurface>,
    pub keyboard:         Option<wl_keyboard::WlKeyboard>,
    pub pool:             SlotPool,

    pub glyph_cache:      GlyphCache,
    pub ui:               UiState,
    pub modifiers:        Modifiers,

    pub width:            u32,
    pub height:           u32,
    pub request_redraw:   bool,
    pub exit:             bool,
}

impl App {
    pub fn new(globals: &GlobalList, qh: &QueueHandle<App>) -> anyhow::Result<Self> {
        let compositor_state = CompositorState::bind(globals, qh)?;
        let output_state     = OutputState::new(globals, qh);
        let shm_state        = Shm::bind(globals, qh)?;
        let layer_shell      = LayerShell::bind(globals, qh)?;
        let seat_state       = SeatState::new(globals, qh);

        let config   = Config::load();
        let void_dir = config.void_dir();
        std::fs::create_dir_all(&void_dir)?;

        let font_bytes = crate::load_font(&config.font_family)?;
        let glyph_cache = GlyphCache::new(&font_bytes)?;

        let active_file = void_dir.join("0.txt");
        if !active_file.exists() { let _ = std::fs::write(&active_file, ""); }

        let file_index = FileIndex::build(&void_dir);
        let mut ring   = Ring::new();
        for line in read_file(&active_file) { ring.push(line); }

        // Create the layer surface — fullscreen, at the bottom, under all windows
        let surface      = compositor_state.create_surface(qh);
        let layer_surface = layer_shell.create_layer_surface(
            qh, surface, Layer::Bottom, Some("voider"), None,
        );
        layer_surface.set_anchor(Anchor::all());
        layer_surface.set_exclusive_zone(-1);
        layer_surface.set_keyboard_interactivity(KeyboardInteractivity::OnDemand);
        layer_surface.commit();

        // Pool sized for double-buffering at a typical 1080p resolution
        let pool = SlotPool::new(1920 * 1080 * 4 * 2, &shm_state)?;

        let ui = UiState {
            config,
            view: View::Write,
            input: String::new(),
            ring,
            command_mode: false,
            cmd_buffer: String::new(),
            active_file,
            file_index,
            nav_cursor: 0,
            search_query: String::new(),
            blink_tick: 0,
            ring_nav_idx: None,
        };

        Ok(Self {
            registry_state:   RegistryState::new(globals),
            compositor_state,
            output_state,
            shm_state,
            seat_state,
            layer_shell,
            layer_surface: Some(layer_surface),
            keyboard: None,
            pool,
            glyph_cache,
            ui,
            modifiers: Modifiers::default(),
            width:  1920,
            height: 1080,
            request_redraw: true,
            exit: false,
        })
    }

    pub fn draw(&mut self, qh: &QueueHandle<App>) {
        let Some(layer) = &self.layer_surface else { return; };
        let stride = self.width * 4;

        let Ok((buffer, canvas)) = self.pool.create_buffer(
            self.width as i32,
            self.height as i32,
            stride as i32,
            wl_shm::Format::Argb8888,
        ) else { return; };

        render::draw_frame(canvas, &mut self.glyph_cache, &self.ui, self.width, self.height);

        let surface = layer.wl_surface();
        surface.attach(Some(buffer.wl_buffer()), 0, 0);
        surface.damage_buffer(0, 0, i32::MAX, i32::MAX);
        // Request next frame callback (drives cursor blink)
        surface.frame(qh, surface.clone());
        surface.commit();
    }
}

// ── sctk delegate implementations ────────────────────────────────────────────

impl CompositorHandler for App {
    fn scale_factor_changed(&mut self, _: &Connection, _: &QueueHandle<Self>, _: &wl_surface::WlSurface, _: i32) {}
    fn transform_changed(&mut self, _: &Connection, _: &QueueHandle<Self>, _: &wl_surface::WlSurface, _: wl_output::Transform) {}
    fn frame(&mut self, _: &Connection, qh: &QueueHandle<Self>, _: &wl_surface::WlSurface, _: u32) {
        self.ui.blink_tick = self.ui.blink_tick.wrapping_add(1);
        self.draw(qh);
    }
}

impl OutputHandler for App {
    fn output_state(&mut self) -> &mut OutputState { &mut self.output_state }
    fn new_output(&mut self, _: &Connection, _: &QueueHandle<Self>, _: wl_output::WlOutput) {}
    fn update_output(&mut self, _: &Connection, _: &QueueHandle<Self>, _: wl_output::WlOutput) {}
    fn output_destroyed(&mut self, _: &Connection, _: &QueueHandle<Self>, _: wl_output::WlOutput) {}
}

impl LayerShellHandler for App {
    fn closed(&mut self, _: &Connection, _: &QueueHandle<Self>, _: &LayerSurface) {
        self.exit = true;
    }
    fn configure(&mut self, _: &Connection, qh: &QueueHandle<Self>, _: &LayerSurface, configure: LayerSurfaceConfigure, _serial: u32) {
        if configure.new_size.0 > 0 && configure.new_size.1 > 0 {
            self.width  = configure.new_size.0;
            self.height = configure.new_size.1;
            let _ = self.pool.resize((self.width * self.height * 4 * 2) as usize);
        }
        // sctk 0.18 acknowledges the configure automatically — no ack_configure needed
        self.draw(qh);
    }
}

impl SeatHandler for App {
    fn seat_state(&mut self) -> &mut SeatState { &mut self.seat_state }

    fn new_seat(&mut self, _: &Connection, _: &QueueHandle<Self>, _: wl_seat::WlSeat) {}

    fn new_capability(&mut self, _: &Connection, qh: &QueueHandle<Self>, seat: wl_seat::WlSeat, cap: Capability) {
        if cap == Capability::Keyboard && self.keyboard.is_none() {
            self.keyboard = self.seat_state.get_keyboard(qh, &seat, None).ok();
        }
    }

    fn remove_capability(&mut self, _: &Connection, _: &QueueHandle<Self>, _: wl_seat::WlSeat, cap: Capability) {
        if cap == Capability::Keyboard {
            if let Some(kbd) = self.keyboard.take() { kbd.release(); }
        }
    }

    fn remove_seat(&mut self, _: &Connection, _: &QueueHandle<Self>, _: wl_seat::WlSeat) {}
}

impl KeyboardHandler for App {
    fn enter(&mut self, _: &Connection, _: &QueueHandle<Self>, _: &wl_keyboard::WlKeyboard, _: &wl_surface::WlSurface, _: u32, _: &[u32], _: &[smithay_client_toolkit::seat::keyboard::Keysym]) {}
    fn leave(&mut self, _: &Connection, _: &QueueHandle<Self>, _: &wl_keyboard::WlKeyboard, _: &wl_surface::WlSurface, _: u32) {}

    fn press_key(&mut self, _: &Connection, _: &QueueHandle<Self>, _: &wl_keyboard::WlKeyboard, _: u32, event: KeyEvent) {
        let action = input::map(event.keysym, event.utf8.as_deref(), &self.modifiers);
        self.ui.apply(action);
        self.request_redraw = true;
    }

    fn release_key(&mut self, _: &Connection, _: &QueueHandle<Self>, _: &wl_keyboard::WlKeyboard, _: u32, _: KeyEvent) {}

    fn update_modifiers(&mut self, _: &Connection, _: &QueueHandle<Self>, _: &wl_keyboard::WlKeyboard, _: u32, modifiers: Modifiers) {
        self.modifiers = modifiers;
    }
    fn update_repeat_info(&mut self, _: &Connection, _: &QueueHandle<Self>, _: &wl_keyboard::WlKeyboard, _: RepeatInfo) {}
}

impl ShmHandler for App {
    fn shm_state(&mut self) -> &mut Shm { &mut self.shm_state }
}

impl ProvidesRegistryState for App {
    fn registry(&mut self) -> &mut RegistryState { &mut self.registry_state }
    registry_handlers![OutputState, SeatState];
}

delegate_compositor!(App);
delegate_output!(App);
delegate_layer!(App);
delegate_seat!(App);
delegate_keyboard!(App);
delegate_shm!(App);
delegate_registry!(App);

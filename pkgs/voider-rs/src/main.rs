// En Windows, sin la ventana negra de consola detrás: Voider ES la interfaz,
// no una herramienta lanzada desde una terminal. En Linux el atributo se ignora.
#![cfg_attr(windows, windows_subsystem = "windows")]

//! voider-rs — a Rust/egui mirror of proto-voider.
//!
//! Parallel to the Python app, which stays untouched: this is a second
//! implementation, built view by view, aiming at 1:1 behaviour. Immediate-mode
//! rendering means we own every pixel and every keystroke — the custom things
//! that fight a widget toolkit (the typewriter caret, scriptio continua) are
//! just "what do I draw this frame?".

mod app;
mod backup;
mod browse;
mod bundle;
mod carousel;
mod config;
mod epub;
mod corpus;
mod f5;
mod fonts;
mod help;
mod hyphen;
mod ipc;
mod library;
mod paragraphs;
mod pdf;
mod line_ring;
mod position;
mod reading;
mod reformat;
mod ring;
mod shot;
mod slides;
mod split;
mod text_line;
mod tts;
mod typeset;
mod undo;
mod void;
mod words;

use eframe::egui;

use app::{caps_lock_on, View, Voider};


/// Matches the Python view: the circle inset from the shorter side.
const CIRCLE_INSET: f32 = 35.0;

fn main() -> eframe::Result {
    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_inner_size([1000.0, 700.0])
            // Ctrl+± thins the ground out; without a transparent surface to
            // begin with there is nothing for it to thin towards.
            .with_transparent(true)
            .with_title("Voider"),
        ..Default::default()
    };
    eframe::run_native(
        "voider-rs",
        options,
        Box::new(|cc| {
            let app = VoiderApp::new();
            install_font(&cc.egui_ctx, &app.voider.config.font_family);
            Ok(Box::new(app))
        }),
    )
}

/// Load the writing font into egui, if it can be found on this machine. Falls
/// back to the built-in face rather than failing — you can always keep writing.
fn install_font(ctx: &egui::Context, family: &str) {
    let Some(bytes) = fonts::load_family(family) else {
        return;
    };
    let mut defs = egui::FontDefinitions::default();
    defs.font_data.insert(
        "voider".to_owned(),
        egui::FontData::from_owned(bytes),
    );
    for fam in [egui::FontFamily::Proportional, egui::FontFamily::Monospace] {
        defs.families.entry(fam).or_default().insert(0, "voider".to_owned());
    }
    ctx.set_fonts(defs);
}

struct VoiderApp {
    /// The mouse pointer is out of the way while you write.
    pointer_hidden: bool,
    /// How many pages F4 laid out last frame — measuring needs the fonts, so
    /// it is known at draw time and remembered for the keys that turn pages.
    reading_pages: usize,
    voider: Voider,
    /// The carousel slide on screen, already drawn into a texture: redrawn only
    /// when the slide (or its frame) changes, not every frame.
    carousel_tex: Option<CarouselTex>,
    /// The font the slides are set in, loaded once.
    carousel_font: Option<typeset::TypeFont>,
    /// The book laid out for the page size on screen, kept until the window or the
    /// chapter changes.
    book_plan: Option<BookPlanCache>,
    /// The page on screen, drawn into a texture.
    book_tex: Option<BookTex>,
}

/// (width, height in pixels, which reading) — what a cached layout was made for.
type BookKey = (u32, u32, u64);

struct BookPlanCache {
    key: BookKey,
    plan: slides::BookPlan,
}

struct BookTex {
    key: BookKey,
    page: usize,
    tex: egui::TextureHandle,
}

/// A rendered slide and the texture it lives in.
struct CarouselTex {
    slide: slides::Slide,
    size: (u32, u32),
    tex: egui::TextureHandle,
}

impl VoiderApp {
    fn new() -> Self {
        Self::with(app::open_sandbox())
    }

    fn with(voider: Voider) -> Self {
        Self {
            voider,
            pointer_hidden: true,
            reading_pages: 1,
            carousel_tex: None,
            carousel_font: None,
            book_plan: None,
            book_tex: None,
        }
    }


    /// The size the writer chose, used by every view.
    fn font_size(&self) -> f32 {
        // The configured size is in points, as the Python's is; the screen is pixels.
        ring::px_from_pt(self.voider.config.font_size)
    }

    /// The jump between the lines of a ring in this font: the font's own height
    /// times the Python's 1.31.
    fn ring_line_h(&self, ctx: &egui::Context, font: &egui::FontId) -> f32 {
        ring::line_height(ctx.fonts(|f| f.row_height(font)))
    }

    /// The mouse pointer: hidden while you type, back on any mouse activity, and
    /// drawn by us as a white ring with a transparent centre so it never hides
    /// the word underneath.
    fn update_pointer(&mut self, ctx: &egui::Context) {
        let (typed, moved) = ctx.input(|i| {
            (
                i.events.iter().any(|e| {
                    matches!(e, egui::Event::Text(_))
                        || matches!(e, egui::Event::Key { pressed: true, .. })
                }),
                i.pointer.velocity() != egui::Vec2::ZERO
                    || i.events.iter().any(|e| {
                        matches!(
                            e,
                            egui::Event::PointerMoved(_)
                                | egui::Event::PointerButton { .. }
                                | egui::Event::MouseWheel { .. }
                        )
                    }),
            )
        });
        if moved {
            self.pointer_hidden = false;
        } else if typed {
            self.pointer_hidden = true;
        }
        // The system arrow never shows: the ring below is the only pointer.
        ctx.set_cursor_icon(egui::CursorIcon::None);
    }

    /// Paint the ring where the pointer is, unless it's hidden.
    fn draw_pointer(&self, painter: &egui::Painter, ctx: &egui::Context) {
        if self.pointer_hidden {
            return;
        }
        if let Some(pos) = ctx.input(|i| i.pointer.hover_pos()) {
            painter.circle_stroke(
                pos,
                11.0,
                egui::Stroke::new(2.0_f32, egui::Color32::WHITE),
            );
        }
    }

    /// Whether Copy / Cut belong to the views rather than to something sitting on
    /// top of them (the help, a browser, a question being asked).
    fn clipboard_keys_free(&self) -> bool {
        !self.voider.help_open
            && self.voider.browser.is_none()
            && self.voider.bundle_prompt.is_none()
            && self.voider.backup_prompt.is_none()
    }

    fn handle_input(&mut self, ctx: &egui::Context) {
        let caps = caps_lock_on();
        let events = ctx.input(|i| i.events.clone());
        for event in events {
            match event {
                // The backtick is a command (the scratch round trip), never a
                // character: the key event below handles it, so drop the text or
                // it would be typed into the line as well.
                egui::Event::Text(t) if t == "`" => {}
                // The sale bundle's name is typed into its own prompt, not the line.
                egui::Event::Text(t) if self.voider.bundle_prompt.is_some() => {
                    self.voider.bundle_type(&t);
                }
                // Ctrl+C and Ctrl+X reach us as Copy and Cut events — egui-winit drops
                // the key for them — so what they mean is decided from the view and
                // the modifiers held (Ctrl+Shift+C is the carousel, in F4).
                egui::Event::Copy if self.clipboard_keys_free() => {
                    let shift = ctx.input(|i| i.modifiers.shift);
                    let searching =
                        self.voider.f2_search.is_some() || self.voider.f3_search.is_some();
                    match copy_action(self.voider.view, shift, searching) {
                        CopyAction::Copy => {
                            if let Some(text) = self.voider.copy_text() {
                                ctx.output_mut(|o| o.copied_text = text);
                            }
                        }
                        CopyAction::Carousel => self.voider.begin_carousel(),
                        CopyAction::Nothing => {}
                    }
                }
                egui::Event::Cut
                    if self.clipboard_keys_free()
                        && self.voider.f2_search.is_none()
                        && self.voider.f3_search.is_none() =>
                {
                    if let Ok(Some(text)) = self.voider.cut_selection() {
                        ctx.output_mut(|o| o.copied_text = text);
                    }
                }
                // Ctrl+V reaches us as a Paste event, not as text.
                egui::Event::Paste(t)
                    if !self.voider.help_open
                        && self.voider.browser.is_none()
                        && self.voider.f2_search.is_none() =>
                {
                    let _ = self.voider.paste_text(&t);
                }
                // While the help is up nothing types: the keypress that closes
                // it must not also land in the text underneath.
                egui::Event::Text(_) if self.voider.help_open => {}
                // Con el navegador abierto no se escribe: la tecla es para él.
                egui::Event::Text(_) if self.voider.browser.is_some() => {}
                egui::Event::Text(t) => self.route_text(&t, caps),
                egui::Event::Key { key, pressed: true, modifiers, .. } => {
                    // The help is a reference, not a mode: any key at all puts
                    // it away, and that key does nothing else.
                    if self.voider.help_open {
                        self.voider.help_open = false;
                        continue;
                    }
                    // El navegador abierto se adueña del teclado: está por
                    // cambiar a qué texto apunta Voider entero.
                    if self.voider.browser.is_some() {
                        match key {
                            egui::Key::ArrowUp => {
                                if let Some(b) = &mut self.voider.browser { b.move_by(-1) }
                            }
                            egui::Key::ArrowDown => {
                                if let Some(b) = &mut self.voider.browser { b.move_by(1) }
                            }
                            egui::Key::Enter => {
                                let _ = self.voider.browser_enter(modifiers.shift);
                            }
                            egui::Key::Escape => self.voider.cancel_browser(),
                            _ => {}
                        }
                        continue;
                    }
                    // So does the sale-bundle question (name, then language).
                    if let Some(p) = self.voider.bundle_prompt.clone() {
                        match key {
                            egui::Key::Enter => {
                                let _ = self.voider.bundle_confirm();
                            }
                            egui::Key::Escape => self.voider.cancel_bundle(),
                            egui::Key::Backspace => self.voider.bundle_backspace(),
                            egui::Key::ArrowUp | egui::Key::ArrowLeft
                                if p.stage == app::BundleStage::Lang =>
                            {
                                self.voider.bundle_cycle_lang(-1)
                            }
                            egui::Key::ArrowDown | egui::Key::ArrowRight | egui::Key::Tab
                                if p.stage == app::BundleStage::Lang =>
                            {
                                self.voider.bundle_cycle_lang(1)
                            }
                            _ => {}
                        }
                        continue;
                    }
                    // A backup waiting to be accepted owns the keyboard: it is
                    // about to write to a drive, so nothing else may fire while
                    // the question is open.
                    if self.voider.backup_prompt.is_some() {
                        match key {
                            egui::Key::Enter => {
                                let _ = self.voider.backup_confirm();
                            }
                            egui::Key::ArrowUp => self.voider.backup_cycle_drive(-1),
                            egui::Key::ArrowDown => self.voider.backup_cycle_drive(1),
                            _ => self.voider.cancel_backup(),
                        }
                        continue;
                    }
                    self.route_key_with(key, modifiers, caps);
                }
                _ => {}
            }
        }
    }

    /// Typed text that no prompt or overlay took, for the view you are in.
    fn route_text(&mut self, t: &str, caps: bool) {
        // With the catalogue open, what is typed filters it — it never reaches
        // the line underneath.
        if self.voider.picker_open && matches!(self.voider.view, View::F2 | View::F5) {
            self.voider.picker_type(t);
            return;
        }
        match self.voider.view {
            // '*' is Tab's twin in the line editors (widgets/circular_view):
            // the cut-up, never a character.
            View::F1 if t == "*" => self.voider.recycle_line(),
            View::F1 => {
                let _ = self.voider.type_text(t, caps);
            }
            View::F2 if t == "*" && self.voider.f2_search.is_none() => {
                let _ = self.voider.doc_tab();
            }
            View::F2 => {
                if self.voider.f2_search.is_some() {
                    self.voider.f2_search_type(&text_line::neutralize_caps(t, caps));
                } else {
                    self.voider.entry.insert(&text_line::neutralize_caps(t, caps));
                    let _ = self.voider.doc_live_save();
                }
            }
            // In F3 the line is the title (or the name being given): typing
            // edits it, and leaving renames. Separators and the portal don't
            // take typing.
            View::F3 => {
                if self.voider.f3_search.is_some() {
                    self.voider.f3_search_type(&text_line::neutralize_caps(t, caps));
                } else {
                    self.voider.f3_type(&text_line::neutralize_caps(t, caps));
                }
            }
            // F9's text goes into egui's own multiline widget, which reads the
            // same events itself — typing it again here would double every
            // character.
            View::F4 | View::F5 | View::F6 | View::F7 | View::F8 | View::F9 | View::F10
            | View::Concat => {}
        }
    }

    /// A key that no prompt or overlay took: Ctrl+A, then the global keys, then
    /// the view's own.
    fn route_key(&mut self, key: egui::Key, modifiers: egui::Modifiers) {
        self.route_key_with(key, modifiers, caps_lock_on());
    }

    fn route_key_with(&mut self, key: egui::Key, modifiers: egui::Modifiers, caps: bool) {
        // Ctrl+A selects the whole line in F1 and F2. (Ctrl+C / X / V never
        // get here as keys: egui-winit turns them into Copy / Cut / Paste
        // events, handled above.)
        let no_search = self.voider.f2_search.is_none() && self.voider.f3_search.is_none();
        if modifiers.ctrl
            && no_search
            && key == egui::Key::A
            && matches!(self.voider.view, View::F1 | View::F2)
        {
            self.voider.entry.select_all();
            return;
        }
        if self.handle_global_key(key, modifiers) {
            return;
        }
        match self.voider.view {
            View::F1 => self.handle_f1_key(key, caps, modifiers),
            View::F2 => self.handle_f2_key(key, caps, modifiers),
            View::F3 => self.handle_f3_key(key, modifiers),
            View::F4 => self.handle_f4_key(key, modifiers),
            View::F6 => self.handle_f6_key(key),
            View::F7 => self.handle_f7_key(key, modifiers),
            View::F8 => self.handle_f8_key(key),
            View::F5 => self.handle_f5_key(key, modifiers),
            View::F9 => self.handle_f9_key(key, modifiers),
            View::F10 => self.handle_f10_key(key, modifiers),
            View::Concat => self.handle_concat_key(key),
        }
    }

    /// Keys that mean the same thing everywhere. Returns true when handled.
    fn handle_global_key(&mut self, key: egui::Key, m: egui::Modifiers) -> bool {
        use egui::Key;
        match key {
            // Con Ctrl, las teclas de vista apuntan Voider a otro lado. Van
            // ANTES que las sin guarda, o el match nunca las alcanza.
            Key::F2 if m.ctrl => self.voider.open_browser(browse::Purpose::ActiveFile),
            Key::F3 if m.ctrl => self.voider.open_browser(browse::Purpose::BookDir),
            Key::F4 if m.ctrl => self.voider.open_browser(browse::Purpose::VoidDir),
            // Alt+F4 quits. Before the plain F4 below, or it would open the reader.
            Key::F4 if m.alt => self.voider.request_quit(),
            Key::F1 => self.voider.switch_to(View::F1),
            Key::F2 => self.voider.switch_to(View::F2),
            // F3 from F3 does nothing — re-entering would reload and move the cursor.
            Key::F3 if self.voider.view == View::F3 => {}
            Key::F3 => self.voider.switch_to(View::F3),
            Key::F4 => self.voider.switch_to(View::F4),
            Key::F5 => self.voider.switch_to(View::F5),
            Key::F6 => self.voider.switch_to(View::F6),
            Key::F7 => self.voider.switch_to(View::F7),
            Key::F8 => self.voider.switch_to(View::F8),
            Key::F9 => self.voider.switch_to(View::F9),
            Key::F10 => self.voider.switch_to(View::F10),
            Key::F11 => self.voider.help_open = true,
            // Ctrl+± thins the ground out and fills it back in — the Python's
            // opacity_up/opacity_down. (Type size lives in F10, on ←/→.)
            Key::Plus | Key::Equals if m.ctrl => self.voider.step_opacity(0.1),
            Key::Minus if m.ctrl => self.voider.step_opacity(-0.1),
            // Shift+F12: the window's centred square into covers/, for carousel art.
            // Before the plain F12, or that one would take it.
            Key::F12 if m.shift => {
                self.voider.take_circle_screenshot();
            }
            Key::F12 => {
                self.voider.take_screenshot();
            }
            Key::W if m.ctrl && m.shift => {
                self.voider.typewriter = !self.voider.typewriter;
                self.voider.status = format!(
                    "Typewriter {}",
                    if self.voider.typewriter { "ON" } else { "OFF" }
                );
            }
            // Ctrl+T: la voz. (Ctrl+Shift+T es el titulo, abajo.)
            Key::T if m.ctrl && !m.shift => self.voider.tts_toggle(),
            Key::T if m.ctrl && m.shift => {
                self.voider.show_title = !self.voider.show_title;
            }
            Key::G if m.ctrl && m.shift => self.voider.commit_void(),
            // Ctrl+B only ASKS: it works out the copy and shows it, and the
            // drive is not touched until that is accepted with Enter.
            // Ctrl+Shift+B is the carousel with a cover (F4), so only the plain one is the backup.
            Key::B if m.ctrl && !m.shift => self.voider.begin_backup(),
            // Undo / redo, only in the views that edit text (F1, F2, F5) and in F3
            // (library operations) unless a name is being typed there — as the
            // Python's eventFilter. Elsewhere Ctrl+Z is the view's own (F9's box).
            Key::Z if m.ctrl && self.undo_here() => {
                let _ = if m.shift { self.voider.redo() } else { self.voider.undo() };
            }
            // Backtick: round trip to the scratch, from wherever you are.
            Key::Backtick => self.voider.scratch_toggle(),
            // PageUp/PageDown are NOT global: each view means something else by
            // them (a paragraph, a book in the library, a page) — see its handler.
            _ => return false,
        }
        true
    }

    fn handle_f1_key(&mut self, key: egui::Key, caps: bool, m: egui::Modifiers) {
        use egui::Key;
        match key {
            Key::Enter => {
                let _ = self.voider.commit_line();
            }
            Key::Backspace if m.ctrl && !caps => {
                self.voider.entry.delete_word_back();
            }
            Key::Backspace => {
                self.voider.backspace(caps);
            }
            Key::Delete if m.ctrl => {
                self.voider.entry.delete_word_forward();
            }
            Key::Delete => {
                self.voider.entry.delete();
            }
            Key::ArrowLeft if m.shift => self.voider.entry.extend_caret(-1),
            Key::ArrowRight if m.shift => self.voider.entry.extend_caret(1),
            Key::Home if m.shift => self.voider.entry.extend_home(),
            Key::End if m.shift => self.voider.entry.extend_end(),
            Key::ArrowLeft => self.voider.entry.move_caret(-1),
            Key::ArrowRight => self.voider.entry.move_caret(1),
            Key::Home => self.voider.entry.home(),
            // Tab: recirculate a line from elsewhere in the book (loop writing).
            Key::Tab => self.voider.recycle_line(),
            // The same cut-up by another route: Ctrl+0 pulls from anywhere in
            // the void, Ctrl+. from this file. (In F2, Ctrl+0 rebases instead —
            // view-scoped, as in the Python.)
            Key::Num0 if m.ctrl => self.voider.random_line_from_void(),
            Key::Period if m.ctrl => self.voider.random_line_from_here(),
            // Alt walks the library without going through F3.
            Key::ArrowUp if m.alt => self.voider.step_file(-1),
            Key::ArrowDown if m.alt => self.voider.step_file(1),
            Key::End => self.voider.entry.end(),
            // Moving keeps what you typed in the line you leave.
            Key::ArrowUp => self.voider.f1_navigate(-1),
            Key::ArrowDown => self.voider.f1_navigate(1),
            Key::PageUp => self.voider.f1_goto_dot(-1),
            Key::PageDown => self.voider.f1_goto_dot(1),
            _ => {}
        }
    }

    fn handle_f2_key(&mut self, key: egui::Key, caps: bool, m: egui::Modifiers) {
        use egui::Key;
        // Con el panel desplegado, las teclas son suyas: estás eligiendo a qué
        // capítulo se va el texto, no editando.
        if self.voider.picker_open {
            self.picker_key(key, m);
            return;
        }
        // A search bar takes exclusive focus: only its own keys mean anything.
        if self.voider.f2_search.is_some() {
            match key {
                Key::ArrowUp => self.voider.f2_search_move(-1),
                Key::ArrowDown => self.voider.f2_search_move(1),
                Key::Enter => self.voider.f2_search_confirm(),
                Key::Escape => self.voider.f2_search_cancel(),
                Key::Backspace => self.voider.f2_search_backspace(),
                _ => {}
            }
            return;
        }
        match key {
            // Ctrl+F: search the document's lines.
            Key::F if m.ctrl && !m.shift => self.voider.open_f2_search(),
            // Ctrl+0: make the current line the file's first.
            Key::Num0 if m.ctrl => {
                let _ = self.voider.rebase_to_current();
            }
            // At the start of the line, Enter is a command (enter/exit focus, or
            // drop into F1 on a blank line); anywhere else it splits the line.
            Key::Enter if self.voider.entry.caret() == 0 => {
                let _ = self.voider.doc_confirm_edit();
            }
            Key::Enter => {
                let _ = self.voider.doc_split_line();
            }
            // Ctrl+Delete at the START of the line sends the whole line down the
            // trash (any file → trash.txt; trash.txt → 0.txt). Anywhere else it
            // deletes the next word, like any editor. Ctrl+Backspace has no such
            // exception: it is always one word back, even at the end of the line.
            // Ctrl+Shift+Delete flattens the document into one paragraph (only on
            // its first dot). Before the arms below, which would otherwise take
            // it for the delete-this-line command.
            Key::Delete if m.ctrl && m.shift => {
                let _ = self.voider.doc_collapse_to_one_paragraph();
            }
            Key::Delete if m.ctrl && self.voider.entry.caret() == 0 => {
                let _ = self.voider.delete_line_to_trash();
            }
            Key::Delete if m.ctrl => {
                self.voider.entry.delete_word_forward();
                let _ = self.voider.doc_live_save();
            }
            Key::Backspace if m.ctrl && !caps && self.voider.entry.caret() > 0 => {
                self.voider.entry.delete_word_back();
                let _ = self.voider.doc_live_save();
            }
            Key::Backspace => {
                if !caps {
                    let _ = self.voider.doc_backspace();
                } // scriptio continua: type and send, no editing
            }
            // Delete at the very end (nothing selected) joins the next line on.
            Key::Delete
                if self.voider.entry.selection().is_none()
                    && self.voider.entry.caret() == self.voider.entry.len() =>
            {
                let _ = self.voider.doc_join_next();
            }
            Key::Delete => {
                self.voider.entry.delete();
                let _ = self.voider.doc_live_save();
            }
            // Ctrl+↑/↓: the start / end of the line (with Shift, selecting there).
            Key::ArrowUp if m.ctrl && m.shift => self.voider.entry.extend_home(),
            Key::ArrowDown if m.ctrl && m.shift => self.voider.entry.extend_end(),
            Key::ArrowUp if m.ctrl => self.voider.entry.home(),
            Key::ArrowDown if m.ctrl => self.voider.entry.end(),
            // Alt+Shift duplicates, the copy going where the arrow points. Before
            // the plain Alt arms below or they would swallow it.
            Key::ArrowUp if m.alt && m.shift => {
                let _ = self.voider.doc_duplicate(-1);
            }
            Key::ArrowDown if m.alt && m.shift => {
                let _ = self.voider.doc_duplicate(1);
            }
            // Alt moves things: the line up/down, the word left/right.
            Key::ArrowUp if m.alt => {
                let _ = self.voider.doc_swap_line(-1);
            }
            Key::ArrowDown if m.alt => {
                let _ = self.voider.doc_swap_line(1);
            }
            // Alt+Shift+→ despliega la biblioteca al costado: la misma idea que
            // Alt mover cosas, pero más lejos — en vez de correr la palabra de
            // al lado, el texto se va a otro capítulo. Va ANTES del Alt+→ suelto,
            // o ese lo taparía.
            // Alt+Shift+←/→: the catalogue, on the side the arrow points, from
            // anywhere (a line, or a paragraph on a dot).
            Key::ArrowLeft | Key::ArrowRight if m.alt && m.shift => {
                self.voider.doc_open_picker();
                self.voider.picker_side =
                    if key == Key::ArrowLeft { app::PickerSide::Left } else { app::PickerSide::Right };
            }
            // Alt+←/→: on a dot, the catalogue on that side; on a line, the word.
            Key::ArrowLeft if m.alt => {
                let _ = self.voider.doc_alt_arrow(-1);
            }
            Key::ArrowRight if m.alt => {
                let _ = self.voider.doc_alt_arrow(1);
            }
            Key::ArrowUp => {
                let _ = self.voider.doc_navigate(-1);
            }
            Key::ArrowDown => {
                let _ = self.voider.doc_navigate(1);
            }
            Key::ArrowLeft if m.shift => self.voider.entry.extend_caret(-1),
            Key::ArrowRight if m.shift => self.voider.entry.extend_caret(1),
            Key::Home if m.shift => self.voider.entry.extend_home(),
            Key::End if m.shift => self.voider.entry.extend_end(),
            Key::ArrowLeft | Key::ArrowRight => self.wrap_caret(key),
            Key::Home => self.voider.doc_jump_edge(false),
            Key::End => self.voider.doc_jump_edge(true),
            Key::PageUp => self.voider.goto_dot(-1),
            Key::PageDown => self.voider.goto_dot(1),
            // Contextual: paragraph order on the leading dot, a paragraph's own
            // lines on any other dot, a random I/ fragment on a content line.
            // Shift+Tab: el fragmento viene del corpus (los libros del working
            // set en F7), no de tu propio libro.
            Key::Tab if m.shift => {
                let _ = self.voider.insert_random_ws_fragment();
            }
            Key::Tab => {
                let _ = self.voider.doc_tab();
            }
            // On the scratch this formats AND splits '/name' blocks out; on any
            // other file it just reformats into one sentence per line.
            Key::F if m.ctrl && m.shift => {
                if self.voider.current_file == self.voider.scratch_path() {
                    let _ = self.voider.split_scratch_into_docs();
                } else {
                    let _ = self.voider.reformat_file();
                }
            }
            Key::S if m.ctrl && m.shift => {
                let _ = self.voider.split_at_markers();
            }
            Key::R if m.ctrl && m.shift => {
                let _ = self.voider.shuffle_scratch();
            }
            // Give a fused scriptio-continua line its line breaks back: every
            // space becomes a break (on a dot: the whole paragraph).
            Key::E if m.ctrl && m.shift => {
                let _ = self.voider.doc_split_line_on_spaces();
            }
            // Send each '/name'-marked paragraph straight to its chapter,
            // leaving the rest of the file untouched.
            Key::D if m.ctrl && m.shift => {
                let _ = self.voider.dispatch_paragraphs();
            }
            Key::Escape if self.voider.para_focus => self.voider.exit_para_focus(),
            Key::Escape => self.voider.switch_to(View::F1),
            _ => {}
        }
    }

    fn handle_f3_key(&mut self, key: egui::Key, m: egui::Modifiers) {
        use egui::Key;
        // A search bar takes exclusive focus: only its own keys mean anything.
        if self.voider.f3_search.is_some() {
            match key {
                Key::ArrowUp => self.voider.f3_search_move(-1),
                Key::ArrowDown => self.voider.f3_search_move(1),
                Key::Enter => self.voider.f3_search_confirm(),
                Key::Escape => self.voider.f3_search_cancel(),
                Key::Backspace => self.voider.f3_search_backspace(),
                _ => {}
            }
            return;
        }
        let before = (self.voider.library.index, self.voider.library.current().to_string());
        match key {
            // Ctrl+F: search the library's chapters.
            Key::F if m.ctrl && !m.shift => self.voider.open_f3_search(),
            // Ctrl+Shift+F: juntar los 0.txt sueltos de subcarpetas en el scratch.
            Key::F if m.ctrl && m.shift => {
                let _ = self.voider.merge_stray_scratches();
            }
            // Ctrl+Shift+M on a separator: name and merge that book into one file.
            Key::M if m.ctrl && m.shift => self.voider.book_merge_prompt(),
            // Split the highlighted (not necessarily open) chapter at its markers.
            Key::S if m.ctrl && m.shift => {
                let _ = self.voider.book_split_current();
            }
            // Shift+Enter opens a blank entry to name; Enter confirms it, or
            // opens the highlighted chapter when we're just browsing. A pending
            // merge takes priority — it's naming a book, not a single chapter.
            // Shift+Enter and Ctrl+Enter both open a blank row to name, wherever
            // the caret is (Ctrl+Enter also works standing on the portal).
            Key::Enter if m.shift || m.ctrl => self.voider.begin_new_chapter(),
            Key::Enter if self.voider.pending_merge => {
                let _ = self.voider.book_do_merge();
            }
            // Caret at the start: settle the name / open what's highlighted.
            // Anywhere else (the end of a name): settle it and add a row below.
            Key::Enter if self.voider.entry.caret() > 0 => {
                let _ = self.voider.f3_enter_at_end();
            }
            Key::Enter => {
                if self.voider.pending_new {
                    let _ = self.voider.settle_pending();
                } else {
                    let _ = self.voider.f3_enter();
                }
            }
            Key::Escape if self.voider.pending_merge => self.voider.book_cancel_merge(),
            Key::Escape if self.voider.pending_new => self.voider.cancel_pending(),
            Key::Escape => self.voider.switch_to(View::F1),
            // Editing the line: the name being given, or the title (never a
            // separator or the portal).
            Key::Backspace if self.f3_editable() => {
                self.voider.entry.backspace();
            }
            Key::Delete if self.f3_editable() && !m.ctrl => {
                self.voider.entry.delete();
            }
            Key::ArrowLeft if m.shift => self.voider.entry.extend_caret(-1),
            Key::ArrowRight if m.shift => self.voider.entry.extend_caret(1),
            Key::ArrowLeft | Key::ArrowRight if !m.alt => self.wrap_caret(key),
            // Alt+Shift+↑/↓ duplicates the chapter, the copy going where the arrow
            // points. Before the plain arrows or they would just move the cursor.
            Key::ArrowUp if m.alt && m.shift => {
                let _ = self.voider.book_duplicate(-1);
            }
            Key::ArrowDown if m.alt && m.shift => {
                let _ = self.voider.book_duplicate(1);
            }
            // Alt+↑/↓: on a dot the whole book moves; on a chapter it swaps.
            Key::ArrowUp if m.alt => {
                let _ = self.voider.book_swap(-1);
            }
            Key::ArrowDown if m.alt => {
                let _ = self.voider.book_swap(1);
            }
            // Ctrl+0: the highlighted entry becomes the first of the library.
            Key::Num0 if m.ctrl => {
                let _ = self.voider.book_rebase();
            }
            // Ctrl+Delete at the start of the line: out of the library (to 0.txt,
            // or — on the trash — emptied). Anywhere else it is a word, as usual.
            Key::Delete if m.ctrl && self.voider.entry.caret() == 0 => {
                let _ = self.voider.book_send_to_zero();
            }
            Key::Delete if m.ctrl && self.f3_editable() => {
                self.voider.entry.delete_word_forward();
            }
            Key::Home if !m.shift => self.voider.f3_jump_edge(false),
            Key::End if !m.shift => self.voider.f3_jump_edge(true),
            Key::Home => self.voider.entry.extend_home(),
            Key::End => self.voider.entry.extend_end(),
            // Moving away settles a named entry and renames an edited title.
            Key::ArrowUp => self.voider.f3_move(-1),
            Key::ArrowDown => self.voider.f3_move(1),
            // PageUp/PageDown: the separator before / after — book by book.
            Key::PageUp => {
                let _ = self.voider.f3_leave_entry();
                self.voider.library.goto_dot(-1);
            }
            Key::PageDown => {
                let _ = self.voider.f3_leave_entry();
                self.voider.library.goto_dot(1);
            }
            // On a separator: shuffle that book. On a title: jump to a random one.
            Key::Tab => {
                let _ = self.voider.f3_leave_entry();
                let _ = self.voider.book_tab();
            }
            _ => {}
        }
        // Whatever moved the cursor (or changed the row under it), the line now
        // shows the new title.
        let after = (self.voider.library.index, self.voider.library.current().to_string());
        if after != before {
            self.voider.f3_sync_entry();
        }
    }

    /// The chapter catalogue owns the keyboard while it is open (F2 and F5):
    /// Escape or ← fold it back, Enter or → send (creating the chapter if the
    /// typed name is new), ↓/Tab and ↑/Shift+Tab cycle, Backspace unfilters.
    /// What is typed filters (see `route_text`).
    fn picker_key(&mut self, key: egui::Key, m: egui::Modifiers) {
        use egui::Key;
        match key {
            Key::Escape | Key::ArrowLeft => self.voider.picker_close(),
            Key::Enter | Key::ArrowRight => {
                let _ = self.voider.picker_confirm();
            }
            Key::Tab if m.shift => self.voider.picker_cycle(-1),
            Key::ArrowDown | Key::Tab => self.voider.picker_cycle(1),
            Key::ArrowUp => self.voider.picker_cycle(-1),
            Key::Backspace => self.voider.picker_backspace(),
            _ => {}
        }
    }

    /// ←/→ in a ring's line (F2, F3): one character — except that ← at the very
    /// start goes round to the end and → at the end back to the start, as the
    /// Python's line editor does.
    fn wrap_caret(&mut self, key: egui::Key) {
        let e = &mut self.voider.entry;
        let free = e.selection().is_none();
        match key {
            egui::Key::ArrowLeft if free && e.caret() == 0 => e.end(),
            egui::Key::ArrowRight if free && e.caret() == e.len() => e.home(),
            egui::Key::ArrowLeft => e.move_caret(-1),
            _ => e.move_caret(1),
        }
    }

    /// Whether Ctrl+Z means undo in the view you are in.
    fn undo_here(&self) -> bool {
        match self.voider.view {
            View::F1 | View::F2 | View::F5 => true,
            View::F3 => !self.voider.f3_mid_edit(),
            _ => false,
        }
    }

    /// Whether the F3 line takes editing keys now.
    fn f3_editable(&self) -> bool {
        let cur = self.voider.library.current();
        self.voider.pending_new
            || self.voider.pending_merge
            || !(library::is_separator(cur) || library::is_portal(cur))
    }

    fn handle_f5_key(&mut self, key: egui::Key, m: egui::Modifiers) {
        use egui::Key;
        // With the catalogue open, the keys belong to it.
        if self.voider.picker_open {
            self.picker_key(key, m);
            return;
        }
        match key {
            // Alt+Up/Down moves the paragraph; plain Up/Down walks them.
            Key::ArrowUp if m.alt => {
                let _ = self.voider.f5_swap(-1);
            }
            Key::ArrowDown if m.alt => {
                let _ = self.voider.f5_swap(1);
            }
            Key::ArrowUp => self.voider.f5_step(-1),
            Key::ArrowDown => self.voider.f5_step(1),
            Key::ArrowRight => self.voider.open_picker(),
            Key::Enter => self.voider.f5_to_f2(),
            Key::Escape => self.voider.switch_to(View::F1),
            _ => {}
        }
    }

    /// F10: ↑↓ walks the fonts (adopting each as you land on it, so you see it),
    /// ←→ the size. Escape goes back to writing.
    fn handle_f10_key(&mut self, key: egui::Key, m: egui::Modifiers) {
        use egui::Key;
        match key {
            // Tab steps the carousel's frame; Ctrl+arrows size a custom one.
            Key::Tab if m.shift => self.voider.settings_step_carousel(-1),
            Key::Tab => self.voider.settings_step_carousel(1),
            Key::ArrowLeft if m.ctrl => self.voider.settings_step_carousel_size(-1, 0),
            Key::ArrowRight if m.ctrl => self.voider.settings_step_carousel_size(1, 0),
            Key::ArrowUp if m.ctrl => self.voider.settings_step_carousel_size(0, 1),
            Key::ArrowDown if m.ctrl => self.voider.settings_step_carousel_size(0, -1),
            Key::ArrowUp => self.voider.settings_step_family(-1),
            Key::ArrowDown => self.voider.settings_step_family(1),
            Key::ArrowLeft => self.voider.settings_step_size(-1),
            Key::ArrowRight => self.voider.settings_step_size(1),
            Key::Escape | Key::Enter => self.voider.switch_to(View::F1),
            _ => {}
        }
    }

    /// F4 is for reading: turn pages, or leave.
    fn handle_f4_key(&mut self, key: egui::Key, m: egui::Modifiers) {
        use egui::Key;
        let pages = self.voider.f4_page_count(self.reading_pages).max(1);
        match key {
            Key::ArrowRight | Key::ArrowDown | Key::PageDown | Key::Space => {
                self.voider.turn_page(1, pages)
            }
            Key::ArrowLeft | Key::ArrowUp | Key::PageUp => self.voider.turn_page(-1, pages),
            // Ctrl+S guarda el libro como PDF; Ctrl+P además lo manda a imprimir.
            Key::S if m.ctrl => {
                self.voider.export_pdf();
            }
            Key::P if m.ctrl => self.voider.print_reading(),
            // V: switch between the book's pages and the carousel's slides. (Python has
            // Ctrl+Shift+V, but egui-winit turns that chord into a Paste event and sends
            // nothing at all when the clipboard is empty, so a bare key it is.)
            Key::V if !m.ctrl && !m.alt => self.voider.toggle_carousel_view(),
            // Ctrl+Shift+C: the book as Instagram slides; Ctrl+Shift+B: the same, with
            // a cover chosen first.
            Key::C if m.ctrl && m.shift => self.voider.begin_carousel(),
            Key::B if m.ctrl && m.shift => self.voider.begin_carousel_with_cover(),
            // Ctrl+Shift+A: PDF + EPUB + TXT together, ready to put up for sale.
            Key::A if m.ctrl && m.shift => self.voider.begin_sale_bundle(),
            Key::Home => self.voider.page = 0,
            Key::End => self.voider.page = pages - 1,
            Key::Escape => self.voider.switch_to(View::F2),
            _ => {}
        }
    }


    /// The whole book, read-only: ↑/↓ walk it, Enter or Escape back to F3.
    fn handle_concat_key(&mut self, key: egui::Key) {
        use egui::Key;
        match key {
            Key::ArrowUp => self.voider.concat_navigate(-1),
            Key::ArrowDown => self.voider.concat_navigate(1),
            Key::Enter | Key::Escape => self.voider.switch_to(View::F3),
            _ => {}
        }
    }

    /// The whole book as a ring: the line you are on lit, the rest dimmed on
    /// the ring's curve, as F2 shows a document — but nothing here is edited.
    fn draw_concat(&self, painter: &egui::Painter, ctx: &egui::Context, rect: egui::Rect) {
        let centre = rect.center();
        let font = egui::FontId::proportional(self.font_size());
        let line_h = self.ring_line_h(ctx, &font);
        let reach = (rect.height() / 2.0 / line_h).ceil() as isize;
        let ring = &self.voider.concat;
        for offset in -reach..=reach {
            let text = ring.get(offset);
            if text.is_empty() {
                continue;
            }
            let alpha = if offset == 0 {
                255
            } else {
                ring::to_u8(ring::edit_line_alpha(
                    offset,
                    offset.unsigned_abs() as f32 * line_h,
                    rect.height() / 2.0,
                    false,
                    0,
                ))
            };
            if alpha == 0 {
                continue;
            }
            painter.text(
                egui::pos2(centre.x, centre.y + offset as f32 * line_h),
                egui::Align2::CENTER_CENTER,
                text,
                font.clone(),
                white_alpha(alpha),
            );
        }
    }

    /// F6, el lector del corpus: moverse por el libro y salir.
    fn handle_f6_key(&mut self, key: egui::Key) {
        use egui::Key;
        match key {
            Key::ArrowUp => self.voider.o_navigate(-1),
            Key::ArrowDown => self.voider.o_navigate(1),
            Key::PageUp => self.voider.o_navigate(-10),
            Key::PageDown => self.voider.o_navigate(10),
            // Volver al working set, que es de donde se viene.
            Key::Escape => self.voider.switch_to(View::F7),
            _ => {}
        }
    }

    /// F7, el working set: sortear, agregar, sacar, abrir.
    fn handle_f7_key(&mut self, key: egui::Key, m: egui::Modifiers) {
        use egui::Key;
        match key {
            Key::ArrowUp => self.voider.ws_move(-2),
            Key::ArrowDown => self.voider.ws_move(2),
            // Tab llena la ranura con un libro que no esté ya en otra.
            Key::Tab => self.voider.ws_tab(),
            Key::Enter if m.shift => self.voider.ws_add_slot(),
            Key::Delete if m.ctrl => self.voider.ws_remove_slot(),
            Key::Enter => {
                if self.voider.open_o_book() {
                    self.voider.switch_to(View::F6);
                }
            }
            Key::Escape => self.voider.switch_to(View::F1),
            _ => {}
        }
    }

    /// F8, el oráculo: cada movimiento es una tirada nueva; Enter se la queda.
    fn handle_f8_key(&mut self, key: egui::Key) {
        use egui::Key;
        match key {
            Key::ArrowUp | Key::ArrowDown | Key::Tab => {
                self.voider.tts.cut();
                self.voider.refresh_oracle();
            }
            Key::Enter => {
                let _ = self.voider.keep_oracle_line();
            }
            Key::Escape => self.voider.switch_to(View::F1),
            _ => {}
        }
    }
    /// F9 leaves editing to the widget: only Ctrl+S (save without leaving) and
    /// Escape (back to F2, where save-on-leave does the writing) are ours.
    fn handle_f9_key(&mut self, key: egui::Key, m: egui::Modifiers) {
        use egui::Key;
        match key {
            Key::S if m.ctrl => {
                let _ = self.voider.prose_save();
            }
            Key::Escape => self.voider.switch_to(View::F2),
            _ => {}
        }
    }

    // ── drawing ───────────────────────────────────────────────────────────────

    /// Lay out the entry and draw it with our own caret. `anchor_caret` pins the
    /// caret to the centre (typewriter) instead of centring the whole line.
    fn draw_entry_line(
        &self,
        painter: &egui::Painter,
        ctx: &egui::Context,
        centre: egui::Pos2,
        clip: egui::Rect,
        anchor_caret: bool,
    ) {
        let font = egui::FontId::proportional(self.font_size());
        let text = self.voider.entry.text();
        let before = self.voider.entry.before_caret();
        let galley =
            ctx.fonts(|f| f.layout_no_wrap(text, font.clone(), egui::Color32::WHITE));
        let before_w =
            ctx.fonts(|f| f.layout_no_wrap(before, font, egui::Color32::WHITE).size().x);

        let size = galley.size();
        let left_x = if anchor_caret {
            centre.x - before_w
        } else {
            centre.x - size.x / 2.0
        };
        let top_y = centre.y - size.y / 2.0;

        let p = painter.with_clip_rect(clip);
        // A selection is a pale band behind the letters.
        if let Some((s, e)) = self.voider.entry.selection() {
            let chars: Vec<char> = self.voider.entry.text().chars().collect();
            let width_of = |n: usize| {
                let t: String = chars[..n].iter().collect();
                ctx.fonts(|f| {
                    f.layout_no_wrap(t, egui::FontId::proportional(self.font_size()), egui::Color32::WHITE)
                        .size()
                        .x
                })
            };
            let band = egui::Rect::from_min_max(
                egui::pos2(left_x + width_of(s), top_y),
                egui::pos2(left_x + width_of(e), top_y + size.y),
            );
            p.rect_filled(band, 2.0, white_alpha(70));
        }
        p.galley(egui::pos2(left_x, top_y), galley, egui::Color32::WHITE);

        // The caret blinks only while the line is empty; once there is text it
        // holds still, so the last letter typed is the thing you look at.
        let blinking = self.voider.entry.is_empty();
        let visible = !blinking || (ctx.input(|i| i.time) * 1.6).sin() > 0.0;
        if visible {
            let x = left_x + before_w;
            p.line_segment(
                [
                    egui::pos2(x, top_y + 2.0),
                    egui::pos2(x, top_y + size.y - 2.0),
                ],
                egui::Stroke::new(2.0_f32, egui::Color32::WHITE),
            );
        }
        if blinking {
            ctx.request_repaint_after(std::time::Duration::from_millis(120));
        }
    }

    fn draw_f1(&self, painter: &egui::Painter, ctx: &egui::Context, rect: egui::Rect) {
        let centre = rect.center();
        let radius = rect.width().min(rect.height()) / 2.0 - CIRCLE_INSET;
        painter.circle_stroke(
            centre,
            radius,
            egui::Stroke::new(10.0_f32, egui::Color32::WHITE),
        );
        // Nothing may show outside the circle.
        let band = egui::Rect::from_min_max(
            egui::pos2(centre.x - radius, rect.top()),
            egui::pos2(centre.x + radius, rect.bottom()),
        );
        self.draw_entry_line(painter, ctx, centre, band, self.voider.typewriter);
    }

    /// The document as a ring: the current line centred and lit, the rest fading
    /// away above and below.
    /// A small bar near the top: the query typed so far, or a placeholder.
    fn draw_search_bar(&self, painter: &egui::Painter, rect: egui::Rect, query: &str, placeholder: &str) {
        let shown = if query.is_empty() { placeholder } else { query };
        let color = if query.is_empty() {
            egui::Color32::from_gray(120)
        } else {
            egui::Color32::WHITE
        };
        painter.text(
            egui::pos2(rect.center().x, rect.top() + self.font_size() * 2.0),
            egui::Align2::CENTER_CENTER,
            shown,
            egui::FontId::proportional(self.font_size() * 0.55),
            color,
        );
    }

    fn draw_f2(&self, painter: &egui::Painter, ctx: &egui::Context, rect: egui::Rect) {
        // Con el panel desplegado (38%, como en Python) el texto se corre al
        // otro lado: la flecha con que lo abriste decide de qué lado sale.
        let full = rect;
        let panel_w = if self.voider.picker_open { (rect.width() * 0.38).floor() } else { 0.0 };
        let left = self.voider.picker_side == app::PickerSide::Left;
        let rect = if left {
            egui::Rect::from_min_max(egui::pos2(rect.min.x + panel_w, rect.min.y), rect.max)
        } else {
            egui::Rect::from_min_max(rect.min, egui::pos2(rect.max.x - panel_w, rect.max.y))
        };
        let centre = rect.center();
        let font = egui::FontId::proportional(self.font_size());
        let line_h = self.ring_line_h(ctx, &font);
        let reach = (rect.height() / 2.0 / line_h).ceil() as isize;

        if let Some(search) = &self.voider.f2_search {
            let m = search.matches.len() as isize;
            for offset in -reach..=reach {
                if m == 0 {
                    continue;
                }
                let idx = (search.highlight as isize + offset).rem_euclid(m) as usize;
                let text = self.voider.ring.lines[search.matches[idx]].as_str();
                if text.is_empty() {
                    continue;
                }
                // The chosen line is full; every other is the ring's curve, dimmed.
                let alpha = ring::to_u8(ring::edit_line_alpha(
                    offset,
                    offset.unsigned_abs() as f32 * line_h,
                    rect.height() / 2.0,
                    false,
                    0,
                ));
                if alpha == 0 {
                    continue;
                }
                painter.text(
                    egui::pos2(centre.x, centre.y + offset as f32 * line_h),
                    egui::Align2::CENTER_CENTER,
                    text,
                    font.clone(),
                    white_alpha(alpha),
                );
            }
            if m == 0 {
                painter.text(
                    centre,
                    egui::Align2::CENTER_CENTER,
                    "—",
                    font.clone(),
                    egui::Color32::from_gray(90),
                );
            }
            self.draw_search_bar(painter, rect, &search.query.text(), "search lines…");
            return;
        }

        // Standing on a dot, the paragraph it opens stays lit and the rest dims.
        let on_dot = self.voider.ring.current() == ".";
        let para_size = if on_dot {
            self.voider.ring.lines.iter().skip(self.voider.ring.index + 1).take_while(|l| *l != ".").count()
        } else {
            0
        };
        for offset in -reach..=reach {
            if offset == 0 {
                continue; // the centred line is the editable entry, drawn below
            }
            let text = self.voider.ring.get(offset);
            if text.is_empty() {
                continue;
            }
            let alpha = ring::to_u8(ring::edit_line_alpha(
                offset,
                offset.unsigned_abs() as f32 * line_h,
                rect.height() / 2.0,
                on_dot,
                para_size,
            ));
            if alpha == 0 {
                continue;
            }
            let y = centre.y + offset as f32 * line_h;
            painter.text(
                egui::pos2(centre.x, y),
                egui::Align2::CENTER_CENTER,
                text,
                font.clone(),
                white_alpha(alpha),
            );
        }
        self.draw_entry_line(painter, ctx, centre, rect, self.voider.typewriter);
        if self.voider.picker_open {
            let x = if left { full.min.x } else { rect.max.x };
            self.draw_picker(painter, ctx, x, panel_w, full, false);
        }
    }

    /// The library: chapter titles in reading order, the current one centred.
    /// Separators show as a dot; the naming of a new entry happens in place.
    fn draw_f3(&self, painter: &egui::Painter, ctx: &egui::Context, rect: egui::Rect) {
        let centre = rect.center();
        let font = egui::FontId::proportional(self.font_size());
        let line_h = self.ring_line_h(ctx, &font);
        let lib = &self.voider.library;
        let reach = (rect.height() / 2.0 / line_h).ceil() as isize;
        let n = lib.entries.len() as isize;

        if let Some(search) = &self.voider.f3_search {
            let m = search.matches.len() as isize;
            for offset in -reach..=reach {
                if m == 0 {
                    continue;
                }
                let idx = (search.highlight as isize + offset).rem_euclid(m) as usize;
                let label = library::display_name(&lib.entries[search.matches[idx]]);
                // The chosen line is full; every other is the ring's curve, dimmed.
                let alpha = ring::to_u8(ring::edit_line_alpha(
                    offset,
                    offset.unsigned_abs() as f32 * line_h,
                    rect.height() / 2.0,
                    false,
                    0,
                ));
                if alpha == 0 {
                    continue;
                }
                painter.text(
                    egui::pos2(centre.x, centre.y + offset as f32 * line_h),
                    egui::Align2::CENTER_CENTER,
                    label,
                    font.clone(),
                    white_alpha(alpha),
                );
            }
            if m == 0 {
                painter.text(
                    centre,
                    egui::Align2::CENTER_CENTER,
                    "—",
                    font.clone(),
                    egui::Color32::from_gray(90),
                );
            }
            self.draw_search_bar(painter, rect, &search.query.text(), "search files…");
            return;
        }

        if n > 0 {
            for offset in -reach..=reach {
                if offset == 0 {
                    continue; // the centre is the editable line, drawn below
                }
                let i = (lib.index as isize + offset).rem_euclid(n) as usize;
                let label = library::display_name(&lib.entries[i]);
                // The chosen line is full; every other is the ring's curve, dimmed.
                let alpha = ring::to_u8(ring::edit_line_alpha(
                    offset,
                    offset.unsigned_abs() as f32 * line_h,
                    rect.height() / 2.0,
                    false,
                    0,
                ));
                if alpha == 0 {
                    continue;
                }
                painter.text(
                    egui::pos2(centre.x, centre.y + offset as f32 * line_h),
                    egui::Align2::CENTER_CENTER,
                    label,
                    font.clone(),
                    white_alpha(alpha),
                );
            }
        }
        // The centre is the line you edit, as in the Python's book_view: the
        // title (or `.` / `0`), or the name being given.
        self.draw_entry_line(painter, ctx, centre, rect, false);
    }

    /// Paragraphs in order, the current one centred and lit, drawn outward from
    /// it and stopped at the screen edges — only what's visible is ever laid out,
    /// so a scratch of thousands of paragraphs stays instant.
    fn draw_f5(&self, painter: &egui::Painter, ctx: &egui::Context, rect: egui::Rect) {
        let units = f5::units(&self.voider.ring.lines);
        if units.is_empty() {
            painter.text(
                rect.center(),
                egui::Align2::CENTER_CENTER,
                "ø",
                egui::FontId::proportional(48.0),
                egui::Color32::from_gray(45),
            );
            return;
        }
        // The catalogue takes the right third when open.
        let panel_w = if self.voider.picker_open { rect.width() * 0.38 } else { 0.0 };
        let col = egui::Rect::from_min_max(
            rect.min,
            egui::pos2(rect.max.x - panel_w, rect.max.y),
        );
        let pad = (col.width() * 0.14).max(48.0);
        let text_w = col.width() - 2.0 * pad;
        let font = egui::FontId::proportional(self.font_size());
        // F5 packs its rows 1.5 × the font's height apart (`reorder_view.py`).
        let row_h = ctx.fonts(|f| f.row_height(&font));
        let lh = (row_h * 1.5).floor();
        // Qt centres the text in its 1.5-high row; egui sets it at the top of it.
        let lead = (lh - row_h) / 2.0;

        let cur = units
            .iter()
            .position(|u| matches!(u, f5::Unit::Para { ordinal, .. } if *ordinal == self.voider.para_idx))
            .unwrap_or(0);

        // Centred and tight, as F2 packs its ring: a unit is as tall as its
        // wrapped lines and nothing more — the `.` separator unit IS the room
        // between groups. Whatever is not the current paragraph fades with its
        // distance from the centre, on the same curve F2 uses.
        let lay = |u: &f5::Unit| {
            let text = match u {
                f5::Unit::Para { text, .. } => text.clone(),
                f5::Unit::Mark { name } => format!("/{name}"),
                f5::Unit::Sep => ".".to_string(),
            };
            centered_galley(ctx, text, font.clone(), text_w, Some(lh))
        };
        let alpha_at = |unit_centre_y: f32| -> u8 {
            let dist = (unit_centre_y - col.center().y).abs();
            ring::to_u8(ring::ring_alpha(dist, col.height() / 2.0) * ring::DIM_FACTOR)
        };
        let x = col.center().x; // rows are centred on the galley's origin

        let here = lay(&units[cur]);
        let cur_top = col.center().y - here.size().y / 2.0;
        painter.galley_with_override_text_color(egui::pos2(x, cur_top + lead), here.clone(), egui::Color32::WHITE);
        // The '>' cue: Right opens the catalogue to send this paragraph.
        painter.text(
            egui::pos2(col.max.x - pad / 2.0, cur_top + here.size().y / 2.0),
            egui::Align2::CENTER_CENTER,
            ">",
            font.clone(),
            egui::Color32::WHITE,
        );

        let mut y = cur_top + here.size().y;
        for u in &units[cur + 1..] {
            if y > col.max.y {
                break;
            }
            let g = lay(u);
            let h = g.size().y;
            let a = alpha_at(y + h / 2.0);
            if a > 0 {
                painter.galley_with_override_text_color(egui::pos2(x, y + lead), g, white_alpha(a));
            }
            y += h;
        }
        let mut top = cur_top;
        for u in units[..cur].iter().rev() {
            let g = lay(u);
            let h = g.size().y;
            top -= h;
            if top + h < col.min.y {
                break;
            }
            let a = alpha_at(top + h / 2.0);
            if a > 0 {
                painter.galley_with_override_text_color(egui::pos2(x, top + lead), g, white_alpha(a));
            }
        }

        if self.voider.picker_open {
            self.draw_picker(painter, ctx, col.max.x, panel_w, rect, true);
        }
    }

    /// The chapter catalogue — the Python's `widgets.draw_chapter_picker`, shared
    /// by F2 and F5: the same font and line spacing as the ring, the same curve
    /// dimmed by 0.3 off the lit row, the filter typed so far at the top (or a
    /// hint to type), the keys at the bottom, `⏎ crear <name>` when nothing
    /// matches what was typed, and `ø` when there is nothing to show.
    fn draw_picker(&self, painter: &egui::Painter, ctx: &egui::Context, x: f32, w: f32, rect: egui::Rect, divider: bool) {
        if divider {
            painter.line_segment(
                [egui::pos2(x, rect.top()), egui::pos2(x, rect.bottom())],
                egui::Stroke::new(1.0_f32, egui::Color32::from_gray(40)),
            );
        }
        let font = egui::FontId::proportional(self.font_size());
        let lh = self.ring_line_h(ctx, &font);
        let pad = 16.0;
        let text_w = (w - 2.0 * pad).max(1.0);
        let cx = x + w / 2.0;
        let cy = rect.center().y;
        let half = rect.height() / 2.0;
        let row = |text: &str, dy: f32, alpha: f32| {
            let shown = elide(ctx, text, &font, text_w);
            painter.text(
                egui::pos2(cx, cy + dy),
                egui::Align2::CENTER_CENTER,
                shown,
                font.clone(),
                white_alpha(ring::to_u8(alpha)),
            );
        };
        let target = self.voider.picker_target();
        let (rows, lit) = self.voider.picker_rows();
        if target.as_ref().is_some_and(|t| t.is_new) && !self.voider.picker_filter.trim().is_empty() {
            row(&format!("⏎ crear  {}", target.unwrap().display), 0.0, 1.0);
        } else if !rows.is_empty() {
            let visible = ((rect.height() / lh) as usize).max(1);
            let first = lit.saturating_sub(visible / 2);
            for j in first..rows.len().min(first + visible) {
                let dy = (j as f32 - lit as f32) * lh;
                let a = if j == lit { 1.0 } else { ring::ring_alpha(dy.abs(), half) * ring::DIM_FACTOR };
                row(&rows[j], dy, a);
            }
        } else {
            row("ø", 0.0, 0.35);
        }
        let prompt = if self.voider.picker_filter.is_empty() {
            "escribí para filtrar…".to_string()
        } else {
            format!("{}▏", self.voider.picker_filter)
        };
        let top = rect.top() + pad + lh / 2.0;
        painter.text(
            egui::pos2(cx, top),
            egui::Align2::CENTER_CENTER,
            elide(ctx, &prompt, &font, text_w),
            font.clone(),
            white_alpha(ring::to_u8(0.45)),
        );
        painter.text(
            egui::pos2(cx, rect.bottom() - 34.0 + 11.0),
            egui::Align2::CENTER_CENTER,
            elide(ctx, "→ enviar   ⏎ nuevo   ⇥ ciclar", &font, text_w),
            font.clone(),
            white_alpha(ring::to_u8(0.30)),
        );
    }

    /// The settings: the families this machine has, the current one lit, and the
    /// size — all drawn in the font itself, so choosing is seeing.
    fn draw_f10(&self, painter: &egui::Painter, rect: egui::Rect) {
        let families = self.voider.font_families();
        let centre = rect.center();
        let line_h = self.font_size() * 1.6;
        let font = egui::FontId::proportional(self.font_size());
        let cur = self.voider.settings_idx.min(families.len().saturating_sub(1));
        let reach = (rect.height() / 2.5 / line_h).ceil() as isize;

        for d in -reach..=reach {
            let i = cur as isize + d;
            if i < 0 || i as usize >= families.len() {
                continue;
            }
            let colour = if d == 0 {
                egui::Color32::WHITE
            } else {
                let fade = (1.0 - (d.unsigned_abs() as f32 / 6.0)).clamp(0.0, 1.0);
                white_alpha((fade * fade * 190.0) as u8)
            };
            painter.text(
                egui::pos2(centre.x, centre.y + d as f32 * line_h),
                egui::Align2::CENTER_CENTER,
                &families[i as usize],
                font.clone(),
                colour,
            );
        }
        painter.text(
            egui::pos2(centre.x, rect.bottom() - 70.0),
            egui::Align2::CENTER_CENTER,
            format!("←  {}  →", self.voider.config.font_size as i32),
            egui::FontId::proportional(self.font_size()),
            egui::Color32::from_gray(200),
        );
        // The carousel's frame, with the size it comes to.
        let (fw, fh) = self.voider.carousel_size();
        painter.text(
            egui::pos2(centre.x, rect.bottom() - 112.0),
            egui::Align2::CENTER_CENTER,
            format!("carrusel  ‹ {} ›  {fw}×{fh}", self.voider.config.carousel_preset),
            egui::FontId::proportional(14.0),
            egui::Color32::from_gray(150),
        );
        painter.text(
            egui::pos2(centre.x, rect.bottom() - 28.0),
            egui::Align2::CENTER_CENTER,
            "↑↓ fuente   ←→ tamaño   Tab carrusel   Ctrl+flechas medida propia   Enter volver",
            egui::FontId::proportional(12.0),
            egui::Color32::from_gray(70),
        );
    }

    /// F9: the active file as one column of editable prose. Generous margins,
    /// the same writing font, no visible scrollbar — a page, not a text box.
    fn draw_f9(&mut self, ui: &mut egui::Ui, rect: egui::Rect) {
        let margin = (rect.width() * 0.22).max(60.0);
        let inner = egui::Rect::from_min_max(
            egui::pos2(rect.min.x + margin, rect.min.y + 56.0),
            egui::pos2(rect.max.x - margin, rect.max.y - 56.0),
        );
        let font = egui::FontId::proportional(self.font_size());
        let edit_id = egui::Id::new("f9_prose");
        // Entering F9 parks the caret on the paragraph you were in, once.
        if let Some(off) = self.voider.prose_caret.take() {
            let mut state = egui::TextEdit::load_state(ui.ctx(), edit_id).unwrap_or_default();
            state
                .cursor
                .set_char_range(Some(egui::text::CCursorRange::one(egui::text::CCursor::new(off))));
            egui::TextEdit::store_state(ui.ctx(), edit_id, state);
        }
        let mut buffer = self.voider.prose.clone();

        let mut child = ui.new_child(egui::UiBuilder::new().max_rect(inner));
        egui::ScrollArea::vertical()
            .auto_shrink([false, false])
            .scroll_bar_visibility(egui::scroll_area::ScrollBarVisibility::AlwaysHidden)
            .show(&mut child, |ui| {
                let edit = egui::TextEdit::multiline(&mut buffer)
                    .id(edit_id)
                    .frame(false)
                    .desired_width(f32::INFINITY)
                    .font(font)
                    .text_color(egui::Color32::from_gray(225));
                let response = ui.add_sized([ui.available_width(), ui.available_height()], edit);
                // Keep the caret in the prose without the user having to click.
                if !response.has_focus() {
                    response.request_focus();
                }
            });

        // Routed through set_prose so an untouched visit stays clean and saves
        // nothing when you leave.
        self.voider.set_prose(&buffer);
    }

    /// The question Ctrl+B asks before writing anything: which drive, how much,
    /// and what it will not follow. Deliberately plain — this is the last look
    /// before the void leaves the machine.
    fn draw_backup_prompt(&self, painter: &egui::Painter, rect: egui::Rect) {
        let Some(prompt) = &self.voider.backup_prompt else {
            return;
        };
        painter.rect_filled(rect, 0.0, egui::Color32::from_black_alpha(242));
        let centre = rect.center();
        let plan = &prompt.plan;

        painter.text(
            egui::pos2(centre.x, centre.y - 70.0),
            egui::Align2::CENTER_CENTER,
            "BACKUP",
            egui::FontId::proportional(self.font_size() * 0.9),
            egui::Color32::from_gray(235),
        );
        painter.text(
            egui::pos2(centre.x, centre.y - 24.0),
            egui::Align2::CENTER_CENTER,
            plan.dest().display().to_string(),
            egui::FontId::monospace(13.0),
            egui::Color32::WHITE,
        );
        painter.text(
            egui::pos2(centre.x, centre.y + 6.0),
            egui::Align2::CENTER_CENTER,
            format!(
                "{} archivos · {}",
                plan.files.len(),
                backup::human_bytes(plan.total_bytes())
            ),
            egui::FontId::proportional(14.0),
            egui::Color32::from_gray(170),
        );
        if !plan.skipped_links.is_empty() {
            let names: Vec<String> = plan
                .skipped_links
                .iter()
                .map(|p| p.to_string_lossy().to_string())
                .collect();
            painter.text(
                egui::pos2(centre.x, centre.y + 32.0),
                egui::Align2::CENTER_CENTER,
                format!("sin seguir: {}", names.join(", ")),
                egui::FontId::proportional(12.0),
                egui::Color32::from_gray(110),
            );
        }
        let hint = if prompt.drives.len() > 1 {
            format!(
                "Enter copiar   ↑↓ otro destino ({}/{})   cualquier otra tecla cancela",
                prompt.idx + 1,
                prompt.drives.len()
            )
        } else {
            "Enter copiar   ·   cualquier otra tecla cancela".to_string()
        };
        painter.text(
            egui::pos2(centre.x, centre.y + 74.0),
            egui::Align2::CENTER_CENTER,
            hint,
            egui::FontId::proportional(12.0),
            egui::Color32::from_gray(95),
        );
    }

    /// The sale-bundle question: the name of the book (a whole book has no single
    /// title), then its language. Plain on purpose, like the backup's — it is about
    /// to write three files, possibly into the site's own folders.
    fn draw_bundle_prompt(&self, painter: &egui::Painter, rect: egui::Rect) {
        let Some(p) = &self.voider.bundle_prompt else {
            return;
        };
        painter.rect_filled(rect, 0.0, egui::Color32::from_black_alpha(242));
        let centre = rect.center();
        painter.text(
            egui::pos2(centre.x, centre.y - 70.0),
            egui::Align2::CENTER_CENTER,
            match p.kind {
                app::PromptKind::Bundle => "BUNDLE DE VENTA · PDF + EPUB + TXT",
                app::PromptKind::Carousel => "CARRUSEL · SLIDES PARA INSTAGRAM",
                app::PromptKind::CarouselCover(_) => "CARRUSEL CON PORTADA",
            },
            egui::FontId::proportional(self.font_size() * 0.7),
            egui::Color32::from_gray(235),
        );
        match p.stage {
            app::BundleStage::Name => {
                painter.text(
                    egui::pos2(centre.x, centre.y - 24.0),
                    egui::Align2::CENTER_CENTER,
                    "Nombre para la carpeta del libro:",
                    egui::FontId::proportional(14.0),
                    egui::Color32::from_gray(150),
                );
                painter.text(
                    egui::pos2(centre.x, centre.y + 14.0),
                    egui::Align2::CENTER_CENTER,
                    format!("{}▏", p.name),
                    egui::FontId::proportional(self.font_size() * 0.8),
                    egui::Color32::WHITE,
                );
                painter.text(
                    egui::pos2(centre.x, centre.y + 74.0),
                    egui::Align2::CENTER_CENTER,
                    if p.kind == app::PromptKind::Bundle {
                        "Enter seguir   ·   Esc cancela"
                    } else {
                        "Enter exportar   ·   Esc cancela"
                    },
                    egui::FontId::proportional(12.0),
                    egui::Color32::from_gray(95),
                );
            }
            app::BundleStage::Lang => {
                painter.text(
                    egui::pos2(centre.x, centre.y - 36.0),
                    egui::Align2::CENTER_CENTER,
                    format!("«{}» — idioma del libro:", p.name),
                    egui::FontId::proportional(14.0),
                    egui::Color32::from_gray(150),
                );
                for (i, l) in bundle::Lang::ALL.iter().enumerate() {
                    let lit = *l == p.lang;
                    painter.text(
                        egui::pos2(centre.x, centre.y + 4.0 + i as f32 * 30.0),
                        egui::Align2::CENTER_CENTER,
                        l.label(),
                        egui::FontId::proportional(self.font_size() * 0.8),
                        if lit { egui::Color32::WHITE } else { egui::Color32::from_gray(80) },
                    );
                }
                painter.text(
                    egui::pos2(centre.x, centre.y + 90.0),
                    egui::Align2::CENTER_CENTER,
                    "Enter exportar   ↑↓ idioma   ·   Esc cancela",
                    egui::FontId::proportional(12.0),
                    egui::Color32::from_gray(95),
                );
            }
        }
    }

    /// F4: the text set in a column and shown a page at a time.
    ///
    /// The whole thing is laid out once as one tall column; a page is a window
    /// onto it, chosen so no line is ever cut across the break. Titles bind to
    /// what follows them, which is why they are measured into the same column
    /// rather than drawn separately.
    fn draw_f4(&mut self, painter: &egui::Painter, ctx: &egui::Context, rect: egui::Rect) {
        if self.voider.carousel_view {
            self.draw_f4_carousel(painter, ctx, rect);
            return;
        }
        if self.voider.reading.is_empty() {
            self.reading_pages = 1;
            return;
        }

        // The page: A5, as large as fits inside 94 % of the window, centred — the
        // Python's `min(W / page_w, H / page_h) * 0.94`. It is drawn at the pixels
        // it will occupy, so the type is as sharp as the screen allows.
        let ppp = ctx.pixels_per_point();
        let ratio = 148.0 / 210.0;
        let page_h = (rect.height() * 0.94).min(rect.width() * 0.94 / ratio);
        let page_w = page_h * ratio;
        let w = ((page_w * ppp).round() as u32).max(1);
        let h = (w as f32 / ratio).round() as u32;
        let key: BookKey = (w, h, self.voider.reading_serial);

        if self.carousel_font.is_none() {
            self.carousel_font = Some(self.voider.type_font());
        }
        if self.book_plan.as_ref().map(|c| c.key) != Some(key) {
            let sections: Vec<(String, Vec<String>)> = self
                .voider
                .reading
                .iter()
                .map(|s| (s.name.clone(), s.lines.clone()))
                .collect();
            let font = self.carousel_font.as_ref().expect("loaded above");
            self.book_plan = Some(BookPlanCache { key, plan: slides::book_plan(&sections, font, w, h) });
            self.book_tex = None;
        }
        let plan = &self.book_plan.as_ref().expect("planned above").plan;
        let total = plan.pages.len().max(1);
        self.reading_pages = total;

        // Opening on the paragraph you were editing: only on the frame we arrive,
        // so turning pages afterwards isn't undone.
        if self.voider.page == 0 && self.voider.open_at_para > 0 {
            if let Some(&page) = plan.para_page.get(self.voider.open_at_para) {
                self.voider.page = page;
            }
            self.voider.open_at_para = 0;
        }
        let page = self.voider.page.min(total - 1);
        let Some(book_page) = plan.pages.get(page).cloned() else {
            return;
        };

        if self.book_tex.as_ref().map(|t| (t.key, t.page)) != Some((key, page)) {
            let font = self.carousel_font.as_ref().expect("loaded above");
            let canvas = slides::render_book_page(&book_page, font, w, h, slides::BOOK_PAPER, slides::BOOK_INK);
            let image = egui::ColorImage::from_rgb([w as usize, h as usize], canvas.rgb());
            let tex = ctx.load_texture("book-page", image, egui::TextureOptions::LINEAR);
            self.book_tex = Some(BookTex { key, page, tex });
        }
        let Some(cached) = &self.book_tex else {
            return;
        };
        let image_rect = egui::Rect::from_center_size(rect.center(), egui::vec2(w as f32 / ppp, h as f32 / ppp));
        painter.image(
            cached.tex.id(),
            image_rect,
            egui::Rect::from_min_max(egui::pos2(0.0, 0.0), egui::pos2(1.0, 1.0)),
            egui::Color32::WHITE,
        );
        if total > 1 {
            painter.text(
                egui::pos2(rect.center().x, rect.top() + 12.0),
                egui::Align2::CENTER_CENTER,
                format!("{} / {}", page + 1, total),
                egui::FontId::proportional(11.0),
                egui::Color32::from_gray(80),
            );
        }
    }

    /// F4 previewing the carousel: the slide that would be written, as it would
    /// be written — drawn into a texture by the same code the export uses — fitted
    /// to the window with its own proportions.
    fn draw_f4_carousel(&mut self, painter: &egui::Painter, ctx: &egui::Context, rect: egui::Rect) {
        let total = self.voider.carousel_slides.len();
        self.reading_pages = total.max(1);
        if total == 0 {
            return;
        }
        let page = self.voider.page.min(total - 1);
        let slide = self.voider.carousel_slides[page].clone();
        let (w, h) = self.voider.carousel_size();

        let stale = match &self.carousel_tex {
            Some(c) => c.slide != slide || c.size != (w, h),
            None => true,
        };
        if stale {
            let font = self
                .carousel_font
                .get_or_insert_with(|| self.voider.type_font());
            let canvas = slides::render_slide(&slide, font, w, h);
            let image = egui::ColorImage::from_rgb([w as usize, h as usize], canvas.rgb());
            let tex = ctx.load_texture("carousel-slide", image, egui::TextureOptions::LINEAR);
            self.carousel_tex = Some(CarouselTex { slide, size: (w, h), tex });
        }
        let Some(cached) = &self.carousel_tex else {
            return;
        };

        // Fit inside the window, leaving a little air, keeping the slide's own shape.
        let room = egui::vec2(rect.width() * 0.92, rect.height() * 0.88);
        let scale = (room.x / w as f32).min(room.y / h as f32);
        let shown = egui::vec2(w as f32 * scale, h as f32 * scale);
        let image_rect = egui::Rect::from_center_size(rect.center(), shown);
        painter.image(
            cached.tex.id(),
            image_rect,
            egui::Rect::from_min_max(egui::pos2(0.0, 0.0), egui::pos2(1.0, 1.0)),
            egui::Color32::WHITE,
        );
        painter.rect_stroke(image_rect, 0.0, egui::Stroke::new(1.0_f32, egui::Color32::from_gray(45)));
        if total > 1 {
            // At the top: the bottom edge belongs to the status line.
            painter.text(
                egui::pos2(rect.center().x, rect.top() + 18.0),
                egui::Align2::CENTER_CENTER,
                format!("{} / {}", page + 1, total),
                egui::FontId::proportional(11.0),
                egui::Color32::from_gray(80),
            );
        }
    }

    /// Un anillo de líneas centrado, con la del medio encendida y las demás
    /// apagándose hacia los bordes. Es la forma que ya tienen F2 y F3; F6 y F7
    /// la comparten porque son la misma idea sobre otro contenido.
    fn draw_ring(
        &self,
        painter: &egui::Painter,
        ctx: &egui::Context,
        rect: egui::Rect,
        lines: &[String],
        index: usize,
        vacio: &str,
    ) {
        let centre = rect.center();
        let font = egui::FontId::proportional(self.font_size());
        let line_h = self.ring_line_h(ctx, &font);
        let n = lines.len() as isize;
        if n == 0 {
            painter.text(
                centre,
                egui::Align2::CENTER_CENTER,
                vacio,
                font,
                egui::Color32::from_gray(70),
            );
            return;
        }
        let reach = (rect.height() / 2.0 / line_h).ceil() as isize;
        for offset in -reach..=reach {
            let i = (index as isize + offset).rem_euclid(n) as usize;
            let text = lines[i].as_str();
            if text.is_empty() {
                continue;
            }
            // Reading rings (F6, F7) are not being edited: the whole ring follows
            // the curve, nothing is dimmed on top of it.
            let alpha = ring::to_u8(ring::ring_alpha(offset.unsigned_abs() as f32 * line_h, rect.height() / 2.0));
            if alpha == 0 {
                continue;
            }
            painter.text(
                egui::pos2(centre.x, centre.y + offset as f32 * line_h),
                egui::Align2::CENTER_CENTER,
                text,
                font.clone(),
                white_alpha(alpha),
            );
        }
    }

    /// F6: el libro del corpus, línea por línea.
    fn draw_f6(&self, painter: &egui::Painter, ctx: &egui::Context, rect: egui::Rect) {
        let v = &self.voider;
        self.draw_ring(
            painter,
            ctx,
            rect,
            &v.o_ring.lines,
            v.o_ring.index,
            "sin libro — Enter en F7 para abrir uno",
        );
        if !v.o_file.is_empty() {
            painter.text(
                egui::pos2(rect.center().x, rect.bottom() - 26.0),
                egui::Align2::CENTER_CENTER,
                corpus::clean_book_title(&v.o_file),
                egui::FontId::proportional(11.0),
                egui::Color32::from_gray(80),
            );
        }
    }

    /// F7: las ranuras del working set.
    fn draw_f7(&self, painter: &egui::Painter, ctx: &egui::Context, rect: egui::Rect) {
        let v = &self.voider;
        let entries = v.ws.browser_entries();
        self.draw_ring(painter, ctx, rect, &entries, v.ws_index, corpus::EMPTY);
        painter.text(
            egui::pos2(rect.center().x, rect.bottom() - 26.0),
            egui::Align2::CENTER_CENTER,
            "Tab sortea   Shift+Enter agrega   Ctrl+Supr saca   Enter abre",
            egui::FontId::proportional(11.0),
            egui::Color32::from_gray(75),
        );
    }

    /// F8: una sola línea, la que salió. Ancha, centrada, sin nada alrededor.
    fn draw_f8(&self, painter: &egui::Painter, ctx: &egui::Context, rect: egui::Rect) {
        let text = if self.voider.oracle.is_empty() { "..." } else { &self.voider.oracle };
        let width = rect.width() * 0.62;
        let galley = ctx.fonts(|f| {
            f.layout(
                text.to_string(),
                egui::FontId::proportional(self.font_size()),
                egui::Color32::from_gray(225),
                width,
            )
        });
        let pos = egui::pos2(
            rect.center().x - galley.size().x / 2.0,
            rect.center().y - galley.size().y / 2.0,
        );
        painter.galley(pos, galley, egui::Color32::from_gray(225));
        painter.text(
            egui::pos2(rect.center().x, rect.bottom() - 26.0),
            egui::Align2::CENTER_CENTER,
            "↑↓ otra   Enter quedársela",
            egui::FontId::proportional(11.0),
            egui::Color32::from_gray(75),
        );
    }

    /// El navegador: la misma forma de anillo que todo lo demás, con el título
    /// arriba diciendo qué se está eligiendo y la carpeta actual abajo.
    fn draw_browser(&self, painter: &egui::Painter, rect: egui::Rect) {
        let Some(b) = &self.voider.browser else {
            return;
        };
        painter.rect_filled(rect, 0.0, egui::Color32::from_black_alpha(244));
        let centre = rect.center();
        let line_h = self.font_size() * 1.55;
        let font = egui::FontId::proportional(self.font_size() * 0.85);

        painter.text(
            egui::pos2(centre.x, rect.top() + 46.0),
            egui::Align2::CENTER_CENTER,
            b.purpose.title(),
            egui::FontId::proportional(self.font_size() * 0.7),
            egui::Color32::from_gray(150),
        );

        let n = b.entries.len() as isize;
        if n == 0 {
            painter.text(
                centre,
                egui::Align2::CENTER_CENTER,
                "(vacío)",
                font,
                egui::Color32::from_gray(80),
            );
        } else {
            let reach = (rect.height() / 2.6 / line_h).ceil() as isize;
            for offset in -reach..=reach {
                let i = (b.index as isize + offset).rem_euclid(n) as usize;
                let entry = &b.entries[i];
                let alpha = if offset == 0 {
                    255
                } else {
                    let fade = (1.0 - (offset.unsigned_abs() as f32 / 6.0)).clamp(0.0, 1.0);
                    (fade * fade * 190.0) as u8
                };
                if alpha == 0 {
                    continue;
                }
                let colour = if entry.is_dir {
                    white_alpha(alpha)
                } else {
                    egui::Color32::from_rgba_unmultiplied(210, 210, 190, alpha)
                };
                painter.text(
                    egui::pos2(centre.x, centre.y + offset as f32 * line_h),
                    egui::Align2::CENTER_CENTER,
                    entry.display(),
                    font.clone(),
                    colour,
                );
            }
        }

        painter.text(
            egui::pos2(centre.x, rect.bottom() - 48.0),
            egui::Align2::CENTER_CENTER,
            b.dir.display().to_string(),
            egui::FontId::monospace(11.0),
            egui::Color32::from_gray(95),
        );
        let hint = if b.looking == browse::Looking::Dir {
            "Enter entrar   Shift+Enter elegir esta carpeta   Esc cancela"
        } else {
            "Enter entrar / elegir   Esc cancela"
        };
        painter.text(
            egui::pos2(centre.x, rect.bottom() - 24.0),
            egui::Align2::CENTER_CENTER,
            hint,
            egui::FontId::proportional(11.0),
            egui::Color32::from_gray(75),
        );
    }
    /// F11: the shortcut reference in two columns over a near-opaque ground.
    fn draw_help(&self, painter: &egui::Painter, rect: egui::Rect) {
        painter.rect_filled(rect, 0.0, egui::Color32::from_black_alpha(238));

        let (left, right) = help::columns(help::ROWS);
        let row_h = 21.0_f32;
        let tallest = left.len().max(right.len()) as f32 * row_h;
        let top = (rect.center().y - tallest / 2.0).max(rect.top() + 40.0);
        let col_w = rect.width() / 2.0;
        let key_font = egui::FontId::monospace(11.5);
        let desc_font = egui::FontId::proportional(12.0);
        let head_font = egui::FontId::proportional(12.0);

        for (col, rows) in [left, right].iter().enumerate() {
            let x = rect.left() + col_w * col as f32 + col_w * 0.10;
            for (i, (key, desc)) in rows.iter().enumerate() {
                let y = top + i as f32 * row_h;
                match desc {
                    // A section head, set apart in white.
                    None if !key.is_empty() => {
                        painter.text(
                            egui::pos2(x, y),
                            egui::Align2::LEFT_TOP,
                            key,
                            head_font.clone(),
                            egui::Color32::from_gray(235),
                        );
                    }
                    None => {} // a spacer
                    Some(d) => {
                        painter.text(
                            egui::pos2(x + 12.0, y),
                            egui::Align2::LEFT_TOP,
                            key,
                            key_font.clone(),
                            egui::Color32::from_gray(165),
                        );
                        painter.text(
                            egui::pos2(x + 12.0 + col_w * 0.30, y),
                            egui::Align2::LEFT_TOP,
                            d,
                            desc_font.clone(),
                            egui::Color32::from_gray(115),
                        );
                    }
                }
            }
        }
        painter.text(
            egui::pos2(rect.center().x, rect.bottom() - 22.0),
            egui::Align2::CENTER_CENTER,
            "cualquier tecla cierra",
            egui::FontId::proportional(11.0),
            egui::Color32::from_gray(70),
        );
    }

    fn draw_title(&self, painter: &egui::Painter, rect: egui::Rect) {
        if !self.voider.show_title {
            return;
        }
        // In F5 the title is the chapter the paragraph sits under.
        let title = match self.voider.view {
            View::F5 => self.voider.f5_title(),
            _ => app::file_title(&self.voider.current_file),
        }
        .to_uppercase();
        painter.text(
            egui::pos2(rect.center().x, rect.top() + 34.0),
            egui::Align2::CENTER_CENTER,
            title,
            egui::FontId::proportional(self.font_size() + 3.0),
            egui::Color32::WHITE,
        );
    }
}

impl eframe::App for VoiderApp {
    /// Voider is black: paint the window background black rather than egui's grey.
    fn clear_color(&self, _visuals: &egui::Visuals) -> [f32; 4] {
        [0.0, 0.0, 0.0, 1.0]
    }

    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        self.update_pointer(ctx);
        // Take in what the other instances did before reading this frame's
        // keys, so a keystroke always lands on the newest text.
        self.voider.poll_ipc();
        // Cuando la linea termino de sonar, la voz sigue sola con la siguiente.
        self.voider.tts_poll();
        self.handle_input(ctx);
        if self.voider.quit_requested {
            ctx.send_viewport_cmd(egui::ViewportCommand::Close);
        }
        // Nothing here generates its own repaints, so without this a sibling's
        // save would sit unnoticed until the next key or mouse move.
        ctx.request_repaint_after(std::time::Duration::from_millis(250));
        // A font chosen in F10 takes effect on this very frame.
        if self.voider.font_dirty {
            self.voider.font_dirty = false;
            let family = self.voider.config.font_family.clone();
            if family == "Default" {
                ctx.set_fonts(egui::FontDefinitions::default());
            } else {
                install_font(ctx, &family);
            }
        }
        egui::CentralPanel::default()
            // Only the ground thins out; the writing on it stays solid. The
            // Python's setWindowOpacity fades the text too, which is exactly
            // what you don't want when the point is to keep reading through it.
            .frame(egui::Frame::none().fill(egui::Color32::from_black_alpha(
                (self.voider.config.opacity.clamp(config::OPACITY_MIN, 1.0) * 255.0) as u8,
            )))
            .show(ctx, |ui| {
                let rect = ui.max_rect();
                let painter = ui.painter().clone();
                match self.voider.view {
                    View::F1 => self.draw_f1(&painter, ctx, rect),
                    View::F2 => self.draw_f2(&painter, ctx, rect),
                    View::F3 => self.draw_f3(&painter, ctx, rect),
                    View::F4 => self.draw_f4(&painter, ctx, rect),
                    View::F6 => self.draw_f6(&painter, ctx, rect),
                    View::F7 => self.draw_f7(&painter, ctx, rect),
                    View::F8 => self.draw_f8(&painter, ctx, rect),
                    View::F5 => self.draw_f5(&painter, ctx, rect),
                    // The only view built from a real widget rather than painted
                    // by hand: F9 wants ordinary prose editing (wrapping,
                    // selection, a caret that behaves), which is exactly what
                    // egui's own multiline box already is.
                    View::F9 => self.draw_f9(ui, rect),
                    View::F10 => self.draw_f10(&painter, rect),
                    View::Concat => self.draw_concat(&painter, ctx, rect),
                }
                self.draw_title(&painter, rect);
                if self.voider.backup_prompt.is_some() {
                    self.draw_backup_prompt(&painter, rect);
                }
                if self.voider.bundle_prompt.is_some() {
                    self.draw_bundle_prompt(&painter, rect);
                }
                if self.voider.browser.is_some() {
                    self.draw_browser(&painter, rect);
                }
                if self.voider.help_open {
                    self.draw_help(&painter, rect);
                }
                self.draw_pointer(&painter, ctx);
                if !self.voider.status.is_empty() {
                    painter.text(
                        egui::pos2(rect.center().x, rect.bottom() - 24.0),
                        egui::Align2::CENTER_CENTER,
                        &self.voider.status,
                        egui::FontId::proportional(13.0),
                        egui::Color32::from_gray(90),
                    );
                }
            });
    }
}

/// White at `alpha`, the way Qt draws it. egui's `Color32::from_white_alpha` works in
/// linear light, so alpha 75 comes out as a 148 grey — twice what the Python draws
/// for the same opacity. This one is plain premultiplied: alpha 75 is a 75 grey.
fn white_alpha(alpha: u8) -> egui::Color32 {
    egui::Color32::from_rgba_premultiplied(alpha, alpha, alpha, alpha)
}

/// What an `Event::Copy` (Ctrl+C, whatever else is held) means in a view.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum CopyAction {
    /// Ctrl+C: what is selected, or else the line / paragraph / chapter.
    Copy,
    /// Ctrl+Shift+C in F4: the book as Instagram slides.
    Carousel,
    Nothing,
}

/// Decide it. F9 has its own text box with its own copy; a search bar keeps its
/// letters; Shift only means something in F4.
fn copy_action(view: View, shift: bool, searching: bool) -> CopyAction {
    if searching || view == View::F9 {
        return CopyAction::Nothing;
    }
    match (view, shift) {
        (View::F4, true) => CopyAction::Carousel,
        (View::F1 | View::F2 | View::F3, false) => CopyAction::Copy,
        _ => CopyAction::Nothing,
    }
}

/// A paragraph laid out for F5: wrapped at `wrap_w` and CENTRED, the way F2
/// centres its lines. egui centres each row on the galley's ORIGIN (x = 0), not
/// on its left edge, so the galley has to be drawn at the MIDDLE of the column.
/// `text` cut to fit `max_w` with a trailing `…` — Qt's `elidedText(ElideRight)`.
fn elide(ctx: &egui::Context, text: &str, font: &egui::FontId, max_w: f32) -> String {
    let width = |s: &str| {
        ctx.fonts(|f| f.layout_no_wrap(s.to_string(), font.clone(), egui::Color32::WHITE).size().x)
    };
    if width(text) <= max_w {
        return text.to_string();
    }
    let chars: Vec<char> = text.chars().collect();
    let (mut lo, mut hi) = (0usize, chars.len());
    // The longest prefix that still fits with the ellipsis after it.
    while lo < hi {
        let mid = (lo + hi + 1) / 2;
        let candidate: String = chars[..mid].iter().collect::<String>() + "…";
        if width(&candidate) <= max_w {
            lo = mid;
        } else {
            hi = mid - 1;
        }
    }
    chars[..lo].iter().collect::<String>() + "…"
}

fn centered_galley(
    ctx: &egui::Context,
    text: String,
    font: egui::FontId,
    wrap_w: f32,
    line_h: Option<f32>,
) -> std::sync::Arc<egui::Galley> {
    let mut job = egui::text::LayoutJob::simple(text, font, egui::Color32::WHITE, wrap_w);
    job.halign = egui::Align::Center;
    // Every row (and so every one-row unit, a dot included) gets the same height.
    for section in &mut job.sections {
        section.format.line_height = line_h;
    }
    ctx.fonts(|f| f.layout_job(job))
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Run one frame so the context has its fonts, then lay a galley out.
    fn galley(text: &str, wrap_w: f32) -> std::sync::Arc<egui::Galley> {
        let ctx = egui::Context::default();
        let mut out = None;
        let _ = ctx.run(egui::RawInput::default(), |ctx| {
            out = Some(centered_galley(
                ctx,
                text.to_string(),
                egui::FontId::proportional(20.0),
                wrap_w,
                None,
            ));
        });
        out.unwrap()
    }

    // ── what F5 really paints, without a window ──────────────────────────────

    /// Run `draw` for one frame on a 1000x700 screen and return every piece of text
    /// it painted, as (text, position).
    fn painted_text(
        app: &mut VoiderApp,
        draw: impl Fn(&mut VoiderApp, &egui::Painter, &egui::Context, egui::Rect),
    ) -> Vec<(String, egui::Pos2)> {
        let ctx = egui::Context::default();
        let raw = egui::RawInput {
            screen_rect: Some(egui::Rect::from_min_size(egui::Pos2::ZERO, egui::vec2(1000.0, 700.0))),
            ..Default::default()
        };
        let mut found: Vec<(String, egui::Pos2)> = Vec::new();
        let out = ctx.run(raw, |ctx| {
            egui::CentralPanel::default().show(ctx, |ui| {
                let painter = ui.painter().clone();
                draw(app, &painter, ctx, ui.max_rect());
            });
        });
        for clipped in &out.shapes {
            collect_text(&clipped.shape, &mut found);
        }
        found
    }

    fn collect_text(shape: &egui::epaint::Shape, out: &mut Vec<(String, egui::Pos2)>) {
        match shape {
            egui::epaint::Shape::Text(t) => out.push((t.galley.text().to_string(), t.pos)),
            egui::epaint::Shape::Vec(v) => v.iter().for_each(|s| collect_text(s, out)),
            _ => {}
        }
    }

    fn f5_app(lines: &[&str]) -> (tempfile::TempDir, VoiderApp) {
        let d = tempfile::tempdir().unwrap();
        let f = d.path().join("c.txt");
        let lines: Vec<String> = lines.iter().map(|s| s.to_string()).collect();
        void::atomic_write(&f, &lines, false).unwrap();
        let mut voider = Voider::open(d.path(), &f);
        voider.switch_to(app::View::F5);
        (d, VoiderApp::with(voider))
    }

    // ── brightness must match Qt's, which blends alpha straight ──────────────

    #[test]
    fn white_at_alpha_75_is_a_75_grey_not_a_148_one() {
        // egui's own `from_white_alpha` works in linear light: alpha 75 comes out as
        // a 148 grey on black — twice what Qt draws for the same opacity.
        assert_eq!(egui::epaint::Color32::from_white_alpha(75).r(), 148, "egui changed; revisit");
        let c = white_alpha(75);
        assert_eq!((c.r(), c.g(), c.b(), c.a()), (75, 75, 75, 75));
        // laid over black, premultiplied, it is exactly a 75 grey
        assert_eq!(white_alpha(255), egui::Color32::WHITE);
        assert_eq!(white_alpha(0), egui::Color32::TRANSPARENT);
    }

    // ── keys that share a letter must not shadow each other ──────────────────

    fn ctrl() -> egui::Modifiers {
        egui::Modifiers { ctrl: true, command: true, ..Default::default() }
    }

    fn ctrl_shift() -> egui::Modifiers {
        egui::Modifiers { ctrl: true, command: true, shift: true, ..Default::default() }
    }

    // egui-winit turns every Ctrl+C into `Event::Copy` and drops the key event, so
    // what Ctrl+C means has to be decided from the view and the modifiers.

    #[test]
    fn copy_event_is_the_contextual_copy_in_the_views_that_have_one() {
        for view in [app::View::F1, app::View::F2, app::View::F3] {
            assert_eq!(copy_action(view, false, false), CopyAction::Copy, "{view:?}");
        }
    }

    #[test]
    fn ctrl_shift_c_in_f4_is_the_carousel_and_nowhere_else() {
        assert_eq!(copy_action(app::View::F4, true, false), CopyAction::Carousel);
        for view in [app::View::F1, app::View::F2, app::View::F3, app::View::F5] {
            assert_eq!(copy_action(view, true, false), CopyAction::Nothing, "{view:?}");
        }
    }

    #[test]
    fn f9_keeps_its_own_copy_and_a_search_bar_keeps_its_letters() {
        assert_eq!(copy_action(app::View::F9, false, false), CopyAction::Nothing);
        assert_eq!(copy_action(app::View::F2, false, true), CopyAction::Nothing);
    }

    #[test]
    fn plain_ctrl_c_in_f4_copies_nothing_in_particular() {
        // F4 has no contextual copy; only Ctrl+Shift+C means something there.
        assert_eq!(copy_action(app::View::F4, false, false), CopyAction::Nothing);
    }

    #[test]
    fn ctrl_shift_b_is_the_carousel_with_cover_not_the_backup() {
        let (_d, mut app) = f5_app(&[".", "Un parrafo."]);
        assert!(!app.handle_global_key(egui::Key::B, ctrl_shift()), "the global arm took Ctrl+Shift+B");
        assert!(app.voider.backup_prompt.is_none());
    }

    #[test]
    fn plain_ctrl_b_is_still_the_backup() {
        let (_d, mut app) = f5_app(&[".", "Un parrafo."]);
        assert!(app.handle_global_key(egui::Key::B, ctrl()));
    }

    #[test]
    fn f4_routes_ctrl_shift_c_and_ctrl_shift_b_to_the_carousel() {
        let (_d, mut app) = f5_app(&[".", "Un parrafo."]);
        app.voider.switch_to(app::View::F4);
        app.handle_f4_key(egui::Key::C, ctrl_shift());
        // one chapter shown: it exports at once, into void/carousel/<name>/
        assert!(app.voider.void_dir.join("carousel").join("c").join("1_titulo.png").is_file());
        app.handle_f4_key(egui::Key::B, ctrl_shift());
        assert_eq!(app.voider.browser.as_ref().map(|b| b.purpose), Some(browse::Purpose::Cover));
    }

    // ── PageUp/PageDown belong to each view, not to everyone (P1-1) ─────────

    fn none() -> egui::Modifiers {
        egui::Modifiers::default()
    }

    #[test]
    fn page_keys_are_not_global() {
        let (_d, mut app) = f5_app(&[".", "a", ".", "b"]);
        assert!(!app.handle_global_key(egui::Key::PageDown, none()));
        assert!(!app.handle_global_key(egui::Key::PageUp, none()));
    }

    #[test]
    fn page_down_in_f4_turns_the_page() {
        let lines = long_file(400);
        let refs: Vec<&str> = lines.iter().map(String::as_str).collect();
        let (_d, mut app) = f5_app(&refs);
        app.voider.switch_to(app::View::F4);
        app.reading_pages = 5;
        let before = app.voider.page;
        app.route_key(egui::Key::PageDown, none());
        assert_eq!(app.voider.page, before + 1);
        let ring_before = app.voider.ring.index;
        app.route_key(egui::Key::PageUp, none());
        assert_eq!(app.voider.page, before);
        assert_eq!(app.voider.ring.index, ring_before, "PageUp moved the document under F4");
    }

    #[test]
    fn page_down_in_f1_keeps_the_edit_and_jumps_a_paragraph() {
        let (_d, mut app) = f5_app(&[".", "a", ".", "b"]);
        app.voider.switch_to(app::View::F1);
        app.voider.ring.index = 1;
        app.voider.entry.set_text("a cambiada");
        app.route_key(egui::Key::PageDown, none());
        assert_eq!(app.voider.ring.lines[1], "a cambiada");
        assert_eq!(app.voider.ring.index, 2);
    }

    #[test]
    fn page_down_in_f3_jumps_to_the_next_book_not_the_document() {
        let (_d, mut app) = f5_app(&[".", "a", ".", "b"]);
        app.voider.switch_to(app::View::F3);
        app.voider.library.entries = vec![".".into(), "A.txt".into(), "B.txt".into(), ".".into(), "C.txt".into()];
        app.voider.library.index = 1;
        let doc = app.voider.ring.index;
        app.route_key(egui::Key::PageDown, none());
        assert_eq!(app.voider.library.index, 3);
        assert_eq!(app.voider.ring.index, doc);
        app.route_key(egui::Key::PageUp, none());
        assert_eq!(app.voider.library.index, 0);
    }

    #[test]
    fn page_keys_in_f5_do_not_move_the_document() {
        let (_d, mut app) = f5_app(&[".", "a", ".", "b"]);
        app.voider.switch_to(app::View::F5);
        let doc = app.voider.ring.index;
        app.route_key(egui::Key::PageDown, none());
        assert_eq!(app.voider.ring.index, doc);
    }

    // ── F3 keys (test_ctrl_enter.py, key_router _handle_f3_keys) ────────────

    fn ctrl_only() -> egui::Modifiers {
        egui::Modifiers { ctrl: true, command: true, ..Default::default() }
    }

    fn f3_app() -> (tempfile::TempDir, VoiderApp) {
        let (d, mut app) = f5_app(&[".", "a"]);
        let i = app.voider.void_dir.join("I");
        void::atomic_write(&i.join("Uno.txt"), &[".".into(), "uno".into()], false).unwrap();
        void::atomic_write(&i.join("Dos.txt"), &[".".into(), "dos".into()], false).unwrap();
        app.voider.switch_to(app::View::F3);
        app.voider.library.entries = vec!["Uno.txt".into(), "Dos.txt".into()];
        app.voider.library.index = 0;
        app.voider.f3_sync_entry();
        (d, app)
    }

    #[test]
    fn pressing_f3_while_in_f3_keeps_the_cursor_where_it_is() {
        let (_d, mut app) = f3_app();
        app.voider.library.index = 1;
        app.voider.f3_sync_entry();
        app.route_key(egui::Key::F3, none());
        assert_eq!(app.voider.library.index, 1);
        assert_eq!(app.voider.entry.text(), "Dos");
    }

    #[test]
    fn escape_in_f3_with_nothing_pending_goes_to_f1() {
        let (_d, mut app) = f3_app();
        app.route_key(egui::Key::Escape, none());
        assert_eq!(app.voider.view, app::View::F1);
    }

    #[test]
    fn escape_in_f3_while_naming_only_drops_the_name() {
        let (_d, mut app) = f3_app();
        app.route_key(egui::Key::Enter, egui::Modifiers { shift: true, ..Default::default() });
        assert!(app.voider.pending_new);
        app.route_key(egui::Key::Escape, none());
        assert!(!app.voider.pending_new);
        assert_eq!(app.voider.view, app::View::F3);
    }

    #[test]
    fn ctrl_enter_in_f3_creates_and_does_not_open() {
        let (_d, mut app) = f3_app();
        app.route_key(egui::Key::Enter, ctrl_only());
        assert!(app.voider.pending_new);
        assert_eq!(app.voider.view, app::View::F3);
    }

    #[test]
    fn plain_enter_at_the_start_still_opens() {
        let (_d, mut app) = f3_app();
        app.route_key(egui::Key::Enter, none());
        assert_eq!(app.voider.view, app::View::F2);
        assert!(app.voider.current_file.ends_with("Uno.txt"));
    }

    #[test]
    fn enter_with_the_caret_at_the_end_of_the_title_adds_a_row_below() {
        let (_d, mut app) = f3_app();
        app.voider.entry.end();
        app.route_key(egui::Key::Enter, none());
        assert_eq!(app.voider.view, app::View::F3);
        assert!(app.voider.pending_new);
        assert_eq!(app.voider.library.entries, vec!["Uno.txt", "", "Dos.txt"]);
    }

    // ── the chapter catalogue's keys (test_doc_send_keys.py) ────────────────

    #[test]
    fn typing_with_the_catalogue_open_filters_and_never_reaches_the_line() {
        let (_d, mut app) = f2_app(&[".", "linea"], 1);
        app.voider.doc_open_picker();
        app.route_text("x", false);
        assert_eq!(app.voider.picker_filter, "x");
        assert_eq!(app.voider.ring.lines[1], "linea");
        app.route_key(egui::Key::Backspace, none());
        assert_eq!(app.voider.picker_filter, "");
    }

    #[test]
    fn alt_shift_left_opens_the_catalogue_on_the_left() {
        let (_d, mut app) = f2_app(&[".", "linea"], 1);
        let alt_shift = egui::Modifiers { alt: true, shift: true, ..Default::default() };
        app.route_key(egui::Key::ArrowLeft, alt_shift);
        assert!(app.voider.picker_open);
        assert_eq!(app.voider.picker_side, app::PickerSide::Left);
        app.route_key(egui::Key::Escape, none());
        assert!(!app.voider.picker_open);
    }

    // ── F2 line editing (circular_view.CustomLineEdit) ──────────────────────

    fn f2_app(lines: &[&str], index: usize) -> (tempfile::TempDir, VoiderApp) {
        let (d, mut app) = f5_app(lines);
        app.voider.ring.index = index;
        app.voider.switch_to(app::View::F2);
        (d, app)
    }

    #[test]
    fn delete_at_the_end_of_the_line_joins_the_next_one() {
        let (_d, mut app) = f2_app(&[".", "hola", "mundo"], 1);
        app.voider.entry.end();
        app.route_key(egui::Key::Delete, none());
        assert_eq!(app.voider.ring.lines, vec![".", "holamundo"]);
    }

    #[test]
    fn left_at_the_start_wraps_to_the_end_and_right_at_the_end_to_the_start() {
        let (_d, mut app) = f2_app(&[".", "hola"], 1);
        assert_eq!(app.voider.entry.caret(), 0);
        app.route_key(egui::Key::ArrowLeft, none());
        assert_eq!(app.voider.entry.caret(), 4);
        app.route_key(egui::Key::ArrowRight, none());
        assert_eq!(app.voider.entry.caret(), 0);
    }

    #[test]
    fn ctrl_up_and_down_go_to_the_start_and_end_of_the_line() {
        let (_d, mut app) = f2_app(&[".", "hola"], 1);
        app.route_key(egui::Key::ArrowDown, ctrl_only());
        assert_eq!(app.voider.entry.caret(), 4);
        assert_eq!(app.voider.ring.index, 1, "Ctrl+↓ moved to another line");
        app.route_key(egui::Key::ArrowUp, ctrl_only());
        assert_eq!(app.voider.entry.caret(), 0);
        let ctrl_shift = egui::Modifiers { ctrl: true, command: true, shift: true, ..Default::default() };
        app.route_key(egui::Key::ArrowDown, ctrl_shift);
        assert_eq!(app.voider.entry.selection(), Some((0, 4)));
    }

    #[test]
    fn a_star_in_f2_is_tab_not_a_character() {
        let (_d, mut app) = f2_app(&[".", "a", "b", ".", "c"], 0);
        app.route_text("*", false);
        assert!(!app.voider.ring.lines.iter().any(|l| l.contains('*')));
    }

    #[test]
    fn a_star_in_f1_recycles_a_line_instead_of_typing_it() {
        let (_d, mut app) = f5_app(&[".", "a"]);
        app.voider.switch_to(app::View::F1);
        app.route_text("*", false);
        assert!(!app.voider.entry.text().contains('*'));
    }

    // ── Ctrl+Z: only where Python has it (new_interface.eventFilter) ────────

    fn undoable_change(app: &mut VoiderApp) {
        app.voider.ring.lines = vec![".".into(), "a".into(), "cambio".into()];
        app.voider.save().unwrap();
    }

    #[test]
    fn ctrl_z_does_nothing_in_f4_or_f9() {
        for view in [app::View::F4, app::View::F9, app::View::F7] {
            let (_d, mut app) = f5_app(&[".", "a"]);
            undoable_change(&mut app);
            let depth = app.voider.undo_depth();
            app.voider.switch_to(view);
            app.route_key(egui::Key::Z, ctrl_only());
            assert_eq!(app.voider.undo_depth(), depth, "Ctrl+Z undid something in {view:?}");
        }
    }

    #[test]
    fn ctrl_z_undoes_in_f2() {
        let (_d, mut app) = f5_app(&[".", "a"]);
        undoable_change(&mut app);
        app.voider.switch_to(app::View::F2);
        let depth = app.voider.undo_depth();
        app.route_key(egui::Key::Z, ctrl_only());
        assert_eq!(app.voider.undo_depth(), depth - 1);
    }

    #[test]
    fn ctrl_z_in_f3_while_a_name_is_being_typed_leaves_the_library_alone() {
        let (_d, mut app) = f3_app();
        undoable_change(&mut app);
        app.voider.entry.set_text("Uno edit");
        let depth = app.voider.undo_depth();
        app.route_key(egui::Key::Z, ctrl_only());
        assert_eq!(app.voider.undo_depth(), depth);
    }

    // ── the carousel preview in F4, without a window ─────────────────────────

    /// Every image the draw painted (anything that is not the font atlas), as its
    /// rectangle on screen.
    fn painted_images(
        app: &mut VoiderApp,
        draw: impl Fn(&mut VoiderApp, &egui::Painter, &egui::Context, egui::Rect),
    ) -> Vec<egui::Rect> {
        let ctx = egui::Context::default();
        let raw = egui::RawInput {
            screen_rect: Some(egui::Rect::from_min_size(egui::Pos2::ZERO, egui::vec2(1000.0, 700.0))),
            ..Default::default()
        };
        let mut found = Vec::new();
        let out = ctx.run(raw, |ctx| {
            egui::CentralPanel::default().show(ctx, |ui| {
                let painter = ui.painter().clone();
                draw(app, &painter, ctx, ui.max_rect());
            });
        });
        fn walk(shape: &egui::epaint::Shape, out: &mut Vec<egui::Rect>) {
            match shape {
                egui::epaint::Shape::Mesh(m) if m.texture_id != egui::TextureId::default() => out.push(m.calc_bounds()),
                egui::epaint::Shape::Vec(v) => v.iter().for_each(|s| walk(s, out)),
                _ => {}
            }
        }
        for clipped in &out.shapes {
            walk(&clipped.shape, &mut found);
        }
        found
    }

    fn f4_carousel_app(lines: &[&str], preset: &str) -> (tempfile::TempDir, VoiderApp) {
        let (d, mut app) = f5_app(lines);
        app.voider.config.carousel_preset = preset.to_string();
        app.voider.switch_to(app::View::F4);
        app.voider.toggle_carousel_view();
        (d, app)
    }

    #[test]
    fn in_carousel_mode_f4_paints_the_slide_as_an_image_with_the_slides_proportions() {
        let (_d, mut app) = f4_carousel_app(&[".", "Un parrafo del capitulo."], "1:1");
        let images = painted_images(&mut app, |a, p, c, r| a.draw_f4(p, c, r));
        assert_eq!(images.len(), 1, "one slide, one image: {images:?}");
        let r = images[0];
        assert!((r.width() - r.height()).abs() < 1.0, "a 1:1 slide must be drawn square: {r:?}");
        // centred on the screen, and not larger than it
        assert!((r.center().x - 500.0).abs() < 2.0 && (r.center().y - 350.0).abs() < 30.0, "{r:?}");
        assert!(r.width() <= 1000.0 && r.height() <= 700.0);
    }

    #[test]
    fn a_4_5_slide_is_drawn_taller_than_wide() {
        let (_d, mut app) = f4_carousel_app(&[".", "Un parrafo."], "4:5");
        let r = painted_images(&mut app, |a, p, c, r| a.draw_f4(p, c, r))[0];
        assert!((r.height() / r.width() - 1350.0 / 1080.0).abs() < 0.01, "{r:?}");
    }

    // ── F4 in book mode: a white A5 page, like the Python's ──────────────────

    fn long_file(n: usize) -> Vec<String> {
        let mut v = vec![".".to_string()];
        for i in 0..n {
            v.push(format!("Parrafo numero {i} con texto suficiente para ocupar espacio real en la pagina de verdad."));
            v.push(".".to_string());
        }
        v
    }

    fn f4_book_app(lines: &[String]) -> (tempfile::TempDir, VoiderApp) {
        let refs: Vec<&str> = lines.iter().map(String::as_str).collect();
        let (d, mut app) = f5_app(&refs);
        app.voider.switch_to(app::View::F4);
        (d, app)
    }

    #[test]
    fn in_book_mode_f4_paints_one_white_a5_page_centred_in_the_window() {
        let (_d, mut app) = f4_book_app(&["Primero.".to_string()]);
        let window = egui::Rect::from_min_size(egui::Pos2::ZERO, egui::vec2(1000.0, 700.0));
        let images = painted_images(&mut app, |a, p, c, _| a.draw_f4(p, c, window));
        assert_eq!(images.len(), 1, "{images:?}");
        let r = images[0];
        assert!((r.width() / r.height() - 148.0 / 210.0).abs() < 0.01, "not A5: {r:?}");
        assert!((r.center().x - 500.0).abs() < 2.0 && (r.center().y - 350.0).abs() < 2.0, "{r:?}");
        // 94 % of the window's height, like the Python's `* 0.94`
        assert!((r.height() - 700.0 * 0.94).abs() < 2.0, "{r:?}");
    }

    #[test]
    fn a_wider_than_tall_window_is_limited_by_its_height_and_a_narrow_one_by_its_width() {
        let (_d, mut app) = f4_book_app(&["Primero.".to_string()]);
        let tall = painted_images(&mut app, |a, p, c, _| a.draw_f4(p, c, egui::Rect::from_min_size(egui::Pos2::ZERO, egui::vec2(300.0, 900.0))))[0];
        assert!((tall.width() - 300.0 * 0.94).abs() < 2.0, "{tall:?}");
        assert!(tall.height() < 900.0 * 0.94);
    }

    #[test]
    fn the_page_counter_follows_the_pages_of_the_book() {
        let (_d, mut app) = f4_book_app(&long_file(60));
        painted_text(&mut app, |a, p, c, r| a.draw_f4(p, c, r));
        assert!(app.reading_pages > 2, "{} pages", app.reading_pages);
        let texts: Vec<String> = painted_text(&mut app, |a, p, c, r| a.draw_f4(p, c, r)).into_iter().map(|(t, _)| t).collect();
        assert!(texts.iter().any(|t| *t == format!("1 / {}", app.reading_pages)), "{texts:?}");
    }

    #[test]
    fn f4_opens_on_the_page_that_holds_the_paragraph_you_were_in() {
        let (_d, mut app) = f4_book_app(&long_file(60));
        app.voider.open_at_para = 50;
        painted_text(&mut app, |a, p, c, r| a.draw_f4(p, c, r));
        assert!(app.voider.page > 0, "should have opened late in the chapter");
        assert_eq!(app.voider.open_at_para, 0, "the jump happens once");
        let page = app.voider.page;
        painted_text(&mut app, |a, p, c, r| a.draw_f4(p, c, r));
        assert_eq!(app.voider.page, page, "turning pages afterwards is not undone");
    }

    #[test]
    fn a_new_window_size_redraws_the_page_at_its_size_but_the_book_keeps_its_pages() {
        // The layout scales with the page, so a smaller window is the same book,
        // smaller: same pages, drawn at the new size (not the old picture stretched).
        let (_d, mut app) = f4_book_app(&long_file(60));
        let big = painted_images(&mut app, |a, p, c, _| a.draw_f4(p, c, egui::Rect::from_min_size(egui::Pos2::ZERO, egui::vec2(1000.0, 700.0))))[0];
        let pages = app.reading_pages;
        let small = painted_images(&mut app, |a, p, c, _| a.draw_f4(p, c, egui::Rect::from_min_size(egui::Pos2::ZERO, egui::vec2(500.0, 350.0))))[0];
        assert!(small.height() < big.height() * 0.6, "{small:?} vs {big:?}");
        assert_eq!(app.reading_pages, pages);
        let (cw, ch) = (app.book_tex.as_ref().unwrap().key.0, app.book_tex.as_ref().unwrap().key.1);
        assert!((cw as f32 - small.width()).abs() < 1.5 && (ch as f32 - small.height()).abs() < 1.5, "the texture is for the new size");
    }

    #[test]
    fn a_different_chapter_is_laid_out_afresh_not_taken_from_the_cache() {
        let (_d, mut app) = f4_book_app(&long_file(60));
        painted_text(&mut app, |a, p, c, r| a.draw_f4(p, c, r));
        let before = app.reading_pages;
        // F4 re-entered after the chapter on disk became a short one: the cache must
        // not hold on to the long one
        app.voider.view = app::View::F2;
        void::atomic_write(&app.voider.current_file.clone(), &[".".to_string(), "Corto.".to_string()], false).unwrap();
        app.voider.switch_to(app::View::F4);
        painted_text(&mut app, |a, p, c, r| a.draw_f4(p, c, r));
        assert!(app.reading_pages < before, "{} vs {before}", app.reading_pages);
    }

    #[test]
    fn an_empty_reading_paints_nothing_and_does_not_crash() {
        let (_d, mut app) = f5_app(&["."]);
        app.voider.switch_to(app::View::F4);
        app.voider.reading.clear();
        assert!(painted_images(&mut app, |a, p, c, r| a.draw_f4(p, c, r)).is_empty());
    }

    #[test]
    fn the_page_counter_and_the_page_turns_follow_the_slides() {
        let (_d, mut app) = f4_carousel_app(&[".", "Un parrafo."], "1:1");
        painted_text(&mut app, |a, p, c, r| a.draw_f4(p, c, r));
        assert_eq!(app.reading_pages, 2, "title slide + one body slide");
        let texts: Vec<String> = painted_text(&mut app, |a, p, c, r| a.draw_f4(p, c, r)).into_iter().map(|(t, _)| t).collect();
        assert!(texts.iter().any(|t| t == "1 / 2"), "{texts:?}");
        app.voider.page = 1;
        let texts: Vec<String> = painted_text(&mut app, |a, p, c, r| a.draw_f4(p, c, r)).into_iter().map(|(t, _)| t).collect();
        assert!(texts.iter().any(|t| t == "2 / 2"), "{texts:?}");
    }

    #[test]
    fn the_texture_is_redrawn_only_when_the_slide_changes() {
        let (_d, mut app) = f4_carousel_app(&[".", "Un parrafo."], "1:1");
        painted_images(&mut app, |a, p, c, r| a.draw_f4(p, c, r));
        let first = app.carousel_tex.as_ref().map(|t| t.slide.clone()).expect("a texture is cached");
        assert_eq!(first, app.voider.carousel_slides[0]);
        app.voider.page = 1;
        painted_images(&mut app, |a, p, c, r| a.draw_f4(p, c, r));
        assert_eq!(app.carousel_tex.as_ref().unwrap().slide, app.voider.carousel_slides[1]);
    }

    #[test]
    fn plain_v_in_f4_toggles_the_preview() {
        let (_d, mut app) = f5_app(&[".", "Un parrafo."]);
        app.voider.switch_to(app::View::F4);
        app.handle_f4_key(egui::Key::V, egui::Modifiers::default());
        assert!(app.voider.carousel_view);
        app.handle_f4_key(egui::Key::V, egui::Modifiers::default());
        assert!(!app.voider.carousel_view);
    }

    #[test]
    fn f5_paints_the_current_paragraph_at_the_centre_and_its_neighbours() {
        let (_d, mut app) = f5_app(&[".", "Primer parrafo del libro.", ".", "Segundo parrafo.", ".", "Tercero."]);
        let drawn = painted_text(&mut app, |a, p, c, r| a.draw_f5(p, c, r));
        let texts: Vec<&str> = drawn.iter().map(|(t, _)| t.as_str()).collect();
        assert!(texts.contains(&"Primer parrafo del libro."), "the current paragraph is not painted: {texts:?}");
        assert!(texts.contains(&"Segundo parrafo."), "its neighbour is not painted: {texts:?}");

        // The current paragraph sits at the vertical middle of the screen and is
        // centred on the column; the one after it comes below, the dot between
        // them in between, tight (no blank line).
        let at = |t: &str| drawn.iter().find(|(s, _)| s == t).map(|(_, p)| *p).unwrap();
        let (first, second) = (at("Primer parrafo del libro."), at("Segundo parrafo."));
        assert!((first.x - 500.0).abs() < 1.0, "not centred: {first:?}");
        assert!((first.y - 350.0).abs() < 25.0, "not vertically centred: {first:?}");
        assert!(second.y > first.y, "the next paragraph should be below");
        let gap = second.y - first.y;
        // a one-row paragraph, then a one-row dot, each 1.5 x the font's height tall
        assert!(gap < 130.0, "units are not packed tight: {gap}");
    }

    #[test]
    fn a_short_paragraph_is_centred_in_the_column() {
        let g = galley("hola", 400.0);
        let row = &g.rows[0];
        let mid = (row.rect.min.x + row.rect.max.x) / 2.0;
        // egui centres on the galley's origin, so it is drawn at the column's middle
        assert!(mid.abs() < 1.0, "row centre at {mid}, wanted 0");
    }

    #[test]
    fn every_wrapped_row_is_centred_on_its_own() {
        let g = galley("uno dos tres cuatro cinco seis siete ocho nueve diez once", 160.0);
        assert!(g.rows.len() > 1, "the text should have wrapped");
        for row in &g.rows {
            let mid = (row.rect.min.x + row.rect.max.x) / 2.0;
            assert!(mid.abs() < 1.0, "a row is centred at {mid}, wanted 0");
        }
    }
}

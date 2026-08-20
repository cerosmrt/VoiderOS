//! voider-rs — a Rust/egui mirror of proto-voider.
//!
//! Parallel to the Python app, which stays untouched: this is a second
//! implementation, built view by view, aiming at 1:1 behaviour. Immediate-mode
//! rendering means we own every pixel and every keystroke — the custom things
//! that fight a widget toolkit (the typewriter caret, scriptio continua) are
//! just "what do I draw this frame?".

mod app;
mod backup;
mod config;
mod corpus;
mod f5;
mod fonts;
mod help;
mod ipc;
mod library;
mod paragraphs;
mod line_ring;
mod position;
mod reading;
mod reformat;
mod split;
mod text_line;
mod tts;
mod undo;
mod void;
mod words;

use eframe::egui;

use app::{caps_lock_on, View, Voider};

/// Matches the Python view: the circle inset from the shorter side.
const CIRCLE_INSET: f32 = 35.0;
/// How far the fade reaches in F2, in lines above and below the centre.
const F2_FADE_LINES: f32 = 7.0;

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
}

impl VoiderApp {
    fn new() -> Self {
        Self { voider: app::open_sandbox(), pointer_hidden: true, reading_pages: 1 }
    }

    /// The size the writer chose, used by every view.
    fn font_size(&self) -> f32 {
        self.voider.config.font_size
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

    fn handle_input(&mut self, ctx: &egui::Context) {
        let caps = caps_lock_on();
        let events = ctx.input(|i| i.events.clone());
        for event in events {
            match event {
                // The backtick is a command (the scratch round trip), never a
                // character: the key event below handles it, so drop the text or
                // it would be typed into the line as well.
                egui::Event::Text(t) if t == "`" => {}
                // While the help is up nothing types: the keypress that closes
                // it must not also land in the text underneath.
                egui::Event::Text(_) if self.voider.help_open => {}
                egui::Event::Text(t) => match self.voider.view {
                    View::F1 => {
                        let _ = self.voider.type_text(&t, caps);
                    }
                    View::F2 => {
                        if self.voider.f2_search.is_some() {
                            self.voider.f2_search_type(&text_line::neutralize_caps(&t, caps));
                        } else {
                            self.voider.entry.insert(&text_line::neutralize_caps(&t, caps));
                            let _ = self.voider.doc_live_save();
                        }
                    }
                    // In F3 typing only means something while naming a new entry,
                    // a book being merged, or searching.
                    View::F3 => {
                        if self.voider.f3_search.is_some() {
                            self.voider.f3_search_type(&text_line::neutralize_caps(&t, caps));
                        } else if self.voider.pending_new || self.voider.pending_merge {
                            self.voider.entry.insert(&text_line::neutralize_caps(&t, caps));
                        }
                    }
                    // F9's text goes into egui's own multiline widget, which
                    // reads the same events itself — typing it again here would
                    // double every character.
                    View::F4 | View::F5 | View::F6 | View::F7 | View::F8 | View::F9 | View::F10 => {}
                },
                egui::Event::Key { key, pressed: true, modifiers, .. } => {
                    // The help is a reference, not a mode: any key at all puts
                    // it away, and that key does nothing else.
                    if self.voider.help_open {
                        self.voider.help_open = false;
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
                    // There is no text selection to fall back to here, so
                    // Ctrl+C always means the contextual copy — unless a search
                    // bar has focus (a 'c' belongs in the query) or we're in F9,
                    // where the prose box has a real selection and its own copy.
                    if key == egui::Key::C
                        && modifiers.ctrl
                        && self.voider.view != View::F9
                        && self.voider.f2_search.is_none()
                        && self.voider.f3_search.is_none()
                    {
                        if let Some(text) = self.voider.smart_copy() {
                            ctx.output_mut(|o| o.copied_text = text);
                        }
                        continue;
                    }
                    if self.handle_global_key(key, modifiers) {
                        continue;
                    }
                    match self.voider.view {
                        View::F1 => self.handle_f1_key(key, caps, modifiers),
                        View::F2 => self.handle_f2_key(key, caps, modifiers),
                        View::F3 => self.handle_f3_key(key, modifiers),
                        View::F4 => self.handle_f4_key(key),
                        View::F6 => self.handle_f6_key(key),
                        View::F7 => self.handle_f7_key(key, modifiers),
                        View::F8 => self.handle_f8_key(key),
                        View::F5 => self.handle_f5_key(key, modifiers),
                        View::F9 => self.handle_f9_key(key, modifiers),
                        View::F10 => self.handle_f10_key(key),
                    }
                }
                _ => {}
            }
        }
    }

    /// Keys that mean the same thing everywhere. Returns true when handled.
    fn handle_global_key(&mut self, key: egui::Key, m: egui::Modifiers) -> bool {
        use egui::Key;
        match key {
            Key::F1 => self.voider.switch_to(View::F1),
            Key::F2 => self.voider.switch_to(View::F2),
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
            Key::B if m.ctrl => self.voider.begin_backup(),
            // Undo / redo of text content, from any view.
            Key::Z if m.ctrl && m.shift => {
                let _ = self.voider.redo();
            }
            Key::Z if m.ctrl => {
                let _ = self.voider.undo();
            }
            // Backtick: round trip to the scratch, from wherever you are.
            Key::Backtick => self.voider.scratch_toggle(),
            // Paragraph jumps, everywhere the document is on screen.
            Key::PageDown => self.voider.goto_dot(1),
            Key::PageUp => self.voider.goto_dot(-1),
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
            Key::Backspace => {
                self.voider.backspace(caps);
            }
            Key::Delete => {
                self.voider.entry.delete();
            }
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
            Key::ArrowUp => {
                self.voider.ring.move_by(-1);
                self.voider.show_current();
            }
            Key::ArrowDown => {
                self.voider.ring.move_by(1);
                self.voider.show_current();
            }
            _ => {}
        }
    }

    fn handle_f2_key(&mut self, key: egui::Key, caps: bool, m: egui::Modifiers) {
        use egui::Key;
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
            // Ctrl+Delete at the start, or Ctrl+Backspace at the end: send the
            // whole line down the trash cascade (other file → 0.txt → trash →
            // gone). At any other caret position they edit normally, below.
            Key::Delete if m.ctrl && self.voider.entry.caret() == 0 => {
                let _ = self.voider.delete_line_to_zero();
            }
            Key::Backspace if m.ctrl && self.voider.entry.caret() == self.voider.entry.len() => {
                let _ = self.voider.delete_line_to_zero();
            }
            Key::Backspace => {
                if caps {
                    // scriptio continua: type and send, no editing
                } else if self.voider.entry.caret() == 0 {
                    let _ = self.voider.doc_join_prev();
                } else {
                    self.voider.entry.backspace();
                    let _ = self.voider.doc_live_save();
                }
            }
            Key::Delete => {
                self.voider.entry.delete();
                let _ = self.voider.doc_live_save();
            }
            // Alt moves things: the line up/down, the word left/right.
            Key::ArrowUp if m.alt => {
                let _ = self.voider.doc_swap_line(-1);
            }
            Key::ArrowDown if m.alt => {
                let _ = self.voider.doc_swap_line(1);
            }
            Key::ArrowLeft if m.alt => {
                let _ = self.voider.doc_swap_words(-1);
            }
            Key::ArrowRight if m.alt => {
                let _ = self.voider.doc_swap_words(1);
            }
            Key::ArrowUp => {
                let _ = self.voider.doc_navigate(-1);
            }
            Key::ArrowDown => {
                let _ = self.voider.doc_navigate(1);
            }
            Key::ArrowLeft => self.voider.entry.move_caret(-1),
            Key::ArrowRight => self.voider.entry.move_caret(1),
            Key::Home => self.voider.doc_jump_edge(false),
            Key::End => self.voider.doc_jump_edge(true),
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
        match key {
            // Ctrl+F: search the library's chapters.
            Key::F if m.ctrl && !m.shift => self.voider.open_f3_search(),
            // Ctrl+Shift+M on a separator: name and merge that book into one file.
            Key::M if m.ctrl && m.shift => self.voider.book_merge_prompt(),
            // Split the highlighted (not necessarily open) chapter at its markers.
            Key::S if m.ctrl && m.shift => {
                let _ = self.voider.book_split_current();
            }
            // Shift+Enter opens a blank entry to name; Enter confirms it, or
            // opens the highlighted chapter when we're just browsing. A pending
            // merge takes priority — it's naming a book, not a single chapter.
            Key::Enter if m.shift => self.voider.begin_new_chapter(),
            Key::Enter if self.voider.pending_merge => {
                let _ = self.voider.book_do_merge();
            }
            Key::Enter => {
                if self.voider.pending_new {
                    let _ = self.voider.settle_pending();
                } else {
                    self.voider.open_current_chapter();
                }
            }
            Key::Escape if self.voider.pending_merge => self.voider.book_cancel_merge(),
            Key::Escape => self.voider.cancel_pending(),
            Key::Backspace => {
                if self.voider.pending_new || self.voider.pending_merge {
                    self.voider.entry.backspace();
                }
            }
            // Moving away settles a named entry instead of losing it.
            Key::ArrowUp => {
                let _ = self.voider.settle_pending();
                self.voider.library.move_by(-1);
            }
            Key::ArrowDown => {
                let _ = self.voider.settle_pending();
                self.voider.library.move_by(1);
            }
            // On a separator: shuffle that book. On a title: jump to a random one.
            Key::Tab => {
                let _ = self.voider.book_tab();
            }
            _ => {}
        }
    }

    fn handle_f5_key(&mut self, key: egui::Key, m: egui::Modifiers) {
        use egui::Key;
        // With the catalogue open, the keys belong to it.
        if self.voider.picker_open {
            match key {
                Key::Escape | Key::ArrowLeft => self.voider.picker_open = false,
                Key::Enter | Key::ArrowRight => {
                    let entries = self.voider.picker_entries();
                    if let Some(e) = entries.get(self.voider.picker_idx).cloned() {
                        let _ = self.voider.send_para_to(&e);
                    }
                }
                Key::ArrowDown | Key::Tab => self.voider.picker_cycle(1),
                Key::ArrowUp => self.voider.picker_cycle(-1),
                _ => {}
            }
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
    fn handle_f10_key(&mut self, key: egui::Key) {
        use egui::Key;
        match key {
            Key::ArrowUp => self.voider.settings_step_family(-1),
            Key::ArrowDown => self.voider.settings_step_family(1),
            Key::ArrowLeft => self.voider.settings_step_size(-1),
            Key::ArrowRight => self.voider.settings_step_size(1),
            Key::Escape | Key::Enter => self.voider.switch_to(View::F1),
            _ => {}
        }
    }

    /// F4 is for reading: turn pages, or leave.
    fn handle_f4_key(&mut self, key: egui::Key) {
        use egui::Key;
        let pages = self.reading_pages.max(1);
        match key {
            Key::ArrowRight | Key::ArrowDown | Key::PageDown | Key::Space => {
                self.voider.turn_page(1, pages)
            }
            Key::ArrowLeft | Key::ArrowUp | Key::PageUp => self.voider.turn_page(-1, pages),
            Key::Home => self.voider.page = 0,
            Key::End => self.voider.page = pages - 1,
            Key::Escape => self.voider.switch_to(View::F2),
            _ => {}
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
        let centre = rect.center();
        let line_h = self.font_size() * 1.7;
        let font = egui::FontId::proportional(self.font_size());
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
                let dist = offset.unsigned_abs() as f32;
                let alpha = if offset == 0 {
                    255
                } else {
                    let fade = (1.0 - (dist / F2_FADE_LINES)).clamp(0.0, 1.0);
                    (fade * fade * 200.0) as u8
                };
                if alpha == 0 {
                    continue;
                }
                painter.text(
                    egui::pos2(centre.x, centre.y + offset as f32 * line_h),
                    egui::Align2::CENTER_CENTER,
                    text,
                    font.clone(),
                    egui::Color32::from_white_alpha(alpha),
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

        for offset in -reach..=reach {
            if offset == 0 {
                continue; // the centred line is the editable entry, drawn below
            }
            let text = self.voider.ring.get(offset);
            if text.is_empty() {
                continue;
            }
            let dist = offset.unsigned_abs() as f32;
            let fade = (1.0 - (dist / F2_FADE_LINES)).clamp(0.0, 1.0);
            let alpha = (fade * fade * 200.0) as u8;
            if alpha == 0 {
                continue;
            }
            let y = centre.y + offset as f32 * line_h;
            painter.text(
                egui::pos2(centre.x, y),
                egui::Align2::CENTER_CENTER,
                text,
                font.clone(),
                egui::Color32::from_white_alpha(alpha),
            );
        }
        self.draw_entry_line(painter, ctx, centre, rect, self.voider.typewriter);
    }

    /// The library: chapter titles in reading order, the current one centred.
    /// Separators show as a dot; the naming of a new entry happens in place.
    fn draw_f3(&self, painter: &egui::Painter, ctx: &egui::Context, rect: egui::Rect) {
        let centre = rect.center();
        let line_h = self.font_size() * 1.7;
        let font = egui::FontId::proportional(self.font_size());
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
                let dist = offset.unsigned_abs() as f32;
                let alpha = if offset == 0 {
                    255
                } else {
                    let fade = (1.0 - (dist / F2_FADE_LINES)).clamp(0.0, 1.0);
                    (fade * fade * 200.0) as u8
                };
                if alpha == 0 {
                    continue;
                }
                painter.text(
                    egui::pos2(centre.x, centre.y + offset as f32 * line_h),
                    egui::Align2::CENTER_CENTER,
                    label,
                    font.clone(),
                    egui::Color32::from_white_alpha(alpha),
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
                if offset == 0 && (self.voider.pending_new || self.voider.pending_merge) {
                    continue; // the name being typed is drawn as the entry line
                }
                let i = (lib.index as isize + offset).rem_euclid(n) as usize;
                let label = library::display_name(&lib.entries[i]);
                let dist = offset.unsigned_abs() as f32;
                let alpha = if offset == 0 {
                    255
                } else {
                    let fade = (1.0 - (dist / F2_FADE_LINES)).clamp(0.0, 1.0);
                    (fade * fade * 200.0) as u8
                };
                if alpha == 0 {
                    continue;
                }
                painter.text(
                    egui::pos2(centre.x, centre.y + offset as f32 * line_h),
                    egui::Align2::CENTER_CENTER,
                    label,
                    font.clone(),
                    egui::Color32::from_white_alpha(alpha),
                );
            }
        }
        if self.voider.pending_new || self.voider.pending_merge {
            self.draw_entry_line(painter, ctx, centre, rect, false);
        }
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
        let line_h = self.font_size() * 1.5;

        let cur = units
            .iter()
            .position(|u| matches!(u, f5::Unit::Para { ordinal, .. } if *ordinal == self.voider.para_idx))
            .unwrap_or(0);

        let layout = |u: &f5::Unit, lit: bool| {
            let (text, colour) = match u {
                f5::Unit::Para { text, .. } => (
                    text.clone(),
                    if lit {
                        egui::Color32::WHITE
                    } else {
                        egui::Color32::from_gray(90)
                    },
                ),
                f5::Unit::Mark { name } => {
                    (format!("/{name}"), egui::Color32::from_gray(180))
                }
            };
            ctx.fonts(|f| f.layout(text, font.clone(), colour, text_w))
        };

        // Centre the current unit, then walk outward until off-screen.
        let here = layout(&units[cur], true);
        let mut y = col.center().y - here.size().y / 2.0;
        let cur_top = y;
        painter.galley(egui::pos2(col.min.x + pad, y), here.clone(), egui::Color32::WHITE);
        // The '>' cue: Right opens the catalogue to send this paragraph.
        painter.text(
            egui::pos2(col.max.x - pad / 2.0, cur_top + here.size().y / 2.0),
            egui::Align2::CENTER_CENTER,
            ">",
            font.clone(),
            egui::Color32::WHITE,
        );

        y = cur_top + here.size().y + line_h;
        for u in &units[cur + 1..] {
            if y > col.max.y {
                break;
            }
            let g = layout(u, false);
            let h = g.size().y;
            painter.galley(egui::pos2(col.min.x + pad, y), g, egui::Color32::WHITE);
            y += h + line_h;
        }
        let mut top = cur_top;
        for u in units[..cur].iter().rev() {
            let g = layout(u, false);
            let h = g.size().y;
            top -= h + line_h;
            if top + h < col.min.y {
                break;
            }
            painter.galley(egui::pos2(col.min.x + pad, top), g, egui::Color32::WHITE);
        }

        if self.voider.picker_open {
            self.draw_picker(painter, col.max.x, panel_w, rect);
        }
    }

    /// The side catalogue: chapters this paragraph can be sent to.
    fn draw_picker(&self, painter: &egui::Painter, x: f32, w: f32, rect: egui::Rect) {
        painter.line_segment(
            [egui::pos2(x, rect.top()), egui::pos2(x, rect.bottom())],
            egui::Stroke::new(1.0_f32, egui::Color32::from_gray(40)),
        );
        let entries = self.voider.picker_entries();
        if entries.is_empty() {
            return;
        }
        let font = egui::FontId::proportional(self.font_size() - 4.0);
        let line_h = self.font_size() * 1.9;
        let cy = rect.center().y;
        let cur = self.voider.picker_idx.min(entries.len() - 1);
        let reach = (rect.height() / 2.0 / line_h).ceil() as isize;

        for d in -reach..=reach {
            let i = cur as isize + d;
            if i < 0 || i as usize >= entries.len() {
                continue;
            }
            let colour = if d == 0 {
                egui::Color32::from_gray(235)
            } else {
                let a = (110 - d.unsigned_abs().min(3) as i32 * 22).max(45) as u8;
                egui::Color32::from_gray(a)
            };
            painter.text(
                egui::pos2(x + w / 2.0, cy + d as f32 * line_h),
                egui::Align2::CENTER_CENTER,
                library::display_name(&entries[i as usize]),
                font.clone(),
                colour,
            );
        }
        painter.text(
            egui::pos2(x + w / 2.0, rect.bottom() - 24.0),
            egui::Align2::CENTER_CENTER,
            "→ enviar   ← volver",
            egui::FontId::proportional(12.0),
            egui::Color32::from_gray(70),
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
                egui::Color32::from_white_alpha((fade * fade * 190.0) as u8)
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
            format!("←  {}  →", self.font_size() as i32),
            egui::FontId::proportional(self.font_size()),
            egui::Color32::from_gray(200),
        );
        painter.text(
            egui::pos2(centre.x, rect.bottom() - 28.0),
            egui::Align2::CENTER_CENTER,
            "↑↓ fuente   ←→ tamaño   ⏎ volver",
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
        let mut buffer = self.voider.prose.clone();

        let mut child = ui.new_child(egui::UiBuilder::new().max_rect(inner));
        egui::ScrollArea::vertical()
            .auto_shrink([false, false])
            .scroll_bar_visibility(egui::scroll_area::ScrollBarVisibility::AlwaysHidden)
            .show(&mut child, |ui| {
                let edit = egui::TextEdit::multiline(&mut buffer)
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
                "⏎ copiar   ↑↓ otro destino ({}/{})   cualquier otra tecla cancela",
                prompt.idx + 1,
                prompt.drives.len()
            )
        } else {
            "⏎ copiar   ·   cualquier otra tecla cancela".to_string()
        };
        painter.text(
            egui::pos2(centre.x, centre.y + 74.0),
            egui::Align2::CENTER_CENTER,
            hint,
            egui::FontId::proportional(12.0),
            egui::Color32::from_gray(95),
        );
    }

    /// F4: the text set in a column and shown a page at a time.
    ///
    /// The whole thing is laid out once as one tall column; a page is a window
    /// onto it, chosen so no line is ever cut across the break. Titles bind to
    /// what follows them, which is why they are measured into the same column
    /// rather than drawn separately.
    fn draw_f4(&mut self, painter: &egui::Painter, ctx: &egui::Context, rect: egui::Rect) {
        let margin = (rect.width() * 0.24).max(70.0);
        let col_w = rect.width() - margin * 2.0;
        let top_pad = 60.0;
        let page_h = rect.height() - top_pad * 2.0;
        let size = self.font_size();
        let body = egui::FontId::proportional(size);
        let head = egui::FontId::proportional(size * 1.05);
        let para_gap = size * 0.85;
        let title_gap = size * 1.9;

        // Lay the column out once: every paragraph becomes a galley, and the
        // lines within it become the units pagination is allowed to break on.
        let mut blocks: Vec<(f32, std::sync::Arc<egui::Galley>, bool)> = Vec::new();
        let mut lines: Vec<reading::Line> = Vec::new();
        let mut y = 0.0_f32;
        // Where each paragraph starts, so we can open on the one you were editing.
        let mut para_tops: Vec<f32> = Vec::new();

        for (s, section) in self.voider.reading.iter().enumerate() {
            if s > 0 {
                y += title_gap;
            }
            let galley = ctx.fonts(|f| {
                f.layout(section.title.clone(), head.clone(), egui::Color32::PLACEHOLDER, col_w)
            });
            for row in &galley.rows {
                lines.push(reading::Line { top: y + row.min_y(), height: row.height() });
            }
            blocks.push((y, galley.clone(), true));
            y += galley.size().y + para_gap;

            for para in &section.paragraphs {
                let galley = ctx.fonts(|f| {
                    f.layout(para.clone(), body.clone(), egui::Color32::PLACEHOLDER, col_w)
                });
                para_tops.push(y);
                for row in &galley.rows {
                    lines.push(reading::Line { top: y + row.min_y(), height: row.height() });
                }
                blocks.push((y, galley.clone(), false));
                y += galley.size().y + para_gap;
            }
        }

        let offsets = reading::page_offsets(&lines, page_h);
        self.reading_pages = offsets.len();

        // Opening on the paragraph you were editing: only on the frame we
        // arrive, so turning pages afterwards isn't undone.
        if self.voider.page == 0 && self.voider.open_at_para > 0 {
            if let Some(top) = para_tops.get(self.voider.open_at_para) {
                self.voider.page = reading::page_of(&offsets, *top);
            }
            self.voider.open_at_para = 0;
        }
        let page = self.voider.page.min(offsets.len().saturating_sub(1));
        let scroll = offsets.get(page).copied().unwrap_or(0.0);

        // Only what belongs on this page: clipped, so a line half over the edge
        // is never drawn as a sliver.
        let page_rect = egui::Rect::from_min_max(
            egui::pos2(rect.left() + margin, rect.top() + top_pad),
            egui::pos2(rect.right() - margin, rect.top() + top_pad + page_h),
        );
        let clipped = painter.with_clip_rect(page_rect);
        for (top, galley, is_title) in &blocks {
            let draw_y = page_rect.top() + top - scroll;
            if draw_y + galley.size().y < page_rect.top() - 1.0 || draw_y > page_rect.bottom() {
                continue; // off this page
            }
            let colour = if *is_title {
                egui::Color32::from_gray(235)
            } else {
                egui::Color32::from_gray(205)
            };
            clipped.galley(egui::pos2(page_rect.left(), draw_y), galley.clone(), colour);
        }

        if offsets.len() > 1 {
            painter.text(
                egui::pos2(rect.center().x, rect.bottom() - 26.0),
                egui::Align2::CENTER_CENTER,
                format!("{} / {}", page + 1, offsets.len()),
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
        rect: egui::Rect,
        lines: &[String],
        index: usize,
        vacio: &str,
    ) {
        let centre = rect.center();
        let line_h = self.font_size() * 1.7;
        let font = egui::FontId::proportional(self.font_size());
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
            let alpha = if offset == 0 {
                255
            } else {
                let fade = (1.0 - (offset.unsigned_abs() as f32 / F2_FADE_LINES)).clamp(0.0, 1.0);
                (fade * fade * 200.0) as u8
            };
            if alpha == 0 {
                continue;
            }
            painter.text(
                egui::pos2(centre.x, centre.y + offset as f32 * line_h),
                egui::Align2::CENTER_CENTER,
                text,
                font.clone(),
                egui::Color32::from_white_alpha(alpha),
            );
        }
    }

    /// F6: el libro del corpus, línea por línea.
    fn draw_f6(&self, painter: &egui::Painter, rect: egui::Rect) {
        let v = &self.voider;
        self.draw_ring(
            painter,
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
    fn draw_f7(&self, painter: &egui::Painter, rect: egui::Rect) {
        let v = &self.voider;
        let entries = v.ws.browser_entries();
        self.draw_ring(painter, rect, &entries, v.ws_index, corpus::EMPTY);
        painter.text(
            egui::pos2(rect.center().x, rect.bottom() - 26.0),
            egui::Align2::CENTER_CENTER,
            "Tab sortea   ⇧⏎ agrega   Ctrl+Supr saca   ⏎ abre",
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
            "↑↓ otra   ⏎ quedársela",
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
                    View::F6 => self.draw_f6(&painter, rect),
                    View::F7 => self.draw_f7(&painter, rect),
                    View::F8 => self.draw_f8(&painter, ctx, rect),
                    View::F5 => self.draw_f5(&painter, ctx, rect),
                    // The only view built from a real widget rather than painted
                    // by hand: F9 wants ordinary prose editing (wrapping,
                    // selection, a caret that behaves), which is exactly what
                    // egui's own multiline box already is.
                    View::F9 => self.draw_f9(ui, rect),
                    View::F10 => self.draw_f10(&painter, rect),
                }
                self.draw_title(&painter, rect);
                if self.voider.backup_prompt.is_some() {
                    self.draw_backup_prompt(&painter, rect);
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

//! voider-rs — a Rust/egui mirror of proto-voider.
//!
//! Parallel to the Python app, which stays untouched: this is a second
//! implementation, built view by view, aiming at 1:1 behaviour. Immediate-mode
//! rendering means we own every pixel and every keystroke — the custom things
//! that fight a widget toolkit (the typewriter caret, scriptio continua) are
//! just "what do I draw this frame?".

mod app;
mod config;
mod f5;
mod fonts;
mod library;
mod paragraphs;
mod line_ring;
mod reformat;
mod split;
mod text_line;
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
    voider: Voider,
}

impl VoiderApp {
    fn new() -> Self {
        Self { voider: app::open_sandbox(), pointer_hidden: true }
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
                egui::Event::Text(t) => match self.voider.view {
                    View::F1 => {
                        let _ = self.voider.type_text(&t, caps);
                    }
                    View::F2 => {
                        self.voider.entry.insert(&text_line::neutralize_caps(&t, caps));
                        let _ = self.voider.doc_live_save();
                    }
                    // In F3 typing only means something while naming a new entry.
                    View::F3 => {
                        if self.voider.pending_new {
                            self.voider.entry.insert(&text_line::neutralize_caps(&t, caps));
                        }
                    }
                    View::F5 | View::F10 => {}
                },
                egui::Event::Key { key, pressed: true, modifiers, .. } => {
                    if self.handle_global_key(key, modifiers) {
                        continue;
                    }
                    match self.voider.view {
                        View::F1 => self.handle_f1_key(key, caps, modifiers),
                        View::F2 => self.handle_f2_key(key, caps, modifiers),
                        View::F3 => self.handle_f3_key(key, modifiers),
                        View::F5 => self.handle_f5_key(key, modifiers),
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
            Key::F5 => self.voider.switch_to(View::F5),
            Key::F10 => self.voider.switch_to(View::F10),
            // Size from anywhere, as the Python has it.
            Key::Plus | Key::Equals if m.ctrl => self.voider.settings_step_size(1),
            Key::Minus if m.ctrl => self.voider.settings_step_size(-1),
            Key::W if m.ctrl && m.shift => {
                self.voider.typewriter = !self.voider.typewriter;
                self.voider.status = format!(
                    "Typewriter {}",
                    if self.voider.typewriter { "ON" } else { "OFF" }
                );
            }
            Key::T if m.ctrl && m.shift => {
                self.voider.show_title = !self.voider.show_title;
            }
            Key::G if m.ctrl && m.shift => self.voider.commit_void(),
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
            // Ctrl+0: make the current line the file's first.
            Key::Num0 if m.ctrl => {
                let _ = self.voider.rebase_to_current();
            }
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
        match key {
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
            Key::Escape if self.voider.para_focus => self.voider.exit_para_focus(),
            Key::Escape => self.voider.switch_to(View::F1),
            _ => {}
        }
    }

    fn handle_f3_key(&mut self, key: egui::Key, m: egui::Modifiers) {
        use egui::Key;
        match key {
            // Shift+Enter opens a blank entry to name; Enter confirms it, or
            // opens the highlighted chapter when we're just browsing.
            Key::Enter if m.shift => self.voider.begin_new_chapter(),
            Key::Enter => {
                if self.voider.pending_new {
                    let _ = self.voider.settle_pending();
                } else {
                    self.voider.open_current_chapter();
                }
            }
            Key::Escape => self.voider.cancel_pending(),
            Key::Backspace => {
                if self.voider.pending_new {
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
    fn draw_f2(&self, painter: &egui::Painter, ctx: &egui::Context, rect: egui::Rect) {
        let centre = rect.center();
        let line_h = self.font_size() * 1.7;
        let font = egui::FontId::proportional(self.font_size());
        let reach = (rect.height() / 2.0 / line_h).ceil() as isize;

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

        if n > 0 {
            for offset in -reach..=reach {
                if offset == 0 && self.voider.pending_new {
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
        if self.voider.pending_new {
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
        self.handle_input(ctx);
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
            .frame(egui::Frame::none().fill(egui::Color32::BLACK))
            .show(ctx, |ui| {
                let rect = ui.max_rect();
                let painter = ui.painter().clone();
                match self.voider.view {
                    View::F1 => self.draw_f1(&painter, ctx, rect),
                    View::F2 => self.draw_f2(&painter, ctx, rect),
                    View::F3 => self.draw_f3(&painter, ctx, rect),
                    View::F5 => self.draw_f5(&painter, ctx, rect),
                    View::F10 => self.draw_f10(&painter, rect),
                }
                self.draw_title(&painter, rect);
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

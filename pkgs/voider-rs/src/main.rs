//! voider-rs — a Rust/egui mirror of proto-voider.
//!
//! Parallel to the Python app, which stays untouched: this is a second
//! implementation, built view by view, aiming at 1:1 behaviour. Immediate-mode
//! rendering means we own every pixel and every keystroke — the custom things
//! that fight a widget toolkit (the typewriter caret, scriptio continua) are
//! just "what do I draw this frame?".

mod app;
mod library;
mod line_ring;
mod text_line;
mod void;

use eframe::egui;

use app::{caps_lock_on, View, Voider};

const FONT_SIZE: f32 = 22.0;
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
        Box::new(|_cc| Ok(Box::new(VoiderApp::new()))),
    )
}

struct VoiderApp {
    voider: Voider,
}

impl VoiderApp {
    fn new() -> Self {
        Self { voider: app::open_sandbox() }
    }

    fn handle_input(&mut self, ctx: &egui::Context) {
        let caps = caps_lock_on();
        let events = ctx.input(|i| i.events.clone());
        for event in events {
            match event {
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
                },
                egui::Event::Key { key, pressed: true, modifiers, .. } => {
                    if self.handle_global_key(key, modifiers) {
                        continue;
                    }
                    match self.voider.view {
                        View::F1 => self.handle_f1_key(key, caps),
                        View::F2 => self.handle_f2_key(key, caps),
                        View::F3 => self.handle_f3_key(key, modifiers),
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
            _ => return false,
        }
        true
    }

    fn handle_f1_key(&mut self, key: egui::Key, caps: bool) {
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

    fn handle_f2_key(&mut self, key: egui::Key, caps: bool) {
        use egui::Key;
        match key {
            Key::Enter => {
                let _ = self.voider.doc_split_line();
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
            Key::ArrowUp => {
                let _ = self.voider.doc_navigate(-1);
            }
            Key::ArrowDown => {
                let _ = self.voider.doc_navigate(1);
            }
            Key::ArrowLeft => self.voider.entry.move_caret(-1),
            Key::ArrowRight => self.voider.entry.move_caret(1),
            Key::Home => self.voider.entry.home(),
            Key::End => self.voider.entry.end(),
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
        let font = egui::FontId::proportional(FONT_SIZE);
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
        let line_h = FONT_SIZE * 1.7;
        let font = egui::FontId::proportional(FONT_SIZE);
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
        let line_h = FONT_SIZE * 1.7;
        let font = egui::FontId::proportional(FONT_SIZE);
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

    fn draw_title(&self, painter: &egui::Painter, rect: egui::Rect) {
        if !self.voider.show_title {
            return;
        }
        let title = app::file_title(&self.voider.current_file).to_uppercase();
        painter.text(
            egui::pos2(rect.center().x, rect.top() + 34.0),
            egui::Align2::CENTER_CENTER,
            title,
            egui::FontId::proportional(FONT_SIZE + 3.0),
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
        self.handle_input(ctx);
        egui::CentralPanel::default()
            .frame(egui::Frame::none().fill(egui::Color32::BLACK))
            .show(ctx, |ui| {
                let rect = ui.max_rect();
                let painter = ui.painter().clone();
                match self.voider.view {
                    View::F1 => self.draw_f1(&painter, ctx, rect),
                    View::F2 => self.draw_f2(&painter, ctx, rect),
                    View::F3 => self.draw_f3(&painter, ctx, rect),
                }
                self.draw_title(&painter, rect);
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

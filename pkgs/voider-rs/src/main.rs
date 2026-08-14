//! voider-rs — a Rust/egui mirror of proto-voider.
//!
//! Parallel to the Python app, which stays untouched: this is a second
//! implementation, built view by view, aiming at 1:1 behaviour. Immediate-mode
//! rendering means we own every pixel and every keystroke — the custom things
//! that fight a widget toolkit (the typewriter caret, scriptio continua) are
//! just "what do I draw this frame?".

mod app;
mod line_ring;
mod text_line;
mod void;

use eframe::egui;

use app::{caps_lock_on, Voider};

const FONT_SIZE: f32 = 22.0;
/// Matches the Python view: the circle inset from the shorter side.
const CIRCLE_INSET: f32 = 35.0;

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

    /// Keys for F1. Text arrives as `Event::Text`, already Caps-applied by the
    /// OS — `type_text` undoes that, and turns the spacebar into "release the
    /// line" while Caps is on (scriptio continua).
    fn handle_input(&mut self, ctx: &egui::Context) {
        let caps = caps_lock_on();
        let events = ctx.input(|i| i.events.clone());
        for event in events {
            match event {
                egui::Event::Text(t) => {
                    let _ = self.voider.type_text(&t, caps);
                }
                egui::Event::Key { key, pressed: true, modifiers, .. } => {
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
                        // Ring navigation mirrors the entry, as F1 does.
                        Key::ArrowUp => {
                            self.voider.ring.move_by(-1);
                            self.voider.show_current();
                        }
                        Key::ArrowDown => {
                            self.voider.ring.move_by(1);
                            self.voider.show_current();
                        }
                        Key::W if modifiers.ctrl && modifiers.shift => {
                            self.voider.typewriter = !self.voider.typewriter;
                            self.voider.status = format!(
                                "Typewriter {}",
                                if self.voider.typewriter { "ON" } else { "OFF" }
                            );
                        }
                        Key::G if modifiers.ctrl && modifiers.shift => {
                            self.voider.commit_void();
                        }
                        _ => {}
                    }
                }
                _ => {}
            }
        }
    }

    fn draw_f1(&self, ui: &egui::Ui, ctx: &egui::Context) {
        let painter = ui.painter();
        let rect = ui.max_rect();
        let center = rect.center();
        let radius = (rect.width().min(rect.height())) / 2.0 - CIRCLE_INSET;

        painter.circle_stroke(
            center,
            radius,
            egui::Stroke::new(10.0_f32, egui::Color32::WHITE),
        );

        let font = egui::FontId::proportional(FONT_SIZE);
        let text = self.voider.entry.text();
        let before = self.voider.entry.before_caret();
        // Lay out both halves to know where the caret falls inside the line.
        let galley = ctx.fonts(|f| {
            f.layout_no_wrap(text.clone(), font.clone(), egui::Color32::WHITE)
        });
        let before_w = ctx.fonts(|f| {
            f.layout_no_wrap(before, font.clone(), egui::Color32::WHITE)
                .size()
                .x
        });

        // Typewriter: place the line so the caret lands exactly on the centre —
        // then the caret never moves and the text slides under it, including
        // when the arrows walk through the line. Classic: plain centred text.
        let left_x = if self.voider.typewriter {
            center.x - before_w
        } else {
            center.x - galley.size().x / 2.0
        };
        let top_y = center.y - galley.size().y / 2.0;

        // Nothing may show outside the circle.
        let band = egui::Rect::from_min_max(
            egui::pos2(center.x - radius, rect.top()),
            egui::pos2(center.x + radius, rect.bottom()),
        );
        let clipped = painter.with_clip_rect(band);
        let galley_size = galley.size();
        clipped.galley(egui::pos2(left_x, top_y), galley, egui::Color32::WHITE);

        // The caret blinks only while the line is empty; once there is text it
        // holds still, so the last letter typed is the thing you look at.
        let caret_x = left_x + before_w;
        let blinking = self.voider.entry.is_empty();
        let visible = !blinking || (ctx.input(|i| i.time) * 1.6).sin() > 0.0;
        if visible {
            clipped.line_segment(
                [
                    egui::pos2(caret_x, top_y + 2.0),
                    egui::pos2(caret_x, top_y + galley_size.y - 2.0),
                ],
                egui::Stroke::new(2.0_f32, egui::Color32::WHITE),
            );
        }
        if blinking {
            ctx.request_repaint_after(std::time::Duration::from_millis(120));
        }

        if !self.voider.status.is_empty() {
            painter.text(
                egui::pos2(center.x, rect.bottom() - 24.0),
                egui::Align2::CENTER_CENTER,
                &self.voider.status,
                egui::FontId::proportional(13.0),
                egui::Color32::from_gray(90),
            );
        }
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
            .show(ctx, |ui| self.draw_f1(ui, ctx));
    }
}

//! voider-rs — a Rust/egui mirror of proto-voider.
//!
//! Parallel to the Python app, which stays untouched: this is a second
//! implementation, built view by view, aiming at 1:1 behaviour. Immediate-mode
//! rendering means we own every pixel and every keystroke — the custom things
//! that fight a widget toolkit (the typewriter caret, scriptio continua) are
//! just "what do I draw this frame?".
//!
//! M0: it compiles, it opens a black window. The data layer, /void and the
//! views come next.

mod line_ring;
mod void;

use eframe::egui;

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
        Box::new(|_cc| Ok(Box::<VoiderApp>::default())),
    )
}

#[derive(Default)]
struct VoiderApp {}

impl eframe::App for VoiderApp {
    /// Voider is black: paint the window background black rather than egui's grey.
    fn clear_color(&self, _visuals: &egui::Visuals) -> [f32; 4] {
        [0.0, 0.0, 0.0, 1.0]
    }

    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        egui::CentralPanel::default()
            .frame(egui::Frame::none().fill(egui::Color32::BLACK))
            .show(ctx, |ui| {
                let rect = ui.max_rect();
                // A single centred glyph — the same "nothing here yet" mark the
                // Python views use.
                ui.painter().text(
                    rect.center(),
                    egui::Align2::CENTER_CENTER,
                    "ø",
                    egui::FontId::proportional(48.0),
                    egui::Color32::from_gray(45),
                );
            });
    }
}

//! Settings that outlive a run: the font, its size, and the toggles.
//!
//! Kept as a small JSON-ish file written atomically like everything else. It is
//! hand-parsed rather than pulling in serde: the file is a handful of flat keys
//! and a writer's settings file should stay readable and repairable by hand.

#![allow(dead_code)]

use std::path::{Path, PathBuf};

use crate::void;

#[derive(Debug, Clone, PartialEq)]
pub struct Config {
    pub font_family: String,
    pub font_size: f32,
    pub typewriter: bool,
    pub show_title: bool,
    /// The last restorable view (F1/F2/F3), so a restart resumes there rather
    /// than always opening on F1.
    pub last_view: Option<String>,
    /// The file that was active when `last_view` was saved.
    pub active_file: Option<String>,
    /// Where the PDF + EPUB + TXT sale bundle goes, by language. Empty (the
    /// default) means the local `gPTA_books` folder inside the void.
    pub sale_bundle_dir_es: String,
    pub sale_bundle_dir_en: String,
    /// The carousel's frame: a preset name (`1:1`, `4:5`, `1.91:1`) or `custom`,
    /// which takes `carousel_w` × `carousel_h`.
    pub carousel_preset: String,
    pub carousel_w: u32,
    pub carousel_h: u32,
    /// How the book and the slides are hyphenated: `auto` (each paragraph's language
    /// is guessed), a language (`es`, `en`), or empty for none. The Python's
    /// `reading_hyphen_lang`.
    pub reading_hyphen_lang: String,
    /// The font and size F4's book (and its PDF, and the carousel) is set in —
    /// not the writing font. The Python's `reading_font` / `reading_size`.
    pub reading_font: String,
    pub reading_size: f32,
    /// Where F3's cursor was left — by index and by name, so it survives a
    /// restart and a reorder (the Python's `last_book_index` / `last_book_entry`).
    pub last_book_index: Option<usize>,
    pub last_book_entry: Option<String>,
    /// What releases a line in F1: `enter` (default; the spacebar too with Caps
    /// on) or `space` (the spacebar always) — the Python's `void_key`.
    pub void_key: String,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            font_family: "EB Garamond".to_string(),
            font_size: 22.0,
            typewriter: false,
            show_title: false,
            last_view: None,
            active_file: None,
            sale_bundle_dir_es: String::new(),
            sale_bundle_dir_en: String::new(),
            carousel_preset: crate::carousel::DEFAULT_PRESET.to_string(),
            carousel_w: 1080,
            carousel_h: 1350,
            reading_hyphen_lang: "auto".to_string(),
            reading_font: "EB Garamond".to_string(),
            reading_size: 13.0,
            last_book_index: None,
            last_book_entry: None,
            void_key: "enter".to_string(),
        }
    }
}

pub fn config_path(void_dir: &Path) -> PathBuf {
    void_dir.join("voider-rs.conf")
}


// Los tamaños que ofrece F10. Sin tope arbitrario arriba: si querés la letra
// enorme, es tu pantalla y tu texto — y desde que el espaciado sigue a la fuente,
// agrandar ya no rompe la vista.
pub const SIZES: [f32; 17] = [
    11.0, 13.0, 15.0, 17.0, 19.0, 22.0, 26.0, 30.0, 33.0, 38.0, 44.0, 52.0,
    64.0, 80.0, 100.0, 130.0, 170.0,
];

impl Config {
    pub fn load(void_dir: &Path) -> Self {
        match std::fs::read_to_string(config_path(void_dir)) {
            Ok(text) => {
                let lines: Vec<String> = text.lines().map(str::to_string).collect();
                Self::from_lines(&lines)
            }
            Err(_) => Self::default(),
        }
    }

    pub fn save(&self, void_dir: &Path) -> std::io::Result<()> {
        void::atomic_write(&config_path(void_dir), &self.to_lines(), false)
    }

    /// Serialise to the lines that go on disk.
    pub fn to_lines(&self) -> Vec<String> {
        let mut lines = vec![
            format!("font_family = {}", self.font_family),
            format!("font_size = {}", self.font_size),
            format!("typewriter = {}", self.typewriter),
            format!("show_title = {}", self.show_title),
        ];
        if let Some(v) = &self.last_view {
            lines.push(format!("last_view = {v}"));
        }
        if let Some(f) = &self.active_file {
            lines.push(format!("active_file = {f}"));
        }
        if !self.sale_bundle_dir_es.is_empty() {
            lines.push(format!("sale_bundle_dir_es = {}", self.sale_bundle_dir_es));
        }
        if !self.sale_bundle_dir_en.is_empty() {
            lines.push(format!("sale_bundle_dir_en = {}", self.sale_bundle_dir_en));
        }
        if self.carousel_preset != crate::carousel::DEFAULT_PRESET {
            lines.push(format!("carousel_preset = {}", self.carousel_preset));
        }
        if self.reading_hyphen_lang != "auto" {
            // Written even when empty: an empty value is how hyphenation is turned off.
            lines.push(format!("reading_hyphen_lang = {}", self.reading_hyphen_lang));
        }
        if self.reading_font != "EB Garamond" {
            lines.push(format!("reading_font = {}", self.reading_font));
        }
        if self.reading_size != 13.0 {
            lines.push(format!("reading_size = {}", self.reading_size));
        }
        if self.void_key != "enter" {
            lines.push(format!("void_key = {}", self.void_key));
        }
        if let Some(i) = self.last_book_index {
            lines.push(format!("last_book_index = {i}"));
        }
        if let Some(e) = &self.last_book_entry {
            lines.push(format!("last_book_entry = {e}"));
        }
        if self.carousel_w != 1080 {
            lines.push(format!("carousel_w = {}", self.carousel_w));
        }
        if self.carousel_h != 1350 {
            lines.push(format!("carousel_h = {}", self.carousel_h));
        }
        lines
    }

    /// Parse from the lines on disk; anything missing or malformed keeps its
    /// default, so a damaged file can never stop Voider from opening.
    pub fn from_lines(lines: &[String]) -> Self {
        let mut c = Self::default();
        for line in lines {
            let Some((key, value)) = line.split_once('=') else {
                continue;
            };
            let value = value.trim();
            match key.trim() {
                "font_family" if !value.is_empty() => c.font_family = value.to_string(),
                "font_size" => {
                    if let Ok(v) = value.parse::<f32>() {
                        if v > 0.0 {
                            c.font_size = v;
                        }
                    }
                }
                "typewriter" => c.typewriter = value == "true",
                "show_title" => c.show_title = value == "true",
                "last_view" if !value.is_empty() => c.last_view = Some(value.to_string()),
                "active_file" if !value.is_empty() => c.active_file = Some(value.to_string()),
                "sale_bundle_dir_es" => c.sale_bundle_dir_es = value.to_string(),
                "sale_bundle_dir_en" => c.sale_bundle_dir_en = value.to_string(),
                "reading_hyphen_lang" => c.reading_hyphen_lang = value.to_string(),
                "last_book_index" => c.last_book_index = value.parse().ok(),
                "void_key" if !value.is_empty() => c.void_key = value.to_string(),
                "reading_font" if !value.is_empty() => c.reading_font = value.to_string(),
                "reading_size" => {
                    if let Ok(v) = value.parse::<f32>() {
                        if v > 0.0 {
                            c.reading_size = v;
                        }
                    }
                }
                "last_book_entry" if !value.is_empty() => c.last_book_entry = Some(value.to_string()),
                "carousel_preset" if !value.is_empty() => c.carousel_preset = value.to_string(),
                "carousel_w" => {
                    if let Ok(v) = value.parse::<u32>() {
                        if v > 0 {
                            c.carousel_w = v;
                        }
                    }
                }
                "carousel_h" => {
                    if let Ok(v) = value.parse::<u32>() {
                        if v > 0 {
                            c.carousel_h = v;
                        }
                    }
                }
                _ => {}
            }
        }
        c
    }

    /// Step to the next/previous offered size, from the nearest one listed.
    pub fn step_size(&mut self, delta: isize) {
        let nearest = SIZES
            .iter()
            .enumerate()
            .min_by(|(_, a), (_, b)| {
                (*a - self.font_size)
                    .abs()
                    .total_cmp(&(*b - self.font_size).abs())
            })
            .map(|(i, _)| i)
            .unwrap_or(0);
        let i = (nearest as isize + delta).clamp(0, SIZES.len() as isize - 1) as usize;
        self.font_size = SIZES[i];
    }

}

#[cfg(test)]
mod tests {
    use super::*;

    fn v(lines: &[&str]) -> Vec<String> {
        lines.iter().map(|s| s.to_string()).collect()
    }

    // Where the sale bundle lands, per language. Empty by default: they are
    // absolute paths to one machine's site checkout, meaningless on anyone else's
    // (test_sale_bundle.py), so unset means "use the local fallback".

    // Hyphenation of the book and the slides: `auto` (the language of each
    // paragraph is guessed), a language, or empty for none.

    #[test]
    fn the_book_hyphenates_automatically_by_default() {
        assert_eq!(Config::default().reading_hyphen_lang, "auto");
    }

    #[test]
    fn the_hyphenation_setting_is_read_back_and_an_empty_one_means_none() {
        let mut c = Config::default();
        assert!(!c.to_lines().iter().any(|l| l.starts_with("reading_hyphen_lang")), "the default is not written");
        c.reading_hyphen_lang = "en_US".into();
        assert_eq!(Config::from_lines(&c.to_lines()).reading_hyphen_lang, "en_US");
        c.reading_hyphen_lang = String::new();
        assert_eq!(Config::from_lines(&c.to_lines()).reading_hyphen_lang, "", "off survives a round trip");
    }

    // The carousel's frame: a named preset, or "custom" with its own size.

    #[test]
    fn the_carousel_defaults_to_the_4_5_frame() {
        let c = Config::default();
        assert_eq!(c.carousel_preset, "4:5");
        assert_eq!((c.carousel_w, c.carousel_h), (1080, 1350));
    }

    #[test]
    fn the_carousel_frame_is_read_back_and_a_nonsense_size_is_ignored() {
        let mut c = Config::default();
        c.carousel_preset = "1:1".into();
        c.carousel_w = 800;
        c.carousel_h = 600;
        let back = Config::from_lines(&c.to_lines());
        assert_eq!((back.carousel_preset.as_str(), back.carousel_w, back.carousel_h), ("1:1", 800, 600));
        let bad = Config::from_lines(&["carousel_w = abc".to_string(), "carousel_h = 0".to_string()]);
        assert_eq!((bad.carousel_w, bad.carousel_h), (1080, 1350)); // kept the defaults
    }

    #[test]
    fn the_sale_bundle_folders_are_empty_until_configured() {
        let c = Config::default();
        assert_eq!(c.sale_bundle_dir_es, "");
        assert_eq!(c.sale_bundle_dir_en, "");
    }

    #[test]
    fn an_empty_sale_bundle_folder_is_not_written_and_a_set_one_is_read_back() {
        let mut c = Config::default();
        assert!(!c.to_lines().iter().any(|l| l.starts_with("sale_bundle_dir")));
        c.sale_bundle_dir_es = "/a b/libros".into();
        let back = Config::from_lines(&c.to_lines());
        assert_eq!(back.sale_bundle_dir_es, "/a b/libros");
        assert_eq!(back.sale_bundle_dir_en, "");
    }

    #[test]
    fn defaults_are_the_writing_font() {
        let c = Config::default();
        assert_eq!(c.font_family, "EB Garamond");
        assert_eq!(c.font_size, 22.0);
        assert!(!c.typewriter);
    }

    #[test]
    fn it_roundtrips_through_disk() {
        let d = tempfile::tempdir().unwrap();
        let c = Config {
            font_family: "Consolas".into(),
            font_size: 33.0,
            typewriter: true,
            show_title: true,
            last_view: Some("F2".into()),
            active_file: Some("Capitulo.txt".into()),
            sale_bundle_dir_es: "/srv/sitio/libros".into(),
            sale_bundle_dir_en: "/srv/sitio/books".into(),
            carousel_preset: "custom".into(),
            carousel_w: 800,
            carousel_h: 600,
            reading_hyphen_lang: "es_ES".into(),
            last_book_index: Some(444),
            last_book_entry: Some("ATTACK BY DRAWING.txt".into()),
            void_key: "space".into(),
            reading_font: "Consolas".into(),
            reading_size: 14.0,
        };
        c.save(d.path()).unwrap();
        assert_eq!(Config::load(d.path()), c);
    }

    #[test]
    fn last_view_and_active_file_default_to_nothing_saved() {
        let c = Config::default();
        assert_eq!(c.last_view, None);
        assert_eq!(c.active_file, None);
    }

    #[test]
    fn a_missing_file_gives_the_defaults() {
        let d = tempfile::tempdir().unwrap();
        assert_eq!(Config::load(d.path()), Config::default());
    }

    #[test]
    fn a_damaged_file_keeps_the_defaults_it_cannot_read() {
        let c = Config::from_lines(&v(&["font_size = no-soy-un-numero", "basura", "font_family = Times"]));
        assert_eq!(c.font_family, "Times"); // the good key survives
        assert_eq!(c.font_size, Config::default().font_size); // the bad one falls back
    }

    #[test]
    fn a_font_name_with_spaces_survives() {
        let c = Config::from_lines(&v(&["font_family = EB Garamond"]));
        assert_eq!(c.font_family, "EB Garamond");
    }

    #[test]
    fn stepping_walks_the_offered_sizes_and_stops() {
        let mut c = Config { font_size: 22.0, ..Default::default() };
        c.step_size(1);
        assert_eq!(c.font_size, 26.0);
        c.step_size(-1);
        assert_eq!(c.font_size, 22.0);
        c.font_size = SIZES[0];
        c.step_size(-1);
        assert_eq!(c.font_size, SIZES[0]); // clamped, no wrap
        c.font_size = SIZES[SIZES.len() - 1];
        c.step_size(1);
        assert_eq!(c.font_size, SIZES[SIZES.len() - 1]);
    }

    #[test]
    fn an_unlisted_size_steps_from_the_nearest() {
        let mut c = Config { font_size: 23.0, ..Default::default() };
        c.step_size(1);
        assert_eq!(c.font_size, 26.0); // nearest is 22 → next is 26
    }
}

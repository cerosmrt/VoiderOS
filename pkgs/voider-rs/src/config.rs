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
    /// How solid the ground is, 0.3–1.0. Ctrl+± moves it.
    pub opacity: f32,
    /// The last restorable view (F1/F2/F3), so a restart resumes there rather
    /// than always opening on F1.
    pub last_view: Option<String>,
    /// The file that was active when `last_view` was saved.
    pub active_file: Option<String>,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            font_family: "EB Garamond".to_string(),
            font_size: 22.0,
            typewriter: false,
            show_title: false,
            opacity: 1.0,
            last_view: None,
            active_file: None,
        }
    }
}

pub fn config_path(void_dir: &Path) -> PathBuf {
    void_dir.join("voider-rs.conf")
}

/// The sizes the settings panel offers.
pub const SIZES: [f32; 12] = [
    11.0, 13.0, 15.0, 17.0, 19.0, 22.0, 26.0, 30.0, 33.0, 38.0, 44.0, 52.0,
];

/// How thin the ground may get. Never 0: a window you cannot see is a window
/// you cannot get back, and the keys to restore it would be invisible too.
pub const OPACITY_MIN: f32 = 0.3;

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
            format!("opacity = {}", self.opacity),
        ];
        if let Some(v) = &self.last_view {
            lines.push(format!("last_view = {v}"));
        }
        if let Some(f) = &self.active_file {
            lines.push(format!("active_file = {f}"));
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
                "opacity" => {
                    if let Ok(v) = value.parse::<f32>() {
                        c.opacity = v.clamp(OPACITY_MIN, 1.0);
                    }
                }
                "last_view" if !value.is_empty() => c.last_view = Some(value.to_string()),
                "active_file" if !value.is_empty() => c.active_file = Some(value.to_string()),
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

    /// Ctrl+± : thin the ground out or fill it back in, a tenth at a time.
    pub fn step_opacity(&mut self, delta: f32) {
        self.opacity = (self.opacity + delta).clamp(OPACITY_MIN, 1.0);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn v(lines: &[&str]) -> Vec<String> {
        lines.iter().map(|s| s.to_string()).collect()
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
            opacity: 0.6,
            last_view: Some("F2".into()),
            active_file: Some("Capitulo.txt".into()),
        };
        c.save(d.path()).unwrap();
        assert_eq!(Config::load(d.path()), c);
    }

    #[test]
    fn opacity_steps_but_never_reaches_invisible() {
        let mut c = Config::default();
        assert_eq!(c.opacity, 1.0);
        c.step_opacity(-0.1);
        assert!((c.opacity - 0.9).abs() < 1e-6);
        for _ in 0..30 {
            c.step_opacity(-0.1);
        }
        // A window you cannot see is a window you cannot get back.
        assert_eq!(c.opacity, OPACITY_MIN);
        for _ in 0..30 {
            c.step_opacity(0.1);
        }
        assert_eq!(c.opacity, 1.0);
    }

    #[test]
    fn a_saved_opacity_of_zero_is_refused_on_the_way_back_in() {
        let c = Config::from_lines(&v(&["opacity = 0"]));
        assert_eq!(c.opacity, OPACITY_MIN);
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

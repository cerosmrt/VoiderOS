//! The sale bundle: a book as PDF + EPUB + TXT, everything needed to put it up
//! for sale in one place.
//!
//! The pure half of `export_sale_bundle` in `f4_mixin.py` — the TXT, the
//! language, and where the three files land. Writing them is `Voider`'s job.

#![allow(dead_code)]

use std::path::{Path, PathBuf};

use crate::config::Config;

/// The language a book is in. The destination is split by language, and Voider
/// cannot guess it from the text.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Lang {
    Es,
    En,
}

impl Lang {
    /// What the prompt offers, in its own words.
    pub const ALL: [Lang; 2] = [Lang::Es, Lang::En];

    pub fn label(self) -> &'static str {
        match self {
            Lang::Es => "Español",
            Lang::En => "English",
        }
    }

    /// The BCP 47 code the EPUB declares.
    pub fn code(self) -> &'static str {
        match self {
            Lang::Es => "es",
            Lang::En => "en",
        }
    }
}

/// The TXT half of the bundle. One chapter is just its own raw lines — the file
/// as it already is in `I/`, still importable into someone else's Voider. A
/// whole book joins its chapters with `/chapter-name` fences, the same marker
/// Voider's own split and dispatch use, not a new format.
pub fn sections_as_txt(sections: &[(String, Vec<String>)]) -> String {
    let mut out: Vec<String> = Vec::new();
    if let [(_, only)] = sections {
        out.extend(only.iter().cloned());
    } else {
        for (name, lines) in sections {
            out.push(format!("/{name}"));
            out.extend(lines.iter().cloned());
        }
    }
    let mut txt = out.join("\n");
    txt.push('\n');
    txt
}

/// A typed name made safe to be ONE folder: path separators and control
/// characters become `-`, and a name that is nothing but dots (`.`, `..`) or blank
/// comes back empty, which the exporters treat as "no name". Without this a
/// `../x` typed at the prompt would write outside the folder it was meant for.
pub fn safe_folder_name(name: &str) -> String {
    let cleaned: String = name
        .trim()
        .chars()
        .map(|c| if c == '/' || c == '\\' || c.is_control() { '-' } else { c })
        .collect();
    let cleaned = cleaned.trim().to_string();
    if cleaned.chars().all(|c| c == '.') {
        String::new()
    } else {
        cleaned
    }
}

/// Where the bundle for `out_name` lands: the folder configured for `lang`, or —
/// when that is empty, as it is on anyone else's machine — `gPTA_books` inside
/// the void.
pub fn bundle_dir(void_dir: &Path, config: &Config, lang: Lang, out_name: &str) -> PathBuf {
    let configured = match lang {
        Lang::Es => &config.sale_bundle_dir_es,
        Lang::En => &config.sale_bundle_dir_en,
    }
    .trim();
    let base = if configured.is_empty() {
        void_dir.join("gPTA_books")
    } else {
        PathBuf::from(configured)
    };
    base.join(out_name)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn lines(v: &[&str]) -> Vec<String> {
        v.iter().map(|s| s.to_string()).collect()
    }

    // ── the TXT (TestSectionsAsTxt) ──────────────────────────────────────────

    #[test]
    fn a_single_section_is_its_raw_lines_unchanged() {
        let secs = vec![("A".to_string(), lines(&["Primera linea.", ".", "Segunda linea."]))];
        assert_eq!(sections_as_txt(&secs), "Primera linea.\n.\nSegunda linea.\n");
    }

    #[test]
    fn several_sections_get_name_fences_between_them() {
        let secs = vec![
            ("Uno".to_string(), lines(&["linea uno."])),
            ("Dos".to_string(), lines(&["linea dos."])),
        ];
        let txt = sections_as_txt(&secs);
        assert_eq!(txt, "/Uno\nlinea uno.\n/Dos\nlinea dos.\n");
    }

    #[test]
    fn a_book_split_back_on_its_fences_gets_its_chapters_again() {
        // The fences are the very marker `/name` seals below, so the TXT of a
        // whole book re-splits into the same chapters.
        let secs = vec![
            ("Uno".to_string(), lines(&["a.", "b."])),
            ("Dos".to_string(), lines(&["c."])),
        ];
        let split = crate::split::plan(&sections_as_txt(&secs).lines().map(str::to_string).collect::<Vec<_>>()).unwrap();
        assert_eq!(split.sealed[0].name, "Uno");
        assert_eq!(split.sealed[0].lines, lines(&["a.", "b."]));
        assert_eq!(split.sealed[1].name, "Dos");
        assert_eq!(split.sealed[1].lines, lines(&["c."]));
    }

    // ── language and destination (TestLanguageAndDestination) ────────────────

    fn cfg(es: &str, en: &str) -> Config {
        Config {
            sale_bundle_dir_es: es.to_string(),
            sale_bundle_dir_en: en.to_string(),
            ..Config::default()
        }
    }

    #[test]
    fn unconfigured_falls_back_to_gpta_books_inside_the_void() {
        let d = bundle_dir(Path::new("/v"), &cfg("", ""), Lang::En, "A");
        assert_eq!(d, Path::new("/v/gPTA_books/A"));
        let d = bundle_dir(Path::new("/v"), &cfg("", ""), Lang::Es, "A");
        assert_eq!(d, Path::new("/v/gPTA_books/A"));
    }

    #[test]
    fn spanish_uses_the_configured_es_folder() {
        let d = bundle_dir(Path::new("/v"), &cfg("/sitio/libros", ""), Lang::Es, "A");
        assert_eq!(d, Path::new("/sitio/libros/A"));
    }

    #[test]
    fn english_uses_the_configured_en_folder() {
        let d = bundle_dir(Path::new("/v"), &cfg("", "/sitio/books"), Lang::En, "A");
        assert_eq!(d, Path::new("/sitio/books/A"));
    }

    #[test]
    fn configuring_only_english_still_falls_back_for_spanish() {
        let d = bundle_dir(Path::new("/v"), &cfg("", "/sitio/books"), Lang::Es, "A");
        assert_eq!(d, Path::new("/v/gPTA_books/A"));
    }

    #[test]
    fn a_folder_of_only_spaces_counts_as_not_configured() {
        let d = bundle_dir(Path::new("/v"), &cfg("   ", ""), Lang::Es, "A");
        assert_eq!(d, Path::new("/v/gPTA_books/A"));
    }

    // ── a typed name stays one folder ────────────────────────────────────────

    #[test]
    fn an_ordinary_name_is_untouched() {
        assert_eq!(safe_folder_name("Mi Libro"), "Mi Libro");
        assert_eq!(safe_folder_name("Capítulo 1: el principio"), "Capítulo 1: el principio");
    }

    #[test]
    fn path_separators_cannot_climb_out_of_the_folder() {
        assert_eq!(safe_folder_name("../../etc/x"), "..-..-etc-x");
        assert_eq!(safe_folder_name("a\\b"), "a-b");
        assert!(!safe_folder_name("../x").contains('/'));
    }

    #[test]
    fn a_name_of_only_dots_or_blanks_is_no_name() {
        assert_eq!(safe_folder_name(".."), "");
        assert_eq!(safe_folder_name("."), "");
        assert_eq!(safe_folder_name("   "), "");
        assert_eq!(safe_folder_name(""), "");
    }

    #[test]
    fn surrounding_space_is_trimmed() {
        assert_eq!(safe_folder_name("  Libro  "), "Libro");
    }

    #[test]
    fn the_language_knows_its_label_and_code() {
        assert_eq!(Lang::Es.label(), "Español");
        assert_eq!(Lang::En.code(), "en");
    }
}

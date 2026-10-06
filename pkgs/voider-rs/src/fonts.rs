//! Finding the writing font on disk.
//!
//! egui needs the actual bytes of a font, so a family name like "EB Garamond"
//! has to be resolved to a file. Rather than pull in a font-config crate, we
//! walk the usual font directories and match on the file name — enough for the
//! handful of families a writer picks, and it fails softly to egui's built-in.

#![allow(dead_code)]

use std::path::{Path, PathBuf};

/// Where fonts live on this kind of system, nearest first.
fn font_dirs() -> Vec<PathBuf> {
    let mut dirs = Vec::new();
    if let Ok(home) = std::env::var("HOME") {
        dirs.push(Path::new(&home).join(".local/share/fonts"));
        dirs.push(Path::new(&home).join(".fonts"));
    }
    dirs.push(PathBuf::from("/run/current-system/sw/share/fonts"));
    dirs.push(PathBuf::from("/usr/share/fonts"));
    // Windows keeps them elsewhere; these are empty off Windows (no such variables).
    dirs.extend(windows_font_dirs(
        std::env::var("windir").ok().as_deref(),
        std::env::var("LOCALAPPDATA").ok().as_deref(),
    ));
    dirs
}

/// "EB Garamond" → "ebgaramond": what a file name looks like once the spaces,
/// dashes and case are gone.
pub fn normalise(name: &str) -> String {
    name.chars()
        .filter(|c| c.is_alphanumeric())
        .flat_map(char::to_lowercase)
        .collect()
}

/// True if `file_name` looks like the regular (not italic/bold) face of `family`.
pub fn is_regular_face(file_name: &str, family: &str) -> bool {
    let f = normalise(file_name);
    if !f.starts_with(&normalise(family)) {
        return false;
    }
    // Skip the decorative and slanted cuts — we want the reading face.
    const AVOID: [&str; 6] = ["italic", "bold", "initials", "smallcap", "sc12", "oblique"];
    !AVOID.iter().any(|bad| f.contains(bad))
}

/// Where fonts live on Windows: the system's, and the per-user ones. Pure, so it can
/// be checked anywhere: it is given the two environment values.
pub fn windows_font_dirs(windir: Option<&str>, local_app_data: Option<&str>) -> Vec<PathBuf> {
    let mut dirs = Vec::new();
    if let Some(w) = windir {
        dirs.push(Path::new(w).join("Fonts"));
    }
    if let Some(l) = local_app_data {
        dirs.push(Path::new(l).join("Microsoft").join("Windows").join("Fonts"));
    }
    dirs
}

/// EB Garamond, inside the program.
static EB_GARAMOND_REGULAR: &[u8] = include_bytes!("../assets/EBGaramond12-Regular.ttf");

/// EB Garamond travels inside the program, so a machine without it (a fresh
/// Windows, say) still draws the book's own letters instead of falling back to
/// whatever face the toolkit has.
pub fn bundled_family(family: &str) -> Option<&'static [u8]> {
    let n = normalise(family);
    (!n.is_empty() && n.starts_with("ebgaramond")).then_some(EB_GARAMOND_REGULAR)
}

/// The bytes of the regular face of `family`, if it can be found.
pub fn load_family(family: &str) -> Option<Vec<u8>> {
    load_family_from(family, &font_dirs())
}

/// Like `load_family`, over the given folders; and when the family is not found, the
/// bundled one if that is what was asked for.
pub fn load_family_from(family: &str, dirs: &[PathBuf]) -> Option<Vec<u8>> {
    let mut fallback: Option<PathBuf> = None;
    for dir in dirs {
        for path in walk(dir, 0) {
            let Some(name) = path.file_name().map(|n| n.to_string_lossy().to_string()) else {
                continue;
            };
            let ext = path
                .extension()
                .map(|e| e.to_string_lossy().to_lowercase())
                .unwrap_or_default();
            if ext != "ttf" && ext != "otf" {
                continue;
            }
            if is_regular_face(&name, family) {
                return std::fs::read(&path).ok();
            }
            // Any face of the family beats no family at all.
            if fallback.is_none() && normalise(&name).starts_with(&normalise(family)) {
                fallback = Some(path);
            }
        }
    }
    fallback
        .and_then(|p| std::fs::read(p).ok())
        .or_else(|| bundled_family(family).map(<[u8]>::to_vec))
}

/// Family names we can offer in the settings panel: whatever is installed,
/// deduplicated and sorted, with egui's built-in always available.
pub fn available_families() -> Vec<String> {
    available_families_in(&font_dirs())
}

/// Like `available_families`, over the given folders. EB Garamond is always offered:
/// it is bundled.
pub fn available_families_in(dirs: &[PathBuf]) -> Vec<String> {
    let mut names: Vec<String> = Vec::new();
    for dir in dirs {
        for path in walk(dir, 0) {
            let ext = path
                .extension()
                .map(|e| e.to_string_lossy().to_lowercase())
                .unwrap_or_default();
            if ext != "ttf" && ext != "otf" {
                continue;
            }
            if let Some(stem) = path.file_stem().map(|s| s.to_string_lossy().to_string()) {
                let family = family_of(&stem);
                if !family.is_empty() && !names.iter().any(|n| normalise(n) == normalise(&family)) {
                    names.push(family);
                }
            }
        }
    }
    if !names.iter().any(|n| normalise(n).starts_with("ebgaramond")) {
        names.push("EB Garamond".to_string());
    }
    names.sort();
    names.insert(0, "Default".to_string());
    names
}

/// "EBGaramond12-Regular" → "EBGaramond12": the part before the face suffix.
fn family_of(stem: &str) -> String {
    stem.split(['-', '_'])
        .next()
        .unwrap_or(stem)
        .trim()
        .to_string()
}

/// Files under `dir`, one level of nesting deep (fonts sit in per-family folders).
fn walk(dir: &Path, depth: usize) -> Vec<PathBuf> {
    let mut out = Vec::new();
    let Ok(entries) = std::fs::read_dir(dir) else {
        return out;
    };
    for e in entries.flatten() {
        let p = e.path();
        if p.is_dir() {
            if depth < 3 {
                out.extend(walk(&p, depth + 1));
            }
        } else {
            out.push(p);
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn names_normalise_to_their_file_form() {
        assert_eq!(normalise("EB Garamond"), "ebgaramond");
        assert_eq!(normalise("EBGaramond12"), "ebgaramond12");
        assert_eq!(normalise("Fira-Code"), "firacode");
    }

    #[test]
    fn the_regular_face_is_the_one_we_want() {
        assert!(is_regular_face("EBGaramond12-Regular.ttf", "EB Garamond"));
        assert!(is_regular_face("EBGaramond-Regular.otf", "EBGaramond"));
        // the cuts a reader shouldn't get by default
        assert!(!is_regular_face("EBGaramond12-Italic.ttf", "EB Garamond"));
        assert!(!is_regular_face("EBGaramond-Bold.ttf", "EB Garamond"));
        assert!(!is_regular_face("EBGaramond-InitialsF2.ttf", "EB Garamond"));
        assert!(!is_regular_face("EBGaramondSC12-Regular.ttf", "EB Garamond"));
        // a different family entirely
        assert!(!is_regular_face("FiraCode-Regular.ttf", "EB Garamond"));
    }

    #[test]
    fn a_family_is_the_part_before_the_face() {
        assert_eq!(family_of("EBGaramond12-Regular"), "EBGaramond12");
        assert_eq!(family_of("FiraCode_Bold"), "FiraCode");
        assert_eq!(family_of("Simple"), "Simple");
    }

    // ── a machine without the font (a fresh Windows) ─────────────────────────

    #[test]
    fn eb_garamond_is_bundled_under_any_spelling_and_nothing_else_is() {
        for name in ["EB Garamond", "EBGaramond", "ebgaramond12", "eb-garamond"] {
            assert!(bundled_family(name).is_some(), "{name}");
        }
        assert!(bundled_family("Consolas").is_none());
        assert!(bundled_family("").is_none());
    }

    #[test]
    fn the_bundled_bytes_are_a_real_font() {
        let bytes = bundled_family("EB Garamond").unwrap();
        assert!(bytes.len() > 100_000);
        assert!(crate::typeset::TypeFont::from_bytes(bytes.to_vec()).is_some());
    }

    #[test]
    fn with_no_font_folders_at_all_eb_garamond_is_still_found() {
        let got = load_family_from("EB Garamond", &[]).expect("falls back to the bundled one");
        assert_eq!(got.as_slice(), bundled_family("EB Garamond").unwrap());
    }

    #[test]
    fn another_family_that_is_missing_stays_missing() {
        assert!(load_family_from("Consolas", &[]).is_none());
    }

    #[test]
    fn an_installed_font_wins_over_the_bundled_one() {
        let d = tempfile::tempdir().unwrap();
        std::fs::write(d.path().join("EBGaramond12-Regular.ttf"), b"installed").unwrap();
        let got = load_family_from("EB Garamond", &[d.path().to_path_buf()]).unwrap();
        assert_eq!(got, b"installed");
    }

    #[test]
    fn the_offered_list_has_eb_garamond_even_when_nothing_is_installed() {
        let list = available_families_in(&[]);
        assert_eq!(list.first().map(String::as_str), Some("Default"));
        assert!(list.iter().any(|n| normalise(n) == "ebgaramond"), "{list:?}");
    }

    #[test]
    fn it_is_not_listed_twice_when_it_is_installed_too() {
        let d = tempfile::tempdir().unwrap();
        std::fs::write(d.path().join("EBGaramond12-Regular.ttf"), b"x").unwrap();
        let list = available_families_in(&[d.path().to_path_buf()]);
        assert_eq!(list.iter().filter(|n| normalise(n).starts_with("ebgaramond")).count(), 1, "{list:?}");
    }

    #[test]
    fn windows_looks_in_the_system_and_the_per_user_font_folders() {
        let d = windows_font_dirs(Some("C:\\Windows"), Some("C:\\Users\\f\\AppData\\Local"));
        assert_eq!(d[0], PathBuf::from("C:\\Windows").join("Fonts"));
        assert_eq!(d[1], PathBuf::from("C:\\Users\\f\\AppData\\Local").join("Microsoft").join("Windows").join("Fonts"));
        assert_eq!(windows_font_dirs(None, None), Vec::<PathBuf>::new());
        assert_eq!(windows_font_dirs(Some("C:\\Windows"), None).len(), 1);
    }

    #[test]
    fn looking_up_a_missing_family_is_soft() {
        assert!(load_family("NoSuchFontFamilyAnywhere").is_none());
    }

    #[test]
    fn the_offered_list_always_has_a_default() {
        let families = available_families();
        assert_eq!(families.first().map(String::as_str), Some("Default"));
    }
}

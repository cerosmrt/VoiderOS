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

/// The bytes of the regular face of `family`, if it can be found.
pub fn load_family(family: &str) -> Option<Vec<u8>> {
    let mut fallback: Option<PathBuf> = None;
    for dir in font_dirs() {
        for path in walk(&dir, 0) {
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
    fallback.and_then(|p| std::fs::read(p).ok())
}

/// Family names we can offer in the settings panel: whatever is installed,
/// deduplicated and sorted, with egui's built-in always available.
pub fn available_families() -> Vec<String> {
    let mut names: Vec<String> = Vec::new();
    for dir in font_dirs() {
        for path in walk(&dir, 0) {
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

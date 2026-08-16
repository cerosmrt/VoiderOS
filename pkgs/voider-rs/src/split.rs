//! Splitting a file at `/name` markers into chapters.
//!
//! A port of `_split_chapter_at_slash`. A line `/name` **seals** everything
//! above it — back to the previous marker or the start of the file — into a
//! chapter called `name`. What comes after the last marker stays where it is.
//! Naming an existing chapter appends into it rather than overwriting: an
//! existing text always survives.

#![allow(dead_code)]

/// One chapter sealed out of the file.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Sealed {
    /// The name after the slash. Empty when the marker was a bare `/`.
    pub name: String,
    pub lines: Vec<String>,
}

/// The result of a split: the chapters sealed off, in order, and what is left
/// in the original file (the text after the last marker).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Split {
    pub sealed: Vec<Sealed>,
    pub remainder: Vec<String>,
}

/// True if this line is a `/name` marker.
pub fn is_marker(line: &str) -> bool {
    line.trim_start().starts_with('/')
}

/// The name a marker carries, trimmed. `/` alone gives "".
pub fn marker_name(line: &str) -> String {
    line.trim().trim_start_matches('/').trim().to_string()
}

/// Plan the split. Returns `None` when the file has no markers at all.
pub fn plan(lines: &[String]) -> Option<Split> {
    let markers: Vec<usize> = lines
        .iter()
        .enumerate()
        .filter(|(_, l)| is_marker(l))
        .map(|(i, _)| i)
        .collect();
    if markers.is_empty() {
        return None;
    }
    let mut sealed = Vec::new();
    let mut used: Vec<String> = Vec::new();
    let mut start = 0usize;
    for &m in &markers {
        let body = lines[start..m].to_vec();
        let mut name = marker_name(&lines[m]);
        if name.is_empty() {
            name = auto_name(&body, &used);
        }
        used.push(name.clone());
        sealed.push(Sealed { name, lines: body });
        start = m + 1;
    }
    Some(Split {
        sealed,
        remainder: lines[start..].to_vec(),
    })
}

/// Auto-name for a bare `/`: the first words of the sealed text, so a chapter is
/// never nameless.
pub fn auto_name(lines: &[String], used: &[String]) -> String {
    let first = lines
        .iter()
        .map(|l| l.trim())
        .find(|l| !l.is_empty() && *l != ".")
        .unwrap_or("");
    let mut base: String = first
        .split_whitespace()
        .take(5)
        .collect::<Vec<_>>()
        .join(" ")
        // These cannot go in a file name on every filesystem.
        .replace(['/', '\\', ':', '?', '*', '"', '<', '>', '|'], "");
    if base.trim().is_empty() {
        base = "Sin nombre".to_string();
    }
    let mut name = base.clone();
    let mut n = 2;
    while used.iter().any(|u| u == &name) {
        name = format!("{base} {n}");
        n += 1;
    }
    name
}

#[cfg(test)]
mod tests {
    use super::*;

    fn v(lines: &[&str]) -> Vec<String> {
        lines.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn a_file_without_markers_has_nothing_to_split() {
        assert!(plan(&v(&[".", "a", "b"])).is_none());
    }

    #[test]
    fn a_marker_seals_everything_above_it() {
        let s = plan(&v(&["uno", "dos", "/Primero", "tres"])).unwrap();
        assert_eq!(s.sealed.len(), 1);
        assert_eq!(s.sealed[0].name, "Primero");
        assert_eq!(s.sealed[0].lines, v(&["uno", "dos"]));
        assert_eq!(s.remainder, v(&["tres"])); // what follows stays put
    }

    #[test]
    fn each_marker_seals_back_to_the_previous_one() {
        let s = plan(&v(&["a", "/Uno", "b", "/Dos", "c"])).unwrap();
        assert_eq!(s.sealed.len(), 2);
        assert_eq!(s.sealed[0].lines, v(&["a"]));
        assert_eq!(s.sealed[1].name, "Dos");
        assert_eq!(s.sealed[1].lines, v(&["b"])); // not everything from the start
        assert_eq!(s.remainder, v(&["c"]));
    }

    #[test]
    fn a_marker_at_the_end_leaves_nothing_behind() {
        let s = plan(&v(&["a", "b", "/Todo"])).unwrap();
        assert_eq!(s.sealed[0].lines, v(&["a", "b"]));
        assert!(s.remainder.is_empty()); // the emptied container can be removed
    }

    #[test]
    fn a_marker_with_nothing_above_seals_nothing() {
        let s = plan(&v(&["/Vacio", "a"])).unwrap();
        assert!(s.sealed[0].lines.is_empty());
        assert_eq!(s.remainder, v(&["a"]));
    }

    #[test]
    fn the_name_is_whatever_follows_the_slash() {
        assert_eq!(marker_name("/Capitulo III"), "Capitulo III");
        assert_eq!(marker_name("  /  Espacios  "), "Espacios");
        assert_eq!(marker_name("/"), "");
        assert!(is_marker("/x"));
        assert!(is_marker("  /x"));
        assert!(!is_marker("x/y"));
    }

    #[test]
    fn a_bare_slash_is_named_from_its_first_words() {
        let name = auto_name(&v(&["El principio de todo lo que sigue", "mas"]), &[]);
        assert!(!name.is_empty());
        assert!(name.starts_with("El principio"));
    }

    #[test]
    fn an_auto_name_avoids_colliding_with_one_already_used() {
        let used = v(&["El principio"]);
        let name = auto_name(&v(&["El principio"]), &used);
        assert_ne!(name, "El principio"); // it must not clash
    }

    #[test]
    fn an_empty_auto_name_still_gives_something() {
        assert!(!auto_name(&v(&[]), &[]).is_empty());
    }

    #[test]
    fn separators_and_blanks_are_carried_along() {
        let s = plan(&v(&[".", "a", "", ".", "b", "/Uno", "c"])).unwrap();
        assert_eq!(s.sealed[0].lines, v(&[".", "a", "", ".", "b"]));
    }
}

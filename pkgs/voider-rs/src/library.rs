//! The library — `I.txt`, the ordered index of the book.
//!
//! Each line is either a chapter's file name or a `.` separator that groups
//! chapters into books. The order in this file *is* the reading order, so it is
//! written atomically like any other text in the void.

#![allow(dead_code)]

use std::path::{Path, PathBuf};

use crate::void;

/// The scratch portal: an entry pointing at `0.txt`. It is a marker, not a
/// chapter — read-only, and there is only ever one.
pub const PORTAL: &str = "0.txt";
pub const SEPARATOR: &str = ".";

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct Library {
    /// Raw entries: file names and `.` separators, in reading order.
    pub entries: Vec<String>,
    pub index: usize,
}

/// `<void>/I.txt`
pub fn library_path(void_dir: &Path) -> PathBuf {
    void_dir.join("I.txt")
}

/// `<void>/I/<name>`
pub fn chapter_path(void_dir: &Path, entry: &str) -> PathBuf {
    void_dir.join("I").join(entry)
}

/// What the reader sees for an entry: the file name without `.txt`, `.` for a
/// separator, `0` for the portal.
pub fn display_name(entry: &str) -> String {
    if entry == SEPARATOR {
        return SEPARATOR.to_string();
    }
    Path::new(entry)
        .file_stem()
        .map(|s| s.to_string_lossy().to_string())
        .unwrap_or_else(|| entry.to_string())
}

pub fn is_portal(entry: &str) -> bool {
    entry.eq_ignore_ascii_case(PORTAL)
}

pub fn is_separator(entry: &str) -> bool {
    entry == SEPARATOR
}

impl Library {
    /// Read `I.txt`, generating it from the chapters on disk the first time.
    pub fn load(void_dir: &Path) -> Self {
        let path = library_path(void_dir);
        if !path.exists() {
            let _ = generate(void_dir);
        }
        let mut entries = Vec::new();
        if let Ok(text) = std::fs::read_to_string(&path) {
            for raw in text.lines() {
                let s = raw.trim();
                if !s.is_empty() {
                    entries.push(s.to_string());
                }
            }
        }
        let mut lib = Self { entries, index: 0 };
        lib.dedupe_portals(None);
        // Park on the first real chapter rather than a separator.
        lib.index = lib
            .entries
            .iter()
            .position(|e| !is_separator(e))
            .unwrap_or(0);
        lib
    }

    pub fn save(&self, void_dir: &Path) -> std::io::Result<()> {
        void::atomic_write(&library_path(void_dir), &self.entries, false)
    }

    pub fn current(&self) -> &str {
        self.entries.get(self.index).map(String::as_str).unwrap_or("")
    }

    /// Step through the library, wrapping.
    pub fn move_by(&mut self, delta: isize) {
        if self.entries.is_empty() {
            return;
        }
        let len = self.entries.len() as isize;
        self.index = (self.index as isize + delta).rem_euclid(len) as usize;
    }

    /// Insert a chapter just below `at`, so a new file lands next to the one it
    /// came from rather than at some stale cursor.
    pub fn insert_below(&mut self, at: usize, entry: impl Into<String>) {
        let pos = (at + 1).min(self.entries.len());
        self.entries.insert(pos, entry.into());
    }

    /// Position of an entry, if it is listed.
    pub fn position(&self, entry: &str) -> Option<usize> {
        self.entries.iter().position(|e| e == entry)
    }

    /// Keep at most one `0` portal — the marker must never pile up. `keep` names
    /// the one that survives; otherwise the first does. Returns where it ended.
    pub fn dedupe_portals(&mut self, keep: Option<usize>) -> Option<usize> {
        let portals: Vec<usize> = self
            .entries
            .iter()
            .enumerate()
            .filter(|(_, e)| is_portal(e))
            .map(|(i, _)| i)
            .collect();
        if portals.len() <= 1 {
            return portals.first().copied();
        }
        let mut survivor = match keep {
            Some(k) if portals.contains(&k) => k,
            _ => portals[0],
        };
        // Collect first: the loop mutates `survivor`, which a filter closure
        // would still be borrowing.
        let doomed: Vec<usize> = portals.iter().copied().filter(|&i| i != survivor).collect();
        for i in doomed.into_iter().rev() {
            self.entries.remove(i);
            if i < survivor {
                survivor -= 1;
            }
            if i < self.index {
                self.index -= 1;
            }
        }
        if self.index >= self.entries.len() {
            self.index = self.entries.len().saturating_sub(1);
        }
        Some(survivor)
    }
}

/// First run: build `I.txt` from the `.txt` files sitting in `I/`.
fn generate(void_dir: &Path) -> std::io::Result<()> {
    let mut names: Vec<String> = std::fs::read_dir(void_dir.join("I"))
        .into_iter()
        .flatten()
        .flatten()
        .map(|e| e.file_name().to_string_lossy().to_string())
        .filter(|n| n.to_lowercase().ends_with(".txt"))
        .collect();
    names.sort();
    void::atomic_write(&library_path(void_dir), &names, false)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn lib(entries: &[&str]) -> Library {
        Library {
            entries: entries.iter().map(|s| s.to_string()).collect(),
            index: 0,
        }
    }

    #[test]
    fn display_names_strip_the_extension() {
        assert_eq!(display_name("Capitulo III.txt"), "Capitulo III");
        assert_eq!(display_name("."), ".");
        assert_eq!(display_name("0.txt"), "0");
    }

    #[test]
    fn the_portal_is_recognised() {
        assert!(is_portal("0.txt"));
        assert!(is_portal("0.TXT"));
        assert!(!is_portal("10.txt"));
        assert!(!is_portal("Capitulo.txt"));
    }

    #[test]
    fn load_generates_the_index_from_disk_when_absent() {
        let d = tempfile::tempdir().unwrap();
        let i = d.path().join("I");
        std::fs::create_dir_all(&i).unwrap();
        std::fs::write(i.join("Beta.txt"), "b").unwrap();
        std::fs::write(i.join("Alfa.txt"), "a").unwrap();
        std::fs::write(i.join("notes.md"), "ignored").unwrap();

        let l = Library::load(d.path());
        assert_eq!(l.entries, vec!["Alfa.txt", "Beta.txt"]); // sorted, .txt only
        assert!(library_path(d.path()).exists()); // and written out
    }

    #[test]
    fn load_reads_the_existing_order_including_separators() {
        let d = tempfile::tempdir().unwrap();
        std::fs::write(library_path(d.path()), ".\nB.txt\nA.txt\n").unwrap();
        let l = Library::load(d.path());
        assert_eq!(l.entries, vec![".", "B.txt", "A.txt"]); // order preserved
    }

    #[test]
    fn save_roundtrips() {
        let d = tempfile::tempdir().unwrap();
        let l = lib(&["A.txt", ".", "B.txt"]);
        l.save(d.path()).unwrap();
        assert_eq!(Library::load(d.path()).entries, l.entries);
    }

    #[test]
    fn navigation_wraps() {
        let mut l = lib(&["A.txt", "B.txt"]);
        assert_eq!(l.current(), "A.txt");
        l.move_by(1);
        assert_eq!(l.current(), "B.txt");
        l.move_by(1);
        assert_eq!(l.current(), "A.txt"); // wrapped
        l.move_by(-1);
        assert_eq!(l.current(), "B.txt");
    }

    #[test]
    fn insert_below_puts_it_next_to_its_origin() {
        let mut l = lib(&["A.txt", "B.txt", "C.txt"]);
        l.insert_below(0, "New.txt");
        assert_eq!(l.entries, vec!["A.txt", "New.txt", "B.txt", "C.txt"]);
    }

    #[test]
    fn insert_below_the_end_appends() {
        let mut l = lib(&["A.txt"]);
        l.insert_below(9, "New.txt");
        assert_eq!(l.entries, vec!["A.txt", "New.txt"]);
    }

    #[test]
    fn position_finds_entries() {
        let l = lib(&["A.txt", ".", "B.txt"]);
        assert_eq!(l.position("B.txt"), Some(2));
        assert_eq!(l.position("Nope.txt"), None);
    }

    #[test]
    fn portals_collapse_to_one() {
        let mut l = lib(&["0.txt", "A.txt", "0.txt", "B.txt"]);
        assert_eq!(l.dedupe_portals(None), Some(0));
        assert_eq!(l.entries, vec!["0.txt", "A.txt", "B.txt"]);
    }

    #[test]
    fn a_named_portal_is_the_one_that_survives() {
        let mut l = lib(&["0.txt", "A.txt", "0.txt", "B.txt"]);
        assert_eq!(l.dedupe_portals(Some(2)), Some(1));
        assert_eq!(l.entries, vec!["A.txt", "0.txt", "B.txt"]);
    }

    #[test]
    fn dedupe_is_a_noop_without_duplicates() {
        let mut l = lib(&["A.txt", "0.txt"]);
        assert_eq!(l.dedupe_portals(None), Some(1));
        assert_eq!(l.entries, vec!["A.txt", "0.txt"]);
        let mut none = lib(&["A.txt"]);
        assert_eq!(none.dedupe_portals(None), None);
    }

    #[test]
    fn dedupe_keeps_the_cursor_in_range() {
        let mut l = lib(&["0.txt", "0.txt", "A.txt"]);
        l.index = 2;
        l.dedupe_portals(None);
        assert!(l.index < l.entries.len());
    }
}

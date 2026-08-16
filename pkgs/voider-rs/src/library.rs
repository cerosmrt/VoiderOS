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

/// The leading chapter number of a title ("3. X" / "3 X" → 3), or None. A bare
/// "0" (the portal marker) is not numbered.
pub fn title_number(display: &str) -> Option<u32> {
    let mut chars = display.chars().peekable();
    let mut digits = String::new();
    while let Some(&c) = chars.peek() {
        if c.is_ascii_digit() {
            digits.push(c);
            chars.next();
        } else {
            break;
        }
    }
    if digits.is_empty() {
        return None;
    }
    match chars.next() {
        Some(c) if c == '.' || c.is_whitespace() => digits.parse().ok(),
        _ => None,
    }
}

/// Reorder `(fname, display)` pairs: numbered titles are sorted by their number
/// into the slots numbered titles occupy, the rest are shuffled into the
/// remaining slots, and the `0` portal (if present) is left exactly where it is.
pub fn reorder_group(files: &[(String, String)]) -> Vec<(String, String)> {
    let mut numbered_pos = Vec::new();
    let mut unnum_pos = Vec::new();
    for (k, (fname, display)) in files.iter().enumerate() {
        if is_portal(fname) || display == "0" {
            continue; // the portal stays put
        }
        if title_number(display).is_some() {
            numbered_pos.push(k);
        } else {
            unnum_pos.push(k);
        }
    }
    let mut result = files.to_vec();

    let mut numbered: Vec<(String, String)> = numbered_pos.iter().map(|&k| files[k].clone()).collect();
    numbered.sort_by_key(|(_, disp)| title_number(disp).unwrap_or(u32::MAX));

    let mut unnum: Vec<(String, String)> = unnum_pos.iter().map(|&k| files[k].clone()).collect();
    shuffle(&mut unnum);

    for (pos, f) in numbered_pos.into_iter().zip(numbered) {
        result[pos] = f;
    }
    for (pos, f) in unnum_pos.into_iter().zip(unnum) {
        result[pos] = f;
    }
    result
}

/// Tab on a separator dot in F3: shuffle the book that follows it (up to the
/// next separator or the end of the library). Returns `true` if anything moved.
pub fn shuffle_group(entries: &mut [String], dot_index: usize) -> bool {
    let n = entries.len();
    let mut idxs = Vec::new();
    let mut i = dot_index + 1;
    while i < n && entries[i] != SEPARATOR {
        idxs.push(i);
        i += 1;
    }
    if idxs.len() < 2 {
        return false;
    }
    let files: Vec<(String, String)> = idxs
        .iter()
        .map(|&k| (entries[k].clone(), display_name(&entries[k])))
        .collect();
    let new = reorder_group(&files);
    if new == files {
        return false;
    }
    for (&k, (fname, _)) in idxs.iter().zip(new) {
        entries[k] = fname;
    }
    true
}

/// Shuffle in place. A small xorshift seeded from the clock — no dependency
/// needed to make things formless again.
pub(crate) fn shuffle<T>(items: &mut [T]) {
    let mut state = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_nanos() as u64)
        .unwrap_or(0x2545F491)
        | 1;
    for i in (1..items.len()).rev() {
        state ^= state << 13;
        state ^= state >> 7;
        state ^= state << 17;
        items.swap(i, (state % (i as u64 + 1)) as usize);
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

    // ── book shuffle (Tab on a dot in F3) ────────────────────────────────────

    #[test]
    fn title_numbers_are_read_from_the_prefix() {
        assert_eq!(title_number("0. La Marca del Vaciador"), Some(0));
        assert_eq!(title_number("10. Algo"), Some(10));
        assert_eq!(title_number("3 Sustancia"), Some(3)); // digit + space
        assert_eq!(title_number("Epilogo"), None);
        assert_eq!(title_number("0"), None); // the bare portal marker
        assert_eq!(title_number(""), None);
    }

    #[test]
    fn reorder_sorts_numbered_into_their_slots_and_keeps_the_portal() {
        let files = vec![
            ("0.txt".to_string(), "0".to_string()),
            ("B.txt".to_string(), "2. B".to_string()),
            ("A.txt".to_string(), "1. A".to_string()),
            ("E.txt".to_string(), "Epilogo".to_string()),
            ("D.txt".to_string(), "Dedicatoria".to_string()),
        ];
        let out = reorder_group(&files);
        assert_eq!(out[0], files[0]); // portal fixed
        assert_eq!(out[1].1, "1. A"); // numbered slots sorted ascending
        assert_eq!(out[2].1, "2. B");
        let unnum: std::collections::HashSet<_> = [out[3].1.clone(), out[4].1.clone()].into_iter().collect();
        assert_eq!(unnum, ["Epilogo".to_string(), "Dedicatoria".to_string()].into_iter().collect());
    }

    #[test]
    fn an_out_of_place_number_goes_to_its_order() {
        let files = vec![
            ("C.txt".to_string(), "3. C".to_string()),
            ("A.txt".to_string(), "1. A".to_string()),
            ("B.txt".to_string(), "2. B".to_string()),
        ];
        let out = reorder_group(&files);
        assert_eq!(
            out.iter().map(|(_, d)| d.clone()).collect::<Vec<_>>(),
            vec!["1. A", "2. B", "3. C"]
        );
    }

    #[test]
    fn unnumbered_titles_stay_in_unnumbered_slots() {
        let files = vec![
            ("X.txt".to_string(), "Alpha".to_string()),
            ("N.txt".to_string(), "5. Five".to_string()),
            ("Y.txt".to_string(), "Beta".to_string()),
        ];
        let out = reorder_group(&files);
        assert_eq!(out[1], files[1]); // the numbered slot is untouched
        let unnum: std::collections::HashSet<_> = [out[0].1.clone(), out[2].1.clone()].into_iter().collect();
        assert_eq!(unnum, ["Alpha".to_string(), "Beta".to_string()].into_iter().collect());
    }

    #[test]
    fn shuffle_group_reorders_the_book_after_the_dot() {
        let mut entries = vec![
            ".".to_string(), "0.txt".into(), "B.txt".into(), "A.txt".into(),
        ];
        // force a deterministic-looking result isn't possible with the RNG, but
        // we can assert invariants: the set of files is unchanged, portal fixed.
        let before = entries.clone();
        shuffle_group(&mut entries, 0);
        assert_eq!(entries[1], "0.txt"); // portal untouched
        let mut a = entries[1..4].to_vec();
        let mut b = before[1..4].to_vec();
        a.sort();
        b.sort();
        assert_eq!(a, b); // same files, just reordered
    }

    #[test]
    fn shuffle_group_with_fewer_than_two_entries_does_nothing() {
        let mut entries = vec![".".to_string(), "A.txt".into()];
        assert!(!shuffle_group(&mut entries, 0));
        assert_eq!(entries, vec![".".to_string(), "A.txt".to_string()]);
    }

    #[test]
    fn shuffle_group_stops_at_the_next_separator() {
        let mut entries = vec![
            ".".to_string(), "A.txt".into(), "B.txt".into(),
            ".".to_string(), "C.txt".into(),
        ];
        let before = entries.clone();
        shuffle_group(&mut entries, 0);
        assert_eq!(entries[3], "."); // the next book's separator is untouched
        assert_eq!(entries[4], before[4]); // and its file never moved
    }
}

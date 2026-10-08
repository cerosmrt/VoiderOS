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

/// A chapter's heading: its name, upper-cased, between rules. F3's Ctrl+C puts it
/// above what it copies so a pasted chapter is told apart from any other block
/// of text (F9 included).
pub fn chapter_title_header(entry: &str) -> String {
    format!("── {} ──", display_name(entry).to_uppercase())
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
        // An empty index can only be a bug, and writing it would wipe a good
        // I.txt — the Python's `_save_library` refuses it too.
        if self.entries.is_empty() {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidInput,
                "refusing to save an empty library index",
            ));
        }
        // A blank row is a new entry still being named: it is not part of the
        // book until it has a name.
        let entries: Vec<String> = self.entries.iter().filter(|e| !e.is_empty()).cloned().collect();
        void::atomic_write(&library_path(void_dir), &entries, false)
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

    /// `[start, end)` of the book whose separator is at `i`.
    fn block_bounds(&self, i: usize) -> (usize, usize) {
        let mut j = i + 1;
        while j < self.entries.len() && !is_separator(&self.entries[j]) {
            j += 1;
        }
        (i, j)
    }

    /// Alt+↑/↓ in F3 — the Python's `_book_swap_up/down`. On a separator the
    /// whole book (its dot and its chapters) moves past the neighbouring book;
    /// on a chapter it swaps with the row next to it, crossing a separator only
    /// when there is a book on the other side. Returns whether anything moved.
    pub fn swap(&mut self, direction: isize) -> bool {
        let n = self.entries.len();
        let idx = self.index;
        if idx >= n {
            return false;
        }
        if is_separator(&self.entries[idx]) {
            let (s, e) = self.block_bounds(idx);
            let order: Vec<usize> = if direction < 0 {
                let Some(p) = (0..s).rev().find(|&p| is_separator(&self.entries[p])) else {
                    return false; // no book above
                };
                self.index = p;
                (0..p).chain(s..e).chain(p..s).chain(e..n).collect()
            } else {
                if e >= n {
                    return false; // no book below
                }
                let (_, e2) = self.block_bounds(e);
                self.index = s + (e2 - e);
                (0..s).chain(e..e2).chain(s..e).chain(e2..n).collect()
            };
            self.entries = order.into_iter().map(|k| self.entries[k].clone()).collect();
            return true;
        }
        let j = idx as isize + direction;
        if j < 0 || j as usize >= n {
            return false;
        }
        let j = j as usize;
        if is_separator(&self.entries[j]) {
            // Cross the separator only if there is a book over there.
            let beyond = if direction < 0 { &self.entries[..j] } else { &self.entries[j + 1..] };
            if !beyond.iter().any(|e| !is_separator(e)) {
                return false;
            }
        }
        self.entries.swap(idx, j);
        self.index = j;
        true
    }

    /// Ctrl+0 in F3: the current entry becomes the first; the cursor then steps
    /// off a separator onto a title — the Python's `_book_rebase`.
    pub fn rebase(&mut self) {
        let n = self.entries.len();
        if self.index == 0 || self.index >= n {
            return;
        }
        self.entries.rotate_left(self.index);
        self.index = 0;
        while is_separator(self.current()) && n > 1 {
            self.move_by(1);
            if self.index == 0 {
                break; // only separators
            }
        }
    }

    /// '.' typed in F3: a separator just above the highlighted title, the
    /// cursor on it. Nothing on a separator.
    pub fn insert_separator(&mut self) -> bool {
        if self.entries.is_empty() || is_separator(self.current()) {
            return false;
        }
        self.entries.insert(self.index, SEPARATOR.to_string());
        true
    }

    // ── Collapsing a book ────────────────────────────────────────────────────
    //
    // A book is a separator and the rows after it up to the next separator. Its
    // first chapter is its title. A book is open if its title's file is in `open`;
    // otherwise it is closed and all of it but the separator is hidden — the
    // separator's row then reads `· TITLE · (n)`.

    /// The row range `(first, end)` of the chapters after the separator at `dot`.
    fn book_rows(&self, dot: usize) -> std::ops::Range<usize> {
        let mut end = dot + 1;
        while end < self.entries.len() && !is_separator(&self.entries[end]) {
            end += 1;
        }
        dot + 1..end
    }

    /// The real chapters of a book: not the portal, not an unnamed row.
    fn book_chapters(&self, dot: usize) -> Vec<usize> {
        self.book_rows(dot)
            .filter(|&i| !self.entries[i].is_empty() && !is_portal(&self.entries[i]))
            .collect()
    }

    /// The file of a book's title — its first chapter.
    pub fn book_title(&self, dot: usize) -> Option<&str> {
        let first = *self.book_chapters(dot).first()?;
        Some(self.entries[first].as_str())
    }

    /// Whether the separator at `dot` stands for a closed book. A separator with
    /// nothing after it has nothing to close.
    pub fn is_collapsed(&self, dot: usize, open: &[String]) -> bool {
        dot < self.entries.len()
            && is_separator(&self.entries[dot])
            && self.book_title(dot).is_some_and(|t| !open.iter().any(|o| o == t))
    }

    /// The separator that owns row `i`: the nearest one above it.
    fn owner_dot(&self, i: usize) -> Option<usize> {
        (0..i).rev().find(|&p| is_separator(&self.entries[p]))
    }

    /// Whether row `i` is hidden inside a closed book (a separator never is).
    pub fn is_hidden(&self, i: usize, open: &[String]) -> bool {
        if i >= self.entries.len() || is_separator(&self.entries[i]) {
            return false;
        }
        self.owner_dot(i).is_some_and(|p| self.is_collapsed(p, open))
    }

    /// `· TITLE · (n)`, n being the chapters that are read — the title is not one.
    pub fn collapsed_label(&self, dot: usize, open: &[String]) -> String {
        let _ = open;
        let chapters = self.book_chapters(dot);
        let title = chapters.first().map(|&i| display_name(&self.entries[i])).unwrap_or_default();
        format!("· {title} · ({})", chapters.len().saturating_sub(1))
    }

    /// The rows that are on screen, in order.
    pub fn visible(&self, open: &[String]) -> Vec<usize> {
        (0..self.entries.len()).filter(|&i| !self.is_hidden(i, open)).collect()
    }

    /// ↑/↓ over what is on screen, wrapping.
    pub fn move_visible(&mut self, delta: isize, open: &[String]) {
        let rows = self.visible(open);
        if rows.is_empty() {
            return;
        }
        let here = rows.iter().position(|&i| i == self.index).unwrap_or(0) as isize;
        let next = (here + delta).rem_euclid(rows.len() as isize) as usize;
        self.index = rows[next];
    }

    /// A cursor left on a hidden row goes to the separator of its book.
    pub fn snap_to_visible(&mut self, open: &[String]) {
        if self.is_hidden(self.index, open) {
            if let Some(p) = self.owner_dot(self.index) {
                self.index = p;
            }
        }
    }

    /// PageUp/PageDown in F3: the separator before / after the cursor, wrapping.
    /// Stays put when there is none.
    pub fn goto_dot(&mut self, direction: isize) {
        let n = self.entries.len() as isize;
        if n == 0 {
            return;
        }
        let mut i = self.index as isize;
        for _ in 0..n {
            i = (i + direction).rem_euclid(n);
            if is_separator(&self.entries[i as usize]) {
                self.index = i as usize;
                return;
            }
        }
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

    // ── Collapsing a book in F3 (design, 2026-10-08) ─────────────────────────
    // A book is a separator and the rows up to the next one; its first chapter is
    // its title. Closed, it is ONE row (the separator's) that reads `· TITLE · (n)`,
    // n being the chapters that are read — the title does not count.

    fn books() -> Library {
        lib(&["Suelto.txt", ".", "26-10-8.txt", "Uno.txt", "Dos.txt", ".", "OTRO.txt", ".", "0.txt", "Viejo.txt", "c.txt"])
    }
    // rows: 0 Suelto | 1 . | 2 26-10-8 | 3 Uno | 4 Dos | 5 . | 6 OTRO | 7 . | 8 0.txt | 9 Viejo | 10 c

    fn closed() -> Vec<String> {
        Vec::new()
    }

    #[test]
    fn a_closed_book_is_one_row_and_the_title_is_not_counted() {
        let l = books();
        assert!(l.is_collapsed(1, &closed()));
        assert_eq!(l.collapsed_label(1, &closed()), "· 26-10-8 · (2)");
        assert_eq!(l.collapsed_label(5, &closed()), "· OTRO · (0)", "only a title: nothing to read yet");
        // the portal inside a book is neither title nor chapter
        assert_eq!(l.collapsed_label(7, &closed()), "· Viejo · (1)");
    }

    #[test]
    fn an_open_book_shows_all_its_rows() {
        let l = books();
        let open = vec!["26-10-8.txt".to_string()];
        assert!(!l.is_collapsed(1, &open));
        assert_eq!(l.visible(&open), vec![0, 1, 2, 3, 4, 5, 7]);
    }

    #[test]
    fn closed_books_hide_everything_but_their_separator() {
        let l = books();
        assert_eq!(l.visible(&closed()), vec![0, 1, 5, 7]);
        assert!(l.is_hidden(3, &closed()) && l.is_hidden(9, &closed()));
        assert!(!l.is_hidden(0, &closed()), "a loose row before any book is always seen");
        assert!(!l.is_hidden(1, &closed()), "the separator is the closed row");
    }

    #[test]
    fn the_cursor_steps_over_hidden_rows_both_ways_and_wraps() {
        let mut l = books();
        l.index = 1;
        l.move_visible(1, &closed());
        assert_eq!(l.index, 5);
        l.move_visible(1, &closed());
        assert_eq!(l.index, 7);
        l.move_visible(1, &closed());
        assert_eq!(l.index, 0, "wraps round");
        l.move_visible(-1, &closed());
        assert_eq!(l.index, 7);
    }

    #[test]
    fn a_cursor_left_on_a_hidden_row_snaps_to_its_books_separator() {
        let mut l = books();
        l.index = 4; // Dos, inside the closed 26-10-8
        l.snap_to_visible(&closed());
        assert_eq!(l.index, 1);
        l.index = 4;
        l.snap_to_visible(&["26-10-8.txt".to_string()]);
        assert_eq!(l.index, 4, "open: where it was");
    }

    #[test]
    fn a_separator_with_nothing_after_it_has_nothing_to_close() {
        let l = lib(&[".", ".", "A.txt"]);
        assert!(!l.is_collapsed(0, &closed()));
        assert_eq!(l.visible(&closed()).len(), 3 - 1 + 0 + 0, "{:?}", l.visible(&closed()));
    }

    // ── Alt+↑/↓ in F3 (test_book_reorder.py) ─────────────────────────────────

    fn names(entries: &[&str]) -> Library {
        let mut l = lib(&entries
            .iter()
            .map(|e| if *e == "." { ".".to_string() } else { format!("{e}.txt") })
            .collect::<Vec<_>>()
            .iter()
            .map(String::as_str)
            .collect::<Vec<_>>());
        l.index = 0;
        l
    }

    fn shown(l: &Library) -> Vec<String> {
        l.entries.iter().map(|e| display_name(e)).collect()
    }

    #[test]
    fn a_chapter_swaps_with_its_immediate_neighbour() {
        let mut l = names(&[".", "A", "B", "C"]);
        l.index = 2;
        assert!(l.swap(-1));
        assert_eq!(shown(&l), vec![".", "B", "A", "C"]);
        assert_eq!(l.index, 1);
    }

    #[test]
    fn a_chapter_at_the_edge_crosses_into_the_next_book() {
        let mut l = names(&[".", "A", "B", ".", "C", "D"]);
        l.index = 2;
        l.swap(1);
        assert_eq!(shown(&l), vec![".", "A", ".", "B", "C", "D"]);
        assert_eq!(l.index, 3);
    }

    #[test]
    fn a_chapter_does_not_cross_into_nothing() {
        let mut l = names(&[".", "A", "B"]);
        l.index = 1;
        assert!(!l.swap(-1));
        assert_eq!(shown(&l), vec![".", "A", "B"]);
    }

    #[test]
    fn a_dot_moves_its_whole_book_down() {
        let mut l = names(&[".", "A", "B", ".", "C"]);
        l.index = 0;
        l.swap(1);
        assert_eq!(shown(&l), vec![".", "C", ".", "A", "B"]);
        assert_eq!(l.index, 2);
    }

    #[test]
    fn a_dot_moves_its_whole_book_up() {
        let mut l = names(&[".", "A", ".", "B", "C"]);
        l.index = 2;
        l.swap(-1);
        assert_eq!(shown(&l), vec![".", "B", "C", ".", "A"]);
        assert_eq!(l.index, 0);
    }

    #[test]
    fn the_first_book_cannot_move_up_nor_the_last_down() {
        let mut l = names(&[".", "A", ".", "B"]);
        l.index = 0;
        assert!(!l.swap(-1));
        l.index = 2;
        assert!(!l.swap(1));
        assert_eq!(shown(&l), vec![".", "A", ".", "B"]);
    }

    // ── Ctrl+0 and '.' in F3 ────────────────────────────────────────────────

    #[test]
    fn rebase_makes_the_current_entry_first_and_skips_to_a_title() {
        let mut l = names(&["A", ".", "B", "C"]);
        l.index = 1;
        l.rebase();
        assert_eq!(shown(&l), vec![".", "B", "C", "A"]);
        assert_eq!(l.index, 1);
    }

    #[test]
    fn a_dot_typed_on_a_title_inserts_a_separator_above_it() {
        let mut l = names(&["A", "B"]);
        l.index = 1;
        assert!(l.insert_separator());
        assert_eq!(shown(&l), vec!["A", ".", "B"]);
        assert_eq!(l.index, 1);
        assert!(!l.insert_separator(), "on a separator it does nothing");
    }

    #[test]
    fn an_empty_index_is_never_written_over_a_good_one() {
        let d = tempfile::tempdir().unwrap();
        std::fs::create_dir_all(d.path().join("I")).unwrap();
        lib(&["Uno.txt", ".", "Dos.txt"]).save(d.path()).unwrap();
        assert!(lib(&[]).save(d.path()).is_err());
        let back = std::fs::read_to_string(library_path(d.path())).unwrap();
        assert!(back.contains("Uno.txt") && back.contains("Dos.txt"));
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

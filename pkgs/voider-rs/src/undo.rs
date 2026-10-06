//! Undo/redo of text content — a port of `undo_manager.py`.
//!
//! Each entry holds, per affected file, the lines before and after a write.
//! Consecutive writes to the SAME single file sharing a coalesce key merge into
//! one entry, so a burst of typing on one line is a single step rather than one
//! per keystroke. Recording anything clears the redo stack.
//!
//! It is pure data: the app records at its write chokepoint and, on undo,
//! writes the `before` lines back through the same atomic writer.

#![allow(dead_code)]

use std::path::PathBuf;

/// One file's change within an entry.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FileChange {
    pub path: PathBuf,
    pub before: Vec<String>,
    pub after: Vec<String>,
}

/// One undo step. Several files can move together (sending a paragraph changes
/// the source and the destination — undoing must put both back).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Entry {
    pub files: Vec<FileChange>,
    /// What lets consecutive writes merge: same key + same single file.
    pub key: Option<String>,
    /// For an F3 operation (reorder, rename, delete, merge, split…): the
    /// library's order and cursor before and after — the Python's
    /// `record_library`. Undo puts I.txt back as well as the files.
    pub library: Option<LibraryChange>,
}

/// The library as an undo step sees it: its rows and where the cursor was.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LibraryState {
    pub entries: Vec<String>,
    pub index: usize,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LibraryChange {
    pub before: LibraryState,
    pub after: LibraryState,
}

#[derive(Debug)]
pub struct UndoManager {
    undo: Vec<Entry>,
    redo: Vec<Entry>,
    cap: usize,
}

impl Default for UndoManager {
    fn default() -> Self {
        Self::new(300)
    }
}

impl UndoManager {
    pub fn new(cap: usize) -> Self {
        Self { undo: Vec::new(), redo: Vec::new(), cap }
    }

    pub fn can_undo(&self) -> bool {
        !self.undo.is_empty()
    }

    pub fn can_redo(&self) -> bool {
        !self.redo.is_empty()
    }

    pub fn clear(&mut self) {
        self.undo.clear();
        self.redo.clear();
    }

    pub fn undo_depth(&self) -> usize {
        self.undo.len()
    }

    /// Record one file's change. A write that repeats the key on the same single
    /// file folds into the entry on top, keeping its original `before`.
    pub fn record(
        &mut self,
        path: impl Into<PathBuf>,
        before: Vec<String>,
        after: Vec<String>,
        key: Option<String>,
    ) {
        if before == after {
            return; // nothing actually changed
        }
        let path = path.into();
        if key.is_some() {
            if let Some(top) = self.undo.last_mut() {
                if top.key == key && top.files.len() == 1 && top.files[0].path == path {
                    top.files[0].after = after;
                    self.redo.clear();
                    return;
                }
            }
        }
        self.push(Entry {
            files: vec![FileChange { path, before, after }],
            key,
            library: None,
        });
    }

    /// Record several files as ONE step (sending a paragraph, a split).
    pub fn record_transaction(&mut self, changes: Vec<FileChange>, key: Option<String>) {
        let files: Vec<FileChange> = changes.into_iter().filter(|c| c.before != c.after).collect();
        if files.is_empty() {
            return;
        }
        self.push(Entry { files, key, library: None });
    }

    /// Record an F3 operation as ONE step: the files it touched and the library
    /// before and after it.
    pub fn record_library(
        &mut self,
        changes: Vec<FileChange>,
        before: LibraryState,
        after: LibraryState,
        key: Option<String>,
    ) {
        let files: Vec<FileChange> = changes.into_iter().filter(|c| c.before != c.after).collect();
        if files.is_empty() && before == after {
            return;
        }
        self.push(Entry { files, key, library: Some(LibraryChange { before, after }) });
    }

    fn push(&mut self, entry: Entry) {
        self.undo.push(entry);
        if self.undo.len() > self.cap {
            self.undo.remove(0);
        }
        self.redo.clear();
    }

    /// Take the last change back; the caller restores each file's `before`.
    pub fn undo(&mut self) -> Option<Entry> {
        let entry = self.undo.pop()?;
        self.redo.push(entry.clone());
        Some(entry)
    }

    /// Put it back; the caller restores each file's `after`.
    pub fn redo(&mut self) -> Option<Entry> {
        let entry = self.redo.pop()?;
        self.undo.push(entry.clone());
        Some(entry)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn v(lines: &[&str]) -> Vec<String> {
        lines.iter().map(|s| s.to_string()).collect()
    }

    fn mgr() -> UndoManager {
        UndoManager::default()
    }

    #[test]
    fn nothing_to_undo_at_the_start() {
        let mut m = mgr();
        assert!(!m.can_undo() && !m.can_redo());
        assert!(m.undo().is_none());
        assert!(m.redo().is_none());
    }

    #[test]
    fn a_change_can_be_taken_back_and_put_again() {
        let mut m = mgr();
        m.record("a.txt", v(&["uno"]), v(&["dos"]), None);
        assert!(m.can_undo());

        let e = m.undo().unwrap();
        assert_eq!(e.files[0].before, v(&["uno"]));
        assert!(!m.can_undo());
        assert!(m.can_redo());

        let e = m.redo().unwrap();
        assert_eq!(e.files[0].after, v(&["dos"]));
        assert!(m.can_undo());
    }

    // ── F3: the library's order is part of the step (record_library) ─────────

    fn lib(entries: &[&str], index: usize) -> LibraryState {
        LibraryState { entries: v(entries), index }
    }

    #[test]
    fn a_library_change_restores_the_order_and_the_cursor() {
        let mut m = mgr();
        m.record_library(vec![], lib(&["A.txt", "B.txt"], 0), lib(&["B.txt", "A.txt"], 1), None);
        let e = m.undo().unwrap();
        let l = e.library.unwrap();
        assert_eq!(l.before, lib(&["A.txt", "B.txt"], 0));
        assert_eq!(l.after, lib(&["B.txt", "A.txt"], 1));
    }

    #[test]
    fn a_library_change_carries_the_files_it_touched() {
        let mut m = mgr();
        let gone = FileChange { path: "I/x.txt".into(), before: v(&[".", "x"]), after: vec![] };
        m.record_library(vec![gone.clone()], lib(&["x.txt"], 0), lib(&["."], 0), Some("delete".into()));
        let e = m.undo().unwrap();
        assert_eq!(e.files, vec![gone]);
        assert!(e.library.is_some());
    }

    #[test]
    fn a_library_change_that_changes_nothing_is_not_recorded() {
        let mut m = mgr();
        m.record_library(vec![], lib(&["A.txt"], 0), lib(&["A.txt"], 0), None);
        assert!(!m.can_undo());
    }

    #[test]
    fn plain_file_changes_carry_no_library() {
        let mut m = mgr();
        m.record("a.txt", v(&["uno"]), v(&["dos"]), None);
        assert!(m.undo().unwrap().library.is_none());
    }

    #[test]
    fn a_write_that_changes_nothing_is_not_recorded() {
        let mut m = mgr();
        m.record("a.txt", v(&["igual"]), v(&["igual"]), None);
        assert!(!m.can_undo());
    }

    #[test]
    fn a_typing_burst_on_one_line_is_a_single_step() {
        let mut m = mgr();
        let key = Some("doc:3".to_string());
        m.record("a.txt", v(&["h"]), v(&["ho"]), key.clone());
        m.record("a.txt", v(&["ho"]), v(&["hol"]), key.clone());
        m.record("a.txt", v(&["hol"]), v(&["hola"]), key.clone());
        assert_eq!(m.undo_depth(), 1);

        let e = m.undo().unwrap();
        assert_eq!(e.files[0].before, v(&["h"])); // the original before survived
        assert_eq!(e.files[0].after, v(&["hola"])); // and the latest after
    }

    #[test]
    fn a_different_key_starts_a_new_step() {
        let mut m = mgr();
        m.record("a.txt", v(&["a"]), v(&["b"]), Some("doc:1".into()));
        m.record("a.txt", v(&["b"]), v(&["c"]), Some("doc:2".into()));
        assert_eq!(m.undo_depth(), 2);
    }

    #[test]
    fn the_same_key_on_another_file_does_not_merge() {
        let mut m = mgr();
        let key = Some("doc:1".to_string());
        m.record("a.txt", v(&["a"]), v(&["b"]), key.clone());
        m.record("b.txt", v(&["x"]), v(&["y"]), key);
        assert_eq!(m.undo_depth(), 2);
    }

    #[test]
    fn without_a_key_every_write_is_its_own_step() {
        let mut m = mgr();
        m.record("a.txt", v(&["a"]), v(&["b"]), None);
        m.record("a.txt", v(&["b"]), v(&["c"]), None);
        assert_eq!(m.undo_depth(), 2);
    }

    #[test]
    fn two_files_can_move_as_one_step() {
        let mut m = mgr();
        m.record_transaction(
            vec![
                FileChange { path: "src.txt".into(), before: v(&["a", "b"]), after: v(&["a"]) },
                FileChange { path: "dst.txt".into(), before: v(&["z"]), after: v(&["z", "b"]) },
            ],
            Some("send".into()),
        );
        assert_eq!(m.undo_depth(), 1);
        let e = m.undo().unwrap();
        assert_eq!(e.files.len(), 2); // both come back together
    }

    #[test]
    fn a_transaction_drops_the_files_that_did_not_change() {
        let mut m = mgr();
        m.record_transaction(
            vec![
                FileChange { path: "a.txt".into(), before: v(&["x"]), after: v(&["x"]) },
                FileChange { path: "b.txt".into(), before: v(&["y"]), after: v(&["z"]) },
            ],
            None,
        );
        assert_eq!(m.undo().unwrap().files.len(), 1);
    }

    #[test]
    fn an_empty_transaction_is_not_recorded() {
        let mut m = mgr();
        m.record_transaction(
            vec![FileChange { path: "a.txt".into(), before: v(&["x"]), after: v(&["x"]) }],
            None,
        );
        assert!(!m.can_undo());
    }

    #[test]
    fn writing_again_abandons_the_redo_branch() {
        let mut m = mgr();
        m.record("a.txt", v(&["a"]), v(&["b"]), None);
        m.undo();
        assert!(m.can_redo());
        m.record("a.txt", v(&["a"]), v(&["c"]), None); // a new future
        assert!(!m.can_redo());
    }

    #[test]
    fn coalescing_also_abandons_the_redo_branch() {
        let mut m = mgr();
        let key = Some("k".to_string());
        m.record("a.txt", v(&["a"]), v(&["b"]), key.clone());
        m.undo();
        m.redo();
        m.record("a.txt", v(&["b"]), v(&["c"]), key);
        assert!(!m.can_redo());
    }

    #[test]
    fn the_history_is_capped_and_drops_the_oldest() {
        let mut m = UndoManager::new(3);
        for i in 0..5 {
            m.record("a.txt", v(&[&i.to_string()]), v(&[&(i + 1).to_string()]), None);
        }
        assert_eq!(m.undo_depth(), 3);
        // what's left is the newest three: the oldest fell off the bottom
        let e = m.undo().unwrap();
        assert_eq!(e.files[0].after, v(&["5"]));
    }

    #[test]
    fn undoing_several_steps_walks_back_in_order() {
        let mut m = mgr();
        m.record("a.txt", v(&["1"]), v(&["2"]), None);
        m.record("a.txt", v(&["2"]), v(&["3"]), None);
        assert_eq!(m.undo().unwrap().files[0].before, v(&["2"]));
        assert_eq!(m.undo().unwrap().files[0].before, v(&["1"]));
        assert!(!m.can_undo());
    }

    #[test]
    fn clearing_empties_both_stacks() {
        let mut m = mgr();
        m.record("a.txt", v(&["a"]), v(&["b"]), None);
        m.undo();
        m.clear();
        assert!(!m.can_undo() && !m.can_redo());
    }
}

//! App state and the F1 view.
//!
//! The state (ring, entry, active file) is kept free of egui so it can be
//! tested without a display; `eframe::App` below only draws it and feeds it
//! keys.

#![allow(dead_code)]

use std::io;
use std::path::{Path, PathBuf};

use crate::f5;
use crate::library::{self, Library};
use crate::line_ring::LineRing;
use crate::text_line::{self, TextLine};
use crate::void;

/// True when any keyboard's Caps Lock LED is lit.
///
/// Read straight from sysfs, as the Python does: Wayland does not expose lock
/// state to clients, and this way scriptio continua matches the physical light
/// exactly. Best effort — false if the LED isn't readable.
pub fn caps_lock_on() -> bool {
    let Ok(entries) = std::fs::read_dir("/sys/class/leds") else {
        return false;
    };
    for entry in entries.flatten() {
        let name = entry.file_name().to_string_lossy().to_lowercase();
        if !name.contains("capslock") {
            continue;
        }
        if let Ok(v) = std::fs::read_to_string(entry.path().join("brightness")) {
            let v = v.trim();
            if !v.is_empty() && v != "0" {
                return true;
            }
        }
    }
    false
}

/// Which view is on screen. Both edit the same ring and the same active file.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum View {
    /// Focus writing: one line at a time, into the active file.
    F1,
    /// The document as a circular list, editing the centred line in place.
    F2,
    /// The library: the book's chapters in reading order.
    F3,
    /// The active file as paragraphs, in order, to be moved or sent away.
    F5,
}

pub struct Voider {
    pub void_dir: PathBuf,
    pub current_file: PathBuf,
    pub ring: LineRing,
    pub library: Library,
    pub view: View,
    /// The line being edited: the write line in F1, the centred line in F2.
    pub entry: TextLine,
    /// Typewriter mode: the caret is pinned and the text slides under it.
    pub typewriter: bool,
    /// The pinned, centred title at the top of the view (a toggle).
    pub show_title: bool,
    /// F3 is holding a blank entry waiting to be named.
    pub pending_new: bool,
    /// F5: which paragraph the cursor is on.
    pub para_idx: usize,
    /// F5: the side catalogue for sending a paragraph to a chapter.
    pub picker_open: bool,
    pub picker_idx: usize,
    /// Where the backtick came from, so it can take you back.
    pub scratch_return: Option<(PathBuf, View)>,
    /// Set when the active file existed but could not be read — saving must stay
    /// blocked, or we would overwrite content we never saw.
    pub load_failed: bool,
    pub status: String,
}

impl Voider {
    /// Open `file` inside `void_dir` as the active document.
    pub fn open(void_dir: impl Into<PathBuf>, file: impl Into<PathBuf>) -> Self {
        let void_dir = void_dir.into();
        let current_file = file.into();
        let doc = void::load_doc(&current_file);
        Self {
            void_dir,
            current_file,
            ring: LineRing::new(doc.lines),
            library: Library::default(),
            view: View::F1,
            entry: TextLine::new(""),
            typewriter: false,
            show_title: false,
            pending_new: false,
            para_idx: 0,
            picker_open: false,
            picker_idx: 0,
            scratch_return: None,
            load_failed: doc.read_failed,
            status: String::new(),
        }
    }

    /// Persist the ring to the active file. A failed load blocks the write.
    pub fn save(&mut self) -> io::Result<()> {
        if self.load_failed {
            self.status = "Save blocked: the active file failed to load".into();
            return Ok(());
        }
        void::atomic_write(&self.current_file, &self.ring.lines, false)
    }

    /// F1 Enter: write the entry into the current line, then open a blank line
    /// below and move onto it (build forward). A `.` separator is preserved —
    /// text is inserted after it, never over it. An empty entry jumps to the end
    /// instead, ready to keep writing.
    pub fn commit_line(&mut self) -> io::Result<()> {
        let text = self.entry.text().trim().to_string();
        if text.is_empty() {
            self.goto_end();
            return Ok(());
        }
        if self.ring.lines.is_empty() {
            self.ring.lines.push(String::new());
        }
        let last = self.ring.lines.len() - 1;
        self.ring.index = self.ring.index.min(last);

        if self.ring.lines[self.ring.index] == "." {
            self.ring.lines.insert(self.ring.index + 1, text);
            self.ring.index += 1;
        } else {
            self.ring.lines[self.ring.index] = text;
        }
        self.ring.lines.insert(self.ring.index + 1, String::new());
        self.ring.index += 1;
        self.entry.clear();
        self.save()
    }

    /// Jump to a fresh blank line at the end of the active file.
    pub fn goto_end(&mut self) {
        if self.ring.lines.is_empty() {
            self.ring.lines.push(String::new());
        }
        if self.ring.lines.last().is_some_and(|l| !l.is_empty()) {
            self.ring.lines.push(String::new());
        }
        self.ring.index = self.ring.lines.len() - 1;
        self.entry.clear();
    }

    /// Mirror the current ring line into the entry (blank for a `.` separator).
    pub fn show_current(&mut self) {
        let cur = self.ring.current();
        self.entry.set_text(if cur == "." { "" } else { cur });
    }

    // ── F2: the document as a ring, editing the centred line ──────────────────

    /// Switch views, carrying the edit with you: leaving F2 persists the line,
    /// and each view mirrors the ring line the way it shows it.
    pub fn switch_to(&mut self, view: View) {
        if self.view == View::F2 {
            let _ = self.doc_live_save();
        }
        self.view = view;
        match view {
            View::F1 => self.show_current(),
            View::F2 => {
                let cur = self.ring.current().to_string();
                self.entry.set_text(&cur);
                self.entry.home(); // F2 lands at the start of the line
            }
            View::F3 => {
                self.library = Library::load(&self.void_dir);
                // Land on the file you were just in, not on some stale cursor.
                if let Some(name) = self.current_file.file_name() {
                    if let Some(i) = self.library.position(&name.to_string_lossy()) {
                        self.library.index = i;
                    }
                }
            }
            View::F5 => {
                // Land on the paragraph holding the line you were editing.
                self.para_idx = f5::para_at_line(&self.ring.lines, self.ring.index);
                let n = f5::para_count(&self.ring.lines);
                self.para_idx = if n == 0 { 0 } else { self.para_idx.min(n - 1) };
                self.picker_open = false;
                self.library = Library::load(&self.void_dir);
            }
        }
    }

    // ── F5: paragraphs ────────────────────────────────────────────────────────

    /// Step through paragraphs. Linear and clamped — F5 doesn't wrap.
    pub fn f5_step(&mut self, delta: isize) {
        let n = f5::para_count(&self.ring.lines);
        if n == 0 {
            return;
        }
        let i = (self.para_idx as isize + delta).clamp(0, n as isize - 1);
        self.para_idx = i as usize;
    }

    /// Move the current paragraph. Fences and separators keep their slots, so a
    /// paragraph pushed past a fence crosses into the next chapter.
    pub fn f5_swap(&mut self, direction: isize) -> io::Result<()> {
        if let Some((lines, ord)) = f5::swap(&self.ring.lines, self.para_idx, direction) {
            self.ring.lines = lines;
            self.para_idx = ord;
            if self.ring.index >= self.ring.lines.len() {
                self.ring.index = self.ring.lines.len().saturating_sub(1);
            }
            self.save()?;
        }
        Ok(())
    }

    /// Enter in F5: jump to F2 on this paragraph's first line.
    pub fn f5_to_f2(&mut self) {
        self.ring.index = f5::line_of_para(&self.ring.lines, self.para_idx);
        self.switch_to(View::F2);
    }

    /// The title pinned in F5: the fence the paragraph sits under, else the file.
    pub fn f5_title(&self) -> String {
        f5::chapter_of_para(&self.ring.lines, self.para_idx)
            .unwrap_or_else(|| file_title(&self.current_file))
    }

    /// Chapters a paragraph can be sent to: never a separator, the portal, or
    /// the file it already lives in.
    pub fn picker_entries(&self) -> Vec<String> {
        let src = self
            .current_file
            .file_name()
            .map(|s| s.to_string_lossy().to_string())
            .unwrap_or_default();
        self.library
            .entries
            .iter()
            .filter(|e| !library::is_separator(e) && !library::is_portal(e) && **e != src)
            .cloned()
            .collect()
    }

    /// Open the catalogue parked on the chapter nearest the active file, so
    /// origin and destination start together and you navigate out from there.
    pub fn open_picker(&mut self) {
        self.picker_open = true;
        self.picker_idx = self.picker_start_idx();
    }

    pub fn picker_start_idx(&self) -> usize {
        let entries = self.picker_entries();
        if entries.is_empty() {
            return 0;
        }
        let Some(name) = self.current_file.file_name() else {
            return 0;
        };
        let Some(anchor) = self.library.position(&name.to_string_lossy()) else {
            return 0;
        };
        // Nearest by library position; ties break toward the chapter just after.
        entries
            .iter()
            .enumerate()
            .min_by_key(|(_, e)| {
                let p = self.library.position(e).unwrap_or(usize::MAX / 2);
                (p.abs_diff(anchor), p < anchor)
            })
            .map(|(i, _)| i)
            .unwrap_or(0)
    }

    pub fn picker_cycle(&mut self, delta: isize) {
        let n = self.picker_entries().len();
        if n == 0 {
            return;
        }
        self.picker_idx = (self.picker_idx as isize + delta).rem_euclid(n as isize) as usize;
    }

    /// Move the current paragraph out of this file and append it to `entry`.
    /// Snapshots the void first: this rewrites two files.
    pub fn send_para_to(&mut self, entry: &str) -> io::Result<bool> {
        let target = library::chapter_path(&self.void_dir, entry);
        if target == self.current_file {
            return Ok(false);
        }
        let Some((para, rest)) = f5::take_para(&self.ring.lines, self.para_idx) else {
            return Ok(false);
        };
        void::git_commit(
            &self.void_dir,
            "I/",
            &format!("f5-send {}", void::timestamp()),
        );

        // Read the target raw (no synthesised leading dot) and append after a
        // separator, so the arriving paragraph stays a paragraph of its own.
        let mut existing: Vec<String> = std::fs::read_to_string(&target)
            .map(|t| t.lines().map(|l| l.trim_end().to_string()).collect())
            .unwrap_or_default();
        while existing.last().is_some_and(|l| l.trim().is_empty()) {
            existing.pop();
        }
        let mut combined = existing;
        if !combined.is_empty() {
            combined.push(".".to_string());
        }
        combined.extend(para);
        void::atomic_write(&target, &combined, false)?;

        self.ring.lines = rest;
        if self.ring.index >= self.ring.lines.len() {
            self.ring.index = self.ring.lines.len().saturating_sub(1);
        }
        self.save()?;
        let n = f5::para_count(&self.ring.lines);
        self.para_idx = if n == 0 { 0 } else { self.para_idx.min(n - 1) };
        self.picker_open = false;
        Ok(true)
    }

    // ── F3: the library ───────────────────────────────────────────────────────

    /// Make `path` the active document, loading it into the ring.
    pub fn set_active_file(&mut self, path: impl Into<PathBuf>) {
        let path = path.into();
        let doc = void::load_doc(&path);
        self.current_file = path;
        self.ring = LineRing::new(doc.lines);
        self.load_failed = doc.read_failed;
    }

    /// Enter in F3: open the highlighted chapter in F2. Separators are structure,
    /// not chapters — they open nothing.
    pub fn open_current_chapter(&mut self) {
        let entry = self.library.current().to_string();
        if entry.is_empty() || library::is_separator(&entry) {
            return;
        }
        let path = library::chapter_path(&self.void_dir, &entry);
        self.set_active_file(path);
        self.switch_to(View::F2);
    }

    /// Start naming a new chapter, to be created below the current entry.
    pub fn begin_new_chapter(&mut self) {
        self.pending_new = true;
        self.entry.clear();
    }

    /// Leaving a half-named entry settles it: a name is created (no Enter
    /// needed), an empty one is dropped. You can never end up with a blank title.
    pub fn settle_pending(&mut self) -> io::Result<()> {
        if !self.pending_new {
            return Ok(());
        }
        self.pending_new = false;
        let name = self.entry.text();
        self.entry.clear();
        self.new_chapter(&name).map(|_| ())
    }

    /// Escape: throw the half-named entry away outright.
    pub fn cancel_pending(&mut self) {
        self.pending_new = false;
        self.entry.clear();
    }

    /// Create a chapter named `name` directly below the current entry — next to
    /// what you were working on — and list it. Returns its path.
    pub fn new_chapter(&mut self, name: &str) -> io::Result<Option<PathBuf>> {
        let name = name.trim();
        if name.is_empty() {
            return Ok(None);
        }
        let file = format!("{name}.txt");
        if self.library.position(&file).is_some() {
            return Ok(None); // an existing name keeps its file; never clobber it
        }
        let path = library::chapter_path(&self.void_dir, &file);
        if !path.exists() {
            void::atomic_write(&path, &[".".to_string()], false)?;
        }
        let at = self.library.index;
        self.library.insert_below(at, file);
        self.library.index = (at + 1).min(self.library.entries.len() - 1);
        self.library.save(&self.void_dir)?;
        Ok(Some(path))
    }

    /// F2 saves on every keystroke. Blank text is never written over a line and
    /// a `.` separator is never overwritten — they're structure, not content.
    pub fn doc_live_save(&mut self) -> io::Result<()> {
        let text = self.entry.text();
        if text.trim().is_empty() || self.ring.lines.is_empty() {
            return Ok(());
        }
        let i = self.ring.index;
        if self.ring.lines[i] == "." {
            return Ok(());
        }
        self.ring.lines[i] = text;
        self.save()
    }

    /// Move through the document. The caret lands at the start of the new line —
    /// unless it was sitting at the end of the old one, in which case it stays
    /// at the end, so walking a paragraph feels continuous.
    pub fn doc_navigate(&mut self, delta: isize) -> io::Result<()> {
        let at_end = self.entry.caret() == self.entry.len();
        self.doc_live_save()?;
        self.ring.move_by(delta);
        let cur = self.ring.current().to_string();
        self.entry.set_text(&cur);
        if at_end {
            self.entry.end();
        } else {
            self.entry.home();
        }
        Ok(())
    }

    /// Enter in F2 breaks the line at the caret: what's after it becomes the
    /// next line, and you land on it.
    pub fn doc_split_line(&mut self) -> io::Result<()> {
        if self.ring.lines.is_empty() {
            return Ok(());
        }
        let chars: Vec<char> = self.entry.text().chars().collect();
        let pos = self.entry.caret().min(chars.len());
        let before: String = chars[..pos].iter().collect();
        let after: String = chars[pos..].iter().collect();
        let i = self.ring.index;
        self.ring.lines[i] = before;
        self.ring.lines.insert(i + 1, after);
        self.ring.index = i + 1;
        let cur = self.ring.current().to_string();
        self.entry.set_text(&cur);
        self.entry.home();
        self.save()
    }

    /// Backspace at the start of a line joins it onto the one above, with the
    /// caret left at the seam. Separators are never swallowed.
    pub fn doc_join_prev(&mut self) -> io::Result<()> {
        let i = self.ring.index;
        if i == 0 || self.ring.lines[i] == "." || self.ring.lines[i - 1] == "." {
            return Ok(());
        }
        let cur = self.ring.lines.remove(i);
        let seam = self.ring.lines[i - 1].chars().count();
        self.ring.lines[i - 1].push_str(&cur);
        self.ring.index = i - 1;
        let joined = self.ring.lines[i - 1].clone();
        self.entry.set_text(&joined);
        self.entry.set_caret(seam);
        self.save()
    }

    /// The scratch, `I/0.txt` — where writing goes when it has no home yet.
    pub fn scratch_path(&self) -> PathBuf {
        library::chapter_path(&self.void_dir, library::PORTAL)
    }

    /// Backtick: a round trip to the scratch. From anywhere else it remembers
    /// where you were and drops you into 0.txt ready to write; from the scratch
    /// it takes you back to that file and view.
    pub fn scratch_toggle(&mut self) {
        let scratch = self.scratch_path();
        if self.current_file != scratch {
            self.scratch_return = Some((self.current_file.clone(), self.view));
            if !scratch.exists() {
                let _ = void::atomic_write(&scratch, &[".".to_string()], false);
            }
            self.set_active_file(scratch);
            self.switch_to(View::F1);
            self.goto_end(); // land ready to write, at the end
        } else if let Some((path, view)) = self.scratch_return.take() {
            self.set_active_file(path);
            self.switch_to(view);
        }
    }

    /// Commit the whole void to git, as Ctrl+Shift+G does in the Python.
    pub fn commit_void(&mut self) {
        let msg = format!("snapshot {}", void::timestamp());
        self.status = match void::git_commit(&self.void_dir, ".", &msg) {
            void::CommitOutcome::Committed { stat } if !stat.is_empty() => {
                format!("Void commit: {msg} — {stat}")
            }
            void::CommitOutcome::Committed { .. } => format!("Void commit: {msg}"),
            void::CommitOutcome::NothingToCommit => "Nothing to commit".into(),
            void::CommitOutcome::Failed { error } => format!("Commit failed: {error}"),
        };
    }

    /// Feed one typed string, honouring Caps (never uppercases) and scriptio
    /// continua (with Caps on, the spacebar releases the line to the void).
    pub fn type_text(&mut self, text: &str, caps_on: bool) -> io::Result<()> {
        if caps_on && text == " " {
            return self.commit_line();
        }
        self.entry.insert(&text_line::neutralize_caps(text, caps_on));
        Ok(())
    }

    /// Backspace. In scriptio continua (Caps on) there is no editing: a line can
    /// only be typed forward or released, so this does nothing.
    pub fn backspace(&mut self, caps_on: bool) -> bool {
        if caps_on {
            return false;
        }
        self.entry.backspace()
    }
}

/// A sandbox void with a scratch file, created on first run. The real `/void` is
/// left alone until this mirror is proven.
pub fn open_sandbox() -> Voider {
    let dir = void::sandbox_dir();
    let _ = std::fs::create_dir_all(dir.join("I"));
    let scratch = dir.join("I/0.txt");
    if !scratch.exists() {
        let _ = void::atomic_write(&scratch, &[".".to_string()], false);
    }
    let mut v = Voider::open(&dir, &scratch);
    v.goto_end();
    v
}

pub fn file_title(path: &Path) -> String {
    path.file_stem()
        .map(|s| s.to_string_lossy().to_string())
        .unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn app(lines: &[&str]) -> (tempfile::TempDir, Voider) {
        let d = tempfile::tempdir().unwrap();
        let f = d.path().join("c.txt");
        let lines: Vec<String> = lines.iter().map(|s| s.to_string()).collect();
        void::atomic_write(&f, &lines, false).unwrap();
        let v = Voider::open(d.path(), &f);
        (d, v)
    }

    #[test]
    fn commit_writes_the_line_and_opens_a_blank_one_below() {
        let (_d, mut v) = app(&[".", "vieja"]);
        v.ring.index = 1;
        v.entry.set_text("nueva");
        v.commit_line().unwrap();
        assert_eq!(v.ring.lines, vec![".", "nueva", ""]);
        assert_eq!(v.ring.index, 2); // on the fresh blank line
        assert_eq!(v.entry.text(), "");
    }

    #[test]
    fn commit_on_a_separator_inserts_after_it() {
        let (_d, mut v) = app(&[".", "otra"]);
        v.ring.index = 0; // sitting on the '.'
        v.entry.set_text("texto");
        v.commit_line().unwrap();
        assert_eq!(v.ring.lines, vec![".", "texto", "", "otra"]);
        assert_eq!(v.ring.lines[0], "."); // the separator survived
    }

    #[test]
    fn commit_persists_to_disk() {
        let (_d, mut v) = app(&[".", "a"]);
        v.ring.index = 1;
        v.entry.set_text("guardada");
        v.commit_line().unwrap();
        let on_disk = void::load_doc(&v.current_file);
        assert!(on_disk.lines.contains(&"guardada".to_string()));
    }

    #[test]
    fn empty_enter_jumps_to_the_end() {
        let (_d, mut v) = app(&[".", "a", "b"]);
        v.ring.index = 0;
        v.entry.clear();
        v.commit_line().unwrap();
        assert_eq!(v.ring.lines.last().unwrap(), "");
        assert_eq!(v.ring.index, v.ring.lines.len() - 1);
    }

    #[test]
    fn goto_end_does_not_stack_blank_lines() {
        let (_d, mut v) = app(&[".", "a"]);
        v.goto_end();
        let n = v.ring.lines.len();
        v.goto_end();
        assert_eq!(v.ring.lines.len(), n); // already blank at the end
    }

    #[test]
    fn show_current_blanks_a_separator() {
        let (_d, mut v) = app(&[".", "texto"]);
        v.ring.index = 1;
        v.show_current();
        assert_eq!(v.entry.text(), "texto");
        v.ring.index = 0;
        v.show_current();
        assert_eq!(v.entry.text(), "");
    }

    #[test]
    fn caps_types_lowercase_and_space_voids_the_line() {
        let (_d, mut v) = app(&[".", ""]);
        v.ring.index = 1;
        v.type_text("H", true).unwrap();
        v.type_text("I", true).unwrap();
        assert_eq!(v.entry.text(), "hi"); // Caps never uppercases
        v.type_text(" ", true).unwrap(); // scriptio: space releases the line
        assert_eq!(v.entry.text(), "");
        assert!(v.ring.lines.contains(&"hi".to_string()));
    }

    #[test]
    fn space_is_a_normal_space_without_caps() {
        let (_d, mut v) = app(&[".", ""]);
        v.type_text("a", false).unwrap();
        v.type_text(" ", false).unwrap();
        assert_eq!(v.entry.text(), "a ");
    }

    #[test]
    fn backspace_is_disabled_in_scriptio_continua() {
        let (_d, mut v) = app(&[".", ""]);
        v.entry.set_text("hola");
        assert!(!v.backspace(true)); // Caps on → type and send only
        assert_eq!(v.entry.text(), "hola");
        assert!(v.backspace(false));
        assert_eq!(v.entry.text(), "hol");
    }

    #[test]
    fn a_failed_load_blocks_saving() {
        let (_d, mut v) = app(&[".", "importante"]);
        v.load_failed = true;
        v.ring.lines = vec![".".to_string()]; // pretend the ring got clobbered
        v.save().unwrap();
        let on_disk = void::load_doc(&v.current_file);
        assert!(on_disk.lines.contains(&"importante".to_string())); // untouched
    }

    // ── F2 ────────────────────────────────────────────────────────────────────

    #[test]
    fn entering_f2_shows_the_line_with_the_caret_at_the_start() {
        let (_d, mut v) = app(&[".", "una linea"]);
        v.ring.index = 1;
        v.switch_to(View::F2);
        assert_eq!(v.entry.text(), "una linea");
        assert_eq!(v.entry.caret(), 0);
    }

    #[test]
    fn f2_live_save_writes_through_to_disk() {
        let (_d, mut v) = app(&[".", "vieja"]);
        v.ring.index = 1;
        v.switch_to(View::F2);
        v.entry.set_text("editada");
        v.doc_live_save().unwrap();
        assert_eq!(v.ring.lines[1], "editada");
        assert!(void::load_doc(&v.current_file).lines.contains(&"editada".to_string()));
    }

    #[test]
    fn f2_never_blanks_a_line_or_a_separator() {
        let (_d, mut v) = app(&[".", "texto"]);
        v.ring.index = 1;
        v.entry.set_text("   ");
        v.doc_live_save().unwrap();
        assert_eq!(v.ring.lines[1], "texto"); // blank never overwrites

        v.ring.index = 0; // on the '.'
        v.entry.set_text("nope");
        v.doc_live_save().unwrap();
        assert_eq!(v.ring.lines[0], "."); // structure survives
    }

    #[test]
    fn navigating_persists_the_edit_and_keeps_an_end_caret() {
        let (_d, mut v) = app(&[".", "a", "bb"]);
        v.ring.index = 1;
        v.switch_to(View::F2);
        v.entry.set_text("editada");
        v.entry.end();
        v.doc_navigate(1).unwrap();
        assert_eq!(v.ring.lines[1], "editada"); // the edit was kept
        assert_eq!(v.entry.text(), "bb");
        assert_eq!(v.entry.caret(), 2); // was at the end, stays at the end
    }

    #[test]
    fn navigating_from_mid_line_lands_at_the_start() {
        let (_d, mut v) = app(&[".", "a", "bb"]);
        v.ring.index = 1;
        v.switch_to(View::F2);
        v.entry.set_caret(0);
        v.doc_navigate(1).unwrap();
        assert_eq!(v.entry.caret(), 0);
    }

    #[test]
    fn enter_splits_the_line_at_the_caret() {
        let (_d, mut v) = app(&[".", "hola mundo"]);
        v.ring.index = 1;
        v.switch_to(View::F2);
        v.entry.set_caret(4);
        v.doc_split_line().unwrap();
        assert_eq!(v.ring.lines, vec![".", "hola", " mundo"]);
        assert_eq!(v.ring.index, 2); // landed on the new line
        assert_eq!(v.entry.text(), " mundo");
        assert_eq!(v.entry.caret(), 0);
    }

    #[test]
    fn backspace_at_the_start_joins_with_the_line_above() {
        let (_d, mut v) = app(&[".", "hola", "mundo"]);
        v.ring.index = 2;
        v.switch_to(View::F2);
        v.doc_join_prev().unwrap();
        assert_eq!(v.ring.lines, vec![".", "holamundo"]);
        assert_eq!(v.ring.index, 1);
        assert_eq!(v.entry.caret(), 4); // the caret sits at the seam
    }

    #[test]
    fn joining_never_swallows_a_separator() {
        let (_d, mut v) = app(&[".", "texto"]);
        v.ring.index = 1;
        v.switch_to(View::F2);
        v.doc_join_prev().unwrap();
        assert_eq!(v.ring.lines, vec![".", "texto"]); // '.' above → refused
    }

    #[test]
    fn leaving_f2_persists_the_edit() {
        let (_d, mut v) = app(&[".", "vieja"]);
        v.ring.index = 1;
        v.switch_to(View::F2);
        v.entry.set_text("nueva");
        v.switch_to(View::F1);
        assert_eq!(v.ring.lines[1], "nueva");
    }

    // ── F3 ────────────────────────────────────────────────────────────────────

    /// A void with two chapters and the scratch, as F3 would find it.
    fn book() -> (tempfile::TempDir, Voider) {
        let d = tempfile::tempdir().unwrap();
        let i = d.path().join("I");
        std::fs::create_dir_all(&i).unwrap();
        void::atomic_write(&i.join("Uno.txt"), &[".".into(), "de uno".into()], false).unwrap();
        void::atomic_write(&i.join("Dos.txt"), &[".".into(), "de dos".into()], false).unwrap();
        let v = Voider::open(d.path(), i.join("Uno.txt"));
        (d, v)
    }

    #[test]
    fn f3_lists_the_book_and_lands_on_the_active_file() {
        let (_d, mut v) = book();
        v.switch_to(View::F3);
        assert_eq!(v.library.entries, vec!["Dos.txt", "Uno.txt"]); // sorted on first build
        assert_eq!(v.library.current(), "Uno.txt"); // where we were
    }

    #[test]
    fn opening_a_chapter_loads_it_into_f2() {
        let (_d, mut v) = book();
        v.switch_to(View::F3);
        v.library.index = v.library.position("Dos.txt").unwrap();
        v.open_current_chapter();
        assert_eq!(v.view, View::F2);
        assert!(v.current_file.ends_with("Dos.txt"));
        assert!(v.ring.lines.contains(&"de dos".to_string()));
    }

    #[test]
    fn a_separator_opens_nothing() {
        let (_d, mut v) = book();
        v.switch_to(View::F3);
        v.library.entries.insert(0, ".".into());
        v.library.index = 0;
        let before = v.current_file.clone();
        v.open_current_chapter();
        assert_eq!(v.current_file, before);
        assert_eq!(v.view, View::F3);
    }

    #[test]
    fn a_new_chapter_lands_below_the_current_one() {
        let (_d, mut v) = book();
        v.switch_to(View::F3);
        v.library.index = v.library.position("Dos.txt").unwrap();
        let path = v.new_chapter("Tres").unwrap().unwrap();
        assert!(path.exists());
        assert_eq!(v.library.entries, vec!["Dos.txt", "Tres.txt", "Uno.txt"]);
        assert_eq!(v.library.current(), "Tres.txt");
        // and it survives a reload from disk
        assert!(Library::load(&v.void_dir).entries.contains(&"Tres.txt".to_string()));
    }

    #[test]
    fn leaving_a_named_entry_creates_it_without_enter() {
        let (_d, mut v) = book();
        v.switch_to(View::F3);
        v.begin_new_chapter();
        v.entry.set_text("Tres");
        v.settle_pending().unwrap(); // e.g. navigating away
        assert!(!v.pending_new);
        assert!(v.library.entries.contains(&"Tres.txt".to_string()));
    }

    #[test]
    fn leaving_an_unnamed_entry_drops_it() {
        let (_d, mut v) = book();
        v.switch_to(View::F3);
        let n = v.library.entries.len();
        v.begin_new_chapter();
        v.settle_pending().unwrap();
        assert_eq!(v.library.entries.len(), n); // no blank title ever persists
    }

    #[test]
    fn escape_throws_a_named_entry_away() {
        let (_d, mut v) = book();
        v.switch_to(View::F3);
        let n = v.library.entries.len();
        v.begin_new_chapter();
        v.entry.set_text("Descartame");
        v.cancel_pending();
        assert_eq!(v.library.entries.len(), n);
        assert!(!v.pending_new);
    }

    #[test]
    fn an_empty_name_creates_nothing() {
        let (_d, mut v) = book();
        v.switch_to(View::F3);
        let n = v.library.entries.len();
        assert!(v.new_chapter("   ").unwrap().is_none());
        assert_eq!(v.library.entries.len(), n);
    }

    #[test]
    fn an_existing_name_never_clobbers_its_file() {
        let (_d, mut v) = book();
        v.switch_to(View::F3);
        assert!(v.new_chapter("Dos").unwrap().is_none());
        let doc = void::load_doc(&library::chapter_path(&v.void_dir, "Dos.txt"));
        assert!(doc.lines.contains(&"de dos".to_string())); // untouched
    }

    // ── F5 ────────────────────────────────────────────────────────────────────

    #[test]
    fn entering_f5_lands_on_the_paragraph_you_were_editing() {
        let (_d, mut v) = app(&[".", "a", ".", "b"]);
        v.ring.index = 3; // on 'b'
        v.switch_to(View::F5);
        assert_eq!(v.para_idx, 1);
    }

    #[test]
    fn f5_steps_are_clamped_at_the_ends() {
        let (_d, mut v) = app(&[".", "a", ".", "b"]);
        v.switch_to(View::F5);
        v.f5_step(-1);
        assert_eq!(v.para_idx, 0); // no wrap
        v.f5_step(5);
        assert_eq!(v.para_idx, 1);
    }

    #[test]
    fn f5_swap_reorders_and_persists() {
        let (_d, mut v) = app(&[".", "a", ".", "b"]);
        v.switch_to(View::F5);
        v.para_idx = 0;
        v.f5_swap(1).unwrap();
        assert_eq!(v.ring.lines, vec![".", "b", ".", "a"]);
        assert_eq!(v.para_idx, 1); // the cursor follows the paragraph
        assert!(void::load_doc(&v.current_file).lines.contains(&"b".to_string()));
    }

    #[test]
    fn enter_in_f5_returns_to_f2_on_that_paragraph() {
        let (_d, mut v) = app(&[".", "a", ".", "b"]);
        v.switch_to(View::F5);
        v.para_idx = 1;
        v.f5_to_f2();
        assert_eq!(v.view, View::F2);
        assert_eq!(v.ring.index, 3); // the first line of 'b'
        assert_eq!(v.entry.text(), "b");
    }

    #[test]
    fn the_f5_title_is_the_fence_or_the_file() {
        let (_d, mut v) = app(&["a", "/Segundo", "b"]);
        v.switch_to(View::F5);
        v.para_idx = 0;
        assert_eq!(v.f5_title(), "c"); // no fence above → the file's own name
        v.para_idx = 1;
        assert_eq!(v.f5_title(), "Segundo");
    }

    #[test]
    fn the_catalogue_excludes_the_source_the_portal_and_separators() {
        let (_d, mut v) = book();
        v.switch_to(View::F5); // active file is Uno.txt
        v.library.entries = vec![
            "Uno.txt".into(),
            ".".into(),
            "0.txt".into(),
            "Dos.txt".into(),
        ];
        assert_eq!(v.picker_entries(), vec!["Dos.txt"]);
    }

    #[test]
    fn the_catalogue_opens_next_to_the_active_file() {
        let (_d, mut v) = book();
        v.switch_to(View::F5);
        v.library.entries = vec![
            "A.txt".into(),
            "Uno.txt".into(), // the active file
            "B.txt".into(),
            "C.txt".into(),
        ];
        // entries seen: A, B, C — the nearest to Uno (index 1) is B, just after.
        v.open_picker();
        assert!(v.picker_open);
        assert_eq!(v.picker_entries()[v.picker_idx], "B.txt");
    }

    #[test]
    fn sending_a_paragraph_moves_it_into_the_chapter() {
        let (_d, mut v) = book();
        v.switch_to(View::F5);
        v.para_idx = 0; // 'de uno'
        assert!(v.send_para_to("Dos.txt").unwrap());

        // it arrived, after a separator, and left the source
        let dest = void::load_doc(&library::chapter_path(&v.void_dir, "Dos.txt"));
        assert!(dest.lines.contains(&"de uno".to_string()));
        assert!(dest.lines.contains(&"de dos".to_string()));
        assert!(!v.ring.lines.contains(&"de uno".to_string()));
        assert!(!v.picker_open);
    }

    #[test]
    fn sending_to_its_own_file_is_refused() {
        let (_d, mut v) = book();
        v.switch_to(View::F5);
        assert!(!v.send_para_to("Uno.txt").unwrap());
        assert!(v.ring.lines.contains(&"de uno".to_string()));
    }

    #[test]
    fn the_backtick_goes_to_the_scratch_and_back() {
        let (_d, mut v) = book();
        v.switch_to(View::F2);
        let origin = v.current_file.clone();

        v.scratch_toggle();
        assert!(v.current_file.ends_with("0.txt"));
        assert_eq!(v.view, View::F1); // dropped into writing
        assert!(v.scratch_path().exists()); // created on the way in

        v.scratch_toggle();
        assert_eq!(v.current_file, origin); // back where we were
        assert_eq!(v.view, View::F2);
        assert!(v.scratch_return.is_none()); // consumed
    }

    #[test]
    fn the_backtick_on_the_scratch_without_an_origin_stays_put() {
        let (_d, mut v) = book();
        v.set_active_file(v.scratch_path());
        v.scratch_toggle(); // arrived by other means → nothing to return to
        assert!(v.current_file.ends_with("0.txt"));
    }

    #[test]
    fn caps_lock_probe_never_panics() {
        let _ = caps_lock_on(); // best effort on any machine
    }
}

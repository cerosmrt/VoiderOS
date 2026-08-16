//! App state and the F1 view.
//!
//! The state (ring, entry, active file) is kept free of egui so it can be
//! tested without a display; `eframe::App` below only draws it and feeds it
//! keys.

#![allow(dead_code)]

use std::io;
use std::path::{Path, PathBuf};

use crate::config::Config;
use crate::f5;
use crate::fonts;
use crate::library::{self, Library};
use crate::paragraphs;
use crate::reformat;
use crate::split;
use crate::line_ring::LineRing;
use crate::text_line::{self, TextLine};
use crate::undo::{self, UndoManager};
use crate::void;
use chrono::Datelike;
use crate::words;

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
    /// Settings: the writing font and its size.
    F10,
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
    /// F3: a blank naming line for the book being merged is open below its dot.
    pub pending_merge: bool,
    /// F3: which separator the merge started from.
    pub merge_dot_idx: Option<usize>,
    /// F2: Enter on a `.` narrows navigation/swap to one paragraph.
    pub para_focus: bool,
    /// F2: the line indices that make up the focused paragraph.
    pub para_focus_content: Vec<usize>,
    /// F5: which paragraph the cursor is on.
    pub para_idx: usize,
    /// F5: the side catalogue for sending a paragraph to a chapter.
    pub picker_open: bool,
    pub picker_idx: usize,
    /// Where the backtick came from, so it can take you back.
    pub scratch_return: Option<(PathBuf, View)>,
    /// Persisted settings: the writing font, its size, the toggles.
    pub config: Config,
    /// F10: which font family is highlighted.
    pub settings_idx: usize,
    /// Raised when the font changed, so the view rebuilds it.
    pub font_dirty: bool,
    /// Text-content undo, recorded at the save chokepoint.
    pub undo: UndoManager,
    /// True while an undo is being written, so it does not record itself.
    pub undo_applying: bool,
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
        let config = Config::load(&void_dir);
        Self {
            typewriter: config.typewriter,
            show_title: config.show_title,
            config,
            void_dir,
            current_file,
            ring: LineRing::new(doc.lines),
            library: Library::default(),
            view: View::F1,
            entry: TextLine::new(""),
            pending_new: false,
            pending_merge: false,
            merge_dot_idx: None,
            para_focus: false,
            para_focus_content: Vec::new(),
            para_idx: 0,
            picker_open: false,
            picker_idx: 0,
            scratch_return: None,
            settings_idx: 0,
            font_dirty: false,
            undo: UndoManager::default(),
            undo_applying: false,
            load_failed: doc.read_failed,
            status: String::new(),
        }
    }

    /// Persist the ring to the active file. A failed load blocks the write.
    ///
    /// This is the chokepoint: every text change passes through here, so it is
    /// also where undo is recorded. `key` lets a burst of typing on one line
    /// coalesce into a single undo step.
    pub fn save(&mut self) -> io::Result<()> {
        self.save_keyed(None)
    }

    pub fn save_keyed(&mut self, key: Option<String>) -> io::Result<()> {
        if self.load_failed {
            self.status = "Save blocked: the active file failed to load".into();
            return Ok(());
        }
        let before = self.on_disk(&self.current_file.clone());
        let after = self.ring.lines.clone();
        // Safety net: if this save would gut the file, keep a .rescue copy of
        // what's on disk first. Never blocks the save — ordinary deleting is
        // normal work — it just makes a catastrophic silent shrink recoverable.
        if void::rescue_on_large_shrink(&self.current_file, &after) {
            self.status = "Large shrink — kept a .rescue copy".into();
        }
        void::atomic_write(&self.current_file, &after, false)?;
        if !self.undo_applying {
            let path = self.current_file.clone();
            self.undo.record(path, before, after, key);
        }
        Ok(())
    }

    /// What the file holds right now, as the ring would see it.
    fn on_disk(&self, path: &Path) -> Vec<String> {
        void::load_doc(path).lines
    }

    /// A git snapshot of the whole void, taken once as the session opens, so it
    /// can always be walked back to no matter what happens after. Best effort —
    /// never blocks startup.
    pub fn snapshot_on_entry(&self) {
        let msg = format!("voider-rs session {}", void::timestamp());
        void::git_commit(&self.void_dir, ".", &msg);
    }

    // ── Undo / redo ───────────────────────────────────────────────────────────

    /// Ctrl+Z. Restores every file in the last step — a paragraph sent away comes
    /// back to its source and leaves its destination in one go.
    pub fn undo(&mut self) -> io::Result<()> {
        let Some(entry) = self.undo.undo() else {
            self.status = "Nothing to undo".into();
            return Ok(());
        };
        self.apply_undo_entry(&entry, true)
    }

    /// Ctrl+Shift+Z.
    pub fn redo(&mut self) -> io::Result<()> {
        let Some(entry) = self.undo.redo() else {
            self.status = "Nothing to redo".into();
            return Ok(());
        };
        self.apply_undo_entry(&entry, false)
    }

    fn apply_undo_entry(&mut self, entry: &undo::Entry, backwards: bool) -> io::Result<()> {
        self.undo_applying = true;
        for change in &entry.files {
            let lines = if backwards { &change.before } else { &change.after };
            if lines.is_empty() {
                // A real Voider file always has at least a '.' — an empty target
                // means this file did not exist at this point in history (a
                // merge's freshly-made container going back, or a chapter a
                // merge deleted going forward), so undo restores that by
                // removing it, not by writing an empty file.
                let _ = std::fs::remove_file(&change.path);
            } else {
                void::atomic_write(&change.path, lines, false)?;
            }
            // If it's the file on screen, show the restored version at once.
            if change.path == self.current_file {
                let keep = self.ring.index;
                self.ring = LineRing::new(void::load_doc(&change.path).lines);
                self.ring.index = keep.min(self.ring.lines.len().saturating_sub(1));
                let cur = self.ring.current().to_string();
                self.entry.set_text(&cur);
                self.entry.home();
            }
        }
        self.undo_applying = false;
        self.status = if backwards { "Undone".into() } else { "Redone".into() };
        Ok(())
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
            View::F10 => {
                // Start the highlight on the font currently in use.
                let families = self.font_families();
                self.settings_idx = families
                    .iter()
                    .position(|f| fonts::normalise(f) == fonts::normalise(&self.config.font_family))
                    .unwrap_or(0);
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
        let target_before = void::load_doc(&target).lines;
        let source_before = void::load_doc(&self.current_file).lines;
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
        // Both files move as ONE undo step: taking it back returns the paragraph
        // to its source and removes it from the destination together.
        self.undo_applying = true;
        self.save()?;
        self.undo_applying = false;
        self.undo.record_transaction(
            vec![
                undo::FileChange {
                    path: self.current_file.clone(),
                    before: source_before,
                    after: self.ring.lines.clone(),
                },
                undo::FileChange {
                    path: target.clone(),
                    before: target_before,
                    after: void::load_doc(&target).lines,
                },
            ],
            Some("send".into()),
        );
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

    /// Tab in F3: on a separator dot, shuffle that book's files (numbered titles
    /// keep their order, the rest scatter); on a title, jump to a random one.
    pub fn book_tab(&mut self) -> io::Result<()> {
        self.settle_pending()?;
        if library::is_separator(self.library.current()) {
            if library::shuffle_group(&mut self.library.entries, self.library.index) {
                self.library.save(&self.void_dir)?;
                self.status = "Shuffled".into();
            }
        } else {
            self.book_random();
        }
        Ok(())
    }

    /// Jump to a random real chapter — never a separator, never the portal.
    pub fn book_random(&mut self) {
        let mut candidates: Vec<usize> = self
            .library
            .entries
            .iter()
            .enumerate()
            .filter(|(_, e)| !library::is_separator(e) && !library::is_portal(e))
            .map(|(i, _)| i)
            .collect();
        if candidates.is_empty() {
            return;
        }
        library::shuffle(&mut candidates);
        self.library.index = candidates[0];
    }

    // ── merging a book into one chapter (Ctrl+Shift+M on a dot in F3) ────────

    /// Ctrl+Shift+M on a separator: open a blank naming line right below it.
    /// Only makes sense on a dot — a no-op elsewhere or mid-merge already.
    pub fn book_merge_prompt(&mut self) {
        if !library::is_separator(self.library.current()) || self.pending_merge {
            return;
        }
        let idx = self.library.index;
        self.merge_dot_idx = Some(idx);
        self.library.entries.insert(idx + 1, String::new());
        self.library.index = idx + 1;
        self.pending_merge = true;
        self.entry.clear();
    }

    /// Remove the blank naming line and leave the book untouched.
    pub fn book_cancel_merge(&mut self) {
        self.pending_merge = false;
        let ph = self.merge_dot_idx.unwrap_or(self.library.index.saturating_sub(1)) + 1;
        if ph < self.library.entries.len() && self.library.entries[ph].is_empty() {
            self.library.entries.remove(ph);
        }
        let n = self.library.entries.len();
        self.library.index = ph.saturating_sub(1).min(n.saturating_sub(1));
        self.merge_dot_idx = None;
    }

    /// Collapse the book (from the dot to the next one) into ONE chapter named
    /// by what's in the entry: each chapter's lines, followed by a `/name` seal
    /// marker, originals removed. Re-splitting (Ctrl+Shift+S) restores them.
    /// Stays in F3. An empty name or an empty book cancels instead of merging.
    /// Returns how many chapters were merged (0 = cancelled).
    pub fn book_do_merge(&mut self) -> io::Result<usize> {
        let name = self.entry.text().trim().to_string();
        let dot_idx = self.merge_dot_idx.unwrap_or(self.library.index.saturating_sub(1));
        let ph = dot_idx + 1;
        let n = self.library.entries.len();
        let mut chapters: Vec<(usize, String)> = Vec::new();
        let mut i = ph + 1;
        while i < n && self.library.entries[i] != library::SEPARATOR {
            let fname = self.library.entries[i].clone();
            if !fname.is_empty() && !library::is_portal(&fname) {
                chapters.push((i, fname));
            }
            i += 1;
        }
        if name.is_empty() || chapters.is_empty() {
            self.book_cancel_merge();
            return Ok(0);
        }

        void::git_commit(&self.void_dir, "I/", &format!("merge {}", void::timestamp()));
        let i_dir = self.void_dir.join("I");

        let mut merged: Vec<String> = Vec::new();
        for (_, fname) in &chapters {
            let fpath = library::chapter_path(&self.void_dir, fname);
            let mut lines: Vec<String> = std::fs::read_to_string(&fpath)
                .map(|t| t.lines().map(|l| l.trim_end().to_string()).collect())
                .unwrap_or_default();
            while lines.last().map(|l| l.trim().is_empty()).unwrap_or(false) {
                lines.pop();
            }
            merged.extend(lines);
            merged.push(format!("/{}", library::display_name(fname)));
        }

        // A name clash steps to "name-2", "name-3", ... like a new chapter would.
        let mut cname = format!("{name}.txt");
        let mut cpath = i_dir.join(&cname);
        let mut k = 2;
        while cpath.exists() || self.library.entries.contains(&cname) {
            cname = format!("{name}-{k}.txt");
            cpath = i_dir.join(&cname);
            k += 1;
        }

        let mut changes = vec![undo::FileChange {
            path: cpath.clone(),
            before: Vec::new(),
            after: merged.clone(),
        }];
        void::atomic_write(&cpath, &merged, false)?;

        self.library.entries[ph] = cname.clone();
        let mut removed = chapters.clone();
        removed.sort_by(|a, b| b.0.cmp(&a.0)); // remove back-to-front
        for (idx, fname) in &removed {
            let fpath = library::chapter_path(&self.void_dir, fname);
            let before: Vec<String> = std::fs::read_to_string(&fpath)
                .map(|t| t.lines().map(|l| l.trim_end().to_string()).collect())
                .unwrap_or_default();
            changes.push(undo::FileChange { path: fpath.clone(), before, after: Vec::new() });
            let _ = std::fs::remove_file(&fpath);
            self.library.entries.remove(*idx);
        }

        self.pending_merge = false;
        self.merge_dot_idx = None;
        self.library.index = ph;
        self.library.save(&self.void_dir)?;
        self.undo.record_transaction(changes, Some("merge".into()));
        self.entry.clear();
        let n_chapters = chapters.len();
        self.status = format!("Merged {n_chapters} chapter(s) → {cname}");
        Ok(n_chapters)
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
        // Keyed by the line: a burst of typing on it is one undo step, not one
        // per keystroke.
        self.save_keyed(Some(format!("doc:{i}")))
    }

    /// Move through the document. The caret lands at the start of the new line —
    /// unless it was sitting at the end of the old one, in which case it stays
    /// at the end, so walking a paragraph feels continuous. Focused (see
    /// `enter_para_focus`), it walks only within the paragraph, wrapping there.
    pub fn doc_navigate(&mut self, delta: isize) -> io::Result<()> {
        let at_end = self.entry.caret() == self.entry.len();
        self.doc_live_save()?;
        if self.para_focus && !self.para_focus_content.is_empty() {
            let n = self.para_focus_content.len() as isize;
            let cur = self.ring.index;
            let pos = self.para_focus_content.iter().position(|&c| c == cur).unwrap_or(0);
            let next = (pos as isize + delta).rem_euclid(n) as usize;
            self.ring.index = self.para_focus_content[next];
        } else {
            self.ring.move_by(delta);
        }
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
    /// next line, and you land on it. Focused, the new line joins the paragraph.
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
        if self.para_focus {
            for idx in self.para_focus_content.iter_mut() {
                if *idx > i {
                    *idx += 1;
                }
            }
            if let Some(p) = self.para_focus_content.iter().position(|&c| c == i) {
                self.para_focus_content.insert(p + 1, i + 1);
            }
        }
        let cur = self.ring.current().to_string();
        self.entry.set_text(&cur);
        self.entry.home();
        self.save()
    }

    /// Enter with the caret at the start of the line: on a `.`, enter focus on
    /// the paragraph after it; focused, leave it; otherwise split at 0 (a blank
    /// line above) or, on an empty line, drop into F1 to write it.
    pub fn doc_confirm_edit(&mut self) -> io::Result<()> {
        let cur = self.ring.current().to_string();
        if cur == "." && !self.para_focus {
            self.enter_para_focus();
            return Ok(());
        }
        if self.para_focus {
            self.exit_para_focus();
            return Ok(());
        }
        if cur.trim().is_empty() {
            self.switch_to(View::F1);
            Ok(())
        } else {
            self.doc_split_line()
        }
    }

    /// Narrow to one paragraph: the lines between the dot at the cursor and the
    /// next one. A no-op on an empty paragraph (nothing to focus on).
    pub fn enter_para_focus(&mut self) {
        let n = self.ring.lines.len();
        if n == 0 {
            return;
        }
        let dot_idx = self.ring.index;
        let mut content = Vec::new();
        let mut i = (dot_idx + 1) % n;
        for _ in 0..n.saturating_sub(1) {
            if self.ring.lines[i] == "." {
                break;
            }
            content.push(i);
            i = (i + 1) % n;
        }
        if content.is_empty() {
            return;
        }
        self.para_focus = true;
        self.ring.index = content[0];
        self.para_focus_content = content;
        self.sync_entry();
    }

    /// Leave focus and land back on the dot that opens the paragraph.
    pub fn exit_para_focus(&mut self) {
        self.para_focus = false;
        self.para_focus_content.clear();
        let n = self.ring.lines.len();
        if n == 0 {
            return;
        }
        let mut idx = (self.ring.index + n - 1) % n;
        for _ in 0..n {
            if self.ring.lines[idx] == "." {
                self.ring.index = idx;
                break;
            }
            idx = (idx + n - 1) % n;
        }
        self.sync_entry();
    }

    /// Alt+Up/Down while focused: swap the current line with its neighbour
    /// WITHIN the paragraph, wrapping there rather than through the whole
    /// document.
    pub fn swap_line_in_focus(&mut self, delta: isize) -> io::Result<()> {
        if self.para_focus_content.is_empty() {
            return Ok(());
        }
        let n = self.para_focus_content.len() as isize;
        let cur = self.ring.index;
        let pos = self.para_focus_content.iter().position(|&c| c == cur).unwrap_or(0);
        let other_pos = (pos as isize + delta).rem_euclid(n) as usize;
        let other = self.para_focus_content[other_pos];
        self.ring.lines.swap(cur, other);
        self.para_focus_content.swap(pos, other_pos);
        self.ring.index = other;
        self.sync_entry();
        self.save()
    }

    /// Alt+Up/Down in F2: move the current line past its neighbour, wrapping at
    /// the ends. The cursor travels with the line, so it can be walked up a
    /// paragraph.
    pub fn doc_swap_line(&mut self, direction: isize) -> io::Result<()> {
        let n = self.ring.lines.len();
        if n < 2 {
            return Ok(());
        }
        // Focused, the swap stays inside the paragraph.
        if self.para_focus {
            return self.swap_line_in_focus(direction);
        }
        // On a separator, the whole paragraph moves rather than the dot.
        if self.ring.current() == "." {
            return self.doc_move_paragraph(direction);
        }
        self.doc_live_save()?;
        let cur = self.ring.index;
        let other = (cur as isize + direction).rem_euclid(n as isize) as usize;
        self.ring.lines.swap(cur, other);
        self.ring.index = other;
        let text = self.ring.current().to_string();
        self.entry.set_text(&text);
        self.entry.home();
        self.save()
    }

    // ── The cut-up ────────────────────────────────────────────────────────────

    /// Tab: pull a random line from another chapter into the entry, to keep or
    /// discard. This is loop writing — a line recirculated without its context.
    /// It only ever COPIES: the file it came from is never touched.
    pub fn recycle_line(&mut self) {
        match self.random_line_from_book() {
            Some(line) => {
                self.entry.set_text(&line);
                self.entry.end();
            }
            None => self.status = "Nothing to recycle yet".into(),
        }
    }

    /// A random line of real text from any chapter but the active one.
    pub fn random_line_from_book(&mut self) -> Option<String> {
        if self.library.entries.is_empty() {
            self.library = Library::load(&self.void_dir);
        }
        let src = self
            .current_file
            .file_name()
            .map(|s| s.to_string_lossy().to_string())
            .unwrap_or_default();
        let mut lines: Vec<String> = Vec::new();
        for entry in &self.library.entries {
            if library::is_separator(entry) || *entry == src {
                continue;
            }
            let path = library::chapter_path(&self.void_dir, entry);
            lines.extend(
                void::load_doc(&path)
                    .lines
                    .into_iter()
                    .filter(|l| !l.trim().is_empty() && l.trim() != "."),
            );
        }
        if lines.is_empty() {
            return None;
        }
        library::shuffle(&mut lines);
        lines.into_iter().next()
    }

    // ── Shaping ───────────────────────────────────────────────────────────────

    /// Ctrl+Shift+F: break the active file into one sentence per line. Backed up
    /// to `.bak` first, and a single undo step.
    pub fn reformat_file(&mut self) -> io::Result<()> {
        let before = self.ring.lines.clone();
        let after = reformat::reformat(&before);
        if after == before {
            self.status = "Already one sentence per line".into();
            return Ok(());
        }
        void::atomic_write(&self.current_file, &after, true)?; // keeps a .bak
        self.ring.lines = after.clone();
        self.ring.index = self.ring.index.min(self.ring.lines.len() - 1);
        self.sync_entry();
        self.undo.record(self.current_file.clone(), before, after, None);
        self.status = "Reformatted".into();
        Ok(())
    }

    /// Ctrl+Shift+F on the scratch: FORMAT, then SPLIT.
    ///
    /// 1. Reformat the scratch into one sentence per line (the `.bak` this
    ///    leaves holds the true original, since nothing is written until step 3).
    /// 2. Every block whose LAST line is a `/name` marker moves to `I/name.txt`
    ///    (created below the `0` portal in the library, or appended if the name
    ///    already exists) and leaves the scratch. `/` alone is auto-named
    ///    `YY-M-D_N`. A block that's ONLY a marker (nothing above it) is left
    ///    exactly as it was — there is nothing to move.
    /// 3. What's left of the scratch — the unmarked blocks, reformatted — is
    ///    written back.
    ///
    /// Chaos in, documents out. One git snapshot, one undo step for everything
    /// this touches. Returns (blocks moved, new docs created).
    pub fn split_scratch_into_docs(&mut self) -> io::Result<(usize, usize)> {
        if self.current_file != self.scratch_path() {
            self.status = "Format/split only applies to the scratch".into();
            return Ok((0, 0));
        }
        if self.library.entries.is_empty() {
            self.library = Library::load(&self.void_dir);
        }

        let original = self.ring.lines.clone();
        let formatted = reformat::reformat(&original);
        let blocks = zero_blocks(&formatted);

        let i_dir = self.void_dir.join("I");
        let now = chrono::Local::now();
        let date_base = format!(
            "{}-{}-{}",
            now.year() % 100,
            now.month(),
            now.day()
        );
        let mut used_names: std::collections::HashSet<String> = std::collections::HashSet::new();

        let mut kept: Vec<Vec<String>> = Vec::new();
        let mut moves: Vec<(String, Vec<String>)> = Vec::new();
        for blk in blocks {
            let last = blk.last().map(|s| s.trim()).unwrap_or("");
            if last.starts_with('/') {
                let content = blk[..blk.len() - 1].to_vec();
                if content.is_empty() {
                    kept.push(blk); // only a marker: nothing to move
                    continue;
                }
                let mut name = last.trim_start_matches('/').trim().to_string();
                if name.is_empty() {
                    name = next_auto_name(&i_dir, &date_base, &mut used_names);
                }
                moves.push((name, content));
            } else {
                kept.push(blk);
            }
        }

        if moves.is_empty() {
            // Formatting always writes (and backs up), even when nothing actually
            // changed — the write is the point, not an optimisation.
            void::atomic_write(&self.current_file, &formatted, true)?;
            self.ring.lines = formatted.clone();
            self.sync_entry();
            self.undo.record(self.current_file.clone(), original, formatted, None);
            self.status = "Formatted — no '/name' blocks to split".into();
            return Ok((0, 0));
        }

        void::git_commit(&self.void_dir, "I/", &format!("split-zero {}", void::timestamp()));

        let mut changes: Vec<undo::FileChange> = Vec::new();
        let mut created: Vec<(String, PathBuf)> = Vec::new();

        for (name, content) in &moves {
            let fname = if name.to_lowercase().ends_with(".txt") {
                name.clone()
            } else {
                format!("{name}.txt")
            };
            let path = i_dir.join(&fname);
            let is_new = !path.exists();
            let before: Vec<String> = if is_new {
                Vec::new()
            } else {
                std::fs::read_to_string(&path)
                    .map(|t| t.lines().map(|l| l.trim_end().to_string()).collect())
                    .unwrap_or_default()
            };
            let mut after = before.clone();
            if !after.is_empty() {
                after.push(".".to_string());
            }
            after.extend(content.iter().cloned());
            void::atomic_write(&path, &after, false)?;
            changes.push(undo::FileChange { path: path.clone(), before, after });
            if is_new {
                created.push((fname, path));
            }
        }

        let mut new_zero: Vec<String> = Vec::new();
        for blk in &kept {
            new_zero.push(".".to_string());
            new_zero.extend(blk.iter().cloned());
        }
        if new_zero.is_empty() {
            new_zero.push(".".to_string());
        }
        // Backs up whatever is STILL on disk — the untouched original, since
        // nothing has been written to the scratch until this line.
        void::atomic_write(&self.current_file, &new_zero, true)?;
        changes.push(undo::FileChange {
            path: self.current_file.clone(),
            before: original,
            after: new_zero.clone(),
        });
        self.ring.lines = new_zero;
        self.sync_entry();

        if !created.is_empty() {
            let portal_at = self
                .library
                .entries
                .iter()
                .position(|e| library::is_portal(e));
            let mut ins = portal_at.map(|i| i + 1).unwrap_or(self.library.entries.len());
            for (fname, _) in &created {
                self.library.entries.insert(ins, fname.clone());
                ins += 1;
            }
            self.library.save(&self.void_dir)?;
        }

        self.undo.record_transaction(changes, Some("split-zero".into()));
        let (n_moved, n_created) = (moves.len(), created.len());
        self.status = format!("Split: {n_moved} block(s) moved, {n_created} new doc(s)");
        Ok((n_moved, n_created))
    }

    /// Ctrl+Shift+R on the scratch: randomise its lines. Only ever the scratch —
    /// it is the formless place documents are formed from. A `.bak` is kept.
    pub fn shuffle_scratch(&mut self) -> io::Result<()> {
        if self.current_file != self.scratch_path() {
            self.status = "Shuffle only applies to the scratch".into();
            return Ok(());
        }
        let before = self.ring.lines.clone();
        let mut content: Vec<String> = before
            .iter()
            .filter(|l| !l.trim().is_empty() && l.trim() != ".")
            .cloned()
            .collect();
        if content.len() < 2 {
            self.status = "Nothing to shuffle".into();
            return Ok(());
        }
        library::shuffle(&mut content);
        let mut after = vec![".".to_string()];
        after.extend(content);
        void::atomic_write(&self.current_file, &after, true)?;
        self.ring.lines = after.clone();
        self.ring.index = 0;
        self.sync_entry();
        self.undo.record(self.current_file.clone(), before, after, None);
        self.status = "Shuffled".into();
        Ok(())
    }

    /// Ctrl+Shift+S: seal the active file at its `/name` markers into chapters.
    ///
    /// Each sealed chapter is written and listed in reading order at the
    /// container's slot; a name that already exists is APPENDED to, never
    /// overwritten. What follows the last marker stays in the file, and if that
    /// remainder is empty the emptied container is removed from the library.
    /// One git snapshot up front, one undo step for the whole thing.
    pub fn split_at_markers(&mut self) -> io::Result<usize> {
        let Some(plan) = split::plan(&self.ring.lines) else {
            self.status = "No '/name' markers to split".into();
            return Ok(0);
        };
        void::git_commit(&self.void_dir, "I/", &format!("split {}", void::timestamp()));
        self.library = Library::load(&self.void_dir);

        let source_name = self
            .current_file
            .file_name()
            .map(|s| s.to_string_lossy().to_string())
            .unwrap_or_default();
        let mut changes: Vec<undo::FileChange> = Vec::new();
        // Insert the new chapters at the container's slot, keeping reading order.
        let mut at = self.library.position(&source_name).unwrap_or(0);

        // The container is trimmed FIRST. A marker may name the container itself;
        // sealing afterwards then appends onto the trimmed file instead of the
        // container write landing on top and swallowing the sealed text.
        let source_before = self.ring.lines.clone();
        let remainder_has_text = plan
            .remainder
            .iter()
            .any(|l| l.trim() != "." && !l.trim().is_empty());
        let source_after = if remainder_has_text {
            let mut r = vec![".".to_string()];
            r.extend(plan.remainder.iter().cloned());
            r
        } else {
            vec![".".to_string()]
        };
        void::atomic_write(&self.current_file, &source_after, false)?;
        changes.push(undo::FileChange {
            path: self.current_file.clone(),
            before: source_before,
            after: source_after,
        });

        for chapter in &plan.sealed {
            let file = format!("{}.txt", chapter.name);
            let path = library::chapter_path(&self.void_dir, &file);
            let before = if path.exists() {
                void::load_doc(&path).lines
            } else {
                Vec::new()
            };
            // An existing chapter is appended to: a text already there survives.
            let mut body: Vec<String> = Vec::new();
            let existing_has_text = before.iter().any(|l| l != ".");
            if existing_has_text {
                body.extend(before.iter().cloned());
                body.push(".".to_string());
            }
            body.extend(chapter.lines.iter().cloned());
            let after = if body.is_empty() { vec![".".to_string()] } else { body };
            void::atomic_write(&path, &after, false)?;
            changes.push(undo::FileChange { path, before, after });

            if self.library.position(&file).is_none() {
                self.library.insert_below(at, file);
            }
            at += 1;
        }

        // An emptied container is no longer a chapter of the book — unless a
        // marker named it (then it holds that sealed text) or it's the scratch
        // (which always needs to exist). Removed for real, on disk and all, so
        // a merged book re-splits cleanly (the merge left no A.txt/B.txt behind
        // for this exact reason).
        let sealed_into_container = plan
            .sealed
            .iter()
            .any(|c| format!("{}.txt", c.name) == source_name);
        let container_removed =
            !remainder_has_text && !sealed_into_container && source_name != library::PORTAL;
        if container_removed {
            self.library.entries.retain(|e| *e != source_name);
            let _ = std::fs::remove_file(&self.current_file);
            if let Some(c) = changes.first_mut() {
                c.after.clear(); // tells undo this file should not exist
            }
        }
        self.library.save(&self.void_dir)?;

        self.ring = if container_removed {
            LineRing::new([".".to_string()])
        } else {
            LineRing::new(void::load_doc(&self.current_file).lines)
        };
        self.sync_entry();
        self.undo.record_transaction(changes, Some("split".into()));
        let n = plan.sealed.len();
        self.status = format!("Split into {n} chapter(s)");
        Ok(n)
    }

    // ── Navigation ────────────────────────────────────────────────────────────

    /// PageDown/PageUp: jump to the next/previous `.` — paragraph by paragraph.
    /// Wraps, and stays put when the file has no separators.
    pub fn goto_dot(&mut self, direction: isize) {
        let n = self.ring.lines.len();
        if n == 0 {
            return;
        }
        let mut idx = self.ring.index as isize;
        for _ in 0..n {
            idx = (idx + direction).rem_euclid(n as isize);
            if self.ring.lines[idx as usize] == "." {
                self.ring.index = idx as usize;
                self.sync_entry();
                return;
            }
        }
    }

    /// Home/End in F2: the first / last line that carries text.
    pub fn doc_jump_edge(&mut self, to_end: bool) {
        let found = if to_end {
            self.ring.lines.iter().rposition(|l| l != ".")
        } else {
            self.ring.lines.iter().position(|l| l != ".")
        };
        if let Some(i) = found {
            self.ring.index = i;
            self.sync_entry();
            if to_end {
                self.entry.end();
            }
        }
    }

    /// Ctrl+0: rotate the file so the current line becomes its first.
    pub fn rebase_to_current(&mut self) -> io::Result<()> {
        if self.ring.index == 0 {
            return Ok(());
        }
        self.doc_live_save()?;
        self.ring.rebase_to_current();
        self.sync_entry();
        self.save()
    }

    /// Alt+Up/Down in F1: walk the library without going through F3.
    pub fn step_file(&mut self, direction: isize) {
        if self.library.entries.is_empty() {
            self.library = Library::load(&self.void_dir);
        }
        let chapters: Vec<String> = self
            .library
            .entries
            .iter()
            .filter(|e| !library::is_separator(e))
            .cloned()
            .collect();
        if chapters.is_empty() {
            return;
        }
        let name = self
            .current_file
            .file_name()
            .map(|s| s.to_string_lossy().to_string())
            .unwrap_or_default();
        let here = chapters.iter().position(|c| *c == name).unwrap_or(0) as isize;
        let next = (here + direction).rem_euclid(chapters.len() as isize) as usize;
        let path = library::chapter_path(&self.void_dir, &chapters[next]);
        self.set_active_file(path);
        self.sync_entry();
    }

    /// Show whatever the cursor is on, the way the current view shows it.
    fn sync_entry(&mut self) {
        match self.view {
            View::F1 => self.show_current(),
            _ => {
                let cur = self.ring.current().to_string();
                self.entry.set_text(&cur);
                self.entry.home();
            }
        }
    }

    /// Alt+Up/Down while sitting on a `.`: move that whole paragraph. At the
    /// ends it moves round rather than swapping — the first becomes the last.
    pub fn doc_move_paragraph(&mut self, direction: isize) -> io::Result<()> {
        let (_, paras) = paragraphs::from_lines(&self.ring.lines);
        let Some(k) = paragraphs::para_at_dot(&self.ring.lines, self.ring.index) else {
            return Ok(());
        };
        let Some((moved, dest)) = paragraphs::move_paragraph(&paras, k, direction) else {
            return Ok(());
        };
        self.ring.lines = paragraphs::to_lines(&moved);
        self.ring.index = paragraphs::dot_line_index(dest, &moved);
        let cur = self.ring.current().to_string();
        self.entry.set_text(&cur);
        self.entry.home();
        self.save()
    }

    /// Alt+Left/Right in F2: move the word under the caret along the line.
    pub fn doc_swap_words(&mut self, direction: isize) -> io::Result<()> {
        if let Some((text, caret)) =
            words::swap_words(&self.entry.text(), self.entry.caret(), direction)
        {
            self.entry.set_text(&text);
            self.entry.set_caret(caret);
            self.doc_live_save()?;
        }
        Ok(())
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

    // ── F10: settings ─────────────────────────────────────────────────────────

    /// The font families this machine can offer.
    pub fn font_families(&self) -> Vec<String> {
        fonts::available_families()
    }

    /// Move the highlight through the offered families and adopt the one landed
    /// on, so the change is visible while you choose.
    pub fn settings_step_family(&mut self, delta: isize) {
        let families = self.font_families();
        if families.is_empty() {
            return;
        }
        let n = families.len() as isize;
        self.settings_idx = (self.settings_idx as isize + delta).rem_euclid(n) as usize;
        self.config.font_family = families[self.settings_idx].clone();
        self.font_dirty = true;
        self.persist_config();
    }

    pub fn settings_step_size(&mut self, delta: isize) {
        self.config.step_size(delta);
        self.persist_config();
    }

    /// Write the settings out, keeping the live toggles in step with them.
    pub fn persist_config(&mut self) {
        self.config.typewriter = self.typewriter;
        self.config.show_title = self.show_title;
        if let Err(e) = self.config.save(&self.void_dir) {
            self.status = format!("Could not save settings: {e}");
        }
    }

    /// The scratch, `I/0.txt` — where writing goes when it has no home yet.
    pub fn scratch_path(&self) -> PathBuf {
        library::chapter_path(&self.void_dir, library::PORTAL)
    }

    /// Where a deleted line lands before it's gone for good.
    pub fn trash_path(&self) -> PathBuf {
        library::chapter_path(&self.void_dir, "trash.txt")
    }

    /// Ctrl+Delete in F2: a three-level cascade. Deleting from any other file
    /// sends the line to the scratch; from the scratch, to `trash.txt`; from
    /// `trash.txt`, it is simply gone. The line is never filtered — even a `.`
    /// separator travels down the cascade like any other line.
    pub fn delete_line_to_zero(&mut self) -> io::Result<()> {
        let n = self.ring.lines.len();
        if n <= 1 {
            return Ok(());
        }
        let cur = self.ring.index;
        let line = self.ring.lines[cur].clone();
        let scratch = self.scratch_path();
        let trash = self.trash_path();

        if self.current_file == trash {
            self.status = "Deleted permanently".into();
        } else if self.current_file == scratch {
            self.append_line(&trash, &line)?;
            self.status = "→ trash.txt".into();
        } else {
            self.append_line(&scratch, &line)?;
            self.status = "→ 0.txt".into();
        }

        self.ring.lines.remove(cur);
        self.ring.index = cur.min(self.ring.lines.len().saturating_sub(1));
        self.sync_entry();
        self.save()
    }

    /// Append one line to `path`, creating it if it doesn't exist yet. Read
    /// through the normal loader so a hand-edited or malformed file still gets
    /// the leading `.` it needs.
    fn append_line(&self, path: &Path, line: &str) -> io::Result<()> {
        let mut lines = if path.exists() {
            void::load_doc(path).lines
        } else {
            vec![".".to_string()]
        };
        lines.push(line.to_string());
        void::atomic_write(path, &lines, false)
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

/// Parse lines into blocks: the runs of non-dot, non-blank lines between `.`
/// separators, in order. A port of `_zero_blocks`.
fn zero_blocks(lines: &[String]) -> Vec<Vec<String>> {
    let mut blocks = Vec::new();
    let mut cur: Vec<String> = Vec::new();
    for line in lines {
        let s = line.trim();
        if s == "." {
            if !cur.is_empty() {
                blocks.push(std::mem::take(&mut cur));
            }
        } else if !s.is_empty() {
            cur.push(line.clone());
        }
    }
    if !cur.is_empty() {
        blocks.push(cur);
    }
    blocks
}

/// `YY-M-D_N`: the next name not already used this run or taken on disk.
fn next_auto_name(i_dir: &Path, date_base: &str, used: &mut std::collections::HashSet<String>) -> String {
    let mut n = 1usize;
    loop {
        let cand = format!("{date_base}_{n}");
        if !used.contains(&cand) && !i_dir.join(format!("{cand}.txt")).exists() {
            used.insert(cand.clone());
            return cand;
        }
        n += 1;
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
    v.snapshot_on_entry();
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

    // ── F3 Tab: shuffle a book / jump to a random chapter ────────────────────

    #[test]
    fn tab_on_a_dot_shuffles_the_book_and_persists() {
        let (_d, mut v) = book();
        v.switch_to(View::F3);
        v.library.entries = vec![".".into(), "A.txt".into(), "B.txt".into(), "C.txt".into()];
        v.library.index = 0; // on the separator
        v.book_tab().unwrap();
        let mut got = v.library.entries[1..4].to_vec();
        got.sort();
        assert_eq!(got, vec!["A.txt", "B.txt", "C.txt"]); // same files
        // Force-persist and reload: whether or not this particular shuffle
        // happened to land back on the original order (and so skipped its own
        // save), the in-memory state should always be what disk holds.
        v.library.save(&v.void_dir).unwrap();
        assert_eq!(Library::load(&v.void_dir).entries, v.library.entries);
    }

    #[test]
    fn tab_on_a_title_jumps_to_a_random_real_chapter() {
        let (_d, mut v) = book();
        v.switch_to(View::F3);
        v.library.entries = vec!["Uno.txt".into(), "Dos.txt".into()];
        v.library.index = 0;
        v.book_tab().unwrap();
        assert!(!library::is_separator(v.library.current()));
        assert!(!library::is_portal(v.library.current()));
    }

    #[test]
    fn book_random_never_lands_on_a_separator_or_the_portal() {
        let (_d, mut v) = book();
        v.library.entries = vec!["0.txt".into(), ".".into(), "A.txt".into()];
        for _ in 0..15 {
            v.book_random();
            assert_eq!(v.library.current(), "A.txt"); // the only eligible one
        }
    }

    #[test]
    fn book_random_with_nothing_eligible_does_not_move() {
        let (_d, mut v) = book();
        v.library.entries = vec!["0.txt".into(), ".".into()];
        v.library.index = 0;
        v.book_random();
        assert_eq!(v.library.index, 0);
    }

    #[test]
    fn alt_moves_the_line_and_the_cursor_follows() {
        let (_d, mut v) = app(&[".", "a", "b"]);
        v.ring.index = 1;
        v.switch_to(View::F2);
        v.doc_swap_line(1).unwrap();
        assert_eq!(v.ring.lines, vec![".", "b", "a"]);
        assert_eq!(v.ring.index, 2); // travelled with the line
        assert_eq!(v.entry.text(), "a");
        assert!(void::load_doc(&v.current_file).lines.contains(&"b".to_string()));
    }

    #[test]
    fn moving_a_line_wraps_at_the_ends() {
        let (_d, mut v) = app(&["a", "b"]); // loads as [".", "a", "b"]
        v.ring.index = 1; // on 'a', a content line
        v.switch_to(View::F2);
        v.doc_swap_line(-1).unwrap();
        assert_eq!(v.ring.index, 0); // moved up onto the separator's slot
        assert_eq!(v.ring.lines, vec!["a", ".", "b"]);
    }

    #[test]
    fn on_a_separator_alt_moves_the_whole_paragraph() {
        let (_d, mut v) = app(&[".", "a1", "a2", ".", "b"]);
        v.ring.index = 0; // sitting on the first '.'
        v.switch_to(View::F2);
        v.doc_swap_line(1).unwrap(); // Alt+Down
        assert_eq!(v.ring.lines, vec![".", "b", ".", "a1", "a2"]);
        assert_eq!(v.ring.index, 2); // the cursor rode with the paragraph
    }

    #[test]
    fn the_first_paragraph_moved_up_goes_to_the_end() {
        let (_d, mut v) = app(&[".", "a", ".", "b", ".", "c"]);
        v.ring.index = 0;
        v.switch_to(View::F2);
        v.doc_swap_line(-1).unwrap();
        // it moves round rather than swapping with the one above
        assert_eq!(v.ring.lines, vec![".", "b", ".", "c", ".", "a"]);
    }

    #[test]
    fn alt_moves_the_word_under_the_caret() {
        let (_d, mut v) = app(&[".", "hola mundo cruel"]);
        v.ring.index = 1;
        v.switch_to(View::F2);
        v.entry.set_caret(0); // on 'hola'
        v.doc_swap_words(1).unwrap();
        assert_eq!(v.entry.text(), "mundo hola cruel");
        assert_eq!(v.ring.lines[1], "mundo hola cruel"); // persisted
    }

    // ── the cut-up ────────────────────────────────────────────────────────────

    #[test]
    fn tab_brings_a_line_from_another_chapter() {
        let (_d, mut v) = book(); // active is Uno.txt; Dos.txt holds 'de dos'
        v.library = Library::load(&v.void_dir);
        v.recycle_line();
        assert_eq!(v.entry.text(), "de dos"); // came from elsewhere
        assert_eq!(v.entry.caret(), 6); // ready to keep writing from its end
    }

    #[test]
    fn recycling_never_takes_from_the_file_you_are_in() {
        let (_d, mut v) = book();
        v.library = Library::load(&v.void_dir);
        for _ in 0..10 {
            v.recycle_line();
            assert_ne!(v.entry.text(), "de uno"); // that's the active file's line
        }
    }

    #[test]
    fn recycling_leaves_the_source_untouched() {
        let (_d, mut v) = book();
        v.library = Library::load(&v.void_dir);
        v.recycle_line();
        let src = void::load_doc(&library::chapter_path(&v.void_dir, "Dos.txt"));
        assert!(src.lines.contains(&"de dos".to_string())); // it was only copied
    }

    #[test]
    fn recycling_with_nowhere_to_pull_from_says_so() {
        let (_d, mut v) = app(&[".", "sola"]);
        v.library = Library::default();
        v.library.entries = vec![];
        v.recycle_line();
        assert_eq!(v.status, "Nothing to recycle yet");
    }

    // ── safety: shrink guard + entry snapshot ───────────────────────────────────

    #[test]
    fn a_gutting_save_leaves_a_rescue_copy_and_says_so() {
        let lines: Vec<&str> = std::iter::once(".").chain(std::iter::repeat("linea").take(15)).collect();
        let (_d, mut v) = app(&lines);
        v.ring.lines.truncate(2); // drop most of the content
        v.save().unwrap();
        assert!(void::rescue_path(&v.current_file).exists());
        assert!(v.status.contains("rescue"));
    }

    #[test]
    fn an_ordinary_save_leaves_no_rescue_copy() {
        let (_d, mut v) = app(&[".", "a", "b", "c"]);
        v.ring.lines.push("d".into());
        v.save().unwrap();
        assert!(!void::rescue_path(&v.current_file).exists());
    }

    #[test]
    fn the_entry_snapshot_commits_the_whole_void() {
        let dir = tempfile::tempdir().unwrap();
        for args in [
            vec!["init", "-q"],
            vec!["config", "user.email", "t@t"],
            vec!["config", "user.name", "t"],
        ] {
            std::process::Command::new("git")
                .arg("-C")
                .arg(dir.path())
                .args(&args)
                .output()
                .unwrap();
        }
        std::fs::create_dir_all(dir.path().join("I")).unwrap();
        std::fs::write(dir.path().join("I/a.txt"), "hola\n").unwrap();

        let v = Voider::open(dir.path(), dir.path().join("I/a.txt"));
        v.snapshot_on_entry();

        let log = std::process::Command::new("git")
            .arg("-C")
            .arg(dir.path())
            .args(["log", "--oneline"])
            .output()
            .unwrap();
        let out = String::from_utf8_lossy(&log.stdout);
        assert!(out.contains("voider-rs session"));
    }

    // ── shaping ───────────────────────────────────────────────────────────────

    #[test]
    fn reformatting_breaks_the_file_into_sentences_and_is_undoable() {
        let (_d, mut v) = app(&["Una frase. Otra frase."]);
        v.reformat_file().unwrap();
        assert_eq!(v.ring.lines, vec![".", "Una frase.", "Otra frase."]);
        assert_eq!(void::load_doc(&v.current_file).lines, v.ring.lines);
        // and there is a .bak of what it was
        assert!(void::backup_path(&v.current_file).exists());

        v.undo().unwrap();
        assert!(void::load_doc(&v.current_file)
            .lines
            .contains(&"Una frase. Otra frase.".to_string()));
    }

    #[test]
    fn reformatting_an_already_formatted_file_does_nothing() {
        let (_d, mut v) = app(&[".", "Sola."]);
        v.reformat_file().unwrap();
        assert_eq!(v.status, "Already one sentence per line");
        assert!(!v.undo.can_undo());
    }

    #[test]
    fn shuffling_only_applies_to_the_scratch() {
        let (_d, mut v) = app(&[".", "a", "b", "c"]);
        v.shuffle_scratch().unwrap();
        assert_eq!(v.ring.lines, vec![".", "a", "b", "c"]); // a chapter is left alone
        assert!(v.status.contains("only applies"));
    }

    #[test]
    fn shuffling_the_scratch_keeps_every_line() {
        let (_d, mut v) = book();
        v.set_active_file(v.scratch_path());
        v.ring.lines = vec![".".into(), "a".into(), ".".into(), "b".into(), "c".into()];
        v.shuffle_scratch().unwrap();
        let mut got: Vec<String> = v.ring.lines.iter().filter(|l| *l != ".").cloned().collect();
        got.sort();
        assert_eq!(got, vec!["a", "b", "c"]); // nothing lost, nothing invented
        assert_eq!(v.ring.lines[0], "."); // and still well-formed
        assert!(v.undo.can_undo()); // undoable
    }

    // ── split the scratch into documents (Ctrl+Shift+F on 0.txt) ──────────────

    fn scratch_split_app(zero_lines: &[&str]) -> (tempfile::TempDir, Voider) {
        let d = tempfile::tempdir().unwrap();
        let i_dir = d.path().join("I");
        std::fs::create_dir_all(&i_dir).unwrap();
        let scratch = i_dir.join("0.txt");
        let lines: Vec<String> = zero_lines.iter().map(|s| s.to_string()).collect();
        void::atomic_write(&scratch, &lines, false).unwrap();
        let v = Voider::open(d.path(), &scratch);
        (d, v)
    }

    #[test]
    fn a_named_marker_creates_a_doc_and_leaves_the_scratch() {
        let (_d, mut v) = scratch_split_app(&[".", "one", "two", "/mydoc", ".", "stays here"]);
        v.split_scratch_into_docs().unwrap();

        let target = void::load_doc(&v.void_dir.join("I/mydoc.txt"));
        assert!(target.lines.contains(&"one".to_string()));
        assert!(target.lines.contains(&"two".to_string()));
        assert!(!v.ring.lines.contains(&"one".to_string()));
        assert!(!v.ring.lines.contains(&"two".to_string()));
        assert!(v.ring.lines.contains(&"stays here".to_string()));
    }

    #[test]
    fn the_marker_line_itself_never_lands_in_the_target() {
        let (_d, mut v) = scratch_split_app(&[".", "body", "/doc"]);
        v.split_scratch_into_docs().unwrap();
        let target = void::load_doc(&v.void_dir.join("I/doc.txt"));
        assert!(!target.lines.iter().any(|l| l.starts_with('/')));
    }

    #[test]
    fn splitting_into_an_existing_doc_appends() {
        let (_d, mut v) = scratch_split_app(&[".", "new line", "/existing"]);
        void::atomic_write(&v.void_dir.join("I/existing.txt"), &[".".to_string(), "old line".to_string()], false).unwrap();
        v.split_scratch_into_docs().unwrap();
        let out = void::load_doc(&v.void_dir.join("I/existing.txt"));
        assert!(out.lines.contains(&"old line".to_string())); // kept
        assert!(out.lines.contains(&"new line".to_string())); // and arrived
    }

    #[test]
    fn a_bare_slash_gets_an_auto_dated_name() {
        let (_d, mut v) = scratch_split_app(&[".", "orphan", "/"]);
        v.split_scratch_into_docs().unwrap();
        let now = chrono::Local::now();
        let base = format!("{}-{}-{}", now.year() % 100, now.month(), now.day());
        assert!(v.void_dir.join(format!("I/{base}_1.txt")).exists());
    }

    #[test]
    fn several_bare_slashes_get_sequential_names() {
        let (_d, mut v) = scratch_split_app(&[".", "a", "/", ".", "b", "/"]);
        v.split_scratch_into_docs().unwrap();
        let now = chrono::Local::now();
        let base = format!("{}-{}-{}", now.year() % 100, now.month(), now.day());
        assert!(v.void_dir.join(format!("I/{base}_1.txt")).exists());
        assert!(v.void_dir.join(format!("I/{base}_2.txt")).exists());
    }

    #[test]
    fn a_new_doc_lands_right_below_the_portal() {
        let (_d, mut v) = scratch_split_app(&[".", "x", "/fresh"]);
        v.library.entries = vec!["PROLOGUE.txt".into(), "0.txt".into(), "OTHER.txt".into()];
        v.split_scratch_into_docs().unwrap();
        assert_eq!(v.library.entries[2], "fresh.txt");
    }

    #[test]
    fn no_markers_still_formats_but_splits_nothing() {
        let (_d, mut v) = scratch_split_app(&[".", "just text", ".", "more"]);
        v.split_scratch_into_docs().unwrap();
        let mut names: Vec<String> = std::fs::read_dir(v.void_dir.join("I"))
            .unwrap()
            .map(|e| e.unwrap().file_name().to_string_lossy().to_string())
            .collect();
        names.sort();
        assert_eq!(names, vec!["0.txt", "0.txt.bak"]); // no new docs created
    }

    #[test]
    fn it_formats_into_sentences_even_without_markers() {
        let (_d, mut v) = scratch_split_app(&[".", "First sentence. Second sentence."]);
        v.split_scratch_into_docs().unwrap();
        assert!(v.ring.lines.contains(&"First sentence.".to_string()));
        assert!(v.ring.lines.contains(&"Second sentence.".to_string()));
    }

    #[test]
    fn splitting_writes_a_backup_of_the_original() {
        let (_d, mut v) = scratch_split_app(&[".", "body", "/doc", ".", "keep"]);
        v.split_scratch_into_docs().unwrap();
        assert!(v.void_dir.join("I/0.txt.bak").exists());
    }

    #[test]
    fn splitting_refuses_a_non_scratch_file() {
        let (_d, mut v) = book(); // active file is Uno.txt, not the scratch
        let before = v.ring.lines.clone();
        v.split_scratch_into_docs().unwrap();
        assert_eq!(v.ring.lines, before); // untouched
        assert!(!v.void_dir.join("I/doc.txt").exists());
    }

    #[test]
    fn a_marker_only_block_with_nothing_above_it_is_left_alone() {
        let (_d, mut v) = scratch_split_app(&[".", "/onlymarker", ".", "real content"]);
        v.split_scratch_into_docs().unwrap();
        assert!(!v.void_dir.join("I/onlymarker.txt").exists());
        assert!(v.ring.lines.iter().any(|l| l == "/onlymarker")); // left in place
    }

    #[test]
    fn a_split_is_one_undo_step_across_every_file_touched() {
        let (_d, mut v) = scratch_split_app(&[".", "one", "two", "/mydoc"]);
        let original = v.ring.lines.clone();
        v.split_scratch_into_docs().unwrap();
        assert!(v.void_dir.join("I/mydoc.txt").exists());

        v.undo().unwrap();
        assert_eq!(void::load_doc(&v.current_file).lines, original);
        assert!(!void::load_doc(&v.void_dir.join("I/mydoc.txt")).lines.contains(&"one".to_string()));
    }

    #[test]
    fn splitting_seals_chapters_and_lists_them() {
        let (_d, mut v) = book();
        v.ring.lines = vec![
            ".".into(), "texto uno".into(),
            "/Nuevo".into(),
            "texto dos".into(),
        ];
        assert_eq!(v.split_at_markers().unwrap(), 1);

        let sealed = void::load_doc(&library::chapter_path(&v.void_dir, "Nuevo.txt"));
        assert!(sealed.lines.contains(&"texto uno".to_string()));
        // what followed the marker stayed in the container
        assert!(v.ring.lines.contains(&"texto dos".to_string()));
        assert!(Library::load(&v.void_dir).entries.contains(&"Nuevo.txt".to_string()));
    }

    #[test]
    fn splitting_into_an_existing_name_appends_and_never_overwrites() {
        let (_d, mut v) = book(); // Dos.txt already holds 'de dos'
        v.ring.lines = vec![".".into(), "agregado".into(), "/Dos".into()];
        v.split_at_markers().unwrap();

        let dest = void::load_doc(&library::chapter_path(&v.void_dir, "Dos.txt"));
        assert!(dest.lines.contains(&"de dos".to_string())); // the old text survived
        assert!(dest.lines.contains(&"agregado".to_string())); // and the new arrived
    }

    #[test]
    fn an_emptied_container_leaves_the_library() {
        let (_d, mut v) = book(); // active is Uno.txt
        v.ring.lines = vec![".".into(), "todo".into(), "/Sellado".into()];
        v.split_at_markers().unwrap();
        let lib = Library::load(&v.void_dir);
        assert!(lib.entries.contains(&"Sellado.txt".to_string()));
        assert!(!lib.entries.contains(&"Uno.txt".to_string())); // emptied, so delisted
    }

    #[test]
    fn several_markers_seal_back_to_the_previous_one() {
        let (_d, mut v) = book();
        v.ring.lines = vec![
            "a".into(), "/Uno".into(), "b".into(), "/Dos".into(), "c".into(),
        ];
        assert_eq!(v.split_at_markers().unwrap(), 2);
        let uno = void::load_doc(&library::chapter_path(&v.void_dir, "Uno.txt"));
        let dos = void::load_doc(&library::chapter_path(&v.void_dir, "Dos.txt"));
        assert!(uno.lines.contains(&"a".to_string()));
        assert!(dos.lines.contains(&"b".to_string()));
        assert!(!dos.lines.contains(&"a".to_string())); // not everything from the top
    }

    #[test]
    fn a_split_is_one_undo_step() {
        let (_d, mut v) = book();
        // the state the split starts from, markers and all
        let before = vec![".".to_string(), "texto".into(), "/Nuevo".into(), "resto".into()];
        v.ring.lines = before.clone();
        v.split_at_markers().unwrap();
        assert!(library::chapter_path(&v.void_dir, "Nuevo.txt").exists());

        v.undo().unwrap();
        // the container came back whole, markers included
        assert_eq!(void::load_doc(&v.current_file).lines, before);
    }

    #[test]
    fn a_file_without_markers_is_left_alone() {
        let (_d, mut v) = book();
        let before = v.ring.lines.clone();
        assert_eq!(v.split_at_markers().unwrap(), 0);
        assert_eq!(v.ring.lines, before);
    }

    // ── merging a book (Ctrl+Shift+M on a dot in F3) ───────────────────────────

    fn merge_book_app() -> (tempfile::TempDir, Voider) {
        let d = tempfile::tempdir().unwrap();
        let i = d.path().join("I");
        std::fs::create_dir_all(&i).unwrap();
        std::fs::write(i.join("A.txt"), "a1\na2\n").unwrap();
        std::fs::write(i.join("B.txt"), "b1\n").unwrap();
        let mut v = Voider::open(d.path(), i.join("A.txt"));
        v.library = Library {
            entries: vec![".".into(), "A.txt".into(), "B.txt".into()],
            index: 0,
        };
        (d, v)
    }

    #[test]
    fn merge_prompt_only_fires_on_a_separator() {
        let (_d, mut v) = merge_book_app();
        v.library.index = 1; // on 'A.txt', not a dot
        v.book_merge_prompt();
        assert!(!v.pending_merge);
        assert_eq!(v.library.entries.len(), 3); // unchanged
    }

    #[test]
    fn merge_prompt_opens_a_blank_naming_line() {
        let (_d, mut v) = merge_book_app();
        v.book_merge_prompt();
        assert!(v.pending_merge);
        assert_eq!(v.library.entries, vec![".", "", "A.txt", "B.txt"]);
        assert_eq!(v.library.index, 1);
    }

    #[test]
    fn merge_collapses_the_book_into_one_sealed_chapter() {
        let (_d, mut v) = merge_book_app();
        v.book_merge_prompt();
        v.entry.set_text("Book1");
        let n = v.book_do_merge().unwrap();
        assert_eq!(n, 2);
        assert_eq!(v.library.entries, vec![".", "Book1.txt"]);

        let merged = void::load_doc(&v.void_dir.join("I/Book1.txt"));
        assert_eq!(merged.lines, vec![".", "a1", "a2", "/A", "b1", "/B"]);
        assert!(!v.void_dir.join("I/A.txt").exists());
        assert!(!v.void_dir.join("I/B.txt").exists());
        assert!(!v.pending_merge); // stays in F3, not opened
    }

    #[test]
    fn merging_then_splitting_restores_the_original_chapters() {
        let (_d, mut v) = merge_book_app();
        v.book_merge_prompt();
        v.entry.set_text("Book1");
        v.book_do_merge().unwrap();

        v.set_active_file(v.void_dir.join("I/Book1.txt"));
        v.split_at_markers().unwrap();

        let mut names: Vec<String> = v
            .library
            .entries
            .iter()
            .filter(|e| !library::is_separator(e))
            .cloned()
            .collect();
        names.sort();
        assert_eq!(names, vec!["A.txt", "B.txt"]);
        assert_eq!(void::load_doc(&v.void_dir.join("I/A.txt")).lines, vec![".", "a1", "a2"]);
        assert_eq!(void::load_doc(&v.void_dir.join("I/B.txt")).lines, vec![".", "b1"]);
        assert!(!v.void_dir.join("I/Book1.txt").exists());
    }

    #[test]
    fn an_empty_name_cancels_the_merge() {
        let (_d, mut v) = merge_book_app();
        v.book_merge_prompt();
        // entry left empty
        let n = v.book_do_merge().unwrap();
        assert_eq!(n, 0);
        assert_eq!(v.library.entries, vec![".", "A.txt", "B.txt"]); // naming line gone
        assert!(v.void_dir.join("I/A.txt").exists()); // untouched
        assert!(!v.pending_merge);
    }

    #[test]
    fn escape_cancels_a_pending_merge() {
        let (_d, mut v) = merge_book_app();
        v.book_merge_prompt();
        v.entry.set_text("Discarded");
        v.book_cancel_merge();
        assert!(!v.pending_merge);
        assert_eq!(v.library.entries, vec![".", "A.txt", "B.txt"]);
        assert!(v.void_dir.join("I/A.txt").exists());
    }

    #[test]
    fn a_name_clash_gets_a_numbered_suffix() {
        let (_d, mut v) = merge_book_app();
        std::fs::write(v.void_dir.join("I/Book1.txt"), "ya existe\n").unwrap();
        v.book_merge_prompt();
        v.entry.set_text("Book1");
        v.book_do_merge().unwrap();
        assert!(v.library.entries.contains(&"Book1-2.txt".to_string()));
        // the pre-existing Book1.txt was never touched by the merge
        assert_eq!(void::load_doc(&v.void_dir.join("I/Book1.txt")).lines, vec![".", "ya existe"]);
    }

    #[test]
    fn merging_is_one_undo_step_across_every_file() {
        let (_d, mut v) = merge_book_app();
        v.book_merge_prompt();
        v.entry.set_text("Book1");
        v.book_do_merge().unwrap();

        v.undo().unwrap();
        assert!(!v.void_dir.join("I/Book1.txt").exists());
        assert_eq!(void::load_doc(&v.void_dir.join("I/A.txt")).lines, vec![".", "a1", "a2"]);
        assert_eq!(void::load_doc(&v.void_dir.join("I/B.txt")).lines, vec![".", "b1"]);
    }

    // ── navigation ────────────────────────────────────────────────────────────

    #[test]
    fn page_down_and_up_walk_the_separators() {
        let (_d, mut v) = app(&[".", "a", ".", "b", ".", "c"]);
        v.ring.index = 1;
        v.goto_dot(1);
        assert_eq!(v.ring.index, 2);
        v.goto_dot(1);
        assert_eq!(v.ring.index, 4);
        v.goto_dot(1);
        assert_eq!(v.ring.index, 0); // wrapped
        v.goto_dot(-1);
        assert_eq!(v.ring.index, 4);
    }

    #[test]
    fn with_no_separators_at_all_the_cursor_stays_put() {
        // A loaded file always gains a leading '.', so build the ring directly.
        let (_d, mut v) = app(&[".", "a", "b"]);
        v.ring.lines = vec!["a".into(), "b".into()];
        v.ring.index = 1;
        v.goto_dot(1);
        assert_eq!(v.ring.index, 1); // nowhere to jump to
    }

    #[test]
    fn home_and_end_reach_the_first_and_last_text() {
        let (_d, mut v) = app(&[".", "primera", ".", "ultima"]);
        v.switch_to(View::F2);
        v.doc_jump_edge(true);
        assert_eq!(v.entry.text(), "ultima");
        assert_eq!(v.entry.caret(), 6); // End leaves the caret at the end
        v.doc_jump_edge(false);
        assert_eq!(v.entry.text(), "primera");
        assert_eq!(v.entry.caret(), 0);
    }

    #[test]
    fn rebasing_makes_the_current_line_first() {
        let (_d, mut v) = app(&[".", "a", ".", "b"]);
        v.ring.index = 3; // on 'b'
        v.switch_to(View::F2);
        v.rebase_to_current().unwrap();
        assert_eq!(v.ring.lines, vec!["b", ".", "a", "."]);
        assert_eq!(v.ring.index, 0);
        assert_eq!(void::load_doc(&v.current_file).lines[0], "."); // reloads well-formed
    }

    #[test]
    fn rebasing_at_the_top_changes_nothing() {
        let (_d, mut v) = app(&[".", "a"]);
        v.ring.index = 0;
        v.rebase_to_current().unwrap();
        assert_eq!(v.ring.lines, vec![".", "a"]);
    }

    #[test]
    fn stepping_files_walks_the_library_and_wraps() {
        let (_d, mut v) = book(); // Dos.txt, Uno.txt — active is Uno
        v.library = Library::load(&v.void_dir);
        v.step_file(1);
        assert!(v.current_file.ends_with("Dos.txt")); // wrapped past the end
        assert!(v.ring.lines.contains(&"de dos".to_string()));
        v.step_file(-1);
        assert!(v.current_file.ends_with("Uno.txt"));
    }

    #[test]
    fn stepping_files_skips_separators() {
        let (_d, mut v) = book();
        v.library = Library::load(&v.void_dir);
        v.library.entries.insert(1, ".".into()); // a separator between the two
        v.step_file(1);
        assert!(v.current_file.ends_with("Dos.txt")); // landed on a chapter, not a dot
    }

    // ── undo, end to end ──────────────────────────────────────────────────────

    #[test]
    fn a_committed_line_can_be_taken_back() {
        let (_d, mut v) = app(&[".", "vieja"]);
        v.ring.index = 1;
        v.entry.set_text("nueva");
        v.commit_line().unwrap();
        assert!(v.ring.lines.contains(&"nueva".to_string()));

        v.undo().unwrap();
        let on_disk = void::load_doc(&v.current_file);
        assert!(on_disk.lines.contains(&"vieja".to_string()));
        assert!(!on_disk.lines.contains(&"nueva".to_string()));
        assert!(v.ring.lines.contains(&"vieja".to_string())); // and on screen
    }

    #[test]
    fn undo_then_redo_returns_the_change() {
        let (_d, mut v) = app(&[".", "vieja"]);
        v.ring.index = 1;
        v.entry.set_text("nueva");
        v.commit_line().unwrap();
        v.undo().unwrap();
        v.redo().unwrap();
        assert!(void::load_doc(&v.current_file).lines.contains(&"nueva".to_string()));
    }

    #[test]
    fn a_burst_of_typing_undoes_as_one_step() {
        let (_d, mut v) = app(&[".", "h"]);
        v.ring.index = 1;
        v.switch_to(View::F2);
        for text in ["ho", "hol", "hola"] {
            v.entry.set_text(text);
            v.doc_live_save().unwrap();
        }
        assert_eq!(v.undo.undo_depth(), 1); // one step, not three
        v.undo().unwrap();
        assert!(void::load_doc(&v.current_file).lines.contains(&"h".to_string()));
    }

    #[test]
    fn undoing_a_sent_paragraph_puts_it_back_on_both_sides() {
        let (_d, mut v) = book();
        v.switch_to(View::F5);
        v.para_idx = 0; // 'de uno'
        v.send_para_to("Dos.txt").unwrap();

        v.undo().unwrap();
        let src = void::load_doc(&v.current_file);
        let dst = void::load_doc(&library::chapter_path(&v.void_dir, "Dos.txt"));
        assert!(src.lines.contains(&"de uno".to_string())); // back home
        assert!(!dst.lines.contains(&"de uno".to_string())); // and gone from there
    }

    #[test]
    fn undoing_with_nothing_recorded_is_harmless() {
        let (_d, mut v) = app(&[".", "intacta"]);
        v.undo().unwrap();
        assert!(void::load_doc(&v.current_file).lines.contains(&"intacta".to_string()));
        assert_eq!(v.status, "Nothing to undo");
    }

    #[test]
    fn a_moved_line_can_be_taken_back() {
        let (_d, mut v) = app(&[".", "a", "b"]);
        v.ring.index = 1;
        v.switch_to(View::F2);
        v.doc_swap_line(1).unwrap();
        v.undo().unwrap();
        assert_eq!(void::load_doc(&v.current_file).lines, vec![".", "a", "b"]);
    }

    // ── paragraph focus (Enter on a dot in F2) ─────────────────────────────────

    #[test]
    fn entering_focus_on_the_first_dot_sets_its_content() {
        let (_d, mut v) = app(&[".", "a", "b", ".", "c"]);
        v.ring.index = 0;
        v.enter_para_focus();
        assert!(v.para_focus);
        let mut got = v.para_focus_content.clone();
        got.sort();
        assert_eq!(got, vec![1, 2]);
    }

    #[test]
    fn entering_focus_on_the_second_dot() {
        let (_d, mut v) = app(&[".", "a", "b", ".", "c"]);
        v.ring.index = 3;
        v.enter_para_focus();
        assert_eq!(v.para_focus_content, vec![4]);
    }

    #[test]
    fn an_empty_paragraph_does_not_enter_focus() {
        let (_d, mut v) = app(&[".", ".", "a"]);
        v.ring.index = 0; // the first dot has nothing after it before the next
        v.enter_para_focus();
        assert!(!v.para_focus);
    }

    #[test]
    fn exiting_focus_clears_state_and_returns_to_the_dot() {
        let (_d, mut v) = app(&[".", "a", "b"]);
        v.ring.index = 0;
        v.enter_para_focus();
        v.ring.index = 2;
        v.exit_para_focus();
        assert!(!v.para_focus);
        assert!(v.para_focus_content.is_empty());
        assert_eq!(v.ring.lines[v.ring.index], ".");
    }

    #[test]
    fn swap_in_focus_wraps_within_the_paragraph_only() {
        let (_d, mut v) = app(&[".", "a", "b", "c", ".", "x"]);
        v.ring.index = 0;
        v.enter_para_focus();
        v.ring.index = 1; // 'a'
        v.swap_line_in_focus(-1).unwrap(); // wraps to the paragraph's last line
        assert_eq!(v.ring.lines[v.ring.index], "a");
        assert_eq!(v.ring.lines[1], "c");
        assert_eq!(v.ring.lines[5], "x"); // outside the paragraph, untouched
    }

    #[test]
    fn navigation_stays_inside_the_focused_paragraph() {
        let (_d, mut v) = app(&[".", "a", "b", ".", "c"]);
        v.switch_to(View::F2);
        v.ring.index = 0;
        v.enter_para_focus(); // content = [1, 2]
        v.ring.index = 1;
        v.doc_navigate(1).unwrap();
        assert_eq!(v.ring.index, 2);
        v.doc_navigate(1).unwrap(); // wraps within the paragraph
        assert_eq!(v.ring.index, 1);
        assert_ne!(v.ring.index, 3); // never spills into the next paragraph
    }

    #[test]
    fn enter_on_a_dot_enters_focus_via_confirm_edit() {
        let (_d, mut v) = app(&[".", "a", "b"]);
        v.ring.index = 0;
        v.doc_confirm_edit().unwrap();
        assert!(v.para_focus);
    }

    #[test]
    fn enter_again_while_focused_exits() {
        let (_d, mut v) = app(&[".", "a", "b"]);
        v.ring.index = 0;
        v.doc_confirm_edit().unwrap(); // enters
        v.doc_confirm_edit().unwrap(); // exits
        assert!(!v.para_focus);
    }

    #[test]
    fn splitting_a_line_inside_focus_keeps_it_in_the_paragraph() {
        let (_d, mut v) = app(&[".", "hola mundo", "b"]);
        v.ring.index = 0;
        v.enter_para_focus(); // content = [1, 2]
        v.ring.index = 1;
        v.entry.set_text("hola mundo");
        v.entry.set_caret(4); // split "hola" | " mundo"
        v.doc_split_line().unwrap();
        assert_eq!(v.ring.lines, vec![".", "hola", " mundo", "b"]);
        // the new line joined the focused paragraph, and the old member shifted
        let mut got = v.para_focus_content.clone();
        got.sort();
        assert_eq!(got, vec![1, 2, 3]);
    }

    // ── the trash cascade (Ctrl+Delete / Ctrl+Backspace in F2) ────────────────

    /// A Voider whose active file is exactly the scratch, `I/0.txt`. `lines` is
    /// set on the ring directly (bypassing load_doc's leading-dot guarantee) so
    /// the test's own indices land where it expects, as the Python tests do by
    /// building the ring by hand too.
    fn scratch_app(lines: &[&str]) -> (tempfile::TempDir, Voider) {
        let d = tempfile::tempdir().unwrap();
        let f = d.path().join("I/0.txt");
        void::atomic_write(&f, &[".".to_string()], false).unwrap();
        let mut v = Voider::open(d.path(), &f);
        v.ring = LineRing::new(lines.iter().map(|s| s.to_string()));
        (d, v)
    }

    fn trash_app(lines: &[&str]) -> (tempfile::TempDir, Voider) {
        let d = tempfile::tempdir().unwrap();
        let f = d.path().join("I/trash.txt");
        void::atomic_write(&f, &[".".to_string()], false).unwrap();
        let mut v = Voider::open(d.path(), &f);
        v.ring = LineRing::new(lines.iter().map(|s| s.to_string()));
        (d, v)
    }

    #[test]
    fn delete_from_another_file_goes_to_the_scratch() {
        let (_d, mut v) = app(&["From book.", ".", "Stay."]);
        v.ring = LineRing::new(["From book.", ".", "Stay."]);
        v.ring.index = 0;
        v.delete_line_to_zero().unwrap();
        let scratch = void::load_doc(&v.scratch_path());
        assert!(scratch.lines.contains(&"From book.".to_string()));
    }

    #[test]
    fn deleting_removes_the_line_from_the_ring() {
        let (_d, mut v) = app(&["Hello world.", ".", "Keep this."]);
        v.ring = LineRing::new(["Hello world.", ".", "Keep this."]);
        v.ring.index = 0;
        v.delete_line_to_zero().unwrap();
        assert!(!v.ring.lines.contains(&"Hello world.".to_string()));
    }

    #[test]
    fn delete_from_the_scratch_goes_to_trash() {
        let (_d, mut v) = scratch_app(&["Hello world.", ".", "Keep this."]);
        v.ring.index = 0; // 'Hello world.'
        v.delete_line_to_zero().unwrap();
        let trash = void::load_doc(&v.trash_path());
        assert!(trash.lines.contains(&"Hello world.".to_string()));
        assert!(!v.ring.lines.contains(&"Hello world.".to_string()));
    }

    #[test]
    fn a_dot_deleted_from_the_scratch_goes_to_trash_too() {
        let (_d, mut v) = scratch_app(&[".", "Line."]);
        v.ring.index = 0; // the dot itself
        v.delete_line_to_zero().unwrap();
        let trash = void::load_doc(&v.trash_path());
        assert!(trash.lines.iter().any(|l| l == "."));
    }

    #[test]
    fn delete_from_trash_is_permanent() {
        let (_d, mut v) = trash_app(&["Trashed line.", ".", "Another."]);
        v.ring.index = 0;
        v.delete_line_to_zero().unwrap();

        assert!(!v.ring.lines.contains(&"Trashed line.".to_string()));
        // gone from the file on disk too, and never duplicated back into it
        let on_disk = void::load_doc(&v.trash_path());
        assert!(!on_disk.lines.contains(&"Trashed line.".to_string()));
    }

    #[test]
    fn deleting_down_to_one_line_is_a_noop_guard() {
        let (_d, mut v) = app(&["sola"]);
        v.ring = LineRing::new(["sola"]);
        v.delete_line_to_zero().unwrap();
        assert_eq!(v.ring.lines, vec!["sola"]); // never empties the file
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

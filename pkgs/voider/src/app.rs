use std::path::PathBuf;

use smithay_client_toolkit::{
    compositor::{CompositorHandler, CompositorState},
    delegate_compositor, delegate_keyboard, delegate_layer, delegate_output,
    delegate_registry, delegate_seat, delegate_shm,
    output::{OutputHandler, OutputState},
    registry::{ProvidesRegistryState, RegistryState},
    registry_handlers,
    seat::{Capability, SeatHandler, SeatState},
    seat::keyboard::{KeyboardHandler, KeyEvent, Modifiers, RepeatInfo},
    shell::{
        WaylandSurface,
        wlr_layer::{
            Anchor, KeyboardInteractivity, Layer, LayerShell, LayerShellHandler,
            LayerSurface, LayerSurfaceConfigure,
        },
    },
    shm::{Shm, ShmHandler, slot::SlotPool},
};
use wayland_client::{
    globals::GlobalList,
    protocol::{wl_keyboard, wl_output, wl_seat, wl_shm, wl_surface},
    Connection, QueueHandle,
};

use std::io::Write as IoWrite;

use crate::{
    config::Config,
    files::{
        append_line, load_book_order, load_vault_lines,
        read_file, save_book_order, save_file, FileIndex,
    },
    input::{self, Action, View},
    render::{self, GlyphCache},
    ring::LineRing,
    text::{parse_line, LineAction},
};

fn random_pick<'a>(items: &'a [String]) -> &'a str {
    if items.is_empty() { return ""; }
    let mut seed = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_nanos() as u64)
        .unwrap_or(0xcafebabe);
    seed ^= seed << 13; seed ^= seed >> 7; seed ^= seed << 17;
    &items[(seed as usize) % items.len()]
}

// ── F2 mode ───────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum F2Mode { Normal, Editing, Inserting }

// ── UI state ──────────────────────────────────────────────────────────────────

pub struct UiState {
    pub config: Config,
    pub view:   View,

    // Active file content — shared ring across all views
    pub ring: LineRing,

    // File/directory state
    pub active_file:  PathBuf,
    pub void_dir:     PathBuf,
    pub book_dir:     PathBuf,
    pub txt_files:    Vec<PathBuf>,  // top-level .txt for Alt+Up/Down in F1
    pub txt_file_idx: usize,
    pub file_index:   FileIndex,

    // F1 state
    pub input:                String,
    pub ring_nav_idx:         Option<usize>,
    pub first_up_after_submit: bool,
    pub last_inserted_idx:    Option<usize>,

    // F2 state
    pub f2_mode:       F2Mode,
    pub f2_editor:     String,   // inline editor text
    pub f2_cursor:     usize,    // cursor position in editor
    pub f2_offset:     f32,      // animation offset in lines
    pub f2_anim_tick:  u64,
    pub f2_anim_delta: isize,    // pending ring.move_by() after animation

    // F3 state (book browser)
    pub book_ring:  LineRing,
    pub book_files: Vec<PathBuf>,

    // F4 state (vault browser)
    pub vault_ring: LineRing,

    // Global
    pub blink_tick:      u64,
    pub opacity:         f32,
    pub show_overlay:    bool,
}

const ANIM_FRAMES: u64 = 11; // ~180ms at 60fps

impl UiState {
    pub fn tick_animation(&mut self) {
        if self.f2_anim_delta == 0 { return; }
        let elapsed = self.blink_tick.saturating_sub(self.f2_anim_tick);
        if elapsed >= ANIM_FRAMES {
            self.ring.move_by(self.f2_anim_delta);
            self.f2_anim_delta = 0;
            self.f2_offset = 0.0;
        } else {
            let t = elapsed as f32 / ANIM_FRAMES as f32;
            let eased = 1.0 - (1.0 - t).powi(2); // OutQuad
            self.f2_offset = -(self.f2_anim_delta as f32) * eased;
        }
    }

    fn start_anim(&mut self, delta: isize) {
        if self.f2_anim_delta != 0 { return; } // busy
        self.f2_anim_delta = delta;
        self.f2_anim_tick  = self.blink_tick;
        self.f2_offset     = 0.0;
    }

    pub fn apply(&mut self, action: Action) {
        // Global opacity handled first before view dispatch
        match &action {
            Action::OpacityUp   => { self.opacity = (self.opacity + 0.1).min(1.0); return; }
            Action::OpacityDown => { self.opacity = (self.opacity - 0.1).max(0.0); return; }
            _ => {}
        }
        match self.view {
            View::Write => self.handle_write(action),
            View::Doc   => self.handle_doc(action),
            View::Book  => self.handle_book(action),
            View::Vault => self.handle_vault(action),
        }
    }

    // ── F1: Write ─────────────────────────────────────────────────────────────

    fn handle_write(&mut self, action: Action) {
        match action {
            Action::SwitchView(v) => {
                self.ring_nav_idx = None;
                // Sync ring to active file before switching
                if v == View::Doc || v == View::Book || v == View::Vault {
                    self.reload_ring();
                }
                if v == View::Book  { self.reload_book(); }
                if v == View::Vault { self.reload_vault(); }
                self.view = v;
            }

            Action::Char(c) => { self.input.push(c); }

            Action::Backspace => {
                if self.input.is_empty() {
                    self.ring_nav_idx = None;
                } else {
                    self.input.pop();
                }
            }

            Action::Escape => {
                self.ring_nav_idx = None;
                self.input.clear();
            }

            Action::Enter => self.f1_submit(),

            // Up: navigate backwards through ring lines
            Action::NavUp => {
                let n = self.ring.len();
                if n == 0 { return; }
                let new_idx = match self.ring_nav_idx {
                    None    => self.ring.index,
                    Some(i) => (i + n - 1) % n,
                };
                // Skip dots
                let mut idx = new_idx;
                for _ in 0..n {
                    if self.ring.lines()[idx].trim() != "." { break; }
                    idx = (idx + n - 1) % n;
                }
                self.ring_nav_idx = Some(idx);
                self.input = self.ring.lines()[idx].clone();
                self.first_up_after_submit = false;
            }

            // Down: navigate forwards; past current index → exit nav
            Action::NavDown => {
                if let Some(i) = self.ring_nav_idx {
                    let n = self.ring.len();
                    let next = (i + 1) % n;
                    if next == self.ring.index {
                        self.ring_nav_idx = None;
                        self.input.clear();
                    } else {
                        // Skip dots
                        let mut idx = next;
                        for _ in 0..n {
                            if self.ring.lines()[idx].trim() != "." { break; }
                            idx = (idx + 1) % n;
                        }
                        self.ring_nav_idx = Some(idx);
                        self.input = self.ring.lines()[idx].clone();
                    }
                }
            }

            // Alt+Up/Down: switch between .txt files in vault
            Action::AltUp => {
                let n = self.txt_files.len();
                if n == 0 { return; }
                self.txt_file_idx = (self.txt_file_idx + n - 1) % n;
                self.load_file(self.txt_files[self.txt_file_idx].clone());
            }
            Action::AltDown => {
                let n = self.txt_files.len();
                if n == 0 { return; }
                self.txt_file_idx = (self.txt_file_idx + 1) % n;
                self.load_file(self.txt_files[self.txt_file_idx].clone());
            }

            // PageUp/Down: jump to previous/next paragraph dot
            Action::PageUp => {
                let idx = self.ring.prev_dot_idx();
                self.ring.index = idx;
                if !self.ring.is_empty() {
                    let line = if self.ring.is_dot() { String::new() } else { self.ring.current().to_owned() };
                    self.input = line;
                }
            }
            Action::PageDown => {
                let idx = self.ring.next_dot_idx();
                self.ring.index = idx;
                if !self.ring.is_empty() {
                    let line = if self.ring.is_dot() { String::new() } else { self.ring.current().to_owned() };
                    self.input = line;
                }
            }

            // Ctrl+. — random line from current file
            Action::RandomSelf => {
                let current = self.ring.current().to_owned();
                let candidates: Vec<String> = self.ring.lines().iter()
                    .filter(|l| l.trim() != "." && !l.is_empty() && **l != current)
                    .cloned().collect();
                if !candidates.is_empty() {
                    self.input = random_pick(&candidates).to_owned();
                } else if !self.ring.is_empty() {
                    self.input = self.ring.current().to_owned();
                }
            }

            // Ctrl+0 (in F1) — random line from any other file
            Action::RandomOther => {
                let candidates = self.collect_other_file_lines(false);
                if !candidates.is_empty() {
                    self.input = random_pick(&candidates).to_owned();
                }
            }

            // * — recycle: random line from any file except active (cut-up)
            Action::Recycle => {
                let candidates = self.collect_other_file_lines(true);
                if !candidates.is_empty() {
                    self.input = random_pick(&candidates).to_owned();
                }
            }

            Action::Tab | Action::ToggleOverlay => {
                self.show_overlay = !self.show_overlay;
            }

            _ => {}
        }
    }

    fn f1_submit(&mut self) {
        let raw = std::mem::take(&mut self.input);
        self.ring_nav_idx = None;

        match parse_line(&raw) {
            LineAction::Empty => {
                self.last_inserted_idx = Some(self.ring.len().saturating_sub(1));
            }

            LineAction::Separator => {
                // Prevent consecutive dots
                if self.ring.len() > 0 && self.ring.current().trim() == "." {
                    return;
                }
                self.ring.push(".".to_string());
                let _ = append_line(&self.active_file, ".");
                self.last_inserted_idx = Some(self.ring.index);
            }

            LineAction::Insert(sentences) => {
                for sentence in sentences {
                    self.ring.push(sentence.clone());
                    let _ = append_line(&self.active_file, &sentence);
                }
                self.last_inserted_idx = Some(self.ring.index);
                self.first_up_after_submit = true;
            }

            LineAction::SwitchFile(name) => {
                let path = self.void_dir.join(&name);
                if !path.exists() { let _ = std::fs::write(&path, ""); }
                self.load_file(path.clone());
                // Refresh txt_files list
                self.refresh_txt_files();
                if let Some(i) = self.txt_files.iter().position(|p| p == &path) {
                    self.txt_file_idx = i;
                }
            }

            LineAction::MoveBlock(fname) => {
                let dest = self.void_dir.join(&fname);
                if !dest.exists() { let _ = std::fs::write(&dest, ""); }
                // Find current paragraph boundaries
                let idx = self.ring.index;
                let n   = self.ring.len();
                // Walk back to find start of paragraph (last dot or index 0)
                let mut start = idx;
                for step in 1..=n {
                    let i = (idx + n - step) % n;
                    if self.ring.lines()[i].trim() == "." {
                        start = (i + 1) % n;
                        break;
                    }
                    if step == n { start = 0; }
                }
                // Collect paragraph lines
                let mut block: Vec<String> = Vec::new();
                let mut i = start;
                loop {
                    let line = &self.ring.lines()[i];
                    if line.trim() == "." && i != start { break; }
                    block.push(line.clone());
                    i = (i + 1) % n;
                    if i == start { break; }
                }
                // Append block to destination
                if let Ok(mut f) = std::fs::OpenOptions::new().append(true).create(true).open(&dest) {
                    let _ = writeln!(f, ".");
                    for l in &block { let _ = writeln!(f, "{l}"); }
                }
                // Remove from source ring and file
                let mut new_lines = self.ring.lines().to_vec();
                let remove_start = if start > 0 && new_lines[(start + n - 1) % n].trim() == "." {
                    (start + n - 1) % n
                } else { start };
                let remove_end = i;
                // Simple approach: rebuild without removed range
                new_lines.retain(|_| true); // can't filter by index easily, rebuild
                let mut rebuilt: Vec<String> = Vec::new();
                let mut k = 0usize;
                let total = new_lines.len();
                while k < total {
                    let in_block = if remove_end >= remove_start {
                        k >= remove_start && k < remove_end
                    } else {
                        k >= remove_start || k < remove_end
                    };
                    if !in_block { rebuilt.push(new_lines[k].clone()); }
                    k += 1;
                }
                self.ring = LineRing::from_lines(rebuilt.clone());
                let _ = save_file(&self.active_file, &rebuilt);
                self.last_inserted_idx = None;
            }

            LineAction::MoveLine(content, fname) => {
                let dest = self.void_dir.join(&fname);
                if !dest.exists() { let _ = std::fs::write(&dest, ""); }
                let _ = append_line(&dest, &content);
                // Remove from current ring if editing an existing line
                if let Some(idx) = self.ring_nav_idx {
                    let remove_idx = idx.min(self.ring.len().saturating_sub(1));
                    self.ring.lines_mut().remove(remove_idx);
                    let _ = save_file(&self.active_file, self.ring.lines());
                }
                self.last_inserted_idx = None;
            }
        }
    }

    // ── F2: Doc ring ──────────────────────────────────────────────────────────

    fn handle_doc(&mut self, action: Action) {
        match self.f2_mode {
            F2Mode::Normal => self.handle_doc_normal(action),
            F2Mode::Editing | F2Mode::Inserting => self.handle_doc_editor(action),
        }
    }

    fn handle_doc_normal(&mut self, action: Action) {
        match action {
            Action::SwitchView(v) => {
                self.auto_save();
                if v == View::Book  { self.reload_book(); }
                if v == View::Vault { self.reload_vault(); }
                self.view = v;
            }
            Action::Escape => {
                self.auto_save();
                self.view = View::Write;
                self.input = if self.ring.is_dot() {
                    String::new()
                } else {
                    self.ring.current().to_owned()
                };
            }

            Action::NavUp   => { if self.f2_anim_delta == 0 { self.start_anim(-1); } }
            Action::NavDown => { if self.f2_anim_delta == 0 { self.start_anim( 1); } }

            // Alt+Up/Down: on a dot, swap whole paragraphs; on text, swap lines
            Action::AltUp => {
                if self.ring.is_dot() {
                    self.swap_paragraphs(-1);
                } else {
                    self.ring.swap_with(-1);
                }
                self.auto_save();
            }
            Action::AltDown => {
                if self.ring.is_dot() {
                    self.swap_paragraphs(1);
                } else {
                    self.ring.swap_with(1);
                }
                self.auto_save();
            }

            Action::PageUp   => { let i = self.ring.prev_dot_idx(); self.ring.index = i; }
            Action::PageDown => { let i = self.ring.next_dot_idx(); self.ring.index = i; }

            // Enter → insert new line below
            Action::Enter => {
                self.f2_editor = String::new();
                self.f2_cursor = 0;
                self.f2_mode   = F2Mode::Inserting;
            }

            // Shift+Enter → edit current line
            Action::ShiftEnter => {
                self.enter_f2_edit();
            }

            // Typing a character in Normal mode → enter edit mode with that char
            Action::Char(c) => {
                self.f2_editor = self.ring.current().to_owned();
                self.f2_cursor = self.f2_editor.len();
                self.f2_editor.push(c);
                self.f2_cursor += c.len_utf8();
                self.f2_mode = F2Mode::Editing;
            }

            // Ctrl+0 in F2 = Rebase (RandomOther action is remapped here)
            Action::Rebase | Action::RandomOther => { self.ring.rebase(); self.auto_save(); }

            Action::Reformat => self.reformat_file(),

            Action::Tab | Action::ToggleOverlay => { self.show_overlay = !self.show_overlay; }

            _ => {}
        }
    }

    fn handle_doc_editor(&mut self, action: Action) {
        match action {
            Action::Char(c) => {
                self.f2_editor.insert(self.f2_cursor, c);
                self.f2_cursor += c.len_utf8();
                // Live save in edit mode
                if self.f2_mode == F2Mode::Editing {
                    self.ring.replace_current(self.f2_editor.clone());
                    self.auto_save();
                }
            }
            Action::Backspace => {
                if self.f2_cursor > 0 {
                    // Find previous char boundary
                    let mut i = self.f2_cursor - 1;
                    while i > 0 && !self.f2_editor.is_char_boundary(i) { i -= 1; }
                    self.f2_editor.remove(i);
                    self.f2_cursor = i;
                    if self.f2_mode == F2Mode::Editing {
                        self.ring.replace_current(self.f2_editor.clone());
                        self.auto_save();
                    }
                } else if self.f2_mode == F2Mode::Editing {
                    // Backspace at start: join with previous
                    let new_cursor = self.ring.join_prev();
                    if let Some(pos) = new_cursor {
                        self.f2_editor = self.ring.current().to_owned();
                        self.f2_cursor = pos;
                        self.auto_save();
                    }
                }
            }
            Action::Delete => {
                if self.f2_cursor < self.f2_editor.len() {
                    let mut end = self.f2_cursor + 1;
                    while end < self.f2_editor.len() && !self.f2_editor.is_char_boundary(end) { end += 1; }
                    self.f2_editor.drain(self.f2_cursor..end);
                    if self.f2_mode == F2Mode::Editing {
                        self.ring.replace_current(self.f2_editor.clone());
                        self.auto_save();
                    }
                } else if self.f2_mode == F2Mode::Editing {
                    // Delete at end: join with next
                    let new_cursor = self.ring.join_next();
                    if let Some(pos) = new_cursor {
                        self.f2_editor = self.ring.current().to_owned();
                        self.f2_cursor = pos;
                        self.auto_save();
                    }
                }
            }
            Action::CursorLeft => {
                if self.f2_cursor > 0 {
                    let mut i = self.f2_cursor - 1;
                    while i > 0 && !self.f2_editor.is_char_boundary(i) { i -= 1; }
                    self.f2_cursor = i;
                }
            }
            Action::CursorRight => {
                if self.f2_cursor < self.f2_editor.len() {
                    let mut i = self.f2_cursor + 1;
                    while i < self.f2_editor.len() && !self.f2_editor.is_char_boundary(i) { i += 1; }
                    self.f2_cursor = i;
                }
            }
            Action::Enter => {
                if self.f2_cursor == 0 && self.f2_mode == F2Mode::Editing {
                    // Enter at start: switch to insert mode below current
                    self.ring.replace_current(self.f2_editor.clone());
                    self.auto_save();
                    self.f2_editor.clear();
                    self.f2_cursor = 0;
                    self.f2_mode = F2Mode::Inserting;
                } else if self.f2_cursor > 0 && self.f2_mode == F2Mode::Editing {
                    // Split at cursor
                    let pos = self.f2_cursor;
                    self.ring.replace_current(self.f2_editor.clone());
                    self.ring.split_at(pos);
                    self.auto_save();
                    self.f2_editor = self.ring.current().to_owned();
                    self.f2_cursor = 0;
                } else {
                    // Inserting mode: commit new line
                    let text = std::mem::take(&mut self.f2_editor);
                    self.f2_cursor = 0;
                    self.f2_mode   = F2Mode::Normal;
                    if !text.is_empty() {
                        self.ring.insert_after(text);
                        self.auto_save();
                    }
                }
            }
            Action::Escape => {
                // Discard, exit edit mode
                if self.f2_mode == F2Mode::Editing {
                    // Restore from ring
                    self.f2_editor = self.ring.current().to_owned();
                }
                self.f2_editor.clear();
                self.f2_cursor = 0;
                self.f2_mode   = F2Mode::Normal;
            }
            Action::NavUp => {
                // Commit edit, navigate
                if self.f2_mode == F2Mode::Editing {
                    self.ring.replace_current(self.f2_editor.clone());
                    self.auto_save();
                }
                self.f2_mode = F2Mode::Normal;
                self.f2_editor.clear();
                self.f2_cursor = 0;
                if self.f2_anim_delta == 0 { self.start_anim(-1); }
            }
            Action::NavDown => {
                if self.f2_mode == F2Mode::Editing {
                    self.ring.replace_current(self.f2_editor.clone());
                    self.auto_save();
                }
                self.f2_mode = F2Mode::Normal;
                self.f2_editor.clear();
                self.f2_cursor = 0;
                if self.f2_anim_delta == 0 { self.start_anim(1); }
            }
            Action::SwitchView(v) => {
                self.f2_mode = F2Mode::Normal;
                self.f2_editor.clear();
                self.f2_cursor = 0;
                self.auto_save();
                if v == View::Book  { self.reload_book(); }
                if v == View::Vault { self.reload_vault(); }
                self.view = v;
            }
            _ => {}
        }
    }

    // ── F3: Book browser ──────────────────────────────────────────────────────

    fn handle_book(&mut self, action: Action) {
        let n = self.book_ring.len();
        match action {
            Action::SwitchView(v) => {
                if v == View::Vault { self.reload_vault(); }
                self.view = v;
            }
            Action::Escape => { self.view = View::Write; }

            Action::NavUp   => { if n > 0 { self.book_ring.move_by(-1); } }
            Action::NavDown => { if n > 0 { self.book_ring.move_by( 1); } }

            Action::AltUp => {
                if n >= 2 {
                    self.book_ring.swap_with(-1);
                    let i = self.book_ring.index;
                    if i + 1 < self.book_files.len() {
                        self.book_files.swap(i, i + 1);
                    }
                    let _ = save_book_order(&self.book_dir, &self.book_files);
                }
            }
            Action::AltDown => {
                if n >= 2 {
                    self.book_ring.swap_with(1);
                    let i = self.book_ring.index;
                    if i > 0 {
                        self.book_files.swap(i, i - 1);
                    }
                    let _ = save_book_order(&self.book_dir, &self.book_files);
                }
            }

            Action::Rebase | Action::RandomOther => {
                self.book_ring.rebase();
                let i = self.book_ring.index;
                if i > 0 && i < self.book_files.len() {
                    self.book_files.rotate_left(i);
                }
                let _ = save_book_order(&self.book_dir, &self.book_files);
            }

            Action::Enter => {
                // Load selected chapter into active file, switch to F2
                let idx = self.book_ring.index;
                if idx < self.book_files.len() {
                    let path = self.book_files[idx].clone();
                    self.load_file(path);
                    self.view = View::Doc;
                    self.f2_mode   = F2Mode::Normal;
                    self.f2_editor.clear();
                    self.f2_cursor = 0;
                }
            }

            _ => {}
        }
    }

    // ── F4: Vault ─────────────────────────────────────────────────────────────

    fn handle_vault(&mut self, action: Action) {
        let n = self.vault_ring.len();
        match action {
            Action::SwitchView(v) => {
                if v == View::Book { self.reload_book(); }
                self.view = v;
            }
            Action::Escape => { self.view = View::Write; }

            Action::NavUp   => { if n > 0 { self.vault_ring.move_by(-1); } }
            Action::NavDown => { if n > 0 { self.vault_ring.move_by( 1); } }

            Action::Reshuffle => { self.reload_vault(); }

            Action::Enter => {
                // Insert vault line into active file
                if n > 0 {
                    let line = self.vault_ring.current().to_owned();
                    self.ring.push(line.clone());
                    let _ = append_line(&self.active_file, &line);
                    self.vault_ring.remove_current();
                }
            }

            _ => {}
        }
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    fn load_file(&mut self, path: PathBuf) {
        self.active_file = path;
        self.reload_ring();
        self.ring_nav_idx = None;
        self.last_inserted_idx = None;
        self.input.clear();
    }

    fn reload_ring(&mut self) {
        let lines = read_file(&self.active_file);
        let idx   = self.ring.index.min(lines.len().saturating_sub(1));
        self.ring = LineRing::from_lines(lines);
        self.ring.index = idx;
    }

    pub fn reload_book(&mut self) {
        self.book_files = load_book_order(&self.book_dir);
        let names: Vec<String> = self.book_files.iter()
            .map(|p| p.file_stem().unwrap_or_default().to_string_lossy().into_owned())
            .collect();
        self.book_ring = if names.is_empty() {
            LineRing::from_lines(vec!["(empty)".to_string()])
        } else {
            LineRing::from_lines(names)
        };
    }

    pub fn reload_vault(&mut self) {
        let lines = load_vault_lines(&self.void_dir);
        self.vault_ring = if lines.is_empty() {
            LineRing::from_lines(vec!["(vault empty)".to_string()])
        } else {
            LineRing::from_lines(lines)
        };
    }

    // ── Random helpers ────────────────────────────────────────────────────────

    fn collect_other_file_lines(&self, exclude_active: bool) -> Vec<String> {
        let mut out = Vec::new();
        let Ok(entries) = std::fs::read_dir(&self.void_dir) else { return out; };
        for entry in entries.flatten() {
            let path = entry.path();
            if !path.is_file() { continue; }
            if path.extension().map(|e| e != "txt").unwrap_or(true) { continue; }
            let name = path.file_name().unwrap_or_default().to_string_lossy().to_lowercase();
            if !exclude_active && name == "0.txt" { continue; }
            if exclude_active && path == self.active_file { continue; }
            if let Ok(content) = std::fs::read_to_string(&path) {
                for line in content.lines() {
                    let s = line.trim();
                    if !s.is_empty() && s != "." { out.push(s.to_string()); }
                }
            }
        }
        out
    }

    fn swap_paragraphs(&mut self, direction: isize) {

        let n = self.ring.len();
        let lines = self.ring.lines().to_vec();
        let mut paras: Vec<(usize, Vec<usize>)> = Vec::new();
        let mut i = 0;
        while i < n {
            if lines[i].trim() == "." {
                let dot_i = i;
                let mut content = Vec::new();
                i += 1;
                while i < n && lines[i].trim() != "." { content.push(i); i += 1; }
                paras.push((dot_i, content));
            } else { i += 1; }
        }
        if paras.len() < 2 { return; }
        let cur = self.ring.index;
        let Some(pi) = paras.iter().position(|(di, _)| *di == cur) else { return; };
        let target_pi = ((pi as isize + direction).rem_euclid(paras.len() as isize)) as usize;
        if pi == target_pi { return; }
        // Build blocks and swap in-place
        let (di_a, ref ca) = paras[pi];
        let (di_b, ref cb) = paras[target_pi];
        let block_a: Vec<String> = std::iter::once(lines[di_a].clone())
            .chain(ca.iter().map(|&idx| lines[idx].clone())).collect();
        let block_b: Vec<String> = std::iter::once(lines[di_b].clone())
            .chain(cb.iter().map(|&idx| lines[idx].clone())).collect();
        let mut new_lines = lines;
        let (start_a, start_b) = (di_a, di_b);
        for (k, l) in block_b.iter().enumerate() { if start_a + k < n { new_lines[start_a + k] = l.clone(); } }
        for (k, l) in block_a.iter().enumerate() { if start_b + k < n { new_lines[start_b + k] = l.clone(); } }
        self.ring = LineRing::from_lines(new_lines);
        self.ring.index = start_b;
    }

    fn refresh_txt_files(&mut self) {
        let mut files: Vec<PathBuf> = std::fs::read_dir(&self.void_dir)
            .into_iter().flatten().flatten()
            .map(|e| e.path())
            .filter(|p| p.is_file() && p.extension().map(|e| e == "txt").unwrap_or(false))
            .collect();
        files.sort();
        self.txt_files = files;
        self.txt_file_idx = self.txt_files.iter()
            .position(|p| p == &self.active_file)
            .unwrap_or(0);
    }

    fn auto_save(&self) {
        let _ = save_file(&self.active_file, self.ring.lines());
    }

    fn enter_f2_edit(&mut self) {
        self.f2_editor = self.ring.current().to_owned();
        self.f2_cursor = self.f2_editor.len();
        self.f2_mode   = F2Mode::Editing;
    }

    fn reformat_file(&mut self) {
        use crate::text::format_sentences;
        let mut result: Vec<String> = Vec::new();
        let mut prev_dot = false;
        for line in self.ring.lines().to_vec() {
            let s = line.trim();
            if s == "." {
                if !prev_dot { result.push(".".to_string()); }
                prev_dot = true;
            } else if !s.is_empty() {
                for sentence in format_sentences(s) {
                    result.push(sentence);
                }
                prev_dot = false;
            }
        }
        let idx = self.ring.index.min(result.len().saturating_sub(1));
        self.ring = LineRing::from_lines(result);
        self.ring.index = idx;
        self.auto_save();
    }
}

// ── App (sctk boilerplate) ────────────────────────────────────────────────────

pub struct App {
    pub registry_state:   RegistryState,
    pub compositor_state: CompositorState,
    pub output_state:     OutputState,
    pub shm_state:        Shm,
    pub seat_state:       SeatState,
    pub layer_shell:      LayerShell,

    pub layer_surface:    Option<LayerSurface>,
    pub keyboard:         Option<wl_keyboard::WlKeyboard>,
    pub pool:             SlotPool,

    pub glyph_cache:      GlyphCache,
    pub ui:               UiState,
    pub modifiers:        Modifiers,

    pub width:            u32,
    pub height:           u32,
    pub exit:             bool,
}

impl App {
    pub fn new(globals: &GlobalList, qh: &QueueHandle<App>) -> anyhow::Result<Self> {
        let compositor_state = CompositorState::bind(globals, qh)?;
        let output_state     = OutputState::new(globals, qh);
        let shm_state        = Shm::bind(globals, qh)?;
        let layer_shell      = LayerShell::bind(globals, qh)?;
        let seat_state       = SeatState::new(globals, qh);

        let config   = Config::load();
        let void_dir = config.void_dir();
        std::fs::create_dir_all(&void_dir)?;

        let font_bytes  = crate::load_font(&config.font_family)?;
        let glyph_cache = GlyphCache::new(&font_bytes)?;

        let active_file = void_dir.join("0.txt");
        if !active_file.exists() { let _ = std::fs::write(&active_file, ""); }

        let file_index = FileIndex::build(&void_dir);
        let ring = {
            let lines = read_file(&active_file);
            LineRing::from_lines(lines)
        };

        let txt_files: Vec<PathBuf> = std::fs::read_dir(&void_dir)
            .into_iter().flatten().flatten()
            .map(|e| e.path())
            .filter(|p| p.is_file() && p.extension().map(|e| e == "txt").unwrap_or(false))
            .collect::<Vec<_>>()
            .into_iter()
            .collect();
        let mut txt_files = txt_files;
        txt_files.sort();
        let txt_file_idx = txt_files.iter().position(|p| p == &active_file).unwrap_or(0);

        let book_dir = void_dir.clone();
        let book_files = load_book_order(&book_dir);
        let book_ring = {
            let names: Vec<String> = book_files.iter()
                .map(|p| p.file_stem().unwrap_or_default().to_string_lossy().into_owned())
                .collect();
            if names.is_empty() {
                LineRing::from_lines(vec!["(empty)".to_string()])
            } else {
                LineRing::from_lines(names)
            }
        };
        let vault_lines = load_vault_lines(&void_dir);
        let vault_ring = if vault_lines.is_empty() {
            LineRing::from_lines(vec!["(vault empty)".to_string()])
        } else {
            LineRing::from_lines(vault_lines)
        };

        let surface      = compositor_state.create_surface(qh);
        let layer_surface = layer_shell.create_layer_surface(
            qh, surface, Layer::Bottom, Some("voider"), None,
        );
        layer_surface.set_anchor(Anchor::all());
        layer_surface.set_exclusive_zone(-1);
        layer_surface.set_keyboard_interactivity(KeyboardInteractivity::OnDemand);
        layer_surface.commit();

        let pool = SlotPool::new(1920 * 1080 * 4 * 2, &shm_state)?;

        let ui = UiState {
            config,
            view: View::Write,
            ring,
            active_file,
            void_dir,
            book_dir,
            txt_files,
            txt_file_idx,
            file_index,
            input: String::new(),
            ring_nav_idx: None,
            first_up_after_submit: false,
            last_inserted_idx: None,
            f2_mode:       F2Mode::Normal,
            f2_editor:     String::new(),
            f2_cursor:     0,
            f2_offset:     0.0,
            f2_anim_tick:  0,
            f2_anim_delta: 0,
            book_ring,
            book_files,
            vault_ring,
            blink_tick: 0,
            opacity: 1.0,
            show_overlay: false,
        };

        Ok(Self {
            registry_state:   RegistryState::new(globals),
            compositor_state,
            output_state,
            shm_state,
            seat_state,
            layer_shell,
            layer_surface: Some(layer_surface),
            keyboard: None,
            pool,
            glyph_cache,
            ui,
            modifiers: Modifiers::default(),
            width:  1920,
            height: 1080,
            exit:   false,
        })
    }

    pub fn draw(&mut self, qh: &QueueHandle<App>) {
        let Some(layer) = &self.layer_surface else { return; };
        let stride = self.width * 4;
        let Ok((buffer, canvas)) = self.pool.create_buffer(
            self.width as i32, self.height as i32, stride as i32, wl_shm::Format::Argb8888,
        ) else { return; };

        render::draw_frame(canvas, &mut self.glyph_cache, &self.ui, self.width, self.height);

        let surface = layer.wl_surface();
        surface.attach(Some(buffer.wl_buffer()), 0, 0);
        surface.damage_buffer(0, 0, i32::MAX, i32::MAX);
        surface.frame(qh, surface.clone());
        surface.commit();
    }
}

// ── sctk delegates ────────────────────────────────────────────────────────────

impl CompositorHandler for App {
    fn scale_factor_changed(&mut self, _: &Connection, _: &QueueHandle<Self>, _: &wl_surface::WlSurface, _: i32) {}
    fn transform_changed(&mut self, _: &Connection, _: &QueueHandle<Self>, _: &wl_surface::WlSurface, _: wl_output::Transform) {}
    fn frame(&mut self, _: &Connection, qh: &QueueHandle<Self>, _: &wl_surface::WlSurface, _: u32) {
        self.ui.blink_tick = self.ui.blink_tick.wrapping_add(1);
        self.ui.tick_animation();
        self.draw(qh);
    }
}

impl OutputHandler for App {
    fn output_state(&mut self) -> &mut OutputState { &mut self.output_state }
    fn new_output(&mut self, _: &Connection, _: &QueueHandle<Self>, _: wl_output::WlOutput) {}
    fn update_output(&mut self, _: &Connection, _: &QueueHandle<Self>, _: wl_output::WlOutput) {}
    fn output_destroyed(&mut self, _: &Connection, _: &QueueHandle<Self>, _: wl_output::WlOutput) {}
}

impl LayerShellHandler for App {
    fn closed(&mut self, _: &Connection, _: &QueueHandle<Self>, _: &LayerSurface) { self.exit = true; }
    fn configure(&mut self, _: &Connection, qh: &QueueHandle<Self>, _: &LayerSurface, configure: LayerSurfaceConfigure, _: u32) {
        if configure.new_size.0 > 0 && configure.new_size.1 > 0 {
            self.width  = configure.new_size.0;
            self.height = configure.new_size.1;
            let _ = self.pool.resize((self.width * self.height * 4 * 2) as usize);
        }
        self.draw(qh);
    }
}

impl SeatHandler for App {
    fn seat_state(&mut self) -> &mut SeatState { &mut self.seat_state }
    fn new_seat(&mut self, _: &Connection, _: &QueueHandle<Self>, _: wl_seat::WlSeat) {}
    fn new_capability(&mut self, _: &Connection, qh: &QueueHandle<Self>, seat: wl_seat::WlSeat, cap: Capability) {
        if cap == Capability::Keyboard && self.keyboard.is_none() {
            self.keyboard = self.seat_state.get_keyboard(qh, &seat, None).ok();
        }
    }
    fn remove_capability(&mut self, _: &Connection, _: &QueueHandle<Self>, _: wl_seat::WlSeat, cap: Capability) {
        if cap == Capability::Keyboard { if let Some(k) = self.keyboard.take() { k.release(); } }
    }
    fn remove_seat(&mut self, _: &Connection, _: &QueueHandle<Self>, _: wl_seat::WlSeat) {}
}

impl KeyboardHandler for App {
    fn enter(&mut self, _: &Connection, _: &QueueHandle<Self>, _: &wl_keyboard::WlKeyboard, _: &wl_surface::WlSurface, _: u32, _: &[u32], _: &[smithay_client_toolkit::seat::keyboard::Keysym]) {}
    fn leave(&mut self, _: &Connection, _: &QueueHandle<Self>, _: &wl_keyboard::WlKeyboard, _: &wl_surface::WlSurface, _: u32) {}
    fn press_key(&mut self, _: &Connection, _: &QueueHandle<Self>, _: &wl_keyboard::WlKeyboard, _: u32, event: KeyEvent) {
        let action = input::map(event.keysym, event.utf8.as_deref(), &self.modifiers);
        self.ui.apply(action);
    }
    fn release_key(&mut self, _: &Connection, _: &QueueHandle<Self>, _: &wl_keyboard::WlKeyboard, _: u32, _: KeyEvent) {}
    fn update_modifiers(&mut self, _: &Connection, _: &QueueHandle<Self>, _: &wl_keyboard::WlKeyboard, _: u32, modifiers: Modifiers) {
        self.modifiers = modifiers;
    }
    fn update_repeat_info(&mut self, _: &Connection, _: &QueueHandle<Self>, _: &wl_keyboard::WlKeyboard, _: RepeatInfo) {}
}

impl ShmHandler for App {
    fn shm_state(&mut self) -> &mut Shm { &mut self.shm_state }
}

impl ProvidesRegistryState for App {
    fn registry(&mut self) -> &mut RegistryState { &mut self.registry_state }
    registry_handlers![OutputState, SeatState];
}

delegate_compositor!(App);
delegate_output!(App);
delegate_layer!(App);
delegate_seat!(App);
delegate_keyboard!(App);
delegate_shm!(App);
delegate_registry!(App);

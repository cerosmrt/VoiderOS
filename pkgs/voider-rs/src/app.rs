//! App state and the F1 view.
//!
//! The state (ring, entry, active file) is kept free of egui so it can be
//! tested without a display; `eframe::App` below only draws it and feeds it
//! keys.

#![allow(dead_code)]

use std::io;
use std::path::{Path, PathBuf};

use crate::backup;
use crate::browse;
use crate::bundle;
use crate::carousel;
use crate::config::Config;
use crate::corpus;
use crate::f5;
use crate::fonts;
use crate::hyphen;
use crate::ipc;
use crate::library::{self, Library};
use crate::paragraphs;
use crate::pdf;
use crate::position;
use crate::reading;
use crate::reformat;
use crate::shot;
use crate::slides;
use crate::split;
use crate::line_ring::LineRing;
use crate::text_line::{self, TextLine};
use crate::tts::Tts;
use crate::typeset;
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

/// Where Ctrl+Shift+A has got to: asking for the book's name (a whole book has no
/// single title), then for its language.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BundleStage {
    Name,
    Lang,
}

/// What the name and language are being asked FOR.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PromptKind {
    /// PDF + EPUB + TXT: name, then language.
    Bundle,
    /// Instagram slides: just a name.
    Carousel,
    /// The same, wrapped in a cover and a countercover; the picture is already chosen.
    CarouselCover(PathBuf),
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BundlePrompt {
    pub stage: BundleStage,
    pub name: String,
    pub lang: bundle::Lang,
    pub kind: PromptKind,
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
    /// El lector del corpus: un libro de O/ como anillo.
    F6,
    /// El working set: los libros elegidos a mano, uno por ranura.
    F7,
    /// El oráculo: una línea al azar del corpus.
    F8,
    /// The book as a book: set in a column, turned page by page.
    F4,
    /// The active file as paragraphs, in order, to be moved or sent away.
    F5,
    /// The active file as flowing prose in one box, saved on leaving.
    F9,
    /// Settings: the writing font and its size.
    F10,
}

impl View {
    /// Restorable across a restart: F1, F2, F3, F4 — the Python's own `(0, 1,
    /// 2, 3)`. The rest edit or configure one thing and are not places to be.
    fn key(self) -> Option<&'static str> {
        match self {
            View::F1 => Some("F1"),
            View::F2 => Some("F2"),
            View::F3 => Some("F3"),
            View::F4 => Some("F4"),
            View::F6 => Some("F6"),
            View::F7 => Some("F7"),
            View::F5 | View::F8 | View::F9 | View::F10 => None,
        }
    }

    fn from_key(s: &str) -> Option<Self> {
        match s {
            "F1" => Some(View::F1),
            "F2" => Some(View::F2),
            "F3" => Some(View::F3),
            "F4" => Some(View::F4),
            "F6" => Some(View::F6),
            "F7" => Some(View::F7),
            _ => None,
        }
    }
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
    /// Alt+F4 was pressed: the window should close once this frame is done.
    pub quit_requested: bool,
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
    /// F2 Tab: (ring index, start, end) of the last `I/` fragment inserted, so
    /// pressing Tab again on the same spot re-rolls it instead of piling up.
    pub pending_fragment: Option<(usize, usize, usize)>,
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
    /// Ctrl+T: la voz. Vive acá porque cada vista decide qué se lee.
    pub tts: Tts,
    /// Telling sibling instances what changed. `None` when running alone (and
    /// in tests, which have no business opening sockets).
    pub ipc: Option<ipc::Ipc>,
    /// Ctrl+F2/F3/F4: el navegador abierto, esperando que elijas.
    pub browser: Option<browse::Browser>,
    /// F11: the shortcut reference, over whatever view is underneath.
    pub help_open: bool,
    /// Ctrl+B: a backup worked out and waiting to be accepted. Nothing is
    /// written to the drive until it is.
    pub backup_prompt: Option<BackupPrompt>,
    /// The sale-bundle question (name, then language), while it is open.
    pub bundle_prompt: Option<BundlePrompt>,
    /// F6: el libro del corpus abierto, como anillo de líneas.
    pub o_ring: LineRing,
    /// F6: qué archivo de O/ es ese (vacío si no hay ninguno).
    pub o_file: String,
    /// F7: los libros elegidos a mano.
    pub ws: corpus::WorkingSet,
    /// F7: la posición del cursor en el anillo del working set.
    pub ws_index: usize,
    /// Los nombres de O/, desde el cache — nunca se recorre en vivo.
    pub o_books: Vec<String>,
    /// F8: la línea que el oráculo sacó.
    pub oracle: String,
    /// F4: what is being read, as titled sections of prose.
    pub reading: Vec<reading::Section>,
    /// Bumped each time F4 gathers what it will show, so a layout cached for a
    /// different chapter is never taken for the current one.
    pub reading_serial: u64,
    /// F4 shows the carousel's slides instead of the book's pages (Ctrl+Shift+V).
    pub carousel_view: bool,
    /// What the preview shows: the same plan the export writes.
    pub carousel_slides: Vec<slides::Slide>,
    /// F4: which page is on screen.
    pub page: usize,
    /// F4: the paragraph to open on — where you were in F2.
    pub open_at_para: usize,
    /// F9: the active file as one editable block of prose.
    pub prose: String,
    /// Whether that prose was actually edited — viewing it saves nothing.
    pub prose_dirty: bool,
    /// Where F9 should park its caret on entry (a character offset into `prose`);
    /// the view takes it once and applies it.
    pub prose_caret: Option<usize>,
    /// Ctrl+F in F2: filtering the ring to matching lines.
    pub f2_search: Option<SearchState>,
    /// Ctrl+F in F3: filtering the library to matching chapters.
    pub f3_search: Option<SearchState>,
}

/// A backup that has been worked out but not yet written: which drives were
/// found, which one is selected, and exactly what would go onto it.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BackupPrompt {
    pub drives: Vec<PathBuf>,
    pub idx: usize,
    pub plan: backup::Plan,
}

/// A live filter over some indexed list (the ring's lines, or the library's
/// entries), ported from `_f2_search_*`/`_f3_search_*` in f2_mixin.py /
/// f3_mixin.py. Tracked by ORIGINAL index rather than by matched text, unlike
/// the Python (which re-finds the confirmed line by text, ambiguous were two
/// lines identical) — an index is unambiguous and needs no placeholder for
/// "nothing matched", so an empty `matches` here just means nothing to show.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SearchState {
    pub query: TextLine,
    /// Original indices of the lines/entries that currently match, in order.
    pub matches: Vec<usize>,
    /// Which match is highlighted.
    pub highlight: usize,
    /// The real index to restore if the search is cancelled.
    pub saved_index: usize,
}

impl Voider {
    /// Open `file` inside `void_dir` as the active document.
    pub fn open(void_dir: impl Into<PathBuf>, file: impl Into<PathBuf>) -> Self {
        let void_dir = void_dir.into();
        let current_file = file.into();
        let doc = void::load_doc(&current_file);
        let config = Config::load(&void_dir);
        let mut ring = LineRing::new(doc.lines);
        ring.index = restored_index(&void_dir, &current_file, ring.lines.len());
        Self {
            typewriter: config.typewriter,
            quit_requested: false,
            show_title: config.show_title,
            config,
            void_dir,
            current_file,
            ring,
            library: Library::default(),
            view: View::F1,
            entry: TextLine::new(""),
            pending_new: false,
            pending_merge: false,
            merge_dot_idx: None,
            para_focus: false,
            para_focus_content: Vec::new(),
            pending_fragment: None,
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
            tts: Tts::default(),
            ipc: None,
            o_ring: LineRing::new([".".to_string()]),
            o_file: String::new(),
            ws: corpus::WorkingSet::default(),
            ws_index: 1,
            o_books: Vec::new(),
            oracle: String::new(),
            reading: Vec::new(),
            reading_serial: 0,
            carousel_view: false,
            carousel_slides: Vec::new(),
            page: 0,
            open_at_para: 0,
            browser: None,
            help_open: false,
            backup_prompt: None,
            bundle_prompt: None,
            prose: String::new(),
            prose_dirty: false,
            prose_caret: None,
            f2_search: None,
            f3_search: None,
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
        let saved = self.current_file.clone();
        self.notify_saved(&saved);
        if !self.undo_applying {
            self.undo.record(saved, before, after, key);
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
        // Where we came FROM matters to F4, which follows the F3 highlight —
        // and self.view is about to stop being it.
        let from = self.view;
        if self.view == View::F2 {
            let _ = self.doc_live_save();
            self.save_last_line();
        }
        // Search bars belong to their own view; leaving it closes them, the
        // cursor restored as if the search had been cancelled.
        if view != View::F2 {
            self.f2_search_cancel();
        }
        if view != View::F3 {
            self.f3_search_cancel();
        }
        // Salir del lector guarda por dónde ibas, como en el Python.
        if self.view == View::F6 && view != View::F6 {
            self.save_o_position();
        }
        // Leaving the prose editor commits what was typed there.
        if self.view == View::F9 && view != View::F9 {
            let _ = self.prose_save();
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
            View::F9 => self.enter_prose_editor(),
            View::F4 => {
                self.enter_reading(from);
                self.rebuild_carousel_plan();
            }
            View::F6 => self.enter_o_reader(),
            View::F7 => self.enter_o_browser(),
            View::F8 => self.refresh_oracle(),
        }
        self.save_last_view();
    }

    // ── F4: the book as a book ─────────────────────────────────────────────────

    /// Gather what F4 should show and where in it to open.

    /// Ctrl+S en F4: el libro que estás leyendo, a un PDF al lado del void.
    ///
    /// El Python abre un diálogo de "guardar como"; acá el destino se deduce del
    /// título, que es lo que uno iba a escribir igual. Devuelve dónde quedó.
    pub fn export_pdf(&mut self) -> Option<PathBuf> {
        if self.reading.is_empty() {
            self.status = "Nada para exportar".into();
            return None;
        }
        let title = self
            .reading
            .first()
            .map(|s| s.title.clone())
            .filter(|t| !t.is_empty())
            .unwrap_or_else(|| file_title(&self.current_file));
        let dest = pdf::default_path(&self.void_dir, &title);
        let family = self.config.font_family.clone();
        let html = pdf::book_html(&self.reading, &family);
        // La fuente se incrusta si está en la máquina, así el PDF se ve igual
        // en cualquier lado.
        let bytes = match pdf::render(&html, &family, fonts::load_family(&family)) {
            Ok(b) => b,
            Err(e) => {
                self.status = format!("PDF: {e}");
                return None;
            }
        };
        match std::fs::write(&dest, &bytes) {
            Ok(()) => {
                self.status = format!("PDF → {}", dest.display());
                Some(dest)
            }
            Err(e) => {
                self.status = format!("No se pudo escribir el PDF: {e}");
                None
            }
        }
    }

    /// The name a sale bundle takes by itself: the chapter's own when F4 shows
    /// exactly one. A whole book has no single title, so it has to be asked
    /// for — `None` means ask.
    pub fn bundle_default_name(&self) -> Option<String> {
        match self.reading.as_slice() {
            [only] => Some(if only.name.is_empty() { "capitulo".to_string() } else { only.name.clone() }),
            _ => None,
        }
    }

    /// Ctrl+Shift+V en F4: cambiar entre las páginas del libro y los slides del
    /// carrusel, tal como se exportarían. Vuelve al primer slide.
    pub fn toggle_carousel_view(&mut self) {
        self.carousel_view = !self.carousel_view;
        self.page = 0;
        self.rebuild_carousel_plan();
        self.status = format!("Carousel preview {}", if self.carousel_view { "ON" } else { "OFF" });
    }

    /// Lay the slides out again — from the sections F4 holds, in the configured
    /// frame. Only while the preview is on; otherwise there is nothing to show.
    fn rebuild_carousel_plan(&mut self) {
        if !self.carousel_view || self.reading.is_empty() {
            self.carousel_slides.clear();
            return;
        }
        let (w, h) = self.carousel_size();
        let font = self.type_font();
        self.carousel_slides = slides::plan(&self.carousel_sections(), &font, w, h);
    }

    /// How many pages F4 turns through: the slides when previewing the carousel,
    /// otherwise what the book layout measured (`measured`).
    pub fn f4_page_count(&self, measured: usize) -> usize {
        if self.carousel_view {
            self.carousel_slides.len().max(1)
        } else {
            measured
        }
    }

    /// The font the book and the slides are set in, with the configured hyphenation.
    pub fn type_font(&self) -> typeset::TypeFont {
        typeset::TypeFont::load(&self.config.font_family)
            .with_hyphenation(hyphen::Mode::from_config(&self.config.reading_hyphen_lang))
    }

    /// The slide size the configuration asks for.
    pub fn carousel_size(&self) -> (u32, u32) {
        carousel::dimensions(&self.config.carousel_preset, self.config.carousel_w, self.config.carousel_h)
    }

    /// The sections F4 is showing, as (name, raw lines) — what a carousel is made of.
    fn carousel_sections(&self) -> Vec<(String, Vec<String>)> {
        self.reading.iter().map(|s| (s.name.clone(), s.lines.clone())).collect()
    }

    /// Write every slide of the carousel into `out_dir`, numbered continuously
    /// from `start_n`. The slides are the plan the preview shows (`slides::plan`),
    /// so what is written is exactly what was previewed. Returns the next free
    /// number and how many body slides there were.
    fn write_carousel_chapters(
        &self,
        out_dir: &Path,
        font: &typeset::TypeFont,
        start_n: usize,
    ) -> io::Result<(usize, usize)> {
        let (w, h) = self.carousel_size();
        let (mut n, mut body_slides) = (start_n, 0);
        for slide in slides::plan(&self.carousel_sections(), font, w, h) {
            let kind = match slide {
                slides::Slide::Title(_) => carousel::SlideKind::Title,
                slides::Slide::Body(_) => {
                    body_slides += 1;
                    carousel::SlideKind::Body
                }
            };
            slides::render_slide(&slide, font, w, h)
                .save_png(&out_dir.join(carousel::file_name(n, &kind)))?;
            n += 1;
        }
        Ok((n, body_slides))
    }

    /// Where a carousel goes, or `None` when there is nothing to export or no
    /// usable name. A typed name stays one folder inside `void/carousel/`.
    fn carousel_dir(&mut self, out_name: &str) -> Option<PathBuf> {
        if self.reading.is_empty() {
            self.status = "Nada para exportar".into();
            return None;
        }
        let name = bundle::safe_folder_name(out_name);
        if name.is_empty() {
            self.status = "Carrusel cancelado (sin nombre)".into();
            return None;
        }
        Some(self.void_dir.join("carousel").join(name))
    }

    /// Ctrl+Shift+C en F4: lo que se está leyendo, como slides de Instagram. El
    /// alcance es el de F4 (el capítulo o el libro entero); cada capítulo tiene un
    /// slide de título propio y después su cuerpo, paginado a la proporción
    /// configurada. Va a `void/carousel/<nombre>/`.
    pub fn export_carousel(&mut self, out_name: &str) -> io::Result<Option<PathBuf>> {
        let Some(dir) = self.carousel_dir(out_name) else {
            return Ok(None);
        };
        std::fs::create_dir_all(&dir)?;
        let font = self.type_font();
        let (_, body) = self.write_carousel_chapters(&dir, &font, 1)?;
        self.status = format!(
            "Carrusel: {} capítulo(s), {body} slides + títulos → {}",
            self.reading.len(),
            dir.display()
        );
        Ok(Some(dir))
    }

    /// Ctrl+Shift+B en F4: lo mismo, envuelto en una portada (la imagen elegida,
    /// con la marca «I» encima) y una contratapa con el título. Un comando aparte
    /// para que un Ctrl+Shift+C nunca necesite una portada. Una imagen que no se
    /// pueda leer deja la portada sobre papel liso, como el Python.
    pub fn export_carousel_with_cover(&mut self, out_name: &str, cover: &Path) -> io::Result<Option<PathBuf>> {
        let Some(dir) = self.carousel_dir(out_name) else {
            return Ok(None);
        };
        std::fs::create_dir_all(&dir)?;
        let (w, h) = self.carousel_size();
        let font = self.type_font();
        let font_px = carousel::geometry(w, h).font_px;
        let back_title = match self.reading.as_slice() {
            [only] => only.name.clone(),
            _ => out_name.trim().to_string(),
        };

        slides::render_cover_slide(cover, w, h, &font, font_px, "I", slides::PAPER, slides::INK)
            .save_png(&dir.join(carousel::file_name(1, &carousel::SlideKind::Cover)))?;
        let (n, body) = self.write_carousel_chapters(&dir, &font, 2)?;
        slides::render_title_slide(&back_title, &font, w, h, font_px, slides::PAPER, slides::INK)
            .save_png(&dir.join(carousel::file_name(n, &carousel::SlideKind::Back)))?;
        self.status = format!(
            "Carrusel con tapa: {} capítulo(s), {body} slides + portada + contratapa → {}",
            self.reading.len(),
            dir.display()
        );
        Ok(Some(dir))
    }

    /// Ctrl+Shift+C en F4: el carrusel. Un capítulo suelto nombra su propia carpeta
    /// y sale de una; un libro entero no tiene un solo título, así que se pregunta.
    pub fn begin_carousel(&mut self) {
        if self.reading.is_empty() {
            self.status = "Nada para exportar".into();
            return;
        }
        match self.bundle_default_name() {
            Some(name) => {
                let _ = self.export_carousel(&name);
            }
            None => {
                self.bundle_prompt = Some(BundlePrompt {
                    stage: BundleStage::Name,
                    name: String::new(),
                    lang: bundle::Lang::Es,
                    kind: PromptKind::Carousel,
                });
            }
        }
    }

    /// Ctrl+Shift+B en F4: lo mismo, con portada. Primero se elige la imagen.
    pub fn begin_carousel_with_cover(&mut self) {
        if self.reading.is_empty() {
            self.status = "Nada para exportar".into();
            return;
        }
        self.open_browser(browse::Purpose::Cover);
    }

    /// La portada ya está elegida: un capítulo suelto exporta de una, un libro
    /// entero pide el nombre.
    fn cover_chosen(&mut self, cover: PathBuf) -> io::Result<()> {
        match self.bundle_default_name() {
            Some(name) => self.export_carousel_with_cover(&name, &cover).map(|_| ()),
            None => {
                self.bundle_prompt = Some(BundlePrompt {
                    stage: BundleStage::Name,
                    name: String::new(),
                    lang: bundle::Lang::Es,
                    kind: PromptKind::CarouselCover(cover),
                });
                Ok(())
            }
        }
    }

    /// Ctrl+Shift+A in F4 starts the question. A single chapter names its own
    /// bundle, so only the language is asked; a whole book is asked its name first.
    pub fn begin_sale_bundle(&mut self) {
        if self.reading.is_empty() {
            self.status = "Nada para exportar".into();
            return;
        }
        let preset = self.bundle_default_name();
        self.bundle_prompt = Some(BundlePrompt {
            stage: if preset.is_some() { BundleStage::Lang } else { BundleStage::Name },
            name: preset.unwrap_or_default(),
            lang: bundle::Lang::Es,
            kind: PromptKind::Bundle,
        });
    }

    /// Text typed into the name, while the name is what is being asked.
    pub fn bundle_type(&mut self, text: &str) {
        if let Some(p) = &mut self.bundle_prompt {
            if p.stage == BundleStage::Name {
                p.name.push_str(text);
            }
        }
    }

    pub fn bundle_backspace(&mut self) {
        if let Some(p) = &mut self.bundle_prompt {
            if p.stage == BundleStage::Name {
                p.name.pop();
            }
        }
    }

    /// Step the language to the next one offered, wrapping.
    pub fn bundle_cycle_lang(&mut self, delta: isize) {
        if let Some(p) = &mut self.bundle_prompt {
            let all = bundle::Lang::ALL;
            let at = all.iter().position(|l| *l == p.lang).unwrap_or(0) as isize;
            p.lang = all[(at + delta).rem_euclid(all.len() as isize) as usize];
        }
    }

    /// Enter: on the name, go on to the language (a blank name cancels, as the
    /// Python's does); on the language, write the bundle.
    pub fn bundle_confirm(&mut self) -> io::Result<()> {
        let Some(p) = self.bundle_prompt.clone() else {
            return Ok(());
        };
        match p.stage {
            BundleStage::Name => {
                if p.name.trim().is_empty() {
                    self.bundle_prompt = None;
                    self.status = match p.kind {
                        PromptKind::Bundle => "Bundle cancelado (sin nombre)",
                        _ => "Carrusel cancelado (sin nombre)",
                    }
                    .into();
                    return Ok(());
                }
                match p.kind {
                    // The bundle still has to ask the language...
                    PromptKind::Bundle => {
                        if let Some(pr) = &mut self.bundle_prompt {
                            pr.stage = BundleStage::Lang;
                        }
                    }
                    // ...a carousel has none to ask: the name is the last answer.
                    PromptKind::Carousel => {
                        self.bundle_prompt = None;
                        self.export_carousel(&p.name)?;
                    }
                    PromptKind::CarouselCover(cover) => {
                        self.bundle_prompt = None;
                        self.export_carousel_with_cover(&p.name, &cover)?;
                    }
                }
                Ok(())
            }
            BundleStage::Lang => {
                self.bundle_prompt = None;
                self.export_sale_bundle(&p.name, p.lang).map(|_| ())
            }
        }
    }

    pub fn cancel_bundle(&mut self) {
        self.bundle_prompt = None;
    }

    /// Ctrl+Shift+A en F4: PDF + EPUB + TXT juntos, todo lo que hace falta para
    /// subir el libro a la venta. El alcance es el de F4: el capítulo que se ve, o
    /// el libro entero si F3 estaba sobre un punto. Devuelve la carpeta donde
    /// quedó, o `None` si no había nada que exportar o el nombre vino vacío.
    ///
    /// Si el PDF falla (por ejemplo, un build sin esa función) el EPUB y el TXT se
    /// escriben igual, y el estado lo dice en vez de dar el bundle por completo.
    pub fn export_sale_bundle(&mut self, out_name: &str, lang: bundle::Lang) -> io::Result<Option<PathBuf>> {
        if self.reading.is_empty() {
            self.status = "Nada para exportar".into();
            return Ok(None);
        }
        let out_name = bundle::safe_folder_name(out_name);
        let out_name = out_name.as_str();
        if out_name.is_empty() {
            self.status = "Bundle cancelado (sin nombre)".into();
            return Ok(None);
        }
        let dir = bundle::bundle_dir(&self.void_dir, &self.config, lang, out_name);
        std::fs::create_dir_all(&dir)?;

        let sections: Vec<(String, Vec<String>)> = self
            .reading
            .iter()
            .map(|s| (s.name.clone(), s.lines.clone()))
            .collect();

        let mut pdf_note = String::new();
        let family = self.config.font_family.clone();
        let html = pdf::book_html(&self.reading, &family);
        match pdf::render(&html, &family, fonts::load_family(&family)) {
            Ok(bytes) => std::fs::write(dir.join(format!("{out_name}.pdf")), bytes)?,
            Err(e) => pdf_note = format!(" (sin PDF: {e})"),
        }
        crate::epub::write_epub(
            &dir.join(format!("{out_name}.epub")),
            &sections,
            out_name,
            "",
            lang.code(),
        )?;
        std::fs::write(
            dir.join(format!("{out_name}.txt")),
            bundle::sections_as_txt(&sections),
        )?;

        self.status = format!(
            "Bundle de venta: {} capítulo(s) → {}{pdf_note}",
            sections.len(),
            dir.display()
        );
        Ok(Some(dir))
    }

    /// Ctrl+P en F4: lo mismo, y después a la impresora.
    pub fn print_reading(&mut self) {
        let Some(path) = self.export_pdf() else {
            return;
        };
        match pdf::send_to_printer(&path) {
            Ok(()) => self.status = format!("A la impresora: {}", path.display()),
            Err(e) => self.status = format!("PDF guardado, pero no se imprimió: {e}"),
        }
    }
    ///
    /// Follows the F3 highlight, as the Python does: sitting on a separator
    /// means the whole book below it, one section per chapter with the scratch
    /// portals skipped; sitting on a chapter (or coming from anywhere else)
    /// means the active file alone. Opening on the paragraph you were just
    /// editing only makes sense when it IS the file being shown.
    pub fn enter_reading(&mut self, from: View) {
        self.reading_serial += 1;
        self.page = 0;
        let from_book = from == View::F3
            || (!self.library.entries.is_empty()
                && library::is_separator(self.library.current()));

        if from_book && library::is_separator(self.library.current()) {
            self.reading = self.book_below_cursor();
            self.open_at_para = 0;
            if !self.reading.is_empty() {
                return;
            }
        }
        // One file: whichever chapter F3 is on, else the active one.
        let path = if from_book && !library::is_separator(self.library.current()) {
            library::chapter_path(&self.void_dir, self.library.current())
        } else {
            self.current_file.clone()
        };
        let lines = void::load_doc(&path).lines;
        self.open_at_para = if same_file(&path, &self.current_file) {
            reading::para_ordinal_at(&self.ring.lines, self.ring.index)
        } else {
            0
        };
        self.reading = vec![reading::Section {
            title: file_title(&path).to_uppercase(),
            paragraphs: reformat::lines_to_paragraphs(&lines),
            name: file_title(&path),
            lines,
        }];
    }

    /// Every chapter from the separator down to the next one, in reading order.
    fn book_below_cursor(&self) -> Vec<reading::Section> {
        let entries = &self.library.entries;
        let n = entries.len();
        let mut out = Vec::new();
        if n == 0 {
            return out;
        }
        let mut i = (self.library.index + 1) % n;
        for _ in 0..n.saturating_sub(1) {
            let name = &entries[i];
            if library::is_separator(name) {
                break;
            }
            if !library::is_portal(name) {
                let path = library::chapter_path(&self.void_dir, name);
                if path.is_file() {
                    let lines = void::load_doc(&path).lines;
                    let paragraphs = reformat::lines_to_paragraphs(&lines);
                    if !paragraphs.is_empty() {
                        out.push(reading::Section {
                            title: library::display_name(name).to_uppercase(),
                            paragraphs,
                            name: library::display_name(name),
                            lines,
                        });
                    }
                }
            }
            i = (i + 1) % n;
        }
        out
    }

    /// Turn pages, clamped — a book has a first and a last page.
    pub fn turn_page(&mut self, delta: isize, total: usize) {
        if total == 0 {
            return;
        }
        self.page = (self.page as isize + delta).clamp(0, total as isize - 1) as usize;
    }

    /// F12: a picture of the screen into `void/screenshots/`.
    ///
    /// The Python grabs the screen through Qt. Wayland does not let a client do
    /// that — a window cannot see the compositor — so this shells out to `grim`,
    /// which is already on this machine and already bound in the Hyprland config.
    /// Returns where it landed.
    pub fn take_screenshot(&mut self) -> Option<PathBuf> {
        let dir = self.void_dir.join("screenshots");
        if let Err(e) = std::fs::create_dir_all(&dir) {
            self.status = format!("Screenshot failed: {e}");
            return None;
        }
        let path = dir.join(format!(
            "snap_{}.png",
            chrono::Local::now().format("%Y%m%d_%H%M%S")
        ));
        match std::process::Command::new("grim").arg(&path).output() {
            Ok(out) if out.status.success() => {
                self.status = format!("Screenshot → {}", path.display());
                Some(path)
            }
            Ok(out) => {
                let err = String::from_utf8_lossy(&out.stderr);
                self.status = format!("Screenshot failed: {}", err.trim());
                None
            }
            Err(e) => {
                self.status = format!("Screenshot failed (is grim installed?): {e}");
                None
            }
        }
    }

    /// Shift+F12: a 1:1 screenshot of the window into `void/covers/`, for carousel
    /// cover art — the window's centred square, the side bars trimmed. The window's
    /// own place comes from `hyprctl -j clients` (matched by pid), the compositor's
    /// own word for it, not the toolkit's belief.
    pub fn take_circle_screenshot(&mut self) -> Option<PathBuf> {
        self.take_circle_screenshot_with(&mut shot::real_run, std::process::id())
    }

    /// The same, with the command runner and the pid handed in, so a test can
    /// answer for `hyprctl` and `grim` without either being installed.
    pub fn take_circle_screenshot_with(
        &mut self,
        run: &mut dyn FnMut(&str, &[String]) -> io::Result<shot::CmdOutput>,
        pid: u32,
    ) -> Option<PathBuf> {
        let clients = match run("hyprctl", &["-j".to_string(), "clients".to_string()]) {
            Ok(out) => out.stdout,
            Err(e) => {
                self.status = format!("Cover screenshot: could not ask hyprctl ({e})");
                return None;
            }
        };
        let Some(win) = shot::window_for_pid(&clients, pid) else {
            self.status = "Cover screenshot: this window was not found in hyprctl".into();
            return None;
        };
        let (x, y, side) = shot::square_crop_for(win);
        if side <= 0 {
            self.status = "Cover screenshot: the window has no size".into();
            return None;
        }
        let dir = self.void_dir.join("covers");
        if let Err(e) = std::fs::create_dir_all(&dir) {
            self.status = format!("Cover screenshot failed: {e}");
            return None;
        }
        let path = dir.join(format!("cover_{}.png", chrono::Local::now().format("%Y%m%d_%H%M%S")));
        let args = vec![
            "-g".to_string(),
            shot::grim_geometry(x, y, side),
            path.to_string_lossy().to_string(),
        ];
        match run("grim", &args) {
            Ok(out) if out.ok => {
                self.status = format!("Cover → {}", path.display());
                Some(path)
            }
            Ok(out) => {
                self.status = format!("Cover screenshot: grim failed — {}", out.stderr.trim());
                None
            }
            Err(e) => {
                self.status = format!("Cover screenshot failed (is grim installed?): {e}");
                None
            }
        }
    }

    /// Ctrl+± : how solid the ground is, remembered across runs.
    pub fn step_opacity(&mut self, delta: f32) {
        self.config.step_opacity(delta);
        let _ = self.config.save(&self.void_dir);
        self.status = format!("Opacity {:.0}%", self.config.opacity * 100.0);
    }

    /// Ctrl+0 in F1: copy a random line from a random file in the void into the
    /// entry, the scratch excluded — the scratch is where lines LAND, so pulling
    /// from it would just recirculate what you were already looking at.
    /// A port of `show_random_line_from_random_file`. Only ever copies.
    pub fn random_line_from_void(&mut self) {
        let mut files: Vec<PathBuf> = Vec::new();
        collect_txt_files(&self.void_dir, &mut files);
        files.retain(|f| {
            f.file_name()
                .map(|n| !library::is_portal(&n.to_string_lossy()))
                .unwrap_or(false)
        });
        if files.is_empty() {
            self.status = "Nothing in the void to pull from".into();
            return;
        }
        library::shuffle(&mut files);
        for path in files {
            let mut lines: Vec<String> = void::load_doc(&path)
                .lines
                .into_iter()
                .filter(|l| !l.trim().is_empty() && l.trim() != ".")
                .collect();
            if lines.is_empty() {
                continue;
            }
            library::shuffle(&mut lines);
            self.entry.set_text(&lines[0]);
            self.entry.home();
            return;
        }
        self.status = "Nothing in the void to pull from".into();
    }

    /// Ctrl+. in F1: a random line from THIS file, skipping whatever the entry
    /// already holds so the same line isn't handed back. A port of
    /// `show_random_line_from_current_file`.
    pub fn random_line_from_here(&mut self) {
        let all: Vec<String> = void::load_doc(&self.current_file)
            .lines
            .into_iter()
            .filter(|l| !l.trim().is_empty() && l.trim() != ".")
            .collect();
        if all.is_empty() {
            self.status = "This file has nothing to pull from".into();
            return;
        }
        let current = self.entry.text().trim().to_string();
        let mut pool: Vec<String> = if !current.is_empty() && all.len() > 1 {
            all.iter().filter(|l| l.trim() != current).cloned().collect()
        } else {
            all.clone()
        };
        if pool.is_empty() {
            pool = all;
        }
        library::shuffle(&mut pool);
        self.entry.set_text(&pool[0]);
        self.entry.home();
    }




    /// Ctrl+Shift+F en F3: absorber los `0.txt` sueltos de subcarpetas de `I/`
    /// dentro del scratch de la raíz, y borrar las carpetas que queden vacías.
    /// Port de `_merge_zero_files`.
    ///
    /// Cada borrador que quedó tirado en una subcarpeta —los que deja sincronizar
    /// desde el teléfono, por ejemplo— vuelve al único scratch, separado por un
    /// punto para no pegarse con lo que ya había. El `0.txt` de la raíz nunca se
    /// toca a sí mismo.
    ///
    /// En el Python esto corre además al arrancar, en silencio. Acá es sólo
    /// explícito: absorber y borrar archivos sin que nadie lo haya pedido, cada
    /// vez que abrís, es mucho poder para algo que nadie miró.
    ///
    /// Devuelve (absorbidos, carpetas borradas).
    pub fn merge_stray_scratches(&mut self) -> io::Result<(usize, usize)> {
        let i_dir = self.void_dir.join("I");
        let root = self.scratch_path();
        let root_real = root.canonicalize().unwrap_or_else(|_| root.clone());

        let mut strays: Vec<PathBuf> = Vec::new();
        collect_txt_files(&i_dir, &mut strays);
        strays.retain(|p| {
            let is_zero = p
                .file_name()
                .and_then(|n| n.to_str())
                .is_some_and(|n| n.eq_ignore_ascii_case("0.txt"));
            let is_root = p.canonicalize().map(|c| c == root_real).unwrap_or(false);
            is_zero && !is_root
        });
        strays.sort();

        if strays.is_empty() {
            self.status = "Nada que juntar".into();
            return Ok((0, 0));
        }
        void::git_commit(&self.void_dir, "I/", &format!("merge-zero {}", void::timestamp()));

        let before = void::load_doc(&root).lines;
        let mut after = before.clone();
        let mut absorbed = 0usize;
        for stray in &strays {
            let Ok(text) = std::fs::read_to_string(stray) else {
                continue;
            };
            let lines: Vec<String> = text
                .lines()
                .map(|l| l.trim_end().to_string())
                .filter(|l| !l.trim().is_empty())
                .collect();
            after.push(".".to_string());
            after.extend(lines);
            if std::fs::remove_file(stray).is_ok() {
                absorbed += 1;
            }
        }
        if absorbed == 0 {
            return Ok((0, 0));
        }
        void::atomic_write(&root, &after, true)?; // deja un .bak
        self.undo.record(root.clone(), before, after.clone(), None);
        if self.current_file == root {
            self.ring = LineRing::new(after);
            self.sync_entry();
        }

        // Las carpetas que quedaron vacías se van; `I/` nunca.
        let mut removed_dirs = 0usize;
        for stray in &strays {
            if let Some(parent) = stray.parent() {
                if parent != i_dir && std::fs::remove_dir(parent).is_ok() {
                    removed_dirs += 1;
                }
            }
        }
        self.status = format!("{absorbed} borrador(es) al scratch");
        Ok((absorbed, removed_dirs))
    }
    // ── El lado O/: el corpus que se lee ───────────────────────────────────────

    /// Dónde vive el corpus. Es un enlace a otro disco, y se lee, nunca se escribe.
    pub fn o_dir(&self) -> PathBuf {
        self.void_dir.join("O")
    }

    /// Cargar el working set y la lista de libros, una sola vez por sesión.
    fn ensure_corpus_loaded(&mut self) {
        if self.o_books.is_empty() {
            self.o_books = corpus::load_cache(&self.void_dir);
        }
        if self.ws.books.is_empty() {
            self.ws = corpus::WorkingSet::load(&self.o_dir());
        }
    }

    /// F7: el working set, un separador antes de cada ranura.
    pub fn enter_o_browser(&mut self) {
        self.ensure_corpus_loaded();
        if self.ws.books.is_empty() {
            self.ws = corpus::WorkingSet::load(&self.o_dir());
        }
        let n = self.ws.browser_entries().len();
        if self.ws_index == 0 || self.ws_index >= n {
            self.ws_index = 1.min(n.saturating_sub(1));
        }
    }

    /// Qué ranura está señalando el cursor de F7, si no está sobre un separador.
    pub fn ws_current_slot(&self) -> Option<usize> {
        self.ws.slot_at(self.ws_index)
    }

    /// Mover el cursor de F7, saltando los separadores: lo que interesa son los
    /// libros, no las marcas entre ellos.
    pub fn ws_move(&mut self, delta: isize) {
        let n = self.ws.browser_entries().len() as isize;
        if n <= 1 {
            return;
        }
        let mut i = self.ws_index as isize;
        for _ in 0..n {
            i = (i + delta).rem_euclid(n);
            if i % 2 == 1 {
                break; // las impares son ranuras
            }
        }
        self.ws_index = i as usize;
    }

    /// Tab en F7: llenar la ranura con un libro al azar que no esté ya en otra.
    pub fn ws_tab(&mut self) {
        self.ensure_corpus_loaded();
        let Some(slot) = self.ws_current_slot() else { return };
        if self.o_books.is_empty() {
            self.status = "No hay cache de O/ — nada para sortear".into();
            return;
        }
        let books = self.o_books.clone();
        match self.ws.randomize(slot, &books) {
            Some(name) => {
                let _ = self.ws.save(&self.o_dir());
                self.status = corpus::clean_book_title(&name);
            }
            None => self.status = "No quedan libros sin usar".into(),
        }
    }

    /// Shift+Enter en F7: una ranura vacía nueva, con el cursor encima.
    pub fn ws_add_slot(&mut self) {
        let at = self.ws.add_slot(self.ws_current_slot());
        let _ = self.ws.save(&self.o_dir());
        self.ws_index = self.ws.ring_index_of(at);
        self.status = format!("{} ranura(s)", self.ws.books.len());
    }

    /// Ctrl+Delete en F7: sacar la ranura, salvo que sea el libro abierto en F6.
    pub fn ws_remove_slot(&mut self) {
        let Some(slot) = self.ws_current_slot() else { return };
        let open = (!self.o_file.is_empty()).then(|| self.o_file.clone());
        match self.ws.remove_slot(slot, open.as_deref()) {
            Some(next) => {
                let _ = self.ws.save(&self.o_dir());
                self.ws_index = self.ws.ring_index_of(next);
                self.status = format!("{} ranura(s)", self.ws.books.len());
            }
            None => self.status = "Ese libro está abierto en el lector".into(),
        }
    }

    /// Enter en F7: abrir esa ranura en el lector, donde la habías dejado.
    pub fn open_o_book(&mut self) -> bool {
        let Some(slot) = self.ws_current_slot() else { return false };
        let name = self.ws.books[slot].path.clone();
        if name.is_empty() {
            return false; // una ranura vacía no abre nada; primero Tab
        }
        let path = self.o_dir().join(&name);
        let Ok(text) = std::fs::read_to_string(&path) else {
            self.status = "No se pudo leer ese libro".into();
            return false;
        };
        let lines: Vec<String> = text
            .lines()
            .map(|l| l.trim_end().to_string())
            .filter(|l| !l.trim().is_empty())
            .collect();
        self.o_ring = LineRing::new(if lines.is_empty() { vec![".".to_string()] } else { lines });
        let pos = self.ws.position_of(&name);
        self.o_ring.index = pos.min(self.o_ring.lines.len().saturating_sub(1));
        self.o_file = name;
        true
    }

    /// F6: el lector. Si no hay libro cargado, trae el de la ranura actual.
    pub fn enter_o_reader(&mut self) {
        self.ensure_corpus_loaded();
        if self.o_file.is_empty() {
            self.open_o_book();
        }
    }

    /// Guardar por dónde ibas leyendo. Al salir de F6.
    pub fn save_o_position(&mut self) {
        if self.o_file.is_empty() {
            return;
        }
        let (file, idx) = (self.o_file.clone(), self.o_ring.index);
        self.ws.save_position(&file, idx);
        let _ = self.ws.save(&self.o_dir());
    }

    /// Moverse por el libro. Corta la voz, como toda navegación.
    pub fn o_navigate(&mut self, delta: isize) {
        self.tts.cut();
        self.o_ring.move_by(delta);
    }

    /// F8: el oráculo. Una línea al azar del corpus, nueva en cada visita y en
    /// cada movimiento — no es una lista para recorrer, es una tirada.
    pub fn refresh_oracle(&mut self) {
        self.ensure_corpus_loaded();
        let dir = self.o_dir();
        let books = self.o_books.clone();
        self.oracle = corpus::oracle_line(&dir, &books);
    }

    /// Enter en F8: quedarse con la línea, metiéndola en el documento activo
    /// debajo de donde estabas, y tirar otra.
    pub fn keep_oracle_line(&mut self) -> io::Result<()> {
        let line = self.oracle.trim().to_string();
        if line.is_empty() || line == "..." {
            return Ok(());
        }
        let at = (self.ring.index + 1).min(self.ring.lines.len());
        self.ring.lines.insert(at, line);
        self.ring.index = at;
        self.save()?;
        self.refresh_oracle();
        Ok(())
    }
    // ── Ctrl+T: la voz ─────────────────────────────────────────────────────────

    /// Lo que le toca leer a cada vista, o nada si esta vista no habla.
    /// F4 no habla a propósito: es una página para mirar, no para escuchar.
    fn tts_current_text(&self) -> Option<String> {
        match self.view {
            View::F1 => Some(self.ring.current().to_string()),
            View::F2 => Some(self.ring.current().to_string()),
            View::F5 => f5::units(&self.ring.lines).into_iter().find_map(|u| match u {
                f5::Unit::Para { ordinal, text } if ordinal == self.para_idx => Some(text),
                _ => None,
            }),
            // F4 no habla: es una pagina para mirar. F3/F9/F10 tampoco.
            _ => None,
        }
    }

    /// Ctrl+T: prender o apagar. Al prender, empieza por donde estás parado.
    pub fn tts_toggle(&mut self) {
        if self.tts.toggle() {
            self.status = "Voz encendida".into();
            self.tts_speak_current();
        } else {
            self.status = "Voz apagada".into();
        }
    }

    fn tts_speak_current(&mut self) {
        if !self.tts.active {
            return;
        }
        if let Some(text) = self.tts_current_text() {
            let dir = self.void_dir.clone();
            self.tts.speak(&dir, &text);
        }
    }

    /// Llamado cada frame: cuando la línea terminó de sonar, avanza a la
    /// siguiente. Sólo en F2, que es la vista que lee seguido; en F1 y F5 se
    /// dice lo que hay y se calla, como en el Python.
    pub fn tts_poll(&mut self) {
        if !self.tts.active || self.tts.is_speaking() {
            return;
        }
        if self.view != View::F2 {
            return;
        }
        // Avanzar a la próxima línea con texto, sin quedarse en los puntos.
        let n = self.ring.lines.len();
        if n == 0 {
            return;
        }
        for _ in 0..n {
            self.ring.move_by(1);
            if crate::tts::is_speakable(self.ring.current()) {
                break;
            }
        }
        self.sync_entry();
        self.tts_speak_current();
    }

    // ── Ctrl+F2/F3/F4: apuntar Voider a otro lado ──────────────────────────────

    /// Abrir el navegador. Arranca donde tiene sentido para cada cosa: el
    /// archivo activo y la carpeta del libro, en `I/`; el void, un nivel arriba
    /// del actual, que es donde estarían los otros.
    pub fn open_browser(&mut self, purpose: browse::Purpose) {
        let start = match purpose {
            browse::Purpose::ActiveFile | browse::Purpose::BookDir => self.void_dir.join("I"),
            // Covers are kept in `covers/` (Shift+F12 puts them there); with none yet,
            // the void itself is the next best place to look.
            browse::Purpose::Cover => self.void_dir.join("covers"),
            browse::Purpose::VoidDir => self
                .void_dir
                .parent()
                .map(Path::to_path_buf)
                .unwrap_or_else(|| self.void_dir.clone()),
        };
        let start = if start.is_dir() { start } else { self.void_dir.clone() };
        self.browser = Some(browse::Browser::open(&start, purpose));
    }

    pub fn cancel_browser(&mut self) {
        if self.browser.take().is_some() {
            self.status = "Cancelado".into();
        }
    }

    /// Enter: entrar a la carpeta, o quedarse con lo señalado.
    ///
    /// Buscando un archivo, una carpeta se abre y un `.txt` se elige. Buscando
    /// una carpeta hay que distinguir: `..` y las carpetas de adentro NAVEGAN,
    /// y lo que se elige es la carpeta donde uno está — por eso confirmar una
    /// carpeta es Shift+Enter, no Enter. Si no, no habría forma de entrar a una
    /// carpeta sin elegirla.
    pub fn browser_enter(&mut self, confirm_dir: bool) -> io::Result<()> {
        let Some(browser) = &mut self.browser else {
            return Ok(());
        };
        if browser.looking == browse::Looking::Dir && !confirm_dir {
            browser.descend();
            return Ok(());
        }
        if matches!(browser.looking, browse::Looking::File | browse::Looking::Image) {
            if let Some(entry) = browser.current() {
                if entry.is_dir {
                    browser.descend();
                    return Ok(());
                }
            }
        }
        let Some(chosen) = browser.selection() else {
            return Ok(());
        };
        let purpose = browser.purpose;
        self.browser = None;
        self.apply_choice(purpose, chosen)
    }

    fn apply_choice(&mut self, purpose: browse::Purpose, chosen: PathBuf) -> io::Result<()> {
        match purpose {
            browse::Purpose::ActiveFile => {
                self.set_active_file(chosen.clone());
                self.status = format!("Activo: {}", file_title(&chosen));
                self.switch_to(View::F2);
            }
            // La carpeta del libro es `I/`, así que elegirla es elegir su padre
            // como void. Es lo mismo que hace el Python, que mueve book_dir y
            // deduce el resto.
            browse::Purpose::BookDir => {
                let void = if chosen.file_name().is_some_and(|n| n == "I") {
                    chosen.parent().map(Path::to_path_buf).unwrap_or(chosen.clone())
                } else {
                    chosen.clone()
                };
                self.retarget_void(void)?;
            }
            browse::Purpose::VoidDir => self.retarget_void(chosen)?,
            browse::Purpose::Cover => self.cover_chosen(chosen)?,
        }
        Ok(())
    }

    /// Apuntar a otro void entero: otra biblioteca, otro scratch, otra config.
    /// Nada del anterior se toca — sólo se deja de mirarlo.
    fn retarget_void(&mut self, dir: PathBuf) -> io::Result<()> {
        if !dir.is_dir() {
            self.status = "Esa carpeta no existe".into();
            return Ok(());
        }
        let _ = std::fs::create_dir_all(dir.join("I"));
        self.void_dir = dir;
        self.config = Config::load(&self.void_dir);
        self.typewriter = self.config.typewriter;
        self.show_title = self.config.show_title;
        self.library = Library::load(&self.void_dir);
        self.ws = corpus::WorkingSet::default();
        self.o_books.clear();
        self.o_file.clear();
        let scratch = self.scratch_path();
        if !scratch.exists() {
            void::atomic_write(&scratch, &[".".to_string()], false)?;
        }
        self.set_active_file(scratch);
        self.undo.clear();
        self.status = format!("Void: {}", self.void_dir.display());
        self.switch_to(View::F1);
        Ok(())
    }
    // ── Ctrl+B: the copy that leaves the machine ───────────────────────────────

    /// Today, as the backup folder names it.
    fn backup_date(&self) -> String {
        let now = chrono::Local::now();
        format!("{:02}-{:02}-{:02}", now.year() % 100, now.month(), now.day())
    }

    /// Ctrl+B: find the drives and work out what a backup WOULD write, without
    /// writing any of it. Nothing touches the drive until `backup_confirm`.
    pub fn begin_backup(&mut self) {
        let drives = backup::detect_drives();
        let Some(first) = drives.first().cloned() else {
            self.status = "No external drive found — plug one in".into();
            return;
        };
        let plan = backup::plan(&self.void_dir, &first, &self.backup_date());
        self.status = plan.summary();
        self.backup_prompt = Some(BackupPrompt { drives, idx: 0, plan });
    }

    /// Several drives can be mounted at once; step between them, re-costing the
    /// backup for each, so the wrong one is never accepted by accident.
    pub fn backup_cycle_drive(&mut self, delta: isize) {
        let Some(prompt) = &self.backup_prompt else {
            return;
        };
        let n = prompt.drives.len();
        if n < 2 {
            return;
        }
        let idx = (prompt.idx as isize + delta).rem_euclid(n as isize) as usize;
        let dest = prompt.drives[idx].clone();
        let plan = backup::plan(&self.void_dir, &dest, &self.backup_date());
        self.status = plan.summary();
        if let Some(p) = &mut self.backup_prompt {
            p.idx = idx;
            p.plan = plan;
        }
    }

    pub fn cancel_backup(&mut self) {
        if self.backup_prompt.take().is_some() {
            self.status = "Backup cancelled".into();
        }
    }

    /// Accepted: commit the void first so nothing uncommitted is left behind,
    /// then write the copy. Returns how many files landed.
    pub fn backup_confirm(&mut self) -> io::Result<usize> {
        let Some(prompt) = self.backup_prompt.take() else {
            return Ok(0);
        };
        void::git_commit(
            &self.void_dir,
            ".",
            &format!("backup {}", void::timestamp()),
        );
        // Re-plan: the commit just changed .git, and that history is the point.
        let plan = backup::plan(
            &self.void_dir,
            &prompt.drives[prompt.idx],
            &self.backup_date(),
        );
        match backup::run(&self.void_dir, &plan) {
            Ok(n) => {
                self.status = format!(
                    "Backup: {n} archivos · {} → {}",
                    backup::human_bytes(plan.total_bytes()),
                    plan.dest().display()
                );
                Ok(n)
            }
            Err(e) => {
                self.status = format!("Backup failed: {e}");
                Err(e)
            }
        }
    }

    // ── F9: the active file as prose ───────────────────────────────────────────

    /// Fill the prose box from the ring: each dot group becomes one paragraph,
    /// its lines joined back into flowing text, paragraphs separated by a blank
    /// line. Entering is never a change — `prose_dirty` starts false, so simply
    /// looking at a file and leaving writes nothing.
    pub fn enter_prose_editor(&mut self) {
        self.prose = reformat::lines_to_paragraphs(&self.ring.lines).join("\n\n");
        self.prose_caret = Some(f5::f9_entry_offset(&self.ring.lines, self.ring.index));
        self.prose_dirty = false;
    }

    /// Leaving F9 (or Ctrl+S): put the prose back into the dot model and write
    /// it. Untouched prose is left alone entirely — no write, no `.bak`, no undo
    /// step — so F9 is safe to browse in.
    ///
    /// The prose goes through `reformat_prose`, so paragraphs become dot groups
    /// and sentences become their own lines: the file comes back in Voider's
    /// format however freely it was typed.
    pub fn prose_save(&mut self) -> io::Result<()> {
        if !self.prose_dirty {
            return Ok(());
        }
        if self.load_failed {
            self.status = "Save blocked: the active file failed to load".into();
            return Ok(());
        }
        let before = self.ring.lines.clone();
        let after = reformat::reformat_prose(&self.prose);
        self.prose_dirty = false;
        if after == before {
            self.status = "Prose unchanged".into();
            return Ok(());
        }
        if void::rescue_on_large_shrink(&self.current_file, &after) {
            self.status = "Large shrink — kept a .rescue copy".into();
        }
        void::atomic_write(&self.current_file, &after, true)?; // keeps a .bak
        self.ring.lines = after.clone();
        self.ring.index = self.ring.index.min(self.ring.lines.len() - 1);
        self.sync_entry();
        self.undo.record(self.current_file.clone(), before, after, None);
        self.status = "Prose saved".into();
        Ok(())
    }

    /// Replace the prose being edited, marking it dirty when it really changed.
    pub fn set_prose(&mut self, text: &str) {
        if self.prose != text {
            self.prose = text.to_string();
            self.prose_dirty = true;
        }
    }

    // ── Search (Ctrl+F in F2 / F3) ───────────────────────────────────────────────

    fn matching_doc_lines(&self, query: &str) -> Vec<usize> {
        let q = query.trim().to_lowercase();
        self.ring
            .lines
            .iter()
            .enumerate()
            .filter(|(_, l)| l.as_str() != "." && (q.is_empty() || l.to_lowercase().contains(&q)))
            .map(|(i, _)| i)
            .collect()
    }

    fn matching_library_entries(&self, query: &str) -> Vec<usize> {
        let q = query.trim().to_lowercase();
        self.library
            .entries
            .iter()
            .enumerate()
            .filter(|(_, e)| {
                !library::is_separator(e)
                    && (q.is_empty() || library::display_name(e).to_lowercase().contains(&q))
            })
            .map(|(i, _)| i)
            .collect()
    }

    /// Ctrl+F in F2: open the search bar, starting on every non-dot line.
    pub fn open_f2_search(&mut self) {
        if self.f2_search.is_some() {
            return;
        }
        let saved_index = self.ring.index;
        let matches = self.matching_doc_lines("");
        let highlight = matches.iter().position(|&i| i == saved_index).unwrap_or(0);
        self.f2_search = Some(SearchState {
            query: TextLine::new(""),
            matches,
            highlight,
            saved_index,
        });
    }

    /// Type into the F2 search query, re-filtering as you go.
    pub fn f2_search_type(&mut self, text: &str) {
        let Some(search) = &mut self.f2_search else {
            return;
        };
        search.query.insert(text);
        let query = search.query.text();
        let matches = self.matching_doc_lines(&query);
        let search = self.f2_search.as_mut().unwrap();
        search.matches = matches;
        search.highlight = 0;
    }

    pub fn f2_search_backspace(&mut self) {
        let Some(search) = &mut self.f2_search else {
            return;
        };
        search.query.backspace();
        let query = search.query.text();
        let matches = self.matching_doc_lines(&query);
        let search = self.f2_search.as_mut().unwrap();
        search.matches = matches;
        search.highlight = 0;
    }

    /// Up/Down while searching: move the highlight, clamped — search never wraps.
    pub fn f2_search_move(&mut self, delta: isize) {
        let Some(search) = &mut self.f2_search else {
            return;
        };
        if search.matches.is_empty() {
            return;
        }
        let n = search.matches.len() as isize;
        search.highlight = (search.highlight as isize + delta).clamp(0, n - 1) as usize;
    }

    /// Enter: jump the ring to the highlighted match and close the search.
    pub fn f2_search_confirm(&mut self) {
        let Some(search) = self.f2_search.take() else {
            return;
        };
        if let Some(&idx) = search.matches.get(search.highlight) {
            self.ring.index = idx;
        }
        self.sync_entry();
    }

    /// Escape: close the search, the ring back where it was.
    pub fn f2_search_cancel(&mut self) {
        let Some(search) = self.f2_search.take() else {
            return;
        };
        self.ring.index = search.saved_index;
        self.sync_entry();
    }

    /// Ctrl+F in F3: open the search bar, starting on every chapter (no dots).
    pub fn open_f3_search(&mut self) {
        if self.f3_search.is_some() {
            return;
        }
        let saved_index = self.library.index;
        let matches = self.matching_library_entries("");
        let highlight = matches.iter().position(|&i| i == saved_index).unwrap_or(0);
        self.f3_search = Some(SearchState {
            query: TextLine::new(""),
            matches,
            highlight,
            saved_index,
        });
    }

    pub fn f3_search_type(&mut self, text: &str) {
        let Some(search) = &mut self.f3_search else {
            return;
        };
        search.query.insert(text);
        let query = search.query.text();
        let matches = self.matching_library_entries(&query);
        let search = self.f3_search.as_mut().unwrap();
        search.matches = matches;
        search.highlight = 0;
    }

    pub fn f3_search_backspace(&mut self) {
        let Some(search) = &mut self.f3_search else {
            return;
        };
        search.query.backspace();
        let query = search.query.text();
        let matches = self.matching_library_entries(&query);
        let search = self.f3_search.as_mut().unwrap();
        search.matches = matches;
        search.highlight = 0;
    }

    pub fn f3_search_move(&mut self, delta: isize) {
        let Some(search) = &mut self.f3_search else {
            return;
        };
        if search.matches.is_empty() {
            return;
        }
        let n = search.matches.len() as isize;
        search.highlight = (search.highlight as isize + delta).clamp(0, n - 1) as usize;
    }

    /// Enter: highlight the matched chapter in the library and close the search.
    pub fn f3_search_confirm(&mut self) {
        let Some(search) = self.f3_search.take() else {
            return;
        };
        if let Some(&idx) = search.matches.get(search.highlight) {
            self.library.index = idx;
        }
    }

    pub fn f3_search_cancel(&mut self) {
        let Some(search) = self.f3_search.take() else {
            return;
        };
        self.library.index = search.saved_index;
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

    /// Chapters a paragraph can be sent to: never a separator or the portal. The
    /// ACTIVE chapter is listed too, as in F2's catalogue, so a stray Enter lands
    /// on the file you are in (a no-op) rather than on its neighbour.
    pub fn picker_entries(&self) -> Vec<String> {
        self.library
            .entries
            .iter()
            .filter(|e| !library::is_separator(e) && !library::is_portal(e))
            .cloned()
            .collect()
    }

    /// The rows the catalogue DRAWS and which one is lit. A `·` row sits between
    /// books, as the dots do in F3; it is shown but never chosen, so the lit row
    /// is the row of the chosen DESTINATION, not its number. A dot with nothing
    /// before it, or nothing after it, or right after another, separates nothing
    /// and is dropped.
    pub fn picker_rows(&self) -> (Vec<String>, usize) {
        let mut rows: Vec<String> = Vec::new();
        let mut lit = 0;
        let mut dest = 0;
        for e in &self.library.entries {
            if library::is_separator(e) {
                if rows.last().is_some_and(|r| r != "·") {
                    rows.push("·".to_string());
                }
            } else if !library::is_portal(e) {
                if dest == self.picker_idx {
                    lit = rows.len();
                }
                rows.push(library::display_name(e));
                dest += 1;
            }
        }
        if rows.last().is_some_and(|r| r == "·") {
            rows.pop();
        }
        (rows, lit)
    }

    /// Open the catalogue parked on the active chapter, so confirming without
    /// moving sends nothing anywhere.
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
        if let Some(i) = entries.iter().position(|e| *e == name.to_string_lossy()) {
            return i;
        }
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
    /// Lo que Alt+→ se llevaría desde donde está el cursor en F2, y con qué
    /// queda el archivo. Sobre un punto, el párrafo que abre (y el punto); sobre
    /// una línea, esa línea sola.
    ///
    /// Es la misma dualidad que F2 ya tiene en todos lados — Alt+↑ mueve el
    /// párrafo sobre un punto y la línea sobre una línea, Ctrl+C copia lo mismo.
    pub fn doc_send_scope(&self) -> Option<(Vec<String>, Vec<String>)> {
        let lines = &self.ring.lines;
        let i = self.ring.index;
        if lines.is_empty() {
            return None;
        }
        if lines[i] == "." {
            // El párrafo que abre este punto: hasta el próximo punto o el final.
            let mut end = i + 1;
            while end < lines.len() && lines[end] != "." {
                end += 1;
            }
            let taken: Vec<String> = lines[i + 1..end].to_vec();
            if taken.iter().all(|l| l.trim().is_empty()) {
                return None; // un punto sin párrafo debajo no manda nada
            }
            let mut rest: Vec<String> = lines[..i].to_vec();
            rest.extend_from_slice(&lines[end..]);
            Some((taken, tidy_after_send(rest)))
        } else {
            if lines[i].trim().is_empty() {
                return None;
            }
            let taken = vec![lines[i].clone()];
            let mut rest: Vec<String> = lines[..i].to_vec();
            rest.extend_from_slice(&lines[i + 1..]);
            Some((taken, tidy_after_send(rest)))
        }
    }

    /// Alt+→ en F2: desplegar la biblioteca al costado para elegir a dónde va.
    /// Sobre un punto vacío o una línea en blanco no hay nada que mandar, así
    /// que no se abre — mejor que abrirse y después no hacer nada.
    pub fn doc_open_picker(&mut self) {
        if self.doc_send_scope().is_none() {
            self.status = "Nada para enviar desde acá".into();
            return;
        }
        if self.library.entries.is_empty() {
            self.library = Library::load(&self.void_dir);
        }
        self.picker_idx = self.picker_start_idx();
        self.picker_open = true;
    }

    /// Mandar lo que el cursor señala al capítulo elegido.
    pub fn doc_send_to(&mut self, entry: &str) -> io::Result<bool> {
        let Some((taken, rest)) = self.doc_send_scope() else {
            return Ok(false);
        };
        let sent = self.append_to_chapter(entry, taken, rest, "doc-send")?;
        if sent {
            self.picker_open = false;
            self.sync_entry();
        }
        Ok(sent)
    }

    /// F5: mandar el párrafo donde está el cursor al capítulo elegido.
    pub fn send_para_to(&mut self, entry: &str) -> io::Result<bool> {
        let Some((para, rest)) = f5::take_para(&self.ring.lines, self.para_idx) else {
            return Ok(false);
        };
        let sent = self.append_to_chapter(entry, para, rest, "f5-send")?;
        if sent {
            let n = f5::para_count(&self.ring.lines);
            self.para_idx = if n == 0 { 0 } else { self.para_idx.min(n - 1) };
            self.picker_open = false;
        }
        Ok(sent)
    }

    /// Sacar `taken` de este archivo y agregarlo al final de `entry`, en UN solo
    /// paso de deshacer. Lo comparten F5 (que manda párrafos) y F2 (que manda un
    /// párrafo o una línea según dónde estés parado).
    ///
    /// El texto que llega se separa con un punto del que ya había, así entra
    /// como párrafo propio en vez de pegarse al último.
    fn append_to_chapter(
        &mut self,
        entry: &str,
        taken: Vec<String>,
        rest: Vec<String>,
        scope: &str,
    ) -> io::Result<bool> {
        let target = library::chapter_path(&self.void_dir, entry);
        if target == self.current_file {
            self.status = "Ese es este mismo archivo".into();
            return Ok(false);
        }
        if taken.is_empty() {
            return Ok(false);
        }
        void::git_commit(
            &self.void_dir,
            "I/",
            &format!("{scope} {}", void::timestamp()),
        );

        // El destino se lee crudo (sin el punto que load_doc sintetiza) para no
        // ir agregando uno en cada envío.
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
        combined.extend(taken);
        void::atomic_write(&target, &combined, false)?;

        self.ring.lines = rest;
        if self.ring.index >= self.ring.lines.len() {
            self.ring.index = self.ring.lines.len().saturating_sub(1);
        }
        // Los dos archivos se mueven como UN paso: deshacer devuelve el texto a
        // su origen y lo saca del destino a la vez.
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
        self.status = format!("→ {}", library::display_name(entry));
        Ok(true)
    }

    // ── F3: the library ───────────────────────────────────────────────────────

    /// Make `path` the active document, loading it into the ring.
    pub fn set_active_file(&mut self, path: impl Into<PathBuf>) {
        let path = path.into();
        let doc = void::load_doc(&path);
        let mut ring = LineRing::new(doc.lines);
        ring.index = restored_index(&self.void_dir, &path, ring.lines.len());
        self.current_file = path;
        self.ring = ring;
        self.load_failed = doc.read_failed;
        self.save_active_file();
    }

    /// Write the library index, telling the other instances it moved. Every
    /// library write goes through here so none of them can forget to.
    pub fn save_library(&mut self) -> io::Result<()> {
        self.library.save(&self.void_dir)?;
        let path = library::library_path(&self.void_dir);
        self.notify_saved(&path);
        Ok(())
    }

    fn notify_saved(&mut self, path: &Path) {
        if let Some(ipc) = &mut self.ipc {
            ipc.notify_saved(path);
        }
    }

    /// Take in anything the sibling instances announced since the last frame.
    pub fn poll_ipc(&mut self) {
        let Some(ipc) = &mut self.ipc else {
            return;
        };
        for path in ipc.poll() {
            self.on_saved_by_other(&path);
        }
    }

    /// Another instance wrote a file. If it's the one open here, or the library
    /// index, take its version — it is newer than ours by definition.
    pub fn on_saved_by_other(&mut self, path: &Path) {
        if same_file(path, &self.current_file) {
            self.reload_doc_from_other();
        } else if same_file(path, &library::library_path(&self.void_dir)) {
            self.reload_library_from_other();
        }
    }

    /// Re-read the active file after someone else changed it, staying as close
    /// to where the cursor was as the new length allows. The line being typed
    /// is left alone: it is not on disk yet, and losing it to a sibling's save
    /// is exactly the kind of theft this whole mechanism exists to prevent.
    pub fn reload_doc_from_other(&mut self) {
        let doc = void::load_doc(&self.current_file);
        if doc.read_failed {
            return;
        }
        let was = self.ring.index;
        self.ring = LineRing::new(doc.lines);
        self.ring.index = was.min(self.ring.lines.len().saturating_sub(1));
        self.load_failed = false;
        self.status = "Reloaded — another Voider saved this file".into();
    }

    /// Re-read the library after another instance reordered/renamed/deleted,
    /// keeping the cursor on the same entry BY NAME rather than by position.
    /// Deferred while this instance is naming something: an unfinished title is
    /// intent that isn't on disk anywhere, and must not be stomped.
    pub fn reload_library_from_other(&mut self) {
        if self.pending_new || self.pending_merge {
            return;
        }
        let selected = self.library.entries.get(self.library.index).cloned();
        self.library = Library::load(&self.void_dir);
        if let Some(name) = selected {
            self.library.index = self
                .library
                .position(&name)
                .unwrap_or_else(|| self.library.index.min(self.library.entries.len().saturating_sub(1)));
        }
        self.status = "Library reloaded — another Voider changed it".into();
    }

    /// Persist the ring's current position for the active file, so a restart
    /// puts the cursor back where it was. A port of `_save_last_line`.
    pub fn save_last_line(&self) {
        if let Some(name) = self.current_file.file_name().and_then(|n| n.to_str()) {
            position::save_last_line(&self.void_dir, name, self.ring.index);
        }
    }

    /// Alt+F4: quit cleanly. Voider takes every keypress itself, so the window
    /// manager's own close handling may never see this one; the position is kept
    /// and the window asked to close, rather than the process being killed.
    pub fn request_quit(&mut self) {
        self.save_last_line();
        self.quit_requested = true;
    }

    /// Remember which file is active, independent of which view is showing it.
    fn save_active_file(&mut self) {
        if let Some(name) = self.current_file.file_name().and_then(|n| n.to_str()) {
            self.config.active_file = Some(name.to_string());
            let _ = self.config.save(&self.void_dir);
        }
    }

    /// Remember the view to resume in, when it's one of the restorable ones.
    fn save_last_view(&mut self) {
        let Some(key) = self.view.key() else {
            return;
        };
        self.config.last_view = Some(key.to_string());
        let _ = self.config.save(&self.void_dir);
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
        // A name already taken — listed, or a file sitting on disk — never
        // shares that file: two rows behind one file edit each other. It steps
        // to "name-2", "name-3", ... like a merge does, and the original stays.
        let mut file = format!("{name}.txt");
        let mut path = library::chapter_path(&self.void_dir, &file);
        let mut k = 2;
        while path.exists() || self.library.position(&file).is_some() {
            file = format!("{name}-{k}.txt");
            path = library::chapter_path(&self.void_dir, &file);
            k += 1;
        }
        void::atomic_write(&path, &[".".to_string()], false)?;
        let at = self.library.index;
        self.library.insert_below(at, file);
        self.library.index = (at + 1).min(self.library.entries.len() - 1);
        self.save_library()?;
        Ok(Some(path))
    }

    /// Tab in F3: on a separator dot, shuffle that book's files (numbered titles
    /// keep their order, the rest scatter); on a title, jump to a random one.
    pub fn book_tab(&mut self) -> io::Result<()> {
        self.settle_pending()?;
        if library::is_separator(self.library.current()) {
            if library::shuffle_group(&mut self.library.entries, self.library.index) {
                self.save_library()?;
                self.status = "Shuffled".into();
            }
        } else {
            self.book_random();
        }
        Ok(())
    }

    /// Jump to a random real chapter — never a separator, never the portal.
    /// Ctrl+Shift+S in F3: split the HIGHLIGHTED chapter at its `/name` markers,
    /// without opening it first — a thin wrapper over `split_at_markers`, which
    /// does the real work, over whichever file the cursor happens to sit on.
    pub fn book_split_current(&mut self) -> io::Result<usize> {
        let cur = self.library.current();
        if library::is_separator(cur) || library::is_portal(cur) {
            return Ok(0);
        }
        let path = library::chapter_path(&self.void_dir, cur);
        if !path.exists() {
            return Ok(0);
        }
        self.set_active_file(path);
        self.split_at_markers()
    }

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
    /// by what's in the entry: a `/name` seal marker, then
    /// each chapter's lines, originals removed. Re-splitting (Ctrl+Shift+S) restores them.
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
            // The marker goes FIRST: it seals what is below it, so merge stays
            // the exact inverse of split.
            merged.push(format!("/{}", library::display_name(fname)));
            merged.extend(lines);
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
        self.save_library()?;
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
        // Navegar corta la voz y la deja apagada, para que no siga sola por
        // donde el lector ya no esta. Es el _tts_cut del Python.
        self.tts.cut();
        let at_end = self.entry.caret() == self.entry.len();
        self.doc_live_save()?;
        self.save_last_line();
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

    // ── Tab in F2: the same cut-up, contextual ──────────────────────────────────

    /// Tab in F2. The ring's index 0 is always the file's leading dot, never a
    /// paragraph's own: there, Tab shuffles the paragraphs' ORDER (each keeps
    /// its own line order). On any other dot it shuffles the LINES within that
    /// one paragraph. On a content line it inserts a random `I/` fragment.
    pub fn doc_tab(&mut self) -> io::Result<()> {
        if self.ring.lines.is_empty() {
            return Ok(());
        }
        if self.ring.index == 0 {
            self.shuffle_paragraph_order()
        } else if self.ring.current() == "." {
            self.shuffle_para_lines()
        } else {
            self.insert_random_i_fragment()
        }
    }

    fn shuffle_paragraph_order(&mut self) -> io::Result<()> {
        let (_, mut paras) = paragraphs::from_lines(&self.ring.lines);
        if paras.len() < 2 {
            return Ok(());
        }
        library::shuffle(&mut paras);
        self.ring.lines = paragraphs::to_lines(&paras);
        self.ring.index = 0;
        self.sync_entry();
        self.save()
    }

    fn shuffle_para_lines(&mut self) -> io::Result<()> {
        let Some(k) = paragraphs::para_at_dot(&self.ring.lines, self.ring.index) else {
            return Ok(());
        };
        let (_, mut paras) = paragraphs::from_lines(&self.ring.lines);
        if paras[k].len() < 2 {
            return Ok(());
        }
        library::shuffle(&mut paras[k]);
        let dot_idx = paragraphs::dot_line_index(k, &paras);
        self.ring.lines = paragraphs::to_lines(&paras);
        self.ring.index = dot_idx;
        self.sync_entry();
        self.save()
    }

    /// A random non-empty, non-dot line from a random `.txt` under `dir`
    /// (walked recursively), never from `exclude`. Read-only — this is a copy.
    pub fn random_line_from_dir(&self, dir: &Path, exclude: Option<&Path>) -> Option<String> {
        let mut files: Vec<PathBuf> = Vec::new();
        collect_txt_files(dir, &mut files);
        if let Some(ex) = exclude {
            files.retain(|f| f != ex);
        }
        library::shuffle(&mut files);
        for path in files {
            let mut lines: Vec<String> = void::load_doc(&path)
                .lines
                .into_iter()
                .filter(|l| !l.trim().is_empty() && l.trim() != ".")
                .collect();
            if !lines.is_empty() {
                library::shuffle(&mut lines);
                return lines.into_iter().next();
            }
        }
        None
    }

    /// Tab over a content line: insert a random `I/` fragment at the caret. A
    /// trailing dot is dropped, and a capital is lowered unless it lands at the
    /// very start of the line. Landing right after a fragment Tab just
    /// inserted re-rolls it in place, rather than piling another one on.
    fn insert_random_i_fragment(&mut self) -> io::Result<()> {
        let i_dir = self.void_dir.join("I");
        let Some(line) = self.random_line_from_dir(&i_dir, Some(&self.current_file)) else {
            self.status = "No I/ lines to pull".into();
            return Ok(());
        };
        self.insert_fragment(&line)
    }

    /// Shift+Tab sobre una línea en F2: lo mismo, pero trayendo del corpus — de
    /// los libros que vos elegiste para el working set, no de tu propio libro.
    /// Port de `_doc_insert_ws_line`.
    ///
    /// (En el Python la señal se llama `altTabPressed` y su comentario dice
    /// "Alt+Tab", pero se emite con `Key_Backtab`, que es Shift+Tab. El nombre
    /// miente; la tecla real es la que está acá. La tabla de ayuda del Python
    /// dice Shift+Tab, y esta vez la que tiene razón es la ayuda.)
    pub fn insert_random_ws_fragment(&mut self) -> io::Result<()> {
        self.ensure_corpus_loaded();
        let Some(line) = self.random_line_from_working_set() else {
            self.status = "No hay libros en el working set (F7)".into();
            return Ok(());
        };
        self.insert_fragment(&line)
    }

    /// Una línea al azar de los libros del working set. Nunca de una ranura
    /// vacía, y si un libro no se puede leer se pasa al siguiente.
    pub fn random_line_from_working_set(&mut self) -> Option<String> {
        let mut filled: Vec<String> = self
            .ws
            .books
            .iter()
            .filter(|b| !b.is_empty())
            .map(|b| b.path.clone())
            .collect();
        if filled.is_empty() {
            return None;
        }
        library::shuffle(&mut filled);
        let o_dir = self.o_dir();
        for name in filled {
            let Ok(text) = std::fs::read_to_string(o_dir.join(&name)) else {
                continue;
            };
            let mut lines: Vec<&str> = text
                .lines()
                .map(str::trim)
                .filter(|l| !l.is_empty() && *l != ".")
                .collect();
            if lines.is_empty() {
                continue;
            }
            library::shuffle(&mut lines);
            return Some(lines[0].to_string());
        }
        None
    }

    /// Meter un fragmento en la línea que se está editando: sin el punto final,
    /// en minúscula salvo que caiga al principio, y reemplazando el fragmento
    /// anterior si el cursor sigue donde lo dejó — así repetir la tecla vuelve a
    /// sortear en vez de apilar.
    fn insert_fragment(&mut self, line: &str) -> io::Result<()> {
        let mut fragment = line.trim_end_matches('.').to_string();
        let (start, end) = match self.pending_fragment {
            Some((idx, s, e)) if idx == self.ring.index && self.entry.caret() == e => (s, e),
            _ => (self.entry.caret(), self.entry.caret()),
        };
        if start > 0 {
            if let Some(first) = fragment.chars().next() {
                if first.is_uppercase() {
                    let lowered: String = first.to_lowercase().collect();
                    fragment = lowered + &fragment[first.len_utf8()..];
                }
            }
        }
        let frag_len = fragment.chars().count();
        self.entry.replace_range(start, end, &fragment);
        self.pending_fragment = Some((self.ring.index, start, start + frag_len));
        self.doc_live_save()
    }

    /// Ctrl+C with nothing selected: copy the contextual unit. F2: the current
    /// line, or — sitting on a dot — the paragraph that follows it. F3: the
    /// highlighted chapter's text under its `── TITLE ──` heading, or — sitting on
    /// a dot — the whole book below it, each chapter titled and joined by a dot
    /// separator, the scratch portal
    /// skipped. Any other view copies nothing.
    pub fn smart_copy(&self) -> Option<String> {
        match self.view {
            View::F2 => {
                if self.ring.lines.is_empty() {
                    return None;
                }
                if self.ring.current() == "." {
                    let n = self.ring.lines.len();
                    let mut para = Vec::new();
                    let mut i = self.ring.index + 1;
                    while i < n && self.ring.lines[i] != "." {
                        para.push(self.ring.lines[i].clone());
                        i += 1;
                    }
                    if para.is_empty() { None } else { Some(para.join("\n")) }
                } else {
                    Some(self.ring.current().to_string())
                }
            }
            View::F3 => {
                let entries = &self.library.entries;
                let n = entries.len();
                if n == 0 {
                    return None;
                }
                if library::is_separator(self.library.current()) {
                    let mut parts = Vec::new();
                    let mut i = (self.library.index + 1) % n;
                    for _ in 0..n.saturating_sub(1) {
                        let fname = &entries[i];
                        if library::is_separator(fname) {
                            break;
                        }
                        if !library::is_portal(fname) {
                            let path = library::chapter_path(&self.void_dir, fname);
                            if let Ok(text) = std::fs::read_to_string(&path) {
                                parts.push(titled_chapter(fname, &text));
                            }
                        }
                        i = (i + 1) % n;
                    }
                    if parts.is_empty() { None } else { Some(parts.join("\n.\n")) }
                } else {
                    let name = self.library.current();
                    let path = library::chapter_path(&self.void_dir, name);
                    std::fs::read_to_string(&path)
                        .ok()
                        .map(|t| titled_chapter(name, &t))
                }
            }
            _ => None,
        }
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
            self.save_library()?;
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
    /// overwritten. A marker seals what is BELOW it, down to the next one; what
    /// comes before the first marker stays in the file, and if that remainder is empty the emptied container is removed from the library.
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
        self.save_library()?;

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

    /// Ctrl+Shift+D in F2: dispatch paragraphs tagged with a `/name` marker.
    ///
    /// A `/name` line sends the paragraph directly above it (everything back to
    /// the preceding `.`, or the start of the file) to `I/name.txt`, appending
    /// with a `.` separator if the file already has text. `/` alone is
    /// timestamped. The paragraph and its marker leave the ring; consecutive
    /// separators left behind collapse to one. Untagged paragraphs never move —
    /// this is the surgical sibling of `split_at_markers`, which seals
    /// EVERYTHING below a marker into a new chapter.
    pub fn dispatch_paragraphs(&mut self) -> io::Result<usize> {
        let lines = self.ring.lines.clone();
        let i_dir = self.void_dir.join("I");

        let mut dispatched: std::collections::HashSet<usize> = std::collections::HashSet::new();
        let mut targets: Vec<(PathBuf, Vec<String>, Vec<String>)> = Vec::new();

        for (idx, line) in lines.iter().enumerate() {
            if !line.starts_with('/') {
                continue;
            }
            let mut name = line.trim_start_matches('/').trim().to_string();
            if name.is_empty() {
                name = chrono::Local::now().format("%Y-%m-%d_%H%M%S").to_string();
            }
            let dest = i_dir.join(format!("{name}.txt"));

            let mut para_indices: Vec<usize> = Vec::new();
            let mut j = idx as isize - 1;
            while j >= 0 && lines[j as usize] != "." {
                para_indices.push(j as usize);
                j -= 1;
            }
            para_indices.reverse();
            dispatched.insert(idx);
            if para_indices.is_empty() {
                continue;
            }
            let para: Vec<String> = para_indices.iter().map(|&k| lines[k].clone()).collect();
            dispatched.extend(para_indices.iter().copied());

            let slot = targets.iter().position(|(p, _, _)| *p == dest).unwrap_or_else(|| {
                let before = if dest.exists() {
                    std::fs::read_to_string(&dest)
                        .map(|t| t.lines().map(|l| l.trim_end().to_string()).collect())
                        .unwrap_or_default()
                } else {
                    Vec::new()
                };
                targets.push((dest.clone(), before.clone(), before));
                targets.len() - 1
            });
            let after = &mut targets[slot].2;
            if !after.is_empty() {
                after.push(".".to_string());
            }
            after.extend(para);
        }

        if dispatched.is_empty() {
            return Ok(0);
        }

        void::git_commit(&self.void_dir, "I/", &format!("dispatch {}", void::timestamp()));

        let mut changes: Vec<undo::FileChange> = Vec::new();
        for (path, before, after) in &targets {
            void::atomic_write(path, after, false)?;
            changes.push(undo::FileChange {
                path: path.clone(),
                before: before.clone(),
                after: after.clone(),
            });
        }

        let source_before = lines.clone();
        let kept: Vec<String> = lines
            .iter()
            .enumerate()
            .filter(|(i, _)| !dispatched.contains(i))
            .map(|(_, l)| l.clone())
            .collect();
        let mut cleaned: Vec<String> = Vec::new();
        for l in kept {
            if l == "." && cleaned.last().is_some_and(|c: &String| c == ".") {
                continue;
            }
            cleaned.push(l);
        }
        if cleaned.is_empty() || cleaned == ["."] {
            cleaned = vec![".".to_string()];
        }
        void::atomic_write(&self.current_file, &cleaned, false)?;
        changes.push(undo::FileChange {
            path: self.current_file.clone(),
            before: source_before,
            after: cleaned.clone(),
        });

        self.ring.lines = cleaned;
        self.ring.index = self.ring.index.min(self.ring.lines.len() - 1);
        self.sync_entry();

        let n = targets.len();
        self.undo.record_transaction(changes, Some("dispatch".into()));
        self.status = format!("Dispatched to {n} file(s)");
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
        self.save_last_line();
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
        if let Some(r) = words::swap_block(
            &self.entry.text(),
            self.entry.caret(),
            self.entry.selection(),
            direction,
        ) {
            self.entry.set_text(&r.text);
            match r.selection {
                // A selected block stays selected, wherever it landed.
                Some((s, e)) => self.entry.select_range(s, e),
                None => self.entry.set_caret(r.caret),
            }
            self.doc_live_save()?;
        }
        Ok(())
    }

    /// Ctrl+C: what is selected in the line if anything is, else the contextual
    /// copy (`smart_copy`) — the Python's `_smart_copy` only ever runs "with
    /// nothing selected".
    pub fn copy_text(&self) -> Option<String> {
        if matches!(self.view, View::F1 | View::F2) {
            if self.entry.selection().is_some() {
                return Some(self.entry.selected_text());
            }
        }
        self.smart_copy()
    }

    /// Ctrl+V: paste into the line, replacing a selection. A line stays a line,
    /// so a line break in the pasted text becomes a space. In F2 it is saved as
    /// it lands; in F1 it waits in the entry for Enter like anything typed.
    pub fn paste_text(&mut self, text: &str) -> io::Result<()> {
        if !matches!(self.view, View::F1 | View::F2) {
            return Ok(());
        }
        let flat: String = text
            .chars()
            .map(|c| if c == '\n' || c == '\r' { ' ' } else { c })
            .collect();
        self.entry.insert(&flat);
        if self.view == View::F2 {
            self.doc_live_save()?;
        }
        Ok(())
    }

    /// Ctrl+X: take the selection out of the line and hand it back. Nothing
    /// selected, nothing happens. In F2 the change is saved as it is made, like
    /// every other edit there.
    pub fn cut_selection(&mut self) -> io::Result<Option<String>> {
        if !matches!(self.view, View::F1 | View::F2) || self.entry.selection().is_none() {
            return Ok(None);
        }
        let cut = self.entry.selected_text();
        self.entry.delete_selection();
        if self.view == View::F2 {
            self.doc_live_save()?;
        }
        Ok(Some(cut))
    }

    /// Ctrl+Shift+E in F2: split the current line on its spaces — or, standing
    /// on a dot, every line of the paragraph that dot opens. The dots themselves
    /// are structure and never touched. One undo step, and nothing written when
    /// nothing would change.
    pub fn doc_split_line_on_spaces(&mut self) -> io::Result<()> {
        let n = self.ring.lines.len();
        if n == 0 {
            return Ok(());
        }
        let idx = self.ring.index;
        let targets: Vec<usize> = if self.ring.lines[idx] == "." {
            ((idx + 1)..n).take_while(|&i| self.ring.lines[i] != ".").collect()
        } else {
            vec![idx]
        };
        if targets.is_empty()
            || targets.iter().all(|&i| {
                words::split_on_spaces(&self.ring.lines[i]) == vec![self.ring.lines[i].clone()]
            })
        {
            self.status = "Nothing to split".into();
            return Ok(());
        }
        if self.para_focus {
            self.exit_para_focus();
        }
        let first = targets[0];
        let mut new_lines: Vec<String> = Vec::new();
        let mut new_index = 0;
        for (i, line) in self.ring.lines.iter().enumerate() {
            if i == first {
                new_index = new_lines.len();
            }
            if targets.contains(&i) {
                let pieces = words::split_on_spaces(line);
                if pieces.is_empty() {
                    new_lines.push(line.clone());
                } else {
                    new_lines.extend(pieces);
                }
            } else {
                new_lines.push(line.clone());
            }
        }
        let before = self.ring.lines.clone();
        void::atomic_write(&self.current_file, &new_lines, true)?; // keeps a .bak
        self.ring.lines = new_lines.clone();
        self.ring.index = new_index;
        self.sync_entry();
        self.entry.home();
        self.undo.record(self.current_file.clone(), before, new_lines, None);
        self.status = "Split on spaces".into();
        Ok(())
    }

    /// Ctrl+Shift+Delete in F2, with the cursor on the document's FIRST dot:
    /// delete every dot separator, merging all paragraphs into one. Tab on the
    /// single remaining dot then shuffles every line of the file at once instead
    /// of one paragraph's worth. A no-op anywhere else, so it cannot fire by
    /// accident mid-edit.
    pub fn doc_collapse_to_one_paragraph(&mut self) -> io::Result<()> {
        if self.ring.index != 0 {
            return Ok(());
        }
        let mut after = vec![".".to_string()];
        after.extend(self.ring.lines.iter().filter(|l| *l != ".").cloned());
        if after == self.ring.lines {
            return Ok(());
        }
        self.ring.lines = after;
        self.ring.index = 0;
        self.sync_entry();
        self.entry.home();
        self.save()?;
        self.status = "Collapsed into one paragraph".into();
        Ok(())
    }

    /// Alt+Shift+↑/↓ in F2: duplicate and put the copy where the arrow points —
    /// before the original going up, after it going down — with the cursor on
    /// the copy. Standing on a line it copies that line; standing on a dot, the
    /// whole paragraph the dot opens, with a dot of its own.
    pub fn doc_duplicate(&mut self, direction: isize) -> io::Result<()> {
        let n = self.ring.lines.len();
        if n == 0 {
            return Ok(());
        }
        let idx = self.ring.index;
        let (start, end) = if self.ring.lines[idx] == "." {
            let mut fin = idx + 1;
            while fin < n && self.ring.lines[fin] != "." {
                fin += 1;
            }
            (idx, fin)
        } else {
            (idx, idx + 1)
        };
        let block: Vec<String> = self.ring.lines[start..end].to_vec();
        let insert_at = if direction < 0 { start } else { end };

        // A line duplicated inside a focused paragraph must stay inside it: the
        // same index shift `doc_split_line` applies when it inserts mid-focus.
        // (Only a single line can happen here — focus never sits on a dot.)
        if self.para_focus && end - start == 1 {
            let k = block.len();
            let orig_new = if insert_at > idx { idx } else { idx + k };
            let mut shifted: Vec<usize> = self
                .para_focus_content
                .iter()
                .map(|&i| if i < insert_at { i } else { i + k })
                .collect();
            if let Some(pos) = shifted.iter().position(|&i| i == orig_new) {
                shifted.insert(if direction < 0 { pos } else { pos + 1 }, insert_at);
            }
            self.para_focus_content = shifted;
        }

        for (offset, line) in block.iter().enumerate() {
            self.ring.lines.insert(insert_at + offset, line.clone());
        }
        self.ring.index = insert_at;
        self.sync_entry();
        self.entry.home();
        self.save()?;
        self.status = format!(
            "⧉ {} line(s) duplicated {}",
            block.len(),
            if direction < 0 { "up" } else { "down" }
        );
        Ok(())
    }

    /// Alt+Shift+↑/↓ in F3: duplicate the highlighted chapter as a new file,
    /// named with the same `-2`, `-3` pattern the merge uses, listed just before
    /// or after the original, with the cursor on the copy. Nothing happens on a
    /// dot (not a chapter), on the `0` portal (a marker, not a file) or while a
    /// new entry is being named.
    pub fn book_duplicate(&mut self, direction: isize) -> io::Result<()> {
        if self.pending_new || self.pending_merge {
            return Ok(());
        }
        let idx = self.library.index;
        let Some(fname) = self.library.entries.get(idx).cloned() else {
            return Ok(());
        };
        if library::is_separator(&fname) || library::is_portal(&fname) {
            return Ok(());
        }
        let fpath = library::chapter_path(&self.void_dir, &fname);
        let Ok(content) = std::fs::read_to_string(&fpath) else {
            self.status = format!("Could not read {fname}");
            return Ok(());
        };

        let (stem, ext) = match fname.rsplit_once('.') {
            Some((s, e)) => (s.to_string(), format!(".{e}")),
            None => (fname.clone(), String::new()),
        };
        let mut new_name = fname.clone();
        let mut new_path = fpath.clone();
        let mut k = 2;
        while new_path.exists() || self.library.entries.contains(&new_name) {
            new_name = format!("{stem}-{k}{ext}");
            new_path = library::chapter_path(&self.void_dir, &new_name);
            k += 1;
        }

        let after: Vec<String> = content.lines().map(|l| l.trim_end().to_string()).collect();
        void::atomic_write(&new_path, &after, false)?;
        let insert_at = if direction < 0 { idx } else { idx + 1 };
        self.library.entries.insert(insert_at, new_name.clone());
        self.library.index = insert_at;
        self.save_library()?;
        self.undo.record_transaction(
            vec![undo::FileChange { path: new_path, before: Vec::new(), after }],
            Some("duplicate".into()),
        );
        self.entry.clear();
        self.status = format!(
            "⧉ {} → {}",
            library::display_name(&fname),
            library::display_name(&new_name)
        );
        Ok(())
    }

    /// Backspace in F2: delete the selection or the character before the caret —
    /// and only at the very start of a line, with nothing selected, join it onto
    /// the one above. A selection made backwards to the start (caret at 0) is
    /// still a selection to delete, not a request to join.
    pub fn doc_backspace(&mut self) -> io::Result<()> {
        if self.entry.selection().is_none() && self.entry.caret() == 0 {
            return self.doc_join_prev();
        }
        self.entry.backspace();
        self.doc_live_save()
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

    /// F10, Tab: step the carousel's frame through the presets and `custom`,
    /// wrapping. Remembered, and a preview that is open is laid out again.
    pub fn settings_step_carousel(&mut self, delta: isize) {
        let at = carousel::FRAMES
            .iter()
            .position(|f| *f == self.config.carousel_preset)
            .unwrap_or_else(|| carousel::FRAMES.iter().position(|f| *f == carousel::DEFAULT_PRESET).unwrap_or(0));
        let n = carousel::FRAMES.len() as isize;
        self.config.carousel_preset = carousel::FRAMES[(at as isize + delta).rem_euclid(n) as usize].to_string();
        self.persist_config();
        self.rebuild_carousel_plan();
    }

    /// F10, Ctrl+arrows: nudge a `custom` frame's width and height by `dw` / `dh`
    /// steps of ten pixels. A named preset is not edited, and a side never goes
    /// below the minimum or above the maximum.
    pub fn settings_step_carousel_size(&mut self, dw: i32, dh: i32) {
        if self.config.carousel_preset != "custom" {
            return;
        }
        let step = |v: u32, d: i32| (v as i64 + d as i64 * carousel::SIZE_STEP as i64)
            .clamp(carousel::SIZE_MIN as i64, carousel::SIZE_MAX as i64) as u32;
        self.config.carousel_w = step(self.config.carousel_w, dw);
        self.config.carousel_h = step(self.config.carousel_h, dh);
        self.persist_config();
        self.rebuild_carousel_plan();
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

    /// Ctrl+Delete in F2: the trash, both ways — the Python's `_delete_line_to_trash`.
    /// Any file (the scratch included) → `trash.txt`; `trash.txt` → the scratch.
    /// The line is never filtered — even a `.` separator travels like any other.
    pub fn delete_line_to_trash(&mut self) -> io::Result<()> {
        let n = self.ring.lines.len();
        if n <= 1 {
            return Ok(());
        }
        let cur = self.ring.index;
        let line = self.ring.lines[cur].clone();
        let scratch = self.scratch_path();
        let trash = self.trash_path();

        // Nothing is ever deleted for good: from the trash the line goes back
        // to the scratch, from anywhere else (the scratch included) to the
        // trash. `?` leaves the line here if the destination can't be written.
        if same_file(&self.current_file, &trash) {
            self.append_line(&scratch, &line)?;
            self.status = "→ 0.txt".into();
        } else {
            self.append_line(&trash, &line)?;
            self.status = "→ trash.txt".into();
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

/// Dejar el archivo prolijo después de sacarle texto: sin puntos repetidos ni
/// colgando al final, pero CON el punto inicial.
///
/// F5 usa `collapse_dots` a secas porque reconstruye el anillo desde los
/// párrafos y vuelve a poner los puntos; en F2 el punto de arriba es
/// estructural — `load_doc` siempre lo garantiza — así que sacarlo dejaría el
/// archivo en un estado que ninguna otra parte del programa produce.
fn tidy_after_send(lines: Vec<String>) -> Vec<String> {
    let mut out = f5::collapse_dots(&lines);
    if out.first().map(|l| l != ".").unwrap_or(true) {
        out.insert(0, ".".to_string());
    }
    out
}

/// Whether two paths mean the same file. Compares canonically where possible
/// (so `/void/I/a.txt` and a path through a symlink agree), falling back to a
/// plain comparison for files that don't exist yet.
fn same_file(a: &Path, b: &Path) -> bool {
    match (a.canonicalize(), b.canonicalize()) {
        (Ok(x), Ok(y)) => x == y,
        _ => a == b,
    }
}

/// The saved ring index for `file`, clamped into `[0, total)`. `0` when
/// nothing was saved — the ordinary case for a file opened for the first time.
/// A chapter's text under its title, as Ctrl+C in F3 copies it. An empty chapter
/// still yields its title, so there is always something saying what was copied.
fn titled_chapter(entry: &str, text: &str) -> String {
    let header = library::chapter_title_header(entry);
    let body = text.trim_end_matches('\n');
    if body.is_empty() {
        header
    } else {
        format!("{header}\n{body}")
    }
}

fn restored_index(void_dir: &Path, file: &Path, total: usize) -> usize {
    file.file_name()
        .and_then(|n| n.to_str())
        .and_then(|name| position::load_last_line(void_dir, name))
        .map(|idx| idx.min(total.saturating_sub(1)))
        .unwrap_or(0)
}

/// Walk `dir` recursively, collecting every `.txt` file that doesn't start
/// with a dot. A port of the file-gathering half of `_random_line_from_dir`.
fn collect_txt_files(dir: &Path, out: &mut Vec<PathBuf>) {
    let Ok(entries) = std::fs::read_dir(dir) else {
        return;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_dir() {
            collect_txt_files(&path, out);
        } else if path
            .file_name()
            .and_then(|n| n.to_str())
            .is_some_and(|n| n.to_lowercase().ends_with(".txt") && !n.starts_with('.'))
        {
            out.push(path);
        }
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
/// Open the sandbox void, resuming the last restorable view (F1/F2/F3) on
/// whichever file was active when it was saved — or, with nothing saved yet
/// (a fresh install, or a view that isn't restorable), the familiar default:
/// F1 on the scratch, ready to write. A port of `_restore_startup_view`.
pub fn open_sandbox() -> Voider {
    let dir = void::sandbox_dir();
    let _ = std::fs::create_dir_all(dir.join("I"));
    let scratch = dir.join("I/0.txt");
    if !scratch.exists() {
        let _ = void::atomic_write(&scratch, &[".".to_string()], false);
    }
    let config = Config::load(&dir);
    let restore_view = config.last_view.as_deref().and_then(View::from_key);
    let target = config
        .active_file
        .as_ref()
        .map(|name| library::chapter_path(&dir, name))
        .filter(|p| p.exists())
        .unwrap_or_else(|| scratch.clone());

    let mut v = Voider::open(&dir, &target);
    v.ipc = Some(ipc::Ipc::start(&ipc::default_socket_path()));
    v.snapshot_on_entry();
    match restore_view {
        Some(view @ (View::F2 | View::F3)) => v.switch_to(view),
        _ => v.goto_end(),
    }
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

    // A repeated name makes a genuinely SEPARATE file — "<name>-2.txt" — never a
    // second row pointing at the old one (test_f3_pending_entry.py).

    #[test]
    fn a_colliding_name_gets_its_own_separate_file() {
        let (_d, mut v) = book();
        v.switch_to(View::F3);
        let path = v.new_chapter("Dos").unwrap().unwrap();
        assert_eq!(path, library::chapter_path(&v.void_dir, "Dos-2.txt"));
        assert!(v.library.entries.contains(&"Dos-2.txt".to_string()));
        assert_eq!(v.library.current(), "Dos-2.txt");
    }

    #[test]
    fn the_existing_chapter_is_never_touched_by_a_colliding_name() {
        let (_d, mut v) = book();
        v.switch_to(View::F3);
        v.new_chapter("Dos").unwrap();
        let doc = void::load_doc(&library::chapter_path(&v.void_dir, "Dos.txt"));
        assert!(doc.lines.contains(&"de dos".to_string())); // untouched
    }

    #[test]
    fn the_new_file_is_empty_of_the_old_one() {
        let (_d, mut v) = book();
        v.switch_to(View::F3);
        v.new_chapter("Dos").unwrap();
        let fresh = void::load_doc(&library::chapter_path(&v.void_dir, "Dos-2.txt"));
        assert!(!fresh.lines.contains(&"de dos".to_string()));
        assert!(fresh.lines.iter().all(|l| l == "."));
    }

    #[test]
    fn a_second_collision_keeps_incrementing() {
        let (_d, mut v) = book();
        v.switch_to(View::F3);
        v.new_chapter("Dos").unwrap(); // Dos-2
        v.new_chapter("Dos").unwrap(); // Dos-3
        assert!(v.library.entries.contains(&"Dos-3.txt".to_string()));
    }

    #[test]
    fn a_file_on_disk_but_unlisted_is_not_adopted_either() {
        let (_d, mut v) = book();
        v.switch_to(View::F3);
        let stray = library::chapter_path(&v.void_dir, "Suelto.txt");
        void::atomic_write(&stray, &["viejo".to_string()], false).unwrap();
        v.new_chapter("Suelto").unwrap();
        assert!(v.library.entries.contains(&"Suelto-2.txt".to_string()));
        assert_eq!(void::load_doc(&stray).lines, vec![".", "viejo"].iter().map(|s| s.to_string()).collect::<Vec<_>>());
    }

    #[test]
    fn a_name_that_does_not_collide_is_unaffected() {
        let (_d, mut v) = book();
        v.switch_to(View::F3);
        v.new_chapter("Nombre Nuevo").unwrap();
        assert!(v.library.entries.contains(&"Nombre Nuevo.txt".to_string()));
        assert!(!v.library.entries.contains(&"Nombre Nuevo-2.txt".to_string()));
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
        assert!(sealed.lines.contains(&"texto dos".to_string()));
        // what came before the marker stayed in the container
        assert!(v.ring.lines.contains(&"texto uno".to_string()));
        assert!(Library::load(&v.void_dir).entries.contains(&"Nuevo.txt".to_string()));
    }

    #[test]
    fn splitting_into_an_existing_name_appends_and_never_overwrites() {
        let (_d, mut v) = book(); // Dos.txt already holds 'de dos'
        v.ring.lines = vec![".".into(), "/Dos".into(), "agregado".into()];
        v.split_at_markers().unwrap();

        let dest = void::load_doc(&library::chapter_path(&v.void_dir, "Dos.txt"));
        assert!(dest.lines.contains(&"de dos".to_string())); // the old text survived
        assert!(dest.lines.contains(&"agregado".to_string())); // and the new arrived
    }

    #[test]
    fn an_emptied_container_leaves_the_library() {
        let (_d, mut v) = book(); // active is Uno.txt
        v.ring.lines = vec!["/Sellado".into(), "todo".into()];
        v.split_at_markers().unwrap();
        let lib = Library::load(&v.void_dir);
        assert!(lib.entries.contains(&"Sellado.txt".to_string()));
        assert!(!lib.entries.contains(&"Uno.txt".to_string())); // emptied, so delisted
    }

    #[test]
    fn several_markers_each_seal_down_to_the_next() {
        let (_d, mut v) = book();
        v.ring.lines = vec![
            "a".into(), "/Uno".into(), "b".into(), "/Dos".into(), "c".into(),
        ];
        assert_eq!(v.split_at_markers().unwrap(), 2);
        let uno = void::load_doc(&library::chapter_path(&v.void_dir, "Uno.txt"));
        let dos = void::load_doc(&library::chapter_path(&v.void_dir, "Dos.txt"));
        assert!(uno.lines.contains(&"b".to_string()));
        assert!(dos.lines.contains(&"c".to_string()));
        assert!(!dos.lines.contains(&"b".to_string())); // not everything below the first
        assert!(v.ring.lines.contains(&"a".to_string())); // the leading text stays
    }

    #[test]
    fn a_marker_with_nothing_below_it_makes_a_placeholder_dot() {
        let (_d, mut v) = book();
        v.ring.lines = vec![".".into(), "a".into(), "/Vacio".into()];
        v.split_at_markers().unwrap();
        let empty = void::load_doc(&library::chapter_path(&v.void_dir, "Vacio.txt"));
        assert_eq!(empty.lines, vec!["."]);
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

    // ── dispatching paragraphs (Ctrl+Shift+D in F2) ─────────────────────────────

    #[test]
    fn a_named_paragraph_is_sent_to_its_chapter() {
        let (_d, mut v) = app(&[".", "Line one.", "Line two.", "/chapter", ".", "Stays here."]);
        assert_eq!(v.dispatch_paragraphs().unwrap(), 1);
        let chapter = void::load_doc(&library::chapter_path(&v.void_dir, "chapter.txt"));
        assert_eq!(chapter.lines, vec![".".to_string(), "Line one.".into(), "Line two.".into()]);
        assert_eq!(v.ring.lines, vec![".".to_string(), "Stays here.".into()]);
    }

    #[test]
    fn a_bare_slash_creates_a_timestamped_file() {
        let (_d, mut v) = app(&[".", "Sin nombre.", "/"]);
        assert_eq!(v.dispatch_paragraphs().unwrap(), 1);
        let i_dir = v.void_dir.join("I");
        let created: Vec<_> = std::fs::read_dir(&i_dir).unwrap().filter_map(|e| e.ok()).collect();
        assert_eq!(created.len(), 1);
        assert_eq!(v.ring.lines, vec![".".to_string()]);
    }

    #[test]
    fn dispatching_to_an_existing_file_appends_never_overwrites() {
        let (_d, mut v) = app(&[".", "Line one.", "/chapter"]);
        v.dispatch_paragraphs().unwrap();
        v.ring.lines = vec![".".to_string(), "Line two.".into(), "/chapter".into()];
        v.dispatch_paragraphs().unwrap();
        let chapter = void::load_doc(&library::chapter_path(&v.void_dir, "chapter.txt"));
        assert_eq!(
            chapter.lines,
            vec![".".to_string(), "Line one.".into(), ".".into(), "Line two.".into()]
        );
    }

    #[test]
    fn no_markers_is_a_noop() {
        let (_d, mut v) = app(&[".", "Nothing to dispatch here."]);
        let before = v.ring.lines.clone();
        assert_eq!(v.dispatch_paragraphs().unwrap(), 0);
        assert_eq!(v.ring.lines, before);
    }

    #[test]
    fn multiple_marked_paragraphs_go_to_their_own_files() {
        let (_d, mut v) = app(&[".", "Para A.", "/alpha", ".", "Para B.", "/beta", ".", "Stay."]);
        assert_eq!(v.dispatch_paragraphs().unwrap(), 2);
        let alpha = void::load_doc(&library::chapter_path(&v.void_dir, "alpha.txt"));
        let beta = void::load_doc(&library::chapter_path(&v.void_dir, "beta.txt"));
        assert_eq!(alpha.lines, vec![".".to_string(), "Para A.".into()]);
        assert_eq!(beta.lines, vec![".".to_string(), "Para B.".into()]);
        assert_eq!(v.ring.lines, vec![".".to_string(), "Stay.".into()]);
    }

    #[test]
    fn dispatch_is_one_undo_step_across_source_and_target() {
        let (_d, mut v) = app(&[".", "Line one.", "/chapter", ".", "Stays here."]);
        let before = v.ring.lines.clone();
        v.dispatch_paragraphs().unwrap();
        assert!(library::chapter_path(&v.void_dir, "chapter.txt").exists());
        v.undo().unwrap();
        assert_eq!(void::load_doc(&v.current_file).lines, before);
    }

    // ── Tab in F2 (contextual cut-up) ───────────────────────────────────────────

    #[test]
    fn tab_on_the_leading_dot_shuffles_paragraph_order_not_their_content() {
        let (_d, mut v) = app(&[".", "a1", "a2", ".", "b1", ".", "c1", "c2"]);
        v.ring.index = 0;
        v.doc_tab().unwrap();
        assert_eq!(v.ring.index, 0); // stays on the leading dot
        let (_, mut got) = paragraphs::from_lines(&v.ring.lines);
        got.sort();
        let mut expected = vec![
            vec!["a1".to_string(), "a2".to_string()],
            vec!["b1".to_string()],
            vec!["c1".to_string(), "c2".to_string()],
        ];
        expected.sort();
        assert_eq!(got, expected); // same blocks, each keeping its own order
    }

    #[test]
    fn tab_on_the_leading_dot_is_a_noop_with_a_single_paragraph() {
        let (_d, mut v) = app(&[".", "only", "one", "para"]);
        let before = v.ring.lines.clone();
        v.doc_tab().unwrap();
        assert_eq!(v.ring.lines, before);
    }

    #[test]
    fn tab_on_another_dot_shuffles_only_that_paragraphs_lines() {
        let (_d, mut v) = app(&[".", "solo", ".", "b1", "b2", "b3"]);
        v.ring.index = 2; // the dot before ['b1','b2','b3']
        v.doc_tab().unwrap();
        assert_eq!(v.ring.index, 2); // stays on the same separator
        let (_, got) = paragraphs::from_lines(&v.ring.lines);
        assert_eq!(got[0], vec!["solo".to_string()]); // untouched
        let mut b = got[1].clone();
        b.sort();
        assert_eq!(b, vec!["b1".to_string(), "b2".to_string(), "b3".to_string()]);
    }

    #[test]
    fn tab_on_a_dot_before_a_single_line_paragraph_is_a_noop() {
        let (_d, mut v) = app(&[".", "a1", "a2", ".", "solo"]);
        v.ring.index = 3; // the dot before ['solo']
        let before = v.ring.lines.clone();
        v.doc_tab().unwrap();
        assert_eq!(v.ring.lines, before);
    }

    #[test]
    fn tab_on_content_inserts_a_random_i_fragment_at_the_caret() {
        let (_d, mut v) = app(&[".", "mine"]);
        std::fs::create_dir_all(v.void_dir.join("I")).unwrap();
        std::fs::write(v.void_dir.join("I").join("src.txt"), ".\nborrowed line\n").unwrap();
        v.ring.index = 1;
        v.entry = TextLine::new("mine"); // caret parked at the end, like Python's test
        v.doc_tab().unwrap();
        assert_eq!(v.ring.lines, vec![".".to_string(), "mineborrowed line".to_string()]);
        assert_eq!(v.ring.index, 1);
    }

    #[test]
    fn tab_at_the_start_of_the_line_inserts_before_the_text() {
        let (_d, mut v) = app(&[".", "mine"]);
        std::fs::create_dir_all(v.void_dir.join("I")).unwrap();
        std::fs::write(v.void_dir.join("I").join("src.txt"), "word\n").unwrap();
        v.ring.index = 1;
        v.entry = TextLine::new("mine");
        v.entry.set_caret(0);
        v.doc_tab().unwrap();
        assert_eq!(v.ring.lines, vec![".".to_string(), "wordmine".to_string()]);
    }

    #[test]
    fn tab_with_no_i_lines_available_is_a_noop() {
        let (_d, mut v) = app(&[".", "mine"]); // empty I/
        v.ring.index = 1;
        v.entry = TextLine::new("mine");
        v.doc_tab().unwrap();
        assert_eq!(v.ring.lines, vec![".".to_string(), "mine".to_string()]);
    }

    #[test]
    fn tab_pressed_again_at_the_same_spot_re_rolls_instead_of_piling_up() {
        let (_d, mut v) = app(&[".", "mine"]);
        std::fs::create_dir_all(v.void_dir.join("I")).unwrap();
        std::fs::write(v.void_dir.join("I").join("src.txt"), "loop\n").unwrap();
        v.ring.index = 1;
        v.entry = TextLine::new("mine");
        v.doc_tab().unwrap();
        assert_eq!(v.entry.text(), "mineloop");
        v.doc_tab().unwrap(); // caret is still right where the fragment ends
        assert_eq!(v.entry.text(), "mineloop"); // replaced, not doubled
    }

    #[test]
    fn random_line_from_dir_never_returns_a_line_from_the_excluded_file() {
        let (_d, v) = app(&["."]);
        let i_dir = v.void_dir.join("I");
        std::fs::create_dir_all(&i_dir).unwrap();
        std::fs::write(i_dir.join("a.txt"), "keep\n").unwrap();
        std::fs::write(i_dir.join("active.txt"), "skip me\n").unwrap();
        let active = i_dir.join("active.txt");
        for _ in 0..10 {
            assert_eq!(v.random_line_from_dir(&i_dir, Some(&active)), Some("keep".to_string()));
        }
    }

    #[test]
    fn random_line_from_dir_with_nothing_there_returns_none() {
        let (_d, v) = app(&["."]);
        let i_dir = v.void_dir.join("I");
        assert_eq!(v.random_line_from_dir(&i_dir, None), None);
    }

    // ── Shift+Tab en F2: el fragmento viene del corpus ──────────────────────────

    #[test]
    fn shift_tab_trae_una_linea_del_working_set() {
        let (_d, mut v) = corpus_app(&["libro.txt"]);
        v.switch_to(View::F7);
        v.ws_tab(); // llenar la ranura
        v.switch_to(View::F2);
        v.ring.index = 1;
        v.entry = TextLine::new("lo mio ");
        v.insert_random_ws_fragment().unwrap();
        assert!(
            v.entry.text().starts_with("lo mio "),
            "no debe pisar lo que ya estaba: {:?}",
            v.entry.text()
        );
        assert!(v.entry.text().len() > "lo mio ".len(), "no insertó nada");
    }

    #[test]
    fn sin_working_set_shift_tab_avisa_y_no_toca_la_linea() {
        let (_d, mut v) = corpus_app(&["libro.txt"]);
        // ninguna ranura llena
        v.ring.index = 1;
        v.entry = TextLine::new("intacto");
        v.insert_random_ws_fragment().unwrap();
        assert_eq!(v.entry.text(), "intacto");
        assert!(v.status.contains("working set"));
    }

    #[test]
    fn el_fragmento_del_corpus_nunca_sale_de_una_ranura_vacia() {
        let (_d, mut v) = corpus_app(&["a.txt"]);
        v.ws.books = vec![corpus::Slot::empty(), corpus::Slot::empty()];
        assert_eq!(v.random_line_from_working_set(), None);
    }

    #[test]
    fn un_libro_ilegible_no_corta_la_busqueda() {
        let (_d, mut v) = corpus_app(&["bueno.txt"]);
        v.ws.books = vec![
            corpus::Slot { path: "no-existe.txt".into(), position: 0 },
            corpus::Slot { path: "bueno.txt".into(), position: 0 },
        ];
        // Se saltea el que no se puede leer y sigue con el siguiente.
        let line = v.random_line_from_working_set();
        assert!(line.is_some(), "un libro roto no debe cortar la búsqueda");
    }

    #[test]
    fn repetir_shift_tab_vuelve_a_sortear_en_vez_de_apilar() {
        let (_d, mut v) = corpus_app(&["libro.txt"]);
        v.switch_to(View::F7);
        v.ws_tab();
        v.switch_to(View::F2);
        v.ring.index = 1;
        v.entry = TextLine::new("");
        v.insert_random_ws_fragment().unwrap();
        let largo = v.entry.text().chars().count();
        v.insert_random_ws_fragment().unwrap();
        assert_eq!(
            v.entry.text().chars().count(),
            largo,
            "apiló en vez de reemplazar: {:?}",
            v.entry.text()
        );
    }

    // ── Smart copy (Ctrl+C, F2 / F3) ─────────────────────────────────────────────

    #[test]
    fn smart_copy_in_f2_copies_the_current_line() {
        let (_d, mut v) = app(&[".", "hello", ".", "world"]);
        v.view = View::F2;
        v.ring.index = 1;
        assert_eq!(v.smart_copy(), Some("hello".to_string()));
    }

    #[test]
    fn smart_copy_on_a_dot_in_f2_copies_the_paragraph_that_follows() {
        let (_d, mut v) = app(&[".", "a", "b", ".", "c"]);
        v.view = View::F2;
        v.ring.index = 0;
        assert_eq!(v.smart_copy(), Some("a\nb".to_string()));
    }

    #[test]
    fn a_dot_with_nothing_after_it_copies_nothing() {
        let (_d, mut v) = app(&["a", "."]);
        v.view = View::F2;
        v.ring.index = v.ring.lines.len() - 1; // the trailing dot
        assert_eq!(v.smart_copy(), None);
    }

    #[test]
    fn smart_copy_on_a_dot_in_f3_copies_the_whole_book() {
        let (_d, mut v) = app(&["."]);
        v.view = View::F3;
        let i = v.void_dir.join("I");
        std::fs::create_dir_all(&i).unwrap();
        std::fs::write(i.join("A.txt"), "a1\na2\n").unwrap();
        std::fs::write(i.join("B.txt"), "b1\n").unwrap();
        v.library = Library {
            entries: vec![".".into(), "A.txt".into(), "B.txt".into()],
            index: 0,
        };
        assert_eq!(v.smart_copy(), Some("── A ──\na1\na2\n.\n── B ──\nb1".to_string()));
    }

    #[test]
    fn smart_copy_on_a_dot_in_f3_skips_the_portal() {
        let (_d, mut v) = app(&["."]);
        v.view = View::F3;
        let i = v.void_dir.join("I");
        std::fs::create_dir_all(&i).unwrap();
        std::fs::write(i.join("0.txt"), "scratch\n").unwrap();
        std::fs::write(i.join("A.txt"), "a1\n").unwrap();
        v.library = Library {
            entries: vec![".".into(), "0.txt".into(), "A.txt".into()],
            index: 0,
        };
        assert_eq!(v.smart_copy(), Some("── A ──\na1".to_string()));
    }

    #[test]
    fn smart_copy_on_a_chapter_in_f3_copies_its_raw_text() {
        let (_d, mut v) = app(&["."]);
        v.view = View::F3;
        let i = v.void_dir.join("I");
        std::fs::create_dir_all(&i).unwrap();
        std::fs::write(i.join("chap.txt"), "line one\n.\nline two\n").unwrap();
        v.library = Library { entries: vec!["chap.txt".into()], index: 0 };
        assert_eq!(v.smart_copy(), Some("── CHAP ──\nline one\n.\nline two".to_string()));
    }

    #[test]
    fn an_empty_chapter_still_copies_its_title() {
        let (_d, mut v) = app(&["."]);
        v.view = View::F3;
        let i = v.void_dir.join("I");
        std::fs::create_dir_all(&i).unwrap();
        std::fs::write(i.join("Vacio.txt"), "").unwrap();
        v.library = Library { entries: vec!["Vacio.txt".into()], index: 0 };
        assert_eq!(v.smart_copy(), Some("── VACIO ──".to_string()));
    }

    // ── Remembering position across runs ────────────────────────────────────────

    // ── Alt+F4: a clean quit (test_quit_app.py) ──────────────────────────────

    // ── a text selection in the entry line ───────────────────────────────────

    #[test]
    fn alt_arrow_with_a_selection_moves_the_whole_block_and_keeps_it_selected() {
        // test_swap_words_selection.py: the word glued to its comma must not stay behind.
        let (_d, mut v) = app(&[".", "eje aplica a la realidad, funciona bien"]);
        v.ring.index = 1;
        v.sync_entry();
        let start = "eje ".chars().count();
        v.entry.select_range(start, start + "aplica a la realidad".chars().count());
        v.doc_swap_words(-1).unwrap();
        assert_eq!(v.entry.text(), "aplica a la realidad, eje funciona bien");
        assert_eq!(v.entry.selection(), Some((0, "aplica a la realidad,".chars().count())));
        assert_eq!(v.ring.lines[1], "aplica a la realidad, eje funciona bien");
    }

    #[test]
    fn copying_with_a_selection_copies_the_selection_not_the_whole_line() {
        let (_d, mut v) = app(&[".", "hola mundo"]);
        v.view = View::F2;
        v.ring.index = 1;
        v.sync_entry();
        assert_eq!(v.copy_text(), Some("hola mundo".to_string())); // nothing selected: the line
        v.entry.select_range(5, 10);
        assert_eq!(v.copy_text(), Some("mundo".to_string()));
    }

    #[test]
    fn cutting_takes_the_selection_out_and_saves() {
        let (_d, mut v) = app(&[".", "hola mundo"]);
        v.view = View::F2;
        v.ring.index = 1;
        v.sync_entry();
        v.entry.select_range(4, 10); // " mundo"
        assert_eq!(v.cut_selection().unwrap(), Some(" mundo".to_string()));
        assert_eq!(v.entry.text(), "hola");
        assert_eq!(void::load_doc(&v.current_file).lines[1], "hola");
    }

    #[test]
    fn pasting_replaces_the_selection_and_keeps_the_line_a_line() {
        let (_d, mut v) = app(&[".", "hola mundo"]);
        v.view = View::F2;
        v.ring.index = 1;
        v.sync_entry();
        v.entry.select_range(5, 10);
        v.paste_text("tierra\nvasta").unwrap();
        assert_eq!(v.entry.text(), "hola tierra vasta"); // a newline becomes a space
        assert_eq!(v.entry.selection(), None);
        assert_eq!(void::load_doc(&v.current_file).lines[1], "hola tierra vasta");
    }

    #[test]
    fn pasting_in_f1_goes_into_the_entry_without_being_committed() {
        let (_d, mut v) = app(&[".", "a"]);
        v.view = View::F1;
        v.entry.clear();
        v.paste_text("sin enter").unwrap();
        assert_eq!(v.entry.text(), "sin enter");
        assert_eq!(void::load_doc(&v.current_file).lines, vec![".", "a"]); // nothing written yet
    }

    #[test]
    fn backspace_on_a_selection_that_reaches_the_start_deletes_it_instead_of_joining_lines() {
        let (_d, mut v) = app(&[".", "arriba", "hola mundo"]);
        v.view = View::F2;
        v.ring.index = 2;
        v.sync_entry();
        v.entry.set_caret(4);
        v.entry.extend_home(); // selected "hola", the caret now at 0
        v.doc_backspace().unwrap();
        assert_eq!(v.entry.text(), " mundo");
        assert_eq!(v.ring.lines, vec![".", "arriba", " mundo"]); // not glued onto "arriba"
    }

    #[test]
    fn backspace_at_the_start_with_nothing_selected_still_joins_the_line_above() {
        let (_d, mut v) = app(&[".", "arriba", "abajo"]);
        v.view = View::F2;
        v.ring.index = 2;
        v.sync_entry();
        v.entry.home();
        v.doc_backspace().unwrap();
        assert_eq!(v.ring.lines, vec![".", "arribaabajo"]);
    }

    #[test]
    fn cutting_with_nothing_selected_does_nothing() {
        let (_d, mut v) = app(&[".", "hola"]);
        v.view = View::F2;
        v.ring.index = 1;
        v.sync_entry();
        assert_eq!(v.cut_selection().unwrap(), None);
        assert_eq!(v.entry.text(), "hola");
    }

    #[test]
    fn in_f5_the_voice_reads_the_paragraph_you_are_on_not_the_nth_unit() {
        // The units now include the dots, so "unit N" is no longer "paragraph N".
        let (_d, mut v) = app(&[".", "uno.", ".", "dos."]);
        v.switch_to(View::F5);
        v.para_idx = 1;
        assert_eq!(v.tts_current_text(), Some("dos.".to_string()));
    }

    // ── Shift+F12: a 1:1 cover screenshot (TestTakeCircleScreenshot) ─────────

    use std::cell::RefCell;

    /// A command runner that answers from a script and remembers what it was asked.
    struct Script {
        hyprctl: io::Result<shot::CmdOutput>,
        grim: io::Result<shot::CmdOutput>,
        calls: RefCell<Vec<(String, Vec<String>)>>,
    }

    fn ok(stdout: &str) -> io::Result<shot::CmdOutput> {
        Ok(shot::CmdOutput { ok: true, stdout: stdout.into(), stderr: String::new() })
    }

    fn clients(pid: u32, at: (i64, i64), size: (i64, i64)) -> String {
        format!(r#"[{{"pid": {pid}, "at": [{}, {}], "size": [{}, {}]}}]"#, at.0, at.1, size.0, size.1)
    }

    impl Script {
        fn new(hyprctl: io::Result<shot::CmdOutput>) -> Self {
            Script { hyprctl, grim: ok(""), calls: RefCell::new(Vec::new()) }
        }
        fn run(&self, prog: &str, args: &[String]) -> io::Result<shot::CmdOutput> {
            self.calls.borrow_mut().push((prog.to_string(), args.to_vec()));
            let r = if prog == "hyprctl" { &self.hyprctl } else { &self.grim };
            match r {
                Ok(o) => Ok(shot::CmdOutput { ok: o.ok, stdout: o.stdout.clone(), stderr: o.stderr.clone() }),
                Err(e) => Err(io::Error::new(e.kind(), e.to_string())),
            }
        }
        fn grim_args(&self) -> Option<Vec<String>> {
            self.calls.borrow().iter().find(|(p, _)| p == "grim").map(|(_, a)| a.clone())
        }
    }

    fn take(v: &mut Voider, script: &Script, pid: u32) -> Option<PathBuf> {
        v.take_circle_screenshot_with(&mut |p, a| script.run(p, a), pid)
    }

    #[test]
    fn grim_gets_a_square_anchored_to_hyprctls_window() {
        let (_d, mut v) = app(&["."]);
        let s = Script::new(ok(&clients(4242, (291, 136), (1117, 916))));
        take(&mut v, &s, 4242).unwrap();
        let args = s.grim_args().expect("grim was not called");
        let at = args.iter().position(|a| a == "-g").unwrap();
        // side = min(1117, 916) = 916; x = 291 + (1117-916)/2 = 391; y = 136
        assert_eq!(args[at + 1], "391,136 916x916");
    }

    #[test]
    fn it_writes_into_covers_with_a_timestamped_name() {
        let (_d, mut v) = app(&["."]);
        let s = Script::new(ok(&clients(1, (0, 0), (800, 600))));
        let out = take(&mut v, &s, 1).unwrap();
        assert_eq!(out.parent().unwrap(), v.void_dir.join("covers"));
        let name = out.file_name().unwrap().to_string_lossy().to_string();
        assert!(name.starts_with("cover_") && name.ends_with(".png"), "{name}");
        assert_eq!(s.grim_args().unwrap().last().unwrap(), &out.to_string_lossy().to_string());
        assert!(v.void_dir.join("covers").is_dir());
    }

    #[test]
    fn no_matching_window_means_no_grim() {
        let (_d, mut v) = app(&["."]);
        let s = Script::new(ok(&clients(7, (0, 0), (1000, 1000))));
        assert!(take(&mut v, &s, 99).is_none());
        assert!(s.grim_args().is_none());
        assert!(v.status.contains("hyprctl"));
    }

    #[test]
    fn a_degenerate_window_means_no_grim() {
        let (_d, mut v) = app(&["."]);
        let s = Script::new(ok(&clients(5, (0, 0), (0, 0))));
        assert!(take(&mut v, &s, 5).is_none());
        assert!(s.grim_args().is_none());
    }

    #[test]
    fn hyprctl_missing_is_handled_without_crashing() {
        let (_d, mut v) = app(&["."]);
        let s = Script::new(Err(io::Error::new(io::ErrorKind::NotFound, "no hyprctl")));
        assert!(take(&mut v, &s, 1).is_none());
        assert!(v.status.contains("hyprctl"));
        assert!(s.grim_args().is_none());
    }

    #[test]
    fn hyprctl_answering_with_garbage_is_handled_without_crashing() {
        let (_d, mut v) = app(&["."]);
        let s = Script::new(ok("not json"));
        assert!(take(&mut v, &s, 1).is_none());
        assert!(s.grim_args().is_none());
    }

    #[test]
    fn grim_failing_does_not_crash_and_says_why() {
        let (_d, mut v) = app(&["."]);
        let mut s = Script::new(ok(&clients(1, (0, 0), (800, 600))));
        s.grim = Ok(shot::CmdOutput { ok: false, stdout: String::new(), stderr: "wlr-screencopy failed".into() });
        assert!(take(&mut v, &s, 1).is_none());
        assert!(v.status.contains("wlr-screencopy failed"), "{}", v.status);
    }

    #[test]
    fn grim_missing_does_not_crash() {
        let (_d, mut v) = app(&["."]);
        let mut s = Script::new(ok(&clients(1, (0, 0), (800, 600))));
        s.grim = Err(io::Error::new(io::ErrorKind::NotFound, "no grim"));
        assert!(take(&mut v, &s, 1).is_none());
        assert!(v.status.contains("grim"), "{}", v.status);
    }

    // ── Ctrl+Shift+Delete: collapse the document into ONE paragraph ──────────
    // Mirrors TestCollapseToOneParagraph in test_paragraphs.py: Tab on the single
    // remaining dot then shuffles every line of the file at once.

    #[test]
    fn collapsing_merges_two_paragraphs_into_one_dot() {
        let (_d, mut v) = app(&[".", "a", "b", ".", "c", "d"]);
        v.ring.index = 0;
        v.doc_collapse_to_one_paragraph().unwrap();
        assert_eq!(v.ring.lines, vec![".", "a", "b", "c", "d"]);
    }

    #[test]
    fn collapsing_keeps_the_order_across_three_paragraphs() {
        let (_d, mut v) = app(&[".", "a", ".", "b", ".", "c"]);
        v.ring.index = 0;
        v.doc_collapse_to_one_paragraph().unwrap();
        assert_eq!(v.ring.lines, vec![".", "a", "b", "c"]);
        assert_eq!(v.ring.index, 0); // the cursor stays on the remaining dot
    }

    #[test]
    fn collapsing_a_single_paragraph_changes_nothing() {
        let (_d, mut v) = app(&[".", "a", "b"]);
        v.ring.index = 0;
        v.doc_collapse_to_one_paragraph().unwrap();
        assert_eq!(v.ring.lines, vec![".", "a", "b"]);
    }

    #[test]
    fn collapsing_reaches_the_disk_and_can_be_undone() {
        let (_d, mut v) = app(&[".", "a", ".", "b"]);
        v.ring.index = 0;
        v.doc_collapse_to_one_paragraph().unwrap();
        assert_eq!(std::fs::read_to_string(&v.current_file).unwrap(), ".\na\nb\n");
        v.undo().unwrap();
        assert_eq!(v.ring.lines, vec![".", "a", ".", "b"]);
    }

    #[test]
    fn collapsing_only_works_on_the_first_dot() {
        // so it can't fire by accident in the middle of editing
        let (_d, mut v) = app(&[".", "a", "b", ".", "c", "d"]);
        let before = v.ring.lines.clone();
        v.ring.index = 3; // the second dot
        v.doc_collapse_to_one_paragraph().unwrap();
        assert_eq!(v.ring.lines, before);
        v.ring.index = 1; // a content line
        v.doc_collapse_to_one_paragraph().unwrap();
        assert_eq!(v.ring.lines, before);
    }

    #[test]
    fn requesting_a_quit_asks_the_window_to_close_and_remembers_the_line() {
        let (_d, mut v) = app(&[".", "a", "b", "c"]);
        v.ring.index = 2;
        assert!(!v.quit_requested);
        v.request_quit();
        assert!(v.quit_requested);
        // a clean quit, not a kill: where you were is kept
        let reopened = Voider::open(&v.void_dir, &v.current_file);
        assert_eq!(reopened.ring.index, 2);
    }

    #[test]
    fn reopening_a_file_restores_its_saved_line() {
        let (_d, mut v) = app(&[".", "a", "b", "c"]);
        v.ring.index = 2;
        v.save_last_line();
        let reopened = Voider::open(&v.void_dir, &v.current_file);
        assert_eq!(reopened.ring.index, 2);
    }

    #[test]
    fn a_saved_line_past_the_end_is_clamped_not_out_of_bounds() {
        let (_d, mut v) = app(&[".", "a", "b"]);
        v.ring.index = 2;
        v.save_last_line();
        // The file shrank between sessions — reopening must not go out of range.
        void::atomic_write(&v.current_file, &[".".to_string()], false).unwrap();
        let reopened = Voider::open(&v.void_dir, &v.current_file);
        assert_eq!(reopened.ring.index, 0);
    }

    #[test]
    fn a_file_never_saved_before_opens_at_the_start() {
        let (_d, v) = app(&[".", "a", "b"]);
        assert_eq!(v.ring.index, 0);
    }

    #[test]
    fn leaving_f2_saves_the_line_it_was_on() {
        let (_d, mut v) = app(&[".", "a", "b"]);
        v.view = View::F2;
        v.ring.index = 2;
        v.switch_to(View::F1);
        let name = v.current_file.file_name().unwrap().to_str().unwrap();
        assert_eq!(position::load_last_line(&v.void_dir, name), Some(2));
    }

    #[test]
    fn switching_to_a_restorable_view_saves_it_as_the_last_view() {
        let (_d, mut v) = app(&[".", "a"]);
        v.switch_to(View::F3);
        assert_eq!(Config::load(&v.void_dir).last_view.as_deref(), Some("F3"));
    }

    #[test]
    fn switching_to_f5_does_not_overwrite_the_last_restorable_view() {
        let (_d, mut v) = app(&[".", "a"]);
        v.switch_to(View::F2);
        v.switch_to(View::F5);
        assert_eq!(Config::load(&v.void_dir).last_view.as_deref(), Some("F2"));
    }

    #[test]
    fn opening_a_different_file_remembers_it_as_the_active_one() {
        let (_d, mut v) = app(&["."]);
        std::fs::create_dir_all(v.void_dir.join("I")).unwrap();
        let other = v.void_dir.join("I").join("other.txt");
        std::fs::write(&other, "x\n").unwrap();
        v.set_active_file(other);
        assert_eq!(Config::load(&v.void_dir).active_file.as_deref(), Some("other.txt"));
    }

    // ── Ctrl+Shift+F en F3: juntar los borradores sueltos ───────────────────────

    #[test]
    fn un_cero_en_una_subcarpeta_vuelve_al_scratch_y_desaparece() {
        let (_d, mut v) = app(&["."]);
        let sub = v.void_dir.join("I").join("telefono");
        std::fs::create_dir_all(&sub).unwrap();
        void::atomic_write(&v.scratch_path(), &[".".into(), "lo de siempre".into()], false).unwrap();
        std::fs::write(sub.join("0.txt"), "escrito en el tren\n").unwrap();

        let (absorbidos, carpetas) = v.merge_stray_scratches().unwrap();
        assert_eq!(absorbidos, 1);
        assert_eq!(carpetas, 1, "la carpeta vacía tenía que irse");
        assert!(!sub.exists());

        let scratch = void::load_doc(&v.scratch_path()).lines;
        assert!(scratch.contains(&"lo de siempre".to_string()), "se perdió lo que ya había");
        assert!(scratch.contains(&"escrito en el tren".to_string()), "no absorbió");
    }

    #[test]
    fn lo_absorbido_va_separado_por_un_punto() {
        let (_d, mut v) = app(&["."]);
        let sub = v.void_dir.join("I").join("sub");
        std::fs::create_dir_all(&sub).unwrap();
        void::atomic_write(&v.scratch_path(), &[".".into(), "viejo".into()], false).unwrap();
        std::fs::write(sub.join("0.txt"), "nuevo\n").unwrap();
        v.merge_stray_scratches().unwrap();
        let s = void::load_doc(&v.scratch_path()).lines;
        let i = s.iter().position(|l| l == "viejo").unwrap();
        assert_eq!(s[i + 1], ".", "se pegó con lo anterior sin separador");
        assert_eq!(s[i + 2], "nuevo");
    }

    #[test]
    fn el_scratch_de_la_raiz_nunca_se_absorbe_a_si_mismo() {
        let (_d, mut v) = app(&["."]);
        void::atomic_write(&v.scratch_path(), &[".".into(), "solo esto".into()], false).unwrap();
        let (absorbidos, _) = v.merge_stray_scratches().unwrap();
        assert_eq!(absorbidos, 0);
        assert_eq!(
            void::load_doc(&v.scratch_path()).lines,
            vec![".".to_string(), "solo esto".into()],
            "se duplicó a sí mismo"
        );
    }

    #[test]
    fn sin_nada_suelto_no_toca_nada_y_lo_dice() {
        let (_d, mut v) = app(&["."]);
        void::atomic_write(&v.scratch_path(), &[".".into(), "intacto".into()], false).unwrap();
        assert_eq!(v.merge_stray_scratches().unwrap(), (0, 0));
        assert!(v.status.contains("Nada que juntar"));
    }

    #[test]
    fn una_carpeta_que_todavia_tiene_cosas_no_se_borra() {
        let (_d, mut v) = app(&["."]);
        let sub = v.void_dir.join("I").join("sub");
        std::fs::create_dir_all(&sub).unwrap();
        std::fs::write(sub.join("0.txt"), "borrador\n").unwrap();
        std::fs::write(sub.join("otra-cosa.txt"), "no soy un scratch\n").unwrap();
        let (absorbidos, carpetas) = v.merge_stray_scratches().unwrap();
        assert_eq!(absorbidos, 1);
        assert_eq!(carpetas, 0, "borró una carpeta que todavía tenía un archivo");
        assert!(sub.join("otra-cosa.txt").exists());
    }

    #[test]
    fn juntar_es_un_solo_paso_de_deshacer() {
        let (_d, mut v) = app(&["."]);
        let sub = v.void_dir.join("I").join("sub");
        std::fs::create_dir_all(&sub).unwrap();
        void::atomic_write(&v.scratch_path(), &[".".into(), "original".into()], false).unwrap();
        std::fs::write(sub.join("0.txt"), "absorbido\n").unwrap();
        v.set_active_file(v.scratch_path());
        v.merge_stray_scratches().unwrap();
        v.undo().unwrap();
        assert_eq!(
            void::load_doc(&v.scratch_path()).lines,
            vec![".".to_string(), "original".into()]
        );
    }

    #[test]
    fn varios_borradores_entran_todos() {
        let (_d, mut v) = app(&["."]);
        for n in ["a", "b", "c"] {
            let sub = v.void_dir.join("I").join(n);
            std::fs::create_dir_all(&sub).unwrap();
            std::fs::write(sub.join("0.txt"), format!("de {n}\n")).unwrap();
        }
        let (absorbidos, carpetas) = v.merge_stray_scratches().unwrap();
        assert_eq!(absorbidos, 3);
        assert_eq!(carpetas, 3);
        let s = void::load_doc(&v.scratch_path()).lines;
        for n in ["a", "b", "c"] {
            assert!(s.contains(&format!("de {n}")), "faltó {n}");
        }
    }

    // ── El lado O/ (F6 lector, F7 working set, F8 oráculo) ──────────────────────

    /// Un Voider con un corpus de mentira: O/ con libros y su cache.
    fn corpus_app(books: &[&str]) -> (tempfile::TempDir, Voider) {
        let (d, mut v) = app(&[".", "mi texto"]);
        let o = v.void_dir.join("O");
        std::fs::create_dir_all(&o).unwrap();
        for b in books {
            std::fs::write(o.join(b), "primera linea\n.\nsegunda linea\n").unwrap();
        }
        corpus::rebuild_cache(&v.void_dir, &o).unwrap();
        v.o_books = corpus::load_cache(&v.void_dir);
        (d, v)
    }

    #[test]
    fn f7_arranca_con_una_ranura_vacia() {
        let (_d, mut v) = corpus_app(&["a.txt"]);
        v.switch_to(View::F7);
        assert_eq!(v.ws.books.len(), 1);
        assert!(v.ws.books[0].is_empty());
        assert_eq!(v.ws_current_slot(), Some(0));
    }

    #[test]
    fn tab_en_f7_llena_la_ranura_y_lo_deja_guardado() {
        let (_d, mut v) = corpus_app(&["a.txt"]);
        v.switch_to(View::F7);
        v.ws_tab();
        assert_eq!(v.ws.books[0].path, "a.txt");
        // Y sobrevive a releer del disco.
        assert_eq!(corpus::WorkingSet::load(&v.o_dir()).books[0].path, "a.txt");
    }

    #[test]
    fn el_cursor_de_f7_salta_los_separadores() {
        let (_d, mut v) = corpus_app(&["a.txt", "b.txt"]);
        v.switch_to(View::F7);
        v.ws_add_slot();
        assert_eq!(v.ws.books.len(), 2);
        for _ in 0..6 {
            v.ws_move(2);
            assert!(v.ws_current_slot().is_some(), "cayó sobre un separador");
        }
    }

    #[test]
    fn enter_en_una_ranura_vacia_no_abre_nada() {
        let (_d, mut v) = corpus_app(&["a.txt"]);
        v.switch_to(View::F7);
        assert!(!v.open_o_book());
        assert!(v.o_file.is_empty());
    }

    #[test]
    fn enter_en_una_ranura_llena_abre_el_libro_en_f6() {
        let (_d, mut v) = corpus_app(&["a.txt"]);
        v.switch_to(View::F7);
        v.ws_tab();
        assert!(v.open_o_book());
        assert_eq!(v.o_file, "a.txt");
        assert!(v.o_ring.lines.contains(&"primera linea".to_string()));
    }

    #[test]
    fn f6_recuerda_por_donde_ibas_en_cada_libro() {
        let (_d, mut v) = corpus_app(&["a.txt"]);
        v.switch_to(View::F7);
        v.ws_tab();
        v.open_o_book();
        v.o_ring.index = 2;
        v.view = View::F6;
        v.switch_to(View::F7); // salir guarda
        v.o_file.clear();
        v.open_o_book();
        assert_eq!(v.o_ring.index, 2, "volvió al principio en vez de a donde estabas");
    }

    #[test]
    fn el_libro_abierto_no_se_puede_sacar_del_conjunto() {
        let (_d, mut v) = corpus_app(&["a.txt"]);
        v.switch_to(View::F7);
        v.ws_tab();
        v.open_o_book();
        v.ws_remove_slot();
        assert_eq!(v.ws.books.len(), 1);
        assert_eq!(v.ws.books[0].path, "a.txt", "se llevó puesto el libro que estaba leyendo");
        assert!(v.status.contains("abierto"));
    }

    #[test]
    fn el_oraculo_saca_una_linea_del_corpus() {
        let (_d, mut v) = corpus_app(&["a.txt"]);
        v.switch_to(View::F8);
        assert!(v.oracle == "primera linea" || v.oracle == "segunda linea");
    }

    #[test]
    fn quedarse_con_la_linea_del_oraculo_la_mete_en_el_documento() {
        let (_d, mut v) = corpus_app(&["a.txt"]);
        v.ring.index = 1; // sobre 'mi texto'
        v.switch_to(View::F8);
        let salida = v.oracle.clone();
        v.keep_oracle_line().unwrap();
        assert_eq!(v.ring.lines[2], salida);
        assert_eq!(v.ring.index, 2);
        // Y quedó guardado en disco.
        assert!(void::load_doc(&v.current_file).lines.contains(&salida));
    }

    #[test]
    fn el_oraculo_tira_otra_despues_de_quedarse_con_una() {
        let (_d, mut v) = corpus_app(&["a.txt"]);
        v.switch_to(View::F8);
        v.keep_oracle_line().unwrap();
        assert!(!v.oracle.is_empty());
    }

    #[test]
    fn sin_corpus_el_oraculo_no_rompe_nada() {
        let (_d, mut v) = app(&[".", "a"]);
        v.switch_to(View::F8);
        assert_eq!(v.oracle, "...");
        v.keep_oracle_line().unwrap(); // no mete "..." en el texto
        assert_eq!(v.ring.lines, vec![".".to_string(), "a".into()]);
    }

    #[test]
    fn f6_y_f7_son_vistas_a_las_que_se_vuelve_al_reiniciar() {
        let (_d, mut v) = corpus_app(&["a.txt"]);
        v.switch_to(View::F7);
        assert_eq!(Config::load(&v.void_dir).last_view.as_deref(), Some("F7"));
        v.switch_to(View::F6);
        assert_eq!(Config::load(&v.void_dir).last_view.as_deref(), Some("F6"));
        // El oráculo no: es una tirada, no un lugar donde se está.
        v.switch_to(View::F8);
        assert_eq!(Config::load(&v.void_dir).last_view.as_deref(), Some("F6"));
    }

    // ── Alt+→ en F2: mandar desde donde estás parado ────────────────────────────

    #[test]
    fn sobre_una_linea_se_manda_esa_linea() {
        let (_d, mut v) = book();
        v.ring.lines = vec![".".into(), "primera".into(), "segunda".into()];
        v.ring.index = 1;
        let (taken, rest) = v.doc_send_scope().unwrap();
        assert_eq!(taken, vec!["primera".to_string()]);
        assert_eq!(rest, vec![".".to_string(), "segunda".into()]);
    }

    #[test]
    fn sobre_un_punto_se_manda_el_parrafo_que_abre() {
        let (_d, mut v) = book();
        v.ring.lines = vec![
            ".".into(), "a1".into(), "a2".into(),
            ".".into(), "b1".into(),
        ];
        v.ring.index = 0; // sobre el primer punto
        let (taken, rest) = v.doc_send_scope().unwrap();
        assert_eq!(taken, vec!["a1".to_string(), "a2".into()]);
        assert_eq!(rest, vec![".".to_string(), "b1".into()], "quedó un punto huérfano");
    }

    #[test]
    fn el_punto_del_medio_se_lleva_su_parrafo_y_no_el_de_arriba() {
        let (_d, mut v) = book();
        v.ring.lines = vec![
            ".".into(), "a1".into(),
            ".".into(), "b1".into(), "b2".into(),
        ];
        v.ring.index = 2;
        let (taken, rest) = v.doc_send_scope().unwrap();
        assert_eq!(taken, vec!["b1".to_string(), "b2".into()]);
        assert_eq!(rest, vec![".".to_string(), "a1".into()]);
    }

    #[test]
    fn un_punto_sin_parrafo_debajo_no_manda_nada() {
        let (_d, mut v) = book();
        v.ring.lines = vec![".".into(), "a".into(), ".".into()];
        v.ring.index = 2; // el punto final, sin nada abajo
        assert!(v.doc_send_scope().is_none());
    }

    #[test]
    fn el_panel_no_se_abre_si_no_hay_nada_para_mandar() {
        let (_d, mut v) = book();
        v.ring.lines = vec![".".into(), "a".into(), ".".into()];
        v.ring.index = 2;
        v.doc_open_picker();
        assert!(!v.picker_open, "se abrió para después no hacer nada");
        assert!(v.status.contains("Nada para enviar"));
    }

    #[test]
    fn el_panel_se_abre_sobre_una_linea() {
        let (_d, mut v) = book();
        v.ring.lines = vec![".".into(), "algo".into()];
        v.ring.index = 1;
        v.doc_open_picker();
        assert!(v.picker_open);
        assert!(!v.library.entries.is_empty(), "el panel se abrió sin biblioteca");
    }

    #[test]
    fn mandar_una_linea_la_saca_de_aca_y_la_pone_alla() {
        let (_d, mut v) = book();
        v.ring.lines = vec![".".into(), "se va".into(), "se queda".into()];
        v.ring.index = 1;
        assert!(v.doc_send_to("Dos.txt").unwrap());

        assert_eq!(v.ring.lines, vec![".".to_string(), "se queda".into()]);
        let destino = void::load_doc(&library::chapter_path(&v.void_dir, "Dos.txt")).lines;
        assert!(destino.contains(&"se va".to_string()), "no llegó: {destino:?}");
        assert!(destino.contains(&"de dos".to_string()), "pisó lo que ya había");
    }

    #[test]
    fn lo_que_llega_entra_como_parrafo_propio() {
        let (_d, mut v) = book();
        v.ring.lines = vec![".".into(), "recien llegado".into()];
        v.ring.index = 1;
        v.doc_send_to("Dos.txt").unwrap();
        let d = void::load_doc(&library::chapter_path(&v.void_dir, "Dos.txt")).lines;
        let i = d.iter().position(|l| l == "recien llegado").unwrap();
        assert_eq!(d[i - 1], ".", "se pegó al párrafo anterior");
    }

    #[test]
    fn mandar_a_este_mismo_archivo_no_hace_nada() {
        let (_d, mut v) = book();
        v.ring.lines = vec![".".into(), "algo".into()];
        v.ring.index = 1;
        let antes = v.ring.lines.clone();
        assert!(!v.doc_send_to("Uno.txt").unwrap()); // Uno.txt ES el activo
        assert_eq!(v.ring.lines, antes);
    }

    #[test]
    fn mandar_es_un_solo_paso_de_deshacer_en_los_dos_archivos() {
        let (_d, mut v) = book();
        v.ring.lines = vec![".".into(), "viajera".into(), "queda".into()];
        v.save().unwrap();
        let origen_antes = void::load_doc(&v.current_file).lines;
        let destino_antes = void::load_doc(&library::chapter_path(&v.void_dir, "Dos.txt")).lines;
        v.ring.index = 1;
        v.doc_send_to("Dos.txt").unwrap();

        v.undo().unwrap();
        assert_eq!(void::load_doc(&v.current_file).lines, origen_antes, "no volvió al origen");
        assert_eq!(
            void::load_doc(&library::chapter_path(&v.void_dir, "Dos.txt")).lines,
            destino_antes,
            "quedó en el destino después de deshacer"
        );
    }

    #[test]
    fn mandar_cierra_el_panel() {
        let (_d, mut v) = book();
        v.ring.lines = vec![".".into(), "algo".into()];
        v.ring.index = 1;
        v.doc_open_picker();
        v.doc_send_to("Dos.txt").unwrap();
        assert!(!v.picker_open);
    }

    #[test]
    fn f5_sigue_mandando_parrafos_como_siempre() {
        // El refactor comparte código con F2; F5 no puede cambiar de conducta.
        let (_d, mut v) = book();
        v.ring.lines = vec![".".into(), "p1a".into(), "p1b".into()];
        v.switch_to(View::F5);
        v.para_idx = 0;
        assert!(v.send_para_to("Dos.txt").unwrap());
        let d = void::load_doc(&library::chapter_path(&v.void_dir, "Dos.txt")).lines;
        assert!(d.contains(&"p1a".to_string()) && d.contains(&"p1b".to_string()));
    }

    // ── F4: the book as a book ───────────────────────────────────────────────────

    #[test]
    fn f4_shows_the_active_file_as_prose() {
        let (_d, mut v) = app(&[".", "Una frase.", "Otra frase.", ".", "Segundo."]);
        v.switch_to(View::F4);
        assert_eq!(v.reading.len(), 1);
        assert_eq!(
            v.reading[0].paragraphs,
            vec!["Una frase. Otra frase.".to_string(), "Segundo.".to_string()]
        );
    }

    #[test]
    fn a_reading_section_keeps_its_own_name_and_its_raw_lines() {
        // The sale bundle needs what the page does not: the chapter's name as it is
        // (not the shouted title) and the file's lines before they are joined.
        let (_d, mut v) = book();
        v.switch_to(View::F3);
        v.library.index = v.library.position("Dos.txt").unwrap();
        v.switch_to(View::F4);
        assert_eq!(v.reading[0].title, "DOS");
        assert_eq!(v.reading[0].name, "Dos");
        assert_eq!(v.reading[0].lines, void::load_doc(&library::chapter_path(&v.void_dir, "Dos.txt")).lines);
    }

    #[test]
    fn f4_opens_on_the_paragraph_you_were_editing() {
        let (_d, mut v) = app(&[".", "uno", ".", "dos", ".", "tres"]);
        v.ring.index = 5; // 'tres', the third paragraph
        v.switch_to(View::F4);
        assert_eq!(v.open_at_para, 2);
    }

    #[test]
    fn f4_on_a_separator_in_f3_reads_the_whole_book_in_order() {
        let (_d, mut v) = book();
        v.library = Library {
            entries: vec![".".into(), "Uno.txt".into(), "Dos.txt".into()],
            index: 0, // on the separator
        };
        v.save_library().unwrap();
        v.view = View::F3;
        v.switch_to(View::F4);
        let titles: Vec<&str> = v.reading.iter().map(|s| s.title.as_str()).collect();
        assert_eq!(titles, vec!["UNO", "DOS"]);
    }

    #[test]
    fn reading_a_book_skips_the_scratch_portal() {
        let (_d, mut v) = book();
        let i = v.void_dir.join("I");
        void::atomic_write(&i.join("0.txt"), &[".".into(), "borrador".into()], false).unwrap();
        v.library = Library {
            entries: vec![".".into(), "0.txt".into(), "Uno.txt".into()],
            index: 0,
        };
        v.save_library().unwrap();
        v.view = View::F3;
        v.switch_to(View::F4);
        let titles: Vec<&str> = v.reading.iter().map(|s| s.title.as_str()).collect();
        assert_eq!(titles, vec!["UNO"]); // the scratch is not a chapter
    }

    #[test]
    fn f4_on_a_chapter_in_f3_reads_that_one_and_starts_at_its_beginning() {
        let (_d, mut v) = book();
        v.switch_to(View::F3);
        v.library.index = v.library.position("Dos.txt").unwrap();
        v.ring.index = 1; // where F2 happened to be, in a DIFFERENT file
        v.switch_to(View::F4);
        assert_eq!(v.reading.len(), 1);
        assert_eq!(v.reading[0].title, "DOS");
        // 'open where I was' only makes sense when it's the file being shown.
        assert_eq!(v.open_at_para, 0);
    }

    #[test]
    fn turning_pages_stops_at_both_ends() {
        let (_d, mut v) = app(&[".", "a"]);
        v.turn_page(-1, 3);
        assert_eq!(v.page, 0);
        v.turn_page(5, 3);
        assert_eq!(v.page, 2);
        v.turn_page(1, 3);
        assert_eq!(v.page, 2); // a book has a last page
    }

    #[test]
    fn turning_pages_in_an_empty_book_does_nothing() {
        let (_d, mut v) = app(&["."]);
        v.turn_page(1, 0);
        assert_eq!(v.page, 0);
    }

    #[test]
    fn f4_is_a_view_a_restart_resumes_into() {
        let (_d, mut v) = app(&[".", "a"]);
        v.switch_to(View::F4);
        assert_eq!(Config::load(&v.void_dir).last_view.as_deref(), Some("F4"));
    }

    #[test]
    fn ctrl_s_en_f4_deja_un_pdf_de_verdad_en_el_disco() {
        let (_d, mut v) = app(&[".", "Una frase.", "Otra frase.", ".", "Segundo parrafo."]);
        v.switch_to(View::F4);
        let dest = v.export_pdf().expect("no exportó");
        assert!(dest.exists(), "el PDF no llegó al disco");
        let bytes = std::fs::read(&dest).unwrap();
        assert!(bytes.starts_with(b"%PDF"), "lo que quedó no es un PDF");
        assert!(v.status.contains("PDF"));
    }

    // ── Ctrl+Shift+A: the sale bundle — PDF + EPUB + TXT (test_sale_bundle.py) ──

    /// F4 open on one chapter ("Dos") or on the whole book, from `book()`.
    fn bundle_app(whole_book: bool) -> (tempfile::TempDir, Voider) {
        let (d, mut v) = book();
        v.library = Library {
            entries: vec![".".into(), "Uno.txt".into(), "Dos.txt".into()],
            index: if whole_book { 0 } else { 2 },
        };
        v.save_library().unwrap();
        v.view = View::F3;
        v.switch_to(View::F4);
        (d, v)
    }

    fn bundle_files(d: &tempfile::TempDir, name: &str) -> std::path::PathBuf {
        d.path().join("gPTA_books").join(name)
    }

    #[test]
    fn a_single_chapter_names_its_own_bundle_and_a_whole_book_asks() {
        let (_d, v) = bundle_app(false);
        assert_eq!(v.bundle_default_name(), Some("Dos".to_string()));
        let (_d, v) = bundle_app(true);
        assert_eq!(v.bundle_default_name(), None); // a whole book has no single title
    }

    #[test]
    fn a_single_chapter_writes_all_three_formats() {
        let (d, mut v) = bundle_app(false);
        let out = v.export_sale_bundle("Dos", bundle::Lang::Es).unwrap().unwrap();
        assert_eq!(out, bundle_files(&d, "Dos"));
        for ext in ["pdf", "epub", "txt"] {
            assert!(out.join(format!("Dos.{ext}")).is_file(), "no Dos.{ext}");
        }
    }

    #[test]
    fn the_pdf_and_the_epub_are_real_files_not_empty_shells() {
        let (d, mut v) = bundle_app(false);
        v.export_sale_bundle("Dos", bundle::Lang::Es).unwrap();
        let dir = bundle_files(&d, "Dos");
        let pdf = std::fs::read(dir.join("Dos.pdf")).unwrap();
        let epub = std::fs::read(dir.join("Dos.epub")).unwrap();
        assert!(pdf.starts_with(b"%PDF") && pdf.len() > 500, "{} bytes", pdf.len());
        assert!(epub.starts_with(b"PK") && epub.len() > 500, "{} bytes", epub.len());
    }

    #[test]
    fn the_txt_holds_the_chapters_real_text() {
        let (d, mut v) = bundle_app(false);
        v.export_sale_bundle("Dos", bundle::Lang::Es).unwrap();
        let txt = std::fs::read_to_string(bundle_files(&d, "Dos").join("Dos.txt")).unwrap();
        assert!(txt.contains("de dos"));
        assert!(!txt.contains("de uno")); // only the chapter that was shown
    }

    #[test]
    fn a_whole_book_bundles_every_chapter_with_fences_in_the_txt() {
        let (d, mut v) = bundle_app(true);
        v.export_sale_bundle("MiLibro", bundle::Lang::Es).unwrap();
        let dir = bundle_files(&d, "MiLibro");
        for ext in ["pdf", "epub", "txt"] {
            assert!(dir.join(format!("MiLibro.{ext}")).is_file(), "no MiLibro.{ext}");
        }
        let txt = std::fs::read_to_string(dir.join("MiLibro.txt")).unwrap();
        assert!(txt.contains("/Uno") && txt.contains("/Dos"));
        assert!(txt.contains("de uno") && txt.contains("de dos"));
    }

    #[test]
    fn an_empty_or_blank_name_writes_nothing() {
        let (d, mut v) = bundle_app(true);
        assert!(v.export_sale_bundle("", bundle::Lang::Es).unwrap().is_none());
        assert!(v.export_sale_bundle("   ", bundle::Lang::Es).unwrap().is_none());
        assert!(!d.path().join("gPTA_books").exists());
    }

    #[test]
    fn nothing_to_read_means_nothing_to_bundle() {
        let (d, mut v) = app(&["."]);
        v.reading.clear();
        assert!(v.export_sale_bundle("X", bundle::Lang::Es).unwrap().is_none());
        assert!(v.status.contains("Nada para exportar"));
        assert!(!d.path().join("gPTA_books").exists());
    }

    #[test]
    fn a_configured_folder_receives_the_bundle_instead_of_the_local_one() {
        let (d, mut v) = bundle_app(false);
        let dest = d.path().join("sitio").join("libros");
        v.config.sale_bundle_dir_es = dest.to_string_lossy().to_string();
        v.export_sale_bundle("Dos", bundle::Lang::Es).unwrap();
        assert!(dest.join("Dos").join("Dos.pdf").is_file());
        assert!(!d.path().join("gPTA_books").exists());
    }

    #[test]
    fn the_epub_declares_the_language_it_was_asked_for() {
        let (d, mut v) = bundle_app(false);
        v.export_sale_bundle("Dos", bundle::Lang::En).unwrap();
        let epub = std::fs::read(bundle_files(&d, "Dos").join("Dos.epub")).unwrap();
        let text = String::from_utf8_lossy(&epub);
        assert!(text.contains("<dc:language>en</dc:language>"));
    }

    // ── F10: the carousel's frame (test_settings_panel_carousel.py) ──────────

    #[test]
    fn the_frame_starts_at_4_5_and_cycles_through_every_preset_then_custom() {
        let (_d, mut v) = app(&["."]);
        assert_eq!(v.config.carousel_preset, "4:5");
        let mut seen = vec![v.config.carousel_preset.clone()];
        for _ in 0..4 {
            v.settings_step_carousel(1);
            seen.push(v.config.carousel_preset.clone());
        }
        assert_eq!(seen, vec!["4:5", "1.91:1", "custom", "1:1", "4:5"]);
    }

    #[test]
    fn stepping_back_goes_the_other_way_and_wraps() {
        let (_d, mut v) = app(&["."]);
        v.settings_step_carousel(-1);
        assert_eq!(v.config.carousel_preset, "1:1");
        v.settings_step_carousel(-1);
        assert_eq!(v.config.carousel_preset, "custom"); // wraps round
    }

    #[test]
    fn the_chosen_frame_is_remembered_across_runs_and_sets_the_size() {
        let (d, mut v) = app(&["."]);
        v.settings_step_carousel(-1); // 1:1
        assert_eq!(v.carousel_size(), (1080, 1080));
        assert_eq!(Config::load(&v.void_dir).carousel_preset, "1:1");
        let _ = d;
    }

    #[test]
    fn a_custom_frame_takes_its_size_from_the_config_and_can_be_nudged() {
        let (_d, mut v) = app(&["."]);
        v.config.carousel_preset = "custom".into();
        v.settings_step_carousel_size(1, 0);
        assert_eq!(v.config.carousel_w, 1080 + 10);
        v.settings_step_carousel_size(0, -1);
        assert_eq!(v.config.carousel_h, 1350 - 10);
        assert_eq!(v.carousel_size(), (1090, 1340));
    }

    #[test]
    fn the_size_cannot_be_nudged_unless_the_frame_is_custom_and_never_below_the_minimum() {
        let (_d, mut v) = app(&["."]);
        v.settings_step_carousel_size(1, 1);
        assert_eq!((v.config.carousel_w, v.config.carousel_h), (1080, 1350)); // a preset is not edited
        v.config.carousel_preset = "custom".into();
        v.config.carousel_w = 120;
        for _ in 0..50 {
            v.settings_step_carousel_size(-1, 0);
        }
        assert!(v.config.carousel_w >= 100, "{}", v.config.carousel_w);
    }

    #[test]
    fn changing_the_frame_while_previewing_redraws_the_preview() {
        let (_d, mut v) = bundle_app(false);
        v.toggle_carousel_view();
        v.settings_step_carousel(-1); // 1:1
        v.switch_to(View::F4);
        assert_eq!(v.carousel_size(), (1080, 1080));
        assert!(!v.carousel_slides.is_empty());
    }

    // ── the font the book is set in carries the hyphenation setting ──────────

    #[test]
    fn the_type_font_follows_the_configured_hyphenation() {
        let (_d, mut v) = app(&["."]);
        assert_eq!(v.type_font().hyphenation(), hyphen::Mode::Auto);
        v.config.reading_hyphen_lang = "es".into();
        assert_eq!(v.type_font().hyphenation(), hyphen::Mode::Fixed(hyphen::Lang::Es));
        v.config.reading_hyphen_lang = String::new();
        assert_eq!(v.type_font().hyphenation(), hyphen::Mode::Off);
    }

    // ── Ctrl+Shift+V: the carousel preview in F4 (test_f4_carousel_view.py) ──

    #[test]
    fn the_preview_is_off_until_toggled_and_toggling_flips_it() {
        let (_d, mut v) = bundle_app(false);
        assert!(!v.carousel_view);
        v.toggle_carousel_view();
        assert!(v.carousel_view);
        v.toggle_carousel_view();
        assert!(!v.carousel_view);
    }

    #[test]
    fn toggling_goes_back_to_the_first_slide() {
        let (_d, mut v) = bundle_app(true);
        v.page = 1;
        v.toggle_carousel_view();
        assert_eq!(v.page, 0);
    }

    #[test]
    fn the_preview_shows_the_title_slide_first_and_then_the_body() {
        let (_d, mut v) = bundle_app(false);
        v.toggle_carousel_view();
        assert_eq!(v.carousel_slides.len(), 2);
        assert!(matches!(v.carousel_slides[0], slides::Slide::Title(ref t) if t == "Dos"));
        assert!(matches!(v.carousel_slides[1], slides::Slide::Body(_)));
    }

    #[test]
    fn the_preview_is_exactly_what_the_export_writes() {
        let (d, mut v) = bundle_app(true);
        v.toggle_carousel_view();
        let previewed = v.carousel_slides.len();
        v.export_carousel("MiLibro").unwrap();
        assert_eq!(slides_in(&d, "MiLibro").len(), previewed);
    }

    #[test]
    fn leaving_and_coming_back_to_f4_keeps_the_mode_and_follows_the_chapter() {
        let (_d, mut v) = bundle_app(false); // Dos
        v.toggle_carousel_view();
        v.switch_to(View::F3);
        v.library.index = v.library.position("Uno.txt").unwrap();
        v.switch_to(View::F4);
        assert!(v.carousel_view, "the mode survives a trip to F3");
        assert!(matches!(v.carousel_slides[0], slides::Slide::Title(ref t) if t == "Uno"));
    }

    #[test]
    fn the_preview_follows_the_configured_frame() {
        let (_d, mut v) = bundle_app(false);
        v.config.carousel_preset = "1:1".into();
        v.toggle_carousel_view();
        assert_eq!(v.carousel_size(), (1080, 1080));
        v.config.carousel_preset = "custom".into();
        v.config.carousel_w = 800;
        v.config.carousel_h = 600;
        assert_eq!(v.carousel_size(), (800, 600));
    }

    #[test]
    fn with_nothing_to_read_the_preview_has_no_slides_and_does_not_crash() {
        let (_d, mut v) = app(&["."]);
        v.reading.clear();
        v.toggle_carousel_view();
        assert!(v.carousel_slides.is_empty());
    }

    #[test]
    fn the_page_count_in_carousel_mode_is_the_slide_count() {
        let (_d, mut v) = bundle_app(true);
        assert_eq!(v.f4_page_count(7), 7); // book mode: whatever the layout measured
        v.toggle_carousel_view();
        assert_eq!(v.f4_page_count(7), v.carousel_slides.len());
    }

    // ── Ctrl+Shift+C: the Instagram carousel (test_carousel_export.py) ───────

    fn slides_in(d: &tempfile::TempDir, folder: &str) -> Vec<String> {
        let dir = d.path().join("carousel").join(folder);
        let mut names: Vec<String> = match std::fs::read_dir(&dir) {
            Ok(rd) => rd.filter_map(|e| e.ok()).map(|e| e.file_name().to_string_lossy().into_owned()).filter(|n| n.ends_with(".png")).collect(),
            Err(_) => Vec::new(),
        };
        // by the number each starts with, so 10 comes after 9
        names.sort_by_key(|n| n.split(|c: char| !c.is_ascii_digit()).next().and_then(|d| d.parse::<u32>().ok()).unwrap_or(0));
        names
    }

    fn size_of(d: &tempfile::TempDir, folder: &str, name: &str) -> (u32, u32) {
        let img = slides::read_png(&d.path().join("carousel").join(folder).join(name)).expect("a readable png");
        (img.w, img.h)
    }

    #[test]
    fn a_single_chapter_writes_its_own_title_slide_and_body() {
        let (d, mut v) = bundle_app(false); // highlights Dos
        v.export_carousel("Dos").unwrap().unwrap();
        let slides = slides_in(&d, "Dos");
        assert!(slides.contains(&"1_titulo.png".to_string()));
        assert!(slides.contains(&"2.png".to_string()));
        assert!(!d.path().join("carousel").join("Uno").exists());
    }

    #[test]
    fn a_whole_book_numbers_its_slides_continuously_across_chapters() {
        let (d, mut v) = bundle_app(true);
        v.export_carousel("MiLibro").unwrap();
        // Uno's title (1), Uno's body (2), Dos's title (3), Dos's body (4) — no gaps
        assert_eq!(slides_in(&d, "MiLibro"), vec!["1_titulo.png", "2.png", "3_titulo.png", "4.png"]);
    }

    #[test]
    fn a_blank_name_writes_nothing() {
        let (d, mut v) = bundle_app(true);
        assert!(v.export_carousel("   ").unwrap().is_none());
        assert!(!d.path().join("carousel").exists());
    }

    #[test]
    fn with_nothing_to_read_there_is_nothing_to_export() {
        let (d, mut v) = app(&["."]);
        v.reading.clear();
        assert!(v.export_carousel("X").unwrap().is_none());
        assert!(v.status.contains("Nada para exportar"));
        assert!(!d.path().join("carousel").exists());
    }

    #[test]
    fn the_default_frame_is_4_5() {
        let (d, mut v) = bundle_app(false);
        v.export_carousel("Dos").unwrap();
        assert_eq!(size_of(&d, "Dos", "1_titulo.png"), (1080, 1350));
        assert_eq!(size_of(&d, "Dos", "2.png"), (1080, 1350));
    }

    #[test]
    fn the_configured_preset_sets_the_size() {
        let (d, mut v) = bundle_app(false);
        v.config.carousel_preset = "1:1".into();
        v.export_carousel("Dos").unwrap();
        assert_eq!(size_of(&d, "Dos", "1_titulo.png"), (1080, 1080));
    }

    #[test]
    fn custom_dimensions_are_honoured() {
        let (d, mut v) = bundle_app(false);
        v.config.carousel_preset = "custom".into();
        v.config.carousel_w = 800;
        v.config.carousel_h = 600;
        v.export_carousel("Dos").unwrap();
        assert_eq!(size_of(&d, "Dos", "1_titulo.png"), (800, 600));
        assert_eq!(size_of(&d, "Dos", "2.png"), (800, 600));
    }

    #[test]
    fn the_title_slide_and_the_body_slide_are_not_blank_and_not_the_same() {
        let (d, mut v) = bundle_app(false);
        v.export_carousel("Dos").unwrap();
        let dir = d.path().join("carousel").join("Dos");
        let title = slides::read_png(&dir.join("1_titulo.png")).unwrap();
        let body = slides::read_png(&dir.join("2.png")).unwrap();
        assert!(title.rgb.iter().any(|&b| b != 0), "the title slide is blank");
        assert!(body.rgb.iter().any(|&b| b != 0), "the body slide is blank");
        assert_ne!(title.rgb, body.rgb);
    }

    #[test]
    fn a_long_chapter_produces_several_body_slides() {
        let (d, mut v) = book();
        let lines: Vec<String> = (0..120)
            .flat_map(|i| [format!("Parrafo numero {i} con texto suficiente para ocupar espacio real en la pagina de verdad."), ".".to_string()])
            .collect();
        void::atomic_write(&d.path().join("I").join("Largo.txt"), &lines, false).unwrap();
        v.library = Library { entries: vec![".".into(), "Largo.txt".into()], index: 1 };
        v.save_library().unwrap();
        v.view = View::F3;
        v.switch_to(View::F4);
        v.export_carousel("Largo").unwrap();
        let body: Vec<String> = slides_in(&d, "Largo").into_iter().filter(|s| s != "1_titulo.png").collect();
        assert!(body.len() > 1, "a long chapter should spill onto several slides, got {body:?}");
        assert_eq!(body.first().unwrap(), "2.png");
    }

    #[test]
    fn exporting_twice_replaces_the_slides_it_wrote_before() {
        let (d, mut v) = bundle_app(false);
        v.export_carousel("Dos").unwrap();
        v.export_carousel("Dos").unwrap();
        assert_eq!(slides_in(&d, "Dos"), vec!["1_titulo.png", "2.png"]);
    }

    // ── Ctrl+Shift+B: with a cover and a countercover (test_carousel_export_cover.py)

    fn cover_png(d: &tempfile::TempDir) -> PathBuf {
        let p = d.path().join("portada.png");
        slides::Canvas::new(300, 300, [0x20, 0x40, 0x60]).save_png(&p).unwrap();
        p
    }

    #[test]
    fn a_single_chapter_gets_a_cover_and_a_countercover() {
        let (d, mut v) = bundle_app(false);
        let cover = cover_png(&d);
        v.export_carousel_with_cover("Dos", &cover).unwrap().unwrap();
        let slides = slides_in(&d, "Dos");
        assert_eq!(slides.first().unwrap(), "1_portada.png");
        assert!(slides.last().unwrap().ends_with("_contratapa.png"));
        assert!(slides.contains(&"2_titulo.png".to_string()));
        assert!(slides.contains(&"3.png".to_string()));
    }

    #[test]
    fn a_whole_book_with_a_cover_is_named_by_what_was_typed() {
        let (d, mut v) = bundle_app(true);
        let cover = cover_png(&d);
        v.export_carousel_with_cover("MiLibro", &cover).unwrap();
        let slides = slides_in(&d, "MiLibro");
        assert_eq!(slides.first().unwrap(), "1_portada.png");
        assert!(slides.last().unwrap().ends_with("_contratapa.png"));
        // cover, [Uno: title, body], [Dos: title, body], countercover
        assert_eq!(slides, vec!["1_portada.png", "2_titulo.png", "3.png", "4_titulo.png", "5.png", "6_contratapa.png"]);
    }

    #[test]
    fn the_countercover_follows_the_configured_ratio() {
        let (d, mut v) = bundle_app(false);
        v.config.carousel_preset = "1:1".into();
        let cover = cover_png(&d);
        v.export_carousel_with_cover("Dos", &cover).unwrap();
        let last = slides_in(&d, "Dos").pop().unwrap();
        assert_eq!(size_of(&d, "Dos", &last), (1080, 1080));
        assert_eq!(size_of(&d, "Dos", "1_portada.png"), (1080, 1080));
    }

    #[test]
    fn a_typed_name_cannot_write_outside_the_carousel_folder() {
        let (d, mut v) = bundle_app(false);
        let out = v.export_carousel("../escape").unwrap().unwrap();
        assert_eq!(out.parent().unwrap(), d.path().join("carousel"));
        assert!(!d.path().join("escape").exists());
        assert_eq!(v.export_carousel("..").unwrap(), None); // nothing but dots is no name
    }

    #[test]
    fn a_typed_name_cannot_write_outside_the_bundle_folder() {
        let (d, mut v) = bundle_app(false);
        let out = v.export_sale_bundle("../escape", bundle::Lang::Es).unwrap().unwrap();
        assert_eq!(out.parent().unwrap(), d.path().join("gPTA_books"));
        assert!(!d.path().join("escape").exists());
    }

    #[test]
    fn a_cover_that_cannot_be_read_still_exports_on_plain_paper() {
        let (d, mut v) = bundle_app(false);
        v.export_carousel_with_cover("Dos", &d.path().join("no-existe.png")).unwrap().unwrap();
        assert!(slides_in(&d, "Dos").contains(&"1_portada.png".to_string()));
    }

    #[test]
    fn the_cover_carries_the_mark() {
        let (d, mut v) = bundle_app(false);
        let black = d.path().join("negra.png");
        slides::Canvas::new(300, 300, [0, 0, 0]).save_png(&black).unwrap();
        v.export_carousel_with_cover("Dos", &black).unwrap();
        let cover = slides::read_png(&d.path().join("carousel").join("Dos").join("1_portada.png")).unwrap();
        assert!(cover.rgb.iter().any(|&b| b != 0), "the 'I' mark was not drawn on the cover");
    }

    // ── Ctrl+Shift+C / Ctrl+Shift+B: how the carousel is asked for ───────────

    #[test]
    fn a_single_chapter_exports_its_carousel_straight_away() {
        let (d, mut v) = bundle_app(false);
        v.begin_carousel();
        assert!(v.bundle_prompt.is_none(), "a lone chapter names its own folder");
        assert_eq!(slides_in(&d, "Dos"), vec!["1_titulo.png", "2.png"]);
        assert!(v.status.contains("Carrusel"));
    }

    #[test]
    fn a_whole_book_asks_for_a_name_and_then_exports_with_no_language_step() {
        let (d, mut v) = bundle_app(true);
        v.begin_carousel();
        assert_eq!(v.bundle_prompt.as_ref().unwrap().stage, BundleStage::Name);
        v.bundle_type("MiLibro");
        v.bundle_confirm().unwrap();
        assert!(v.bundle_prompt.is_none(), "a carousel has no language to ask");
        assert_eq!(slides_in(&d, "MiLibro").len(), 4);
    }

    #[test]
    fn a_blank_name_cancels_the_carousel() {
        let (d, mut v) = bundle_app(true);
        v.begin_carousel();
        v.bundle_type("  ");
        v.bundle_confirm().unwrap();
        assert!(v.bundle_prompt.is_none());
        assert!(!d.path().join("carousel").exists());
    }

    #[test]
    fn nothing_to_read_opens_neither_a_prompt_nor_a_browser() {
        let (_d, mut v) = app(&["."]);
        v.reading.clear();
        v.begin_carousel();
        v.begin_carousel_with_cover();
        assert!(v.bundle_prompt.is_none() && v.browser.is_none());
        assert!(v.status.contains("Nada para exportar"));
    }

    #[test]
    fn the_cover_picker_opens_where_the_covers_are_kept() {
        let (d, mut v) = bundle_app(false);
        std::fs::create_dir_all(d.path().join("covers")).unwrap();
        std::fs::write(d.path().join("covers").join("cover_1.png"), "x").unwrap();
        v.begin_carousel_with_cover();
        let b = v.browser.as_ref().expect("the browser opens");
        assert_eq!(b.purpose, browse::Purpose::Cover);
        assert_eq!(b.dir, d.path().join("covers"));
        assert!(!d.path().join("carousel").exists(), "nothing is written before a cover is chosen");
    }

    #[test]
    fn the_cover_picker_falls_back_to_the_void_when_there_is_no_covers_folder() {
        let (d, mut v) = bundle_app(false);
        v.begin_carousel_with_cover();
        assert_eq!(v.browser.as_ref().unwrap().dir, d.path().to_path_buf());
    }

    #[test]
    fn cancelling_the_cover_picker_writes_nothing() {
        let (d, mut v) = bundle_app(false);
        v.begin_carousel_with_cover();
        v.cancel_browser();
        assert!(!d.path().join("carousel").exists());
    }

    fn pick(v: &mut Voider, file: &str) {
        let b = v.browser.as_mut().expect("a browser is open");
        b.index = b.entries.iter().position(|e| e.name == file).expect("the file is listed");
        v.browser_enter(false).unwrap();
    }

    #[test]
    fn choosing_a_cover_for_a_single_chapter_exports_with_it_right_away() {
        let (d, mut v) = bundle_app(false);
        std::fs::create_dir_all(d.path().join("covers")).unwrap();
        slides::Canvas::new(200, 200, [30, 60, 90]).save_png(&d.path().join("covers").join("c.png")).unwrap();
        v.begin_carousel_with_cover();
        pick(&mut v, "c.png");
        assert!(v.browser.is_none());
        let slides = slides_in(&d, "Dos");
        assert_eq!(slides.first().unwrap(), "1_portada.png");
        assert!(slides.last().unwrap().ends_with("_contratapa.png"));
    }

    #[test]
    fn choosing_a_cover_for_a_whole_book_then_asks_for_the_name() {
        let (d, mut v) = bundle_app(true);
        std::fs::create_dir_all(d.path().join("covers")).unwrap();
        slides::Canvas::new(200, 200, [30, 60, 90]).save_png(&d.path().join("covers").join("c.png")).unwrap();
        v.begin_carousel_with_cover();
        pick(&mut v, "c.png");
        assert_eq!(v.bundle_prompt.as_ref().unwrap().stage, BundleStage::Name);
        assert!(!d.path().join("carousel").exists(), "nothing before the name");
        v.bundle_type("MiLibro");
        v.bundle_confirm().unwrap();
        let slides = slides_in(&d, "MiLibro");
        assert_eq!(slides.first().unwrap(), "1_portada.png");
        assert!(slides.last().unwrap().ends_with("_contratapa.png"));
    }

    // ── the prompt that asks for the name and the language ───────────────────

    #[test]
    fn a_single_chapter_skips_the_name_and_asks_only_the_language() {
        let (_d, mut v) = bundle_app(false);
        v.begin_sale_bundle();
        let p = v.bundle_prompt.as_ref().expect("a prompt opens");
        assert_eq!(p.stage, BundleStage::Lang);
        assert_eq!(p.name, "Dos");
    }

    #[test]
    fn a_whole_book_asks_for_its_name_first() {
        let (_d, mut v) = bundle_app(true);
        v.begin_sale_bundle();
        assert_eq!(v.bundle_prompt.as_ref().unwrap().stage, BundleStage::Name);
    }

    #[test]
    fn with_nothing_to_read_no_prompt_opens() {
        let (_d, mut v) = app(&["."]);
        v.reading.clear();
        v.begin_sale_bundle();
        assert!(v.bundle_prompt.is_none());
        assert!(v.status.contains("Nada para exportar"));
    }

    #[test]
    fn typing_a_name_then_enter_moves_on_to_the_language_and_enter_exports() {
        let (d, mut v) = bundle_app(true);
        v.begin_sale_bundle();
        v.bundle_type("Mi ");
        v.bundle_type("Libro");
        v.bundle_confirm().unwrap();
        assert_eq!(v.bundle_prompt.as_ref().unwrap().stage, BundleStage::Lang);
        assert!(!d.path().join("gPTA_books").exists(), "nothing is written before the language");
        v.bundle_confirm().unwrap();
        assert!(v.bundle_prompt.is_none());
        assert!(bundle_files(&d, "Mi Libro").join("Mi Libro.epub").is_file());
    }

    #[test]
    fn the_language_defaults_to_spanish_and_can_be_cycled() {
        let (_d, mut v) = bundle_app(false);
        v.begin_sale_bundle();
        assert_eq!(v.bundle_prompt.as_ref().unwrap().lang, bundle::Lang::Es);
        v.bundle_cycle_lang(1);
        assert_eq!(v.bundle_prompt.as_ref().unwrap().lang, bundle::Lang::En);
        v.bundle_cycle_lang(1);
        assert_eq!(v.bundle_prompt.as_ref().unwrap().lang, bundle::Lang::Es); // wraps
    }

    #[test]
    fn the_chosen_language_reaches_the_epub() {
        let (d, mut v) = bundle_app(false);
        v.begin_sale_bundle();
        v.bundle_cycle_lang(1); // English
        v.bundle_confirm().unwrap();
        let epub = std::fs::read(bundle_files(&d, "Dos").join("Dos.epub")).unwrap();
        assert!(String::from_utf8_lossy(&epub).contains("<dc:language>en</dc:language>"));
    }

    #[test]
    fn enter_on_an_empty_name_cancels_and_writes_nothing() {
        let (d, mut v) = bundle_app(true);
        v.begin_sale_bundle();
        v.bundle_type("   ");
        v.bundle_confirm().unwrap();
        assert!(v.bundle_prompt.is_none());
        assert!(!d.path().join("gPTA_books").exists());
    }

    #[test]
    fn escape_cancels_at_either_stage_and_writes_nothing() {
        let (d, mut v) = bundle_app(true);
        v.begin_sale_bundle();
        v.cancel_bundle();
        assert!(v.bundle_prompt.is_none());
        v.begin_sale_bundle();
        v.bundle_type("X");
        v.bundle_confirm().unwrap(); // now on the language
        v.cancel_bundle();
        assert!(v.bundle_prompt.is_none());
        assert!(!d.path().join("gPTA_books").exists());
    }

    #[test]
    fn backspace_edits_the_name() {
        let (_d, mut v) = bundle_app(true);
        v.begin_sale_bundle();
        v.bundle_type("Libros");
        v.bundle_backspace();
        assert_eq!(v.bundle_prompt.as_ref().unwrap().name, "Libro");
    }

    #[test]
    fn sin_nada_para_leer_no_se_exporta_nada() {
        let (_d, mut v) = app(&["."]);
        v.reading.clear();
        assert!(v.export_pdf().is_none());
        assert!(v.status.contains("Nada para exportar"));
    }

    // ── Another instance saved (the IPC handlers) ───────────────────────────────

    #[test]
    fn a_sibling_saving_this_file_brings_in_its_version() {
        let (_d, mut v) = app(&[".", "vieja"]);
        // Another Voider rewrites the same file behind our back.
        void::atomic_write(&v.current_file, &[".".into(), "nueva".into()], false).unwrap();
        let path = v.current_file.clone();
        v.on_saved_by_other(&path);
        assert_eq!(v.ring.lines, vec![".".to_string(), "nueva".into()]);
        assert!(v.status.contains("another Voider"));
    }

    #[test]
    fn the_cursor_survives_a_sibling_save_and_clamps_if_it_has_to() {
        let (_d, mut v) = app(&[".", "a", "b", "c"]);
        v.ring.index = 3;
        void::atomic_write(&v.current_file, &[".".into(), "a".into()], false).unwrap();
        let path = v.current_file.clone();
        v.on_saved_by_other(&path);
        assert_eq!(v.ring.index, 1); // clamped into the shorter file, not out of range
    }

    #[test]
    fn a_sibling_saving_some_other_file_changes_nothing_here() {
        let (_d, mut v) = app(&[".", "mia"]);
        let before = v.ring.lines.clone();
        v.on_saved_by_other(Path::new("/void/I/ajeno.txt"));
        assert_eq!(v.ring.lines, before);
        assert!(v.status.is_empty());
    }

    #[test]
    fn a_sibling_reordering_the_library_is_taken_in_keeping_the_selection() {
        let (_d, mut v) = book();
        v.switch_to(View::F3);
        v.library.index = v.library.position("Uno.txt").unwrap();
        // Another instance reorders and adds one.
        let reordered = Library {
            entries: vec!["Nuevo.txt".into(), "Dos.txt".into(), "Uno.txt".into()],
            index: 0,
        };
        reordered.save(&v.void_dir).unwrap();

        let lib_path = library::library_path(&v.void_dir);
        v.on_saved_by_other(&lib_path);
        assert_eq!(v.library.entries, vec!["Nuevo.txt", "Dos.txt", "Uno.txt"]);
        assert_eq!(v.library.current(), "Uno.txt"); // followed by name, not by index
    }

    #[test]
    fn a_library_reload_is_deferred_while_a_name_is_being_typed() {
        let (_d, mut v) = book();
        v.switch_to(View::F3);
        let before = v.library.entries.clone();
        v.begin_new_chapter(); // mid-naming: unsaved intent
        Library { entries: vec!["Otro.txt".into()], index: 0 }
            .save(&v.void_dir)
            .unwrap();
        let lib_path = library::library_path(&v.void_dir);
        v.on_saved_by_other(&lib_path);
        assert_eq!(v.library.entries, before); // untouched until the name settles
    }

    #[test]
    fn a_selection_that_the_sibling_deleted_lands_somewhere_valid() {
        let (_d, mut v) = book();
        v.switch_to(View::F3);
        v.library.index = v.library.position("Uno.txt").unwrap();
        Library { entries: vec!["Dos.txt".into()], index: 0 }
            .save(&v.void_dir)
            .unwrap();
        let lib_path = library::library_path(&v.void_dir);
        v.on_saved_by_other(&lib_path);
        assert!(v.library.index < v.library.entries.len());
    }

    #[test]
    fn polling_without_any_ipc_attached_is_harmless() {
        let (_d, mut v) = app(&[".", "a"]);
        assert!(v.ipc.is_none()); // tests have no business opening sockets
        v.poll_ipc();
    }

    // ── Random lines into the entry (Ctrl+0 / Ctrl+. in F1) ─────────────────────

    #[test]
    fn ctrl_zero_pulls_a_line_from_somewhere_in_the_void() {
        let (_d, mut v) = app(&["."]);
        let i = v.void_dir.join("I");
        std::fs::create_dir_all(&i).unwrap();
        std::fs::write(i.join("otro.txt"), ".\nlinea prestada\n").unwrap();
        v.random_line_from_void();
        assert_eq!(v.entry.text(), "linea prestada");
        assert_eq!(v.entry.caret(), 0);
    }

    #[test]
    fn ctrl_zero_never_pulls_from_the_scratch() {
        let (_d, mut v) = app(&["."]);
        let i = v.void_dir.join("I");
        std::fs::create_dir_all(&i).unwrap();
        // The scratch is where lines land; pulling from it recirculates nothing.
        std::fs::write(i.join("0.txt"), ".\ndel scratch\n").unwrap();
        std::fs::write(i.join("libro.txt"), ".\ndel libro\n").unwrap();
        for _ in 0..12 {
            v.random_line_from_void();
            assert_eq!(v.entry.text(), "del libro");
        }
    }

    #[test]
    fn ctrl_zero_with_an_empty_void_says_so_and_leaves_the_entry_alone() {
        let (_d, mut v) = app(&["."]);
        v.entry.set_text("lo que escribia");
        v.random_line_from_void();
        assert_eq!(v.entry.text(), "lo que escribia");
        assert!(v.status.contains("Nothing in the void"));
    }

    #[test]
    fn ctrl_period_pulls_a_line_from_this_file() {
        let (_d, mut v) = app(&[".", "unica linea"]);
        v.random_line_from_here();
        assert_eq!(v.entry.text(), "unica linea");
        assert_eq!(v.entry.caret(), 0);
    }

    #[test]
    fn ctrl_period_does_not_hand_back_the_line_already_in_the_entry() {
        let (_d, mut v) = app(&[".", "una", "otra"]);
        v.entry.set_text("una");
        for _ in 0..12 {
            v.random_line_from_here();
            assert_eq!(v.entry.text(), "otra"); // the only one left
            v.entry.set_text("una");
        }
    }

    #[test]
    fn ctrl_period_falls_back_when_the_entry_holds_the_only_line() {
        let (_d, mut v) = app(&[".", "sola"]);
        v.entry.set_text("sola");
        v.random_line_from_here();
        assert_eq!(v.entry.text(), "sola"); // better that than nothing
    }

    #[test]
    fn ctrl_period_on_a_file_of_only_separators_says_so() {
        let (_d, mut v) = app(&["."]);
        v.entry.set_text("intacto");
        v.random_line_from_here();
        assert_eq!(v.entry.text(), "intacto");
        assert!(v.status.contains("nothing to pull"));
    }

    // ── Ctrl+F2/F3/F4: apuntar Voider a otro lado ───────────────────────────────

    #[test]
    fn el_navegador_de_archivo_arranca_en_la_carpeta_del_libro() {
        let (_d, mut v) = book();
        v.open_browser(browse::Purpose::ActiveFile);
        let b = v.browser.as_ref().unwrap();
        assert_eq!(b.dir, v.void_dir.join("I"));
        assert_eq!(b.looking, browse::Looking::File);
    }

    #[test]
    fn elegir_un_txt_lo_deja_activo_y_abre_f2() {
        let (_d, mut v) = book();
        v.open_browser(browse::Purpose::ActiveFile);
        let b = v.browser.as_mut().unwrap();
        b.index = b.entries.iter().position(|e| e.name == "Dos.txt").unwrap();
        v.browser_enter(false).unwrap();
        assert!(v.browser.is_none());
        assert_eq!(v.current_file, library::chapter_path(&v.void_dir, "Dos.txt"));
        assert_eq!(v.view, View::F2);
    }

    #[test]
    fn buscando_carpeta_enter_navega_y_shift_enter_elige() {
        let (_d, mut v) = book();
        let otro = v.void_dir.join("otro-void");
        std::fs::create_dir_all(otro.join("I")).unwrap();
        v.open_browser(browse::Purpose::VoidDir);
        // Enter entra, no elige.
        let b = v.browser.as_mut().unwrap();
        b.dir = v.void_dir.clone();
        b.entries = browse::list(&b.dir, browse::Looking::Dir);
        b.index = b.entries.iter().position(|e| e.name == "otro-void").unwrap();
        v.browser_enter(false).unwrap();
        assert!(v.browser.is_some(), "Enter no debe elegir una carpeta");
        assert_eq!(v.browser.as_ref().unwrap().dir, otro);
        // Shift+Enter sí.
        v.browser_enter(true).unwrap();
        assert!(v.browser.is_none());
        assert_eq!(v.void_dir, otro);
    }

    #[test]
    fn cambiar_de_void_no_toca_el_anterior() {
        let (_d, mut v) = book();
        let viejo = v.void_dir.clone();
        let antes = void::load_doc(&library::chapter_path(&viejo, "Uno.txt")).lines;
        let otro = viejo.join("otro");
        std::fs::create_dir_all(otro.join("I")).unwrap();

        v.open_browser(browse::Purpose::VoidDir);
        if let Some(b) = v.browser.as_mut() {
            b.dir = otro.clone();
            b.entries = browse::list(&otro, browse::Looking::Dir);
        }
        v.browser_enter(true).unwrap();

        assert_eq!(v.void_dir, otro);
        // El void viejo quedó exactamente como estaba.
        assert_eq!(void::load_doc(&library::chapter_path(&viejo, "Uno.txt")).lines, antes);
    }

    #[test]
    fn cambiar_de_void_deja_el_scratch_abierto_y_limpia_lo_del_anterior() {
        let (_d, mut v) = book();
        let otro = v.void_dir.join("otro");
        std::fs::create_dir_all(otro.join("I")).unwrap();
        v.o_file = "algo.txt".into();
        v.open_browser(browse::Purpose::VoidDir);
        if let Some(b) = v.browser.as_mut() {
            b.dir = otro.clone();
        }
        v.browser_enter(true).unwrap();
        assert_eq!(v.current_file, v.scratch_path());
        assert_eq!(v.view, View::F1);
        assert!(v.o_file.is_empty(), "quedó el libro del corpus anterior");
        assert!(!v.undo.can_undo(), "el historial del void anterior no debe cruzarse");
    }

    #[test]
    fn elegir_la_carpeta_del_libro_apunta_al_void_que_la_contiene() {
        let (_d, mut v) = book();
        let otro = v.void_dir.join("otro");
        std::fs::create_dir_all(otro.join("I")).unwrap();
        v.apply_choice(browse::Purpose::BookDir, otro.join("I")).unwrap();
        assert_eq!(v.void_dir, otro, "I/ es la carpeta del libro; el void es su padre");
    }

    #[test]
    fn cancelar_no_cambia_nada() {
        let (_d, mut v) = book();
        let antes = v.current_file.clone();
        v.open_browser(browse::Purpose::ActiveFile);
        v.cancel_browser();
        assert!(v.browser.is_none());
        assert_eq!(v.current_file, antes);
    }

    #[test]
    fn apuntar_a_una_carpeta_que_no_existe_no_rompe_nada() {
        let (_d, mut v) = book();
        let antes = v.void_dir.clone();
        v.apply_choice(browse::Purpose::VoidDir, PathBuf::from("/no/existe")).unwrap();
        assert_eq!(v.void_dir, antes);
        assert!(v.status.contains("no existe"));
    }

    // ── Ctrl+B: the backup, and the question it asks first ───────────────────────

    /// A Voider whose void has some content, plus a stand-in "drive" to copy to.
    fn backup_app() -> (tempfile::TempDir, tempfile::TempDir, Voider) {
        let d = tempfile::tempdir().unwrap();
        let i = d.path().join("I");
        std::fs::create_dir_all(&i).unwrap();
        std::fs::write(i.join("a.txt"), ".\nhola\n").unwrap();
        let drive = tempfile::tempdir().unwrap();
        let v = Voider::open(d.path(), i.join("a.txt"));
        (d, drive, v)
    }

    /// Put a prompt in place pointing at `drive`, as begin_backup would with a
    /// real pendrive mounted (which a test can't rely on).
    fn prompt_for(v: &mut Voider, drive: &Path) {
        let plan = backup::plan(&v.void_dir, drive, "25-01-01");
        v.backup_prompt = Some(BackupPrompt {
            drives: vec![drive.to_path_buf()],
            idx: 0,
            plan,
        });
    }

    #[test]
    fn opening_the_backup_prompt_writes_nothing_to_the_drive() {
        let (_d, drive, mut v) = backup_app();
        prompt_for(&mut v, drive.path());
        assert!(v.backup_prompt.is_some());
        // The whole point of the confirm step: the drive is still untouched.
        assert_eq!(std::fs::read_dir(drive.path()).unwrap().count(), 0);
    }

    #[test]
    fn the_prompt_says_what_it_would_copy_and_where() {
        let (_d, drive, mut v) = backup_app();
        prompt_for(&mut v, drive.path());
        let plan = &v.backup_prompt.as_ref().unwrap().plan;
        assert_eq!(plan.files.len(), 1);
        assert!(plan.summary().contains(&drive.path().display().to_string()));
    }

    #[test]
    fn confirming_writes_the_copy() {
        let (_d, drive, mut v) = backup_app();
        prompt_for(&mut v, drive.path());
        let n = v.backup_confirm().unwrap();
        assert!(n >= 1);
        assert!(v.backup_prompt.is_none());
        // The file really is on the "drive", under its dated folder.
        let folder = std::fs::read_dir(drive.path())
            .unwrap()
            .next()
            .unwrap()
            .unwrap()
            .path();
        assert_eq!(std::fs::read_to_string(folder.join("I/a.txt")).unwrap(), ".\nhola\n");
    }

    #[test]
    fn cancelling_leaves_the_drive_alone() {
        let (_d, drive, mut v) = backup_app();
        prompt_for(&mut v, drive.path());
        v.cancel_backup();
        assert!(v.backup_prompt.is_none());
        assert_eq!(std::fs::read_dir(drive.path()).unwrap().count(), 0);
    }

    #[test]
    fn confirming_with_no_prompt_open_does_nothing() {
        let (_d, _drive, mut v) = backup_app();
        assert_eq!(v.backup_confirm().unwrap(), 0);
    }

    #[test]
    fn with_no_drive_found_there_is_nothing_to_accept() {
        let (_d, _drive, mut v) = backup_app();
        // detect_drives finds real mount points; on a machine with none mounted
        // this must fail closed rather than open a prompt pointed at nowhere.
        v.begin_backup();
        if v.backup_prompt.is_none() {
            assert!(v.status.contains("No external drive"));
        }
    }

    #[test]
    fn stepping_between_drives_re_costs_the_copy_for_each() {
        let (_d, drive_a, mut v) = backup_app();
        let drive_b = tempfile::tempdir().unwrap();
        let plan = backup::plan(&v.void_dir, drive_a.path(), "25-01-01");
        v.backup_prompt = Some(BackupPrompt {
            drives: vec![drive_a.path().to_path_buf(), drive_b.path().to_path_buf()],
            idx: 0,
            plan,
        });
        v.backup_cycle_drive(1);
        let p = v.backup_prompt.as_ref().unwrap();
        assert_eq!(p.idx, 1);
        assert_eq!(p.plan.dest_root, drive_b.path()); // re-planned for the new drive
    }

    // ── F9: the prose editor ─────────────────────────────────────────────────────

    #[test]
    fn entering_f9_shows_the_file_as_paragraphs_of_flowing_prose() {
        let (_d, mut v) = app(&[".", "Una frase.", "Otra frase.", ".", "Segundo parrafo."]);
        v.switch_to(View::F9);
        assert_eq!(v.prose, "Una frase. Otra frase.\n\nSegundo parrafo.");
        assert!(!v.prose_dirty); // merely looking is not editing
    }

    #[test]
    fn entering_f9_parks_the_caret_on_the_paragraph_you_were_in() {
        let (_d, mut v) = app(&[".", "Primero.", ".", "Segundo.", ".", "Tercero."]);
        v.ring.index = 3; // on 'Segundo.'
        v.switch_to(View::F9);
        let off = v.prose_caret.expect("a caret position is set on entry");
        let tail: String = v.prose.chars().skip(off).collect();
        assert!(tail.starts_with("Segundo."));
    }

    #[test]
    fn entering_f5_on_a_dot_lands_on_the_paragraph_it_opens() {
        let (_d, mut v) = app(&[".", "a", ".", "b", ".", "c"]);
        v.ring.index = 2; // the dot before 'b'
        v.switch_to(View::F5);
        assert_eq!(v.para_idx, 1);
    }

    #[test]
    fn entering_f5_on_a_trailing_dot_falls_back_to_the_last_paragraph() {
        let (_d, mut v) = app(&[".", "a", ".", "b", "."]);
        v.ring.index = 4;
        v.switch_to(View::F5);
        assert_eq!(v.para_idx, 1); // nothing to open — stay put
    }

    #[test]
    fn leaving_f9_untouched_does_not_rewrite_the_file() {
        // The Python's test_unmodified_does_not_rewrite.
        let (_d, mut v) = app(&[".", "Unchanged line."]);
        v.switch_to(View::F9);
        let before = std::fs::read_to_string(&v.current_file).unwrap();
        v.switch_to(View::F2);
        assert_eq!(std::fs::read_to_string(&v.current_file).unwrap(), before);
        assert!(!library::chapter_path(&v.void_dir, "c.txt.bak").exists()); // no backup either
    }

    #[test]
    fn edited_prose_saves_back_as_the_dot_model() {
        // The Python's test_edited_prose_saves_as_dot_model.
        let (_d, mut v) = app(&[".", "Old."]);
        v.switch_to(View::F9);
        v.set_prose("First sentence. Second sentence.\n\nSecond paragraph here.");
        v.switch_to(View::F2);
        assert_eq!(
            void::load_doc(&v.current_file).lines,
            vec![
                ".".to_string(),
                "First sentence.".into(),
                "Second sentence.".into(),
                ".".into(),
                "Second paragraph here.".into(),
            ]
        );
        assert!(!v.prose_dirty); // the edit was consumed
    }

    #[test]
    fn the_ring_follows_the_prose_that_was_saved() {
        let (_d, mut v) = app(&[".", "Old."]);
        v.switch_to(View::F9);
        v.set_prose("Nuevo texto.");
        v.switch_to(View::F2);
        assert_eq!(v.ring.lines, vec![".".to_string(), "Nuevo texto.".into()]);
    }

    #[test]
    fn ctrl_s_saves_without_leaving_the_prose_editor() {
        let (_d, mut v) = app(&[".", "Old."]);
        v.switch_to(View::F9);
        v.set_prose("Nuevo.");
        v.prose_save().unwrap();
        assert_eq!(v.view, View::F9); // still here
        assert_eq!(void::load_doc(&v.current_file).lines, vec![".".to_string(), "Nuevo.".into()]);
        assert!(!v.prose_dirty);
    }

    #[test]
    fn setting_the_same_prose_back_is_not_an_edit() {
        let (_d, mut v) = app(&[".", "Igual."]);
        v.switch_to(View::F9);
        let same = v.prose.clone();
        v.set_prose(&same);
        assert!(!v.prose_dirty);
    }

    #[test]
    fn a_prose_save_is_one_undo_step() {
        let (_d, mut v) = app(&[".", "Original."]);
        let before = v.ring.lines.clone();
        v.switch_to(View::F9);
        v.set_prose("Reemplazo entero.");
        v.switch_to(View::F2);
        v.undo().unwrap();
        assert_eq!(void::load_doc(&v.current_file).lines, before);
    }

    #[test]
    fn f9_is_not_a_view_a_restart_resumes_into() {
        let (_d, mut v) = app(&[".", "a"]);
        v.switch_to(View::F2);
        v.switch_to(View::F9);
        // F9 edits one file rather than being a place to be — like F5 and F10,
        // it never becomes the remembered view.
        assert_eq!(Config::load(&v.void_dir).last_view.as_deref(), Some("F2"));
    }

    // ── Search in F2 ─────────────────────────────────────────────────────────────

    #[test]
    fn opening_f2_search_starts_on_every_non_dot_line() {
        let (_d, mut v) = app(&[".", "manzana", "pera", ".", "uva"]);
        v.open_f2_search();
        let search = v.f2_search.as_ref().unwrap();
        assert_eq!(search.matches, vec![1, 2, 4]); // dots excluded
        assert_eq!(search.saved_index, 0);
    }

    #[test]
    fn opening_f2_search_starts_highlighted_on_the_current_line() {
        let (_d, mut v) = app(&[".", "manzana", "pera", "uva"]);
        v.ring.index = 2; // 'pera'
        v.open_f2_search();
        let search = v.f2_search.as_ref().unwrap();
        assert_eq!(search.matches[search.highlight], 2);
    }

    #[test]
    fn typing_filters_to_matching_lines_case_insensitively() {
        let (_d, mut v) = app(&[".", "Manzana", "pera", "uva"]);
        v.open_f2_search();
        v.f2_search_type("AN");
        assert_eq!(v.f2_search.as_ref().unwrap().matches, vec![1]); // 'Manzana' only
    }

    #[test]
    fn backspace_widens_the_filter_back_out() {
        let (_d, mut v) = app(&[".", "manzana", "pera", "uva"]);
        v.open_f2_search();
        v.f2_search_type("z");
        assert_eq!(v.f2_search.as_ref().unwrap().matches, vec![1]);
        v.f2_search_backspace();
        assert_eq!(v.f2_search.as_ref().unwrap().matches, vec![1, 2, 3]); // back to all
    }

    #[test]
    fn search_move_clamps_instead_of_wrapping() {
        let (_d, mut v) = app(&[".", "a", "b", "c"]);
        v.open_f2_search();
        v.f2_search_move(-5);
        assert_eq!(v.f2_search.as_ref().unwrap().highlight, 0);
        v.f2_search_move(5);
        assert_eq!(v.f2_search.as_ref().unwrap().highlight, 2); // 'c', the last match
        v.f2_search_move(1);
        assert_eq!(v.f2_search.as_ref().unwrap().highlight, 2); // stays, no wrap
    }

    #[test]
    fn confirming_jumps_the_ring_to_the_highlighted_match_and_closes_search() {
        let (_d, mut v) = app(&[".", "manzana", "pera", "uva"]);
        v.open_f2_search();
        v.f2_search_move(2); // 'uva'
        v.f2_search_confirm();
        assert!(v.f2_search.is_none());
        assert_eq!(v.ring.index, 3);
    }

    #[test]
    fn cancelling_restores_the_line_the_search_started_from() {
        let (_d, mut v) = app(&[".", "manzana", "pera", "uva"]);
        v.ring.index = 1;
        v.open_f2_search();
        v.f2_search_move(2); // highlight moves onto 'uva'
        v.f2_search_cancel();
        assert!(v.f2_search.is_none());
        assert_eq!(v.ring.index, 1); // back to where it was, not the highlight
    }

    #[test]
    fn confirming_with_no_matches_closes_search_without_moving() {
        let (_d, mut v) = app(&[".", "manzana", "pera"]);
        v.ring.index = 1;
        v.open_f2_search();
        v.f2_search_type("xyz");
        assert!(v.f2_search.as_ref().unwrap().matches.is_empty());
        v.f2_search_confirm();
        assert!(v.f2_search.is_none());
        assert_eq!(v.ring.index, 1);
    }

    #[test]
    fn leaving_f2_cancels_an_open_search() {
        let (_d, mut v) = app(&[".", "manzana", "pera"]);
        v.view = View::F2;
        v.ring.index = 1;
        v.open_f2_search();
        v.f2_search_move(1);
        v.switch_to(View::F1);
        assert!(v.f2_search.is_none());
        assert_eq!(v.ring.index, 1);
    }

    // ── Search in F3 ─────────────────────────────────────────────────────────────

    #[test]
    fn opening_f3_search_starts_on_every_chapter_dots_excluded() {
        let (_d, mut v) = app(&["."]);
        v.library = Library {
            entries: vec![".".into(), "Alfa.txt".into(), "Beta.txt".into()],
            index: 0,
        };
        v.open_f3_search();
        assert_eq!(v.f3_search.as_ref().unwrap().matches, vec![1, 2]);
    }

    #[test]
    fn f3_search_matches_the_display_name_not_the_extension() {
        let (_d, mut v) = app(&["."]);
        v.library = Library {
            entries: vec!["Capitulo Uno.txt".into(), "Otro.txt".into()],
            index: 0,
        };
        v.open_f3_search();
        v.f3_search_type("uno");
        assert_eq!(v.f3_search.as_ref().unwrap().matches, vec![0]);
        v.f3_search_type("txt"); // now "unotxt" -- no entry contains that
        assert!(v.f3_search.as_ref().unwrap().matches.is_empty());
    }

    #[test]
    fn confirming_f3_search_highlights_the_match_and_closes() {
        let (_d, mut v) = app(&["."]);
        v.library = Library {
            entries: vec!["Alfa.txt".into(), "Beta.txt".into()],
            index: 0,
        };
        v.open_f3_search();
        v.f3_search_type("beta");
        v.f3_search_confirm();
        assert!(v.f3_search.is_none());
        assert_eq!(v.library.index, 1);
    }

    #[test]
    fn cancelling_f3_search_restores_the_highlighted_entry() {
        let (_d, mut v) = app(&["."]);
        v.library = Library {
            entries: vec!["Alfa.txt".into(), "Beta.txt".into()],
            index: 0,
        };
        v.open_f3_search();
        v.f3_search_move(1);
        v.f3_search_cancel();
        assert!(v.f3_search.is_none());
        assert_eq!(v.library.index, 0);
    }

    #[test]
    fn leaving_f3_cancels_an_open_search() {
        let (_d, mut v) = book();
        v.switch_to(View::F3);
        v.open_f3_search();
        v.f3_search_type("uno");
        v.switch_to(View::F2);
        assert!(v.f3_search.is_none());
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
        assert_eq!(merged.lines, vec![".", "/A", "a1", "a2", "/B", "b1"]);
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

    #[test]
    fn splitting_the_highlighted_chapter_does_not_require_opening_it_first() {
        let (_d, mut v) = book(); // active file is Uno.txt
        let doc_path = v.void_dir.join("I/doc.txt");
        void::atomic_write(&doc_path, &["/X".to_string(), "a".to_string(), "/Y".to_string(), "b".to_string()], false).unwrap();
        v.library = Library {
            entries: vec!["doc.txt".into()],
            index: 0,
        };
        let n = v.book_split_current().unwrap();
        assert_eq!(n, 2);
        assert!(v.library.entries.contains(&"X.txt".to_string()));
        assert!(v.library.entries.contains(&"Y.txt".to_string()));
        assert_eq!(void::load_doc(&v.void_dir.join("I/X.txt")).lines, vec![".", "a"]);
        assert_eq!(void::load_doc(&v.void_dir.join("I/Y.txt")).lines, vec![".", "b"]);
        assert!(!doc_path.exists()); // the emptied container is gone
    }

    #[test]
    fn splitting_a_separator_or_the_portal_does_nothing() {
        let (_d, mut v) = book();
        v.library = Library { entries: vec![".".into(), "0.txt".into()], index: 0 };
        assert_eq!(v.book_split_current().unwrap(), 0);
        v.library.index = 1;
        assert_eq!(v.book_split_current().unwrap(), 0);
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

    // ── Ctrl+Shift+E: give a fused scriptio line its line breaks back ────────
    // Mirrors test_split_spaces.py.

    #[test]
    fn splitting_on_spaces_on_a_line_splits_that_line_only() {
        let (_d, mut v) = app(&[".", "uno dos tres", "otra linea"]);
        v.ring.index = 1;
        v.doc_split_line_on_spaces().unwrap();
        assert_eq!(v.ring.lines, vec![".", "uno", "dos", "tres", "otra linea"]);
        assert_eq!(v.ring.index, 1); // the caret stays on the first piece
        assert_eq!(v.ring.current(), "uno");
    }

    #[test]
    fn splitting_on_spaces_on_a_dot_splits_the_whole_paragraph() {
        let (_d, mut v) = app(&[".", "a b", "c d", ".", "no me toques"]);
        v.ring.index = 0;
        v.doc_split_line_on_spaces().unwrap();
        assert_eq!(v.ring.lines, vec![".", "a", "b", "c", "d", ".", "no me toques"]);
    }

    #[test]
    fn splitting_on_spaces_never_explodes_the_dots() {
        let (_d, mut v) = app(&[".", "a b", ".", "c d"]);
        v.ring.index = 0;
        v.doc_split_line_on_spaces().unwrap();
        assert_eq!(v.ring.lines.iter().filter(|l| *l == ".").count(), 2);
    }

    #[test]
    fn splitting_on_spaces_reaches_the_disk_and_is_one_undo_step() {
        let (_d, mut v) = app(&[".", "uno dos"]);
        v.ring.index = 1;
        v.doc_split_line_on_spaces().unwrap();
        assert_eq!(void::load_doc(&v.current_file).lines, vec![".", "uno", "dos"]);
        v.undo().unwrap();
        assert_eq!(v.ring.lines, vec![".", "uno dos"]);
    }

    #[test]
    fn splitting_a_line_with_nothing_to_split_writes_nothing() {
        let (_d, mut v) = app(&[".", "unasola"]);
        v.ring.index = 1;
        v.doc_split_line_on_spaces().unwrap();
        assert_eq!(v.ring.lines, vec![".", "unasola"]);
        assert!(!v.undo.can_undo(), "no empty undo step");
    }

    #[test]
    fn splitting_twice_does_nothing_the_second_time() {
        let (_d, mut v) = app(&[".", "unofrag dosfrag tresfrag"]);
        v.ring.index = 0;
        v.doc_split_line_on_spaces().unwrap();
        let once = v.ring.lines.clone();
        v.doc_split_line_on_spaces().unwrap();
        assert_eq!(v.ring.lines, once);
    }

    #[test]
    fn the_split_result_survives_a_round_trip_through_f9() {
        // What makes it survive is that F9 no longer joins unpunctuated lines.
        let (_d, mut v) = app(&[".", "unofrag dosfrag tresfrag"]);
        v.ring.index = 1;
        v.doc_split_line_on_spaces().unwrap();
        let bare: Vec<String> = v.ring.lines.iter().filter(|l| *l != ".").cloned().collect();
        assert_eq!(reformat::lines_to_paragraphs(&v.ring.lines), bare);
    }

    // ── Alt+Shift+↑/↓: duplicate, and put the copy where the arrow points ────
    // Mirrors test_doc_duplicate.py (F2) and test_book_duplicate.py (F3).

    #[test]
    fn duplicating_down_puts_the_copy_right_after() {
        let (_d, mut v) = app(&[".", "uno.", "dos."]);
        v.ring.index = 1;
        v.doc_duplicate(1).unwrap();
        assert_eq!(v.ring.lines, vec![".", "uno.", "uno.", "dos."]);
        assert_eq!(v.ring.index, 2); // the cursor follows the copy
    }

    #[test]
    fn duplicating_up_puts_the_copy_right_before_and_the_cursor_stays_on_it() {
        let (_d, mut v) = app(&[".", "uno.", "dos."]);
        v.ring.index = 1;
        v.doc_duplicate(-1).unwrap();
        assert_eq!(v.ring.lines, vec![".", "uno.", "uno.", "dos."]);
        assert_eq!(v.ring.index, 1);
    }

    #[test]
    fn a_duplicated_line_reaches_the_disk() {
        let (_d, mut v) = app(&[".", "uno."]);
        v.ring.index = 1;
        v.doc_duplicate(1).unwrap();
        assert_eq!(void::load_doc(&v.current_file).lines, vec![".", "uno.", "uno."]);
    }

    #[test]
    fn duplicating_on_a_dot_copies_the_whole_paragraph_with_its_own_dot() {
        let (_d, mut v) = app(&[".", "uno.", "dos.", ".", "otro."]);
        v.ring.index = 0;
        v.doc_duplicate(1).unwrap();
        assert_eq!(v.ring.lines, vec![".", "uno.", "dos.", ".", "uno.", "dos.", ".", "otro."]);
        assert_eq!(v.ring.lines.iter().filter(|l| *l == ".").count(), 3);
    }

    #[test]
    fn duplicating_a_paragraph_up_leaves_the_cursor_on_the_copys_dot() {
        let (_d, mut v) = app(&[".", "uno.", "dos.", ".", "otro."]);
        v.ring.index = 0;
        v.doc_duplicate(-1).unwrap();
        assert_eq!(v.ring.lines, vec![".", "uno.", "dos.", ".", "uno.", "dos.", ".", "otro."]);
        assert_eq!(v.ring.index, 0);
    }

    #[test]
    fn the_paragraph_scope_never_crosses_into_the_next() {
        let (_d, mut v) = app(&[".", "uno.", ".", "dos.", "tres."]);
        v.ring.index = 0;
        v.doc_duplicate(1).unwrap();
        assert_eq!(v.ring.lines, vec![".", "uno.", ".", "uno.", ".", "dos.", "tres."]);
    }

    #[test]
    fn an_empty_paragraph_still_duplicates_its_dot() {
        let (_d, mut v) = app(&[".", ".", "algo."]);
        v.ring.index = 0;
        v.doc_duplicate(1).unwrap();
        assert_eq!(v.ring.lines, vec![".", ".", ".", "algo."]);
    }

    #[test]
    fn duplicating_inside_a_focused_paragraph_keeps_the_copy_in_focus() {
        let (_d, mut v) = app(&[".", "uno.", "dos.", "tres."]);
        v.ring.index = 0;
        v.enter_para_focus(); // content = [1, 2, 3], on 'uno.'
        v.doc_duplicate(1).unwrap();
        assert_eq!(v.ring.lines, vec![".", "uno.", "uno.", "dos.", "tres."]);
        let mut focus = v.para_focus_content.clone();
        focus.sort();
        assert_eq!(focus, vec![1, 2, 3, 4]);
    }

    #[test]
    fn duplicating_a_line_is_one_undo_step() {
        let (_d, mut v) = app(&[".", "uno."]);
        v.ring.index = 1;
        v.doc_duplicate(1).unwrap();
        v.undo().unwrap();
        assert_eq!(v.ring.lines, vec![".", "uno."]);
    }

    fn dup_book_app(
        library: &[&str],
        contents: &[(&str, &str)],
    ) -> (tempfile::TempDir, Voider) {
        let d = tempfile::tempdir().unwrap();
        let i = d.path().join("I");
        std::fs::create_dir_all(&i).unwrap();
        for (name, text) in contents {
            std::fs::write(i.join(name), text).unwrap();
        }
        for name in library {
            if *name != "." && !i.join(name).exists() && !library::is_portal(name) {
                std::fs::write(i.join(name), format!("{}\n", library::display_name(name))).unwrap();
            }
        }
        let first = library.iter().find(|n| **n != ".").unwrap();
        let mut v = Voider::open(d.path(), i.join(first));
        v.library = Library { entries: library.iter().map(|s| s.to_string()).collect(), index: 0 };
        (d, v)
    }

    fn i_files(d: &tempfile::TempDir) -> Vec<String> {
        let mut f: Vec<String> = std::fs::read_dir(d.path().join("I"))
            .unwrap()
            .filter_map(|e| e.ok())
            .map(|e| e.file_name().to_string_lossy().into_owned())
            .filter(|n| n.ends_with(".txt"))
            .collect();
        f.sort();
        f
    }

    #[test]
    fn duplicating_a_chapter_makes_a_new_file_with_the_same_content() {
        let (d, mut v) = dup_book_app(&[".", "Uno.txt", "Dos.txt"], &[("Uno.txt", "a.\nb.\n")]);
        v.library.index = 1;
        v.book_duplicate(1).unwrap();
        assert!(i_files(&d).contains(&"Uno-2.txt".to_string()));
        assert_eq!(std::fs::read_to_string(d.path().join("I/Uno-2.txt")).unwrap(), "a.\nb.\n");
        assert_eq!(std::fs::read_to_string(d.path().join("I/Uno.txt")).unwrap(), "a.\nb.\n");
    }

    #[test]
    fn a_duplicated_chapters_name_steps_on_a_collision() {
        let (d, mut v) = dup_book_app(&[".", "Uno.txt", "Uno-2.txt"], &[]);
        v.library.index = 1;
        v.book_duplicate(1).unwrap();
        assert!(i_files(&d).contains(&"Uno-3.txt".to_string()));
    }

    #[test]
    fn duplicating_down_lists_the_copy_right_after_and_the_cursor_follows() {
        let (_d, mut v) = dup_book_app(&[".", "Uno.txt", "Dos.txt"], &[]);
        v.library.index = 1;
        v.book_duplicate(1).unwrap();
        assert_eq!(v.library.entries, vec![".", "Uno.txt", "Uno-2.txt", "Dos.txt"]);
        assert_eq!(v.library.index, 2);
    }

    #[test]
    fn duplicating_up_lists_the_copy_right_before_and_the_cursor_follows() {
        let (_d, mut v) = dup_book_app(&[".", "Uno.txt", "Dos.txt"], &[]);
        v.library.index = 1;
        v.book_duplicate(-1).unwrap();
        assert_eq!(v.library.entries, vec![".", "Uno-2.txt", "Uno.txt", "Dos.txt"]);
        assert_eq!(v.library.index, 1);
    }

    #[test]
    fn a_duplicated_chapter_persists_in_the_library_file() {
        let (d, mut v) = dup_book_app(&[".", "Uno.txt"], &[]);
        v.library.index = 1;
        v.book_duplicate(1).unwrap();
        assert_eq!(Library::load(d.path()).entries, vec![".", "Uno.txt", "Uno-2.txt"]);
    }

    #[test]
    fn duplicating_a_dot_or_the_portal_does_nothing() {
        let (d, mut v) = dup_book_app(&[".", "0.txt", "Uno.txt"], &[]);
        v.library.index = 0;
        v.book_duplicate(1).unwrap();
        v.library.index = 1;
        v.book_duplicate(1).unwrap();
        assert_eq!(v.library.entries, vec![".", "0.txt", "Uno.txt"]);
        assert_eq!(i_files(&d), vec!["Uno.txt"]);
    }

    #[test]
    fn duplicating_while_naming_a_pending_entry_does_nothing() {
        let (_d, mut v) = dup_book_app(&[".", "Uno.txt"], &[]);
        v.library.index = 1;
        v.pending_new = true;
        v.book_duplicate(1).unwrap();
        assert_eq!(v.library.entries, vec![".", "Uno.txt"]);
    }

    #[test]
    fn a_duplicated_chapter_can_be_undone() {
        let (d, mut v) = dup_book_app(&[".", "Uno.txt"], &[]);
        v.library.index = 1;
        v.book_duplicate(1).unwrap();
        v.undo().unwrap();
        assert!(!d.path().join("I/Uno-2.txt").exists());
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
    fn delete_from_another_file_goes_straight_to_trash() {
        let (_d, mut v) = app(&["From book.", ".", "Stay."]);
        v.ring = LineRing::new(["From book.", ".", "Stay."]);
        v.ring.index = 0;
        v.delete_line_to_trash().unwrap();
        let trash = void::load_doc(&v.trash_path());
        assert!(trash.lines.contains(&"From book.".to_string()));
        let scratch = void::load_doc(&v.scratch_path());
        assert!(!scratch.lines.contains(&"From book.".to_string()));
    }

    #[test]
    fn deleting_removes_the_line_from_the_ring() {
        let (_d, mut v) = app(&["Hello world.", ".", "Keep this."]);
        v.ring = LineRing::new(["Hello world.", ".", "Keep this."]);
        v.ring.index = 0;
        v.delete_line_to_trash().unwrap();
        assert!(!v.ring.lines.contains(&"Hello world.".to_string()));
    }

    #[test]
    fn delete_from_the_scratch_goes_to_trash() {
        let (_d, mut v) = scratch_app(&["Hello world.", ".", "Keep this."]);
        v.ring.index = 0; // 'Hello world.'
        v.delete_line_to_trash().unwrap();
        let trash = void::load_doc(&v.trash_path());
        assert!(trash.lines.contains(&"Hello world.".to_string()));
        assert!(!v.ring.lines.contains(&"Hello world.".to_string()));
    }

    #[test]
    fn a_dot_deleted_from_the_scratch_goes_to_trash_too() {
        let (_d, mut v) = scratch_app(&[".", "Line."]);
        v.ring.index = 0; // the dot itself
        v.delete_line_to_trash().unwrap();
        let trash = void::load_doc(&v.trash_path());
        assert!(trash.lines.iter().any(|l| l == "."));
    }

    #[test]
    fn delete_from_trash_restores_to_the_scratch() {
        let (_d, mut v) = trash_app(&["Trashed line.", ".", "Another."]);
        v.ring.index = 0;
        v.delete_line_to_trash().unwrap();

        assert!(!v.ring.lines.contains(&"Trashed line.".to_string()));
        let on_disk = void::load_doc(&v.trash_path());
        assert!(!on_disk.lines.contains(&"Trashed line.".to_string()));
        // Nothing is ever deleted for good: from the trash it goes back to 0.txt.
        let scratch = void::load_doc(&v.scratch_path());
        assert!(scratch.lines.contains(&"Trashed line.".to_string()));
    }

    #[test]
    fn if_the_destination_cannot_be_written_the_line_stays() {
        let (d, mut v) = app(&["Keep me.", ".", "Other."]);
        v.ring = LineRing::new(["Keep me.", ".", "Other."]);
        v.ring.index = 0;
        // A directory where trash.txt should be: the append must fail.
        std::fs::create_dir_all(d.path().join("I/trash.txt")).unwrap();
        assert!(v.delete_line_to_trash().is_err());
        assert!(v.ring.lines.contains(&"Keep me.".to_string()));
    }

    #[test]
    fn deleting_down_to_one_line_is_a_noop_guard() {
        let (_d, mut v) = app(&["sola"]);
        v.ring = LineRing::new(["sola"]);
        v.delete_line_to_trash().unwrap();
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

    // The catalogue lists the ACTIVE chapter too, like F2's: a stray Enter then
    // lands on the file you are in (a no-op) instead of silently sending the
    // paragraph to the next chapter over (test_picker_parks_home.py).

    #[test]
    fn the_catalogue_lists_the_active_file_but_not_the_portal_or_separators() {
        let (_d, mut v) = book();
        v.switch_to(View::F5); // active file is Uno.txt
        v.library.entries = vec![
            "Uno.txt".into(),
            ".".into(),
            "0.txt".into(),
            "Dos.txt".into(),
        ];
        assert_eq!(v.picker_entries(), vec!["Uno.txt", "Dos.txt"]);
    }

    #[test]
    fn the_catalogue_opens_parked_on_the_active_file() {
        let (_d, mut v) = book();
        v.switch_to(View::F5);
        v.library.entries = vec![
            "A.txt".into(),
            "Uno.txt".into(), // the active file
            "B.txt".into(),
            "C.txt".into(),
        ];
        v.open_picker();
        assert!(v.picker_open);
        assert_eq!(v.picker_entries()[v.picker_idx], "Uno.txt");
    }

    #[test]
    fn confirming_the_catalogue_without_moving_changes_nothing() {
        let (_d, mut v) = book();
        v.switch_to(View::F5);
        v.open_picker();
        let here = v.picker_entries()[v.picker_idx].clone();
        let before = v.ring.lines.clone();
        assert!(!v.send_para_to(&here).unwrap());
        assert_eq!(v.ring.lines, before);
    }

    #[test]
    fn f2s_catalogue_also_opens_parked_on_the_active_file() {
        let (_d, mut v) = book();
        v.ring.lines = vec![".".into(), "algo".into()];
        v.ring.index = 1;
        v.doc_open_picker();
        assert_eq!(v.picker_entries()[v.picker_idx], "Uno.txt");
    }

    // ── the dots between books show in the catalogue (test_picker_separators.py)

    fn sep_book(entries: &[&str], active: &str) -> (tempfile::TempDir, Voider) {
        let (d, mut v) = dup_book_app(entries, &[]);
        v.set_active_file(d.path().join("I").join(active));
        (d, v)
    }

    const SEP: &str = "·";

    #[test]
    fn the_catalogue_rows_carry_the_dots_between_books() {
        let (_d, v) = sep_book(&[".", "A.txt", "B.txt", ".", "C.txt", "D.txt"], "B.txt");
        // The leading dot separates nothing, so it is not shown.
        assert_eq!(v.picker_rows().0, vec!["A", "B", SEP, "C", "D"]);
    }

    #[test]
    fn the_highlight_follows_the_right_row_not_the_destination_number() {
        let (_d, mut v) = sep_book(&[".", "A.txt", "B.txt", ".", "C.txt", "D.txt"], "B.txt");
        v.picker_idx = 2; // the third destination: C
        let (rows, i) = v.picker_rows();
        assert_eq!(rows[i], "C");
        v.picker_idx = 0;
        let (rows, i) = v.picker_rows();
        assert_eq!(rows[i], "A");
    }

    #[test]
    fn cycling_never_parks_on_a_separator() {
        let (_d, mut v) = sep_book(&[".", "A.txt", "B.txt", ".", "C.txt", "D.txt"], "B.txt");
        for k in 0..v.picker_entries().len() * 2 {
            v.picker_idx = k % v.picker_entries().len();
            let (rows, i) = v.picker_rows();
            assert_ne!(rows[i], SEP, "parked on a separator with idx {k}");
        }
    }

    #[test]
    fn a_separator_is_never_a_destination() {
        let (_d, v) = sep_book(&[".", "A.txt", "B.txt", ".", "C.txt"], "B.txt");
        assert!(!v.picker_entries().iter().any(|e| library::is_separator(e)));
    }

    #[test]
    fn two_dots_in_a_row_collapse_and_a_trailing_dot_is_dropped() {
        let (_d, v) = sep_book(&[".", ".", "A.txt", ".", ".", "B.txt", "."], "A.txt");
        assert_eq!(v.picker_rows().0, vec!["A", SEP, "B"]);
    }

    #[test]
    fn a_library_with_no_dots_still_works() {
        let (_d, v) = sep_book(&["A.txt", "B.txt"], "A.txt");
        let (rows, i) = v.picker_rows();
        assert_eq!(rows, vec!["A", "B"]);
        assert_eq!(rows[i], "A");
    }

    #[test]
    fn an_empty_library_does_not_crash_the_catalogue() {
        let (_d, mut v) = book();
        v.library.entries = vec![".".into()];
        assert_eq!(v.picker_rows(), (Vec::<String>::new(), 0));
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

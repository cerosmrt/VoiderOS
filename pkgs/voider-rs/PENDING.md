# voider-rs — what's still missing

Derived from the Python's command surface (`config.json` keybindings +
`key_router_mixin.py`) and its 592 tests. Ordered by what a writer loses without
it. Tick them off as they land; each should arrive with the Python's tests
ported, not just the code.

Legend: **[ ]** to do · **[~]** partial · **[x]** done

---

## 1. Safety — must land before the real `/void` is touched

- [x] **Undo / redo** (`Ctrl+Z` / `Ctrl+Shift+Z`) — `test_undo`, `test_undo_cursor`,
      `test_f3_undo` (19 tests). Text changes only; navigation is not undoable.
      Keystroke bursts on one line coalesce into a single step. F3 gets its own
      stack for library operations (rename/reorder/delete/merge/split).
      *Nothing else on this list matters as much: without it a wrong key has no
      way back but git.*
- [x] **Git snapshot on entry**, so any session can be walked back — beyond the
      Python, which only snapshots before specific destructive ops.
- [x] **Save-time shrink guard** — refuse/rescue when a save would drop a large
      fraction of a file (`_rescue_on_large_shrink`).
- [x] **Backup to a pendrive** (`Ctrl+B`) — the faithful mirror + git, built to
      the design in `roadmap/pending.txt` rather than ported from
      `_backup_vault` (which opens a folder dialog and copies only `.txt`,
      losing the history). Detects the mounted drives, works out the whole copy
      WITHOUT writing anything, shows destination + file count + size, and only
      then — on Enter — commits the void and copies. Any other key cancels.
      Two rules worth knowing: `.git` travels (that is the point), and
      symlinked directories are reported but never followed, so `O/` → `/mnt/data`
      can't silently turn a backup of the writing into a copy of the corpus.
      Still open from that roadmap entry: the portable bundle (void + app + a
      Windows rebuild path), and the reconciliation flow back from a pendrive.

## 2. Navigation a writer uses constantly

- [x] **Paragraph jumps** (`PageUp`/`PageDown` → `goto_prev_dot`/`goto_next_dot`)
      — `test_movement`.
- [x] **Previous/next file** (`Alt+Up`/`Alt+Down` in F1 → `show_previous_file` /
      `show_next_file`) — walks the library without going through F3.
- [x] **Rebase the ring** (`Ctrl+0` → `rebase_to_index_zero`): make the current
      line the file's first. Also `_book_rebase` in F3.
- [x] **Home/End across the whole document** (`_doc_jump_start` / `_doc_jump_end`),
      not just the line.
- [x] **Remember position across runs**: last line per file
      (`_save_last_line`/`_restore_last_line`, a `_last_lines.conf` sidecar in
      `I/`) and the last restorable view + active file (`_restore_startup_view`)
      — `test_startup_restore`. F3's own "last highlighted entry" is covered
      for free: `switch_to(F3)` already re-lands on the active file's library
      slot. `test_open_position` turned out to be F4 reading-view anchors
      (paragraph ordinals for the HTML view), not position persistence — F4
      isn't built yet, so that one's still open, filed under F4 below.
- [x] **Search** (`Ctrl+F` in F2 and F3) with a centred search bar. No
      `test_search.py` exists in the Python (checked — `test_open_position.py`
      turned out to be F4 anchors, not this); ported straight from
      `_f2_search_*`/`_f3_search_*`/the search half of `key_router_mixin.py`,
      with Rust's own tests written from that reading. One deliberate
      difference: matches are tracked by ORIGINAL INDEX, not by matched text —
      the Python re-finds the confirmed line with `.index(text)`, ambiguous if
      two lines read the same; an index has no such bug and needs no `['.']`
      placeholder for "nothing matched" either.

## 3. Shaping text

- [x] **Reformat** (`Ctrl+Shift+F` → `reformat_active_file`): one sentence per
      line — `test_reformat` (13 tests).
- [x] **Split a file at `/name` markers** into chapters (`Ctrl+Shift+S` →
      `_split_chapter_at_slash`): a marker seals everything above it; a name
      clash appends into the existing chapter — `test_split_chapter` (9).
- [x] **Split the scratch into documents** (`_split_zero_to_docs`).
- [x] **Merge books** (`Ctrl+Shift+M` → `_book_merge_prompt` / `_book_do_merge`)
      — `test_merge`.
- [x] **Dispatch paragraphs** (`Ctrl+Shift+D`) — `test_dispatch`.
- [x] **Shuffle the scratch** (`Ctrl+Shift+R`) and **shuffle a book** (Tab on a
      dot in F3, numbered titles keeping their order) — `test_shuffle`,
      `test_book_shuffle`.
- [x] **Paragraph focus** (Enter on a `.` in F2): isolate one paragraph;
      navigation, Alt+Up/Down and Enter-again stay within it — `test_focus`.
- [x] **Delete line to zero / trash cascade** (`Ctrl+Delete` / `Ctrl+Backspace`
      in F2) — same feature, PENDING listed it twice — `test_trash_cascade`.
- [ ] **Merge stray `0.txt` files** (`_merge_zero_files`, Ctrl+Shift+F in F3):
      absorbs subdirectory scratches into the root one. Doesn't map cleanly onto
      the flat `I/` model here (no nested folders); deferred, low value.
- [x] **`_book_split_current`** (Ctrl+Shift+S in F3): split the file the F3
      cursor is highlighting, without opening it. `split_at_markers` already
      does the real work on the ACTIVE file from F2 — this would just be a
      thin F3 entry point onto the same logic.

## 4. The cut-up (loop writing)

- [x] **Tab in F1**: pull a random line from the void into the entry
      (`recycle_line_to_zero_txt`) — `test_controls` (32).
- [x] **Tab in F2**: contextual — paragraph order on the leading dot, a
      paragraph's own lines on any other dot, a random `I/` fragment on a
      content line (`_doc_tab`, `_doc_insert_random_i_line`) — `test_doc_tab`.
      Re-rolling a fragment in place (repeated Tab replaces, doesn't pile up)
      needed a small addition the Python doesn't: `TextLine::replace_range`,
      standing in for the text-selection Python gets for free from `QLineEdit`.
- [ ] **Alt+Tab in F2**: insert from the working set (`_doc_insert_ws_line`).
      Deferred — needs F7's working set, not built yet.
- [ ] **Ctrl+0 / Ctrl+.**: a random line from a random file / from this file.
- [x] **Smart copy** (`Ctrl+C` with no selection: line → paragraph → chapter) —
      `test_smart_copy` (5). There is no selection to fall back to yet (no
      selection model in `TextLine`), so every Ctrl+C is the contextual copy.

## 5. The other views

- [ ] **F4 — reading & print**: paginated book view, justified, hyphenated;
      `Ctrl+P` print, `Ctrl+S` export PDF — `test_reading_page`, `_sections`,
      `test_print` (29).
- [ ] **F6 — the `O/` reader**: read a corpus book, remember the position.
- [ ] **F7 — the `O/` browser** and the working set — `test_working_set`,
      `test_tab_ws` (26).
- [ ] **F8 — the oracle**: a random line from the corpus.
- [x] **F9 — prose editor**: the active file as flowing prose in one box, saved
      on leave — `test_editor_view`. The one view built from a real widget
      (egui's multiline box) instead of painted by hand — F9 wants *ordinary*
      editing, which is precisely what that widget already is. It also made
      `reformat_active_file`'s raw-prose branch reachable at last: F9 writes
      what you typed straight to disk, so a blank line really is a paragraph
      break there and wrapped lines DO join before splitting — the exact
      opposite of the ring-side `reformat`. Both branches now exist, as
      `reformat_prose` and `reformat`.
- [x] **F11 — help overlay**: the shortcut reference over whatever view you were
      in, any key closing it. NOT a port of the Python's HELP table — that table
      describes bindings this mirror doesn't have (F6/F7/F8, the metronome) or
      means differently (F5 is paragraphs here), and has drifted from its own
      code besides (it lists F9 as "Metronome"; `new_interface.py` opens the
      prose editor). A help screen that lies is worse than none, so this one is
      written from voider-rs's real keymap.
- [ ] **Escape → lock screen** — `test_lock_screen` (7). *Deliberately not built
      yet, and it should be a decision rather than a default.* The Python's
      version authenticates the real Linux password through PAM. That is the one
      piece of this mirror I cannot verify without Federico at the keyboard: I
      can write the overlay and its state machine, but I cannot test that PAM
      actually accepts the right password and refuses the wrong one, and an
      unlock path that silently fails open is worse than no lock at all. It also
      wants a new system dependency (the `pam` crate + PAM libs in `shell.nix`).
      Worth doing together, not alone — and worth remembering that the lock is a
      privacy screen either way, not a security boundary: it lives inside the
      app, so a TTY switch or killing the process walks straight past it, in the
      Python exactly as much as here.

## 6. The shell it lives in

- [ ] **Multi-instance IPC**: when one instance saves, the others reload —
      `test_integrity_sync` (5).
- [x] **Mouse cursor**: the white ring, auto-hidden while typing —
      `test_cursor_autohide` (12). Trivial here; just not wired.
- [ ] **Screenshots** (`F12`), **opacity** (`Ctrl+±`), **TTS** (`Ctrl+T`).
- [ ] **Pickers**: active file, book folder, void folder.
- [ ] **Be the desktop**: wlr-layer-shell. `pkgs/voider-shell/` is already a Rust
      layer-shell host, so this is closer than it looks.

---

## Done

- [x] `/void` data layer: load, atomic write, git commit — `void.rs`
- [x] `LineRing` 1:1 — `line_ring.rs`
- [x] The custom text line and its caret — `text_line.rs`
- [x] F1 writing, F2 the document ring, F3 the library, F5 paragraphs
- [x] Typewriter (caret pinned, text slides, clipped) and the caret that only
      blinks when empty — *beyond the Python*
- [x] Scriptio continua: Caps never uppercases, space releases, no backspace —
      *beyond the Python*
- [x] Alt moves lines, paragraphs (moving at the ends) and words
- [x] Send a paragraph to a chapter, catalogue anchored at the active file
- [x] The backtick round trip to the scratch
- [x] F10: the fonts installed on this machine, the size, persisted and live
- [x] Pinned title toggle · commit the void with its stat line

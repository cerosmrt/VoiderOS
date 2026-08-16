# Parity with proto-voider

Where the Rust mirror stands against the Python, measured by the Python's own
test suite: **63 files, 592 tests**. This is the honest map — what is ported,
what is partial, and what does not exist here yet.

Rust tests today: **136**.

## Ported, with tests

| Python suite | Tests | Rust home |
|---|---|---|
| `test_line_ring` / `_extended` | 41 | `line_ring.rs` — the core is 1:1 (incl. the negative-modulo trap Python hides) |
| `test_movement` | 21 | `paragraphs.rs`, `app.rs` — line swap, paragraph move (moves at the ends, not swaps) |
| `test_paragraphs` | 8 | `paragraphs.rs` |
| `test_f5_reorder` / `_send` / `_picker_start` / `_new_chapter_insert` | 34 | `f5.rs`, `app.rs` |
| `test_f3_new_entry` / `_separator` / `_position` | 25 | `app.rs` — settle-on-leave, new chapter below the current |
| `test_file_io` / `test_integrity` | 16 | `void.rs` — atomic write, no temp left behind, failed read blocks saving |
| `test_portal_singleton` | 6 | `library.rs` |
| `test_scratch_backtick` / `test_scratch_jump` | 15 | `app.rs` |
| `test_caps_scriptio` / `test_scriptio_continua` | 8 | `text_line.rs`, `app.rs` |
| `test_typewriter_entry` / `test_view_title_toggle` | 8 | `main.rs`, `app.rs` — and the caret behaviour the Python still owes |
| `test_commit_void` / `_stat` | 6 | `void.rs` |
| `test_config_split` / `test_editor_font` / `test_input_font_scaling` | 7 | `config.rs`, `fonts.rs` |
| `test_book` / `test_book_reorder` (part) | ~12 | `library.rs` |

## Partial — the behaviour exists, the edges are not all pinned down

- `test_edge_cases` (34), `test_pure_functions` (40): a grab bag over the whole
  app; the parts touching ported code hold, the rest reach features below.
- `test_split` / `test_split_chapter` (19): F2 splits a line; splitting a file at
  `/name` markers into chapters is **not** built.
- `test_open_position` / `test_startup_restore` (10): the last line and view are
  not remembered across runs yet.
- `test_files_module` (24): `void.rs` covers reading/writing; the wider file
  helpers are not ported.

## Landed since this file was first written

Everything below moved out of "not built" over the course of one long session.
Each arrived the same way: read the Python source AND its tests, write the Rust
tests from that spec, watch them fail, implement, keep the whole suite green.

| Feature | Python suite | Notes |
|---|---|---|
| Undo / redo | `test_undo`, `test_undo_cursor`, `test_f3_undo` (19) | was the biggest gap |
| Reformat (one sentence per line) | `test_reformat` (13) | both branches — see below |
| Dispatch / merge / trash cascade | `test_dispatch`, `test_merge`, `test_trash_cascade` | |
| Split at markers, split the scratch | `test_split_chapter` | |
| Shuffle (scratch, and Tab-on-dot in F3) | `test_shuffle`, `test_book_shuffle` | |
| Tab cut-up in F1 and F2 | `test_doc_tab`, `test_controls`, `test_tab_replace` | |
| Random line into the entry (Ctrl+0 / Ctrl+.) | `controls.py` | |
| Smart copy | `test_smart_copy` (5) | |
| Search in F2 and F3 | — (no Python test exists) | from the source |
| Position / view / active file across runs | `test_startup_restore` | |
| F9 prose editor | `test_editor_view` (2) | |
| F4 reading | `test_reading_page`, `_sections`, `test_open_position` | print/PDF still open |
| F11 help overlay | `help_overlay.py` | table rewritten, not ported |
| Multi-instance IPC | `test_integrity_sync` (5) | on `std::os::unix::net` |
| Backup to a drive (Ctrl+B) | — (built to `roadmap/pending.txt`) | better than `_backup_vault` |
| Screenshot (F12), opacity (Ctrl+±) | — | `grim`; opacity was mis-bound |
| Mouse cursor auto-hide | `test_cursor_autohide` (12) | |

One thing worth recording, because it corrects a claim made earlier in this
same file's history: `reformat_active_file` has TWO branches, and both are now
here. The ring-side one (`reformat`) treats every line as its own unit, because
`load_doc` has already removed the blank lines a paragraph break would need.
The raw-prose one (`reformat_prose`) joins wrapped lines before splitting them
into sentences, and is reachable only through F9, which writes what you typed
straight to disk without passing through `load_doc`. Calling the second branch
"unreachable" was right about the ring and wrong about the program.

## Not built here yet

| Feature | Python suite | Notes |
|---|---|---|
| F6–F8: the `O/` reader, browser, oracle | `test_working_set`, `test_tab_ws` (26) | needs the corpus |
| Print / PDF export from F4 | `test_print` | needs a PDF crate + `lp` |
| Justified, hyphenated setting in F4 | `test_reading_page` | no Spanish hyphenation here |
| Lock screen | `test_lock_screen` (7) | PAM — see PENDING.md |
| TTS | — | needs a speech engine decision |
| Alt+Tab in F2 (working-set fragment) | `test_tab_ws` | needs F7 |
| Pickers (active file, book folder, void folder) | — | |
| Merge stray `0.txt` files | — | doesn't fit the flat `I/` model |
| Be the desktop (wlr-layer-shell) | — | |

## Before pointing this at the real `/void`

The mirror writes to a sandbox on purpose. What has to be true first:

1. **Undo exists.** ✅ Ctrl+Z/Ctrl+Shift+Z, coalesced bursts, multi-file
   transactions (`undo.rs`).
2. **A git snapshot on entry**, so a session can always be walked back. ✅
   `snapshot_on_entry`, beyond what the Python does.
3. **Save-time shrink guard.** ✅ A `.rescue` copy before a write that would gut
   a substantial file (`rescue_on_large_shrink`).
4. **Instances don't overwrite each other.** ✅ `ipc.rs` — every save announces
   itself and the others re-read, so two open windows can't lose each other's
   lines. The Python's own solution, ported.
5. **A copy that leaves the machine.** ✅ Ctrl+B, with the whole void and its
   git history, and a confirm step before anything is written.
6. **The destructive paths are covered**: send-to-chapter, paragraph moves,
   split, merge, dispatch, the trash cascade and the library rewrite all pass
   tests — but they have not been run over a real book with hundreds of
   chapters. Different scale hides different bugs than unit tests do.
7. **Run it a while on a copy of the real void** — same size, same file names
   (accents, `:`, `?`), same `I.txt` — and diff the results against the Python.

Items 6 and 7 are the remaining gate, and they are the same gate they always
were: not a feature to build, a judgement call on whether the mirror is
trustworthy enough with the actual book. Everything mechanical that could be
done before that call has now been done. The call itself is Federico's, and
should be made with him at the keyboard — the sensible shape is a copy of the
real void, a while spent working in it, and a diff, not a switch thrown.

Until then `VOIDER_RS_VOID` points at `~/.local/share/voider-rs/void`, and the
real `/void` is untouched.

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

## Not built here yet

Each of these is a feature, not a missing test:

| Feature | Python suite | Notes |
|---|---|---|
| Undo / redo | `test_undo`, `test_undo_cursor`, `test_f3_undo` (19) | the biggest gap |
| F4 reading & print/PDF | `test_reading_page`, `_sections`, `test_print` (29) | |
| F6–F8: the `O/` reader, browser, oracle | `test_working_set`, `test_tab_ws` (26) | |
| Tab cut-up (random line into the entry) | `test_doc_tab`, `test_controls`, `test_tab_replace` (55) | `controls.py` |
| Reformat (one sentence per line) | `test_reformat` (13) | |
| Dispatch / merge / trash cascade | `test_dispatch`, `test_merge`, `test_trash_cascade` (14) | |
| Shuffle (0.txt, and Tab-on-dot in F3) | `test_shuffle`, `test_book_shuffle` (9) | |
| Smart copy | `test_smart_copy` (5) | |
| Multi-instance IPC | `test_integrity_sync` (5) | |
| Lock screen | `test_lock_screen` (7) | |
| TTS | — | |
| Mouse cursor auto-hide | `test_cursor_autohide` (12) | trivial in egui, just not wired |
| F9 prose editor | `test_editor_view` (2) | |

## Before pointing this at the real `/void`

The mirror writes to a sandbox on purpose. What has to be true first:

1. **Undo exists.** Today a wrong keystroke here has no way back except git.
2. **The destructive paths are covered**: send-to-chapter, paragraph moves and
   the library rewrite all pass tests, but they have not been run over a real
   book with hundreds of chapters.
3. **A git snapshot on entry**, so a session can always be walked back.
4. **Run it a while on a copy of the real void** — same size, same file names
   (accents, `:`, `?`), same `I.txt` — and diff the results against the Python.

Until then `VOIDER_RS_VOID` points at `~/.local/share/voider-rs/void`, and the
real `/void` is untouched.

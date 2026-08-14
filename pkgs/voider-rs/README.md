# voider-rs — the Rust mirror

A second implementation of Voider in Rust + [egui](https://github.com/emilk/egui),
built **alongside** the Python app. `proto-voider/` and `pkgs/voider-py/` are the
running system and are never touched by this work.

## Why

Immediate-mode means we own every pixel and every keystroke. The things that
fight a widget toolkit in PyQt6 — the typewriter caret, scriptio continua, the
circular views — stop being battles and become "what do I draw this frame?".
It also gets us a single portable binary (Rust cross-compiles to Windows, which
PyInstaller cannot do from NixOS — see the portable-backup item in
`roadmap/pending.txt`).

## Ground rules

- **Mirror, not a replacement.** The Python stays as-is until this is proven.
- **1:1 with current behaviour.** `roadmap/pending.txt` is the list of things to
  do *beyond* parity — several of them (the teleprompter typewriter, scriptio
  without backspace) are easy here and should be built properly the first time.
- **Sandbox data first.** Work against a copy of `/void`; only touch the real
  one once reads/writes/git are proven. `/void` is sacred.

## Build & test

The system nixpkgs ships rustc 1.86, below the MSRV of some eframe deps, so the
shell pins nixos-unstable:

```bash
cd pkgs/voider-rs
nix-shell --run "cargo test"     # unit tests
nix-shell --run "cargo run"      # opens the window
```

## Milestones

- **M0 — scaffold.** ✅ Crate, black window, `LineRing` ported.
- **M1 — the core.** ✅ The `/void` data layer (atomic writes, git), the custom
  text line, and F1 writing for real.
- **M2 — F2.** ✅ The document as a ring, edited in place.
- **M3 — F3.** ✅ The library: `I.txt`, opening and creating chapters.
- **M4 — F5.** ✅ Paragraphs: reorder across fences, send to a chapter.
- **Next:** F4 (reading/print), F6–F8 (the O/ reader and oracle), F9, F10;
  config file; undo/redo; multi-instance IPC.
- **M final — be the desktop.** wlr-layer-shell. Note `pkgs/voider-shell/` is
  already a Rust layer-shell host (smithay-client-toolkit), so this is closer
  than it looks.

## Keys

| | |
|---|---|
| `F1` `F2` `F3` `F5` | views |
| `` ` `` | round trip to the scratch and back |
| `Ctrl+Shift+W` | typewriter mode |
| `Ctrl+Shift+T` | pinned title |
| `Ctrl+Shift+G` | commit the void |
| F3: `Shift+Enter` / `Enter` / `Esc` | new chapter / open / cancel |
| F5: `Alt+↑↓` / `→` / `←` / `Enter` | move paragraph / catalogue / back / to F2 |

Caps Lock is scriptio continua: the spacebar releases the line, it never
uppercases, and there is no Backspace — type and send.

## Layout

```
src/
├── main.rs       eframe window: input routing and all drawing
├── app.rs        app state and view logic (no egui — testable headless)
├── void.rs       /void: load, atomic write, git
├── library.rs    I.txt, the ordered index of the book
├── f5.rs         paragraph tokenising and reordering
├── text_line.rs  the editable line we own the caret of
└── line_ring.rs  port of line_ring.py
```

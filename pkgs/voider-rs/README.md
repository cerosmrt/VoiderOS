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

- **M0 — scaffold.** ✅ Crate, black window, `LineRing` ported with tests.
- **M1 — the core.** F1 + the `/void` data layer (atomic writes) + git2 + the
  custom text line (owning the caret ⇒ the typewriter comes for free).
- **M2** F2 · **M3** F3 · **M4** F5 · **M5** F4/F6–F10.
- **M final — be the desktop.** wlr-layer-shell. Note `pkgs/voider-shell/` is
  already a Rust layer-shell host (smithay-client-toolkit), so this is closer
  than it looks.

## Layout

```
src/
├── main.rs       app entry + eframe window
└── line_ring.rs  port of line_ring.py (pure logic, tested)
```

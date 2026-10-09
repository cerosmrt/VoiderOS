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
- [x] **Merge stray `0.txt` files** (`_merge_zero_files`, Ctrl+Shift+F in F3):
      absorbs subdirectory scratches into the root one. *Estaba diferido con una
      razón equivocada*: dije que no encajaba en el modelo plano de `I/` "porque
      no hay carpetas anidadas". Las hay — el void real tiene `I/0` y
      `I/0/25-10-25_phone`. La función no era código muerto, sólo no tenía nada
      que absorber ese día. Una diferencia deliberada: en el Python esto además
      corre al arrancar, en silencio; acá es sólo explícito, porque borrar
      archivos sin que nadie lo pida cada vez que abrís es mucho poder para algo
      que nadie miró.
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
- [x] **Shift+Tab in F2**: insert a fragment from the working set instead of
      from `I/` (`_doc_insert_ws_line`). *No es Alt+Tab*, aunque PENDING y el
      propio Python lo llamaran así: la señal se llama `altTabPressed` y su
      comentario dice "Alt+Tab", pero se emite con `Key_Backtab`, que es
      Shift+Tab. La tabla de ayuda del Python acertaba; el nombre de la señal
      no. Estaba trabado por F7, que ahora existe.
- [x] **Ctrl+0 / Ctrl+.** in F1: a random line from anywhere in the void
      (scratch excluded — it's where lines LAND) / from this file, skipping
      whatever the entry already holds. Both only ever copy.
      *Note*: `Ctrl+0` is view-scoped in the Python and now here too — the
      random pull in F1, rebase-the-ring in F2. It had been global (rebase
      everywhere) by mistake.
- [x] **Smart copy** (`Ctrl+C` with no selection: line → paragraph → chapter) —
      `test_smart_copy` (5). There is no selection to fall back to yet (no
      selection model in `TextLine`), so every Ctrl+C is the contextual copy.

## 5. The other views

- [~] **F4 — reading**: the book set in a column and turned page by page. The
      layout idea is the Python's and worth keeping — the whole text is laid out
      ONCE as one tall column and a page is a window onto it, so "never cut a
      line across a page break" is a property of how the offsets are chosen
      rather than something the renderer worries about. Follows the F3 highlight
      (on a separator: the whole book, one section per chapter, portals skipped;
      on a chapter: that one), and opens on the paragraph you were editing when
      it's that file being shown. `_para_ordinal_at` is ported with the Python's
      own `test_open_position` cases — which is where that test finally landed.
      Still missing from this view:
      - **Justification and hyphenation.** egui has no justified layout and
        there's no Spanish hyphenation dictionary here; both are real work and
        purely typographic, so the column is ragged-right for now.
      - [x] **`Ctrl+S` exporta PDF / `Ctrl+P` imprime** (`test_print`). Resultó
        un port más fiel de lo previsto: `printpdf` renderiza HTML igual que
        `QTextDocument`, así que el formato del libro se describe una sola vez.
        Trae la justificación de regalo — el PDF sale justificado aunque F4 en
        pantalla siga en bandera. Las anclas `vparaN` van incluidas, que es lo
        que pedía `test_open_position`. *Imprimir no funciona todavía en esta
        máquina*: no hay `lp` ni CUPS en la config de NixOS, y `nix/` está
        congelado; el error lo dice en vez de fallar mudo.
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

- [x] **Multi-instance IPC**: when one instance saves, the others reload —
      `test_integrity_sync`. A port of `ipc.py` onto `std::os::unix::net` (no
      new dependency): first instance binds the socket and becomes the hub,
      later ones connect as clients, every save sends `SAVED:<path>` and the
      hub relays it to everyone else. Polled once a frame instead of
      callback-driven, with a repaint timer so a sibling's save is noticed
      without needing a keystroke first. A socket left by a crash is reclaimed.
      The socket name is voider-rs's own and deliberately NOT shared with the
      Python's: the two point at different voids, and a save here must never
      make the real Voider reload something that isn't its own.
      The line being typed is never touched by a reload — it isn't on disk yet,
      and losing it to a sibling is the exact theft this prevents.
- [x] **Mouse cursor**: the white ring, auto-hidden while typing —
      `test_cursor_autohide` (12). Trivial here; just not wired.
- [x] **Screenshots** (`F12`) — via `grim`, already on this machine and already
      in the Hyprland config. Qt's own grab can't work here: Wayland doesn't let
      a window photograph the compositor.
- [x] **Opacity** (`Ctrl+±`), persisted, floored at 30% — a window you can't see
      is a window you can't get back. Only the ground thins; the writing stays
      solid, unlike Qt's `setWindowOpacity`, which fades the text along with it.
      *This corrected a real mistake*: `Ctrl+±` had been bound to type size here
      with a comment claiming the Python did the same. It doesn't — it binds
      `opacity_up`/`opacity_down`, and size lives on F10's `←/→`.
- [x] **TTS** (`Ctrl+T`) — `piper` + `aplay`, igual que el Python, con los
      mismos argumentos y los mismos modelos `.onnx`. La detección de idioma
      es una heurística propia en vez de `langdetect`: acentos, signos de
      apertura y palabras muy frecuentes, cayendo a inglés ante la duda como
      hace el Python. Navegar corta la voz (`_tts_cut`); en F2 sigue sola
      línea por línea; F4 no habla, es una página para mirar.
- [x] **Pickers**: archivo activo (`Ctrl+F2`), carpeta del libro (`Ctrl+F3`),
      void entero (`Ctrl+F4`). El Python abre un `QFileDialog`; acá es un
      navegador propio (`browse.rs`) con la misma forma de anillo que el resto,
      porque una caja gris de GTK en el medio rompería lo único que la
      aplicación defiende. Buscando una carpeta, Enter NAVEGA y Shift+Enter
      ELIGE la carpeta donde estás — si no, no habría forma de entrar a una sin
      elegirla. Cambiar de void no toca el anterior: sólo se deja de mirarlo, y
      se limpia el historial de deshacer para que no se crucen.
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

---

## Lo que falta — al 2026-10-08 (cierre del día)

Todo esto está sin implementar. El detalle de cada ítem (archivo:línea de Python,
test que lo respalda, estado en Rust) está en `TWIN.md`; las siglas P1-n / P2-n son
las de ese documento.

### Pedido de Federico, a medias
- [ ] **Exportar por libros** (diseño ya conversado). Una tecla en F3 (propuesta:
      Ctrl+Shift+L) genera `void/libros/<TÍTULO>/`, una carpeta por libro, con
      `00 TÍTULO.txt` (la fuente) y `01 …`, `02 …` (los capítulos en orden).
      Re-exportar actualiza la carpeta generada; `I/` no se toca nunca. Lo que está
      antes del primer separador va a `_sueltos`; el portal `0` no se exporta.
      **Frenado a pedido de Federico: se revisa después.** Falta decidir en detalle
      qué entra y cómo se nombra.
- [ ] **Migrar a Python** lo que se decidió solo para Rust: el primer capítulo es
      el título/fuente (F4 y exportaciones), F3 con libros colapsables (Espacio),
      typewriter en F2, Ctrl+←/→ por palabra ya está en Python. Va al final, con
      Rust probado. En Python va primero en `proto-voider/`, con tests, y se
      promueve a `pkgs/voider-py/`. El detalle ahora está en `proto-voider/PENDING.md`.
- [~] **Probar Rust contra el void real** — desde el 2026-10-09 `~/.local/share/voider-rs/void`
      es un enlace a `/home/federico/void` (el de prueba quedó en `void.sandbox`; para
      volver: borrar el enlace y `mv void.sandbox void`). Federico va a pasar una lista
      de lo que no se comporta como Python; después se revisa Python contra esa lista.

### Antes de abrir el `/void` real con Rust
- [x] **P3-3** Canal entre instancias compartido con Python (`/tmp/voider_ipc`, mismo
      protocolo `SAVED:`). Probado solo con tests propios: **falta verlo andar contra un
      Python real** abierto sobre el mismo archivo.
- [ ] **P3-4** Un solo archivo de posiciones (`I/_last_lines.json`) y un solo
      config (hoy Rust usa `voider-rs.conf` y Python `config.json`). `voider-rs.conf` e
      `I/_last_lines.conf` están excluidos del git del void (`.git/info/exclude`): hoy el
      config de Rust **no viaja** con el repo.
- [ ] Decidir si `I.txt` entra en el snapshot de git (CLAUDE.md pide solo `I/`).

### Pantallas y teclas
- [ ] **P1-9** Pantalla de bloqueo con la contraseña del sistema (necesita PAM) y
      Escape en F1 como disparador.
- [ ] **P1-14** Teclas configurables desde el config (hoy fijas en el código).
- [ ] **P2-11 / D-5** F10 como formulario (familia, tamaño 4–999, colores, proporción
      del carrusel con medida propia). Los colores de texto/fondo no hacen nada
      en Python tampoco: decidir si se implementan en las dos o se sacan.
- [ ] **P2-12 / D-4** Ayuda (F11): una columna como Python, y decidir qué tabla queda
      (la de Python está desactualizada: F5 "Fork", F9 "Metronome").
- [ ] **P2-1** Resto de F1: recorte elíptico del renglón al círculo (hoy es una banda
      rectangular; el degradé del typewriter ya está).
- [ ] **P2-2** Líneas largas: que el cursor nunca quede fuera de la pantalla.
- [ ] **P2-6** Selección (fondo blanco, letras negras) y cursor titilando siempre
      (decisión D-7: hoy titila solo con el renglón vacío).
- [ ] **P2-8** F5: línea gris a los lados de los `/nombre`, `ø` en la fuente de la app.
- [ ] **P2-13 / D-1** Línea de estado y ayudas al pie que Python no tiene: decidir si
      se quedan.
- [ ] **P2-14** Ventana sin marco y a pantalla completa (hoy 1000×700 con marco).

### Migrar el sistema a otra computadora
- [ ] **Paquete de Nix para voider-rs** (hoy se corre con `cargo` desde el repo; Super+O
      llama a `voider-rs-dev`, en `nix/profiles/dev.nix`, que busca `target/release/voider-rs`).
- [ ] Decidir **dónde vive el config de Rust** para que viaje con el repo (ver P3-4).
- [ ] Lo que no es del programa y hay que llevar a mano: el corpus `O/` (`/mnt/data`),
      los modelos de voz `tts/`, y la config de Hyprland.

### Infraestructura
- [ ] **P1-57** `I_preview.txt` y archivos en MAYÚSCULAS por subcarpeta de `I/`, y
      resolver capítulos en subcarpetas (hoy solo `I/<nombre>`). No importa mientras
      el void sea plano.
- [ ] **P3-1** Panel de efectos de Hyprland (Super+J/K/L).
- [ ] **P3-5** Idioma de la voz: Rust usa una heurística propia, Python `langdetect`.
- [ ] **P3-6** Partir con `/` sin nombre: Python usa la fecha `%y-%m-%d_%H%M%S`, Rust
      las primeras cinco palabras.
- [ ] **D-9** Cuándo Rust pasa al `/void` real (depende de la sección de arriba).

### Para verificar en uso (se implementó con tests, no se vio en pantalla real)
- Todo el dibujo del 2026-10-07/08: `ø` en F2, foco de párrafo, F3 iluminando el
  libro bajo un punto, plegado de F3 y su punto de cierre, barra de búsqueda abajo,
  degradé del typewriter, panel de capítulos, F6/F7/F8 como anillos.
- F11 que "cambia las vistas" y F12 que "abre lo mismo que F11": no se reprodujeron;
  falta `wev` (qué tecla llega) y probar F12 con la ayuda cerrada.
- "Los puntos en F3 no me dejan pasar un título": no se reprodujo con las flechas;
  falta saber si era con Alt+↑/↓ y la forma de la lista.

### Cosas tuyas sin commitear (no las toqué)
- `proto-voider/io_mixin.py` (reintento FAT del backup), `proto-voider/config.json`,
  `roadmap/pending.txt`, `proto-voider/d`.
- Antes de cualquier rebuild: `pkgs/voider-py/config.json` ya está restaurado, pero no
  correr nunca la suite de tests de `pkgs/voider-py` (pisa ese config).

### Diferencias nuevas: Python hace y Rust no (anotar acá cada una)
- [ ] **F4 sobre un capítulo suelto que es el primero de su libro**: Python muestra su
      contenido (Federico pidió ese capítulo explícitamente); Rust hoy lo trata como título
      sin leerlo. Decidir y alinear (2026-10-09).
- [ ] Hechas en Python el 2026-10-09 y no en Rust: Ctrl+Z/redo llevan el cursor a la línea que
      cambió; posición guardada sola cada 2 s y al cerrar; Ctrl+F en F3 abre con la lista de F3
      (con separadores); refoco del editor al volver de otra ventana; candado sin caída si
      falta pam (Esc desbloquea solo sin pam); remaps en `keybindings.json`.
- [ ] F10 como lista de teclas remapeables (Python, 2026-10-09): Rust no tiene remapeo
      (P1-14); el diseño y el formato `keybindings.json` ya están definidos del lado Python.

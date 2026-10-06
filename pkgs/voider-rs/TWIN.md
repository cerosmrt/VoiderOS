# TWIN — lo que le falta a voider-rs para ser gemelo de proto-voider

Auditoría del 2026-10-06, de noche, **solo lectura**: no se tocó código. Se leyó
proto-voider entero (key_router, new_interface, f1/f2/f3/f4/f5/f5678 mixins, io_mixin,
circular_view, reorder_view, reading_page, widgets, views, controls, files, settings_panel,
help_overlay, lock_screen, fx_panel, tts, ipc, undo_manager, line_ring) y sus 117 archivos
de tests, y se comparó contra `src/main.rs` (teclas y dibujo) y `src/app.rs` (lógica).

Cómo leer cada ítem:

- **Py** = dónde está el comportamiento en Python (archivo:línea) · **Test** = el test de
  Python que lo respalda, si hay · **Rs** = qué hace Rust hoy (archivo:línea).
- **✔ verificado** = confirmado leyendo los dos códigos lado a lado, o corriendo un test.
  **? sin confirmar** = deducido pero no probado; mirarlo antes de implementar.
- Prioridad: **P0** = puede perder o romper texto · **P1** = una tecla o un comportamiento
  distinto · **P2** = se ve distinto · **P3** = secundario / infraestructura.

Al final: **D** = decisiones que son tuyas (bugs de Python que no conviene copiar, y
lugares donde Rust hace otra cosa a propósito).

---

## 0. Antes que nada (no es de Rust)

**`pkgs/voider-py/config.json` está pisado.** Anoche, más temprano en esta misma sesión, corrí los tests
viejos de `pkgs/voider-py/tests` y uno (`test_manual_picker_still_works`) escribió en el
`config.json` de producción: `void_dir` apunta a una carpeta temporal de pytest
(`/tmp/nix-shell-39120-0/...`), fuente Consolas 11. Modificado a las 00:37. Esa suite no
tiene el `conftest.py` que en proto-voider aísla el config. **Si hacés rebuild así, el
Voider del sistema arranca sin tu void.** Lo quise restaurar desde git y el sistema de
permisos no me dejó; quedó igual (`git diff pkgs/voider-py/config.json` lo muestra).
Para arreglarlo:

```bash
git -C /home/federico/VoiderOS checkout -- pkgs/voider-py/config.json
```

(El diff solo tiene valores del test; no había nada tuyo ahí.) Y conviene copiar el
`tests/conftest.py` de proto a `pkgs/voider-py/tests/`, o no correr nunca más esa suite.

---

## P0 — puede perder o romper texto

**P0-1 · El tacho borra para siempre.** ✔
Py: ida y vuelta, nunca se borra: cualquier archivo (0.txt incluido) → `trash.txt`;
desde `trash.txt` → `0.txt`. Si no se pudo escribir el destino, la línea no se saca.
`f2_mixin.py:892` · Test: `test_trash_cascade.py` (`test_nothing_is_ever_deleted_forever`,
`test_delete_from_zero_goes_to_trash`, `test_delete_from_trash_restores_to_zero`).
Rs: cascada vieja de tres niveles, archivo → 0.txt → trash → **borrado**
(`app.rs:3814 delete_line_to_zero`). Cambiar a la regla de Python y renombrar la función.

**P0-2 · Ctrl+0 (rebase) rompe el modelo de puntos.** ✔
Py: sobre un punto rota los **párrafos** (ese queda primero); sobre una línea rota las
líneas **dentro de su párrafo**. El índice 0 siempre sigue siendo un punto.
`f2_mixin.py:1117` · Test: `test_movement.py` (`test_rebase_on_text_line_rotates_paragraph`,
`test_rebase_on_dot_rotates_paragraphs`, `test_rebase_multi_line_para`).
Rs: rota el anillo entero (`app.rs:3391` → `line_ring.rs:87`): una línea de texto queda en
el índice 0 sin punto adelante.

**P0-3 · Partir (Ctrl+Shift+S) deja Voider apuntando a un archivo borrado.** ✔
Py: si el contenedor quedó vacío y se borró, el archivo activo pasa a ser el primer
capítulo sellado (`io_mixin.py:995-1001`). Rs: `current_file` sigue siendo el archivo
borrado con el anillo `['.']` (`app.rs` final de `split_at_markers`); el próximo guardado lo
vuelve a crear vacío y lo deja fuera de la biblioteca.

**P0-4 · Un nombre nuevo "0" o "." en F3 crea archivos raros.** ✔
Py: al nombrar una entrada nueva, `.` la vuelve separador y `0` la vuelve el portal del
scratch (único; los otros portales se sacan) (`f3_mixin.py:323-337`) · Test:
`test_portal.py::test_pending_new_zero_becomes_portal`, `test_portal_singleton.py`.
Rs: `new_chapter` (`app.rs:2319`) crea `..txt` o `0-2.txt`.

**P0-5 · Rust puede escribir un `I.txt` vacío.** ✔
Py: `_save_library` se niega a guardar una lista vacía (`io_mixin.py:1151`).
Rs: `Library::save` (`library.rs:89`) escribe lo que le den. Agregar el mismo guardia.

**P0-6 · F6 lee los libros crudos y las posiciones compartidas no coinciden.** ✔
Py: al abrir un libro de O/ le saca la cabecera/pie de Project Gutenberg y lo reformatea a
una oración por línea con puntos de párrafo (`f5678_mixin.py:365-471`); la posición
guardada en `O/.working_set.json` es un índice sobre **ese** anillo, y arranca en 1.
Rs: `open_o_book` (`app.rs:1350`) carga las líneas crudas del archivo. Como el
`.working_set.json` es el **mismo** archivo para las dos apps, una posición guardada por una
cae en otro lugar en la otra. Además, cuando F6 sea editable (P1-30), un guardado desde
Rust escribiría el libro en otro formato. Portar `_strip_gutenberg_boilerplate` y
`_reformat_raw_to_lines` (el reformateo ya existe en `reformat.rs`; verificar que dé las
mismas líneas).

**P0-7 · El backup copia las voces y pierde archivos con "?" en pendrives FAT.** ✔
Py: no viaja la carpeta `tts/` de la raíz del void (309 MB) (`io_mixin.py:26, 1366`); si
copiar falla con errno 22 (FAT32/exFAT rechaza `¿pregunta?.txt`), reintenta con el nombre
saneado (`io_mixin.py:1410-1444`) · Test: `test_backup_vault.py`.
Rs: `backup.rs` no excluye `tts/` y no tiene el reintento con nombre saneado.

**P0-8 · F1: lo que escribiste se pierde al moverte con ↑/↓/PageUp/PageDown.** ✔
Py: antes de moverse guarda el renglón en la línea (solo si no está vacío, es distinto, y
nunca sobre un punto) (`f1_mixin.py:152`, `key_router_mixin.py:223-238`).
Rs: `main.rs:490-497` y el PageUp/PageDown global (`main.rs:447`) mueven sin guardar.

---

## P1 — teclas y comportamiento

### Globales (`main.rs:387 handle_global_key`)

**P1-1 · PageUp/PageDown globales se roban la tecla en todas las vistas.** ✔
El manejador global corre **antes** que el de cada vista y siempre mueve el anillo del
documento (`main.rs:447`). Consecuencias: en F4 PageUp/PageDown nunca pasan página; en F6
nunca llega el salto de 10; en F3 se mueve el documento en vez de la biblioteca; en F5/F7/F8
se mueve el documento a ciegas. Py: cada vista decide (`key_router_mixin.py:223, 287, 368,
449, 189`). Sacarlo del global y ponerlo en F1 (con P0-8), F2, F3 (puntos de la
biblioteca), F4 (página) y F6 (puntos del libro, P1-30).

**P1-2 · F3 estando en F3 no hace nada.** ✔ Py: `key_router_mixin.py:73`. Rs:
`switch_to(F3)` recarga la biblioteca y te mueve el cursor.

**P1-3 · F10 vuelve a donde estabas.** ✔ Py: recuerda `_prev_view`; Esc o F10 vuelven ahí
(`key_router_mixin.py:89, 207`). Rs: Esc/Enter → F1, y F10 de nuevo reentra (`main.rs:783`).

**P1-4 · Ctrl+Shift+X abre la basura en F2.** ✔ Py: `io_mixin.py:1237` (crea `trash.txt`
vacío si no existe) · Test: `test_open_trash.py`. Rs: no existe.

**P1-5 · Ctrl+F12 abre la carpeta de capturas** (`xdg-open`). ✔ Py: `io_mixin.py:1525`.
Rs: no existe.

**P1-6 · Ctrl+P / Ctrl+S según la vista.** ✔ Py (`key_router_mixin.py:139-150`):
F2 → imprimir / PDF del archivo (HTML simple: título, líneas centradas, puntos como
espacio; `f4_mixin.py:371`, `io_mixin.py:1651-1666`); F3 → la biblioteca entera, un
capítulo por página (`io_mixin.py:1603-1649`); F4 → ver P1-27. Ambos con diálogo
(imprimir / "guardar como" con nombre propuesto). Rs: solo F4.

**P1-7 · El undo solo vale en F1, F2, F5 y F3.** ✔ Py: `new_interface.py:1223-1229`; en F3
solo si no estás escribiendo un título (ahí deshace el campo). En las demás vistas Ctrl+Z
no hace nada. Rs: global (`main.rs:438`).

**P1-8 · Undo de la biblioteca (F3).** ✔ Py: reordenar, renombrar, borrar, duplicar,
mezclar, fusionar y partir se deshacen como **un** paso que restaura `I.txt`, el cursor y
los archivos tocados (`io_mixin.py:219-277`, `undo_manager.py:45`) · Test:
`test_f3_undo.py`, `test_empty_trash.py::test_ctrl_z_brings_the_trash_back`.
Rs: `undo.rs` no tiene tipo "biblioteca"; merge/split guardan los archivos pero no el orden
de `I.txt`; reordenar y mezclar no se deshacen.

**P1-9 · Escape bloquea la pantalla.** ✔ Py: la tecla `quit` (Escape) en F1 abre la
pantalla de bloqueo con contraseña PAM (`lock_screen.py`; `key_router_mixin.py:217`; también
en view 9 y F10 tras su propio Esc). Mientras está, se come todas las teclas; Escape no la
cierra. Dibujo: fondo `rgba(0,0,0,240)`, usuario en `#888` 14pt, campo de 300 px `#1a1a1a`
borde `#333`, error "incorrect password" `#884444`. Test: `test_lock_screen.py`.
Rs: Escape en F1 no hace nada; no hay bloqueo. (Necesita PAM: crate `pam` o
`unix_chkpwd`.)

**P1-10 · Tinta: Ctrl+Shift+± atenúa el blanco aparte del fondo.** ✔ Py: dos ejes,
fondo (Ctrl+±, con las variantes `Ctrl+=`, `Ctrl+Shift+=`, `Ctrl+_`) y tinta
(Ctrl+Shift+± del numérico) (`new_interface.py:1018-1070`) · Test: `test_opacity.py`.
Rs: solo el fondo.

**P1-11 · La opacidad es de la sesión.** ✔ Py: arranca siempre opaca, no se guarda, baja
hasta 0 (`new_interface.py:136-143, 1005`) · Test: `test_opacity.py::
test_arranca_opaco_aunque_el_config_diga_otra_cosa`, `test_no_se_guardan_en_el_config`.
Rs: la guarda en el config y el mínimo es 0.3 (`app.rs:1111`, `config.rs:76`).

**P1-12 · Ctrl+Shift+W y Ctrl+Shift+T se guardan al instante.** ✔ Py: `new_interface.py:
1237-1260`. Rs: cambian el estado pero solo se escriben la próxima vez que F10 guarda
(`main.rs:420-431`; `persist_config` en `app.rs:3792`).

**P1-13 · El título fijo es solo de F2 y F5.** ✔ Py: `new_interface.py:1244`. Rs:
`draw_title` (`main.rs:1933`) lo pone en todas las vistas.

**P1-14 · Teclas configurables.** ✔ Py: todas las teclas salen de `keybindings` en
`config.json` (`app_config.py`, `key_router_mixin.py:9`). Rs: fijas en el código.
(Relacionado con D-6: qué config lee Rust.)

### F1 — escribir

**P1-15 · Escape en F1** → bloqueo (P1-9). ✔

**P1-16 · Ctrl+Enter en F1 espía 0.txt en F2** sin cambiar el archivo activo. ✔
Py: `key_router_mixin.py:95-101`, `new_interface.py:599`. Rs: no existe.

**P1-17 · `/0` + Enter** lleva al scratch y deja **un solo** portal `0` justo arriba del
capítulo actual en `I.txt`. ✔ Py: `new_interface.py:1281`, `f1_mixin.py:82` · Test:
`test_scratch_jump.py`. Rs: lo escribe como texto.

**P1-18 · Shift+Tab en F1** trae una línea del working set (cursor al principio; sin
working set no toca el renglón). ✔ Py: `f1_mixin.py:33`, `widgets.py:242` · Test:
`test_f1_shift_tab.py`. Rs: Shift+Tab hace lo mismo que Tab (`main.rs:480`).

**P1-19 · `*` (y Shift+8) también reciclan**, como Tab. ✔ Py: `widgets.py:273`. Rs: escribe `*`.

**P1-20 · Tab en F1: de dónde sale y dónde queda el cursor.** ✔ Py: un archivo `.txt` al
azar de `book_dir` (recursivo, sin ocultos, sin el activo), y una línea al azar de ese
archivo; **cursor al principio** (`controls.py:84`). Rs: todas las líneas de los capítulos
de la biblioteca juntas, cursor al **final** (`app.rs:2696`).

**P1-21 · Ctrl+0 en F1 no debe entrar en O/.** ✔ Py: `os.walk` no sigue symlinks, así que
el corpus (O/ → /mnt/data) queda afuera (`controls.py:44`). Rs: `collect_txt_files`
(`app.rs`) usa `is_dir()`, que sí sigue el symlink: sortearía entre 76 mil libros.

**P1-22 · El scratch (`` ` ``) va y vuelve como en Python.** ✔ Py: guarda la línea, recuerda
archivo y vista, consolida el portal `0` arriba del capítulo (P1-17), abre 0.txt **en su
línea guardada**; a la vuelta: desde F1 → F1, desde F2/F5 → esa vista, desde cualquier otra
→ F2 (`f1_mixin.py:126`) · Test: `test_scratch_backtick.py`. Rs: no mueve el portal, cae en
una línea en blanco al final, vuelve a cualquier vista (`app.rs:3856`).

**P1-23 · Modo barra espaciadora.** ✔ Py: `void_key: "space"` en config hace que la
barra suelte la línea siempre, no solo con Caps (`new_interface.py:149, 1169`). Rs: solo
con Caps.

### F2 — el documento

**P1-24 · Delete al final de la línea une con la siguiente** (nunca a través de un punto). ✔
Py: `circular_view.py` (`deleteAtEnd`) → `f2_mixin.py:640`. Rs: borra un carácter.

**P1-25 · Flechas que dan la vuelta y Ctrl+↑/↓.** ✔ Py (todos los editores de anillo,
`circular_view.py` `CustomLineEdit`): ← en la columna 0 salta al final; → al final salta al
principio; Ctrl+↑/↓ = inicio/fin del renglón; Ctrl+Shift+↑/↓ = seleccionar hasta ahí.
Rs: `text_line.rs:241` frena en los bordes; Ctrl+↑/↓ no existen.

**P1-26 · `*` en F2 = Tab.** ✔ Py: `circular_view.py` (`Key_Asterisk`). Rs: escribe `*`.

**P1-27 · Alt+←/→ sobre un punto abre el panel de capítulos** (de ese lado); sobre una
línea mueve la palabra. Alt+Shift+← lo abre a la izquierda. ✔ Py: `f2_mixin.py:460-490`,
`circular_view.py:189-250` (el texto se corre al otro lado). Test: `test_doc_send_keys.py`.
Rs: Alt+← sobre un punto intenta mover palabras; solo Alt+Shift+→ abre, siempre a la derecha.

**P1-28 · El panel de capítulos (F2 y F5) filtra y crea.** ✔ Py: escribir filtra,
Backspace borra el filtro, Shift+Tab/Backtab cicla hacia atrás, y si el nombre no existe
Enter **crea** el capítulo (debajo del activo en la biblioteca) y manda ahí
(`f5_reorder_mixin.py:310-450`, `widgets.py:89`). Con el scratch activo, 0.txt aparece en
la lista para que el panel abra parado ahí (`f5_reorder_mixin.py:333`). Tests:
`test_f5_send.py`, `test_f5_new_chapter_insert.py`, `test_picker_*.py`. Rs: sin filtro, sin
crear, el portal nunca aparece (`app.rs:1933-2010`).

**P1-29 · Enter al principio estando enfocado en un párrafo.** ✔ Py: sale del foco **y
sigue** (línea vacía → F1; si no, parte en 0) (`f2_mixin.py:707`). Rs: sale y no hace más
(`app.rs:2582`).

**P1-30 (ver F6)** · **P1-31 · Archivo vacío.** ✔ Py: si el archivo solo tiene puntos,
agrega un renglón en blanco y pone el cursor ahí, para poder escribir
(`io_mixin.py:64`). Rs: queda parado en un punto de solo lectura (`void.rs:27`).

**P1-32 · Tab sobre una línea selecciona el fragmento insertado.** ✔ Py: el fragmento queda
seleccionado y el próximo Tab lo reemplaza (`f2_mixin.py:318`) · Test: `test_tab_replace.py`.
Rs: sin selección visible, recuerda el rango aparte (`app.rs:2873`). Igualar: seleccionarlo.

### F3 — la biblioteca (es la vista más lejos de Python)

**P1-33 · Los títulos se renombran escribiendo encima.** ✔ Py: el renglón muestra el título
y se puede editar; al salir, navegar o Enter se renombra el archivo (rechaza `0`/`0.txt` y
nombres que ya existen; actualiza el archivo activo y el config) (`f3_mixin.py:175`) · Test:
`test_portal.py::test_rename_to_*`. Rs: en F3 solo se escribe al nombrar algo nuevo.

**P1-34 · `.` inserta un separador arriba.** ✔ Py: `f3_mixin.py:511`. Rs: no existe.

**P1-35 · Ctrl+Delete en la columna 0.** ✔ Py (`f3_mixin.py:418`): sobre un punto lo saca;
sobre el portal saca solo el marcador; sobre `trash.txt` **vacía la basura** (borra el
archivo, no manda nada a 0.txt); sobre otro capítulo manda sus líneas a 0.txt detrás de un
punto y borra el archivo; nunca sobre 0.txt. Un paso de undo de biblioteca · Test:
`test_empty_trash.py`, `test_portal.py::test_send_to_zero_removes_marker_keeps_file`.
Rs: no existe.

**P1-36 · Enter.** ✔ Py (`f3_mixin.py:231, 261`): con el cursor al principio — sobre un
punto abre la **vista concatenada** del libro (P1-43); sobre el portal abre 0.txt en F2;
sobre un capítulo lo abre (renombrando antes si lo editaste). Con el cursor al final del
nombre — confirma y abre una entrada nueva vacía debajo. Rs: sobre un punto no hace nada
(test `a_separator_opens_nothing`); no hay "Enter al final".

**P1-37 · Ctrl+Enter crea una entrada nueva**, igual que Shift+Enter, sin mirar el cursor
(funciona parado en el portal). ✔ Py: `circular_view.py` (`ctrlReturnPressed`),
`new_interface.py:660` · Test: `test_ctrl_enter.py`. Rs: Ctrl+Enter abre el capítulo.

**P1-38 · La entrada nueva aparece en la lista al instante** (renglón fantasma vacío debajo
del actual) y Escape la saca dejando el cursor en la de arriba. ✔ Py: `f3_mixin.py:371`,
`key_router_mixin.py:355` · Test: `test_f3_pending_entry.py`, `test_f3_new_entry.py`.
Rs: no se dibuja el renglón; Escape lo limpia sin mover. Archivo nuevo: Py lo crea vacío,
Rs escribe `['.']` (menor).

**P1-39 · Escape sin nada pendiente vuelve a F1.** ✔ Py: `key_router_mixin.py:367`. Rs:
se queda en F3 (`main.rs:701`).

**P1-40 · Alt+↑/↓ reordena.** ✔ Py (`f3_mixin.py:651-715`): sobre un punto mueve el
**libro entero** más allá del vecino; sobre un capítulo lo cambia con el de al lado (cruza
un separador solo si del otro lado hay un libro). Undo de biblioteca · Test:
`test_book_reorder.py`. Rs: Alt+↑ solo mueve el cursor (`main.rs:716`).

**P1-41 · Ctrl+0, Home/End, PageUp/PageDown en F3.** ✔ Py: Ctrl+0 rota la biblioteca
(`f3_mixin.py:833`); Home/End → primera/última entrada que no es punto
(`f3_mixin.py:153-173`); PageUp/PageDown → separador anterior/siguiente
(`key_router_mixin.py:368-387`). Rs: no existen (y PageUp/PageDown mueven el documento,
P1-1).

**P1-42 · Ctrl+F en F3: Enter abre el capítulo en F2.** ✔ Py: `f3_mixin.py:1060`.
Rs: solo lo resalta (`app.rs:1876`).

**P1-43 · Vista concatenada (Enter sobre un punto).** ✔ Py (`f3_mixin.py:553-627`,
`new_interface.py:824`): un anillo de solo lectura con todo el libro — por capítulo, el
encabezado `── NOMBRE ──` y sus líneas, puntos entre capítulos; ↑/↓ saltean puntos,
blancos y encabezados; Enter o Escape vuelven a F3. Rs: no existe.

**P1-44 · F3 recuerda dónde estabas, entre sesiones.** ✔ Py: al entrar busca la entrada
recordada (`last_book_index` + `last_book_entry`, guardados en `state.json`) por índice
exacto, después por nombre, después la fila del archivo activo (`f3_mixin.py:727`) · Test:
`test_f3_position.py`. Rs: siempre la fila del archivo activo.

**P1-45 · Salir de F3 activa el capítulo resaltado.** ✔ Py: cualquier salida (F1, F2, F4,
F5…) convierte el capítulo resaltado en el archivo activo, salvo puntos y portal
(`f3_mixin.py:753`, `new_interface.py:548`). Rs: solo Enter abre; F4 sigue el resaltado
pero F1/F2/F5 no.

**P1-46 · F4 sigue el resaltado de F3 aunque no vengas de F3.** ? Py: `_reading_sections`
mira siempre el cursor de F3 (`f4_mixin.py:47`); si lo dejaste sobre un punto, F4 desde F1
muestra el libro entero. Rs: solo cuando venís de F3 (`app.rs:943 enter_reading(from)`).
Depende de P1-44/45.

### F4 — leer

**P1-47 · Backspace pasa a la página anterior.** ✔ Py: `key_router_mixin.py:453`. Rs: no.

**P1-48 · El PDF y la impresión salen iguales a la pantalla.** ✔ Py: Ctrl+S / Ctrl+P en F4
(y el PDF del paquete de venta) usan **el mismo armado que la pantalla**: A5, fuente de
lectura (`reading_font`/`reading_size` 13), justificado, hifenado, tinta `#111`, una
página de PDF por página de pantalla (`io_mixin.py:1668-1703`, `reading_page.py:294`,
`f4_mixin.py:184`) · Test: `test_export_vault_pdf.py`, `test_sale_bundle.py`. Ctrl+S abre
"guardar como" con `void/<título>.pdf`; Ctrl+P abre el diálogo de impresión.
Rs: `pdf.rs` arma HTML aparte con `printpdf` (11pt, la fuente de escritura, otros márgenes),
sin diálogo, y imprime con `lp` (`app.rs:553, 928`). Hacer el PDF desde
`slides::book_plan` (los mismos renglones y posiciones que la pantalla), idealmente como
texto vectorial.

**P1-49 · Config de lectura.** ✔ Py: `reading_font` y `reading_size` en el config. Rs: no
existen (usa EB Garamond 13 fijo). Coincide con tus valores actuales.

### F5 — párrafos

**P1-50 · Picker:** ver P1-28.

### F6 / F7 / F8 — el corpus

**P1-30 · F6 se edita.** ✔ Py (`new_interface.py:712-747`, `f5678_mixin.py:517-756`,
`key_router_mixin.py:182-196`): Enter parte la línea (siempre); Backspace al principio une
con la de arriba y Delete al final con la de abajo (nunca a través de un punto); Alt+←/→
mueve palabras; Alt+↑/↓ mueve la línea (sin cruzar puntos); PageUp/PageDown van al punto
anterior/siguiente; Tab o `*` saltan a una línea al azar; cada tecla se guarda en el libro;
Ctrl+Delete en la columna 0 **cosecha** la línea (o, sobre un punto, el párrafo entero) a
0.txt y la saca del libro; Ctrl+C copia la línea o el párrafo. Navegar se detiene también
en los puntos (renglón bloqueado). La posición se guarda en cada movimiento. Escape → F1.
Tests: `test_o_editable.py`, `test_o_editing_parity.py`. Rs: solo navega
(`main.rs:821`); Escape → F7.

**P1-51 · De F6 a F1 te llevás la línea.** ✔ Py: al pasar de F6 a F1 la línea actual del
libro queda en el renglón, seleccionada (`new_interface.py:567-592`). Rs: no.

**P1-52 · F7 → F6 con la tecla F6 abre el resaltado.** ✔ Py: `new_interface.py:523`. Rs:
`enter_o_reader` solo abre si no había libro.

**P1-53 · F7 guarda en cada movimiento** el índice resaltado (`browser_index` en
`.working_set.json`). ✔ Py: `f5678_mixin.py:335`. Rs: `corpus.rs` lee y escribe el campo, pero
`app.rs` nunca le pasa `ws_index`: F7 arranca siempre en la primera ranura.

**P1-54 · F8: el renglón se puede editar** antes de quedártelo. ✔ Py: CircularView con
editor (`new_interface.py:777`). Rs: texto fijo. (Qué hace Enter: ver D-2.)

**P1-55 · La voz en F6 y F8.** ✔ Py: en F6 lee seguido el libro, con pre-render de la línea
siguiente para que no haya silencio entre líneas; en F8 lee la línea del oráculo; al
cambiar de vista con la voz prendida, cada vista arranca su lectura (`tts_mixin.py:
87-189`). Rs: solo F1/F2/F5, sin pre-render, no reacciona al cambio de vista
(`app.rs:1424-1480`).

### Arranque

**P1-56 · Qué vista se restaura.** ✔ Py: solo F1–F4; F5 en adelante arranca en F1
(`new_interface.py:477`) · Test: `test_startup_restore.py`. Rs: también F6/F7 (test
`f6_y_f7_son_vistas_a_las_que_se_vuelve_al_reiniciar`).

**P1-57 · `I_preview.txt` y archivos en MAYÚSCULAS por subcarpeta.** ✔ Py: al arrancar
(`io_mixin.py:325`). Con tu `I/` plano no hace nada hoy. Rs: no existe. Junto con esto:
Python resuelve capítulos en **subcarpetas** de `I/` (`io_mixin.py:1104`); Rust solo
`I/<nombre>` (`library.rs:31`). P3 mientras tu void sea plano.

---

## P2 — se ve distinto

**P2-1 · F1: el renglón se recorta al círculo y se apaga hacia el borde.** ✔ Py: máscara
elíptica sobre el renglón (nada se ve fuera del círculo, ni las esquinas de letras altas)
y, en typewriter, un degradé del color del fondo desde el borde del círculo hasta el 55%,
con el círculo redibujado encima (`views.py:37-136`, `new_interface.py:901-962`) · Tests:
`test_edge_fade*.py`, `test_entry_clip.py`. Rs: recorte rectangular, sin degradé
(`main.rs:949`).

**P2-2 · Líneas largas: el cursor nunca se va de la pantalla.** ? Py: el renglón es un
QLineEdit (F1: ancho `min(w,h)-90`; F2/F3: `w-100`) que se desplaza para mostrar el cursor.
Rs: la línea va centrada y se corta en los dos bordes; con una línea más ancha que la
ventana el cursor puede quedar afuera (`main.rs:886`). En el anillo, Py alinea a la
izquierda del margen las líneas que no entran (`circular_view.py:299`).

**P2-3 · El ø en el punto índice 0 de F2.** ✔ Py: en el anillo y en el renglón
(`circular_view.py:296-309`, `f2_mixin.py:34`). Rs: dibuja `.`.

**P2-4 · Foco de párrafo y F3 sobre un punto.** ✔ Py: enfocado, lo que no es el párrafo va
al 10% (`circular_view.py:282`); en F3 parado en un punto se ilumina el libro que abre
(mismo `edit_alpha` que F2). Rs: `draw_f2` no mira el foco; `draw_f3` usa `on_dot=false`
siempre (`main.rs:984-1161`).

**P2-5 · La búsqueda (Ctrl+F).** ✔ Py: la barra va **abajo** (`h - alto - 24`), ancho
`min(w-100, 800)`, la fuente normal, subrayada, con placeholder; la lista no da la vuelta
(no se dibuja más allá de los extremos); lo que no es el centro va al 30% del anillo
(`new_interface.py:198-225, 963-970`; `circular_view.py:270-281`). Rs: la barra arriba en
55% de tamaño, la lista da la vuelta (`main.rs:968-1039`).

**P2-6 · Selección.** ✔ Py: fondo blanco, letras negras. Rs: banda blanca al 27% detrás
(`main.rs:926`). Cursor: Qt titila siempre, 1 px; Rust titila solo con el renglón vacío,
2 px (ver D-7).

**P2-7 · El panel de capítulos.** ✔ Py: 38% del ancho (F2 y F5), misma fuente que el
anillo, salto 1.31, curva del anillo × 0.3, arriba el filtro o "escribí para filtrar…"
(al 45%), abajo "→ enviar   ⏎ nuevo   ⇥ ciclar" (al 30%), `ø` si no hay nada; sin línea
divisoria en F2 (en F5 sí, gris 40) (`widgets.py:89-146`, `circular_view.py:242`). Rs:
32% en F2, fuente 4 px más chica, salto 1.9, grises escalonados, "→ enviar ← volver",
divisoria en las dos (`main.rs:988, 1261`).

**P2-8 · F5: los `/nombre`.** ✔ Py: línea gris (60) a los dos lados con el nombre en gris
180 (`reorder_view.py:219`); vacío = `ø` gris 45 en la fuente de la app. Rs: `/nombre` como
texto común; `ø` a 48 px.

**P2-9 · F6/F7/F8 son anillos en modo edición.** ✔ Py: centro = renglón editable, el resto
× 0.3 (como F2). F8 muestra `.` arriba y la línea en el centro. Rs: F6/F7 sin atenuar
(`main.rs:1691`), F8 una sola línea envuelta al 62% en gris 225.

**P2-10 · F9.** ✔ Py: márgenes laterales `max(60, 12% del ancho)`, 44 px arriba/abajo,
texto `#dddddd`, selección `#444` (`new_interface.py:795-822`). Rs: 22%, 56 px, gris 225
(`main.rs:1362`).

**P2-11 · F10.** ✔ Py: formulario Qt — familia (todas las del sistema), tamaño 4–999 pt,
color de texto, color de fondo, proporción del carrusel y medida propia, botón Apply,
"Press F10 or Esc to close without applying" (`settings_panel.py`). Rs: lista de fuentes
con flechas, tamaños de una tabla fija de 11 a 170, Tab para el carrusel, guarda al
instante (`main.rs:1308`). (Los colores en Python casi no se usan: ver D-5.)

**P2-12 · F11.** ✔ Py: una columna, filas de 22 px, teclas en gris 185, descripción gris
95, secciones gris 70, "any key  close" (`help_overlay.py`). Rs: dos columnas y otro texto
(ver D-4).

**P2-13 · Lo que Rust dibuja y Python no.** ✔ Línea de estado abajo (`main.rs:2023`),
contador de página en F4 (`main.rs:1623`), título del libro abajo en F6, ayudas al pie de
F7/F8/F10. Python no tiene nada de eso: imprime a la consola. Ver D-1.

**P2-14 · Ventana.** ✔ Py: sin marco, pantalla completa (`new_interface.py:165, 855`).
Rs: ventana de 1000×700 con marco (`main.rs:53`).

---

## P3 — secundario / infraestructura

**P3-1 · FX de Hyprland (Super+J/K/L).** ✔ Py: un panel encima de todo para afinar CRT,
grano y blanco y negro; lo pide Hyprland dejando un archivo `voider-fx-panel` en el
temporal (sondeo cada 100 ms), escribe `voider-fx` y corre `voider-fx-update`
(`fx_panel.py`, `new_interface.py:859-885`). Rs: no existe. Solo importa cuando Rust sea
el escritorio.

**P3-2 · Hyprland: transparencia real.** ✔ Py: al arrancar le pide a Hyprland
`alphaoverride/alpha/alphafullscreen*/noblur` para que no atenúe ni desenfoque la ventana
(`new_interface.py:1111-1154`) · Test: `test_opacity.py`. Rs: no.

**P3-3 · IPC con Python.** ✔ Rs usa su propio socket `voider-rs.sock` a propósito
(`ipc.rs:17-35`) para no molestar al Voider real mientras usa el void de prueba. El día que
Rust abra `/void`, tiene que hablar el mismo protocolo en el mismo nombre que
`QLocalServer("voider_ipc")`, o un Python y un Rust abiertos a la vez se pisan.

**P3-4 · Archivos de estado compartidos.** ✔ Mismo archivo en las dos: `O/.working_set.json`,
`.o_files_cache.txt`, `I.txt`. Distintos: posiciones por archivo (Py
`I/_last_lines.json`, JSON; Rs `I/_last_lines.conf`) y configuración (Py `config.json` +
`state.json` junto al programa; Rs `void/voider-rs.conf`). Para que las dos retomen en la
misma línea, Rust debería leer y escribir `_last_lines.json`. (Config: ver D-6.)

**P3-5 · Idioma de la voz.** Py usa `langdetect`; Rs una heurística propia
(`tts.rs:49`). Puede elegir otra voz en textos cortos o mezclados. Si molesta: crate
`lingua`.

**P3-6 · Partir con `/` sin nombre.** ✔ Py: nombre por fecha `%y-%m-%d_%H%M%S`
(`io_mixin.py:951`). Rs: las primeras cinco palabras del texto (`split.rs:70`).

**P3-7 · Detalles chicos.** Barajar el scratch: Py retoma la línea guardada, Rs va al 0. F3
al dejar un renglón con `·` vs `.` (Py muestra `· · ·` al cargar y `.` al navegar —
inconsistencia de Python, no copiar).

---

## D — decisiones tuyas

(Los dos tests que confirman D-2 y D-3 corrieron fuera del repo, en el scratchpad de esta
sesión: `verify_py/test_verify_py_bugs.py`. Si se arregla Python, son el punto de partida.)

**D-1 · ¿Rust muestra mensajes en pantalla?** Python no tiene línea de estado: todo va a
la consola, que en el escritorio no ves. Rust muestra "→ 0.txt", "Shuffled", errores de
PDF, etc. Gemelo exacto = sacarlos. Mi recomendación: dejarlos (sin consola, un error
silencioso es peor) o llevarlos también a Python.

**D-2 · F8 Enter — bug de Python, no copiar.** ✔ verificado con un test. En Python, Enter
en F8 reemplaza el anillo del lector de F6 por `['.', línea]` **sin soltar el libro
abierto** y salta a F5 (que hoy es reordenar párrafos, no el viejo "transform")
(`f5678_mixin.py:107-115`). Si después pasás a F6 y escribís algo, el guardado escribe
**ese anillo de dos líneas encima del libro de O/** — y O/ no tiene git. Rust hace lo que
decía la intención original: mete la línea en el documento debajo de donde estabas.
Propuesta: arreglar Python para que haga lo de Rust.

**D-3 · F1 Alt+↑/↓ — bug de Python, no copiar.** ✔ verificado con un test. Python cambia
`current_file_path` al archivo siguiente (orden alfabético de `book_dir`) **sin recargar
el anillo** (`io_mixin.py:1299-1319`); el próximo Enter escribe el contenido del archivo
anterior encima del nuevo. Rust recarga (`app.rs:3402`, en orden de biblioteca). Propuesta:
arreglar Python (recargar, y decidir si el orden es el de `I.txt` como en Rust).

**D-4 · La ayuda (F11).** La tabla de Python está desactualizada: dice que F5 es "Fork" y
F9 "Metronome". Rust tiene una propia y correcta. ¿Copiar la de Python tal cual, o
corregir la de Python y que las dos digan lo mismo?

**D-5 · Colores en F10.** En Python `text_color` solo se aplica al arrancar y lo pisa enseguida
`_repaint_surfaces`; `bg_color` se guarda pero nadie lo lee (`new_interface.py:160, 1080`).
O sea: hoy no hacen nada. ¿Se implementan de verdad (en los dos) o se sacan del formulario?

**D-6 · ¿Un solo config?** Rust tiene `voider-rs.conf` en el void; Python `config.json`
junto al programa. Para que sean gemelos de verdad (fuente, tamaño, teclas, carrusel,
carpetas de venta), Rust podría leer el `config.json` de Python. Tu `font_size` es 22 en
proto; Rust usa 22 por defecto (en pt, igual que Python), así que hoy coinciden.

**D-7 · El cursor.** Rust titila solo con el renglón vacío (decisión tuya de antes: "la
última letra es lo que mirás"). Python titila siempre. ¿Se queda así?

**D-8 · F5 y la voz.** Python en F5 lee el texto del renglón de F1 (resto de cuando F5 era
otra cosa). Rust lee el párrafo actual. Rust tiene razón; ¿arreglar Python?

**D-9 · ¿Cuándo pasa Rust al `/void` real?** Hoy usa el void de prueba. Antes de eso hacen
falta P0 completo, P3-3 (IPC) y P3-4 (posiciones).

---

## Orden sugerido para la mañana

1. **0** (config de voider-py) — vos, un comando.
2. **P0-1 … P0-8**, uno por commit, test primero.
3. **P1-1** (PageUp/PageDown) — destraba F3/F4/F6.
4. **F3 completo**: P1-33 … P1-46 (es donde más se nota la diferencia).
5. **F2**: P1-24 … P1-32.
6. **F1**: P1-15 … P1-23.
7. **F6/F7/F8**: P1-30, P1-51 … P1-55.
8. **F4 PDF** (P1-48), globales restantes (P1-2 … P1-14), arranque (P1-56).
9. **P2** visual, de a una pantalla, comparando capturas con el harness de Xvfb.
10. **P3** y las **D** según lo que decidas.

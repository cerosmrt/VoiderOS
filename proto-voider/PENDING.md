# proto-voider (Python) — lo que falta

Pendientes de la versión Python. Los de Rust están en `pkgs/voider-rs/PENDING.md`.
Se desarrolla en `proto-voider/` con tests primero, y recién después se promueve a
`pkgs/voider-py/` (copia byte-idéntica de cada commit). Nunca correr los tests de
`pkgs/voider-py` (pisan su `config.json`).

## Decididas en Rust, falta llevarlas a Python
- [ ] **Primer capítulo de cada libro = título y fuente.** F4 abre con una página que
      muestra solo el nombre del libro; el texto de ese capítulo nunca se lee (tampoco
      en PDF/EPUB/TXT/carrusel/paquete de venta).
- [ ] **F3 con libros colapsables** (Espacio abre/cierra, por defecto cerrado, se
      recuerda por archivo-título). Fila `· TÍTULO · (n)` con n = capítulos sin contar
      el título; el punto de cierre se dibuja visualmente.
- [ ] **Typewriter en F2**: todas las líneas arrancan en el centro y corren a la derecha.
- [ ] **Sin cursor en filas de solo lectura** (F3).
- [ ] **Degradé del typewriter en F1** (revisar contra el de Rust).
- [x] Ctrl+←/→ por palabra (ya estaba en Python).
- [ ] **Exportar por libros** (`void/libros/<TÍTULO>/`, `00 TÍTULO.txt`, `01 …`). Diseño
      frenado: se revisa antes de implementar en cualquiera de las dos.

## Cosas que Rust ya hace y Python no (a decidir)
- [ ] **Canal entre instancias**: Rust ya usa `voider_ipc`; falta verlo andar contra
      este Python real con el mismo archivo abierto.
- [ ] **P3-4** Un solo archivo de posiciones (`I/_last_lines.json`) y un solo config.
- [ ] **P3-5** Idioma de la voz (`langdetect` acá, heurística en Rust).
- [ ] **P3-6** Partir con `/` sin nombre: acá usa fecha `%y-%m-%d_%H%M%S`, Rust las
      primeras cinco palabras. Decidir cuál queda.
- [ ] **Ayuda (F11)**: la tabla está desactualizada (F5 "Fork", F9 "Metronome").
- [ ] **Backup a FAT**: reintento en `io_mixin.py` (cambio tuyo, sin commitear).

## Lista de Federico tras probar Rust contra el void real
- [ ] Federico pasa lo que no se comporta como Python; se revisa Python contra esa
      lista (aún vacía).

## Cosas tuyas sin commitear (no las toqué)
- `proto-voider/io_mixin.py`, `proto-voider/config.json`, `roadmap/pending.txt`,
  `proto-voider/d`.

## Bugs que pasaste (2026-10-09), en este orden
- [x] 8. Omitir el contenido del primer capítulo de un libro en F4 / slides / PDF / EPUB / TXT
      (queda el título, sin página aparte). Si se pide ese capítulo suelto, se muestra entero.
      Tests escritos (fallan); falta implementar. Esperando que cierres proto.
- [x] 2. Esc → pide contraseña (`lock_screen.py`), con cualquier clave se "bugea" y sale.
- [x] 7. Ctrl+Z restaura también la posición del cursor (`undo_manager.py`).
- [x] 6. A veces no se guarda la posición del cursor al cerrar.
- [~] 1. Comando en F2 que borra todos los separadores (para hacer shuffle).
- [x] 5. Ctrl+F en F3 debe verse igual que F3.
- [~] 4. Opacidad (Windows empaquetado): al bajarla el fondo se aclara pero el input queda negro.
- [x] 3. Menú de remapeo de teclas con JSON propio (solo los cambios), para que un exe nuevo no pise.
- [x] 9. Al volver a Voider desde otra ventana (VSCodium) no andan flechas arriba/abajo ni las
      letras, pero sí RePág/AvPág. Hipótesis: al reactivarse la ventana el foco no vuelve al
      editor (`_refocus_active_editor` en `key_router_mixin.py` solo se llama al cambiar de vista).
- Nota del 2 (candado): el Python del launcher `proto-voider` no tiene `python-pam`; falta
  agregarlo en Nix (lo hace Federico con el rebuild). Mientras tanto, sin pam, Esc desbloquea.
- Nota 1: ya existe `collapse_paragraphs` (Ctrl+Shift+Delete) en F2, pero solo actúa con el cursor
  en el primer punto; decidir si hay que relajar esa condición.
- Nota 4: el fix de input transparente está en el código desde 2026-09-10 (c79ff45); el .exe de
  Windows probablemente es anterior. Reconstruir el exe y probar antes de tocar más.
- Nota 3: hecha la capa keybindings.json; falta el MENÚ en la app para remapear (sin diseñar).

## F10 como lista tipo F3 (pedido de Federico, 2026-10-09)
Diseño: F10 es un anillo de renglones como F3. El primer renglón es el título
("Configuración", no editable); los demás son parámetros/funciones con su valor o tecla.
↑/↓ y RePág/AvPág navegan; Enter entra al renglón: en uno de tecla, se aprieta la combinación
nueva y se guarda en `keybindings.json`; en uno de ajuste, se ve o se cambia el valor.
- [x] **Fase 1 (B, hecha 2026-10-09):** solo las teclas son renglones. El formulario actual de F10
      (fuente de lectura, tamaño, carrusel, hifenación, carpetas de venta) queda como está.
- [x] **Fase 2 (A, hecha 2026-10-09):** los ajustes del formulario también pasan
      a ser renglones de la lista y el formulario viejo se retira.

## Accesibilidad: menú clicable (pedido de Federico, 2026-10-09) — después de F10
Su coach le pidió trabajar la accesibilidad. Idea: una barra de menú clicable (Archivo,
Exportar, Guardar, Salir, Menú, Opciones…) que **aparece solo al mover el mouse y se oculta
al usar el teclado** (mismo criterio que el cursor auto-oculto, `cursor_autohide.py`).
Cada entrada llama a las funciones que hoy están solo en teclas. Falta diseñar: qué entradas,
y cómo se muestra la tecla de cada una (se puede leer de `keybindings.json`). Rust después.
- Fase 1 hecha: F10 abre `KeysPanel` (`keys_panel.py`, modelo `keys_model.py`); Enter captura la
  tecla nueva, Supr restaura el default, la última fila "Ajustes…" abre el formulario de antes.
  Falta verlo en pantalla real (solo probado con tests). Los nombres de acción se muestran
  tal cual (`view f1`, `help`…): faltan etiquetas legibles. No avisa choques entre vistas a
  propósito (Alt+↑ ya repite entre acciones de vistas distintas).

## Hecho el 2026-10-09 (sin probar en pantalla real — Federico prueba al final)
- F10 fase 2: ajustes como renglones (`keys_model.py`, `keys_panel.py`); `settings_panel.py` retirado.
  Faltan etiquetas legibles para las acciones y avisos de elegir fuente/color con vista previa.
- Menú clicable (`menu_bar.py`, `menu_model.py`): aparece al mover el mouse, se oculta con una tecla;
  cada entrada presiona la tecla de su acción. Pendiente de verlo: tamaño/posición sobre cada vista,
  si tapa algo importante, y si hace falta un modo "siempre visible" y navegación del menú con teclado
  (accesibilidad real: lector de pantalla / foco). Las entradas son una primera lista.

## Visualizador de audio (pedido de Federico, 2026-10-09) — hecho, sin probar en pantalla real
Alrededor del círculo de F1/F2, tres estilos (F10 → `visualizer style`): pulso, onda
(osciloscopio curvado) y barras (espectro). Fuente (`visualizer source`): apagado (por defecto),
micrófono, o salida (monitor de PipeWire: TTS, YouTube, lo que suene). Viene del `AudioMonitor`
de las primeras versiones (solo volumen, solo salida), ahora con mic, onda y espectro.
Por verificar en uso: que `pyaudio` encuentre el dispositivo *monitor* en tu PipeWire (si no,
`AudioMonitor.status` lo dice y la animación queda quieta); cuánto dibuja en el margen de 35 px;
y en Windows la salida (monitor) no existe: allí solo sirve el micrófono (hace falta WASAPI loopback).
Ideas: más estilos, elegir dispositivo concreto, sensibilidad (hoy `GAIN=6`), mostrarlo en más vistas.

## Dictado (hablar → el void escribe) — hecho; probado de punta a punta con voz de piper
Ctrl+Shift+Space (remapeable en F10) enciende/apaga. Encendido, escucha siempre; cada frase (voz +
pausa de ~1 s) se transcribe con faster-whisper (offline, en proceso) y se inserta en el cursor de la
línea enfocada: se puede seguir tecleando y corregir en el medio. Idioma `dictation_language`
(es/en/auto) en F10; modelo `dictation_model` (small) en `<void>/stt/` (ya descargado, fuera de git).
**Para que ande en proto hace falta TU rebuild**: `faster-whisper` (y `python-pam`) ya están en
`nix/profiles/dev.nix`. La primera vez que se enciende carga el modelo (~30 s, dice "cargando").
Whisper.cpp de nixpkgs (1.7.5) se cae al cargar (le falta el backend de CPU), por eso faster-whisper.
Medido: ~6 s por frase en CPU. Falta probar con micrófono real y ruido de cuarto.
Pendiente / ideas: pausar el dictado mientras habla el TTS (si no, se transcribe a sí mismo);
comandos de voz ("punto", "nueva línea"); modo en vivo; modelo más chico (`base`) si `small` va lento;
aviso de "sin modelo" más visible; en F3/F5 solo se inserta si hay un campo de texto enfocado.

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
- [ ] 7. Ctrl+Z restaura también la posición del cursor (`undo_manager.py`).
- [ ] 6. A veces no se guarda la posición del cursor al cerrar.
- [ ] 1. Comando en F2 que borra todos los separadores (para hacer shuffle).
- [ ] 5. Ctrl+F en F3 debe verse igual que F3.
- [ ] 4. Opacidad (Windows empaquetado): al bajarla el fondo se aclara pero el input queda negro.
- [ ] 3. Menú de remapeo de teclas con JSON propio (solo los cambios), para que un exe nuevo no pise.
- [ ] 9. Al volver a Voider desde otra ventana (VSCodium) no andan flechas arriba/abajo ni las
      letras, pero sí RePág/AvPág. Hipótesis: al reactivarse la ventana el foco no vuelve al
      editor (`_refocus_active_editor` en `key_router_mixin.py` solo se llama al cambiar de vista).
- Nota del 2 (candado): el Python del launcher `proto-voider` no tiene `python-pam`; falta
  agregarlo en Nix (lo hace Federico con el rebuild). Mientras tanto, sin pam, Esc desbloquea.

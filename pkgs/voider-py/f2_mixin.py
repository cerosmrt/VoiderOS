# f2_mixin.py — F2 doc editor methods
import os
import random
import re

from PyQt6.QtCore import Qt

from line_ring import LineRing


def split_on_spaces(text):
    """Devolverle los saltos de línea a un texto de scriptio continua fundido.

    En scriptio continua la barra espaciadora suelta la línea al void, así que
    dentro de una línea el espacio no separa palabras: ES el salto de línea que
    se perdió. Partir por espacio devuelve exactamente los fragmentos que
    escribió. Un punto que ya estuviera en el texto también corta — eso no
    cambió — pero no se le agrega ninguno a lo que no tenía.

    Ya NO puntúa. Antes le agregaba un punto a cada fragmento, porque F9 unía
    todo lo que hubiera entre dos puntos sin mirar qué tenía cada línea, y sin
    puntuación el texto se fundía en una sola línea al volver de ahí. Con el
    arreglo del "cojoiner" de F9 (reading_page.lines_to_paragraphs, que ahora
    sólo une una línea con la siguiente si la primera ya cierra una oración),
    ese parche dejó de hacer falta: una línea sin puntuación sobrevive sola.
    """
    return [p for p in re.split(r'[\s.]+', text.strip()) if p]


class F2Mixin:

    _ZERO_GLYPH = 'ø'

    def _doc_editor_text(self):
        """Text the F2 editor should show for the current line: the ø glyph when
        parked on the index-0 marker (so it stays marked while highlighted instead
        of looking like a plain '.'), otherwise the line itself. The ring keeps
        '.' — this is display only, and the marker line is read-only."""
        cur = self.line_ring.current()
        if self.circular_view.zero_marker and self.line_ring.index == 0 and cur == '.':
            return self._ZERO_GLYPH
        return cur

    def _smart_copy(self):
        """Ctrl+C with no selection: copy the contextual unit to the clipboard.

        F2 (view 1): the current line, or — when sitting on a '.' — the paragraph
        that follows it (the block highlighted on a dot). F3 (view 2): the raw text
        of the highlighted chapter. Other views do nothing.
        """
        from PyQt6.QtWidgets import QApplication
        text = None
        if self.current_view == 1:
            ring = self.line_ring
            cur = ring.current()
            if cur == '.':
                lines, n, i, para = ring.lines, len(ring.lines), ring.index + 1, []
                while i < n and lines[i] != '.':
                    para.append(lines[i]); i += 1
                text = '\n'.join(para)
            else:
                text = cur
        elif self.current_view == 2:
            ring = self.book_ring
            if ring and ring.lines and ring.current() == '.':
                # On a '.' separator → copy the whole book (the group below it),
                # chapters concatenated with a '.' between, scratch portals skipped.
                parts = []
                n = len(self._library_lines)
                i = (ring.index + 1) % n
                for _ in range(n - 1):
                    fn = self._library_lines[i]
                    if fn == '.':
                        break
                    if fn != '0.txt':
                        fp = self._library_path_cache.get(fn)
                        if fp and os.path.isfile(fp):
                            from widgets import chapter_title_header
                            try:
                                with open(fp, 'r', encoding='utf-8', errors='replace') as f:
                                    body = f.read().rstrip('\n')
                                parts.append(chapter_title_header(fn) + '\n' + body
                                            if body else chapter_title_header(fn))
                            except Exception as e:
                                print(f"⚠️ Copy error: {e}")
                    i = (i + 1) % n
                text = '\n.\n'.join(parts) if parts else None
            else:
                fname = self._library_current_fname()
                if fname:
                    fpath = self._library_path_cache.get(fname)
                    if fpath and os.path.isfile(fpath):
                        from widgets import chapter_title_header
                        try:
                            with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                                body = f.read().rstrip('\n')
                            header = chapter_title_header(fname)
                            text = header + '\n' + body if body else header
                        except Exception as e:
                            print(f"⚠️ Copy error: {e}")
        if text:
            QApplication.clipboard().setText(text)
            print(f"📋 Copied {len(text)} char(s)")

    def _doc_show_editor(self):
        """Show F2 editor with current doc line, cursor at start."""
        if not self.circular_view or not self.line_ring.lines:
            return
        view = self.circular_view
        view.edit_mode = True
        center_y = view.height() // 2
        # Use almost the full width (drop the 800px cap) so a long line stays
        # visible while editing instead of scrolling out the right edge.
        editor_width = view.width() - 100
        view.editor.setFixedWidth(editor_width)
        view.editor.move(
            (view.width() - editor_width) // 2,
            center_y - view.editor.sizeHint().height() // 2
        )
        view.editor.setText(self._doc_editor_text())
        view.editor.setCursorPosition(0)
        view.editor.setReadOnly(self.line_ring.current() == '.')
        # The ø behaves like any dot: white when you're on it (no red, no select).
        self._apply_editor_style(view.editor)
        view.editor.show()
        view.editor.setFocus()
        view.update()

    def _doc_random_line(self):
        """* in F2: jump to a random non-dot line in the current document."""
        candidates = [i for i, l in enumerate(self.line_ring.lines) if l != '.']
        if not candidates:
            return
        self.line_ring.index = random.choice(candidates)
        self.circular_view._offset = 0.0
        self.circular_view.editor.setText(self._doc_editor_text())
        self.circular_view.editor.setCursorPosition(0)
        self._apply_editor_style(self.circular_view.editor)
        self.circular_view.editor.setReadOnly(False)
        self.circular_view.update()

    def _random_line_from_dir(self, directory, exclude_path=None):
        """Pick a random non-empty, non-dot line from a random .txt in directory
        (recursively). Returns the line or None. The source file is never
        modified — this is a copy (cut-up)."""
        try:
            txts = []
            for root, dirs, files in os.walk(directory):
                for f in files:
                    if f.lower().endswith('.txt') and not f.startswith('.'):
                        p = os.path.join(root, f)
                        if exclude_path and os.path.abspath(p) == os.path.abspath(exclude_path):
                            continue
                        txts.append(p)
            random.shuffle(txts)
            for p in txts:
                try:
                    with open(p, 'r', encoding='utf-8', errors='replace') as fh:
                        lines = [l.strip() for l in fh
                                 if l.strip() and l.strip() != '.']
                except OSError:
                    continue
                if lines:
                    return random.choice(lines)
        except Exception as e:
            print(f"⚠️ random line scan failed: {e}")
        return None

    def _doc_refresh_editor(self, select=False):
        """Repaint F2 and sync the editor to the current ring line."""
        cur = self.line_ring.current()
        ed = self.circular_view.editor
        self.circular_view._offset = 0.0
        ed.setText(self._doc_editor_text())
        if select:
            ed.selectAll()
        else:
            ed.setCursorPosition(0)
        ed.setReadOnly(cur == '.')
        is_zero_dot = self.circular_view.zero_marker and self.line_ring.index == 0
        self._apply_editor_style(ed, red=is_zero_dot)
        self.circular_view.update()

    def _dispatch_paragraphs(self):
        """Ctrl+Shift+D in F2: dispatch paragraphs tagged with /name markers.

        Scans the ring for lines starting with '/'. The paragraph ABOVE the marker
        (between the preceding '.' and the marker) is appended to name.txt in the
        I/ folder. '/' alone generates a timestamped filename. The paragraph and its
        marker are removed from the ring; untagged paragraphs stay.
        """
        import datetime
        ring = self.line_ring
        lines = list(ring.lines)
        dispatched_indices = set()
        i_dir = self.book_dir

        # Identify paragraphs and their dispatch targets
        # A paragraph = a block of lines between two '.' separators
        # Find all marker lines (start with '/')
        for idx, line in enumerate(lines):
            if not (isinstance(line, str) and line.startswith('/')):
                continue
            name = line[1:].strip()
            if not name:
                ts = datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')
                name = ts
            dest = os.path.join(i_dir, name + '.txt')

            # Collect the paragraph above: walk backwards to the previous '.' or start
            para = []
            para_indices = []
            j = idx - 1
            while j >= 0 and lines[j] != '.':
                para_indices.append(j)
                j -= 1
            para = [lines[k] for k in reversed(para_indices)]

            if not para:
                dispatched_indices.add(idx)
                continue

            # Append paragraph to destination file
            try:
                sep = '\n.\n' if os.path.exists(dest) else ''
                with open(dest, 'a', encoding='utf-8') as f:
                    if sep:
                        f.write(sep)
                    f.write('\n'.join(para) + '\n')
            except Exception as e:
                print(f"⚠️ Dispatch error writing {dest}: {e}")
                continue

            dispatched_indices.add(idx)
            dispatched_indices.update(para_indices)
            print(f"📤 {len(para)} lines → {os.path.basename(dest)}")

        if not dispatched_indices:
            return

        # Rebuild ring without dispatched lines; collapse double-dots
        new_lines = [l for i, l in enumerate(lines) if i not in dispatched_indices]
        # Collapse consecutive dots
        cleaned = []
        for l in new_lines:
            if l == '.' and cleaned and cleaned[-1] == '.':
                continue
            cleaned.append(l)
        if not cleaned or cleaned == ['.']:
            cleaned = ['.']

        ring.lines = cleaned
        ring.index = min(ring.index, len(cleaned) - 1)
        self.auto_save_circular()
        self.load_doc_lines()

    def _doc_tab(self):
        """Contextual Tab in F2:
          - on the ø zero-marker (index 0): shuffle the paragraph ORDER (each
            paragraph keeps its lines in their relative order).
          - on a '.' separator: shuffle the LINES within that paragraph.
          - on a content line: insert a random I/ line below the cursor,
            selected, so repeated Tab re-rolls it (source file untouched).
        """
        ring = self.line_ring
        if not ring.lines:
            return
        if self.circular_view.zero_marker and ring.index == 0:
            self._doc_shuffle_paragraphs()
        elif ring.current() == '.':
            self._doc_shuffle_para_lines()
        else:
            self._doc_insert_random_i_line()

    def _doc_shuffle_paragraphs(self):
        """Tab on ø: shuffle paragraph order; lines keep their order inside each."""
        _, paragraphs = self._paragraphs_from_ring()
        if len(paragraphs) < 2:
            return
        random.shuffle(paragraphs)
        self._rebuild_ring_from_paragraphs(paragraphs)
        self.line_ring.index = 0          # stay on the ø
        self.auto_save_circular()
        self._doc_tab_cand = None
        self._doc_refresh_editor()

    def _doc_shuffle_para_lines(self):
        """Tab on a '.': shuffle the lines within that paragraph (needs >=2)."""
        k, paragraphs = self._current_para_idx()
        if k is None:
            return
        if len(paragraphs[k]) < 2:
            return
        random.shuffle(paragraphs[k])
        dot_idx = self._dot_line_index(k, paragraphs)
        self._rebuild_ring_from_paragraphs(paragraphs)
        self.line_ring.index = dot_idx    # stay on the same separator
        self.auto_save_circular()
        self._doc_tab_cand = None
        self._doc_refresh_editor()

    def _doc_insert_fragment(self, line):
        """Insert a raw line as an inline fragment at the cursor / over selection.

        Strips trailing dot. Keeps leading capital only when the insertion point
        is at position 0 (start of line); lowercases otherwise. Selects the
        inserted text so the next Tab re-rolls it.
        """
        fragment = line.rstrip('.')

        ed = self.circular_view.editor
        current = ed.text()
        if ed.hasSelectedText():
            start = ed.selectionStart()
            sel_len = len(ed.selectedText())
        else:
            start = ed.cursorPosition()
            sel_len = 0

        if start > 0 and fragment and fragment[0].isupper():
            fragment = fragment[0].lower() + fragment[1:]

        new_text = current[:start] + fragment + current[start + sel_len:]
        ed.setText(new_text)
        ed.setSelection(start, len(fragment))
        self.line_ring.lines[self.line_ring.index] = new_text
        self.auto_save_circular()
        self.circular_view.update()

    def _doc_insert_random_i_line(self):
        """Tab on a content line: insert/replace with a random I/ fragment."""
        line = self._random_line_from_dir(self.book_dir,
                                          exclude_path=self.current_file_path)
        if not line:
            print("↩ No I/ lines to pull.")
            return
        self._doc_insert_fragment(line)

    def _random_line_from_ws(self):
        """Pick a random non-dot line from the F7 working set books."""
        if not getattr(self, '_ws_loaded', False):
            self._load_working_set()
        ws = getattr(self, '_ws_books', [])
        filled = [e for e in ws if e.get('path')]
        if not filled:
            return None
        random.shuffle(filled)
        for e in filled:
            fpath = os.path.join(self.o_dir, e['path'])
            try:
                with open(fpath, 'r', encoding='utf-8', errors='replace') as fh:
                    lines = [l.strip() for l in fh
                             if l.strip() and l.strip() != '.']
                if lines:
                    return random.choice(lines)
            except OSError:
                continue
        return None

    # ── Mandar desde F2 a otro capitulo ──────────────────────────────────────
    #
    # Esto no existia en el Python — solo en el mirror de Rust. El panel de
    # capitulos lo reusamos de F5 (_f5_pick_*): el filtrado, el orden de
    # biblioteca y el crear-si-no-existe ya estaban resueltos ahi y no dependen
    # de la vista. Los nombres siguen diciendo _f5_ porque ahi nacieron; el
    # picker es uno solo y nunca hay dos abiertos a la vez.

    def _doc_send_scope(self):
        """Que se manda, segun donde estes parado: (lineas, indices_a_sacar).

        Sobre una linea, esa linea. Sobre un punto, el parrafo entero que ese
        punto abre — y el punto se va con el, porque un separador sin parrafo no
        separa nada. Es la misma regla que Ctrl+C, Ctrl+Shift+E y el Ctrl+Delete
        de F6: el punto es el selector de alcance.
        """
        ring = self.line_ring
        n = len(ring.lines)
        if not n:
            return [], []
        idx = ring.index
        if ring.lines[idx] != '.':
            linea = ring.lines[idx]
            return ([linea], [idx]) if linea.strip() else ([], [])
        fin = idx + 1
        while fin < n and ring.lines[fin] != '.':
            fin += 1
        lineas = [ring.lines[i] for i in range(idx + 1, fin) if ring.lines[i].strip()]
        if not lineas:
            return [], []
        return lineas, list(range(idx, fin))

    def _doc_send_to(self, fname):
        """MOVER el alcance actual al capitulo `fname`. True si se hizo.

        Mover y no copiar, igual que en F5: el texto sale del archivo de origen.
        Se appendea al destino detras de un punto, para que no se pegue con lo
        que ya habia. Un snapshot de git y un solo paso de undo — se toca /void.

        Si el destino no se puede escribir, el origen NO se toca: primero que
        aterrice en algun lado, despues se suelta. Mismo criterio que el tacho.
        """
        lineas, quitar = self._doc_send_scope()
        if not lineas:
            return False
        destino = self._library_path_cache.get(fname)
        if not destino:
            print(f"⚠️ No sé dónde está {fname}")
            return False
        if os.path.abspath(destino) == os.path.abspath(self.current_file_path):
            return False                       # el mismo archivo: no tiene sentido

        try:
            with open(destino, 'r', encoding='utf-8', errors='replace') as f:
                existente = [l.rstrip('\n') for l in f]
        except FileNotFoundError:
            existente = []
        except Exception as e:
            print(f"⚠️ No se pudo leer {fname}: {e}")
            return False
        while existente and not existente[-1].strip():
            existente.pop()
        combinado = (existente + ['.'] + lineas) if existente else (['.'] + lineas)

        self._undo_begin()
        self._git_snapshot_void('f2-send')
        if not self._atomic_write_lines(destino, combinado):
            return False                       # no aterrizo: el origen queda intacto

        fuera = set(quitar)
        quedan = self._f5_collapse_dots(
            [l for i, l in enumerate(self.line_ring.lines) if i not in fuera])
        # _f5_collapse_dots tambien se come el punto de arriba, que aca es
        # estructural (mismo caso que en la cosecha de F6).
        if not quedan or quedan[0].strip() != '.':
            quedan.insert(0, '.')
        self.line_ring.lines = quedan
        if self.line_ring.index >= len(quedan):
            self.line_ring.index = max(0, len(quedan) - 1)
        self.auto_save_circular()
        self._undo_commit(key=('f2send', fname))
        print(f"→ {len(lineas)} línea(s) a {os.path.splitext(fname)[0]}")
        return True

    def _doc_alt_arrow(self, direction):
        """Alt+flecha en F2: depende de donde estes parado.

        Sobre un PUNTO abre el catalogo de capitulos para mandar el parrafo;
        sobre una LINEA mueve la palabra, que es lo que hizo siempre. La
        decision vive aca y no en el editor porque el editor no conoce el
        anillo — no sabe si abajo del cursor hay un punto o una linea.
        """
        if self.line_ring.current() == '.':
            self._doc_open_picker('left' if direction < 0 else 'right')
        else:
            self._swap_words(direction)

    def _doc_open_picker(self, side='right'):
        """Abrir el catalogo de capitulos en F2. `side` es de que lado sale."""
        lineas, _ = self._doc_send_scope()
        if not lineas:
            print("↩ No hay nada que mandar desde acá.")
            return
        # La biblioteca se carga al entrar a F3, y a F2 se puede llegar sin haber
        # pasado por ahi — entonces el catalogo saldria vacio. Se carga a pedido.
        if not self._library_lines and hasattr(self, '_load_library'):
            self._load_library()
        self._doc_picker_open = True
        self._doc_picker_side = side
        # El capitulo donde ya estas aparece en la lista, y el panel abre parado
        # ahi: asi cerrar sin querer no manda nada a ningun lado.
        self._pick_include_self = True
        self._f5_pick_filter = ''
        self._f5_pick_match_idx = self._f5_pick_start_idx()
        self._doc_refresh_picker()

    def _doc_close_picker(self):
        self._doc_picker_open = False
        # Se apaga al cerrar: si queda prendido, el panel de F5 hereda el activo
        # en su lista y alla no corresponde.
        self._pick_include_self = False
        self._doc_refresh_picker()

    def _doc_pick_confirm(self):
        """Enter en el panel: mandar al capitulo elegido, creandolo si el nombre
        que escribiste no existe todavia."""
        if not getattr(self, '_doc_picker_open', False):
            return
        target = self._f5_pick_target()
        if not target or not target['path']:
            return
        if target['is_new']:
            path = target['path']
            if not os.path.exists(path):
                open(path, 'w', encoding='utf-8').close()
            if target['fname'] not in self._library_lines:
                ins = self._f5_new_chapter_insert_idx()
                self._library_lines.insert(ins, target['fname'])
                self.book_ring.lines.insert(ins, target['display'])
                self._library_path_cache[target['fname']] = path
                self._save_library()
        self._doc_send_to(target['fname'])
        self._doc_close_picker()
        self._doc_refresh_editor()

    def _doc_refresh_picker(self):
        """Pasarle el estado del panel a la vista para que lo dibuje."""
        view = getattr(self, 'circular_view', None)
        if view is None or not hasattr(view, 'set_picker_state'):
            return
        abierto = getattr(self, '_doc_picker_open', False)
        objetivo = self._f5_pick_target() if abierto else None
        # Las filas que se dibujan NO son la lista de destinos: llevan los puntos
        # separadores, que se ven pero no se eligen. _pick_display traduce cual
        # queda resaltada.
        filas, idx = self._pick_display() if abierto else ([], 0)
        view.set_picker_state(
            abierto,
            getattr(self, '_f5_pick_filter', ''),
            filas,
            idx,
            bool(objetivo and objetivo.get('is_new')),
            (objetivo or {}).get('display', ''),
            getattr(self, '_doc_picker_side', 'right'),
        )
        view.update()

    def _doc_insert_ws_line(self):
        """Alt+Tab in F2: insert/replace with a random line from the working set."""
        line = self._random_line_from_ws()
        if not line:
            print("↩ No working set books to pull from.")
            return
        self._doc_insert_fragment(line)

    def _doc_navigate(self, delta):
        """Move doc ring and update F2 editor text.

        Caret defaults to the START of the destination line — EXCEPT when it sat
        at the END of the current line: then it lands at the end of the target
        line (Up or Down)."""
        self._tts_cut()
        ed = self.circular_view.editor
        at_end = ed.cursorPosition() == len(ed.text())
        self._save_last_line()
        if self._para_focus and self._para_focus_content:
            content = self._para_focus_content
            cur = self.line_ring.index
            pos = content.index(cur) if cur in content else 0
            self.line_ring.index = content[(pos + delta) % len(content)]
        else:
            self.line_ring.move(delta)
        self.circular_view._offset = 0.0
        self.circular_view.editor.setText(self._doc_editor_text())
        new_len = len(self.circular_view.editor.text())
        self.circular_view.editor.setCursorPosition(new_len if at_end else 0)
        self.circular_view.editor.setReadOnly(self.line_ring.current() == '.')
        self._apply_editor_style(self.circular_view.editor)
        self.circular_view.update()

    def _doc_jump_start(self):
        """Home in F2: jump to first non-dot content line."""
        self._tts_cut()
        self._save_last_line()
        ring = self.line_ring
        for i in range(len(ring.lines)):
            if ring.lines[i] != '.':
                ring.index = i
                break
        self.circular_view._offset = 0.0
        self.circular_view.editor.setText(self._doc_editor_text())
        self.circular_view.editor.setCursorPosition(0)
        self.circular_view.editor.setReadOnly(ring.current() == '.')
        self._apply_editor_style(self.circular_view.editor)
        self.circular_view.update()

    def _doc_jump_end(self):
        """End in F2: jump to last non-dot content line."""
        self._tts_cut()
        self._save_last_line()
        ring = self.line_ring
        for i in range(len(ring.lines) - 1, -1, -1):
            if ring.lines[i] != '.':
                ring.index = i
                break
        self.circular_view._offset = 0.0
        self.circular_view.editor.setText(self._doc_editor_text())
        new_len = len(self.circular_view.editor.text())
        self.circular_view.editor.setCursorPosition(new_len)
        self.circular_view.editor.setReadOnly(ring.current() == '.')
        self._apply_editor_style(self.circular_view.editor)
        self.circular_view.update()

    def _doc_join_prev(self):
        """Backspace at line start: join current line with previous (blocked by dots)."""
        ring = self.line_ring
        cur = ring.index
        n = len(ring.lines)
        if n < 2:
            return
        prev = (cur - 1) % n
        if ring.lines[prev] == '.':
            return  # never join across a paragraph boundary
        join_pos = len(ring.lines[prev])
        ring.lines[prev] = ring.lines[prev] + ring.lines[cur]
        ring.lines.pop(cur)
        ring.index = prev
        # Adjust para_focus indices
        if self._para_focus:
            self._para_focus_content = [
                i if i < cur else i - 1
                for i in self._para_focus_content
                if i != cur
            ]
            if self.circular_view:
                dot_idx = self._get_focus_dot_idx()
                self.circular_view.focus_indices = set(self._para_focus_content) | {dot_idx}
        self.auto_save_circular()
        self.circular_view._offset = 0.0
        self.circular_view.editor.setText(ring.current())
        self.circular_view.editor.setCursorPosition(join_pos)
        self.circular_view.editor.setReadOnly(False)
        self.circular_view.update()

    def _doc_join_next(self):
        """Delete at line end: join current line with next (blocked by dots)."""
        ring = self.line_ring
        cur = ring.index
        n = len(ring.lines)
        if n < 2:
            return
        nxt = (cur + 1) % n
        if ring.lines[nxt] == '.':
            return  # never join across a paragraph boundary
        join_pos = len(ring.lines[cur])
        ring.lines[cur] = ring.lines[cur] + ring.lines[nxt]
        ring.lines.pop(nxt)
        # Adjust para_focus indices
        if self._para_focus:
            self._para_focus_content = [
                i if i < nxt else i - 1
                for i in self._para_focus_content
                if i != nxt
            ]
            if self.circular_view:
                dot_idx = self._get_focus_dot_idx()
                self.circular_view.focus_indices = set(self._para_focus_content) | {dot_idx}
        self.auto_save_circular()
        self.circular_view._offset = 0.0
        self.circular_view.editor.setText(ring.current())
        self.circular_view.editor.setCursorPosition(join_pos)
        self.circular_view.editor.setReadOnly(False)
        self.circular_view.update()

    def _doc_split_line(self, pos):
        """Split current line at cursor pos into two lines."""
        ring = self.line_ring
        cur = ring.index
        text = ring.lines[cur]
        before, after = text[:pos], text[pos:]
        ring.lines[cur] = before
        ring.lines.insert(cur + 1, after)
        ring.index = cur + 1
        # Adjust para_focus indices
        if self._para_focus:
            self._para_focus_content = [
                i if i <= cur else i + 1
                for i in self._para_focus_content
            ]
            # Insert new line right after cur in focus
            if cur in self._para_focus_content:
                ins = self._para_focus_content.index(cur) + 1
                self._para_focus_content.insert(ins, cur + 1)
            if self.circular_view:
                dot_idx = self._get_focus_dot_idx()
                self.circular_view.focus_indices = set(self._para_focus_content) | {dot_idx}
        self.auto_save_circular()
        self.circular_view._offset = 0.0
        self.circular_view.editor.setText(ring.current())
        self.circular_view.editor.setCursorPosition(0)
        self.circular_view.editor.setReadOnly(False)
        self.circular_view.update()

    def _doc_live_save(self, text):
        """Save on every keystroke in F2 editor."""
        if text.strip():
            self.line_ring.lines[self.line_ring.index] = text
            # Coalesce the keystroke burst on this line into one undo step.
            self.auto_save_circular(undo_key=('doc', self.line_ring.index))
            self.circular_view.update()

    def _doc_confirm_edit(self):
        """Enter (cursor at start) in F2: dot → paragraph focus; empty line → drop
        into F1 focus writing here; non-empty → split the line at the start (Enter
        keeps breaking the line, just like a split mid-text)."""
        cur = self.line_ring.current()
        if cur == '.' and not self._para_focus:
            self._enter_para_focus()
            return
        if self._para_focus:
            self._exit_para_focus()
        if cur.strip() == '':
            self.switch_to_view(0)   # F1 mirrors this empty line; write here
        else:
            self._doc_split_line(0)

    def _doc_duplicate(self, direction):
        """Alt+Shift+↑/↓ en F2: duplicar y colocar la copia en la dirección de
        la flecha. Arriba (-1) la copia queda ANTES del original; abajo (+1),
        DESPUÉS. El cursor sigue a la copia — es el bloque que acaba de
        aparecer del lado al que apuntaste.

        El alcance es el de siempre: sobre una línea, esa línea; sobre un
        punto, el párrafo entero que ese punto abre (con su propio punto —
        la copia también es un párrafo completo, no contenido suelto).
        """
        ring = self.line_ring
        n = len(ring.lines)
        if not n:
            return
        idx = ring.index
        if ring.lines[idx] == '.':
            fin = idx + 1
            while fin < n and ring.lines[fin] != '.':
                fin += 1
            start, end = idx, fin
        else:
            start, end = idx, idx + 1
        bloque = list(ring.lines[start:end])
        insert_at = start if direction < 0 else end

        # El foco de párrafo (Enter sobre un punto) nunca coincide con estar
        # PARADO en un punto — ahí el cursor nunca está sobre un punto — así
        # que esto sólo puede pasar en el caso de una línea sola (end-start==1).
        if self._para_focus and end - start == 1:
            k = len(bloque)
            orig_new_idx = idx if insert_at > idx else idx + k
            shifted = [i if i < insert_at else i + k for i in self._para_focus_content]
            if orig_new_idx in shifted:
                pos = shifted.index(orig_new_idx)
                shifted.insert(pos if direction < 0 else pos + 1, insert_at)
            self._para_focus_content = shifted
            if self.circular_view:
                dot_idx = self._get_focus_dot_idx()
                self.circular_view.focus_indices = set(self._para_focus_content) | {dot_idx}

        ring.lines[insert_at:insert_at] = bloque
        ring.index = insert_at
        self.auto_save_circular()
        if self.circular_view:
            self.circular_view._offset = 0.0
            self.circular_view.editor.setText(self._doc_editor_text())
            self.circular_view.editor.setCursorPosition(0)
            self.circular_view.editor.setReadOnly(ring.current() == '.')
            self._apply_editor_style(self.circular_view.editor)
            self.circular_view.update()
        print(f"⧉ {len(bloque)} línea(s) duplicada(s) {'arriba' if direction < 0 else 'abajo'}")

    def _split_line_on_spaces(self):
        """Ctrl+Shift+E en F2: partirle los espacios a la línea donde estoy —
        o, parado en un punto, a todas las líneas de ese párrafo.

        Devuelve los saltos de línea que se perdieron al escribir en scriptio
        continua: el espacio vuelve a ser el salto que era. No agrega
        puntuación — eso quedó del lado de F9 (ver split_on_spaces).

        Los puntos separadores del dot-model no se tocan nunca — son la
        estructura.
        """
        ring = self.line_ring
        lines = ring.lines
        n = len(lines)
        if not n:
            return
        idx = ring.index

        if lines[idx] == '.':
            # El párrafo que abre este punto. El punto mismo queda afuera.
            targets = []
            i = (idx + 1) % n
            for _ in range(n - 1):
                if lines[i] == '.':
                    break
                targets.append(i)
                i = (i + 1) % n
        else:
            targets = [idx]
        if not targets:
            return

        # Si no cambia nada, no se escribe un paso de undo vacío ni un .bak que
        # pisaría uno bueno. "Cambiar" incluye sólo agregarle el punto a una
        # línea que ya está sola: es lo que la hace sobrevivir a F9.
        if all(split_on_spaces(lines[i]) == [lines[i]] for i in targets):
            print("↩ Nada que partir ni que puntuar.")
            return

        if self._para_focus:
            self._exit_para_focus()

        first = targets[0]
        tset = set(targets)
        new_lines, new_index = [], 0
        for i, line in enumerate(lines):
            if i == first:
                new_index = len(new_lines)
            if i in tset:
                pieces = split_on_spaces(line)
                new_lines.extend(pieces if pieces else [line])
            else:
                new_lines.append(line)

        self._undo_begin()
        if not self._atomic_write_lines(self.current_file_path, new_lines, backup=True):
            return
        ring.lines = new_lines
        ring.index = new_index
        self._undo_commit(key=('split_spaces', self.current_file_path))
        if self.circular_view:
            self.circular_view._offset = 0.0
            self.circular_view.editor.setText(ring.current())
            self.circular_view.editor.setCursorPosition(0)
            self.circular_view.update()
        print(f"↵ {len(targets)} línea(s) → {len(new_lines) - (n - len(targets))} líneas")

    def _enter_para_focus(self):
        ring = self.line_ring
        n = len(ring.lines)
        dot_idx = ring.index
        content = []
        i = (dot_idx + 1) % n
        for _ in range(n - 1):
            if ring.lines[i] == '.':
                break
            content.append(i)
            i = (i + 1) % n
        if not content:
            return
        self._para_focus = True
        self._para_focus_content = content
        self.circular_view.focus_indices = set(content) | {dot_idx}
        ring.index = content[0]
        self.circular_view._offset = 0.0
        self.circular_view.editor.setText(ring.current())
        self.circular_view.editor.setCursorPosition(0)
        self.circular_view.editor.setReadOnly(False)
        self.circular_view.update()

    def _exit_para_focus(self):
        self._para_focus = False
        self._para_focus_content = []
        self.circular_view.focus_indices = None
        # Return to the dot that precedes this paragraph
        ring = self.line_ring
        n = len(ring.lines)
        idx = (ring.index - 1) % n
        for _ in range(n):
            if ring.lines[idx] == '.':
                ring.index = idx
                break
            idx = (idx - 1) % n
        self._doc_show_editor()

    def _get_focus_dot_idx(self):
        """Return the ring index of the dot preceding the focused paragraph."""
        ring = self.line_ring
        n = len(ring.lines)
        if not self._para_focus_content:
            return 0
        idx = (self._para_focus_content[0] - 1) % n
        for _ in range(n):
            if ring.lines[idx] == '.':
                return idx
            idx = (idx - 1) % n
        return 0

    def _delete_line_to_trash(self):
        """Ctrl+Delete / Ctrl+Backspace en F2 — el tacho, que va y vuelve:

            cualquier archivo (0.txt incluido)  → trash.txt
            trash.txt                           → 0.txt

        Antes esto era una cascada de tres niveles que terminaba en borrado
        permanente. Ya no: ningún camino termina en la nada. Una línea siempre
        queda escrita en algún lado, y desde la basura vuelve al scratch.
        """
        lines = self.line_ring.lines
        n = len(lines)
        cur = self.line_ring.index
        if n <= 1:
            return
        line = lines[cur]
        new_lines = [l for i, l in enumerate(lines) if i != cur]
        new_index = min(cur, len(new_lines) - 1)

        trash_file = getattr(self, '_trash_file',
                             os.path.join(self.void_dir, 'I', 'trash.txt'))
        on_trash = os.path.abspath(self.current_file_path) == os.path.abspath(trash_file)

        dest, arrow = (self.f1_file, '♻️ → 0.txt') if on_trash else (trash_file, '🗑️ → trash.txt')
        try:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, 'a', encoding='utf-8') as f:
                f.write(line + '\n')
            print(f"{arrow}: {line[:60]}")
        except Exception as e:
            print(f"❌ {os.path.basename(dest)}: {e}")
            return   # si no se pudo escribir el destino, la línea NO se saca de acá

        self.line_ring.lines = new_lines
        self.line_ring.index = new_index
        self.auto_save_circular()
        self.circular_view._offset = 0.0
        self.circular_view.editor.setText(self.line_ring.current())
        self.circular_view.editor.setCursorPosition(0)
        self.circular_view.update()

    def _find_move_target(self, start, delta):
        """Find nearest non-dot index in direction delta (wrapping).
        Returns (index, wrapped) where wrapped=True means the boundary was crossed."""
        n = len(self.line_ring.lines)
        idx = (start + delta) % n
        for _ in range(n - 1):
            if self.line_ring.lines[idx] != '.':
                wrapped = (delta == -1 and idx > start) or (delta == 1 and idx < start)
                return idx, wrapped
            idx = (idx + delta) % n
        return None, False

    def _swap_line_in_focus(self, delta):
        """Swap line within para focus content, wrapping circularly inside the paragraph."""
        content = self._para_focus_content
        if not content:
            return
        lines = self.line_ring.lines
        cur = self.line_ring.index
        pos = content.index(cur) if cur in content else 0
        other_pos = (pos + delta) % len(content)
        other = content[other_pos]
        lines[cur], lines[other] = lines[other], lines[cur]
        # Update focus_content indices to follow swapped positions
        self._para_focus_content[pos], self._para_focus_content[other_pos] = \
            self._para_focus_content[other_pos], self._para_focus_content[pos]
        self.line_ring.index = other
        self.auto_save_circular()
        self.circular_view._offset = 0.0
        self.circular_view.editor.setText(self.line_ring.current())
        self.circular_view.editor.setCursorPosition(0)
        self.circular_view.update()

    def swap_line_up(self):
        if len(self.line_ring.lines) < 2:
            return
        if self._para_focus:
            self._swap_line_in_focus(-1)
            return
        lines = self.line_ring.lines
        cur = self.line_ring.index
        n = len(lines)
        prev = (cur - 1) % n
        lines[cur], lines[prev] = lines[prev], lines[cur]
        self.line_ring.index = prev
        self.auto_save_circular()
        self.circular_view._offset = 0.0
        self.circular_view.editor.setText(self.line_ring.current())
        self.circular_view.editor.setCursorPosition(0)
        self.circular_view.update()

    def swap_line_down(self):
        if len(self.line_ring.lines) < 2:
            return
        if self._para_focus:
            self._swap_line_in_focus(+1)
            return
        lines = self.line_ring.lines
        cur = self.line_ring.index
        n = len(lines)
        nxt = (cur + 1) % n
        lines[cur], lines[nxt] = lines[nxt], lines[cur]
        self.line_ring.index = nxt
        self.auto_save_circular()
        self.circular_view._offset = 0.0
        self.circular_view.editor.setText(self.line_ring.current())
        self.circular_view.editor.setCursorPosition(0)
        self.circular_view.update()

    # ── Paragraph helpers ─────────────────────────────────────────────────────
    # Model: each '.' is a paragraph separator. _paragraphs_from_ring extracts
    # paragraph content arrays (no dots). _rebuild_ring_from_paragraphs puts them
    # back, always emitting a dot before each paragraph. This makes circular
    # paragraph operations (including wrapping first↔last) natural.

    def _paragraphs_from_ring(self):
        """Return (dot_indices, paragraphs) where paragraphs[k] is the list of
        content lines between dot_indices[k] and the next dot (or end)."""
        lines = self.line_ring.lines
        dot_indices = [i for i, l in enumerate(lines) if l == '.']
        if not dot_indices:
            return [], [list(lines)]
        paragraphs = []
        for k, d in enumerate(dot_indices):
            next_d = dot_indices[k + 1] if k + 1 < len(dot_indices) else len(lines)
            paragraphs.append(list(lines[d + 1:next_d]))
        return dot_indices, paragraphs

    def _rebuild_ring_from_paragraphs(self, paragraphs):
        """Rebuild ring.lines from paragraph content arrays, inserting a dot before each."""
        new_lines = []
        for para in paragraphs:
            new_lines.append('.')
            new_lines.extend(para)
        if not new_lines:
            new_lines = ['.']
        self.line_ring.lines = new_lines
        # Keep the cursor in range — LineRing.current() indexes without modulo,
        # so an index left past the new (shorter) list would raise IndexError.
        if self.line_ring.index >= len(new_lines):
            self.line_ring.index = len(new_lines) - 1
        if self.line_ring.index < 0:
            self.line_ring.index = 0

    def _dot_line_index(self, para_idx, paragraphs):
        """Return the line index of the dot that precedes paragraphs[para_idx]."""
        return sum(1 + len(paragraphs[j]) for j in range(para_idx))

    def goto_prev_dot(self):
        ring = self.line_ring
        n = len(ring.lines)
        if n == 0:
            return
        idx = (ring.index - 1) % n
        for _ in range(n):
            if ring.lines[idx] == '.':
                ring.index = idx
                return
            idx = (idx - 1) % n

    def goto_next_dot(self):
        ring = self.line_ring
        n = len(ring.lines)
        if n == 0:
            return
        idx = (ring.index + 1) % n
        for _ in range(n):
            if ring.lines[idx] == '.':
                ring.index = idx
                return
            idx = (idx + 1) % n

    def _move_paragraph(self, k, paragraphs, direction):
        """Move paragraph k up (-1) or down (+1). At boundaries: move, not swap."""
        n = len(paragraphs)
        if n <= 1:
            return
        other_k = k + direction
        wrapped = other_k < 0 or other_k >= n
        if not wrapped:
            # Normal: swap adjacent paragraphs
            paragraphs[k], paragraphs[other_k] = paragraphs[other_k], paragraphs[k]
            dest = other_k
        else:
            # Boundary: remove and insert at the other end
            para = paragraphs.pop(k)
            if direction == -1:
                paragraphs.append(para)   # first → becomes last
                dest = len(paragraphs) - 1
            else:
                paragraphs.insert(0, para)  # last → becomes first
                dest = 0
        self._rebuild_ring_from_paragraphs(paragraphs)
        self.line_ring.index = self._dot_line_index(dest, paragraphs)
        self.auto_save_circular()
        self.circular_view._offset = 0.0
        self.circular_view.editor.setText(self.line_ring.current())
        self.circular_view.editor.setCursorPosition(0)
        self.circular_view.update()

    def _current_para_idx(self):
        """Return the paragraph index (k) whose dot is at ring.index, or None."""
        _, paragraphs = self._paragraphs_from_ring()
        for k in range(len(paragraphs)):
            if self._dot_line_index(k, paragraphs) == self.line_ring.index:
                return k, paragraphs
        return None, None

    def swap_paragraph_up(self):
        if not self.line_ring.lines or self.line_ring.current() != '.':
            return
        k, paragraphs = self._current_para_idx()
        if k is None:
            return
        self._move_paragraph(k, paragraphs, -1)

    def swap_paragraph_down(self):
        if not self.line_ring.lines or self.line_ring.current() != '.':
            return
        k, paragraphs = self._current_para_idx()
        if k is None:
            return
        self._move_paragraph(k, paragraphs, +1)

    def rebase_to_index_zero(self):
        """Ctrl+0 in F2: make current line/paragraph the first in the ring."""
        if self.current_view != 1:
            return
        ring = self.line_ring
        _, paragraphs = self._paragraphs_from_ring()

        if ring.current() == '.':
            # Standing on a dot: rotate paragraphs so this one becomes first
            dot_indices, _ = self._paragraphs_from_ring()
            para_idx = dot_indices.index(ring.index) if ring.index in dot_indices else 0
            if para_idx == 0:
                return
            paragraphs = paragraphs[para_idx:] + paragraphs[:para_idx]
            self._rebuild_ring_from_paragraphs(paragraphs)
            ring.index = 0
        else:
            # Standing on a text line: rotate within its paragraph
            for k, para in enumerate(paragraphs):
                dot_pos = self._dot_line_index(k, paragraphs)
                next_dot = dot_pos + 1 + len(para)
                if dot_pos < ring.index < next_dot:
                    offset = ring.index - dot_pos - 1
                    paragraphs[k] = para[offset:] + para[:offset]
                    self._rebuild_ring_from_paragraphs(paragraphs)
                    ring.index = self._dot_line_index(k, paragraphs) + 1
                    break

        self.auto_save_circular()
        self.circular_view._offset = 0.0
        # Use _doc_editor_text() (not the raw '.') so the new index-0 line shows
        # the ø glyph immediately, and match the normal read-only/white styling.
        self.circular_view.editor.setText(self._doc_editor_text())
        self.circular_view.editor.setCursorPosition(0)
        self.circular_view.editor.setReadOnly(ring.current() == '.')
        self._apply_editor_style(self.circular_view.editor)
        self.circular_view.update()
        print(f"🔁 Rebase | '{ring.current()[:50]}'")

    def _swap_words(self, direction, editor=None, ring=None, save=None):
        """Alt+Left/Right: swap word(s) at cursor or selection within the current line.
        Trailing sentence-ending punctuation (.!?…) stays fixed at the end.
        direction: -1=left, +1=right. Wraps circularly.

        Los tres ultimos parametros son opcionales y por defecto son los de F2,
        asi que las llamadas de siempre se comportan exactamente igual. Existen
        para que F6 pueda usar ESTA implementacion en vez de una copia: son 80
        lineas de logica delicada, y duplicarlas significa arreglar un bug en un
        lado y no en el otro.
        """
        editor = editor if editor is not None else self.circular_view.editor
        ring = ring if ring is not None else self.line_ring
        save = save if save is not None else self.auto_save_circular
        text = editor.text()
        if not text.strip():
            return

        # Separate trailing sentence-ending punctuation
        trailing = ''
        core = text
        if text and text[-1] in '.!?…':
            j = len(text) - 1
            while j >= 0 and text[j] in '.!?…':
                j -= 1
            candidate_core = text[:j + 1]
            if candidate_core.strip():
                core = candidate_core
                trailing = text[j + 1:]

        # Split into tokens (split on spaces, drop empties)
        tokens = core.split()
        if len(tokens) < 2:
            return

        # Build span positions for each token in `core`
        spans = []
        search_from = 0
        for tok in tokens:
            idx = core.find(tok, search_from)
            spans.append((idx, idx + len(tok)))
            search_from = idx + len(tok)

        # Determine which token(s) form the "block" to move
        if editor.hasSelectedText():
            sel_start = editor.selectionStart()
            sel_end = sel_start + len(editor.selectedText())
            # Overlap, not full containment: a selection made by shift-arrow
            # or double-click-drag stops right after the last letter of a
            # word, never reaching punctuation glued to it with no space
            # (e.g. "palabra,"). That comma is part of the SAME token
            # (core.split() only splits on whitespace), so requiring the
            # token's span to fit entirely inside the selection silently
            # dropped it from the block — it stayed behind while the rest
            # of the phrase moved.
            block_indices = [i for i, (s, e) in enumerate(spans)
                             if s < sel_end and e > sel_start]
        else:
            cur = editor.cursorPosition()
            block_indices = [i for i, (s, e) in enumerate(spans) if s <= cur <= e]
            if not block_indices:
                # cursor between tokens: pick nearest
                block_indices = [min(range(len(spans)),
                                     key=lambda i: min(abs(cur - spans[i][0]),
                                                       abs(cur - spans[i][1])))]

        if not block_indices:
            return

        b0, b1 = block_indices[0], block_indices[-1]
        n = len(tokens)
        block = tokens[b0:b1 + 1]

        if direction == -1:  # swap left
            if b0 == 0:
                # wrap: block moves to end
                rest = tokens[b1 + 1:]
                new_tokens = rest + block
                new_b0 = len(rest)
            else:
                new_tokens = tokens[:b0 - 1] + block + [tokens[b0 - 1]] + tokens[b1 + 1:]
                new_b0 = b0 - 1
        else:  # swap right
            if b1 == n - 1:
                # wrap: block moves to start
                rest = tokens[:b0]
                new_tokens = block + rest
                new_b0 = 0
            else:
                new_tokens = tokens[:b0] + [tokens[b1 + 1]] + block + tokens[b1 + 2:]
                new_b0 = b0 + 1

        new_text = ' '.join(new_tokens) + trailing
        had_selection = editor.hasSelectedText()
        editor.setText(new_text)

        # Place cursor at start of moved block; restore selection if there was one
        new_b1 = new_b0 + (b1 - b0)
        sel_start = sum(len(new_tokens[i]) + 1 for i in range(new_b0))
        sel_end = sum(len(new_tokens[i]) + 1 for i in range(new_b1 + 1)) - 1
        if had_selection:
            editor.setSelection(sel_start, sel_end - sel_start)
        else:
            editor.setCursorPosition(sel_start)

        ring.lines[ring.index] = new_text
        save()
        # getattr: llamado desde F6 no hay vista de F2 que refrescar.
        vista = getattr(self, 'circular_view', None)
        if vista is not None:
            vista.update()

    def _f2_search_show_center(self):
        """Highlight center of display ring; surroundings dimmed. Search bar keeps focus."""
        if not self._f2_display_ring or not self.circular_view:
            return
        view = self.circular_view
        view.edit_mode = False
        view.editor.hide()
        view.search_highlight_center = True
        view.update()
        self._f2_search_bar.setFocus()

    def _open_f2_search(self):
        if self._f2_search_active:
            return
        self._f2_search_active = True
        self._f2_search_saved = self.line_ring.index
        display = [l for l in self.line_ring.lines if l != '.'] or ['.']
        self._f2_display_ring = LineRing(display)
        # Start at the line currently shown in F2
        cur = self.line_ring.current()
        if cur and cur != '.' and cur in display:
            self._f2_display_ring.index = display.index(cur)
        self.circular_view.search_mode = True
        self.circular_view.ring = self._f2_display_ring
        self.circular_view._offset = 0.0
        self._f2_search_bar.clear()
        self._f2_search_bar.show()
        self._f2_search_bar.raise_()
        self._f2_search_show_center()

    def _close_f2_search(self, restore=True):
        if not self._f2_search_active:
            return
        self._f2_search_active = False
        self._f2_search_bar.hide()
        self._f2_display_ring = None
        if restore and self._f2_search_saved is not None:
            self.line_ring.index = self._f2_search_saved
        self.circular_view.search_mode = False
        self.circular_view.search_highlight_center = False
        self.circular_view.ring = self.line_ring
        self._f2_search_saved = None
        self.circular_view._offset = 0.0
        self.circular_view.update()
        self._doc_show_editor()

    def _f2_search_changed(self, text):
        if not self._f2_search_active:
            return
        q = text.strip().lower()
        if not q:
            filtered = [l for l in self.line_ring.lines if l != '.'] or ['.']
        else:
            filtered = [l for l in self.line_ring.lines if l != '.' and q in l.lower()] or ['.']
        self._f2_display_ring = LineRing(filtered)
        self.circular_view.ring = self._f2_display_ring
        self.circular_view._offset = 0.0
        self._f2_search_show_center()

    def _f2_search_confirm(self):
        """Enter: jump to the highlighted match in the full ring and close search."""
        if not self._f2_search_active:
            return
        matched = self._f2_display_ring.current() if self._f2_display_ring else None
        self._f2_search_active = False
        self._f2_search_bar.hide()
        self._f2_display_ring = None
        self._f2_search_saved = None
        if matched and matched != '.' and matched in self.line_ring.lines:
            self.line_ring.index = self.line_ring.lines.index(matched)
        self.circular_view.search_mode = False
        self.circular_view.search_highlight_center = False
        self.circular_view.ring = self.line_ring
        self.circular_view._offset = 0.0
        self.circular_view.update()
        self._doc_show_editor()

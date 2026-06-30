# f2_mixin.py — F2 doc editor methods
import os
import random

from PyQt6.QtCore import Qt

from line_ring import LineRing


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
                            try:
                                with open(fp, 'r', encoding='utf-8', errors='replace') as f:
                                    parts.append(f.read().rstrip('\n'))
                            except Exception as e:
                                print(f"⚠️ Copy error: {e}")
                    i = (i + 1) % n
                text = '\n.\n'.join(parts) if parts else None
            else:
                fname = self._library_current_fname()
                if fname:
                    fpath = self._library_path_cache.get(fname)
                    if fpath and os.path.isfile(fpath):
                        try:
                            with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                                text = f.read().rstrip('\n')
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

    def _delete_line_to_zero(self):
        """Ctrl+Delete / Ctrl+Backspace in F2 — three-level cascade:
        other file → 0.txt;  0.txt → trash.txt;  trash.txt → permanent."""
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
        on_scratch = os.path.abspath(self.current_file_path) == os.path.abspath(self.f1_file)
        on_trash   = os.path.abspath(self.current_file_path) == os.path.abspath(trash_file)

        if on_trash:
            print(f"🗑️ Deleted permanently: {line[:60]}")
        elif on_scratch:
            try:
                os.makedirs(os.path.dirname(trash_file), exist_ok=True)
                with open(trash_file, 'a', encoding='utf-8') as f:
                    f.write(line + '\n')
                print(f"🗑️ → trash.txt: {line[:60]}")
            except Exception as e:
                print(f"❌ Delete to trash error: {e}")
                return
        else:
            try:
                with open(self.f1_file, 'a', encoding='utf-8') as f:
                    f.write(line + '\n')
                print(f"♻️ → 0.txt: {line[:60]}")
            except Exception as e:
                print(f"❌ Delete to 0.txt error: {e}")
                return

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

    def _swap_words(self, direction):
        """Alt+Left/Right: swap word(s) at cursor or selection within the current line.
        Trailing sentence-ending punctuation (.!?…) stays fixed at the end.
        direction: -1=left, +1=right. Wraps circularly."""
        editor = self.circular_view.editor
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
            block_indices = [i for i, (s, e) in enumerate(spans)
                             if s >= sel_start and e <= sel_end]
            if not block_indices:
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

        self.line_ring.lines[self.line_ring.index] = new_text
        self.auto_save_circular()
        self.circular_view.update()

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

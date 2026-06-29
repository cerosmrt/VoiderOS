# f1_mixin.py — F1 normal view + scratch mode methods
from PyQt6.QtCore import Qt

from circular_view import CircularView


class F1Mixin:

    # ── F1 focus writing on the active file ─────────────────────────────────────

    def _f1_commit_line(self, text):
        """F1 Enter: write `text` into the current line of the ACTIVE file, then
        open a blank line just below and move to it (build forward). A '.'
        separator is preserved — text is inserted after it, never over it. Empty
        input is a no-op. Persists atomically via auto_save_circular."""
        t = text.strip()
        if not t:
            return
        ring = self.line_ring
        if not ring.lines:
            ring.lines = ['']
        ring.index = max(0, min(ring.index, len(ring.lines) - 1))
        if ring.lines[ring.index] == '.':
            ring.lines.insert(ring.index + 1, t)
            ring.index += 1
        else:
            ring.lines[ring.index] = t
        ring.lines.insert(ring.index + 1, '')
        ring.index += 1
        self.auto_save_circular()

    def _f1_show_current(self):
        """Mirror the current line into the F1 entry (blank for a '.' separator),
        cursor at the start (F2-standard position)."""
        cur = self.line_ring.current() if self.line_ring.lines else ''
        self.entry.setText('' if cur == '.' else cur)
        self.entry.setCursorPosition(0)
        self.current_active_line_index = self.line_ring.index

    def _f1_scratch_jump(self):
        """/0 in F1: move the single '0' scratch portal directly above the current
        chapter and switch the active file to 0.txt. Consolidates to one portal so
        scratch is always one step from where you were. No-op if already on 0.txt."""
        import os
        cur_fname = os.path.basename(self.current_file_path)
        if cur_fname == '0.txt':
            return
        # Drop every existing '0' portal (keep parallel arrays aligned).
        kept_lines, kept_ring = [], []
        for fn, disp in zip(self._library_lines, self.book_ring.lines):
            if fn == '0.txt':
                continue
            kept_lines.append(fn)
            kept_ring.append(disp)
        self._library_lines = kept_lines
        self.book_ring.lines = kept_ring
        # Insert one portal just above the current chapter.
        try:
            i = self._library_lines.index(cur_fname)
        except ValueError:
            i = min(self.book_ring.index, len(self._library_lines))
        self._library_lines.insert(i, '0.txt')
        self.book_ring.lines.insert(i, '0')
        self.book_ring.index = i
        self._save_library()
        # Switch to the scratch and mirror its current line into the entry.
        self.current_file_path = self.f1_file
        self.load_doc_lines()
        self._f1_show_current()

    def _f1_persist_entry(self):
        """Before navigating away from a line in F1, save the entry into it
        (matches F2 live-save: only non-empty text, never overwrites a '.')."""
        t = self.entry.text().strip()
        ring = self.line_ring
        if not ring.lines or not (0 <= ring.index < len(ring.lines)):
            return
        if ring.lines[ring.index] == '.':
            return
        if t and t != ring.lines[ring.index]:
            ring.lines[ring.index] = t
            self.auto_save_circular()

    def _f5_fork(self):
        text = self.entry.text().strip()
        if not text:
            return
        insert_pos = self.line_ring.index + 1
        self.line_ring.lines.insert(insert_pos, text)
        self.line_ring.index = insert_pos
        self.auto_save_circular()
        self.o_reader_ring.move(1)
        while self.o_reader_ring.current() in ('.', ''):
            self.o_reader_ring.move(1)
        self.entry.setText(self.o_reader_ring.current())
        self.entry.setCursorPosition(len(self.entry.text()))
        print(f"✅ F5 fork→I/[{insert_pos}]: '{text}'")

    def _f5_navigate(self, delta):
        self.o_reader_ring.move(delta)
        while self.o_reader_ring.current() in ('.', ''):
            self.o_reader_ring.move(delta)
        self.entry.setText(self.o_reader_ring.current())
        self.entry.setCursorPosition(len(self.entry.text()))

    def toggle_void_key_mode(self):
        from app_config import _save_config
        self.use_spacebar_for_void = not self.use_spacebar_for_void
        self.config['void_key'] = 'space' if self.use_spacebar_for_void else 'enter'
        _save_config(self.config)
        self._print_void_mode_status()
        self._connect_void_key()

    def _f1_tab_toggle(self):
        """Tab in F1: toggle between write entry and 0.txt scratch circular view."""
        if self.current_view != 0:
            return
        if not self._f1_scratch_mode:
            self._enter_f1_scratch()
        else:
            self._exit_f1_scratch()

    def _enter_f1_scratch(self):
        self._f1_scratch_mode = True
        if not self.scratch_view:
            self.scratch_view = CircularView(self.line_ring, self)
            self.scratch_view.zero_marker = True
            self.scratch_view.setFont(self._app_font)
            self.scratch_view.editor.returnPressed.disconnect()
            self.scratch_view.editor.returnPressed.connect(self._scratch_enter)
            self.scratch_view.editor.textEdited.connect(self._scratch_live_save)
            self.scratch_view.editor.upPressed.connect(lambda: self._scratch_navigate(-1))
            self.scratch_view.editor.downPressed.connect(lambda: self._scratch_navigate(1))
            self.scratch_view.editor.deleteLineToZero.connect(self._scratch_delete_line)
            self.scratch_view.editor.tabPressed.connect(self._f1_tab_toggle)
            self.stack.addWidget(self.scratch_view)
        else:
            self.scratch_view.ring = self.line_ring
            self.scratch_view._offset = 0.0
        self.stack.setCurrentWidget(self.scratch_view)
        self.entry.hide()
        self.scratch_view.update()
        self._scratch_show_editor()

    def _exit_f1_scratch(self, fork_line=None):
        self._f1_scratch_mode = False
        if self.scratch_view:
            self.scratch_view.edit_mode = False
            self.scratch_view.editor.hide()
        self.stack.setCurrentWidget(self.normal_view)
        self.entry.show()
        self.entry.raise_()
        if fork_line:
            self.entry.setText(fork_line)
            self.entry.selectAll()
        else:
            self.entry.clear()
        self.entry.setFocus()

    def _scratch_show_editor(self):
        view = self.scratch_view
        view.edit_mode = True
        center_y = view.height() // 2
        editor_width = view.width() - 100
        view.editor.setFixedWidth(editor_width)
        view.editor.move(
            (view.width() - editor_width) // 2,
            center_y - view.editor.sizeHint().height() // 2
        )
        view.editor.setText(self.line_ring.current())
        view.editor.setCursorPosition(0)
        is_zero_dot = view.zero_marker and self.line_ring.index == 0
        self._apply_editor_style(view.editor, red=is_zero_dot)
        view.editor.setReadOnly(self.line_ring.current() == '.')
        view.editor.show()
        view.editor.setFocus()
        view.update()

    def _scratch_navigate(self, delta):
        self._tts_cut()
        self._save_last_line()
        self.line_ring.move(delta)
        self.scratch_view._offset = 0.0
        self.scratch_view.editor.setText(self.line_ring.current())
        self.scratch_view.editor.setCursorPosition(0)
        is_zero_dot = self.scratch_view.zero_marker and self.line_ring.index == 0
        self._apply_editor_style(self.scratch_view.editor, red=is_zero_dot)
        self.scratch_view.editor.setReadOnly(self.line_ring.current() == '.')
        self.scratch_view.update()

    def _scratch_live_save(self, text):
        if text.strip():
            self.line_ring.lines[self.line_ring.index] = text
            self.auto_save_circular()
            self.scratch_view.update()

    def _scratch_enter(self):
        """Enter in F1 scratch: fork current line to entry and return to write mode."""
        cur = self.line_ring.current()
        fork_line = cur if cur and cur != '.' else None
        self._exit_f1_scratch(fork_line=fork_line)

    def _scratch_delete_line(self):
        """Ctrl+Delete in F1 scratch: permanently delete (already in 0.txt)."""
        lines = self.line_ring.lines
        n = len(lines)
        cur = self.line_ring.index
        if n <= 1:
            return
        line = lines[cur]
        new_lines = [l for i, l in enumerate(lines) if i != cur]
        new_index = min(cur, len(new_lines) - 1)
        self.line_ring.lines = new_lines
        self.line_ring.index = new_index
        self.auto_save_circular()
        self.scratch_view._offset = 0.0
        self.scratch_view.editor.setText(self.line_ring.current())
        self.scratch_view.editor.setCursorPosition(0)
        self.scratch_view.update()
        print(f"🗑️ Scratch deleted: {line[:60]}")

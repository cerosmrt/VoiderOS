# f1_mixin.py — F1 normal view + scratch mode methods
from PyQt6.QtCore import Qt

from circular_view import CircularView


class F1Mixin:

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

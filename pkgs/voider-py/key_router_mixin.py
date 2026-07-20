# key_router_mixin.py — key routing methods
import os

from PyQt6.QtCore import Qt


class KeyRouterMixin:

    def _matches(self, key, modifiers, action):
        kb = self._kb.get(action)
        return kb is not None and key == kb[0] and modifiers == kb[1]

    def _refocus_active_editor(self):
        if self.current_view == 0:
            if self._f1_scratch_mode and self.scratch_view:
                self.scratch_view.editor.setFocus()
            else:
                self.entry.setFocus()
        elif self.current_view == 1 and self.circular_view:
            self.circular_view.editor.setFocus()
        elif self.current_view == 2 and self.book_view:
            self.book_view.editor.setFocus()
        elif self.current_view == 3 and self.reading_view:
            self.reading_view.setFocus()
        elif self.current_view == 9 and self.book_concat_view:
            self.book_concat_view.editor.setFocus()

    def keyPressEvent(self, event):
        key = event.key()
        mods = event.modifiers()

        # Lock screen absorbs all keys while visible (except its own Enter/Escape)
        if self._lock_screen and self._lock_screen.isVisible():
            self._lock_screen.keyPressEvent(event)
            event.accept()
            return

        # Route Up/Down to the display ring when search is active (clamped, no wrap)
        if self._f2_search_active and self.current_view == 1 and self._f2_display_ring:
            if key == Qt.Key.Key_Up:
                self._f2_display_ring.index = max(0, self._f2_display_ring.index - 1)
                self.circular_view._offset = 0.0
                self._f2_search_show_center()
                event.accept(); return
            elif key == Qt.Key.Key_Down:
                self._f2_display_ring.index = min(len(self._f2_display_ring.lines) - 1,
                                                  self._f2_display_ring.index + 1)
                self.circular_view._offset = 0.0
                self._f2_search_show_center()
                event.accept(); return
        if self._f3_search_active and self.current_view == 2 and self._f3_display_ring:
            if key == Qt.Key.Key_Up:
                self._f3_display_ring.index = max(0, self._f3_display_ring.index - 1)
                self.book_view._offset = 0.0
                self._f3_search_show_center()
                event.accept(); return
            elif key == Qt.Key.Key_Down:
                self._f3_display_ring.index = min(len(self._f3_display_ring.lines) - 1,
                                                  self._f3_display_ring.index + 1)
                self.book_view._offset = 0.0
                self._f3_search_show_center()
                event.accept(); return

        # Global: view switching
        if self._matches(key, mods, 'view_f1'):
            self.switch_to_view(0); event.accept(); return
        if self._matches(key, mods, 'view_f2'):
            self.switch_to_view(1); event.accept(); return
        if self._matches(key, mods, 'view_f3'):
            if self.current_view != 2:
                self.switch_to_view(2)
            event.accept(); return
        if self._matches(key, mods, 'view_f4'):
            self.switch_to_view(3); event.accept(); return
        if self._matches(key, mods, 'view_f5'):
            self.switch_to_view(4); event.accept(); return
        if self._matches(key, mods, 'view_f6'):
            self.switch_to_view(5); event.accept(); return
        if self._matches(key, mods, 'view_f7'):
            self.switch_to_view(6); event.accept(); return
        if self._matches(key, mods, 'view_f8'):
            self.switch_to_view(7); event.accept(); return
        if self._matches(key, mods, 'view_f9'):
            self.switch_to_view(8); event.accept(); return
        if self._matches(key, mods, 'view_f10'):
            self._prev_view = self.current_view
            self.switch_to_view(10); event.accept(); return
        if self._matches(key, mods, 'help'):
            self._toggle_help(); event.accept(); return

        # F1: Ctrl+Enter → temporary peek at 0.txt in F2 (doesn't change f2_file)
        if self.current_view == 0 and key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and \
                (mods & Qt.KeyboardModifier.ControlModifier):
            self._f2_peek_0 = True
            self.switch_to_view(1)
            event.accept()
            return

        # Global: backtick → round-trip to the 0.txt scratch (and back).
        if self._matches(key, mods, 'scratch_toggle'):
            self._goto_scratch_toggle(); event.accept(); return

        # Global: rebase (F2 only, enforced inside; F3 handled view-specifically)
        if self._matches(key, mods, 'rebase') and self.current_view != 2:
            self.rebase_to_index_zero(); event.accept(); return

        # Global: reshuffle vault
        if self._matches(key, mods, 'reshuffle'):
            self.load_vault_lines()
            if self.current_view == 3 and self.vault_view:
                self.vault_view.update()
            event.accept(); return

        # Global: file/folder pickers
        if self._matches(key, mods, 'pick_active_file'):
            self.pick_active_file(); event.accept(); return
        if self._matches(key, mods, 'pick_book_dir'):
            self.pick_book_directory(); event.accept(); return
        if self._matches(key, mods, 'pick_dir'):
            self.change_void_directory(); event.accept(); return

        # Print (Ctrl+P) and Export/Save as (Ctrl+S)
        if self._matches(key, mods, 'print_doc') and self.current_view == 2:
            self.print_book(); event.accept(); return
        if self._matches(key, mods, 'print_doc') and self.current_view == 1:
            self.print_doc(); event.accept(); return
        if self._matches(key, mods, 'print_doc') and self.current_view == 3:
            self.print_vault(); event.accept(); return
        if self._matches(key, mods, 'export_doc') and self.current_view == 2:
            self.export_book(); event.accept(); return
        if self._matches(key, mods, 'export_doc') and self.current_view == 1:
            self.export_doc(); event.accept(); return
        if self._matches(key, mods, 'export_doc') and self.current_view == 3:
            self.export_vault(); event.accept(); return

        # Global: screenshot / open folder
        if self._matches(key, mods, 'screenshot'):
            self.take_screenshot(); event.accept(); return
        if self._matches(key, mods, 'open_screenshots'):
            self.open_screenshots_folder(); event.accept(); return

        if self._matches(key, mods, 'commit_void'):
            self.commit_void()
            event.accept(); return

        if self._matches(key, mods, 'backup'):
            self._backup_vault()
            event.accept(); return

        if self._matches(key, mods, 'tts_toggle'):
            self._tts_toggle(); event.accept(); return

        # View-specific
        if self.current_view == 0:
            self._handle_f1_keys(key, mods)
        elif self.current_view == 1:
            self._handle_f2_keys(key, mods, event)
        elif self.current_view == 2:
            self._handle_f3_keys(key, mods, event)
        elif self.current_view == 3:
            self._handle_f4_keys(key, mods, event)
        elif self.current_view == 4:
            self._handle_f5_keys(key, mods, event)
        elif self.current_view in (5, 6, 7):
            if key == Qt.Key.Key_Escape:
                self.switch_to_view(0); event.accept()
            elif self._matches(key, mods, 'quit'):
                self._show_lock_screen(); event.accept()
        elif self.current_view == 8:   # F9 prose editor
            if key == Qt.Key.Key_S and (mods & Qt.KeyboardModifier.ControlModifier):
                self._editor_save(); event.accept()
            elif key == Qt.Key.Key_Escape:
                self.switch_to_view(1); event.accept()   # save-on-leave handles it
        elif self.current_view == 9:
            if key == Qt.Key.Key_Escape:
                self.switch_to_view(2); event.accept()
            elif self._matches(key, mods, 'quit'):
                self._show_lock_screen(); event.accept()
        elif self.current_view == 10:
            if key in (Qt.Key.Key_Escape, Qt.Key.Key_F10):
                self.switch_to_view(getattr(self, '_prev_view', 0)); event.accept()
            elif self._matches(key, mods, 'quit'):
                self._show_lock_screen(); event.accept()

    def _handle_f1_keys(self, key, mods):
        if self._f1_scratch_mode and key == Qt.Key.Key_Escape:
            self._exit_f1_scratch()
            return
        if self._matches(key, mods, 'quit'):
            self._show_lock_screen()
        elif self._matches(key, mods, 'file_prev'):
            self.show_previous_file()
        elif self._matches(key, mods, 'file_next'):
            self.show_next_file()
        elif self._matches(key, mods, 'para_prev'):
            self._f1_persist_entry()
            self.goto_prev_dot()
            self._f1_show_current()
        elif self._matches(key, mods, 'para_next'):
            self._f1_persist_entry()
            self.goto_next_dot()
            self._f1_show_current()
        elif key == Qt.Key.Key_Up and mods == Qt.KeyboardModifier.NoModifier:
            self._f1_persist_entry()
            self.line_ring.move(-1)
            self._f1_show_current()
        elif key == Qt.Key.Key_Down and mods == Qt.KeyboardModifier.NoModifier:
            self._f1_persist_entry()
            self.line_ring.move(1)
            self._f1_show_current()

    def _handle_f2_keys(self, key, mods, event):
        # Up/Down/Enter handled by circular_view.editor signals.
        if self._matches(key, mods, 'swap_up'):
            if self.line_ring.current() == '.':
                self.swap_paragraph_up()
            else:
                self.swap_line_up()
            event.accept()
        elif self._matches(key, mods, 'swap_down'):
            if self.line_ring.current() == '.':
                self.swap_paragraph_down()
            else:
                self.swap_line_down()
            event.accept()
        elif self._matches(key, mods, 'para_prev'):
            self.goto_prev_dot()
            self._doc_show_editor()
            event.accept()
        elif self._matches(key, mods, 'para_next'):
            self.goto_next_dot()
            self._doc_show_editor()
            event.accept()
        elif self._matches(key, mods, 'reformat_file'):
            # On 0.txt this key splits the scratch into documents; elsewhere it
            # reformats the active file into one sentence per line.
            if os.path.abspath(self.current_file_path) == os.path.abspath(self.f1_file):
                self._split_zero_to_docs()
            else:
                self.reformat_active_file()
            event.accept()
        elif self._matches(key, mods, 'shuffle_zero'):
            self._shuffle_zero()
            event.accept()
        elif self._matches(key, mods, 'dispatch'):
            self._dispatch_paragraphs()
            event.accept()
        elif self._matches(key, mods, 'split_chapter'):
            self._split_chapter_at_slash()
            event.accept()
        elif (mods & Qt.KeyboardModifier.ControlModifier) and key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            editor = self.circular_view.editor
            at_start = editor.cursorPosition() == 0
            at_end = editor.cursorPosition() == len(editor.text())
            if (key == Qt.Key.Key_Delete and at_start) or (key == Qt.Key.Key_Backspace and at_end):
                self._delete_line_to_zero()
                event.accept()
        elif mods == Qt.KeyboardModifier.ControlModifier and key == Qt.Key.Key_F:
            self._open_f2_search(); event.accept()
        elif key == Qt.Key.Key_Escape:
            if self._f2_search_active:
                self._close_f2_search(restore=True)
            elif self._para_focus:
                self._exit_para_focus()
            else:
                self.switch_to_view(0)

    def _handle_f3_keys(self, key, mods, event):
        # Up/Down/Enter handled by book_view.editor signals.
        if mods == Qt.KeyboardModifier.ControlModifier and key == Qt.Key.Key_F:
            self._open_f3_search(); event.accept(); return
        if self._matches(key, mods, 'merge_book'):
            self._book_merge_prompt(); event.accept(); return
        if self._matches(key, mods, 'split_chapter'):
            self._book_split_current(); event.accept(); return
        if key == Qt.Key.Key_Escape and self._f3_search_active:
            self._close_f3_search(restore=True); event.accept(); return
        if key == Qt.Key.Key_Escape:
            if getattr(self, '_book_pending_merge', False):
                self._book_cancel_merge()
            elif self._book_pending_new:
                idx = self.book_ring.index
                self.book_ring.lines.pop(idx)
                self._library_lines.pop(idx)
                if not self.book_ring.lines:
                    self.book_ring.lines = ['.']
                    self._library_lines = ['.']
                self.book_ring.index = max(0, idx - 1) % len(self.book_ring.lines)
                self._book_pending_new = False
                self.book_view._offset = 0.0
                self._book_show_editor()
            else:
                self.switch_to_view(0)
        elif self._matches(key, mods, 'para_prev'):
            ring = self.book_ring
            n = len(ring.lines)
            idx = (ring.index - 1) % n
            for _ in range(n):
                if ring.lines[idx] == '.':
                    ring.index = idx
                    break
                idx = (idx - 1) % n
            self._book_show_editor(); event.accept()
        elif self._matches(key, mods, 'para_next'):
            ring = self.book_ring
            n = len(ring.lines)
            idx = (ring.index + 1) % n
            for _ in range(n):
                if ring.lines[idx] == '.':
                    ring.index = idx
                    break
                idx = (idx + 1) % n
            self._book_show_editor(); event.accept()
        elif self._matches(key, mods, 'swap_up'):
            self._book_swap_up(); event.accept()
        elif self._matches(key, mods, 'swap_down'):
            self._book_swap_down(); event.accept()
        elif self._matches(key, mods, 'rebase'):
            self._book_rebase(); event.accept()
        elif self._matches(key, mods, 'reformat_file'):
            self._merge_zero_files(silent=False); event.accept()
        elif self._matches(key, mods, 'quit'):
            self._show_lock_screen()

    def _handle_f5_keys(self, key, mods, event):
        """F5 — linear paragraph reorder. Up/Down navigate, Alt+Up/Down swap, Enter
        → F2. Right opens the in-view chapter picker to send the current paragraph."""
        Alt = Qt.KeyboardModifier.AltModifier
        Ctrl = Qt.KeyboardModifier.ControlModifier
        No = Qt.KeyboardModifier.NoModifier
        K = Qt.Key
        # In-view chapter picker (send mode): type-to-filter, cycle, send, cancel.
        if getattr(self, '_f5_picker_open', False):
            if key == K.Key_Escape:
                self._f5_close_picker(); event.accept(); return
            if key in (K.Key_Return, K.Key_Enter, K.Key_Right):
                self._f5_pick_confirm(); event.accept(); return
            if key in (K.Key_Tab, K.Key_Down):
                self._f5_pick_cycle(1); event.accept(); return
            if key in (K.Key_Backtab, K.Key_Up):
                self._f5_pick_cycle(-1); event.accept(); return
            if key == K.Key_Backspace:
                self._f5_pick_filter_backspace(); event.accept(); return
            text = event.text()
            if text and text.isprintable() and not (mods & (Ctrl | Alt)):
                self._f5_pick_filter_add(text); event.accept(); return
            event.accept(); return
        # Swap the current paragraph up/down (fences are crossed, not moved).
        if key == K.Key_Up and (mods & Alt):
            self._f5_swap_up(); event.accept(); return
        if key == K.Key_Down and (mods & Alt):
            self._f5_swap_down(); event.accept(); return
        # Navigate paragraphs (linear, clamped at the ends).
        if key == K.Key_Up and mods == No:
            self._f5_prev_para(); event.accept(); return
        if key == K.Key_Down and mods == No:
            self._f5_next_para(); event.accept(); return
        # Right → open the in-view picker to send this paragraph to a chapter.
        if key == K.Key_Right and mods == No:
            self._f5_open_picker(); event.accept(); return
        # Enter → jump to F2 on this paragraph.
        if key in (K.Key_Return, K.Key_Enter):
            self._f5_enter_to_f2(); event.accept(); return
        if key == K.Key_Escape:
            self.switch_to_view(0); event.accept(); return
        if self._matches(key, mods, 'quit'):
            self._show_lock_screen(); event.accept(); return

    def _handle_f4_keys(self, key, mods, event):
        # F4 is a paginated book reader: flip pages, never scroll.
        K = Qt.Key
        rv = self.reading_view
        if key in (K.Key_Space, K.Key_Right, K.Key_PageDown, K.Key_Down):
            if rv:
                rv.next_page()
            event.accept(); return
        if key in (K.Key_Backspace, K.Key_Left, K.Key_PageUp, K.Key_Up):
            if rv:
                rv.prev_page()
            event.accept(); return
        if key == K.Key_Home:
            if rv:
                rv.first_page()
            event.accept(); return
        if key == K.Key_End:
            if rv:
                rv.last_page()
            event.accept(); return
        if key == K.Key_Escape:
            self.switch_to_view(1); event.accept(); return
        if self._matches(key, mods, 'quit'):
            self._show_lock_screen(); event.accept()

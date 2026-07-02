# f3_mixin.py — F3 library/book browser methods
import os
import random

from PyQt6.QtCore import Qt

from app_config import _save_config
from line_ring import LineRing


class F3Mixin:

    def _book_is_portal(self, idx=None):
        """True if the F3 entry at idx (default current) is the read-only '0'
        scratch portal. A portal is any library entry named '0' / '0.txt'; it is
        not renamable and Enter on it jumps to the scratch 0.txt."""
        if idx is None:
            idx = self.book_ring.index
        if idx < 0 or idx >= len(self.book_ring.lines):
            return False
        if self.book_ring.lines[idx] == '0':
            return True
        return (idx < len(self._library_lines)
                and self._library_lines[idx].lower() == '0.txt')

    def _book_show_editor(self):
        """Show F3 editor; dots and the '0' portal show read-only."""
        if not self.book_ring.lines:
            return
        view = self.book_view
        view.edit_mode = True
        center_y = view.height() // 2
        # Almost full width (no 800px cap) so long titles stay fully visible.
        editor_width = view.width() - 100
        view.editor.setFixedWidth(editor_width)
        view.editor.move(
            (view.width() - editor_width) // 2,
            center_y - view.editor.sizeHint().height() // 2
        )
        if self.book_ring.current() == '.':
            view.editor.setText('.')
            view.editor.setReadOnly(True)
        elif self._book_is_portal():
            view.editor.setText('0')
            view.editor.setReadOnly(True)
        else:
            view.editor.setText(self.book_ring.current())
            view.editor.setReadOnly(False)
        view.editor.setCursorPosition(0)
        view.editor.show()
        view.editor.setFocus()
        view.update()

    def _book_random(self):
        """Tab in F3: jump to a random real book title (skip '.' separators and
        the read-only '0' portals)."""
        if self._book_pending_new:
            return
        self._book_try_rename()
        candidates = [i for i, l in enumerate(self.book_ring.lines)
                      if l != '.' and not self._book_is_portal(i)]
        if not candidates:
            return
        self.book_ring.index = random.choice(candidates)
        self.book_view._offset = 0.0
        self._book_show_editor()

    def _book_navigate(self, delta):
        self._tts_cut()
        if self._book_pending_new:
            # Cancel the pending new entry
            idx = self.book_ring.index
            self.book_ring.lines.pop(idx)
            self._library_lines.pop(idx)
            if not self.book_ring.lines:
                self.book_ring.lines = ['.']
                self._library_lines = ['.']
            self.book_ring.index = max(0, idx - 1) % len(self.book_ring.lines)
            self._book_pending_new = False
        self._book_try_rename()
        if len(self.book_ring.lines) < 2:
            return
        self.book_ring.move(delta)
        self.book_view._offset = 0.0
        if self.book_ring.current() == '.':
            self.book_view.editor.setText('.')
            self.book_view.editor.setReadOnly(True)
        elif self._book_is_portal():
            self.book_view.editor.setText('0')
            self.book_view.editor.setReadOnly(True)
        else:
            self.book_view.editor.setText(self.book_ring.current())
            self.book_view.editor.setReadOnly(False)
        self.book_view.editor.setCursorPosition(0)
        self.book_view.update()

    def _book_jump_start(self):
        """Home in F3: jump to first non-dot entry."""
        self._tts_cut()
        ring = self.book_ring
        for i in range(len(ring.lines)):
            if ring.lines[i] != '.':
                ring.index = i
                break
        self._book_show_editor()

    def _book_jump_end(self):
        """End in F3: jump to last non-dot entry."""
        self._tts_cut()
        ring = self.book_ring
        for i in range(len(ring.lines) - 1, -1, -1):
            if ring.lines[i] != '.':
                ring.index = i
                break
        self._book_show_editor()

    def _book_try_rename(self):
        if not self.book_view:
            return True
        if self._book_pending_new:
            return True
        # The '0' portal is read-only — never rename it.
        if self._book_is_portal():
            return True
        fname = self._library_current_fname()
        if not fname:
            return True
        new_display = self.book_view.editor.text().strip()
        if not new_display or new_display.startswith('.'):
            self.book_view.editor.setText(self.book_ring.current())
            return True
        # '0' is reserved for the scratch portal. Refuse to rename any real file
        # to '0'/'0.txt' — os.rename overwrites the destination, which would erase
        # the scratch 0.txt. (Use Shift+Enter + '0' to add a portal instead.)
        if new_display == '0' or new_display.lower() == '0.txt':
            print("⛔ '0' is reserved for the scratch portal — rename refused.")
            self.book_view.editor.setText(self.book_ring.current())
            return True
        new_fname = new_display + '.txt'
        if new_fname == fname:
            return True
        old_path = self._library_path_cache.get(fname)
        if not old_path or not os.path.exists(old_path):
            return True
        new_path = os.path.join(os.path.dirname(old_path), new_fname)
        if os.path.exists(new_path):
            print(f"⛔ {new_fname} already exists — rename refused (would overwrite it).")
            self.book_view.editor.setText(self.book_ring.current())
            return True
        try:
            self._f3_undo_begin()
            self._f3_undo_file(old_path)
            self._f3_undo_file(new_path)
            os.rename(old_path, new_path)
            if self.current_file_path == old_path:
                self.current_file_path = new_path
                self.config['active_file'] = new_path
                _save_config(self.config)
            idx = self.book_ring.index
            self._library_lines[idx] = new_fname
            self.book_ring.lines[idx] = new_display
            del self._library_path_cache[fname]
            self._library_path_cache[new_fname] = new_path
            self._save_library()
            self._f3_undo_commit('rename')
            print(f"📝 Renamed: {fname} → {new_fname}")
        except Exception as e:
            self._f3_txn = None
            print(f"⚠️ Rename failed: {e}")
            return False
        return True

    def _book_confirm_edit(self):
        """Enter in F3: handle new-entry mode, dot → concat view, title → F2."""
        if getattr(self, '_book_pending_merge', False):
            self._book_do_merge()
            return
        if self._book_pending_new:
            text = self.book_view.editor.text().strip()
            idx = self.book_ring.index
            if not text:
                # Empty → cancel, remove placeholder
                self.book_ring.lines.pop(idx)
                self._library_lines.pop(idx)
                if not self.book_ring.lines:
                    self.book_ring.lines = ['.']
                    self._library_lines = ['.']
                self.book_ring.index = max(0, idx - 1) % len(self.book_ring.lines)
            elif text == '.':
                # Convert placeholder to separator
                self.book_ring.lines[idx] = '.'
                self._library_lines[idx] = '.'
                self._save_library()
            elif text == '0':
                # Convert placeholder to a '0' scratch portal — no file is
                # created, no collision with the real 0.txt. Read-only marker.
                self.book_ring.lines[idx] = '0'
                self._library_lines[idx] = '0.txt'
                self._save_library()
            else:
                # Create new file and open in F2
                fname = text + '.txt'
                fpath = os.path.join(self.void_dir, 'I', fname)
                if not os.path.exists(fpath):
                    open(fpath, 'w', encoding='utf-8').close()
                self.book_ring.lines[idx] = text
                self._library_lines[idx] = fname
                self._library_path_cache[fname] = fpath
                self._save_library()
                self._book_pending_new = False
                self._set_f2_file(fpath)
                self.switch_to_view(1)
                return
            self._book_pending_new = False
            self._book_show_editor()
            return

        if self.book_ring.current() == '.':
            self._book_open_concat()
            return
        if self._book_is_portal():
            # Portal → jump to the scratch 0.txt in F2 (no rename, no file ops).
            self._set_f2_file(self.f1_file)
            self.switch_to_view(1)
            return
        if not self._book_try_rename():
            return
        fname = self._library_current_fname()
        if not fname:
            return
        fpath = self._library_path_cache.get(fname)
        if not fpath:
            fpath = os.path.join(self.void_dir, 'I', fname)
        self._set_f2_file(fpath)
        self.switch_to_view(1)

    def _book_new_entry(self):
        """Shift+Enter in F3: insert a blank entry below current for the user to name."""
        if self._book_pending_new:
            return
        self._book_try_rename()
        idx = self.book_ring.index
        self.book_ring.lines.insert(idx + 1, '')
        self._library_lines.insert(idx + 1, '')
        self.book_ring.index = idx + 1
        self._book_pending_new = True
        self.book_view._offset = 0.0
        self.book_view.editor.setText('')
        self.book_view.editor.setReadOnly(False)
        self.book_view.editor.setCursorPosition(0)
        self.book_view.update()

    def _book_send_to_zero(self):
        """Ctrl+Delete in F3: on dot → delete separator; on title → send lines to 0.txt and delete file."""
        if self._book_pending_new:
            return
        if self.book_ring.current() == '.':
            self._book_backspace_on_dot()
            return
        if self._book_is_portal():
            # Remove only the portal marker from the library — never touch 0.txt.
            idx = self.book_ring.index
            self.book_ring.lines.pop(idx)
            self._library_lines.pop(idx)
            if not self.book_ring.lines:
                self.book_ring.lines = ['.']
                self._library_lines = ['.']
            n = len(self.book_ring.lines)
            self.book_ring.index = idx % n
            self._save_library()
            self.book_view._offset = 0.0
            self._book_show_editor()
            print("🗑️ Portal '0' removed (0.txt untouched)")
            return
        fname = self._library_current_fname()
        if not fname:
            return
        fpath = self._library_path_cache.get(fname)
        if not fpath or not os.path.exists(fpath):
            return
        if os.path.abspath(fpath) == os.path.abspath(self.f1_file):
            return
        self._f3_undo_begin()
        self._f3_undo_file(self.f1_file)
        self._f3_undo_file(fpath)
        try:
            with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                lines = [l.strip() for l in f if l.strip() and l.strip() != '.']
        except Exception as e:
            print(f"⚠️ Cannot read {fpath}: {e}")
            return
        if lines:
            try:
                with open(self.f1_file, 'a', encoding='utf-8') as f:
                    f.write('\n.\n')
                    f.write('\n'.join(lines) + '\n')
            except Exception as e:
                print(f"⚠️ Cannot append to 0.txt: {e}")
                return
        try:
            os.remove(fpath)
        except Exception as e:
            print(f"⚠️ Cannot delete {fpath}: {e}")
            return
        idx = self.book_ring.index
        self.book_ring.lines.pop(idx)
        self._library_lines.pop(idx)
        if fname in self._library_path_cache:
            del self._library_path_cache[fname]
        if not self.book_ring.lines:
            self.book_ring.lines = ['.']
            self._library_lines = ['.']
        n = len(self.book_ring.lines)
        self.book_ring.index = idx % n
        while self.book_ring.current() == '.' and n > 1:
            self.book_ring.index = (self.book_ring.index + 1) % n
        self._save_library()
        self._f3_undo_commit('delete')
        if self.current_file_path == self.f1_file:
            self.load_doc_lines()
        self.book_view._offset = 0.0
        self._book_show_editor()
        print(f"🗑️ {len(lines)} lines from {fname} → 0.txt, file deleted")

    def _book_insert_separator(self):
        """Tab in F3: insert a group separator dot above the current position."""
        if self.book_ring.current() == '.':
            return
        self._book_try_rename()
        idx = self.book_ring.index
        self.book_ring.lines.insert(idx, '.')
        self._library_lines.insert(idx, '.')
        self.book_ring.index = idx
        self._save_library()
        self.book_view._offset = 0.0
        self.book_view.editor.setText('.')
        self.book_view.editor.setReadOnly(True)
        self.book_view.editor.setCursorPosition(0)
        self.book_view.update()

    def _book_backspace_on_dot(self):
        """Backspace in F3 when on a dot: delete the group separator."""
        if self.book_ring.current() != '.':
            return
        idx = self.book_ring.index
        self.book_ring.lines.pop(idx)
        self._library_lines.pop(idx)
        if not self.book_ring.lines:
            self.book_ring.lines = ['.']
            self._library_lines = ['.']
            self.book_ring.index = 0
        else:
            self.book_ring.index = idx % len(self.book_ring.lines)
            while self.book_ring.current() == '.' and len(self.book_ring.lines) > 1:
                self.book_ring.index = (self.book_ring.index + 1) % len(self.book_ring.lines)
        self._save_library()
        self.book_view._offset = 0.0
        if self.book_ring.current() == '.':
            self.book_view.editor.setText('.')
            self.book_view.editor.setReadOnly(True)
        else:
            self.book_view.editor.setText(self.book_ring.current())
            self.book_view.editor.setReadOnly(False)
        self.book_view.editor.setCursorPosition(0)
        self.book_view.update()

    def _book_open_concat(self):
        """Build a read-only concatenated ring from all files in the current dot group."""
        dot_idx = self.book_ring.index
        n = len(self._library_lines)
        group_fnames = []
        i = (dot_idx + 1) % n
        for _ in range(n - 1):
            if self._library_lines[i] == '.':
                break
            group_fnames.append(self._library_lines[i])
            i = (i + 1) % n
        if not group_fnames:
            return

        lines = ['.']
        header_indices = set()
        for fname in group_fnames:
            fpath = self._library_path_cache.get(fname)
            if not fpath or not os.path.exists(fpath):
                continue
            stem = os.path.splitext(fname)[0].upper()
            header_indices.add(len(lines))
            lines.append(f'── {stem} ──')
            try:
                with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                    for raw in f:
                        s = raw.strip()
                        if s and s != '.':
                            lines.append(s)
            except Exception:
                pass
            lines.append('.')

        if len(lines) <= 1:
            return

        self.book_concat_ring = LineRing(lines)
        self._book_concat_header_indices = header_indices
        for start_i in range(len(lines)):
            if lines[start_i] not in ('.', '') and start_i not in header_indices:
                self.book_concat_ring.index = start_i
                break

        self.switch_to_view(9)

    def _book_concat_show_editor(self):
        view = self.book_concat_view
        view.edit_mode = True
        center_y = view.height() // 2
        editor_width = view.width() - 100
        view.editor.setFixedWidth(editor_width)
        view.editor.move(
            (view.width() - editor_width) // 2,
            center_y - view.editor.sizeHint().height() // 2
        )
        view.editor.setText(self.book_concat_ring.current())
        view.editor.setReadOnly(True)
        view.editor.setCursorPosition(0)
        view.editor.show()
        view.editor.setFocus()
        view.update()

    def _book_concat_navigate(self, delta):
        self._tts_cut()
        ring = self.book_concat_ring
        n = len(ring.lines)
        for _ in range(n):
            ring.move(delta)
            cur = ring.current()
            if cur not in ('.', '') and ring.index not in self._book_concat_header_indices:
                break
        self.book_concat_view._offset = 0.0
        self.book_concat_view.editor.setText(ring.current())
        self.book_concat_view.editor.setCursorPosition(0)
        self.book_concat_view.update()

    def _book_block_bounds(self, i):
        """[start, end) of the book block led by the dot at index i (i is a dot)."""
        lines = self.book_ring.lines
        n = len(lines)
        j = i + 1
        while j < n and lines[j] != '.':
            j += 1
        return i, j

    def _apply_book_order(self, order):
        """Reorder both parallel arrays by an index permutation (keeps them
        aligned) and persist."""
        self.book_ring.lines = [self.book_ring.lines[k] for k in order]
        self._library_lines = [self._library_lines[k] for k in order]
        self._save_library()

    def _book_swap_entries(self, a, b):
        bl, ll = self.book_ring.lines, self._library_lines
        bl[a], bl[b] = bl[b], bl[a]
        ll[a], ll[b] = ll[b], ll[a]
        self._save_library()

    def _book_move_block(self, up):
        """Move the whole book (the dot + its chapters) at the current dot past
        the adjacent book."""
        idx = self.book_ring.index
        lines = self.book_ring.lines
        n = len(lines)
        s, e = self._book_block_bounds(idx)             # current book [s, e)
        if up:
            p = s - 1                                   # start of previous book
            while p >= 0 and lines[p] != '.':
                p -= 1
            if p < 0:
                return                                  # no book above
            order = (list(range(0, p)) + list(range(s, e))
                     + list(range(p, s)) + list(range(e, n)))
            self.book_ring.index = p
        else:
            if e >= n:
                return                                  # no book below
            _, e2 = self._book_block_bounds(e)          # next book [e, e2)
            order = (list(range(0, s)) + list(range(e, e2))
                     + list(range(s, e)) + list(range(e2, n)))
            self.book_ring.index = s + (e2 - e)
        self._apply_book_order(order)

    def _book_swap_up(self):
        """Alt+Up in F3: a dot moves its whole book up; a chapter swaps with its
        immediate neighbour (reorders within the book, or crosses into the book
        above when the neighbour is a separator)."""
        self._book_try_rename()   # commit an edited title before reordering
        idx = self.book_ring.index
        lines = self.book_ring.lines
        self._f3_undo_begin()
        if lines[idx] == '.':
            self._book_move_block(up=True)
        elif idx > 0:
            j = idx - 1
            # cross a separator only if there's a book above to move into
            if not (lines[j] == '.' and not any(x != '.' for x in lines[:j])):
                self._book_swap_entries(idx, j)
                self.book_ring.index = j
        self._f3_undo_commit('reorder')
        self._book_refresh_editor()

    def _book_swap_down(self):
        """Alt+Down in F3: a dot moves its whole book down; a chapter swaps with
        its immediate neighbour."""
        self._book_try_rename()   # commit an edited title before reordering
        idx = self.book_ring.index
        lines = self.book_ring.lines
        self._f3_undo_begin()
        if lines[idx] == '.':
            self._book_move_block(up=False)
        elif idx < len(lines) - 1:
            j = idx + 1
            # cross a separator only if there's a book below to move into
            if not (lines[j] == '.' and not any(x != '.' for x in lines[j + 1:])):
                self._book_swap_entries(idx, j)
                self.book_ring.index = j
        self._f3_undo_commit('reorder')
        self._book_refresh_editor()

    def _book_refresh_editor(self):
        if not self.book_view:
            return
        self.book_view._offset = 0.0
        cur = self.book_ring.current()
        self.book_view.editor.setText('.' if cur == '.' else cur)
        self.book_view.editor.setReadOnly(cur == '.')
        self.book_view.editor.setCursorPosition(0)
        self.book_view.update()

    def _resolve_f3_index(self, active_fname):
        """Where the F3 cursor should land on entry: the remembered entry (by exact
        index, then by name so it survives reordering between sessions), else the
        active file's row, else the top. Fixes the reopen/re-entry reset to index 0."""
        lib = self._library_lines
        n = len(lib)
        if n == 0:
            return 0
        last = getattr(self, '_book_last_index', None)
        entry = getattr(self, '_book_last_entry', None)
        # 1) exact: the remembered index still holds the remembered entry
        #    (also how a specific '.' separator or '0' portal position is kept).
        if last is not None and 0 <= last < n and entry is not None and lib[last] == entry:
            return last
        # 2) find the remembered real file by name (order may have changed)
        if entry and entry not in ('.', '', '0.txt'):
            try:
                return lib.index(entry)
            except ValueError:
                pass
        # 3) fall back to the active file's row
        try:
            return lib.index(active_fname)
        except ValueError:
            return 0

    def _book_activate_current(self):
        """Make the highlighted chapter the active file. Called when LEAVING F3
        (any exit — Enter, F2, F4, …), NOT on every navigation, so browsing the
        library doesn't load a file per keystroke. Dots and '0' portals never
        become the active file."""
        if self.book_ring.current() == '.' or self._book_is_portal():
            return
        self._book_try_rename()
        fname = self._library_current_fname()
        if not fname:
            return
        fpath = self._library_path_cache.get(fname)
        if not (fpath and os.path.isfile(fpath)):
            return
        if os.path.abspath(fpath) == os.path.abspath(self.current_file_path):
            return
        self._set_f2_file(fpath)
        self.current_file_path = fpath
        self.load_doc_lines()

    def _book_rebase(self):
        """Ctrl+0 in F3: rotate ring so current title becomes first."""
        idx = self.book_ring.index
        if idx == 0:
            return
        self.book_ring.lines = self.book_ring.lines[idx:] + self.book_ring.lines[:idx]
        self._library_lines = self._library_lines[idx:] + self._library_lines[:idx]
        self.book_ring.index = 0
        while self.book_ring.current() == '.' and len(self.book_ring.lines) > 1:
            self.book_ring.move(1)
        self._save_library()
        self.book_view._offset = 0.0
        self.book_view.editor.setText(self.book_ring.current())
        self.book_view.editor.setReadOnly(False)
        self.book_view.editor.setCursorPosition(0)
        self.book_view.update()

    # ── Merge a book into one doc (inverse of split) ───────────────────────────

    def _book_merge_prompt(self):
        """Ctrl+Shift+M on a dot in F3: open a blank naming line right below the dot
        (an empty caret) to name the merged doc. Enter merges; empty/Esc cancels.
        The dot stays; only meaningful on a separator."""
        if self.book_ring.current() != '.' or getattr(self, '_book_pending_merge', False):
            return
        self._f3_undo_begin()          # capture the clean book (before the naming line)
        idx = self.book_ring.index
        self._merge_dot_idx = idx
        self.book_ring.lines.insert(idx + 1, '')
        self._library_lines.insert(idx + 1, '')
        self.book_ring.index = idx + 1
        self._book_pending_merge = True
        if self.book_view:
            self.book_view._offset = 0.0
            self.book_view.editor.setText('')
            self.book_view.editor.setReadOnly(False)
            self.book_view.editor.setCursorPosition(0)
            self.book_view.editor.setFocus()
            self.book_view.update()
        print("🔗 Name the merged doc, Enter to merge (empty/Esc cancels).")

    def _book_cancel_merge(self):
        """Remove the blank naming line and leave the book untouched."""
        self._f3_txn = None            # discard the pending undo transaction
        self._book_pending_merge = False
        ph = getattr(self, '_merge_dot_idx', self.book_ring.index - 1) + 1
        if 0 <= ph < len(self._library_lines) and self._library_lines[ph] == '':
            self._library_lines.pop(ph)
            self.book_ring.lines.pop(ph)
        self.book_ring.index = max(0, min(ph - 1, len(self.book_ring.lines) - 1))
        self._book_show_editor()

    def _book_do_merge(self):
        """Collapse the book (dot -> next dot) into ONE chapter (the named line just
        typed): each chapter's lines followed by a '/name' seal marker, originals
        removed. Stays in F3. Re-split (Ctrl+Shift+S) restores it."""
        name = self.book_view.editor.text().strip() if self.book_view else ''
        dot_idx = getattr(self, '_merge_dot_idx', self.book_ring.index - 1)
        ph = dot_idx + 1                     # the blank naming line
        n = len(self._library_lines)
        chapters = []                        # (index, fname) after the naming line
        i = ph + 1
        while i < n and self._library_lines[i] != '.':
            fn = self._library_lines[i]
            if fn not in ('', '0.txt'):
                chapters.append((i, fn))
            i += 1
        if not name or not chapters:
            self._book_cancel_merge()
            return

        self._git_snapshot_void('merge')
        i_dir = os.path.join(self.void_dir, 'I')

        merged = []
        for _, fn in chapters:
            fpath = self._library_path_cache.get(fn)
            try:
                with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                    lines = [l.rstrip('\n') for l in f]
            except Exception:
                lines = []
            while lines and not lines[-1].strip():
                lines.pop()
            merged.extend(lines)
            merged.append('/' + os.path.splitext(fn)[0])   # seal marker

        cname = name + '.txt'
        cpath = os.path.join(i_dir, cname)
        k = 2
        while os.path.exists(cpath) or cname in self._library_lines:
            cname = f"{name}-{k}.txt"
            cpath = os.path.join(i_dir, cname)
            k += 1
        # Register every file the merge touches for undo (container + chapters).
        self._f3_undo_file(cpath)
        for _, fn in chapters:
            self._f3_undo_file(self._library_path_cache.get(fn))
        if not self._atomic_write_lines(cpath, merged):
            self._book_cancel_merge()
            return

        # The blank naming line becomes the merged container.
        self._library_lines[ph] = cname
        self.book_ring.lines[ph] = name
        self._library_path_cache[cname] = cpath
        # Remove the merged chapters (all after the naming line), reverse order.
        for idx, fn in sorted(chapters, key=lambda t: t[0], reverse=True):
            self._library_lines.pop(idx)
            self.book_ring.lines.pop(idx)
            p = self._library_path_cache.pop(fn, None)
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass

        self._book_pending_merge = False
        self.book_ring.index = ph
        self._save_library()
        self._f3_undo_commit('merge')
        self._book_show_editor()             # stay in F3
        print(f"🔗 Merged {len(chapters)} chapter(s) → {cname}")

    def _book_split_current(self):
        """Ctrl+Shift+S in F3: split the highlighted chapter/merged doc at its
        '/name' markers (activates it, splits, then refreshes the library)."""
        if self.book_ring.current() == '.' or self._book_is_portal():
            return
        self._book_try_rename()
        fname = self._library_current_fname()
        if not fname:
            return
        fpath = self._library_path_cache.get(fname)
        if not (fpath and os.path.isfile(fpath)):
            return
        self.current_file_path = fpath
        self._set_f2_file(fpath)
        self.load_doc_lines()
        self._split_chapter_at_slash()
        self._book_show_editor()

    def _vault_show_editor(self):
        """Show the vault inline editor with the current vault line, cursor at start."""
        if not self.vault_ring.lines:
            return
        view = self.vault_view
        view.edit_mode = True
        center_y = view.height() // 2
        editor_width = view.width() - 100
        view.editor.setFixedWidth(editor_width)
        view.editor.move(
            (view.width() - editor_width) // 2,
            center_y - view.editor.sizeHint().height() // 2
        )
        view.editor.setText(self.vault_ring.current())
        view.editor.setCursorPosition(0)
        view.editor.show()
        view.editor.setFocus()
        view.update()

    def _f3_search_show_center(self):
        """Highlight center of display ring; surroundings dimmed. Search bar keeps focus."""
        if not self._f3_display_ring or not self.book_view:
            return
        view = self.book_view
        view.edit_mode = False
        view.editor.hide()
        view.search_highlight_center = True
        view.update()
        self._f3_search_bar.setFocus()

    def _open_f3_search(self):
        if self._f3_search_active:
            return
        self._f3_search_active = True
        self._f3_search_saved = self.book_ring.index
        display = [l for l in self.book_ring.lines if l != '.'] or ['.']
        self._f3_display_ring = LineRing(display)
        # Start at the file currently highlighted in F3
        cur = self.book_ring.current()
        if cur and cur != '.' and cur in display:
            self._f3_display_ring.index = display.index(cur)
        self.book_view.search_mode = True
        self.book_view.ring = self._f3_display_ring
        self.book_view._offset = 0.0
        self._f3_search_bar.clear()
        self._f3_search_bar.show()
        self._f3_search_bar.raise_()
        self._f3_search_show_center()

    def _close_f3_search(self, restore=True):
        if not self._f3_search_active:
            return
        self._f3_search_active = False
        self._f3_search_bar.hide()
        self._f3_display_ring = None
        if restore and self._f3_search_saved is not None:
            self.book_ring.index = self._f3_search_saved
        self.book_view.search_mode = False
        self.book_view.search_highlight_center = False
        self.book_view.ring = self.book_ring
        self._f3_search_saved = None
        self.book_view._offset = 0.0
        self.book_view.update()
        self._book_show_editor()

    def _f3_search_changed(self, text):
        if not self._f3_search_active:
            return
        q = text.strip().lower()
        if not q:
            filtered = [l for l in self.book_ring.lines if l != '.'] or ['.']
        else:
            filtered = [l for l in self.book_ring.lines if l != '.' and q in l.lower()] or ['.']
        self._f3_display_ring = LineRing(filtered)
        self.book_view.ring = self._f3_display_ring
        self.book_view._offset = 0.0
        self._f3_search_show_center()

    def _f3_search_confirm(self):
        """Enter: load the highlighted file and close search."""
        if not self._f3_search_active:
            return
        matched_display = self._f3_display_ring.current() if self._f3_display_ring else None
        self._f3_search_active = False
        self._f3_search_bar.hide()
        self._f3_display_ring = None
        self._f3_search_saved = None
        if matched_display and matched_display != '.':
            for i, l in enumerate(self.book_ring.lines):
                if l == matched_display:
                    self.book_ring.index = i
                    break
        self.book_view.search_mode = False
        self.book_view.search_highlight_center = False
        self.book_view.ring = self.book_ring
        self.book_view._offset = 0.0
        self.book_view.update()
        # Sync editor text NOW so switch_to_view's _book_try_rename sees no change
        if matched_display and matched_display != '.':
            self.book_view.editor.setText(matched_display)
            self.book_view.editor.setReadOnly(False)
        fname = self._library_current_fname()
        if fname:
            fpath = self._library_path_cache.get(fname)
            if fpath and os.path.isfile(fpath):
                self.f2_file = fpath
                self.current_file_path = fpath
                self.load_doc_lines()
                self.switch_to_view(1)
                return
        self._book_show_editor()

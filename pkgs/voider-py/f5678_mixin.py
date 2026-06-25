# f5678_mixin.py — O/ reader + working set + oracle methods
import os
import json
import random
import threading

from line_ring import LineRing
from app_config import _clean_book_title


class F5678Mixin:

    def _pick_oracle_line(self, source_dir):
        """Pick one random non-empty, non-dot line from source_dir."""
        txt_files = []
        for root, _, files in os.walk(source_dir):
            for f in files:
                if f.lower().endswith('.txt') and f.lower() != '0.txt':
                    txt_files.append(os.path.join(root, f))
        if not txt_files:
            return "..."
        for _ in range(20):
            fpath = random.choice(txt_files)
            try:
                with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                    lines = [l.strip() for l in f if l.strip() and l.strip() != '.']
                if lines:
                    return random.choice(lines)
            except Exception:
                continue
        return "..."

    def _refresh_oracle(self):
        """Pick a fresh oracle line from I/ and update the vault ring."""
        source = os.path.join(self.void_dir, 'I')
        line = self._pick_oracle_line(source)
        self.vault_ring = LineRing(['.', line])
        self.vault_ring.index = 1
        if self.vault_view:
            self.vault_view.ring = self.vault_ring
            self.vault_view._offset = 0.0
        print(f"🔮 Oracle: '{line[:80]}'")

    def load_vault_lines(self):
        self._refresh_oracle()

    def _vault_navigate(self, delta):
        """Pick a fresh oracle line on each navigation."""
        self._tts_cut()
        self._refresh_oracle()
        self.vault_view._offset = 0.0
        self.vault_view.editor.setText(self.vault_ring.current())
        self.vault_view.editor.setCursorPosition(0)
        self.vault_view.update()

    def _vault_confirm_edit(self):
        """Append editor text to doc ring, then pick a fresh oracle line."""
        view = self.vault_view
        new_text = view.editor.text().strip()
        if not new_text:
            return
        insert_pos = self.line_ring.index + 1
        self.line_ring.lines.insert(insert_pos, new_text)
        self.line_ring.index = insert_pos
        self.auto_save_circular()
        self._refresh_oracle()
        view._offset = 0.0
        view.update()
        view.editor.setText(self.vault_ring.current())
        view.editor.setCursorPosition(0)
        view.editor.setFocus()
        print(f"✅ Oracle→Doc[{insert_pos}]: '{new_text}'")

    # ── F8: Oracle from O/ ────────────────────────────────────────────────────

    def _refresh_oracle_o(self):
        line = self._pick_oracle_line(self.o_dir)
        self.oracle_o_ring = LineRing(['.', line])
        self.oracle_o_ring.index = 1
        if self.oracle_o_view:
            self.oracle_o_view.ring = self.oracle_o_ring
            self.oracle_o_view._offset = 0.0
        print(f"🔮 Oracle O/: '{line[:80]}'")

    def _oracle_o_show_editor(self):
        view = self.oracle_o_view
        view.edit_mode = True
        center_y = view.height() // 2
        editor_width = view.width() - 100
        view.editor.setFixedWidth(editor_width)
        view.editor.move((view.width() - editor_width) // 2,
                         center_y - view.editor.sizeHint().height() // 2)
        view.editor.setText(self.oracle_o_ring.current())
        view.editor.show()
        view.editor.setFocus()
        view.editor.setCursorPosition(0)
        view.update()

    def _oracle_o_navigate(self, delta):
        self._tts_cut()
        self._refresh_oracle_o()
        self.oracle_o_view._offset = 0.0
        self.oracle_o_view.editor.setText(self.oracle_o_ring.current())
        self.oracle_o_view.editor.setCursorPosition(0)
        self.oracle_o_view.update()

    def _oracle_o_confirm(self):
        new_text = self.oracle_o_view.editor.text().strip()
        if not new_text:
            return
        self.o_reader_ring = LineRing(['.', new_text])
        self.o_reader_ring.index = 1
        if self.transform_view:
            self.transform_view.ring = self.o_reader_ring
        self.switch_to_view(4)

    # ── F7: O/ book browser — working set ────────────────────────────────────

    _WS_FILE = '.working_set.json'
    _WS_EMPTY = '∅'   # display marker for an empty (unfilled) slot

    def _ws_json_path(self):
        return os.path.join(self.o_dir, self._WS_FILE)

    def _ws_slot_is_empty(self, e):
        return not e.get('path')

    def _load_working_set(self):
        """Load the manual working set from JSON.

        The set is built by hand and uncapped: each entry is a slot the user
        filled by shuffling (Tab). No auto-population. An empty set means a
        single empty slot to start from.
        """
        books = []
        path = self._ws_json_path()
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # Support old locked/unlocked format for migration
                if 'books' in data:
                    books = data['books']
                else:
                    books = data.get('locked', []) + data.get('unlocked', [])
                # Keep only slots whose file still exists (empty slots aren't saved).
                books = [e for e in books
                         if e.get('path')
                         and os.path.exists(os.path.join(self.o_dir, e['path']))]
                self._ws_browser_index = data.get('browser_index', 1)
            except Exception:
                pass
        if not books:
            books = [{'path': '', 'position': 0}]   # start from one empty slot
        self._ws_books = books
        self._ws_loaded = True

    def _save_working_set(self):
        try:
            # Persist only filled slots — empty slots are transient.
            saved = [e for e in self._ws_books if not self._ws_slot_is_empty(e)]
            with open(self._ws_json_path(), 'w', encoding='utf-8') as f:
                json.dump({
                    'books': saved,
                    'browser_index': self._ws_browser_index,
                }, f, indent=2)
        except Exception as e:
            print(f"⚠️ Could not save working set: {e}")

    def _ws_save_position(self):
        if not self.o_reader_file:
            return
        fname = os.path.basename(self.o_reader_file)
        idx = self.o_reader_ring.index
        for e in self._ws_books:
            if e['path'] == fname:
                e['position'] = idx
                break
        self._save_working_set()

    def _ws_fname_from_display(self, display):
        return display.strip()

    def _ws_slot_display(self, e):
        """What a slot shows in the F7 ring: clean title, or the empty marker."""
        if not e.get('path'):
            return self._WS_EMPTY
        return _clean_book_title(e['path'])

    def _ws_cur_slot(self):
        """Map the current F7 ring position to a _ws_books index.

        The ring is built as ['.', slot0, '.', slot1, ...], so the book at ring
        index r is slot (r-1)//2. Returns None if the ring sits on a separator
        or there are no slots.
        """
        if not self._ws_books:
            return None
        r = self.o_browser_ring.index
        if r <= 0 or r % 2 == 0:   # 0 or even index → a '.' separator
            return None
        i = (r - 1) // 2
        return i if 0 <= i < len(self._ws_books) else None

    def _ws_build_browser_ring(self, slot=None):
        """Rebuild the F7 ring from _ws_books. If slot is given, park the cursor
        on that slot; otherwise keep index 1 (first slot)."""
        entries = []
        for e in self._ws_books:
            entries.extend(['.', self._ws_slot_display(e)])
        self.o_browser_ring = LineRing(entries or ['.'])
        if slot is not None and self._ws_books:
            slot = max(0, min(slot, len(self._ws_books) - 1))
            self.o_browser_ring.index = 2 * slot + 1
        else:
            self.o_browser_ring.index = 1 if len(self.o_browser_ring.lines) > 1 else 0
        if self.o_browser_view:
            self.o_browser_view.ring = self.o_browser_ring
            self.o_browser_view._offset = 0.0

    def _ws_refresh_browser(self, slot):
        """Rebuild + repaint the F7 ring parked on slot, syncing the editor text."""
        self._ws_build_browser_ring(slot=slot)
        if self.o_browser_view:
            self.o_browser_view.editor.setText(self.o_browser_ring.current())
            self.o_browser_view.editor.setCursorPosition(0)
            self.o_browser_view.update()

    def _ws_tab_randomize(self):
        """TAB/* in F7: (re)fill the current slot with a random O/ book, never
        repeating a book already used by another slot."""
        slot = self._ws_cur_slot()
        if slot is None:
            return
        used = {e['path'] for e in self._ws_books if e.get('path')}
        candidates = [f for f in self._ws_all_o_files if f not in used]
        if not candidates:
            print("🔀 TAB: no unused O/ books left")
            return
        prev = self._ws_books[slot].get('path') or self._WS_EMPTY
        self._ws_books[slot] = {'path': random.choice(candidates), 'position': 0}
        self._save_working_set()
        self._ws_refresh_browser(slot)
        print(f"🔀 TAB: {prev} → {self.o_browser_ring.current()}")

    def _ws_add_slot(self):
        """Shift+Enter in F7: insert a new empty slot below the current one and
        move the cursor onto it (then Tab to fill)."""
        slot = self._ws_cur_slot()
        insert_at = (slot + 1) if slot is not None else len(self._ws_books)
        self._ws_books.insert(insert_at, {'path': '', 'position': 0})
        self._save_working_set()   # empty slot itself isn't persisted, but flush index
        self._ws_refresh_browser(insert_at)
        print(f"➕ F7: new empty slot at {insert_at}")

    def _ws_remove_slot(self):
        """Ctrl+Delete in F7: remove the current slot. Never go below one slot —
        if the set empties out, leave a single empty slot to build from again.

        The book currently open in the F6 reader can't be removed (silently):
        that way deleting all the others just leaves that one book loaded, with
        no stale ghost in F6.
        """
        slot = self._ws_cur_slot()
        if slot is None:
            return
        path = self._ws_books[slot].get('path')
        if path and self.o_reader_file and \
                os.path.basename(self.o_reader_file) == path:
            return
        del self._ws_books[slot]
        if not self._ws_books:
            self._ws_books = [{'path': '', 'position': 0}]
            slot = 0
        else:
            slot = min(slot, len(self._ws_books) - 1)
        self._save_working_set()
        self._ws_refresh_browser(slot)
        print(f"🗑️ F7: slot removed → {len(self._ws_books)} slot(s)")

    def _load_o_browser(self):
        if not self._ws_loaded:
            self._load_working_set()
        self._ws_build_browser_ring()

    def _ws_cache_path(self):
        return os.path.join(self.void_dir, '.o_files_cache.txt')

    def _ws_load_o_files_cache(self):
        """Load persisted O/ file list from disk into memory (instant)."""
        path = self._ws_cache_path()
        try:
            with open(path, 'r', encoding='utf-8') as f:
                self._ws_all_o_files = [l.rstrip('\n') for l in f if l.strip()]
            print(f"📚 O/ cache: {len(self._ws_all_o_files)} files loaded")
        except FileNotFoundError:
            pass  # first launch — rebuild will create it
        except Exception as e:
            print(f"⚠️ Could not read O/ cache: {e}")

    def _ws_rebuild_o_files_cache(self):
        """Background: re-scan O/ and overwrite the cache file. Catches new books."""
        def _scan():
            try:
                files = sorted(
                    f for f in os.listdir(self.o_dir)
                    if f.lower().endswith('.txt') and not f.startswith('.')
                )
                self._ws_all_o_files = files
                with open(self._ws_cache_path(), 'w', encoding='utf-8') as f:
                    f.write('\n'.join(files))
                print(f"📚 O/ cache rebuilt: {len(files)} files")
            except Exception as e:
                print(f"⚠️ O/ cache rebuild failed: {e}")
        threading.Thread(target=_scan, daemon=True).start()

    def _o_browser_show_editor(self):
        view = self.o_browser_view
        view.edit_mode = True
        center_y = view.height() // 2
        editor_width = view.width() - 100
        view.editor.setFixedWidth(editor_width)
        view.editor.move((view.width() - editor_width) // 2,
                         center_y - view.editor.sizeHint().height() // 2)
        cur = self.o_browser_ring.current()
        while cur == '.' and len(self.o_browser_ring.lines) > 1:
            self.o_browser_ring.move(1)
            cur = self.o_browser_ring.current()
        view.editor.setText(cur)
        view.editor.setCursorPosition(0)
        view.editor.show()
        view.editor.setFocus()
        view.update()

    def _o_browser_navigate(self, delta):
        self._tts_cut()
        self.o_browser_ring.move(delta)
        while self.o_browser_ring.current() == '.':
            self.o_browser_ring.move(delta)
        self.o_browser_view._offset = 0.0
        self.o_browser_view.editor.setText(self.o_browser_ring.current())
        self.o_browser_view.editor.setCursorPosition(0)
        self.o_browser_view.update()
        # Persist the highlighted book on every move (robust to watcher hard-kills).
        self._ws_browser_index = self.o_browser_ring.index
        self._save_working_set()

    def _o_browser_open(self):
        """Enter in F7: open the current slot's book in the F6 reader. An empty
        slot does nothing — shuffle (Tab) to fill it first."""
        slot = self._ws_cur_slot()
        if slot is None:
            return
        e = self._ws_books[slot]
        if self._ws_slot_is_empty(e):
            return
        fpath = os.path.join(self.o_dir, e['path'])
        if not os.path.exists(fpath):
            return
        self._load_o_reader(fpath)
        self.switch_to_view(5)

    # ── F6: O/ reader ─────────────────────────────────────────────────────────

    def _strip_gutenberg_boilerplate(self, raw):
        """Return raw text with Project Gutenberg header/footer removed."""
        import re
        start_pat = re.compile(
            r'\*{3}\s*START OF (?:THIS|THE) PROJECT GUTENBERG[^\n]*\n', re.IGNORECASE)
        end_pat = re.compile(
            r'\*{3}\s*END OF (?:THIS|THE) PROJECT GUTENBERG[^\n]*', re.IGNORECASE)
        m = start_pat.search(raw)
        if m:
            raw = raw[m.end():]
        m = end_pat.search(raw)
        if m:
            raw = raw[:m.start()]
        return raw.strip()

    def _reformat_raw_to_lines(self, raw):
        """Apply sentence-per-line reformat to a raw text string, return list of lines."""
        import re

        ABBREVS = {
            'mr', 'dr', 'mrs', 'ms', 'st', 'prof', 'jr', 'sr',
            'ud', 'vd', 'pág', 'núm', 'art', 'ed', 'vol', 'fig', 'cap',
            'e.g', 'i.e', 'etc', 'vs', 'cf', 'no',
        }

        def is_exception(text, dot_pos):
            if text[dot_pos:dot_pos+3] == '...':
                return True
            if dot_pos >= 2 and text[dot_pos-2:dot_pos] == '..':
                return True
            if (dot_pos > 0 and text[dot_pos-1].isdigit() and
                    dot_pos+1 < len(text) and text[dot_pos+1].isdigit()):
                return True
            if dot_pos > 0 and text[dot_pos-1].isupper():
                if dot_pos == 1 or text[dot_pos-2] in (' ', '\t'):
                    return True
            word_start = dot_pos - 1
            while word_start > 0 and text[word_start-1].isalpha():
                word_start -= 1
            word = text[word_start:dot_pos].lower()
            if word in ABBREVS:
                return True
            return False

        def split_sentences(text):
            sentences, current_start, i = [], 0, 0
            while i < len(text):
                ch = text[i]
                if ch in '.!?':
                    if ch == '.' and is_exception(text, i):
                        i += 1; continue
                    end = i + 1
                    while end < len(text) and text[end] in '.!?\'"»)':
                        end += 1
                    rest = text[end:]
                    if not rest.strip():
                        sentences.append(text[current_start:end].strip())
                        current_start = end; i = end; continue
                    m = re.match(r'\s+([A-ZÁÉÍÓÚÜÑ"«¿¡(])', rest)
                    if m:
                        sentences.append(text[current_start:end].strip())
                        current_start = end + m.end() - 1; i = current_start; continue
                i += 1
            tail = text[current_start:].strip()
            if tail:
                sentences.append(tail)
            return [s for s in sentences if s]

        paragraphs = re.split(r'\n\s*\n+', raw)
        result = ['.']
        for para_idx, para in enumerate(paragraphs):
            text = re.sub(r'\s+', ' ', para.strip())
            if not text or text == '.':
                continue
            if para_idx > 0:
                result.append('.')
            result.extend(split_sentences(text))
        return result

    def _load_o_reader(self, fpath):
        """Load an O/ book into the reader ring, applying Gutenberg strip + reformat."""
        try:
            with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                raw = f.read()
        except Exception as e:
            print(f"⚠️ Cannot open {fpath}: {e}")
            return
        raw = self._strip_gutenberg_boilerplate(raw)
        lines = self._reformat_raw_to_lines(raw)
        if not lines or lines[0] != '.':
            lines.insert(0, '.')
        self.o_reader_ring = LineRing(lines)
        self.o_reader_file = fpath
        # Restore saved position, or start at 1 (skip leading dot)
        fname = os.path.basename(fpath)
        saved_pos = next(
            (e.get('position', 1) for e in self._ws_books
             if e['path'] == fname), 1
        )
        self.o_reader_ring.index = min(max(saved_pos, 1), len(lines) - 1)
        if self.o_reader_view:
            self.o_reader_view.ring = self.o_reader_ring
            self.o_reader_view._offset = 0.0
        if self.transform_view:
            self.transform_view.ring = self.o_reader_ring
            self.transform_view._offset = 0.0
        print(f"📖 Opened: {os.path.basename(fpath)} ({len(lines)} lines)")

    def _reader_show_editor(self):
        view = self.o_reader_view
        view.edit_mode = True
        center_y = view.height() // 2
        editor_width = view.width() - 100
        view.editor.setFixedWidth(editor_width)
        view.editor.move((view.width() - editor_width) // 2,
                         center_y - view.editor.sizeHint().height() // 2)
        cur = self.o_reader_ring.current()
        view.editor.setText(cur if cur != '.' else '')
        view.editor.setReadOnly(True)
        view.editor.setCursorPosition(0)
        view.editor.show()
        view.editor.setFocus()
        view.update()

    def _reader_random_line(self):
        """* in F6: jump to a random non-dot line in the current O/ book."""
        candidates = [i for i, l in enumerate(self.o_reader_ring.lines)
                      if l not in ('.', '')]
        if not candidates:
            return
        self.o_reader_ring.index = random.choice(candidates)
        self.o_reader_view._offset = 0.0
        self.o_reader_view.editor.setText(self.o_reader_ring.current())
        self.o_reader_view.editor.setCursorPosition(0)
        self.o_reader_view.update()

    def _reader_navigate(self, delta):
        self._tts_cut()
        self.o_reader_ring.move(delta)
        while self.o_reader_ring.current() == '.':
            self.o_reader_ring.move(delta)
        self.o_reader_view._offset = 0.0
        cur = self.o_reader_ring.current()
        self.o_reader_view.editor.setText(cur)
        self.o_reader_view.editor.setCursorPosition(0)
        self.o_reader_view.update()
        # Persist on every move — proto's watcher can kill the process without a
        # clean closeEvent, so saving only on view-switch/close loses the position.
        self._ws_save_position()

    def _reader_fork_to_transform(self):
        """Fork current reader line into F5 transform view."""
        cur = self.o_reader_ring.current()
        if not cur or cur == '.':
            return
        self.o_reader_line_idx = self.o_reader_ring.index
        self.switch_to_view(4)

    # ── F5: Transform ─────────────────────────────────────────────────────────

    def _transform_show_editor(self):
        view = self.transform_view
        view.edit_mode = True
        center_y = view.height() // 2
        editor_width = view.width() - 100
        view.editor.setFixedWidth(editor_width)
        view.editor.move((view.width() - editor_width) // 2,
                         center_y - view.editor.sizeHint().height() // 2)
        cur = self.o_reader_ring.current()
        view.editor.setReadOnly(False)
        view.editor.setText(cur if cur != '.' else '')
        view.editor.setCursorPosition(len(view.editor.text()))
        view.editor.show()
        view.editor.setFocus()
        view.update()

    def _transform_navigate(self, delta):
        """Advance the reader position and load next line into transform."""
        self.o_reader_ring.move(delta)
        while self.o_reader_ring.current() == '.':
            self.o_reader_ring.move(delta)
        self.transform_view._offset = 0.0
        cur = self.o_reader_ring.current()
        self.transform_view.editor.setText(cur)
        self.transform_view.editor.setCursorPosition(len(cur))
        self.transform_view.update()

    def _transform_confirm(self):
        """Append edited line to active I/ doc, advance to next reader line."""
        view = self.transform_view
        new_text = view.editor.text().strip()
        if not new_text:
            return
        insert_pos = self.line_ring.index + 1
        self.line_ring.lines.insert(insert_pos, new_text)
        self.line_ring.index = insert_pos
        self.auto_save_circular()
        # Advance reader to next non-dot line
        self.o_reader_ring.move(1)
        while self.o_reader_ring.current() == '.':
            self.o_reader_ring.move(1)
        self.transform_view._offset = 0.0
        self.transform_view.update()
        cur = self.o_reader_ring.current()
        view.editor.setText(cur)
        view.editor.setCursorPosition(len(cur))
        view.editor.setFocus()
        print(f"✅ Transform→Doc[{insert_pos}]: '{new_text}'")

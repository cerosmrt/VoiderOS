import os


class F5TriageMixin:
    """F5 paragraph triage: navigate paragraphs on the left, books on the right.

    State:
        _triage_paragraphs  — list of paragraph line-lists (no dots)
        _triage_para_idx    — index into _triage_paragraphs, or -1 for the ø mark
    The book ring (right panel) is the shared self.book_ring from F3.
    """

    def _triage_enter(self):
        """Load paragraphs from the current line_ring; jump to the active paragraph."""
        dot_indices, paragraphs = self._paragraphs_from_ring()
        lines = self.line_ring.lines
        cur = self.line_ring.index

        non_empty = [(k, p) for k, p in enumerate(paragraphs) if p]
        self._triage_paragraphs = [p for _, p in non_empty]

        if not self._triage_paragraphs:
            self._triage_para_idx = -1
            self._triage_refresh()
            return

        # If ring index is on a content line, find its paragraph.
        # If on a dot line, default to para 0.
        self._triage_para_idx = 0
        if dot_indices and lines and lines[cur] != '.':
            for j, (k, p) in enumerate(non_empty):
                dot_pos = dot_indices[k]
                if dot_pos + 1 <= cur <= dot_pos + len(p):
                    self._triage_para_idx = j
                    break

        self._triage_refresh()

    def _triage_refresh(self):
        """Sync the triage_view widget with current state."""
        view = getattr(self, 'triage_view', None)
        if view is None:
            return

        view.set_para(self._triage_paragraphs, self._triage_para_idx)

        ring = self.book_ring
        non_dot = [(i, name) for i, name in enumerate(ring.lines) if name != '.']
        cur_display = next((j for j, (i, _) in enumerate(non_dot) if i == ring.index), 0)
        book_names = [name for _, name in non_dot]
        view.set_book(book_names, cur_display)

    # ── Paragraph navigation (Up / Down) ─────────────────────────────────────

    def _triage_next_para(self):
        n = len(self._triage_paragraphs)
        if n == 0:
            return
        if self._triage_para_idx == n - 1:   # last → ø
            self._triage_para_idx = -1
        elif self._triage_para_idx == -1:    # ø → first
            self._triage_para_idx = 0
        else:
            self._triage_para_idx += 1
        self._triage_refresh()

    def _triage_prev_para(self):
        n = len(self._triage_paragraphs)
        if n == 0:
            return
        if self._triage_para_idx == 0:       # first → ø
            self._triage_para_idx = -1
        elif self._triage_para_idx == -1:    # ø → last
            self._triage_para_idx = n - 1
        else:
            self._triage_para_idx -= 1
        self._triage_refresh()

    # ── Book navigation (Shift+Up / Shift+Down) ───────────────────────────────

    def _triage_next_book(self):
        ring = self.book_ring
        n = len(ring.lines)
        for _ in range(n):
            ring.move(1)
            if ring.current() != '.':
                break
        self._triage_refresh()

    def _triage_prev_book(self):
        ring = self.book_ring
        n = len(ring.lines)
        for _ in range(n):
            ring.move(-1)
            if ring.current() != '.':
                break
        self._triage_refresh()

    # ── Dispatch (→ Right arrow) ──────────────────────────────────────────────

    def _triage_dispatch(self):
        """Append current paragraph to the centered book, remove from source."""
        if self._triage_para_idx < 0:
            return
        if not self._triage_paragraphs:
            return
        if self.book_ring.current() == '.':
            return

        fname = self._library_current_fname()
        if not fname:
            return
        fpath = self._library_path_cache.get(fname)
        if not fpath or not os.path.exists(fpath):
            return

        para = self._triage_paragraphs[self._triage_para_idx]

        try:
            with open(fpath, 'a', encoding='utf-8') as f:
                f.write('.\n')
                f.write('\n'.join(para) + '\n')
        except Exception as e:
            print(f'⚠️ Triage dispatch error: {e}')
            return

        self._triage_paragraphs.pop(self._triage_para_idx)
        self._rebuild_ring_from_paragraphs(self._triage_paragraphs)

        n = len(self._triage_paragraphs)
        if n > 0:
            self._triage_para_idx = min(self._triage_para_idx, n - 1)
        else:
            self._triage_para_idx = -1

        self.auto_save_circular()
        print(f'→ {len(para)} line(s) → {fname}')
        self._triage_refresh()

    # ── Reorder (Alt+Up / Alt+Down) ───────────────────────────────────────────

    def _triage_swap_up(self):
        idx = self._triage_para_idx
        if idx <= 0:
            return
        p = self._triage_paragraphs
        p[idx], p[idx - 1] = p[idx - 1], p[idx]
        self._triage_para_idx = idx - 1
        self._rebuild_ring_from_paragraphs(p)
        self.auto_save_circular()
        self._triage_refresh()

    def _triage_swap_down(self):
        idx = self._triage_para_idx
        if idx < 0:
            return
        p = self._triage_paragraphs
        if idx >= len(p) - 1:
            return
        p[idx], p[idx + 1] = p[idx + 1], p[idx]
        self._triage_para_idx = idx + 1
        self._rebuild_ring_from_paragraphs(p)
        self.auto_save_circular()
        self._triage_refresh()

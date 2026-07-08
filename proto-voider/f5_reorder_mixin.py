import os


class F5ReorderMixin:
    """F5 — linear, read-only paragraph reorder over the active file.

    Replaces the old triage/dispatch (that job now belongs to the '/name' slash
    split/merge). F5 shows the active file (usually a merged doc) as paragraphs,
    top-to-bottom (NOT circular), with the current paragraph highlighted. '/name'
    lines are shown as fixed chapter fences: a paragraph swapped past one crosses
    into the adjacent chapter; the fence itself never moves.

    Alt+Up/Down swaps the current paragraph with its neighbour (no wrap at the
    ends). Enter jumps to F2 on that paragraph; entering F5 from F2 lands on the
    paragraph containing F2's current line. Reorders persist via the normal atomic
    save, so Ctrl+Z (content undo) and a later split both see the new order.

    Shares self.line_ring with F2 (same active file), so the two stay in sync.
    Cursor: self._f5_para_idx is the 0-based ordinal of the current paragraph.
    """

    # ── Tokenise / flatten ────────────────────────────────────────────────────

    def _f5_tokens(self, lines):
        """Lines → ordered tokens: ['para', [lines]] | ['mark', '/name'] |
        ['sep', '.']. Blank lines are dropped; a run of text lines is one para."""
        toks, cur = [], []
        for raw in lines:
            s = raw.strip()
            if s.startswith('/'):
                if cur:
                    toks.append(['para', cur]); cur = []
                toks.append(['mark', raw])
            elif s == '.':
                if cur:
                    toks.append(['para', cur]); cur = []
                toks.append(['sep', '.'])
            elif s:
                cur.append(raw)
        if cur:
            toks.append(['para', cur])
        return toks

    def _f5_flatten(self, toks):
        """Tokens → lines (inverse of _f5_tokens; separators/fences kept in place)."""
        lines = []
        for kind, val in toks:
            if kind == 'para':
                lines.extend(val)
            else:
                lines.append(val)
        return lines

    def _f5_para_positions(self, toks):
        """Token indices that are paragraphs, in order (their ordinal is the list
        position)."""
        return [i for i, t in enumerate(toks) if t[0] == 'para']

    def _f5_para_count(self):
        return len(self._f5_para_positions(self._f5_tokens(self.line_ring.lines)))

    # ── Navigation (linear, clamped — no wrap) ────────────────────────────────

    def _f5_next_para(self):
        n = self._f5_para_count()
        if self._f5_para_idx < n - 1:
            self._f5_para_idx += 1
            self._f5_refresh()

    def _f5_prev_para(self):
        if self._f5_para_idx > 0:
            self._f5_para_idx -= 1
            self._f5_refresh()

    # ── Reorder (swap with neighbour; fences are crossed, not moved) ───────────

    def _f5_swap(self, direction):
        """Swap the current paragraph with the one `direction` away (+1 down, -1
        up). Separators and '/name' fences keep their positions, so a paragraph
        pushed past a fence lands in the adjacent chapter. Linear: edges no-op."""
        toks = self._f5_tokens(self.line_ring.lines)
        paras = self._f5_para_positions(toks)
        n = len(paras)
        i = self._f5_para_idx
        j = i + direction
        if not (0 <= i < n and 0 <= j < n):
            return
        a, b = paras[i], paras[j]
        toks[a], toks[b] = toks[b], toks[a]
        self.line_ring.lines = self._f5_flatten(toks)
        if self.line_ring.index >= len(self.line_ring.lines):
            self.line_ring.index = max(0, len(self.line_ring.lines) - 1)
        self._f5_para_idx = j                 # cursor follows the moved paragraph
        self.auto_save_circular()             # atomic save + content-undo capture
        self._f5_refresh()

    def _f5_swap_up(self):
        self._f5_swap(-1)

    def _f5_swap_down(self):
        self._f5_swap(1)

    # ── F2 ↔ F5 position mapping ──────────────────────────────────────────────

    def _f5_para_at_line(self, lines, line_idx):
        """Ordinal of the paragraph containing lines[line_idx]. A '.'/'/name'/blank
        line maps to the paragraph that precedes it (0 if none)."""
        if not lines:
            return 0
        line_idx = max(0, min(line_idx, len(lines) - 1))
        ordinal, last, in_para = -1, 0, False
        for i, raw in enumerate(lines):
            s = raw.strip()
            is_text = False
            if s.startswith('/') or s == '.':
                in_para = False
            elif s:
                if not in_para:
                    ordinal += 1
                    in_para = True
                last = ordinal
                is_text = True
            if i == line_idx:
                return max(0, ordinal if is_text else last)
        return max(0, last)

    def _f5_line_of_para(self, ordinal):
        """First line index of the paragraph with this ordinal (0 if not found)."""
        ord_, in_para = -1, False
        for i, raw in enumerate(self.line_ring.lines):
            s = raw.strip()
            if s.startswith('/') or s == '.':
                in_para = False
            elif s:
                if not in_para:
                    ord_ += 1
                    in_para = True
                    if ord_ == ordinal:
                        return i
        return 0

    def _f5_enter(self):
        """On entering F5: land on the paragraph holding F2's current line."""
        self._f5_para_idx = self._f5_para_at_line(self.line_ring.lines,
                                                  self.line_ring.index)
        n = self._f5_para_count()
        if n:
            self._f5_para_idx = max(0, min(self._f5_para_idx, n - 1))
        else:
            self._f5_para_idx = 0
        self._f5_refresh()

    def _f5_enter_to_f2(self):
        """Enter in F5: jump to F2 positioned on the current paragraph's first line."""
        self.line_ring.index = self._f5_line_of_para(self._f5_para_idx)
        self.switch_to_view(1)

    # ── Send a paragraph to another chapter (F5 → '>' → F3 → Enter) ─────────────

    def _f5_begin_send(self):
        """Right arrow in F5: remember the current paragraph and open F3 to pick a
        destination chapter (send mode). Esc cancels, Enter sends."""
        if self._f5_para_count() == 0:
            return
        self._f5_send_mode = True
        self._f5_send_para = self._f5_para_idx
        self._f5_send_source = self.current_file_path
        self.switch_to_view(2)
        if self.book_view:
            self.book_view.send_marker = True
            self.book_view.update()

    def _f5_cancel_send(self):
        """Esc in F3 send mode: back to F5 on the same paragraph, nothing moved."""
        self._f5_send_mode = False
        if self.book_view:
            self.book_view.send_marker = False
        self.switch_to_view(4)

    def _f5_collapse_dots(self, lines):
        out = []
        for l in lines:
            if l.strip() == '.' and (not out or out[-1].strip() == '.'):
                continue                      # drop leading/duplicate separators
            out.append(l)
        while out and out[-1].strip() == '.':
            out.pop()                         # drop trailing separator
        return out

    def _f5_confirm_send(self):
        """Enter in F3 send mode: MOVE the remembered paragraph out of the source
        file and append it to the highlighted chapter (source '.' para). Snapshot +
        one undo step. Returns to F5 on the paragraph that now takes its place."""
        if not getattr(self, '_f5_send_mode', False):
            return
        if self.book_ring.current() == '.' or self._book_is_portal():
            return                            # can't send to a separator / portal
        target_fname = self._library_current_fname()
        if not target_fname:
            return
        target_path = self._library_path_cache.get(target_fname)
        src = self._f5_send_source
        if not target_path or os.path.abspath(target_path) == os.path.abspath(src):
            return                            # invalid / same file: ignore

        toks = self._f5_tokens(self.line_ring.lines)
        paras = self._f5_para_positions(toks)
        i = self._f5_send_para
        if not (0 <= i < len(paras)):
            self._f5_cancel_send()
            return
        para_lines = list(toks[paras[i]][1])
        del toks[paras[i]]
        new_source = self._f5_collapse_dots(self._f5_flatten(toks)) or ['.']

        self._undo_begin()
        self._git_snapshot_void('f5-send')
        try:
            with open(target_path, 'r', encoding='utf-8', errors='replace') as f:
                existing = [l.rstrip('\n') for l in f]
        except FileNotFoundError:
            existing = []
        while existing and not existing[-1].strip():
            existing.pop()
        combined = (existing + ['.'] + para_lines) if existing else para_lines
        self._atomic_write_lines(target_path, combined)
        self.line_ring.lines = new_source
        if self.line_ring.index >= len(self.line_ring.lines):
            self.line_ring.index = max(0, len(self.line_ring.lines) - 1)
        self.auto_save_circular()             # persist the shrunk source
        self._undo_commit(key=('f5send', target_fname))

        self._f5_send_mode = False
        if self.book_view:
            self.book_view.send_marker = False
        self.switch_to_view(4)
        n = self._f5_para_count()
        self._f5_para_idx = max(0, min(i, n - 1)) if n else 0
        self._f5_refresh()

    # ── View state ────────────────────────────────────────────────────────────

    def _f5_units(self):
        """Ordered display units for the view: paragraphs (with ordinal + prose)
        and '/name' fences. Separators are implicit (paragraphs are spaced)."""
        units, ordinal = [], -1
        for kind, val in self._f5_tokens(self.line_ring.lines):
            if kind == 'para':
                ordinal += 1
                units.append({'kind': 'para', 'ordinal': ordinal,
                              'text': ' '.join(val)})
            elif kind == 'mark':
                units.append({'kind': 'mark', 'name': val.strip()[1:].strip()})
        return units

    def _f5_refresh(self):
        view = getattr(self, 'reorder_view', None)
        if view is not None:
            view.set_state(self._f5_units(), self._f5_para_idx)

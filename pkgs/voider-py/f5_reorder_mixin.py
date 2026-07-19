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

    # ── Send a paragraph to a chapter via the in-view picker (F5 → '>' → pick) ──

    def _f5_collapse_dots(self, lines):
        out = []
        for l in lines:
            if l.strip() == '.' and (not out or out[-1].strip() == '.'):
                continue                      # drop leading/duplicate separators
            out.append(l)
        while out and out[-1].strip() == '.':
            out.pop()                         # drop trailing separator
        return out

    def _f5_move_current_to(self, target_path):
        """MOVE the current paragraph out of the active file and append it to
        target_path (existing '.' para). One snapshot + one undo step. Leaves the
        cursor on the paragraph that now takes its place. Returns True on success."""
        toks = self._f5_tokens(self.line_ring.lines)
        paras = self._f5_para_positions(toks)
        i = self._f5_para_idx
        if not (0 <= i < len(paras)):
            return False
        if os.path.abspath(target_path) == os.path.abspath(self.current_file_path):
            return False                      # same file: ignore
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
        self._undo_commit(key=('f5send', os.path.basename(target_path)))

        n = self._f5_para_count()
        self._f5_para_idx = max(0, min(i, n - 1)) if n else 0
        return True

    # ── In-view chapter picker (opens on the right of F5) ───────────────────────

    def _f5_open_picker(self):
        """Right in F5: open the in-view type-to-filter chapter picker."""
        if self._f5_para_count() == 0:
            return
        self._f5_picker_open = True
        self._f5_pick_filter = ''
        self._f5_pick_match_idx = 0
        self._f5_refresh()

    def _f5_close_picker(self):
        self._f5_picker_open = False
        self._f5_refresh()

    def _f5_pick_matches(self):
        """[(fname, display)] of chapters whose name contains the filter — never the
        separators, the '0' portal, or the source file itself."""
        flt = self._f5_pick_filter.strip().lower()
        src = os.path.basename(self.current_file_path or '')
        out = []
        for fname in self._library_lines:
            if fname in ('.', '0.txt') or fname == src:
                continue
            display = os.path.splitext(fname)[0]
            if flt in display.lower():
                out.append((fname, display))
        return out

    def _f5_pick_target(self):
        """Resolve the destination: an existing match, else create-new from a
        non-empty filter, else None."""
        matches = self._f5_pick_matches()
        if matches:
            fname, display = matches[self._f5_pick_match_idx % len(matches)]
            return {'fname': fname, 'display': display,
                    'path': self._library_path_cache.get(fname), 'is_new': False}
        flt = self._f5_pick_filter.strip()
        if flt:
            fname = flt + '.txt'
            return {'fname': fname, 'display': flt,
                    'path': os.path.join(self.void_dir, 'I', fname), 'is_new': True}
        return None

    def _f5_pick_filter_add(self, ch):
        self._f5_pick_filter += ch
        self._f5_pick_match_idx = 0
        self._f5_refresh()

    def _f5_pick_filter_backspace(self):
        if self._f5_pick_filter:
            self._f5_pick_filter = self._f5_pick_filter[:-1]
            self._f5_pick_match_idx = 0
            self._f5_refresh()

    def _f5_pick_cycle(self, delta):
        matches = self._f5_pick_matches()
        if matches:
            self._f5_pick_match_idx = (self._f5_pick_match_idx + delta) % len(matches)
            self._f5_refresh()

    def _f5_pick_confirm(self):
        """Enter/→ in the picker: send the current paragraph to the resolved target
        (creating the chapter first if the typed name is new), then close + advance."""
        if not getattr(self, '_f5_picker_open', False):
            return
        target = self._f5_pick_target()
        if not target or not target['path']:
            return
        if target['is_new']:                  # create the new chapter first
            path = target['path']
            if not os.path.exists(path):
                open(path, 'w', encoding='utf-8').close()
            if target['fname'] not in self._library_lines:
                ins = self.book_ring.index
                if not (0 <= ins < len(self._library_lines)):
                    ins = len(self._library_lines)
                self._library_lines.insert(ins, target['fname'])
                self.book_ring.lines.insert(ins, target['display'])
                self._library_path_cache[target['fname']] = path
                self._save_library()
        self._f5_move_current_to(target['path'])
        self._f5_close_picker()

    # ── Fixed title header (chapter the current paragraph sits under) ──────────

    def _f5_current_title(self):
        """Title pinned at the top of F5: the '/name' fence the current paragraph
        sits under, or the active file's name (no extension) if it sits under
        none. In the usual single-chapter file this is always the file name."""
        toks = self._f5_tokens(self.line_ring.lines)
        ordinal, mark = -1, None
        for kind, val in toks:
            if kind == 'mark':
                mark = val.strip()[1:].strip()
            elif kind == 'para':
                ordinal += 1
                if ordinal == self._f5_para_idx:
                    if mark:
                        return mark
                    break
        base = os.path.basename(getattr(self, 'current_file_path', '') or '')
        return os.path.splitext(base)[0]

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
        if view is None:
            return
        view.set_state(self._f5_units(), self._f5_para_idx, self._f5_current_title())
        if getattr(self, '_f5_picker_open', False):
            matches = self._f5_pick_matches()
            target = self._f5_pick_target()
            view.set_picker_state(True, self._f5_pick_filter,
                                  [d for _, d in matches], self._f5_pick_match_idx,
                                  bool(target and target.get('is_new')),
                                  target['display'] if target else '')
        else:
            view.set_picker_state(False, '', [], 0, False, '')

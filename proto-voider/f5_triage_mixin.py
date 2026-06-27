import os
import subprocess
import datetime


class F5TriageMixin:
    """F5 paragraph triage.

    Left panel: the paragraphs of the scratch 0.txt (self.f1_file), shown as prose.
    Right panel: a type-to-filter chapter picker. Typing narrows the library; the
    highlighted match is the dispatch target. If the typed name matches no existing
    chapter, → creates <name>.txt and dispatches into it.

    Source is ALWAYS 0.txt — independent of the F2 active file. Dispatch:
      1. git-snapshots I/ once per F5 session (safety),
      2. appends the paragraph to the target chapter atomically (+ IPC),
      3. removes it from 0.txt and writes 0.txt atomically (+ IPC),
      4. keeps the F1/F2 ring in sync (and in range) when it points at 0.txt.

    State:
        _triage_paragraphs  — list of paragraph line-lists (no dots)
        _triage_para_idx    — index into _triage_paragraphs, or -1 for the ø mark
        _triage_filter      — current target filter string
        _triage_match_idx   — index into the filtered match list
        _triage_snapshotted — True once a snapshot was taken this session
    """

    # ── Enter / parse ─────────────────────────────────────────────────────────

    def _triage_enter(self):
        """Load paragraphs from 0.txt on disk and reset session state."""
        self._triage_paragraphs = self._triage_parse_file(self.f1_file)
        self._triage_para_idx = 0 if self._triage_paragraphs else -1
        self._triage_filter = ''
        self._triage_match_idx = 0
        self._triage_snapshotted = False
        self._triage_refresh()

    def _triage_parse_lines(self, lines):
        """Split lines on '.' separators into paragraphs (no dots, no empty lines)."""
        paras, cur = [], []
        for raw in lines:
            if raw.strip() == '.':
                if cur:
                    paras.append(cur); cur = []
            elif raw.strip():
                cur.append(raw)
        if cur:
            paras.append(cur)
        return paras

    def _triage_parse_file(self, path):
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                lines = [l.rstrip('\n') for l in f]
        except FileNotFoundError:
            return []
        except Exception as e:
            print(f'⚠️ Triage read error: {e}')
            return []
        return self._triage_parse_lines(lines)

    def _triage_save(self):
        """Atomically write the remaining paragraphs back to 0.txt (+ IPC),
        and keep the F1/F2 ring consistent if it is showing 0.txt."""
        lines = []
        for para in self._triage_paragraphs:
            lines.append('.')
            lines.extend(para)
        if not lines:
            lines = ['.']
        self._atomic_write_lines(self.f1_file, lines)  # notifies IPC
        if getattr(self, 'current_file_path', None) == self.f1_file:
            ring = self.line_ring
            ring.lines = list(lines)
            if ring.index >= len(ring.lines):
                ring.index = len(ring.lines) - 1
            if ring.index < 0:
                ring.index = 0

    # ── Paragraph navigation (Up / Down) ─────────────────────────────────────

    def _triage_next_para(self):
        n = len(self._triage_paragraphs)
        if n == 0:
            return
        if self._triage_para_idx == n - 1:
            self._triage_para_idx = -1
        elif self._triage_para_idx == -1:
            self._triage_para_idx = 0
        else:
            self._triage_para_idx += 1
        self._triage_refresh()

    def _triage_prev_para(self):
        n = len(self._triage_paragraphs)
        if n == 0:
            return
        if self._triage_para_idx == 0:
            self._triage_para_idx = -1
        elif self._triage_para_idx == -1:
            self._triage_para_idx = n - 1
        else:
            self._triage_para_idx -= 1
        self._triage_refresh()

    # ── Target filter ─────────────────────────────────────────────────────────

    def _triage_matches(self):
        """Return [(fname, display), ...] of chapters whose name contains the filter.
        The scratch portal ('0.txt') and separators ('.') are never targets."""
        flt = self._triage_filter.strip().lower()
        out = []
        for fname in self._library_lines:
            if fname == '.' or fname == '0.txt':
                continue
            display = os.path.splitext(fname)[0]
            if flt in display.lower():
                out.append((fname, display))
        return out

    def _triage_target(self):
        """Resolve the current dispatch target.
        existing match → that chapter; non-empty filter with no match → create-new;
        empty filter with no books → None."""
        matches = self._triage_matches()
        if matches:
            fname, display = matches[self._triage_match_idx % len(matches)]
            return {'fname': fname, 'display': display,
                    'path': self._library_path_cache.get(fname), 'is_new': False}
        flt = self._triage_filter.strip()
        if flt:
            fname = flt + '.txt'
            return {'fname': fname, 'display': flt,
                    'path': os.path.join(self.void_dir, 'I', fname), 'is_new': True}
        return None

    def _triage_filter_add(self, ch):
        self._triage_filter += ch
        self._triage_match_idx = 0
        self._triage_refresh()

    def _triage_filter_backspace(self):
        if self._triage_filter:
            self._triage_filter = self._triage_filter[:-1]
            self._triage_match_idx = 0
            self._triage_refresh()

    def _triage_cycle_match(self, delta):
        matches = self._triage_matches()
        if not matches:
            return
        self._triage_match_idx = (self._triage_match_idx + delta) % len(matches)
        self._triage_refresh()

    # ── Safety ────────────────────────────────────────────────────────────────

    def _triage_snapshot_once(self):
        """Git-snapshot I/ once per F5 session, before the first write to /void."""
        if getattr(self, '_triage_snapshotted', False):
            return
        self._triage_snapshotted = True
        ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        try:
            subprocess.run(['git', '-C', self.void_dir, 'add', '-A', 'I/'],
                           capture_output=True, timeout=10)
            subprocess.run(['git', '-C', self.void_dir, 'commit',
                            '-m', f'triage snapshot {ts}'],
                           capture_output=True, timeout=10)
        except Exception as e:
            print(f'⚠️ Triage snapshot failed: {e}')

    # ── Create new chapter (Enter) ────────────────────────────────────────────

    def _triage_create(self):
        """Enter: create an empty chapter file named after the filter. No paragraph
        is moved — this just adds a destination you can later dispatch into."""
        name = self._triage_filter.strip()
        if not name:
            return
        fname = name + '.txt'
        if fname.lower() in {l.lower() for l in self._library_lines}:
            return  # already exists — nothing to create
        fpath = os.path.join(self.void_dir, 'I', fname)
        self._triage_snapshot_once()
        try:
            if not os.path.exists(fpath):
                open(fpath, 'w', encoding='utf-8').close()
        except Exception as e:
            print(f'⚠️ Triage create error: {e}')
            return
        insert_pos = self.book_ring.index + 1
        self._library_lines.insert(insert_pos, fname)
        self.book_ring.lines.insert(insert_pos, name)
        self._library_path_cache[fname] = fpath
        self._save_library()
        self._triage_match_idx = 0  # new chapter is now the only match
        print(f'＋ created {fname}')
        self._triage_refresh()

    # ── Dispatch (→) ──────────────────────────────────────────────────────────

    def _triage_dispatch(self):
        """→ : send the current paragraph to the highlighted EXISTING chapter.
        Never creates a file (that is Enter's job). No-op if the target is new."""
        if self._triage_para_idx < 0 or not self._triage_paragraphs:
            return
        target = self._triage_target()
        if not target or target['is_new']:
            return

        self._triage_snapshot_once()

        para = self._triage_paragraphs[self._triage_para_idx]
        fpath = target['path']

        # Append paragraph to the target chapter, atomically (+ IPC).
        try:
            with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                existing = [l.rstrip('\n') for l in f]
        except FileNotFoundError:
            existing = []
        while existing and existing[-1].strip() == '':
            existing.pop()
        self._atomic_write_lines(fpath, existing + ['.'] + list(para))

        # Remove from source and persist 0.txt. Keep the filter so consecutive
        # paragraphs can be sent to the same chapter.
        self._triage_paragraphs.pop(self._triage_para_idx)
        n = len(self._triage_paragraphs)
        self._triage_para_idx = min(self._triage_para_idx, n - 1) if n else -1
        self._triage_save()

        print(f'→ {len(para)} line(s) → {target["display"]}')
        self._triage_refresh()

    # ── Reorder (Alt+Up / Alt+Down) ───────────────────────────────────────────

    def _triage_swap_up(self):
        idx = self._triage_para_idx
        if idx <= 0:
            return
        p = self._triage_paragraphs
        p[idx], p[idx - 1] = p[idx - 1], p[idx]
        self._triage_para_idx = idx - 1
        self._triage_save()
        self._triage_refresh()

    def _triage_swap_down(self):
        idx = self._triage_para_idx
        if idx < 0 or idx >= len(self._triage_paragraphs) - 1:
            return
        p = self._triage_paragraphs
        p[idx], p[idx + 1] = p[idx + 1], p[idx]
        self._triage_para_idx = idx + 1
        self._triage_save()
        self._triage_refresh()

    # ── View sync ─────────────────────────────────────────────────────────────

    def _triage_refresh(self):
        view = getattr(self, 'triage_view', None)
        if view is None:
            return
        view.set_para(self._triage_paragraphs, self._triage_para_idx,
                      os.path.basename(self.f1_file))
        matches = self._triage_matches()
        target = self._triage_target()
        view.set_target(self._triage_filter,
                        [d for _, d in matches],
                        self._triage_match_idx % len(matches) if matches else 0,
                        bool(target and target['is_new']),
                        target['display'] if target else '')

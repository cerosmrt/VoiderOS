"""F4 and F5 must open at the user's current position, not the top.

Covers the line-index -> paragraph-ordinal mapping shared by both, the F4
reading-HTML anchors, and F5 sourcing the current file at the current paragraph.
"""
import os
import types
from unittest.mock import MagicMock

import pytest

from line_ring import LineRing
from helpers import make_ring_app


# ── shared line -> paragraph ordinal helper ───────────────────────────────────

class TestParaOrdinal:

    def _app(self):
        from new_interface import FullscreenCircleApp
        app = make_ring_app(['.'])
        app._para_ordinal_at = types.MethodType(
            FullscreenCircleApp._para_ordinal_at, app)
        return app

    def test_first_paragraph(self):
        app = self._app()
        lines = ['.', 'a', 'b', '.', 'c', '.', 'd']
        assert app._para_ordinal_at(lines, 1) == 0   # 'a'
        assert app._para_ordinal_at(lines, 2) == 0   # 'b'

    def test_middle_paragraph(self):
        app = self._app()
        lines = ['.', 'a', 'b', '.', 'c', '.', 'd']
        assert app._para_ordinal_at(lines, 4) == 1   # 'c'
        assert app._para_ordinal_at(lines, 6) == 2   # 'd'

    def test_on_separator_maps_to_preceding_paragraph(self):
        app = self._app()
        lines = ['.', 'a', '.', 'b']
        assert app._para_ordinal_at(lines, 2) == 0   # the '.' after 'a'

    def test_leading_separator_maps_to_zero(self):
        app = self._app()
        lines = ['.', 'a', '.', 'b']
        assert app._para_ordinal_at(lines, 0) == 0

    def test_empty_lines_ignored(self):
        app = self._app()
        lines = ['.', 'a', '', 'b', '.', 'c']
        assert app._para_ordinal_at(lines, 5) == 1   # 'c' is 2nd paragraph


# ── F4 reading anchors ────────────────────────────────────────────────────────

class TestReadingAnchors:

    def _app(self):
        from new_interface import FullscreenCircleApp
        app = make_ring_app(['.'])
        for m in ('_build_reading_html',):
            app.__dict__[m] = types.MethodType(getattr(FullscreenCircleApp, m), app)
        return app

    def test_each_paragraph_has_anchor(self):
        app = self._app()
        html = app._build_reading_html(['a', '.', 'b', '.', 'c'], 'T')
        assert 'name="vpara0"' in html
        assert 'name="vpara1"' in html
        assert 'name="vpara2"' in html


# ── F5 sources the current file at the current paragraph ──────────────────────

def _triage_app(tmp_path, current_lines, source_name='0.txt', library=None):
    from new_interface import FullscreenCircleApp
    app = make_ring_app(['.'])
    void = tmp_path
    (void / 'I').mkdir(exist_ok=True)
    app.void_dir = str(void)
    app.f1_file = str(void / 'I' / '0.txt')
    open(app.f1_file, 'w').close()

    src_path = str(void / 'I' / source_name)
    with open(src_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(current_lines) + ('\n' if current_lines else ''))
    app.current_file_path = src_path
    app.line_ring = LineRing(list(current_lines) or ['.'])

    library = library or []
    app._library_lines = []
    app._library_path_cache = {}
    ring_names = []
    for name in library:
        fn = name + '.txt'
        app._library_lines.append(fn)
        ring_names.append(name)
        p = str(void / 'I' / fn)
        open(p, 'w').close()
        app._library_path_cache[fn] = p
    app.book_ring = LineRing(ring_names or ['.'])

    app._ipc = MagicMock()
    app.triage_view = MagicMock()
    app.switch_to_view = MagicMock()
    app._show_lock_screen = MagicMock()

    for name in ('_triage_enter', '_triage_refresh', '_triage_parse_file',
                 '_triage_parse_lines', '_triage_save', '_triage_matches',
                 '_triage_target', '_triage_dispatch', '_para_ordinal_at',
                 '_atomic_write_lines', '_triage_next_para', '_triage_prev_para',
                 '_triage_snapshot_once'):
        if hasattr(FullscreenCircleApp, name):
            setattr(app, name, types.MethodType(getattr(FullscreenCircleApp, name), app))
    return app


def _read_paras(path):
    with open(path, 'r', encoding='utf-8') as f:
        lines = [l.rstrip('\n') for l in f]
    paras, cur = [], []
    for l in lines:
        if l.strip() == '.':
            if cur:
                paras.append(cur); cur = []
        elif l.strip():
            cur.append(l)
    if cur:
        paras.append(cur)
    return paras


class TestTriageSourcesCurrentFile:

    def test_reads_current_chapter_not_zero(self, tmp_path):
        # current file is a chapter with content; 0.txt is empty
        app = _triage_app(tmp_path, ['.', 'x', '.', 'y'], source_name='chap.txt')
        app._triage_enter()
        assert app._triage_paragraphs == [['x'], ['y']]

    def test_starts_at_current_paragraph(self, tmp_path):
        app = _triage_app(tmp_path, ['.', 'a', '.', 'b', '.', 'c'],
                          source_name='chap.txt')
        app.line_ring.index = 3   # 'b' -> paragraph 1
        app._triage_enter()
        assert app._triage_para_idx == 1

    def test_dispatch_removes_from_current_file(self, tmp_path):
        app = _triage_app(tmp_path, ['.', 'gone', '.', 'stays'],
                          source_name='chap.txt', library=['target'])
        app._triage_enter()
        app._triage_para_idx = 0
        app._triage_filter = 'target'
        app._triage_dispatch()
        assert _read_paras(app.current_file_path) == [['stays']]
        assert ['gone'] in _read_paras(app._library_path_cache['target.txt'])

    def test_source_excluded_from_targets(self, tmp_path):
        # the file you're triaging must not be offered as its own target
        app = _triage_app(tmp_path, ['.', 'a'], source_name='chap.txt',
                          library=['chap', 'other'])
        app._triage_enter()
        names = [d for _, d in app._triage_matches()]
        assert 'chap' not in names
        assert 'other' in names

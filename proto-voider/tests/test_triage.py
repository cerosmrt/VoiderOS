"""Tests for F5 paragraph triage view (source = 0.txt, type-to-filter target)."""
import os
import types
from unittest.mock import MagicMock

import pytest

from line_ring import LineRing
from helpers import make_ring_app


TRIAGE_METHODS = (
    '_paragraphs_from_ring', '_rebuild_ring_from_paragraphs', '_dot_line_index',
    '_atomic_write_lines', '_library_path', '_library_current_fname', '_save_library',
    '_triage_enter', '_triage_refresh', '_triage_parse_file', '_triage_parse_lines',
    '_triage_save', '_triage_next_para', '_triage_prev_para', '_para_ordinal_at',
    '_triage_matches', '_triage_target', '_triage_dispatch', '_triage_create',
    '_triage_swap_up', '_triage_swap_down',
    '_triage_filter_add', '_triage_filter_backspace', '_triage_cycle_match',
    '_triage_snapshot_once',
)


def _triage_app(tmp_path, zero_lines, library=None, current_is_zero=True):
    from new_interface import FullscreenCircleApp

    app = make_ring_app(['.'])
    void = tmp_path
    (void / 'I').mkdir(exist_ok=True)
    app.void_dir = str(void)
    app.f1_file = str(void / 'I' / '0.txt')
    with open(app.f1_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(zero_lines) + ('\n' if zero_lines else ''))

    library = library or []
    app._library_lines = []
    ring_names = []
    app._library_path_cache = {}
    for name in library:
        fname = name + '.txt'
        app._library_lines.append(fname)
        ring_names.append(name)
        p = str(void / 'I' / fname)
        open(p, 'w').close()
        app._library_path_cache[fname] = p
    app.book_ring = LineRing(ring_names or ['.'])

    if current_is_zero:
        app.current_file_path = app.f1_file
    else:
        chap = str(void / 'I' / 'otherchap.txt')
        open(chap, 'w').close()
        app.current_file_path = chap

    app.line_ring = LineRing(list(zero_lines) or ['.'])
    app._ipc = MagicMock()
    app.triage_view = MagicMock()
    app._triage_paragraphs = []
    app._triage_para_idx = 0
    app._triage_filter = ''
    app._triage_match_idx = 0
    app._triage_snapshotted = False
    app.switch_to_view = MagicMock()
    app._show_lock_screen = MagicMock()

    for name in TRIAGE_METHODS:
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


class TestTriageLoad:

    def test_loads_paragraphs_from_zero(self, tmp_path):
        app = _triage_app(tmp_path, ['.', 'a', 'b', '.', 'c'])
        app._triage_enter()
        assert app._triage_paragraphs == [['a', 'b'], ['c']]
        assert app._triage_para_idx == 0

    def test_empty_zero_sets_idx_minus1(self, tmp_path):
        app = _triage_app(tmp_path, [])
        app._triage_enter()
        assert app._triage_paragraphs == []
        assert app._triage_para_idx == -1


class TestTriageNavigation:

    def test_next_para_advances(self, tmp_path):
        app = _triage_app(tmp_path, ['.', 'a', '.', 'b', '.', 'c'])
        app._triage_enter()
        app._triage_next_para()
        assert app._triage_para_idx == 1

    def test_prev_at_first_goes_to_zo(self, tmp_path):
        app = _triage_app(tmp_path, ['.', 'a', '.', 'b'])
        app._triage_enter()
        app._triage_para_idx = 0
        app._triage_prev_para()
        assert app._triage_para_idx == -1

    def test_next_at_last_goes_to_zo(self, tmp_path):
        app = _triage_app(tmp_path, ['.', 'a', '.', 'b'])
        app._triage_enter()
        app._triage_para_idx = 1
        app._triage_next_para()
        assert app._triage_para_idx == -1


class TestTriageTargetResolution:

    def test_matches_substring(self, tmp_path):
        app = _triage_app(tmp_path, ['.', 'a'],
                          library=['moonlight', 'sunrise', 'moon-river'])
        app._triage_enter()
        app._triage_filter = 'moon'
        names = [d for _, d in app._triage_matches()]
        assert names == ['moonlight', 'moon-river']

    def test_target_existing_when_match(self, tmp_path):
        app = _triage_app(tmp_path, ['.', 'a'], library=['chapter-a'])
        app._triage_enter()
        app._triage_filter = 'chapter-a'
        target = app._triage_target()
        assert target['is_new'] is False
        assert target['fname'] == 'chapter-a.txt'

    def test_target_new_when_no_match(self, tmp_path):
        app = _triage_app(tmp_path, ['.', 'a'], library=['chapter-a'])
        app._triage_enter()
        app._triage_filter = 'totally-original'
        target = app._triage_target()
        assert target['is_new'] is True
        assert target['fname'] == 'totally-original.txt'

    def test_target_none_when_empty_filter_no_books(self, tmp_path):
        app = _triage_app(tmp_path, ['.', 'a'], library=[])
        app._triage_enter()
        app._triage_filter = ''
        assert app._triage_target() is None


class TestTriageDispatchExisting:

    def test_dispatch_appends_to_existing_chapter(self, tmp_path):
        app = _triage_app(tmp_path, ['.', 'p1', 'p2', '.', 'q'],
                          library=['chapter-a'])
        app._triage_enter()
        app._triage_para_idx = 0
        app._triage_filter = 'chapter-a'
        app._triage_dispatch()
        paras = _read_paras(app._library_path_cache['chapter-a.txt'])
        assert ['p1', 'p2'] in paras

    def test_dispatch_removes_from_source_zero(self, tmp_path):
        app = _triage_app(tmp_path, ['.', 'gone', '.', 'stays'],
                          library=['chapter-a'])
        app._triage_enter()
        app._triage_para_idx = 0
        app._triage_filter = 'chapter-a'
        app._triage_dispatch()
        assert _read_paras(app.f1_file) == [['stays']]

    def test_dispatch_no_new_file_for_existing(self, tmp_path):
        app = _triage_app(tmp_path, ['.', 'p'], library=['chapter-a'])
        app._triage_enter()
        app._triage_filter = 'chapter-a'
        before = list(app._library_lines)
        app._triage_dispatch()
        assert app._library_lines == before

    def test_dispatch_notifies_ipc_for_both_files(self, tmp_path):
        app = _triage_app(tmp_path, ['.', 'p', '.', 'r'], library=['chapter-a'])
        app._triage_enter()
        app._triage_filter = 'chapter-a'
        app._triage_dispatch()
        notified = {c.args[0] for c in app._ipc.notify_saved.call_args_list}
        assert app.f1_file in notified
        assert app._library_path_cache['chapter-a.txt'] in notified

    def test_dispatch_keeps_filter(self, tmp_path):
        # filter is preserved so consecutive paragraphs can go to the same chapter
        app = _triage_app(tmp_path, ['.', 'p', '.', 'r'], library=['chapter-a'])
        app._triage_enter()
        app._triage_filter = 'chapter-a'
        app._triage_dispatch()
        assert app._triage_filter == 'chapter-a'

    def test_dispatch_does_not_create_on_miss(self, tmp_path):
        # → never creates; an unmatched filter makes dispatch a no-op
        app = _triage_app(tmp_path, ['.', 'hello'], library=[])
        app._triage_enter()
        app._triage_filter = 'totally-original'
        app._triage_dispatch()
        assert not os.path.exists(str(tmp_path / 'I' / 'totally-original.txt'))
        assert app._triage_paragraphs == [['hello']]  # paragraph not moved


class TestTriageCreate:
    """Enter creates a new empty chapter from the typed name — no paragraph moves."""

    def test_create_makes_empty_file(self, tmp_path):
        app = _triage_app(tmp_path, ['.', 'hello'], library=[])
        app._triage_enter()
        app._triage_filter = 'newchap'
        app._triage_create()
        newpath = str(tmp_path / 'I' / 'newchap.txt')
        assert os.path.exists(newpath)
        assert _read_paras(newpath) == []  # empty, no paragraph sent

    def test_create_registers_in_library(self, tmp_path):
        app = _triage_app(tmp_path, ['.', 'hello'], library=[])
        app._triage_enter()
        app._triage_filter = 'newchap'
        app._triage_create()
        assert 'newchap.txt' in app._library_lines

    def test_create_does_not_move_paragraph(self, tmp_path):
        app = _triage_app(tmp_path, ['.', 'hello'], library=[])
        app._triage_enter()
        app._triage_filter = 'newchap'
        app._triage_create()
        assert app._triage_paragraphs == [['hello']]

    def test_create_keeps_filter(self, tmp_path):
        # filter preserved so → immediately dispatches the newly created chapter
        app = _triage_app(tmp_path, ['.', 'hello'], library=[])
        app._triage_enter()
        app._triage_filter = 'newchap'
        app._triage_create()
        assert app._triage_filter == 'newchap'

    def test_create_inserts_after_current_book_ring_index(self, tmp_path):
        app = _triage_app(tmp_path, ['.', 'hello'], library=['alpha', 'beta', 'gamma'])
        app._triage_enter()
        app.book_ring.index = 1  # pointing at 'beta'
        app._triage_filter = 'newchap'
        app._triage_create()
        # should be inserted at index 2, right after 'beta'
        assert app.book_ring.lines[2] == 'newchap'
        assert app._library_lines[2] == 'newchap.txt'

    def test_create_noop_when_already_exists(self, tmp_path):
        app = _triage_app(tmp_path, ['.', 'hello'], library=['chapter-a'])
        app._triage_enter()
        app._triage_filter = 'chapter-a'
        before = list(app._library_lines)
        app._triage_create()
        assert app._library_lines == before  # no duplicate

    def test_create_noop_on_empty_filter(self, tmp_path):
        app = _triage_app(tmp_path, ['.', 'hello'], library=[])
        app._triage_enter()
        app._triage_filter = ''
        before = list(app._library_lines)
        app._triage_create()
        assert app._library_lines == before


class TestTriageCrashClamp:

    def test_ring_index_valid_after_dispatch(self, tmp_path):
        app = _triage_app(tmp_path, ['.', 'a', '.', 'b', '.', 'c'],
                          library=['chapter-a'], current_is_zero=True)
        app._triage_enter()
        # park line_ring on the very last line
        app.line_ring.index = len(app.line_ring.lines) - 1
        app._triage_filter = 'chapter-a'
        app._triage_para_idx = 0
        app._triage_dispatch()
        assert app.line_ring.index < len(app.line_ring.lines)
        # must not raise
        app.line_ring.current()

    def test_rebuild_clamps_out_of_range_index(self, tmp_path):
        app = _triage_app(tmp_path, ['.', 'a', '.', 'b', '.', 'c'])
        app.line_ring = LineRing(['.', 'a', '.', 'b', '.', 'c'])
        app.line_ring.index = 5
        app._rebuild_ring_from_paragraphs([['a']])
        assert app.line_ring.index < len(app.line_ring.lines)
        app.line_ring.current()


class TestTriageSnapshot:

    def test_snapshot_runs_once_per_session(self, tmp_path, monkeypatch):
        import f5_triage_mixin
        calls = []
        monkeypatch.setattr(f5_triage_mixin.subprocess, 'run',
                            lambda *a, **k: calls.append(a))
        app = _triage_app(tmp_path, ['.', 'p', '.', 'q', '.', 'r'],
                          library=['chapter-a'])
        app._triage_enter()
        app._triage_filter = 'chapter-a'
        app._triage_dispatch()
        first = len(calls)
        app._triage_filter = 'chapter-a'
        app._triage_dispatch()
        # second dispatch must not snapshot again
        assert len(calls) == first
        assert first >= 1


class TestTriageReorder:

    def test_swap_up_persists(self, tmp_path):
        app = _triage_app(tmp_path, ['.', 'first', '.', 'second'])
        app._triage_enter()
        app._triage_para_idx = 1
        app._triage_swap_up()
        assert app._triage_paragraphs[0] == ['second']
        assert _read_paras(app.f1_file)[0] == ['second']

    def test_swap_up_noop_at_first(self, tmp_path):
        app = _triage_app(tmp_path, ['.', 'one', '.', 'two'])
        app._triage_enter()
        app._triage_para_idx = 0
        app._triage_swap_up()
        assert app._triage_paragraphs == [['one'], ['two']]

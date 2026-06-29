"""F1 focus writing on the active file: commit current line + open blank below."""
import os
import types
from unittest.mock import MagicMock

from line_ring import LineRing
from helpers import make_ring_app


def _f1_app(tmp_path, lines, idx):
    from new_interface import FullscreenCircleApp
    app = make_ring_app(['.'])
    void = tmp_path
    (void / 'I').mkdir(exist_ok=True)
    app.current_file_path = str(void / 'I' / 'chap.txt')
    open(app.current_file_path, 'w').close()
    app.line_ring = LineRing(list(lines))
    app.line_ring.index = idx
    app._ipc = MagicMock()
    app._doc_load_failed = False
    for nm in ('_f1_commit_line', 'auto_save_circular'):
        setattr(app, nm, types.MethodType(getattr(FullscreenCircleApp, nm), app))
    return app


def _disk(app):
    with open(app.current_file_path, 'r', encoding='utf-8') as f:
        return [l.rstrip('\n') for l in f]


def test_commit_on_empty_line_replaces_and_opens_below(tmp_path):
    app = _f1_app(tmp_path, ['', 'x'], 0)
    app._f1_commit_line('hello')
    assert app.line_ring.lines == ['hello', '', 'x']
    assert app.line_ring.index == 1          # parked on the new blank


def test_commit_on_text_line_updates_then_opens_below(tmp_path):
    app = _f1_app(tmp_path, ['old', 'x'], 0)
    app._f1_commit_line('new')
    assert app.line_ring.lines == ['new', '', 'x']
    assert app.line_ring.index == 1


def test_commit_on_dot_preserves_separator(tmp_path):
    app = _f1_app(tmp_path, ['a', '.', 'b'], 1)   # sitting on the dot
    app._f1_commit_line('mid')
    assert app.line_ring.lines == ['a', '.', 'mid', '', 'b']
    assert app.line_ring.index == 3


def test_empty_input_is_noop(tmp_path):
    app = _f1_app(tmp_path, ['', 'x'], 0)
    app._f1_commit_line('   ')
    assert app.line_ring.lines == ['', 'x']
    assert app.line_ring.index == 0


def test_commit_persists_to_active_file(tmp_path):
    app = _f1_app(tmp_path, ['', 'x'], 0)
    app._f1_commit_line('hello')
    assert 'hello' in _disk(app)


def test_consecutive_commits_build_forward(tmp_path):
    app = _f1_app(tmp_path, [''], 0)
    app._f1_commit_line('one')
    app._f1_commit_line('two')
    # one, then a blank gets filled by two, then a new blank
    assert app.line_ring.lines[:2] == ['one', 'two']
    assert app.line_ring.lines[app.line_ring.index] == ''

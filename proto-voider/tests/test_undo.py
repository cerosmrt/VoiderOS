"""UndoManager: coalescing, transactions, redo-clear, undo/redo round trips."""
import os
import types
from unittest.mock import MagicMock

from line_ring import LineRing
from helpers import make_ring_app
from undo_manager import UndoManager


def _read(path):
    with open(path, 'r', encoding='utf-8') as f:
        return [l.rstrip('\n') for l in f]


def _undo_app(tmp_path):
    from new_interface import FullscreenCircleApp
    app = make_ring_app(['.'])
    (tmp_path / 'I').mkdir(exist_ok=True)
    app.void_dir = str(tmp_path)
    app.book_dir = str(tmp_path / 'I')
    app.current_file_path = str(tmp_path / 'I' / '0.txt')
    with open(app.current_file_path, 'w', encoding='utf-8') as f:
        f.write('.\n')
    app.line_ring = LineRing(['.'])
    app._ipc = MagicMock()
    app._doc_load_failed = False
    app.current_view = 1
    app._undo = UndoManager()
    app._undo_last = {}
    app._undo_applying = False
    app._undo_txn = None
    app.load_doc_lines = MagicMock()
    app._doc_show_editor = MagicMock()
    for nm in ('auto_save_circular', '_atomic_write_lines', '_undo_capture',
               '_undo_apply', '_undo_refresh', '_undo_begin', '_undo_commit',
               '_undo_trackable'):
        setattr(app, nm, types.MethodType(getattr(FullscreenCircleApp, nm), app))
    return app


class TestUndoIntegration:

    def test_undo_redo_restores_file(self, tmp_path):
        app = _undo_app(tmp_path)
        app.line_ring.lines = ['.', 'hello']
        app.auto_save_circular()
        app.line_ring.lines = ['.', 'hello', 'world']
        app.auto_save_circular()
        assert _read(app.current_file_path) == ['.', 'hello', 'world']

        app._undo_apply(redo=False)
        assert _read(app.current_file_path) == ['.', 'hello']
        app._undo_apply(redo=True)
        assert _read(app.current_file_path) == ['.', 'hello', 'world']

    def test_keystroke_burst_is_one_undo(self, tmp_path):
        app = _undo_app(tmp_path)
        # simulate typing on the same line (coalesced by undo_key)
        for txt in (['.', 'h'], ['.', 'he'], ['.', 'hel'], ['.', 'hello']):
            app.line_ring.lines = txt
            app.auto_save_circular(undo_key=('doc', 1))
        # one undo step returns to the pre-burst content
        app._undo_apply(redo=False)
        assert _read(app.current_file_path) == ['.']

    def test_applying_undo_does_not_record(self, tmp_path):
        app = _undo_app(tmp_path)
        app.line_ring.lines = ['.', 'a']
        app.auto_save_circular()
        app._undo_apply(redo=False)          # undo
        assert app._undo.can_redo()
        # the restore write must not have created a new undo entry
        assert not app._undo.can_undo()


def test_record_and_undo_returns_before():
    u = UndoManager()
    u.record('a.txt', ['x'], ['x', 'y'])
    assert u.can_undo() and not u.can_redo()
    e = u.undo()
    assert e['files'] == [('a.txt', ['x'], ['x', 'y'])]
    assert u.can_redo() and not u.can_undo()


def test_noop_when_before_equals_after():
    u = UndoManager()
    u.record('a.txt', ['x'], ['x'])
    assert not u.can_undo()


def test_coalesce_same_key_same_file():
    u = UndoManager()
    u.record('a.txt', ['ab'], ['abc'], key=('line', 0))
    u.record('a.txt', ['abc'], ['abcd'], key=('line', 0))
    assert len(u._undo) == 1
    e = u.undo()
    # before is the start of the burst, after is the latest
    assert e['files'] == [('a.txt', ['ab'], ['abcd'])]


def test_different_key_separate_entries():
    u = UndoManager()
    u.record('a.txt', ['a'], ['ax'], key=('line', 0))
    u.record('a.txt', ['ax'], ['axy'], key=('line', 1))
    assert len(u._undo) == 2


def test_none_key_never_coalesces():
    u = UndoManager()
    u.record('a.txt', ['a'], ['b'])
    u.record('a.txt', ['b'], ['c'])
    assert len(u._undo) == 2


def test_record_clears_redo():
    u = UndoManager()
    u.record('a.txt', ['a'], ['b'])
    u.undo()
    assert u.can_redo()
    u.record('a.txt', ['a'], ['z'])
    assert not u.can_redo()


def test_undo_redo_round_trip():
    u = UndoManager()
    u.record('a.txt', ['a'], ['b'])
    assert u.undo()['files'][0] == ('a.txt', ['a'], ['b'])   # restore 'a'
    assert u.redo()['files'][0] == ('a.txt', ['a'], ['b'])   # restore 'b'
    assert not u.can_redo() and u.can_undo()


def test_transaction_groups_files():
    u = UndoManager()
    u.record_transaction([('src.txt', ['p', 'q'], ['q']),
                          ('dst.txt', [], ['p'])])
    e = u.undo()
    assert len(e['files']) == 2
    paths = {f[0] for f in e['files']}
    assert paths == {'src.txt', 'dst.txt'}


def test_transaction_drops_unchanged_files():
    u = UndoManager()
    u.record_transaction([('a.txt', ['x'], ['x']), ('b.txt', ['y'], ['z'])])
    e = u.undo()
    assert [f[0] for f in e['files']] == ['b.txt']


def test_cap_drops_oldest():
    u = UndoManager(cap=3)
    for i in range(5):
        u.record('a.txt', [str(i)], [str(i + 1)])
    assert len(u._undo) == 3
    # oldest ('0'->'1') dropped; newest kept
    assert u._undo[-1]['files'][0][2] == ['5']

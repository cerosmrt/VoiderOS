"""MERGE (F3, on a dot): collapse a book into one doc with '/name' seal markers,
and the split round-trip that restores the chapters."""
import os
import types
from unittest.mock import MagicMock

from line_ring import LineRing
from helpers import make_ring_app


def _read(path):
    with open(path, 'r', encoding='utf-8') as f:
        return [l.rstrip('\n') for l in f]


def _merge_app(tmp_path):
    from new_interface import FullscreenCircleApp
    app = make_ring_app(['.'])
    (tmp_path / 'I').mkdir(exist_ok=True)
    app.void_dir = str(tmp_path)
    app.f1_file = str(tmp_path / 'I' / '0.txt')
    open(app.f1_file, 'w').close()

    def mk(name, content):
        p = str(tmp_path / 'I' / (name + '.txt'))
        with open(p, 'w', encoding='utf-8') as f:
            f.write('\n'.join(content) + '\n')
        return p

    app._library_lines = ['.', 'A.txt', 'B.txt']
    app.book_ring = LineRing(['.', 'A', 'B'])
    app._library_path_cache = {'A.txt': mk('A', ['a1', 'a2']),
                               'B.txt': mk('B', ['b1'])}
    app._ipc = MagicMock()
    app.book_view = MagicMock()
    app.current_file_path = app.f1_file
    app.switch_to_view = MagicMock()
    app._set_f2_file = MagicMock()
    app._book_show_editor = MagicMock()
    app.load_doc_lines = MagicMock()
    app._doc_show_editor = MagicMock()
    app._book_pending_merge = False
    for nm in ('_book_merge_prompt', '_book_cancel_merge', '_book_do_merge',
               '_split_chapter_at_slash', '_git_snapshot_void',
               '_atomic_write_lines', '_save_library', '_library_path'):
        setattr(app, nm, types.MethodType(getattr(FullscreenCircleApp, nm), app))
    return app


def test_merge_collapses_book(tmp_path):
    app = _merge_app(tmp_path)
    app.book_ring.index = 0
    app._book_merge_prompt()                          # blank naming line below dot
    assert app._library_lines == ['.', '', 'A.txt', 'B.txt']
    app.book_view.editor.text.return_value = 'Book1'
    app._book_do_merge()
    assert app._library_lines == ['.', 'Book1.txt']
    assert app.switch_to_view.call_count == 0          # stays in F3
    assert _read(str(tmp_path / 'I' / 'Book1.txt')) == ['a1', 'a2', '/A', 'b1', '/B']
    assert not os.path.exists(str(tmp_path / 'I' / 'A.txt'))
    assert not os.path.exists(str(tmp_path / 'I' / 'B.txt'))


def test_merge_then_split_round_trip(tmp_path):
    app = _merge_app(tmp_path)
    app.book_ring.index = 0
    app._book_merge_prompt()
    app.book_view.editor.text.return_value = 'Book1'
    app._book_do_merge()

    # now re-split the merged container
    merged = _read(str(tmp_path / 'I' / 'Book1.txt'))
    app.current_file_path = str(tmp_path / 'I' / 'Book1.txt')
    app.line_ring = LineRing(merged)
    app.book_ring.index = app._library_lines.index('Book1.txt')
    app._split_chapter_at_slash()

    assert app._library_lines == ['.', 'A.txt', 'B.txt']
    assert _read(str(tmp_path / 'I' / 'A.txt')) == ['a1', 'a2']
    assert _read(str(tmp_path / 'I' / 'B.txt')) == ['b1']
    assert not os.path.exists(str(tmp_path / 'I' / 'Book1.txt'))


def test_split_from_f3_highlighted_file(tmp_path):
    from new_interface import FullscreenCircleApp
    app = make_ring_app(['.'])
    (tmp_path / 'I').mkdir(exist_ok=True)
    app.void_dir = str(tmp_path)
    app.f1_file = str(tmp_path / 'I' / '0.txt')
    open(app.f1_file, 'w').close()
    dpath = str(tmp_path / 'I' / 'doc.txt')
    with open(dpath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(['a', '/X', 'b', '/Y']) + '\n')
    app._library_lines = ['.', 'doc.txt']
    app.book_ring = LineRing(['.', 'doc'])
    app._library_path_cache = {'doc.txt': dpath}
    app.book_ring.index = 1                          # highlighting 'doc'
    app.current_file_path = app.f1_file
    app._ipc = MagicMock()
    app.book_view = MagicMock()
    app.book_view.editor.text.return_value = 'doc'   # no rename
    app._book_pending_new = False
    app._set_f2_file = MagicMock()
    app._doc_show_editor = MagicMock()
    app._book_show_editor = MagicMock()

    def _load():
        with open(app.current_file_path, 'r', encoding='utf-8') as f:
            app.line_ring = LineRing([l.strip() for l in f if l.strip()] or ['.'])
    app.load_doc_lines = _load

    for nm in ('_book_split_current', '_split_chapter_at_slash', '_git_snapshot_void',
               '_atomic_write_lines', '_save_library', '_library_path',
               '_book_is_portal', '_library_current_fname', '_book_try_rename'):
        setattr(app, nm, types.MethodType(getattr(FullscreenCircleApp, nm), app))

    app._book_split_current()
    assert 'X.txt' in app._library_lines and 'Y.txt' in app._library_lines
    assert _read(str(tmp_path / 'I' / 'X.txt')) == ['a']
    assert _read(str(tmp_path / 'I' / 'Y.txt')) == ['b']
    assert not os.path.exists(dpath)                 # merged container consumed


def test_merge_empty_name_cancels(tmp_path):
    app = _merge_app(tmp_path)
    app.book_ring.index = 0
    app._book_merge_prompt()
    app.book_view.editor.text.return_value = ''      # no name
    app._book_do_merge()
    assert app._library_lines == ['.', 'A.txt', 'B.txt']   # naming line removed
    assert os.path.exists(str(tmp_path / 'I' / 'A.txt'))
    assert app.switch_to_view.call_count == 0

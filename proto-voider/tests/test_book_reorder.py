"""F3 reorder: dots move whole books; chapters swap with the immediate neighbour."""
import types
from unittest.mock import MagicMock

from line_ring import LineRing
from helpers import make_ring_app

METHODS = ('_book_swap_up', '_book_swap_down', '_book_block_bounds',
           '_apply_book_order', '_book_swap_entries', '_book_move_block',
           '_book_refresh_editor', '_save_library', '_library_path',
           '_atomic_write_lines')


def _app(tmp_path, names):
    """names: book_ring display list ('.' separators, else chapters)."""
    from new_interface import FullscreenCircleApp
    app = make_ring_app(['.'])
    app.void_dir = str(tmp_path)
    app.book_view = None
    app._ipc = MagicMock()
    app.book_ring = LineRing(list(names))
    app._library_lines = ['.' if x == '.' else x + '.txt' for x in names]
    for nm in METHODS:
        setattr(app, nm, types.MethodType(getattr(FullscreenCircleApp, nm), app))
    return app


def test_swap_commits_edited_title_first(tmp_path, monkeypatch):
    # rename a chapter in the editor, then Alt-move: the rename must be committed
    # (file renamed, new name moves with the swap), not reverted.
    import f3_mixin
    from new_interface import FullscreenCircleApp
    monkeypatch.setattr(f3_mixin, '_save_config', lambda *a, **k: None)

    (tmp_path / 'I').mkdir()
    (tmp_path / 'I' / 'A.txt').write_text('a', encoding='utf-8')
    (tmp_path / 'I' / 'B.txt').write_text('b', encoding='utf-8')

    app = make_ring_app(['.'])
    app.void_dir = str(tmp_path)
    app.book_dir = str(tmp_path / 'I')
    app.config = {}
    app.current_file_path = str(tmp_path / 'I' / 'A.txt')
    app._book_pending_new = False
    app._library_lines = ['.', 'A.txt', 'B.txt']
    app.book_ring = LineRing(['.', 'A', 'B'])
    app.book_ring.index = 2                       # on B
    app._library_path_cache = {
        'A.txt': str(tmp_path / 'I' / 'A.txt'),
        'B.txt': str(tmp_path / 'I' / 'B.txt'),
    }
    app._ipc = MagicMock()
    app.book_view = MagicMock()
    app.book_view.editor.text.return_value = 'Bee'   # user renamed B -> Bee
    for nm in METHODS + ('_book_try_rename', '_book_is_portal',
                         '_library_current_fname', '_library_path'):
        if hasattr(FullscreenCircleApp, nm):
            setattr(app, nm, types.MethodType(getattr(FullscreenCircleApp, nm), app))

    app._book_swap_up()

    assert (tmp_path / 'I' / 'Bee.txt').exists()          # rename committed
    assert not (tmp_path / 'I' / 'B.txt').exists()
    assert app.book_ring.lines == ['.', 'Bee', 'A']       # new name moved up
    assert app._library_lines == ['.', 'Bee.txt', 'A.txt']


def test_chapter_swaps_with_immediate_neighbour(tmp_path):
    app = _app(tmp_path, ['.', 'A', 'B', 'C'])
    app.book_ring.index = 2          # B
    app._book_swap_up()
    assert app.book_ring.lines == ['.', 'B', 'A', 'C']
    assert app._library_lines == ['.', 'B.txt', 'A.txt', 'C.txt']
    assert app.book_ring.index == 1


def test_chapter_at_edge_crosses_into_neighbour_book(tmp_path):
    # last chapter of book1 (B) moves down past the dot into book2 (no interchange)
    app = _app(tmp_path, ['.', 'A', 'B', '.', 'C', 'D'])
    app.book_ring.index = 2          # B (last of book1)
    app._book_swap_down()
    # B crosses the dot; C and D are NOT interchanged
    assert app.book_ring.lines == ['.', 'A', '.', 'B', 'C', 'D']
    assert app.book_ring.index == 3


def test_dot_moves_whole_book_down(tmp_path):
    app = _app(tmp_path, ['.', 'A', 'B', '.', 'C'])
    app.book_ring.index = 0          # first book's dot
    app._book_swap_down()
    # book1 [. A B] swaps with book2 [. C]
    assert app.book_ring.lines == ['.', 'C', '.', 'A', 'B']
    assert app.book_ring.lines[app.book_ring.index] == '.'
    # the moved book's dot now leads [. A B]
    s, e = app._book_block_bounds(app.book_ring.index)
    assert app.book_ring.lines[s:e] == ['.', 'A', 'B']


def test_dot_moves_whole_book_up(tmp_path):
    app = _app(tmp_path, ['.', 'A', '.', 'B', 'C'])
    app.book_ring.index = 2          # second book's dot
    app._book_swap_up()
    assert app.book_ring.lines == ['.', 'B', 'C', '.', 'A']
    s, e = app._book_block_bounds(app.book_ring.index)
    assert app.book_ring.lines[s:e] == ['.', 'B', 'C']


def test_first_book_cannot_move_up(tmp_path):
    app = _app(tmp_path, ['.', 'A', '.', 'B'])
    app.book_ring.index = 0
    app._book_swap_up()
    assert app.book_ring.lines == ['.', 'A', '.', 'B']


def test_last_book_cannot_move_down(tmp_path):
    app = _app(tmp_path, ['.', 'A', '.', 'B'])
    app.book_ring.index = 2
    app._book_swap_down()
    assert app.book_ring.lines == ['.', 'A', '.', 'B']


def test_parallel_arrays_stay_aligned_after_block_move(tmp_path):
    app = _app(tmp_path, ['.', 'A', 'B', '.', 'C'])
    app.book_ring.index = 0
    app._book_swap_down()
    assert len(app.book_ring.lines) == len(app._library_lines)
    for disp, fn in zip(app.book_ring.lines, app._library_lines):
        assert (fn == '.') == (disp == '.')
        if disp != '.':
            assert fn == disp + '.txt'

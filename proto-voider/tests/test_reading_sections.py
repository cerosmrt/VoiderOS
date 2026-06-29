"""F4 content selection: whole book on a '.' separator, single file otherwise."""
import os
import types
from unittest.mock import MagicMock

from line_ring import LineRing
from helpers import make_ring_app


def _app(tmp_path, library, book_index, current_name='chap.txt'):
    """library: list of names ('.' for separators). Builds files for non-dot,
    non-portal names; book_ring positioned at book_index."""
    from new_interface import FullscreenCircleApp
    app = make_ring_app(['.'])
    void = tmp_path
    (void / 'I').mkdir(exist_ok=True)
    app.void_dir = str(void)
    app._library_lines = []
    app._library_path_cache = {}
    ring_names = []
    for name in library:
        if name == '.':
            app._library_lines.append('.')
            ring_names.append('.')
            continue
        fn = name + '.txt'
        app._library_lines.append(fn)
        ring_names.append(name)
        p = str(void / 'I' / fn)
        with open(p, 'w', encoding='utf-8') as f:
            f.write(f'body of {name}\n')
        app._library_path_cache[fn] = p
    app.book_ring = LineRing(ring_names)
    app.book_ring.index = book_index
    app.current_file_path = str(void / 'I' / current_name)
    with open(app.current_file_path, 'w', encoding='utf-8') as f:
        f.write('current body\n')
    for nm in ('_reading_sections', '_reading_file_lines'):
        setattr(app, nm, types.MethodType(getattr(FullscreenCircleApp, nm), app))
    return app


def test_on_dot_returns_whole_group(tmp_path):
    # layout: . A B . C   — dot at index 0 owns the group [A, B]
    app = _app(tmp_path, ['.', 'A', 'B', '.', 'C'], book_index=0)
    sections, single = app._reading_sections()
    assert single is False
    assert [t for t, _ in sections] == ['A', 'B']


def test_second_group_on_its_dot(tmp_path):
    app = _app(tmp_path, ['.', 'A', '.', 'B', 'C'], book_index=2)  # dot before B
    sections, single = app._reading_sections()
    assert [t for t, _ in sections] == ['B', 'C']


def test_portals_skipped_in_book(tmp_path):
    app = _app(tmp_path, ['.', '0', 'A'], book_index=0)
    # '0' becomes 0.txt portal entry
    app._library_lines = ['.', '0.txt', 'A.txt']
    app.book_ring = LineRing(['.', '0', 'A'])
    app.book_ring.index = 0
    sections, single = app._reading_sections()
    assert [t for t, _ in sections] == ['A']


def test_on_chapter_returns_highlighted_chapter(tmp_path):
    # F4 follows the F3 highlight, not the last-opened file
    app = _app(tmp_path, ['.', 'A', 'B'], book_index=1)  # highlight A
    sections, at_para = app._reading_sections()
    assert [t for t, _ in sections] == ['A']
    assert sections[0][1] == ['body of A']
    assert at_para is False                       # A isn't the active file


def test_at_para_true_when_highlight_is_active_file(tmp_path):
    app = _app(tmp_path, ['.', 'A', 'B'], book_index=1)
    app.current_file_path = app._library_path_cache['A.txt']   # active == highlight
    sections, at_para = app._reading_sections()
    assert at_para is True

"""Slash-split: a bare '/' line cuts the current chapter; the text after it
becomes a NEW chapter named by the first following line (consumed), inserted in
the library right below the current chapter. All '/' markers split."""
import os
import types
from unittest.mock import MagicMock

from line_ring import LineRing
from helpers import make_ring_app


METHODS = ('_split_chapter_at_slash', '_git_snapshot_void',
           '_atomic_write_lines', '_save_library', '_library_path')


def _split_app(tmp_path, cur_name, cur_lines, library):
    from new_interface import FullscreenCircleApp
    app = make_ring_app(['.'])
    void = tmp_path
    (void / 'I').mkdir(exist_ok=True)
    app.void_dir = str(void)
    app.f1_file = str(void / 'I' / '0.txt')
    open(app.f1_file, 'w').close()

    app._library_lines = []
    app._library_path_cache = {}
    ring = []
    for nm in library:
        fn = nm + '.txt'
        app._library_lines.append(fn)
        ring.append(nm)
        p = str(void / 'I' / fn)
        open(p, 'w').close()
        app._library_path_cache[fn] = p
    app.book_ring = LineRing(ring or ['.'])

    cur_path = str(void / 'I' / (cur_name + '.txt'))
    with open(cur_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(cur_lines) + '\n')
    app.current_file_path = cur_path
    app.line_ring = LineRing(list(cur_lines) or ['.'])

    app._ipc = MagicMock()
    app.load_doc_lines = MagicMock()
    app._doc_show_editor = MagicMock()
    for nm in METHODS:
        setattr(app, nm, types.MethodType(getattr(FullscreenCircleApp, nm), app))
    return app, cur_path


def _read(path):
    with open(path, 'r', encoding='utf-8') as f:
        return [l.rstrip('\n') for l in f]


def test_single_split(tmp_path):
    app, cur = _split_app(tmp_path, 'chapA',
                          ['keep1', 'keep2', '/', 'NewTitle', 'b1', 'b2'],
                          ['chapA', 'other'])
    app._split_chapter_at_slash()
    assert _read(cur) == ['keep1', 'keep2']
    newp = str(tmp_path / 'I' / 'NewTitle.txt')
    assert os.path.exists(newp)
    assert _read(newp) == ['b1', 'b2']
    li = app._library_lines
    assert li.index('NewTitle.txt') == li.index('chapA.txt') + 1


def test_name_is_consumed_not_in_body(tmp_path):
    app, cur = _split_app(tmp_path, 'c', ['x', '/', 'Title', 'b'], ['c'])
    app._split_chapter_at_slash()
    assert _read(str(tmp_path / 'I' / 'Title.txt')) == ['b']


def test_multiple_splits_in_order(tmp_path):
    app, cur = _split_app(tmp_path, 'c',
                          ['head', '/', 'A', 'a1', '/', 'B', 'b1'], ['c', 'z'])
    app._split_chapter_at_slash()
    assert _read(cur) == ['head']
    assert _read(str(tmp_path / 'I' / 'A.txt')) == ['a1']
    assert _read(str(tmp_path / 'I' / 'B.txt')) == ['b1']
    li = app._library_lines
    assert li.index('A.txt') == li.index('c.txt') + 1
    assert li.index('B.txt') == li.index('A.txt') + 1


def test_no_slash_is_noop(tmp_path):
    app, cur = _split_app(tmp_path, 'c', ['a', 'b'], ['c'])
    before = list(app._library_lines)
    app._split_chapter_at_slash()
    assert _read(cur) == ['a', 'b']
    assert app._library_lines == before


def test_collision_merges_into_existing(tmp_path):
    # 'other' already exists with content → new body APPENDS to it (with a sep)
    app, cur = _split_app(tmp_path, 'c', ['x', '/', 'other', 'b'], ['c', 'other'])
    with open(str(tmp_path / 'I' / 'other.txt'), 'w', encoding='utf-8') as f:
        f.write('old1\nold2\n')
    app._split_chapter_at_slash()
    assert not os.path.exists(str(tmp_path / 'I' / 'other-2.txt'))   # no uniquify
    assert _read(str(tmp_path / 'I' / 'other.txt')) == ['old1', 'old2', '.', 'b']
    assert app._library_lines.count('other.txt') == 1               # no duplicate entry


def test_collision_merge_into_empty_has_no_leading_dot(tmp_path):
    # existing chapter is empty → merge is just the body (no stray leading '.')
    app, cur = _split_app(tmp_path, 'c', ['x', '/', 'other', 'b'], ['c', 'other'])
    app._split_chapter_at_slash()
    assert _read(str(tmp_path / 'I' / 'other.txt')) == ['b']


def test_slash_at_top_empties_current(tmp_path):
    app, cur = _split_app(tmp_path, 'c', ['/', 'T', 'b'], ['c'])
    app._split_chapter_at_slash()
    assert _read(cur) == ['.']
    assert _read(str(tmp_path / 'I' / 'T.txt')) == ['b']


def test_writes_are_atomic_no_tmp_left(tmp_path):
    app, cur = _split_app(tmp_path, 'c', ['k', '/', 'New', 'b'], ['c'])
    app._split_chapter_at_slash()
    leftovers = [p for p in os.listdir(str(tmp_path / 'I')) if p.endswith('.tmp')]
    assert leftovers == []

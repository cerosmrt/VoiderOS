"""Slash-split (new spec): a '/name' line SEALS the text above it (back to the
previous marker or the file start) into a chapter 'name'. The trailing remainder
stays in the current file; if that remainder is empty, the container is removed.
Sealed chapters take the container's slot, in order."""
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


def test_seals_text_above(tmp_path):
    app, cur = _split_app(tmp_path, 'chapA',
                          ['before1', 'before2', '/Sealed', 'after1'],
                          ['chapA', 'other'])
    app._split_chapter_at_slash()
    assert _read(str(tmp_path / 'I' / 'Sealed.txt')) == ['before1', 'before2']
    assert _read(cur) == ['after1']                       # trailing stays
    li = app._library_lines
    assert li.index('Sealed.txt') < li.index('chapA.txt')  # sealed above container


def test_multiple_markers_in_order(tmp_path):
    app, cur = _split_app(tmp_path, 'c', ['a', '/X', 'b', '/Y', 'c'], ['c'])
    app._split_chapter_at_slash()
    assert _read(str(tmp_path / 'I' / 'X.txt')) == ['a']
    assert _read(str(tmp_path / 'I' / 'Y.txt')) == ['b']
    assert _read(cur) == ['c']
    li = app._library_lines
    assert li.index('X.txt') < li.index('Y.txt') < li.index('c.txt')


def test_all_sealed_removes_container(tmp_path):
    # merge round-trip: everything sealed, no trailing -> container removed
    app, cur = _split_app(tmp_path, 'MERGED', ['a', '/X', 'b', '/Y'],
                          ['MERGED', 'z'])
    app._split_chapter_at_slash()
    assert app._library_lines == ['X.txt', 'Y.txt', 'z.txt']
    assert not os.path.exists(cur)
    assert _read(str(tmp_path / 'I' / 'X.txt')) == ['a']
    assert _read(str(tmp_path / 'I' / 'Y.txt')) == ['b']


def test_name_with_spaces(tmp_path):
    app, cur = _split_app(tmp_path, 'c', ['a', '/El Tercer Templo', 't'], ['c'])
    app._split_chapter_at_slash()
    assert _read(str(tmp_path / 'I' / 'El Tercer Templo.txt')) == ['a']


def test_bare_slash_auto_names(tmp_path):
    app, cur = _split_app(tmp_path, 'c', ['a', '/', 't'], ['c'])
    app._split_chapter_at_slash()
    made = [f for f in os.listdir(str(tmp_path / 'I'))
            if f not in ('c.txt', '0.txt')]
    assert len(made) == 1                                  # one auto-named chapter


def test_no_marker_is_noop(tmp_path):
    app, cur = _split_app(tmp_path, 'c', ['a', 'b'], ['c'])
    before = list(app._library_lines)
    app._split_chapter_at_slash()
    assert _read(cur) == ['a', 'b']
    assert app._library_lines == before


def test_clash_merges_into_existing(tmp_path):
    app, cur = _split_app(tmp_path, 'c', ['x', '/other', 't'], ['c', 'other'])
    with open(str(tmp_path / 'I' / 'other.txt'), 'w', encoding='utf-8') as f:
        f.write('old1\nold2\n')
    app._split_chapter_at_slash()
    assert not os.path.exists(str(tmp_path / 'I' / 'other-2.txt'))
    assert _read(str(tmp_path / 'I' / 'other.txt')) == ['old1', 'old2', '.', 'x']
    assert app._library_lines.count('other.txt') == 1


def test_writes_are_atomic_no_tmp_left(tmp_path):
    app, cur = _split_app(tmp_path, 'c', ['k', '/New', 't'], ['c'])
    app._split_chapter_at_slash()
    leftovers = [p for p in os.listdir(str(tmp_path / 'I')) if p.endswith('.tmp')]
    assert leftovers == []

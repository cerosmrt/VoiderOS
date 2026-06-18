"""Tests for _split_zero_to_docs — Ctrl+Shift+F on 0.txt sends each block with a
trailing '/name' marker to void/I/name.txt and removes it from 0.txt."""
import os
import types
import datetime
import pytest
from unittest.mock import MagicMock

from line_ring import LineRing
from helpers import make_ring_app


def _split_app(tmp_path, zero_lines, library=None, portal_idx=0, on_scratch=True):
    from new_interface import FullscreenCircleApp

    i_dir = tmp_path / 'I'
    i_dir.mkdir(exist_ok=True)
    scratch = i_dir / '0.txt'
    scratch.write_text('\n'.join(zero_lines) + '\n', encoding='utf-8')

    app = make_ring_app(list(zero_lines), tmp_file=str(scratch))
    app.void_dir = str(tmp_path)
    app.f1_file = str(scratch)
    app.line_ring = LineRing(list(zero_lines))
    app.current_file_path = str(scratch) if on_scratch else str(i_dir / 'other.txt')

    # Library: list of (display, raw). Default: a single '0' portal.
    if library is None:
        library = [('0', '0.txt')]
    app.book_ring = LineRing([d for d, _ in library])
    app._library_lines = [r for _, r in library]
    app.book_ring.index = portal_idx
    app._library_path_cache = {'0.txt': str(scratch)}
    app._save_library = MagicMock()

    for name in ('_split_zero_to_docs', '_zero_blocks', '_atomic_write_lines',
                 '_book_is_portal'):
        setattr(app, name, types.MethodType(getattr(FullscreenCircleApp, name), app))
    app.load_doc_lines = MagicMock()
    app._doc_show_editor = MagicMock()
    return app, scratch, i_dir


def test_named_marker_creates_doc_and_removes_block(tmp_path):
    zero = ['.', 'one', 'two', '/mydoc', '.', 'stays here']
    app, scratch, i_dir = _split_app(tmp_path, zero)
    app._split_zero_to_docs()

    target = i_dir / 'mydoc.txt'
    assert target.exists()
    assert target.read_text(encoding='utf-8').splitlines() == ['.', 'one', 'two']
    # 0.txt keeps only the unmarked block
    out = scratch.read_text(encoding='utf-8').splitlines()
    assert 'one' not in out and 'two' not in out
    assert 'stays here' in out


def test_marker_line_not_included_in_target(tmp_path):
    app, scratch, i_dir = _split_app(tmp_path, ['.', 'body', '/doc'])
    app._split_zero_to_docs()
    assert '/doc' not in (i_dir / 'doc.txt').read_text(encoding='utf-8')


def test_existing_doc_is_appended(tmp_path):
    app, scratch, i_dir = _split_app(tmp_path, ['.', 'new line', '/existing'])
    (i_dir / 'existing.txt').write_text('.\nold line\n', encoding='utf-8')
    app._split_zero_to_docs()
    lines = (i_dir / 'existing.txt').read_text(encoding='utf-8').splitlines()
    assert lines == ['.', 'old line', '.', 'new line']


def test_bare_slash_gets_auto_date_name(tmp_path):
    app, scratch, i_dir = _split_app(tmp_path, ['.', 'orphan', '/'])
    app._split_zero_to_docs()
    now = datetime.datetime.now()
    base = f"{now.year % 100}-{now.month}-{now.day}"
    assert (i_dir / f"{base}_1.txt").exists()


def test_multiple_bare_slashes_sequential(tmp_path):
    zero = ['.', 'a', '/', '.', 'b', '/']
    app, scratch, i_dir = _split_app(tmp_path, zero)
    app._split_zero_to_docs()
    now = datetime.datetime.now()
    base = f"{now.year % 100}-{now.month}-{now.day}"
    assert (i_dir / f"{base}_1.txt").exists()
    assert (i_dir / f"{base}_2.txt").exists()


def test_new_doc_inserted_below_portal(tmp_path):
    # library: [PROLOGUE, '0' portal, OTHER]; portal at index 1
    library = [('PROLOGUE', 'PROLOGUE.txt'), ('0', '0.txt'), ('OTHER', 'OTHER.txt')]
    app, scratch, i_dir = _split_app(tmp_path, ['.', 'x', '/fresh'],
                                     library=library, portal_idx=1)
    app._split_zero_to_docs()
    # 'fresh' must land at index 2 (right after the portal)
    assert app._library_lines[2] == 'fresh.txt'
    assert app.book_ring.lines[2] == 'fresh'
    app._save_library.assert_called()


def test_unmarked_only_is_noop(tmp_path):
    app, scratch, i_dir = _split_app(tmp_path, ['.', 'just text', '.', 'more'])
    app._split_zero_to_docs()
    app.load_doc_lines.assert_not_called()        # nothing moved → early return
    assert list(i_dir.iterdir()) == [scratch]      # no new files


def test_writes_backup(tmp_path):
    app, scratch, i_dir = _split_app(tmp_path, ['.', 'body', '/doc', '.', 'keep'])
    app._split_zero_to_docs()
    assert os.path.exists(str(scratch) + '.bak')


def test_refuses_non_scratch(tmp_path):
    app, scratch, i_dir = _split_app(tmp_path, ['.', 'body', '/doc'], on_scratch=False)
    app._split_zero_to_docs()
    assert not (i_dir / 'doc.txt').exists()
    app.load_doc_lines.assert_not_called()

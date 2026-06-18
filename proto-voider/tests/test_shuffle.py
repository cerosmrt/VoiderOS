"""Tests for _shuffle_zero — Ctrl+Shift+R randomises all lines of 0.txt only."""
import os
import types
import pytest
from unittest.mock import MagicMock

from line_ring import LineRing
from helpers import make_ring_app


def _shuffle_app(tmp_path, lines, on_scratch=True):
    from new_interface import FullscreenCircleApp

    i_dir = tmp_path / 'I'
    i_dir.mkdir(exist_ok=True)
    scratch = i_dir / '0.txt'
    scratch.write_text('\n'.join(lines) + '\n', encoding='utf-8')

    app = make_ring_app(list(lines), tmp_file=str(scratch))
    app.f1_file = str(scratch)
    app.line_ring = LineRing(list(lines))
    app.current_file_path = str(scratch) if on_scratch else str(i_dir / 'other.txt')

    for name in ('_shuffle_zero', '_atomic_write_lines'):
        setattr(app, name, types.MethodType(getattr(FullscreenCircleApp, name), app))
    app.load_doc_lines = MagicMock()
    app._doc_show_editor = MagicMock()
    return app, scratch


def test_shuffle_preserves_all_content_lines(tmp_path):
    lines = ['.', 'alpha', 'beta', '.', 'gamma', 'delta', 'epsilon']
    app, scratch = _shuffle_app(tmp_path, lines)
    app._shuffle_zero()
    out = scratch.read_text(encoding='utf-8').splitlines()
    # Exactly one leading dot, no other dots, same multiset of content
    assert out[0] == '.'
    assert out.count('.') == 1
    assert sorted(out[1:]) == ['alpha', 'beta', 'delta', 'epsilon', 'gamma']


def test_shuffle_writes_backup(tmp_path):
    lines = ['.', 'one', 'two', 'three']
    app, scratch = _shuffle_app(tmp_path, lines)
    app._shuffle_zero()
    bak = str(scratch) + '.bak'
    assert os.path.exists(bak)
    # Backup holds the pre-shuffle content
    assert open(bak, encoding='utf-8').read().splitlines() == lines


def test_shuffle_reloads_ring(tmp_path):
    app, _ = _shuffle_app(tmp_path, ['.', 'a', 'b', 'c'])
    app._shuffle_zero()
    app.load_doc_lines.assert_called_once()
    app._doc_show_editor.assert_called_once()


def test_shuffle_refuses_non_scratch_file(tmp_path):
    app, scratch = _shuffle_app(tmp_path, ['.', 'a', 'b', 'c'], on_scratch=False)
    app._shuffle_zero()
    # Did not touch the scratch and did not reload
    app.load_doc_lines.assert_not_called()
    assert not os.path.exists(str(scratch) + '.bak')


def test_shuffle_noop_on_too_few_lines(tmp_path):
    app, scratch = _shuffle_app(tmp_path, ['.', 'only one'])
    app._shuffle_zero()
    app.load_doc_lines.assert_not_called()
    assert not os.path.exists(str(scratch) + '.bak')

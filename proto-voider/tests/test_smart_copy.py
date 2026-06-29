"""Ctrl+C contextual copy: F2 line / paragraph-on-dot, F3 chapter (raw text)."""
import os
import types

import pytest

from PyQt6.QtWidgets import QApplication

from line_ring import LineRing
from helpers import make_ring_app


@pytest.fixture(scope='module')
def qapp():
    yield QApplication.instance() or QApplication([])


def _app(lines, view=1):
    from new_interface import FullscreenCircleApp
    app = make_ring_app(lines)
    app.current_view = view
    app._smart_copy = types.MethodType(FullscreenCircleApp._smart_copy, app)
    app._library_current_fname = types.MethodType(
        FullscreenCircleApp._library_current_fname, app)
    return app


def test_copy_current_line(qapp):
    app = _app(['.', 'hello', '.', 'world'])
    app.line_ring.index = 1            # 'hello'
    app._smart_copy()
    assert QApplication.clipboard().text() == 'hello'


def test_copy_paragraph_on_dot(qapp):
    app = _app(['.', 'a', 'b', '.', 'c'])
    app.line_ring.index = 0            # on the leading dot → following paragraph
    app._smart_copy()
    assert QApplication.clipboard().text() == 'a\nb'


def test_dot_with_no_following_paragraph_copies_nothing(qapp):
    QApplication.clipboard().setText('SENTINEL')
    app = _app(['a', '.'])
    app.line_ring.index = 1            # trailing dot, nothing after
    app._smart_copy()
    assert QApplication.clipboard().text() == 'SENTINEL'   # unchanged


def test_copy_chapter_raw_in_f3(tmp_path, qapp):
    app = _app(['.'], view=2)
    void = tmp_path
    (void / 'I').mkdir(exist_ok=True)
    fpath = str(void / 'I' / 'chap.txt')
    with open(fpath, 'w', encoding='utf-8') as f:
        f.write('line one\n.\nline two\n')
    app._library_lines = ['chap.txt']
    app._library_path_cache = {'chap.txt': fpath}
    app.book_ring = LineRing(['chap'])
    app.book_ring.index = 0
    app._smart_copy()
    assert QApplication.clipboard().text() == 'line one\n.\nline two'

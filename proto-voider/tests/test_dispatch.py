"""Tests for Ctrl+Shift+D paragraph dispatch from 0.txt via /name markers."""
import os
import types
import tempfile

import pytest
from line_ring import LineRing
from helpers import make_ring_app


DISPATCH_METHODS = ('_dispatch_paragraphs',)


def _dispatch_app(lines, i_dir=None):
    from new_interface import FullscreenCircleApp

    tmp = tempfile.mkdtemp()
    f0 = os.path.join(tmp, '0.txt')
    with open(f0, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')

    app = make_ring_app(list(lines), tmp_file=f0)
    app.line_ring = LineRing(list(lines))
    app.f1_file = f0
    app.book_dir = i_dir or tmp

    for name in DISPATCH_METHODS:
        setattr(app, name, types.MethodType(getattr(FullscreenCircleApp, name), app))

    # stub out auto_save_circular and load_doc_lines
    app.auto_save_circular = lambda: None
    app.load_doc_lines = lambda: None

    return app, tmp


def _read(path):
    with open(path, encoding='utf-8') as f:
        return [l.rstrip('\n') for l in f if l.strip()]


def test_dispatch_named_paragraph(tmp_path):
    """A paragraph followed by /chapter is appended to chapter.txt."""
    lines = ['.', 'Line one.', 'Line two.', '/chapter', '.', 'Stays here.']
    app, tmp = _dispatch_app(lines, str(tmp_path))
    app._dispatch_paragraphs()

    chapter = tmp_path / 'chapter.txt'
    assert chapter.exists()
    content = _read(str(chapter))
    assert 'Line one.' in content
    assert 'Line two.' in content

    # Stays here. must remain in ring (no /marker above it)
    remaining = [l for l in app.line_ring.lines if l not in ('.', '')]
    assert 'Stays here.' in remaining
    assert 'Line one.' not in remaining
    assert '/chapter' not in remaining


def test_dispatch_slash_alone_creates_timestamped_file(tmp_path, monkeypatch):
    """/  alone (no name) creates a timestamped file."""
    import datetime
    fixed = datetime.datetime(2026, 6, 24, 10, 30, 0)
    monkeypatch.setattr(datetime, 'datetime',
                        type('dt', (), {'now': staticmethod(lambda: fixed)})())

    lines = ['.', 'Solo paragraph.', '/']
    app, tmp = _dispatch_app(lines, str(tmp_path))
    app._dispatch_paragraphs()

    files = list(tmp_path.glob('*.txt'))
    txt_files = [f for f in files if f.name != '0.txt']
    assert len(txt_files) == 1
    content = _read(str(txt_files[0]))
    assert 'Solo paragraph.' in content


def test_dispatch_appends_to_existing_file(tmp_path):
    """Dispatching to an existing file appends, doesn't overwrite."""
    chapter = tmp_path / 'notes.txt'
    chapter.write_text('Existing line.\n', encoding='utf-8')

    lines = ['.', 'New line.', '/notes']
    app, tmp = _dispatch_app(lines, str(tmp_path))
    app._dispatch_paragraphs()

    content = _read(str(chapter))
    assert 'Existing line.' in content
    assert 'New line.' in content


def test_dispatch_no_markers_is_noop(tmp_path):
    """No /markers → nothing dispatched, ring unchanged."""
    lines = ['.', 'Keep me.', 'Keep me too.']
    app, tmp = _dispatch_app(lines, str(tmp_path))
    before = list(app.line_ring.lines)
    app._dispatch_paragraphs()
    assert app.line_ring.lines == before


def test_dispatch_multiple_paragraphs(tmp_path):
    """Multiple dispatched paragraphs each go to their named file."""
    lines = ['.', 'Para A.', '/alpha', '.', 'Para B.', '/beta', '.', 'Stay.']
    app, tmp = _dispatch_app(lines, str(tmp_path))
    app._dispatch_paragraphs()

    assert (tmp_path / 'alpha.txt').exists()
    assert (tmp_path / 'beta.txt').exists()
    remaining = [l for l in app.line_ring.lines if l not in ('.', '')]
    assert remaining == ['Stay.']

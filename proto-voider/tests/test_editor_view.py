"""F9 prose editor: editing prose saves back into the dot-model (only if changed)."""
import types
from unittest.mock import MagicMock

import pytest

from PyQt6.QtWidgets import QApplication, QPlainTextEdit

from line_ring import LineRing
from helpers import make_ring_app


@pytest.fixture(scope='module')
def qapp():
    yield QApplication.instance() or QApplication([])


def _editor_app(tmp_path, dot_lines):
    from new_interface import FullscreenCircleApp
    app = make_ring_app(['.'])
    (tmp_path / 'I').mkdir(exist_ok=True)
    app.void_dir = str(tmp_path)
    app.book_dir = str(tmp_path / 'I')
    app.current_file_path = str(tmp_path / 'I' / 'c.txt')
    with open(app.current_file_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(dot_lines) + '\n')
    app.line_ring = LineRing(list(dot_lines))
    app._ipc = MagicMock()
    app._doc_load_failed = False
    app.circular_view = None            # _doc_show_editor / load guard on this
    app._undo = None
    app._undo_last = {}
    app._undo_applying = False
    app._undo_txn = None
    app.editor_view = QPlainTextEdit()
    for nm in ('_editor_save', '_atomic_write_lines', 'reformat_active_file',
               'load_doc_lines', '_doc_show_editor', '_undo_begin', '_undo_commit',
               '_undo_capture', '_undo_trackable', '_restore_last_line',
               '_last_lines_path'):
        if hasattr(FullscreenCircleApp, nm):
            setattr(app, nm, types.MethodType(getattr(FullscreenCircleApp, nm), app))
    return app


def _read(app):
    with open(app.current_file_path, 'r', encoding='utf-8') as f:
        return [l.rstrip('\n') for l in f]


def test_unmodified_does_not_rewrite(tmp_path, qapp):
    app = _editor_app(tmp_path, ['.', 'Unchanged line.'])
    app.editor_view.setPlainText('Unchanged line.')
    app.editor_view.document().setModified(False)      # just viewed
    app._editor_save()
    assert _read(app) == ['.', 'Unchanged line.']       # untouched


def test_edited_prose_saves_as_dot_model(tmp_path, qapp):
    app = _editor_app(tmp_path, ['.', 'Old.'])
    app.editor_view.setPlainText(
        'First sentence. Second sentence.\n\nSecond paragraph here.')
    app.editor_view.document().setModified(True)
    app._editor_save()
    result = _read(app)
    # paragraphs -> dot groups, sentences -> their own lines
    assert result == ['.', 'First sentence.', 'Second sentence.',
                      '.', 'Second paragraph here.']
    assert not app.editor_view.document().isModified()

"""Startup resume: proto reopens the last restorable view (F1–F4) on the active
file at its saved line, instead of always dropping into F1/beginning."""
import os
import types
from unittest.mock import MagicMock

from helpers import make_ring_app


def _restore_app(tmp_path, last_view):
    from new_interface import FullscreenCircleApp
    app = make_ring_app(['.'])
    f2 = str(tmp_path / 'chap.txt')
    with open(f2, 'w', encoding='utf-8') as f:
        f.write('l1\nl2\nl3\n')
    app.f2_file = f2
    app.current_file_path = str(tmp_path / '0.txt')
    open(app.current_file_path, 'w').close()
    app.config = {'last_view': last_view}
    app.switch_to_view = MagicMock()
    app.load_doc_lines = MagicMock()
    app._restore_startup_view = types.MethodType(
        FullscreenCircleApp._restore_startup_view, app)
    return app, f2


def test_restore_doc_view_loads_active_file(tmp_path):
    app, f2 = _restore_app(tmp_path, 1)          # last view = F2
    app._restore_startup_view()
    app.switch_to_view.assert_called_once_with(1)
    assert app.current_file_path == f2           # points at the active file
    app.load_doc_lines.assert_called_once()


def test_restore_f3_does_not_reload_doc(tmp_path):
    app, f2 = _restore_app(tmp_path, 2)          # last view = F3 (library)
    app._restore_startup_view()
    app.switch_to_view.assert_called_once_with(2)
    app.load_doc_lines.assert_not_called()       # F3 syncs the file itself


def test_non_restorable_view_falls_back_to_f1(tmp_path):
    app, f2 = _restore_app(tmp_path, 4)          # F5 triage → not restorable
    app._restore_startup_view()
    app.switch_to_view.assert_called_once_with(0)


def test_missing_last_view_defaults_to_f1(tmp_path):
    app, f2 = _restore_app(tmp_path, 1)
    app.config = {}                              # nothing saved yet
    app._restore_startup_view()
    app.switch_to_view.assert_called_once_with(0)

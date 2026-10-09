"""Alt-tabbing back to Voider left no widget with focus (arrows and letters dead,
PageUp/Down still worked): refocus the active editor when the app is activated."""
import types
from unittest.mock import MagicMock

from PyQt6.QtCore import Qt

from helpers import make_ring_app


def _app():
    from new_interface import FullscreenCircleApp
    app = make_ring_app(['.', 'a'])
    app._refocus_active_editor = MagicMock()
    app._on_app_state_changed = types.MethodType(
        FullscreenCircleApp._on_app_state_changed, app)
    return app


def test_refocus_when_application_becomes_active():
    app = _app()
    app._on_app_state_changed(Qt.ApplicationState.ApplicationActive)
    app._refocus_active_editor.assert_called_once()


def test_no_refocus_when_application_goes_inactive():
    app = _app()
    app._on_app_state_changed(Qt.ApplicationState.ApplicationInactive)
    app._refocus_active_editor.assert_not_called()

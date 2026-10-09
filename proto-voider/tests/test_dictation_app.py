"""Dictation wired into the app: toggle key, text inserted at the cursor of the
focused line (so you can keep typing and correcting), status label, config."""
import types
from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QApplication, QLineEdit

from app_config import DEFAULT_CONFIG
from helpers import make_ring_app


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


class _FakeEngine:
    def __init__(self, transcriber):
        self.transcriber = transcriber
        self.state, self.error, self.started, self.stopped, self.texts = 'off', '', 0, 0, []

    def start(self):
        self.started += 1
        self.state = 'listening'

    def stop(self):
        self.stopped += 1
        self.state = 'off'

    def poll(self):
        out, self.texts = self.texts, []
        return out


def _app(qapp, ok=True, why=''):
    from new_interface import FullscreenCircleApp
    app = make_ring_app(['.', 'a'])
    app.config = {'dictation_language': 'es', 'void_dir': '/v'}
    app.void_dir = '/v'
    app._dictation = None
    app.height, app.width = (lambda: 600), (lambda: 800)
    app._dictation_label = MagicMock()
    app.editor = QLineEdit()
    app._dictation_target = lambda: app.editor
    transcriber = MagicMock()
    transcriber.available.return_value = (ok, why)
    app._make_transcriber = lambda: transcriber
    app._make_dictation_engine = lambda t: _FakeEngine(t)
    for nm in ('_dictation_toggle', '_dictation_insert', '_dictation_tick', '_dictation_show'):
        setattr(app, nm, types.MethodType(getattr(FullscreenCircleApp, nm), app))
    return app


def test_toggle_on_starts_the_engine_and_shows_the_label(qapp):
    app = _app(qapp)
    app._dictation_toggle()
    assert app._dictation.started == 1
    assert 'escuchando' in app._dictation_label.setText.call_args[0][0]


def test_toggle_twice_stops_it_and_hides_the_label(qapp):
    app = _app(qapp)
    app._dictation_toggle()
    app._dictation_toggle()
    assert app._dictation is None
    app._dictation_label.hide.assert_called()


def test_unavailable_engine_does_not_start_and_says_why(qapp):
    app = _app(qapp, ok=False, why='falta el modelo: /v/stt/m.bin')
    app._dictation_toggle()
    assert app._dictation is None
    assert 'falta el modelo' in app._dictation_label.setText.call_args[0][0]


def test_text_is_inserted_at_the_cursor(qapp):
    app = _app(qapp)
    app.editor.setText('hola mundo')
    app.editor.setCursorPosition(4)
    app._dictation_insert('lindo')
    assert app.editor.text() == 'hola lindo mundo'


def test_inserting_into_an_empty_line_adds_no_leading_space(qapp):
    app = _app(qapp)
    app._dictation_insert('buen día')
    assert app.editor.text() == 'buen día'


def test_inserting_after_a_space_does_not_double_it(qapp):
    app = _app(qapp)
    app.editor.setText('hola ')
    app.editor.setCursorPosition(5)
    app._dictation_insert('mundo')
    assert app.editor.text() == 'hola mundo'


def test_read_only_line_is_left_alone(qapp):
    app = _app(qapp)
    app.editor.setReadOnly(True)
    app._dictation_insert('no entra')
    assert app.editor.text() == ''


def test_no_focused_line_drops_the_text(qapp):
    app = _app(qapp)
    app._dictation_target = lambda: None
    app._dictation_insert('al aire')             # must not raise


def test_tick_inserts_what_the_engine_heard_and_updates_the_label(qapp):
    app = _app(qapp)
    app._dictation_toggle()
    app._dictation.texts = ['uno', 'dos']
    app._dictation.state = 'transcribing'
    app._dictation_tick()
    assert app.editor.text() == 'uno dos'
    assert 'transcribiendo' in app._dictation_label.setText.call_args[0][0]


def test_tick_stops_on_engine_error(qapp):
    app = _app(qapp)
    app._dictation_toggle()
    app._dictation.state, app._dictation.error = 'error', 'mic unplugged'
    app._dictation_tick()
    assert app._dictation is None
    assert 'mic unplugged' in app._dictation_label.setText.call_args[0][0]


def test_tick_without_dictation_does_nothing(qapp):
    app = _app(qapp)
    app._dictation_tick()                        # no engine: must not raise


def test_default_key_menu_entry_and_language_setting_exist():
    from menu_model import MENUS
    from keys_model import SETTING_DEFS
    assert DEFAULT_CONFIG['keybindings']['dictation_toggle']
    assert 'dictation_toggle' in {a for _, es in MENUS for _, a in es}
    lang = next(d for d in SETTING_DEFS if d.key == 'dictation_language')
    assert lang.choices == ('es', 'en', 'auto')
    assert DEFAULT_CONFIG['dictation_language'] == 'es'


def test_label_says_the_model_is_loading(qapp):
    app = _app(qapp)
    app._dictation_toggle()
    app._dictation.state = 'loading'
    app._dictation_tick()
    assert 'cargando' in app._dictation_label.setText.call_args[0][0]


def test_make_transcriber_uses_model_size_language_and_void_stt_dir(qapp):
    from new_interface import FullscreenCircleApp
    app = _app(qapp)
    app.config.update({'dictation_model': 'base', 'dictation_language': 'en'})
    t = FullscreenCircleApp._make_transcriber(app)
    assert (t.model_size, t.language, t.root) == ('base', 'en', '/v/stt')


def test_make_transcriber_defaults_to_the_small_model(qapp):
    from new_interface import FullscreenCircleApp
    app = _app(qapp)
    assert FullscreenCircleApp._make_transcriber(app).model_size == 'small'

"""F10 keys list: a ring of rows like F3 — title first, then one row per action,
then the entry to the settings form. Pure model, no Qt widgets."""
from PyQt6.QtCore import Qt

from keys_model import KeysModel, SETTINGS_ROW, TITLE_ROW

K, M = Qt.Key, Qt.KeyboardModifier
DEFAULTS = {'help': 'F11', 'view_f1': 'F1', 'rebase': 'Ctrl+0'}


def _m(overrides=None):
    return KeysModel(DEFAULTS, overrides or {})


def test_rows_are_title_then_actions_then_settings():
    m = _m()
    assert [r.action for r in m.rows] == [TITLE_ROW, 'help', 'view_f1', 'rebase', SETTINGS_ROW]


def test_row_shows_current_key_and_custom_flag():
    m = _m({'help': 'F5'})
    help_row = m.rows[1]
    assert help_row.keytext == 'F5' and help_row.custom
    assert m.rows[2].keytext == 'F1' and not m.rows[2].custom


def test_arrows_wrap_like_a_ring():
    m = _m()
    m.move(-1)
    assert m.rows[m.index].action == SETTINGS_ROW
    m.move(1)
    assert m.index == 0


def test_page_moves_by_a_page_and_clamps():
    m = KeysModel({f'a{i}': 'F1' for i in range(30)}, {})
    m.page(1)
    assert m.index == 10
    m.page(1); m.page(1); m.page(1)
    assert m.index == len(m.rows) - 1
    m.page(-1)
    assert m.index == len(m.rows) - 11


def test_cannot_capture_on_title_or_settings_row():
    m = _m()
    assert not m.begin_capture()                      # title row
    m.index = len(m.rows) - 1
    assert not m.begin_capture()                      # settings row


def test_capture_assigns_the_pressed_key():
    m = _m()
    m.index = 1
    assert m.begin_capture() and m.capturing
    assert m.capture(K.Key_F6, M.NoModifier) == 'ok'
    assert not m.capturing
    assert m.overrides == {'help': 'F6'}
    assert m.rows[1].keytext == 'F6'


def test_escape_cancels_capture_without_changes():
    m = _m()
    m.index = 1
    m.begin_capture()
    assert m.capture(K.Key_Escape, M.NoModifier) == 'cancel'
    assert not m.capturing and m.overrides == {}


def test_unsupported_key_is_refused_and_capture_stays_open():
    m = _m()
    m.index = 1
    m.begin_capture()
    assert m.capture(K.Key_Home, M.NoModifier) == 'refused'
    assert m.capturing and m.overrides == {}


def test_bare_modifier_keeps_waiting():
    m = _m()
    m.index = 1
    m.begin_capture()
    assert m.capture(K.Key_Control, M.ControlModifier) == 'wait'
    assert m.capturing


def test_assigning_the_default_back_removes_the_override():
    m = _m({'help': 'F5'})
    m.index = 1
    m.begin_capture()
    m.capture(K.Key_F11, M.NoModifier)
    assert m.overrides == {}


def test_reset_row_restores_default():
    m = _m({'help': 'F5'})
    m.index = 1
    assert m.reset()
    assert m.overrides == {} and m.rows[1].keytext == 'F11'


def test_clash_names_the_other_action():
    m = _m()
    m.index = 1
    m.begin_capture()
    m.capture(K.Key_F1, M.NoModifier)                 # view_f1 already uses F1
    assert m.clash == 'view_f1'

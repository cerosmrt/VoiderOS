"""F10 keys list: a ring of rows like F3 — title first, then one row per action,
then the entry to the settings form. Pure model, no Qt widgets."""
from PyQt6.QtCore import Qt

from keys_model import KeysModel, TITLE_ROW

K, M = Qt.Key, Qt.KeyboardModifier
DEFAULTS = {'help': 'F11', 'view_f1': 'F1', 'rebase': 'Ctrl+0'}


def _m(overrides=None, values=None, fonts=None):
    return KeysModel(DEFAULTS, overrides or {}, values or {}, fonts)


def _row(m, action):
    return next(r for r in m.rows if r.action == action)


def _goto(m, action):
    m.index = [r.action for r in m.rows].index(action)


def test_rows_are_title_then_settings_then_actions():
    m = _m()
    actions = [r.action for r in m.rows]
    assert actions[0] == TITLE_ROW
    assert actions[1:14] == ['set:language', 'set:font_family', 'set:font_size', 'set:text_color',
                             'set:bg_color', 'set:carousel_preset', 'set:carousel_w',
                             'set:carousel_h', 'set:visualizer_source',
                             'set:visualizer_style', 'set:dictation_language', 'set:dictation_model',
                             'set:gravitor_books']
    assert actions[14:] == ['help', 'view_f1', 'rebase']


def test_row_shows_current_key_and_custom_flag():
    m = _m({'help': 'F5'})
    help_row = _row(m, 'help')
    assert help_row.keytext == 'F5' and help_row.custom
    assert _row(m, 'view_f1').keytext == 'F1' and not _row(m, 'view_f1').custom


def test_arrows_wrap_like_a_ring():
    m = _m()
    m.move(-1)
    assert m.rows[m.index].action == 'rebase'
    m.move(1)
    assert m.index == 0


def test_page_moves_by_a_page_and_clamps():
    m = KeysModel({f'a{i}': 'F1' for i in range(30)}, {})
    m.page(1)
    assert m.index == 10
    for _ in range(len(m.rows) // 10 + 1):
        m.page(1)
    assert m.index == len(m.rows) - 1
    m.page(-1)
    assert m.index == len(m.rows) - 11


def test_cannot_capture_on_title_or_setting_row():
    m = _m()
    assert not m.begin_capture()                      # title row
    m.index = 1
    assert not m.begin_capture()                      # a setting row


def test_capture_assigns_the_pressed_key():
    m = _m()
    _goto(m, 'help')
    assert m.begin_capture() and m.capturing
    assert m.capture(K.Key_F6, M.NoModifier) == 'ok'
    assert not m.capturing
    assert m.overrides == {'help': 'F6'}
    assert _row(m, 'help').keytext == 'F6'


def test_escape_cancels_capture_without_changes():
    m = _m()
    _goto(m, 'help')
    m.begin_capture()
    assert m.capture(K.Key_Escape, M.NoModifier) == 'cancel'
    assert not m.capturing and m.overrides == {}


def test_unsupported_key_is_refused_and_capture_stays_open():
    m = _m()
    _goto(m, 'help')
    m.begin_capture()
    assert m.capture(K.Key_Home, M.NoModifier) == 'refused'
    assert m.capturing and m.overrides == {}


def test_bare_modifier_keeps_waiting():
    m = _m()
    _goto(m, 'help')
    m.begin_capture()
    assert m.capture(K.Key_Control, M.ControlModifier) == 'wait'
    assert m.capturing


def test_assigning_the_default_back_removes_the_override():
    m = _m({'help': 'F5'})
    _goto(m, 'help')
    m.begin_capture()
    m.capture(K.Key_F11, M.NoModifier)
    assert m.overrides == {}


def test_reset_row_restores_default():
    m = _m({'help': 'F5'})
    _goto(m, 'help')
    assert m.reset()
    assert m.overrides == {} and _row(m, 'help').keytext == 'F11'


def test_clash_names_the_other_action():
    m = _m()
    _goto(m, 'help')
    m.begin_capture()
    m.capture(K.Key_F1, M.NoModifier)                 # view_f1 already uses F1
    assert m.clash == 'view_f1'


# ── ajustes como renglones (fase 2) ──────────────────────────────────────────

def _sm(values=None, fonts=None):
    return _m(values={'font_family': 'EB Garamond', 'font_size': 12,
                      'text_color': '#ffffff', 'bg_color': '#000000',
                      'carousel_preset': '4:5', 'carousel_w': 1080,
                      'carousel_h': 1350, **(values or {})}, fonts=fonts)


def test_setting_row_shows_its_current_value():
    m = _sm()
    assert _row(m, 'set:font_size').keytext == '12'
    assert _row(m, 'set:font_size').kind == 'setting'
    assert _row(m, 'help').kind == 'key'


def test_edit_an_int_setting_and_commit():
    m = _sm()
    _goto(m, 'set:font_size')
    assert m.begin_edit() and m.editing
    for _ in range(2):
        m.backspace()
    m.type('3'); m.type('3')
    assert m.commit() == ('ok', 'font_size', 33)
    assert not m.editing and _row(m, 'set:font_size').keytext == '33'


def test_int_out_of_range_is_refused_and_stays_open():
    m = _sm()
    _goto(m, 'set:font_size')
    m.begin_edit()
    m.backspace(); m.backspace(); m.type('2')          # 2 < min 4
    assert m.commit()[0] == 'refused'
    assert m.editing
    m.backspace(); m.type('1'); m.type('0')
    assert m.commit() == ('ok', 'font_size', 10)


def test_font_size_has_the_old_range():
    m = _sm()
    _goto(m, 'set:font_size')
    m.begin_edit()
    for _ in range(2):
        m.backspace()
    for ch in '999':
        m.type(ch)
    assert m.commit() == ('ok', 'font_size', 999)
    m.begin_edit()
    for _ in range(3):
        m.backspace()
    for ch in '1000':
        m.type(ch)
    assert m.commit()[0] == 'refused'


def test_color_must_be_hex():
    m = _sm()
    _goto(m, 'set:text_color')
    m.begin_edit()
    for _ in range(7):
        m.backspace()
    for ch in 'red':
        m.type(ch)
    assert m.commit()[0] == 'refused'
    for _ in range(3):
        m.backspace()
    for ch in '#ff0000':
        m.type(ch)
    assert m.commit() == ('ok', 'text_color', '#ff0000')


def test_font_must_exist_when_the_list_is_known():
    m = _sm(fonts=['EB Garamond', 'Georgia'])
    _goto(m, 'set:font_family')
    m.begin_edit()
    for _ in range(len('EB Garamond')):
        m.backspace()
    for ch in 'Nopeface':
        m.type(ch)
    assert m.commit()[0] == 'refused'
    for _ in range(len('Nopeface')):
        m.backspace()
    for ch in 'georgia':
        m.type(ch)
    assert m.commit() == ('ok', 'font_family', 'Georgia')      # canonical case


def test_cancel_edit_changes_nothing():
    m = _sm()
    _goto(m, 'set:font_size')
    m.begin_edit(); m.type('9')
    m.cancel_edit()
    assert not m.editing and _row(m, 'set:font_size').keytext == '12'


def test_choice_setting_cycles_through_its_options():
    m = _sm()
    _goto(m, 'set:carousel_preset')
    assert not m.begin_edit()                           # choices don't take typing
    assert m.cycle(1) == ('carousel_preset', '1.91:1')
    assert m.cycle(1) == ('carousel_preset', 'custom')
    assert m.cycle(1) == ('carousel_preset', '1:1')     # wraps
    assert m.cycle(-1) == ('carousel_preset', 'custom')


def test_left_right_step_an_int_setting_within_range():
    m = _sm({'font_size': 4})
    _goto(m, 'set:font_size')
    assert m.cycle(-1) is None                          # already at the minimum
    assert m.cycle(1) == ('font_size', 5)


def test_cycle_does_nothing_on_a_text_setting_or_key_row():
    m = _sm()
    _goto(m, 'set:text_color')
    assert m.cycle(1) is None
    _goto(m, 'help')
    assert m.cycle(1) is None


def test_visualizer_source_and_style_are_choices_that_cycle():
    m = _sm({'visualizer_source': 'off', 'visualizer_style': 'pulse'})
    _goto(m, 'set:visualizer_source')
    assert m.cycle(1) == ('visualizer_source', 'mic')
    assert m.cycle(1) == ('visualizer_source', 'output')
    assert m.cycle(1) == ('visualizer_source', 'off')
    _goto(m, 'set:visualizer_style')
    assert m.cycle(1) == ('visualizer_style', 'wave')
    assert m.cycle(1) == ('visualizer_style', 'bars')


def test_dictation_model_is_a_choice_from_fastest_to_most_accurate():
    m = _sm({'dictation_model': 'small'})
    _goto(m, 'set:dictation_model')
    assert m.cycle(1) == ('dictation_model', 'tiny')       # wraps
    assert m.cycle(1) == ('dictation_model', 'base')
    assert m.cycle(1) == ('dictation_model', 'small')

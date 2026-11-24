"""El selector de capítulos de F8: una lista con filtro, de a UNO, que se maneja con el
teclado (escribir filtra, ↑/↓ elige, Enter acepta, Esc cancela)."""
import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication

from chapter_picker import ChapterPicker

NO = Qt.KeyboardModifier.NoModifier
NAMES = ['Power.txt', 'Las costumbres.txt', 'Lonely boy.txt', 'Vision.txt']


@pytest.fixture(scope='module')
def qapp():
    yield QApplication.instance() or QApplication([])


def _key(widget, key, text=''):
    widget.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, key, NO, text))


def _shown(p):
    return [p.list.item(i).text() for i in range(p.list.count())]


def test_it_lists_the_chapters_without_the_extension(qapp):
    assert _shown(ChapterPicker(None, NAMES)) == ['Power', 'Las costumbres', 'Lonely boy', 'Vision']


def test_typing_filters_ignoring_case_and_accents(qapp):
    p = ChapterPicker(None, NAMES + ['Acción.txt'])
    p.filter.setText('ACCION')
    assert _shown(p) == ['Acción']
    p.filter.setText('lo')
    assert _shown(p) == ['Lonely boy']
    p.filter.setText('s')
    assert _shown(p) == ['Las costumbres', 'Vision']


def test_the_first_match_is_always_selected_so_enter_just_works(qapp):
    p = ChapterPicker(None, NAMES)
    assert p.chosen() == 'Power.txt'
    p.filter.setText('vis')
    assert p.chosen() == 'Vision.txt'


def test_down_and_up_move_the_selection_while_the_filter_keeps_the_focus(qapp):
    p = ChapterPicker(None, NAMES)
    p.move_selection(+1)
    assert p.chosen() == 'Las costumbres.txt'
    p.move_selection(+1)
    p.move_selection(-1)
    assert p.chosen() == 'Las costumbres.txt'


def test_the_selection_does_not_wrap_past_the_ends(qapp):
    p = ChapterPicker(None, NAMES)
    p.move_selection(-1)
    assert p.chosen() == 'Power.txt'
    for _ in range(10):
        p.move_selection(+1)
    assert p.chosen() == 'Vision.txt'


def test_a_filter_with_no_matches_chooses_nothing(qapp):
    p = ChapterPicker(None, NAMES)
    p.filter.setText('zzz')
    assert p.chosen() is None and p.list.count() == 0


def test_a_current_chapter_starts_selected(qapp):
    p = ChapterPicker(None, NAMES, current='Lonely boy.txt')
    assert p.chosen() == 'Lonely boy.txt'


def test_enter_accepts_and_escape_cancels(qapp):
    p = ChapterPicker(None, NAMES)
    p.accept_choice()
    assert p.result() == 1
    q = ChapterPicker(None, NAMES)
    q.reject()
    assert q.result() == 0


def test_enter_with_nothing_to_choose_does_not_accept(qapp):
    p = ChapterPicker(None, NAMES)
    p.filter.setText('zzz')
    p.accept_choice()
    assert p.result() == 0


def test_pick_chapter_returns_the_name_or_none(qapp, monkeypatch):
    import chapter_picker
    monkeypatch.setattr(ChapterPicker, 'exec', lambda self: 1)
    assert chapter_picker.pick_chapter(None, NAMES) == 'Power.txt'
    monkeypatch.setattr(ChapterPicker, 'exec', lambda self: 0)
    assert chapter_picker.pick_chapter(None, NAMES) is None


def test_pick_chapter_with_nothing_to_offer_returns_none_without_a_dialog(qapp):
    import chapter_picker
    assert chapter_picker.pick_chapter(None, []) is None

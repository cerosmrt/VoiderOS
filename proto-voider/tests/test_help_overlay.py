"""F11, la ayuda. Con la letra de la app grande las líneas se pisaban: la altura de fila
era fija (22 px) y el tamaño de la letra venía de la configuración (en el void de
Federico, 33). Ahora la fila sale de las métricas de la letra, la letra de la ayuda
tiene un tope, y si la lista no entra en la pantalla se desplaza."""
import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtCore import Qt, QEvent, QPoint, QPointF
from PyQt6.QtGui import QFont, QFontMetrics, QKeyEvent, QWheelEvent
from PyQt6.QtWidgets import QApplication, QWidget

import help_overlay as ho

NO = Qt.KeyboardModifier.NoModifier


@pytest.fixture(scope='module')
def qapp():
    yield QApplication.instance() or QApplication([])


class Host(QWidget):
    def __init__(self, pt, w=1280, h=800):
        super().__init__()
        self._app_font = QFont('Sans Serif', pt)
        self.resize(w, h)
        self.refocused = 0

    def _refocus_active_editor(self):
        self.refocused += 1


def _overlay(qapp, pt=12, w=1280, h=800):
    host = Host(pt, w, h)
    host.show()                      # el hijo sólo es visible si el padre lo es
    ov = ho.HelpOverlay(host)
    ov.resize(w, h)
    ov.show()
    ov.host = host                   # que el padre no se destruya al salir de acá
    return host, ov


def _press(ov, key):
    ov.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, key, NO))


@pytest.mark.parametrize('pt', [8, 12, 20, 33, 60])
def test_a_row_is_always_taller_than_its_text(qapp, pt):
    _, ov = _overlay(qapp, pt)
    font, _, _, row_h, _ = ov._metrics()
    assert row_h >= QFontMetrics(font).height()


@pytest.mark.parametrize('pt', [8, 12, 33, 60])
def test_the_help_text_never_gets_bigger_than_the_cap(qapp, pt):
    _, ov = _overlay(qapp, pt)
    font, *_ = ov._metrics()
    assert font.pointSize() <= ho.HELP_MAX_PT


def test_a_small_app_font_is_kept_not_inflated(qapp):
    _, ov = _overlay(qapp, 9)
    font, *_ = ov._metrics()
    assert font.pointSize() == 9


def test_the_key_column_fits_the_longest_key(qapp):
    _, ov = _overlay(qapp, 12)
    font, _, _, _, key_w = ov._metrics()
    fm = QFontMetrics(font)
    longest = max(fm.horizontalAdvance(k) for k, _ in ho.HELP)
    assert key_w >= min(longest, int(ov.width() * 0.45))


def test_the_key_column_never_takes_more_than_almost_half_the_width(qapp):
    _, ov = _overlay(qapp, 12, w=700)
    *_, key_w = ov._metrics()
    assert key_w <= int(700 * 0.45)


# ── desplazarse ──────────────────────────────────────────────────────────────

def test_the_whole_list_does_not_fit_on_a_short_screen_so_it_scrolls(qapp):
    _, ov = _overlay(qapp, 12, h=300)
    assert ov._max_scroll() > 0


def test_a_tall_screen_needs_no_scroll(qapp):
    _, ov = _overlay(qapp, 9, h=4000)
    assert ov._max_scroll() == 0


def test_down_scrolls_instead_of_closing_when_there_is_more(qapp):
    _, ov = _overlay(qapp, 12, h=300)
    _press(ov, Qt.Key.Key_Down)
    assert ov.isVisible() and ov._scroll > 0


def test_up_scrolls_back_and_never_goes_above_the_top(qapp):
    _, ov = _overlay(qapp, 12, h=300)
    _press(ov, Qt.Key.Key_Up)
    assert ov._scroll == 0 and ov.isVisible()
    _press(ov, Qt.Key.Key_Down)
    _press(ov, Qt.Key.Key_Up)
    assert ov._scroll == 0


def test_page_down_scrolls_a_screenful_and_stops_at_the_end(qapp):
    _, ov = _overlay(qapp, 12, h=300)
    _press(ov, Qt.Key.Key_PageDown)
    assert ov._scroll > 0
    for _ in range(100):
        _press(ov, Qt.Key.Key_PageDown)
    assert ov._scroll == ov._max_scroll() and ov.isVisible()


def test_home_and_end_jump_to_the_ends(qapp):
    _, ov = _overlay(qapp, 12, h=300)
    _press(ov, Qt.Key.Key_End)
    assert ov._scroll == ov._max_scroll()
    _press(ov, Qt.Key.Key_Home)
    assert ov._scroll == 0


def test_the_mouse_wheel_scrolls(qapp):
    _, ov = _overlay(qapp, 12, h=300)
    ev = QWheelEvent(QPointF(10, 10), QPointF(10, 10), QPoint(0, 0), QPoint(0, -120),
                     Qt.MouseButton.NoButton, NO, Qt.ScrollPhase.NoScrollPhase, False)
    ov.wheelEvent(ev)
    assert ov._scroll > 0


def test_any_other_key_closes_and_gives_the_focus_back(qapp):
    host, ov = _overlay(qapp, 12, h=300)
    _press(ov, Qt.Key.Key_Down)
    _press(ov, Qt.Key.Key_Escape)
    assert not ov.isVisible() and host.refocused == 1


def test_with_nothing_to_scroll_the_arrows_close_like_any_key(qapp):
    host, ov = _overlay(qapp, 9, h=4000)
    _press(ov, Qt.Key.Key_Down)
    assert not ov.isVisible()


def test_opening_it_again_starts_from_the_top(qapp):
    host, ov = _overlay(qapp, 12, h=300)
    _press(ov, Qt.Key.Key_End)
    ov.hide()
    ov.toggle()
    assert ov._scroll == 0


def test_it_paints_at_every_size_without_crashing(qapp):
    for pt in (9, 33, 60):
        _, ov = _overlay(qapp, pt, h=500)
        _press(ov, Qt.Key.Key_PageDown)
        assert not ov.grab().isNull()

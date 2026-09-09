"""El renglón de F1 recortado al círculo por una máscara, no por pintura negra.

Antes lo recortaba EdgeFade tapando con negro opaco lo que caía afuera del
círculo. Funcionaba mientras el fondo fuera negro sólido; con el fondo
transparente ese negro deja de tapar y la letra grande se vuelve a desparramar.
Una máscara recorta de verdad: lo de afuera no se dibuja, con cualquier opacidad.
"""
import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication, QWidget, QLineEdit
from PyQt6.QtCore import QPoint

from new_interface import FullscreenCircleApp as App
from views import EdgeFade


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


class _Fake(QWidget):
    """Lo mínimo que _clip_entry_to_circle toca."""
    def __init__(self, view):
        super().__init__()
        self.current_view = view
        self.entry = QLineEdit(self)


def _clip(qapp, view, x, y, ew, eh, w=1000, h=800):
    app = _Fake(view)
    app.entry.setFixedSize(ew, eh)
    app.entry.move(x, y)
    App._clip_entry_to_circle(app, x, y, ew, eh, w, h)
    return app


def test_outside_f1_there_is_no_mask(qapp):
    """F2/F3/F4 no tienen círculo: recortar ahí sería comerse el texto."""
    app = _clip(qapp, 1, 300, 390, 400, 24)
    assert app.entry.mask().isEmpty()


def test_a_short_line_through_the_middle_is_untouched(qapp):
    """A la altura del centro el círculo es ancho: no hay nada que recortar."""
    app = _clip(qapp, 0, 400, 390, 200, 20)
    m = app.entry.mask()
    assert not m.isEmpty()
    assert m.contains(QPoint(0, 10)) and m.contains(QPoint(199, 10))


def test_a_tall_line_loses_its_corners(qapp):
    """El caso que rompía: con la letra grande el renglón es alto, y arriba y
    abajo el círculo se angosta. Las esquinas tienen que quedar afuera."""
    w = h = 800
    r = min(w, h) // 2 - EdgeFade.CIRCLE_INSET     # 365
    ew, eh = 2 * r, 300                            # tan ancho como el círculo
    x, y = w // 2 - ew // 2, h // 2 - eh // 2
    app = _clip(qapp, 0, x, y, ew, eh, w, h)
    m = app.entry.mask()
    assert m.contains(QPoint(ew // 2, eh // 2)), 'el centro se tiene que ver'
    assert not m.contains(QPoint(0, 0)), 'la esquina de arriba a la izquierda cae afuera'
    assert not m.contains(QPoint(ew - 1, 0)), 'la de arriba a la derecha también'
    assert not m.contains(QPoint(0, eh - 1))
    assert not m.contains(QPoint(ew - 1, eh - 1))


def test_the_mask_is_centred_on_the_circle_not_on_the_entry(qapp):
    """El renglón puede estar corrido (typewriter lo alinea a la derecha). La
    máscara sigue al círculo de la ventana, no al renglón."""
    w = h = 1000
    r = min(w, h) // 2 - EdgeFade.CIRCLE_INSET        # 465
    ew, eh = 900, 200
    x, y = 0, h // 2 - eh // 2                        # renglón corrido a la izquierda
    app = _clip(qapp, 0, x, y, ew, eh, w, h)
    m = app.entry.mask()
    cx, cy = w // 2 - x, h // 2 - y                   # el círculo: (500, 100)

    assert m.contains(QPoint(cx, cy)), 'el centro del círculo se tiene que ver'
    # Este punto es el que distingue: está a 490 del centro del CÍRCULO (afuera,
    # r=465) pero a sólo 440 del centro del RENGLÓN, que está en 450. Si la
    # máscara siguiera al renglón, caería adentro.
    assert not m.contains(QPoint(10, cy)), 'la máscara está centrada en el renglón'
    assert r == 465 and abs(cx - ew // 2) == 50       # la geometría del caso


def test_a_degenerate_window_does_not_crash(qapp):
    """Durante el arranque la ventana puede medir 0: no puede explotar."""
    app = _clip(qapp, 0, 0, 0, 0, 0, 0, 0)
    assert app.entry.mask().isEmpty()

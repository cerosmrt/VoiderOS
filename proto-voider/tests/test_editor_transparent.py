"""El renglón que estás editando en F2 también se transparenta.

Cabo suelto del cambio de opacidad (b9457b0): _apply_editor_style escribía
"background-color: black" a pelo, así que con el fondo bajado todo se
transparentaba menos ese rectángulo en el medio.

Y no alcanzaba con ponerlo transparente: paintEvent evitaba dibujar la línea
del centro sólo cuando NO estabas parado en un punto. Sobre un punto la dibujan
los dos, y el negro opaco lo tapaba. Al volverlo transparente se veía duplicado.
"""
import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication, QLineEdit

from new_interface import FullscreenCircleApp as App
from circular_view import CircularView


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


class _Win:
    """Una ventana mínima con los dos ejes de opacidad."""
    def __init__(self, ink=1.0):
        self.opacity, self.ink_opacity = 1.0, ink


def _style(qapp, red=False, ink=1.0):
    ed = QLineEdit()
    app = _Win(ink)
    App._apply_editor_style(app, ed, red=red)
    return ed.styleSheet()


# ── el fondo ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("red", [False, True])
def test_the_editor_background_is_transparent(qapp, red):
    s = _style(qapp, red=red)
    assert "background: transparent" in s
    assert "background-color: black" not in s, 'el negro opaco es justo el bug'


@pytest.mark.parametrize("red", [False, True])
def test_the_text_follows_the_ink_axis(qapp, red):
    """Ctrl+Shift+± tiene que atenuar también lo que estás escribiendo."""
    opaco = _style(qapp, red=red, ink=1.0)
    tenue = _style(qapp, red=red, ink=0.4)
    assert opaco != tenue, 'la tinta no llega al editor de F2'
    assert "255)" in opaco or "1.0" in opaco


def test_the_red_marker_is_still_red(qapp):
    """El ø sigue siendo rojo: es un marcador, no decoración."""
    s = _style(qapp, red=True)
    assert "255, 40, 40" in s or "255,40,40" in s


# ── quién dibuja la línea del centro ─────────────────────────────────────────

class TestCenterLineOwnership:
    """En modo edición el widget del editor ES la línea del centro. paintEvent
    no la tiene que dibujar nunca — ni sobre un punto."""

    def _alpha(self, i, on_dot, edit_mode=True, base=1.0, highlight=None):
        return CircularView.edit_alpha(
            i, on_dot, base, highlight if highlight is not None else set(),
            edit_mode)

    def test_the_center_is_never_painted_while_editing(self):
        assert self._alpha(0, on_dot=False) == 0.0
        assert self._alpha(0, on_dot=True, highlight={0, 1, 2}) == 0.0

    def test_the_paragraph_under_a_dot_stays_lit(self):
        assert self._alpha(1, on_dot=True, highlight={0, 1, 2}) == 1.0

    def test_lines_outside_the_paragraph_are_dimmed(self):
        assert self._alpha(5, on_dot=True, highlight={0, 1, 2}) == pytest.approx(0.3)

    def test_neighbours_are_dimmed_on_a_content_line(self):
        assert self._alpha(3, on_dot=False) == pytest.approx(0.3)

    def test_outside_edit_mode_the_center_is_painted_normally(self):
        assert self._alpha(0, on_dot=False, edit_mode=False) == 1.0

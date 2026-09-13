"""El panel se dibuja igual que la lista de F3.

Federico: "fijate como se muestra en f3 y replicalo. ahora se ven diferentes".
Tenía razón, y eran tres diferencias concretas:

  * la FUENTE: F3 usa la de la app, el panel usaba una dos puntos más chica.
  * el ESPACIADO: F3 separa los renglones a 1.31 veces el alto de la letra
    (CircularView.LINE_SPACING), el panel usaba 1.9.
  * la ATENUACIÓN: F3 apaga con una curva coseno según la distancia al centro,
    que llega a cero en los bordes; el panel tenía dos tonos planos (blanco y
    gris), que es lo que le habíamos puesto el paso anterior.

Ahora comparten la función: ring_alpha vive en widgets y la usan los dos.
CircularView.calculate_alpha delega ahí, así no puede volver a divergir —
cualquier cambio en la curva de F3 se ve en el panel y al revés.
"""
import math
import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont, QFontMetrics

from widgets import ring_alpha, picker_line_height
from circular_view import CircularView
from line_ring import LineRing


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


_vivos = []


# ── la curva es la misma ─────────────────────────────────────────────────────

def test_the_centre_is_full():
    assert ring_alpha(0, 400) == 1.0


def test_it_reaches_zero_at_the_edge():
    assert ring_alpha(400, 400) == 0.0
    assert ring_alpha(900, 400) == 0.0


def test_it_is_a_cosine_not_a_straight_line():
    """A media distancia el coseno da 0.707, una recta daría 0.5."""
    assert ring_alpha(200, 400) == pytest.approx(math.cos(math.pi / 4), abs=1e-6)


def test_a_window_with_no_height_does_not_divide_by_zero():
    assert ring_alpha(10, 0) == 1.0


def test_f3_delegates_to_the_shared_curve(qapp):
    """Si F3 se quedara con su propia copia, volverían a divergir."""
    v = CircularView(LineRing(['.', 'a.']))
    v.resize(1200, 800)
    _vivos.append(v)
    for d in (0, 50, 200, 399, 500):
        assert v.calculate_alpha(d) == pytest.approx(ring_alpha(d, 400))


# ── el espaciado es el mismo ─────────────────────────────────────────────────

def test_the_line_height_matches_f3(qapp):
    f = QFont('Consolas', 13)
    v = CircularView(LineRing(['.', 'a.']))
    v.setFont(f)
    v.resize(1200, 800)
    _vivos.append(v)
    assert picker_line_height(f) == v.line_height


def test_it_follows_the_font_size(qapp):
    chica = picker_line_height(QFont('Consolas', 9))
    grande = picker_line_height(QFont('Consolas', 30))
    assert grande > chica, 'el espaciado tiene que seguir a la fuente, como en F3'


def test_it_is_never_zero(qapp):
    assert picker_line_height(QFont('Consolas', 1)) >= 1


# ── y el panel los usa ───────────────────────────────────────────────────────

def test_the_picker_uses_the_shared_curve():
    """row_alpha compone la curva del anillo con el factor de atenuación; las
    dos piezas son las mismas que usa F3."""
    import inspect
    from widgets import draw_chapter_picker, row_alpha
    src = inspect.getsource(draw_chapter_picker)
    assert 'row_alpha' in src, 'el panel sigue con su propia atenuación'
    assert 'ring_alpha' in inspect.getsource(row_alpha)
    assert 'picker_line_height' in src, 'el panel sigue con su propio espaciado'


def test_the_picker_does_not_shrink_the_font():
    """F3 usa la fuente de la app; el panel usaba una dos puntos más chica."""
    import inspect
    from widgets import draw_chapter_picker
    src = inspect.getsource(draw_chapter_picker)
    assert 'pointSize() - 2' not in src


def test_it_still_paints(qapp):
    """Que el cambio de layout no rompa el dibujo."""
    from PyQt6.QtGui import QPixmap, QColor
    v = CircularView(LineRing(['.', 'una linea.']))
    v.resize(1200, 800)
    v.set_picker_state(True, '', [f'Capitulo {i}' for i in range(40)],
                       20, False, '', 'right')
    _vivos.append(v)
    v.render(QPixmap(1200, 800))

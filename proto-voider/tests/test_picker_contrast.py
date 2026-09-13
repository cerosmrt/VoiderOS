"""En el panel se tiene que ver cuál está elegida.

Dos pasadas en falso antes de esto, las dos mías:
  * primero puse dos tonos planos (blanco / gris). Federico: "ahora se ven
    diferentes" — no se parecía a F3.
  * después copié la curva coseno de F3 sola, y quedó peor: "esta todo blanco
    no se que esta highlitghteado". La curva es muy plana cerca del centro —
    a un renglón de distancia da 0.975.

Lo que me faltaba: en F3 la curva NO es lo único. edit_alpha multiplica además
por 0.3 todo lo que no es la línea del centro (circular_view.py). Ese factor es
el que da el contraste; la curva sola sirve para el desvanecido hacia los
bordes, no para marcar cuál es la elegida.

Ahora el factor vive en widgets.DIM_FACTOR y lo usan los dos.
"""
import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication

from widgets import ring_alpha, row_alpha, DIM_FACTOR
from circular_view import CircularView


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def test_the_selected_row_is_full():
    assert row_alpha(0, 400) == 1.0


def test_a_neighbour_is_clearly_dimmer():
    """El caso que falló: a un renglón (57px) la curva sola daba 0.975."""
    a = row_alpha(57, 400)
    assert a < 0.45, f'el vecino queda en {a:.3f} — indistinguible del elegido'


def test_the_contrast_is_big_enough_to_see():
    assert row_alpha(0, 400) - row_alpha(57, 400) > 0.5


def test_it_still_fades_towards_the_edges():
    """El desvanecido del anillo se conserva: no es un gris plano."""
    assert row_alpha(57, 400) > row_alpha(200, 400) > row_alpha(380, 400)


def test_it_is_the_curve_times_the_factor():
    for d in (57, 150, 300):
        assert row_alpha(d, 400) == pytest.approx(ring_alpha(d, 400) * DIM_FACTOR)


def test_f3_uses_the_same_factor():
    """Si F3 se queda con su 0.3 escrito a mano, vuelven a divergir."""
    base = 1.0
    assert CircularView.edit_alpha(3, False, base, set()) == pytest.approx(
        base * DIM_FACTOR)


def test_the_picker_uses_row_alpha():
    import inspect
    from widgets import draw_chapter_picker
    assert 'row_alpha' in inspect.getsource(draw_chapter_picker)

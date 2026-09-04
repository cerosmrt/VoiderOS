"""F1 typewriter: el texto se apaga hacia el borde del círculo.

Dos problemas que resuelve la misma capa:
  * con la letra grande, el renglón se salía del círculo;
  * sólo debería leerse nítido lo que estás escribiendo ahora.

Al llegar a negro justo contra el borde, lo que sobresale deja de verse: el
degradado ES el recorte.
"""
import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPixmap, QColor
from PyQt6.QtCore import Qt

from views import EdgeFade


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def _render(w, width=400, height=60):
    w.resize(width, height)
    pm = QPixmap(width, height)
    pm.fill(QColor("white"))   # fondo blanco: lo que pinte la capa se nota
    w.render(pm)
    return pm.toImage()


def test_el_borde_queda_negro(qapp):
    img = _render(EdgeFade())
    c = QColor(img.pixel(1, 30))
    assert c.red() < 30 and c.green() < 30, f"el borde no se apagó: {c.red()}"


def test_el_centro_queda_limpio(qapp):
    img = _render(EdgeFade())
    c = QColor(img.pixel(398, 30))
    assert c.red() > 200, f"el centro se ensució: {c.red()}"


def test_es_un_degrade_y_no_un_corte(qapp):
    """Lo que pidió Federico: más cerca del círculo, más negro. Progresivo."""
    img = _render(EdgeFade())
    muestras = [QColor(img.pixel(x, 30)).red() for x in (1, 60, 120, 180)]
    assert muestras == sorted(muestras), f"no crece parejo: {muestras}"
    assert muestras[-1] > muestras[0], "no hay degradado"


def test_no_se_come_los_clicks(qapp):
    """Es una capa de pintura: si robara el mouse, no podrías tocar el texto."""
    w = EdgeFade()
    assert w.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)


def test_no_roba_el_foco(qapp):
    w = EdgeFade()
    assert w.focusPolicy() == Qt.FocusPolicy.NoFocus


def test_arranca_escondida(qapp):
    """Sólo aparece en F1 typewriter; en cualquier otro lado estorbaría."""
    assert not EdgeFade().isVisible()


def test_no_rompe_con_tamano_cero(qapp):
    w = EdgeFade()
    w.resize(0, 0)
    w.render(QPixmap(1, 1))   # no debe explotar

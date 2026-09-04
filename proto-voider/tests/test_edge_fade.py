"""F1 typewriter: el texto se apaga hacia el borde del círculo.

Dos problemas que resuelve la misma capa:
  * con la letra grande, el renglón se salía del círculo;
  * sólo debería leerse nítido lo que estás escribiendo.

Al llegar a negro justo contra el borde, lo que sobresale deja de verse: el
degradado ES el recorte.

Y un tercero, que apareció al probarlo: el rectángulo negro tapaba el TRAZO del
círculo por la izquierda y se veía cortado. La capa tiene que apagar el texto,
no el borde que lo contiene, así que redibuja el círculo encima del degradado.
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


W, H = 600, 400


def _render(fondo="white", entry=True):
    w = EdgeFade()
    w.resize(W, H)
    if entry:
        # Un renglón como el de typewriter: del borde del círculo al centro.
        r = min(W, H) // 2 - EdgeFade.CIRCLE_INSET
        w.set_entry_rect(W // 2 - r, H // 2 - 20, r, 40)
    pm = QPixmap(W, H)
    pm.fill(QColor(fondo))
    w.render(pm)
    return pm.toImage()


def _rojo(img, x, y):
    return QColor(img.pixel(x, y)).red()


def test_el_texto_se_apaga_contra_el_borde(qapp):
    img = _render()
    r = min(W, H) // 2 - EdgeFade.CIRCLE_INSET
    izq = W // 2 - r
    # Adentro del trazo del círculo (pluma de 10px → ±5), no encima de él.
    assert _rojo(img, izq + 9, H // 2) < 60, "el renglón no se apagó cerca del borde"


def test_el_centro_del_renglon_queda_limpio(qapp):
    img = _render()
    assert _rojo(img, W // 2 - 5, H // 2) > 200, "se ensució el centro"


def test_es_un_degrade_progresivo_y_no_un_corte(qapp):
    img = _render()
    r = min(W, H) // 2 - EdgeFade.CIRCLE_INSET
    izq = W // 2 - r
    muestras = [_rojo(img, izq + d, H // 2) for d in (9, 40, 80, 120)]
    assert muestras == sorted(muestras), f"no crece parejo: {muestras}"
    assert muestras[-1] > muestras[0], "no hay degradado"


def test_el_circulo_sobrevive_al_degrade(qapp):
    """La regresión que Federico vio: el negro se comía el trazo del círculo.

    Sobre fondo NEGRO el trazo blanco tiene que seguir estando en el borde
    izquierdo, que es justo donde el degradado es más oscuro.
    """
    img = _render(fondo="black")
    r = min(W, H) // 2 - EdgeFade.CIRCLE_INSET
    izq = W // 2 - r
    # Barrer unos pocos píxeles alrededor del borde: el trazo tiene ancho.
    tramo = [_rojo(img, x, H // 2) for x in range(izq - 8, izq + 9)]
    assert max(tramo) > 180, f"el círculo desapareció bajo el degradado: {max(tramo)}"


def test_el_circulo_se_dibuja_aunque_no_haya_renglon(qapp):
    img = _render(fondo="black", entry=False)
    r = min(W, H) // 2 - EdgeFade.CIRCLE_INSET
    tramo = [_rojo(img, x, H // 2) for x in range(W // 2 - r - 8, W // 2 - r + 9)]
    assert max(tramo) > 180


def test_no_se_come_los_clicks(qapp):
    assert EdgeFade().testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)


def test_no_roba_el_foco(qapp):
    assert EdgeFade().focusPolicy() == Qt.FocusPolicy.NoFocus


def test_arranca_escondida(qapp):
    assert not EdgeFade().isVisible()


def test_no_rompe_con_tamano_cero(qapp):
    w = EdgeFade()
    w.resize(0, 0)
    w.render(QPixmap(1, 1))


def test_nada_se_ve_fuera_del_circulo(qapp):
    """Lo que Federico vio: con la letra grande, las letras desbordaban.

    El renglón es un rectángulo y el círculo es redondo — arriba y abajo del
    centro el círculo se angosta, así que las puntas del renglón caen AFUERA.
    Tapar el exterior lo recorta de verdad, a cualquier tamaño de fuente.

    Sobre fondo blanco: todo lo de afuera del círculo tiene que quedar negro.
    """
    img = _render(fondo="white")
    r = min(W, H) // 2 - EdgeFade.CIRCLE_INSET
    cx, cy = W // 2, H // 2
    # Puntos claramente afuera: las cuatro esquinas y los costados lejanos.
    afuera = [(5, 5), (W - 5, 5), (5, H - 5), (W - 5, H - 5), (2, cy), (W - 3, cy)]
    for x, y in afuera:
        assert _rojo(img, x, y) < 30, f"se ve algo fuera del círculo en ({x},{y})"


def test_la_esquina_del_renglon_no_desborda(qapp):
    """El caso exacto del bug: un renglón ALTO (letra grande). Su esquina
    superior izquierda cae fuera del círculo, y no se tiene que ver."""
    w = EdgeFade()
    w.resize(W, H)
    r = min(W, H) // 2 - EdgeFade.CIRCLE_INSET
    # Renglón de 160px de alto, como con fuente enorme.
    w.set_entry_rect(W // 2 - r, H // 2 - 80, r, 160)
    pm = QPixmap(W, H)
    pm.fill(QColor("white"))
    w.render(pm)
    img = pm.toImage()
    # Arriba a la izquierda del renglón: dentro del rectángulo, fuera del círculo.
    x, y = W // 2 - r + 4, H // 2 - 78
    assert QColor(img.pixel(x, y)).red() < 30, "la esquina del renglón desborda"


def test_adentro_del_circulo_sigue_viendose(qapp):
    """El recorte no puede tapar de más: el centro tiene que seguir limpio."""
    img = _render(fondo="white")
    assert _rojo(img, W // 2 - 5, H // 2) > 200

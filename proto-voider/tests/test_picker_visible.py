"""El panel de capítulos no puede heredar la opacidad de la última línea.

EL BUG: paintEvent dibuja las líneas del anillo con painter.setOpacity(alpha)
—se atenúan con la distancia al centro— y nunca lo resetea. El panel se dibuja
DESPUÉS, así que salía con la opacidad de la última línea del bucle, que es la
más lejana y por lo tanto casi cero. Federico: "no se ve la letra man".

Por qué no lo agarró el test de pintura anterior: usaba un anillo de dos
líneas. Con pocas líneas el bucle termina con opacidad alta y el panel se ve
igual. Hace falta un anillo largo, como su archivo real, para que la última
línea dibujada quede tenue. Eso es lo que hace este test.
"""
import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPixmap, QColor

from circular_view import CircularView
from line_ring import LineRing


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


_vivos = []


def _opacidad_al_dibujar_el_panel(n_lineas, edit_mode=True):
    """La opacidad que tiene el painter en el momento exacto en que se dibuja
    el panel. Es la medicion que importa: medir el brillo del pixmap renderizado
    no sirve — el fondo del widget lo domina y da el mismo numero con panel y
    sin panel."""
    import widgets
    visto = []
    real = widgets.draw_chapter_picker

    def espia(painter, *a, **k):
        visto.append(painter.opacity())
        return real(painter, *a, **k)

    widgets.draw_chapter_picker = espia
    try:
        lineas = ['.'] + [f'linea {i} con texto suficiente' for i in range(n_lineas)]
        v = CircularView(LineRing(lineas))
        v.ring.index = len(lineas) // 2
        v.edit_mode = edit_mode
        v.resize(1200, 800)
        v.set_picker_state(True, '', [f'Capitulo {i}' for i in range(30)],
                           15, False, '', 'right')
        _vivos.append(v)
        pm = QPixmap(1200, 800)
        pm.fill(QColor(0, 0, 0))
        v.render(pm)
    finally:
        widgets.draw_chapter_picker = real
    return visto[0] if visto else None


def test_the_picker_paints_at_full_opacity(qapp):
    """EL BUG, medido: sin el reset el painter llegaba al panel con 0.016 — el
    1,6%. Todo lo que dibujaba salia invisible."""
    op = _opacidad_al_dibujar_el_panel(400)
    assert op is not None, 'el panel no se dibujo'
    assert op > 0.99, f'el panel se dibuja al {op:.1%} de opacidad'


def test_it_holds_with_a_short_ring_too(qapp):
    assert _opacidad_al_dibujar_el_panel(3) > 0.99


def test_it_holds_outside_edit_mode(qapp):
    assert _opacidad_al_dibujar_el_panel(400, edit_mode=False) > 0.99



def _opacidad_al_dibujar_el_panel(n_lineas, edit_mode=True):
    """La opacidad que tiene el painter en el momento exacto en que se dibuja
    el panel. Es la medicion que importa: medir el brillo del pixmap renderizado
    no sirve — el fondo del widget lo domina y da el mismo numero con panel y
    sin panel."""
    import widgets
    visto = []
    real = widgets.draw_chapter_picker

    def espia(painter, *a, **k):
        visto.append(painter.opacity())
        return real(painter, *a, **k)

    widgets.draw_chapter_picker = espia
    try:
        lineas = ['.'] + [f'linea {i} con texto suficiente' for i in range(n_lineas)]
        v = CircularView(LineRing(lineas))
        v.ring.index = len(lineas) // 2
        v.edit_mode = edit_mode
        v.resize(1200, 800)
        v.set_picker_state(True, '', [f'Capitulo {i}' for i in range(30)],
                           15, False, '', 'right')
        _vivos.append(v)
        pm = QPixmap(1200, 800)
        pm.fill(QColor(0, 0, 0))
        v.render(pm)
    finally:
        widgets.draw_chapter_picker = real
    return visto[0] if visto else None


def test_the_picker_paints_at_full_opacity(qapp):
    """EL BUG, medido: sin el reset el painter llegaba al panel con 0.016 — el
    1,6%. Todo lo que dibujaba salia invisible."""
    op = _opacidad_al_dibujar_el_panel(400)
    assert op is not None, 'el panel no se dibujo'
    assert op > 0.99, f'el panel se dibuja al {op:.1%} de opacidad'


def test_it_holds_with_a_short_ring_too(qapp):
    assert _opacidad_al_dibujar_el_panel(3) > 0.99


def test_it_holds_outside_edit_mode(qapp):
    assert _opacidad_al_dibujar_el_panel(400, edit_mode=False) > 0.99



def _render(qapp, n_lineas, picker=True):
    lineas = ['.'] + [f'linea numero {i} con texto suficiente' for i in range(n_lineas)]
    v = CircularView(LineRing(lineas))
    v.ring.index = len(lineas) // 2
    v.resize(1200, 800)
    v.set_picker_state(picker, '', [f'Capitulo {i}' for i in range(30)],
                       15, False, '', 'right')
    _vivos.append(v)
    pm = QPixmap(1200, 800)
    pm.fill(QColor(0, 0, 0))
    v.render(pm)
    return pm.toImage()


def _brillo_max(img, x0, x1):
    mx = 0
    for y in range(0, 800, 3):
        for x in range(x0, x1, 3):
            mx = max(mx, QColor(img.pixel(x, y)).red())
    return mx


def test_the_lines_themselves_still_fade(qapp):
    """No arreglarlo poniendo todo opaco: las lineas se tienen que seguir
    atenuando con la distancia al centro, que es el efecto del anillo.

    Se prueba calculate_alpha, que es la funcion pura que decide eso. Espiar
    QPainter.setOpacity seria mas directo pero reemplazar un metodo de PyQt a
    nivel de clase tira un core dump — probado.
    """
    v = CircularView(LineRing(['.', 'una.', 'otra.']))
    v.resize(1200, 800)
    _vivos.append(v)
    centro = v.calculate_alpha(0)
    medio = v.calculate_alpha(200)
    lejos = v.calculate_alpha(390)
    assert centro > 0.99, 'la linea del centro va entera'
    assert medio < centro, 'tiene que atenuarse con la distancia'
    assert lejos < medio
    assert lejos < 0.1, 'las del borde tienen que llegar a casi nada'

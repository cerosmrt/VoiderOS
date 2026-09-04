"""Ctrl+± cambia la opacidad de la ventana.

La función existía pero podía no responder: `Ctrl++` no matchea en teclados
donde `+` es Shift+`=` (como el layout GB de esta máquina). Ahí apretar Ctrl y +
manda Ctrl+Shift+=, y sólo bajar la opacidad funcionaba. Por eso se registran
las tres formas.

Y no bajaba con piso: llegaba a 0.0, o sea ventana invisible — y las teclas para
volver a subirla también invisibles.
"""
import pytest

pytest.importorskip("PyQt6")

from new_interface import FullscreenCircleApp as App


def test_no_se_puede_desaparecer_la_ventana():
    """Una ventana que no se ve es una ventana que no se puede recuperar."""
    assert App._clamp_opacity(0.0) >= App.OPACITY_MIN
    assert App._clamp_opacity(-5) >= App.OPACITY_MIN


def test_no_pasa_de_opaco():
    assert App._clamp_opacity(1.5) == 1.0
    assert App._clamp_opacity(1.0) == 1.0


def test_los_valores_del_medio_pasan_intactos():
    assert App._clamp_opacity(0.6) == pytest.approx(0.6)


def test_el_piso_deja_ver_lo_suficiente():
    """Si el piso fuera muy bajo no serviría de nada como salvavidas."""
    assert App.OPACITY_MIN >= 0.15, "demasiado transparente para recuperarla"
    assert App.OPACITY_MIN <= 0.5, "demasiado alto, no deja atenuar de verdad"


def test_se_registran_las_variantes_de_teclado_para_subir():
    """El bug real: en layout GB, '+' es Shift+'=' y Ctrl++ no matchea."""
    import inspect
    src = inspect.getsource(App._setup_opacity_shortcuts)
    assert "Ctrl+=" in src, "sin esta variante, subir la opacidad no responde"
    assert "Ctrl++" in src
    assert "Ctrl+-" in src

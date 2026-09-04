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


def test_se_le_pide_a_hyprland_no_solo_a_qt():
    """Qt no puede en Wayland: imprime "This plugin does not support setting
    window opacity" y no pasa nada. La opacidad la decide el compositor.

    Se sigue llamando setWindowOpacity porque es lo correcto donde SÍ funciona
    (X11), pero además hay que pedírselo a Hyprland.
    """
    import inspect
    src = inspect.getsource(App._apply_opacity)
    assert "hyprctl" in src, "sin esto no pasa nada en Wayland"
    assert "setWindowOpacity" in src, "no hay que perder el camino que sí anda en X11"


def test_usa_alphaoverride():
    """Sin alphaoverride, Hyprland multiplica nuestro alpha por su regla global
    y el efecto casi no se nota."""
    import inspect
    assert "alphaoverride" in inspect.getsource(App._apply_opacity)


def test_sin_hyprland_no_se_rompe():
    """En otro escritorio, o en una VM, hyprctl no existe. Eso no es un error:
    la opacidad es un accesorio y no puede impedir escribir."""
    import inspect
    src = inspect.getsource(App._apply_opacity)
    assert "except" in src and "pass" in src

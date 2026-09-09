"""Opacidad en dos ejes.

Antes había uno solo: le pedíamos a Hyprland que bajara el alpha de TODA la
ventana, así que al atenuar el fondo se atenuaba también el texto. Ahora la
transparencia la pintamos nosotros y son dos valores independientes:

    Ctrl+ + / -         el FONDO (el negro). El blanco no se toca.
    Ctrl+Shift+ + / -   la TINTA (el círculo y las letras).

Los dos con piso: ni una ventana invisible ni un texto invisible, porque las
teclas para recuperarlos también serían invisibles.
"""
import pytest

pytest.importorskip("PyQt6")

from new_interface import FullscreenCircleApp as App


# ── los pisos ────────────────────────────────────────────────────────────────

def test_no_se_puede_desaparecer_el_fondo():
    assert App._clamp_opacity(0.0) >= App.OPACITY_MIN
    assert App._clamp_opacity(-5) >= App.OPACITY_MIN


def test_no_se_puede_desaparecer_la_tinta():
    """Un texto invisible no se puede volver a subir: no lo ves para saber dónde."""
    assert App._clamp_ink(0.0) >= App.INK_MIN
    assert App._clamp_ink(-5) >= App.INK_MIN


def test_ninguno_pasa_de_opaco():
    assert App._clamp_opacity(1.5) == 1.0
    assert App._clamp_ink(1.5) == 1.0


def test_los_valores_del_medio_pasan_intactos():
    assert App._clamp_opacity(0.6) == pytest.approx(0.6)
    assert App._clamp_ink(0.6) == pytest.approx(0.6)


def test_los_pisos_son_razonables():
    assert 0.0 <= App.OPACITY_MIN <= 0.5, "el fondo tiene que poder atenuarse de verdad"
    assert 0.1 <= App.INK_MIN <= 0.5, "la tinta tiene que seguir siendo legible"


# ── el color que sale de cada eje ────────────────────────────────────────────

def test_el_fondo_es_negro_con_el_alpha_del_fondo():
    c = App._bg_color(0.5)
    assert (c.red(), c.green(), c.blue()) == (0, 0, 0)
    assert c.alpha() == 128          # 0.5 * 255 = 127.5, redondeado


def test_la_tinta_es_blanca_con_el_alpha_de_la_tinta():
    c = App._ink_color(1.0)
    assert (c.red(), c.green(), c.blue()) == (255, 255, 255)
    assert c.alpha() == 255
    assert App._ink_color(0.5).alpha() == 128


def test_bajar_el_fondo_no_toca_la_tinta():
    """El pedido entero: atenuar el negro dejando el blanco intacto."""
    assert App._ink_color(1.0).alpha() == 255
    assert App._bg_color(0.3).alpha() < 255


# ── las teclas ───────────────────────────────────────────────────────────────

def test_se_registran_las_variantes_de_teclado_para_el_fondo():
    """En layout GB '+' es Shift+'=' y Ctrl++ solo no matchea."""
    import inspect
    src = inspect.getsource(App._setup_opacity_shortcuts)
    assert "Ctrl+=" in src
    assert "Ctrl++" in src
    assert "Ctrl+-" in src


def test_la_tinta_tiene_su_propio_par_de_teclas():
    import inspect
    src = inspect.getsource(App._setup_opacity_shortcuts)
    assert "_change_ink" in src, "Ctrl+Shift+± no está cableado a la tinta"
    assert "ShiftModifier" in src, "la tinta se registra con Shift explícito"


# ── ya no se le pide al compositor que atenúe todo ───────────────────────────

def test_hyprland_ya_no_atenua_la_ventana_entera():
    """Ese era el bug: el compositor bajaba el alpha de todo, texto incluido.
    Ahora se le pide lo contrario — que NO toque nada — y el alpha lo pintamos."""
    import inspect
    src = inspect.getsource(App._apply_opacity)
    assert "alphaoverride" in src, "sin esto Hyprland multiplica por su regla global"
    assert "'1'" in src or '"1"' in src, "hay que fijarle alpha 1 y pintar nosotros"


def test_la_ventana_es_translucida_de_verdad():
    """Sin WA_TranslucentBackground el alpha que pintamos no se ve: Qt pide un
    visual sin canal alfa y el compositor no tiene qué componer."""
    import inspect
    src = inspect.getsource(App.__init__)
    assert "WA_TranslucentBackground" in src


def test_sin_hyprland_no_se_rompe():
    import inspect
    src = inspect.getsource(App._apply_opacity)
    assert "except" in src and "pass" in src


def test_se_le_pide_a_hyprland_que_no_bluree():
    """Contra de haber hecho la ventana translúcida: Hyprland trae el blur
    prendido de fábrica y sólo actúa donde una ventana deja pasar lo de atrás.
    Con la superficie opaca no tenía nada que blurear; al volverla translúcida
    el fondo se veía borroso. La gracia de la transparencia es ver lo de atrás
    nítido."""
    import inspect
    assert "noblur" in inspect.getsource(App._apply_opacity)

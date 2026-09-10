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


# ── los límites ──────────────────────────────────────────────────────────────
# Sin piso. Yo le había puesto 25% al fondo y 20% a la tinta por miedo a que se
# perdiera la ventana; él lo pidió sacar dos veces: "no deberia haber limitede
# trasnaprencia, que lleguie a 0". Es su pantalla. Y se recupera a ciegas: la
# transparencia no toca el foco, así que Ctrl++ sigue respondiendo aunque no se
# vea nada.

def test_el_fondo_llega_a_cero():
    assert App._clamp_opacity(0.0) == 0.0


def test_la_tinta_llega_a_cero():
    assert App._clamp_ink(0.0) == 0.0


def test_no_se_baja_de_cero():
    """0 ya es transparente del todo; más abajo no significa nada."""
    assert App._clamp_opacity(-5) == 0.0
    assert App._clamp_ink(-5) == 0.0


def test_ninguno_pasa_de_opaco():
    assert App._clamp_opacity(1.5) == 1.0
    assert App._clamp_ink(1.5) == 1.0


def test_los_valores_del_medio_pasan_intactos():
    assert App._clamp_opacity(0.6) == pytest.approx(0.6)
    assert App._clamp_ink(0.6) == pytest.approx(0.6)


def test_bajando_de_a_pasos_se_llega_exactamente_a_cero():
    """Diez pasos de 0.1 desde 1.0 dan 2.7e-16 en flotante, no 0. Tiene que
    terminar en 0 pelado, o "transparente del todo" no se alcanza nunca."""
    v = 1.0
    for _ in range(20):
        v = App._clamp_opacity(v - 0.1)
    assert v == 0.0


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


# ── los pasos son redondos ───────────────────────────────────────────────────
# "por que hace esto y no va de diez en deiz y chau?" — porque 0.7 + 0.1 en
# flotante da 0.7999999999999999, y ese ruido se acumula, se imprime truncado
# (int(0.8999*100) = 89) y encima se guarda así en config.json.

def test_los_pasos_caen_en_decimas_exactas():
    v = 0.0
    vistos = []
    for _ in range(10):
        v = App._step_value(v, 0.1, App._clamp_opacity)
        vistos.append(v)
    assert vistos == [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]


def test_bajar_tambien_cae_en_decimas_exactas():
    v = 1.0
    vistos = []
    for _ in range(10):
        v = App._step_value(v, -0.1, App._clamp_opacity)
        vistos.append(v)
    assert vistos == [0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1, 0.0]


def test_el_porcentaje_que_se_imprime_no_se_saltea_numeros():
    """Lo que él vio: 89% y 99% en vez de 90% y 100%."""
    v = 0.0
    pct = []
    for _ in range(10):
        v = App._step_value(v, 0.1, App._clamp_opacity)
        pct.append(App._as_pct(v))
    assert pct == [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]


def test_ir_y_volver_devuelve_el_mismo_valor():
    """Sin esto el ruido se acumula y nunca se vuelve al punto de partida."""
    v = 0.5
    for _ in range(20):
        v = App._step_value(v, 0.1, App._clamp_opacity)
    for _ in range(20):
        v = App._step_value(v, -0.1, App._clamp_opacity)
    assert v == 0.0


# ── la transparencia es de la sesión, no del archivo ─────────────────────────
# "tambien deberia arrancar al 100 cuando abro el programa". Antes se guardaba
# en config y volvía como la dejaste — lo que además hacía que un 0 sobreviviera
# al reinicio y Voider arrancara invisible. Ahora cada arranque empieza opaco.

def test_arranca_opaco_aunque_el_config_diga_otra_cosa():
    import inspect
    src = inspect.getsource(App.__init__)
    assert "self.opacity = 1.0" in src, "el fondo tiene que arrancar en 1.0 fijo"
    assert "self.ink_opacity = 1.0" in src
    assert 'config.get("opacity"' not in src, "no se lee del config"
    assert 'config.get("ink_opacity"' not in src


def test_no_se_guardan_en_el_config():
    """Si no se leen, guardarlos sólo ensucia config.json (y es un archivo
    committeado: cada cambio de opacidad sería ruido en git)."""
    import inspect
    for m in (App._change_opacity, App._change_ink):
        src = inspect.getsource(m)
        assert "config[" not in src, f"{m.__name__} sigue escribiendo el config"
        assert "_save_config" not in src

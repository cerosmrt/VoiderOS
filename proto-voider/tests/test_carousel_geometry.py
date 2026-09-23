"""F4 → carrusel de Instagram: geometría pura, sin Qt.

carousel_page_pt(w_px, h_px) inventa una página FÍSICA (en el mismo sistema de
puntos que A5_PT) con el ancho de A5 (148mm) y el alto que haga falta para que
la proporción coincida con w_px:h_px. Mismo ancho que A5 → misma tipografía,
márgenes e hifenación que ya están afinados; sólo cambia el alto.
"""
import pytest

import reading_page as rp


def test_width_matches_a5():
    w, h = rp.carousel_page_pt(1080, 1350)
    assert w == pytest.approx(rp.A5_PT[0])


def test_square_ratio_is_a_square_page():
    w, h = rp.carousel_page_pt(1080, 1080)
    assert h == pytest.approx(w)


def test_4_5_ratio_height():
    w, h = rp.carousel_page_pt(1080, 1350)
    assert h == pytest.approx(w * 1350 / 1080)


def test_landscape_ratio_is_shorter_than_wide():
    w, h = rp.carousel_page_pt(1080, 566)
    assert h < w


def test_presets_contain_the_three_instagram_ratios():
    assert rp.CAROUSEL_PRESETS['1:1'] == (1080, 1080)
    assert rp.CAROUSEL_PRESETS['4:5'] == (1080, 1350)
    assert rp.CAROUSEL_PRESETS['1.91:1'] == (1080, 566)

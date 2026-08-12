"""F1 typewriter mode (a toggle, off by default). When ON, the input spans from
the circle's left edge to the screen centre: the right-aligned caret sits on the
centre and text flows left, clipped at the circle (nothing shows outside it).
When OFF, the entry is centred as classic."""
import pytest

pytest.importorskip("PyQt6")
from new_interface import FullscreenCircleApp

_geom = FullscreenCircleApp._entry_geometry


def test_typewriter_caret_at_centre_and_clips_at_circle():
    # w=1000,h=800 → circle radius = min(1000,800)//2 - 35 = 365
    x, y, width = _geom(1000, 800, 40, True)
    assert x + width == 500           # caret (right edge) on the centre
    assert x == 500 - 365             # left edge = the circle's left edge (clip)
    assert width == 365
    assert y == 800 // 2 - 40 // 2


def test_typewriter_scales_with_size():
    x, _, width = _geom(1920, 1080, 50, True)
    assert x + width == 960           # caret on the centre of a 1920 screen
    assert width == min(1920, 1080) // 2 - 35


def test_classic_mode_is_centred():
    x, y, width = _geom(1000, 800, 40, False)
    assert width == min(1000, 800) - 90       # classic width
    assert x == (1000 - width) // 2           # centred horizontally
    assert y == 800 // 2 - 40 // 2


def test_degenerate_size_is_safe():
    _, _, width = _geom(0, 0, 0, True)
    assert width >= 1

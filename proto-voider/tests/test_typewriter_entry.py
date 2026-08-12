"""F1 typewriter entry: the input occupies the left half so its right edge —
where the caret sits with right-alignment — lands on the screen centre. Text
then flows left from that fixed point, like a typewriter."""
import pytest

pytest.importorskip("PyQt6")
from new_interface import FullscreenCircleApp


def test_right_edge_is_the_screen_centre():
    x, y, width = FullscreenCircleApp._entry_geometry(1000, 800, 40)
    assert x == 0                     # spans from the screen's left edge
    assert x + width == 500           # caret (right edge) at horizontal centre
    assert y == 800 // 2 - 40 // 2    # vertically centred


def test_scales_with_width():
    _, _, width = FullscreenCircleApp._entry_geometry(1920, 1080, 50)
    assert 0 + width == 960           # centre of a 1920-wide screen


def test_degenerate_size_is_safe():
    x, y, width = FullscreenCircleApp._entry_geometry(0, 0, 0)
    assert width >= 1                 # never a zero/negative width

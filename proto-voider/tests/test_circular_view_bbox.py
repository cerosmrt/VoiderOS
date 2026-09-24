"""Shift+F12 circle screenshot: crops the same circle F1/NormalView and
F2/CircularView both draw — centered in the WHOLE WINDOW, radius
min(w,h)//2-35 (the exact formula already duplicated in NormalView.paintEvent,
CircularView.paintEvent and FullscreenCircleApp._entry_geometry). Computed
from the main window directly, not from a specific child view, so it works
from F1 (the actual use case — opacity-tuned cover shots) even when
circular_view hasn't been lazily created yet (it only exists after F2 has
been visited at least once).
"""
import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication

import io_mixin


@pytest.fixture(scope='module')
def qapp():
    yield QApplication.instance() or QApplication([])


def test_bbox_is_a_square_of_twice_the_radius():
    x, y, side = io_mixin._circle_bbox_for(800, 600)
    assert side == 2 * (min(800, 600) // 2 - 35)


def test_bbox_is_centered_on_the_window():
    x, y, side = io_mixin._circle_bbox_for(800, 600)
    r = side // 2
    assert x == 800 // 2 - r
    assert y == 600 // 2 - r


def test_bbox_tracks_window_size():
    x, y, side = io_mixin._circle_bbox_for(1920, 1080)
    r = min(1920, 1080) // 2 - 35
    assert side == 2 * r
    assert x == 1920 // 2 - r
    assert y == 1080 // 2 - r


def test_a_tiny_window_is_a_degenerate_point_not_a_crash():
    x, y, side = io_mixin._circle_bbox_for(50, 50)
    assert side == 0


class TestTakeCircleScreenshot:
    """Shift+F12: crop the circle out via `grim` and save it to
    void_dir/covers/, for later reuse as a carousel cover image.

    Qt's own QScreen.grabWindow() was tried first and confirmed dead on this
    Wayland/Hyprland setup — it returns a null pixmap even for a normal,
    non-layer-shell window (verified live: "grabWindow(0) devolvió un pixmap
    vacío"). grim (already installed, already used elsewhere in this
    system's Hyprland config for Super+S) talks to the compositor directly
    via wlr-screencopy and supports a region geometry natively.
    """

    def _app(self, qapp, tmp_path, w=800, h=600, pos=(0, 0)):
        import types
        from unittest.mock import MagicMock
        from PyQt6.QtCore import QPoint
        from helpers import make_ring_app
        from new_interface import FullscreenCircleApp
        a = make_ring_app(['.'])
        a.void_dir = str(tmp_path)
        a.width = lambda: w
        a.height = lambda: h
        a.mapToGlobal = lambda p: QPoint(p.x() + pos[0], p.y() + pos[1])
        a.take_circle_screenshot = types.MethodType(
            FullscreenCircleApp.take_circle_screenshot, a)
        return a

    def _ok_result(self):
        from unittest.mock import MagicMock
        return MagicMock(returncode=0, stderr='')

    def test_calls_grim_with_a_region_matching_the_window_circle(self, qapp, tmp_path):
        from unittest.mock import patch
        a = self._app(qapp, tmp_path, w=800, h=600, pos=(50, 60))
        with patch('io_mixin.subprocess.run', return_value=self._ok_result()) as run:
            a.take_circle_screenshot()
        args = run.call_args[0][0]
        assert args[0] == 'grim'
        geom = args[args.index('-g') + 1]
        # r = min(800,600)//2 - 35 = 265; bbox = (400-265, 300-265, 530) = (135, 35, 530);
        # +pos (50, 60) -> (185, 95).
        assert geom == '185,95 530x530'

    def test_works_even_when_circular_view_is_none(self, qapp, tmp_path):
        # The actual bug: circular_view is only created after F2 has been
        # visited (new_interface.py, lazy) — None beforehand, e.g. right
        # after launch, straight into F1. take_circle_screenshot must not
        # depend on it at all — F1 is the primary use case.
        from unittest.mock import patch
        a = self._app(qapp, tmp_path)
        a.circular_view = None
        with patch('io_mixin.subprocess.run', return_value=self._ok_result()) as run:
            a.take_circle_screenshot()
        run.assert_called_once()

    def test_success_writes_into_covers_with_a_timestamped_name(self, qapp, tmp_path):
        from unittest.mock import patch
        a = self._app(qapp, tmp_path)
        with patch('io_mixin.subprocess.run', return_value=self._ok_result()) as run:
            a.take_circle_screenshot()
        out_path = run.call_args[0][0][-1]
        assert out_path.startswith(str(tmp_path / 'covers' / 'cover_'))
        assert out_path.endswith('.png')

    def test_grim_failure_does_not_crash(self, qapp, tmp_path):
        from unittest.mock import patch, MagicMock
        a = self._app(qapp, tmp_path)
        bad = MagicMock(returncode=1, stderr='wlr-screencopy failed')
        with patch('io_mixin.subprocess.run', return_value=bad):
            a.take_circle_screenshot()   # must not raise

    def test_grim_missing_does_not_crash(self, qapp, tmp_path):
        from unittest.mock import patch
        a = self._app(qapp, tmp_path)
        with patch('io_mixin.subprocess.run', side_effect=FileNotFoundError()):
            a.take_circle_screenshot()   # must not raise

    def test_a_tiny_window_is_a_noop(self, qapp, tmp_path):
        from unittest.mock import patch
        a = self._app(qapp, tmp_path, w=50, h=50)
        with patch('io_mixin.subprocess.run', return_value=self._ok_result()) as run:
            a.take_circle_screenshot()
        run.assert_not_called()

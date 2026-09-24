"""CircularView.circle_bbox(): the circle's bounding square in the widget's
own local coordinates — used by the Shift+F12 circle screenshot to know what
to crop, independent of actually grabbing a real screen."""
import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication

from line_ring import LineRing
from circular_view import CircularView


@pytest.fixture(scope='module')
def qapp():
    yield QApplication.instance() or QApplication([])


def _view(qapp, w, h, radius):
    v = CircularView(LineRing(['.']))
    v.resize(w, h)
    v.circle_radius = radius
    return v


def test_bbox_is_a_square_of_twice_the_radius(qapp):
    v = _view(qapp, 800, 600, 100)
    x, y, bw, bh = v.circle_bbox()
    assert bw == bh == 200


def test_bbox_is_centered_on_the_widget(qapp):
    v = _view(qapp, 800, 600, 100)
    x, y, bw, bh = v.circle_bbox()
    assert x == 800 // 2 - 100
    assert y == 600 // 2 - 100


def test_bbox_tracks_widget_resize(qapp):
    v = _view(qapp, 1920, 1080, 300)
    x, y, bw, bh = v.circle_bbox()
    assert x == 1920 // 2 - 300
    assert y == 1080 // 2 - 300
    assert bw == bh == 600


def test_zero_radius_is_a_degenerate_point_not_a_crash(qapp):
    v = _view(qapp, 800, 600, 0)
    x, y, bw, bh = v.circle_bbox()
    assert bw == bh == 0


class TestTakeCircleScreenshot:
    """Shift+F12: crop the circle out via `grim` and save it to
    void_dir/covers/, for later reuse as a carousel cover image.

    Qt's own QScreen.grabWindow() was tried first and confirmed dead on this
    Wayland/Hyprland setup — it returns a null pixmap even for a normal,
    non-layer-shell window (verified live: "grabWindow(0) devolvió un pixmap
    vacío"). grim (already installed, already used elsewhere in this
    system's Hyprland config for Super+S) talks to the compositor directly
    via wlr-screencopy and supports a region geometry natively — no need to
    grab the whole screen and crop it ourselves in Qt.
    """

    def _app(self, qapp, tmp_path, radius=100, pos=(0, 0)):
        import types
        from helpers import make_ring_app
        from new_interface import FullscreenCircleApp
        a = make_ring_app(['.'])
        a.void_dir = str(tmp_path)
        a.circular_view = _view(qapp, 800, 600, radius)
        a.circular_view.move(*pos)
        a.take_circle_screenshot = types.MethodType(
            FullscreenCircleApp.take_circle_screenshot, a)
        return a

    def _ok_result(self):
        from unittest.mock import MagicMock
        return MagicMock(returncode=0, stderr='')

    def test_calls_grim_with_a_region_matching_the_circle(self, qapp, tmp_path):
        from unittest.mock import patch
        a = self._app(qapp, tmp_path, radius=100, pos=(50, 60))
        with patch('io_mixin.subprocess.run', return_value=self._ok_result()) as run:
            a.take_circle_screenshot()
        args = run.call_args[0][0]
        assert args[0] == 'grim'
        geom = args[args.index('-g') + 1]
        # bbox for an 800x600 view, radius 100, is (300, 200, 200, 200);
        # moved to (50, 60) -> global top-left (350, 260).
        assert geom == '350,260 200x200'

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

    def test_zero_size_bbox_is_a_noop(self, qapp, tmp_path):
        from unittest.mock import patch
        a = self._app(qapp, tmp_path, radius=0)
        with patch('io_mixin.subprocess.run', return_value=self._ok_result()) as run:
            a.take_circle_screenshot()
        run.assert_not_called()

    def test_no_circular_view_is_a_noop(self, qapp, tmp_path):
        import types
        from unittest.mock import patch
        from helpers import make_ring_app
        from new_interface import FullscreenCircleApp
        a = make_ring_app(['.'])
        a.void_dir = str(tmp_path)
        a.circular_view = None
        a.take_circle_screenshot = types.MethodType(
            FullscreenCircleApp.take_circle_screenshot, a)
        with patch('io_mixin.subprocess.run', return_value=self._ok_result()) as run:
            a.take_circle_screenshot()
        run.assert_not_called()

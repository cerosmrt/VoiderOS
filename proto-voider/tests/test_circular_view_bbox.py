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
    """Shift+F12: crop a full-screen grab to the circle and save it to
    void_dir/covers/, for later reuse as a carousel cover image."""

    def _app(self, qapp, tmp_path, radius=100):
        import types
        from helpers import make_ring_app
        from new_interface import FullscreenCircleApp
        a = make_ring_app(['.'])
        a.void_dir = str(tmp_path)
        a.circular_view = _view(qapp, 800, 600, radius)
        a.screen = lambda: QApplication.primaryScreen()
        a.take_circle_screenshot = types.MethodType(
            FullscreenCircleApp.take_circle_screenshot, a)
        return a

    def test_writes_a_png_into_covers(self, qapp, tmp_path):
        a = self._app(qapp, tmp_path)
        a.take_circle_screenshot()
        covers = list((tmp_path / 'covers').glob('*.png'))
        assert len(covers) == 1

    def test_the_saved_image_matches_the_circle_bbox_size(self, qapp, tmp_path):
        a = self._app(qapp, tmp_path, radius=150)
        a.take_circle_screenshot()
        from PyQt6.QtGui import QPixmap
        covers = list((tmp_path / 'covers').glob('*.png'))
        pm = QPixmap(str(covers[0]))
        assert pm.width() == pm.height() == 300

    def test_no_circular_view_is_a_noop(self, qapp, tmp_path):
        import types
        from helpers import make_ring_app
        from new_interface import FullscreenCircleApp
        a = make_ring_app(['.'])
        a.void_dir = str(tmp_path)
        a.circular_view = None
        a.screen = lambda: QApplication.primaryScreen()
        a.take_circle_screenshot = types.MethodType(
            FullscreenCircleApp.take_circle_screenshot, a)
        a.take_circle_screenshot()
        assert not (tmp_path / 'covers').exists()

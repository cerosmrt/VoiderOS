"""Shift+F12 cover screenshot: crops to 1:1 (a centered square, trimming the
side bars when the window is wider than tall) — for carousel cover art.
Circle-precision was tried first (crop exactly to the F1/F2 circle) but
dropped: not worth the fragility, a plain square crop is enough.

The window's own position/size come from `hyprctl -j clients` (matched by
this process's pid), not from Qt's self-reported geometry — seen live, for a
floating (detached) window, Qt's own width()/mapToGlobal() didn't match
where the window actually sits on screen. hyprctl and grim both operate in
the compositor's own coordinate space, so anchoring to hyprctl's numbers is
what keeps the two in agreement. This also sidesteps Qt's
QScreen.grabWindow(), confirmed to return a null pixmap on this Wayland
setup.
"""
import json
import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication

import io_mixin


@pytest.fixture(scope='module')
def qapp():
    yield QApplication.instance() or QApplication([])


def test_square_crop_uses_the_smaller_dimension_as_the_side():
    x, y, side = io_mixin._square_crop_for(0, 0, 1117, 916)
    assert side == 916


def test_square_crop_is_centered_trimming_the_wider_axis():
    x, y, side = io_mixin._square_crop_for(0, 0, 1117, 916)
    assert x == (1117 - 916) // 2
    assert y == 0


def test_square_crop_offsets_by_the_windows_own_position():
    x, y, side = io_mixin._square_crop_for(291, 136, 1117, 916)
    assert x == 291 + (1117 - 916) // 2
    assert y == 136


def test_a_taller_than_wide_window_trims_vertically_instead():
    x, y, side = io_mixin._square_crop_for(0, 0, 600, 900)
    assert side == 600
    assert x == 0
    assert y == (900 - 600) // 2


def test_a_zero_size_window_is_a_degenerate_point_not_a_crash():
    x, y, side = io_mixin._square_crop_for(0, 0, 0, 0)
    assert side == 0


class TestTakeCircleScreenshot:
    """Shift+F12: crop to 1:1 via `grim` and save it to void_dir/covers/,
    for later reuse as a carousel cover image."""

    def _app(self, qapp, tmp_path):
        import types
        from helpers import make_ring_app
        from new_interface import FullscreenCircleApp
        a = make_ring_app(['.'])
        a.void_dir = str(tmp_path)
        a.take_circle_screenshot = types.MethodType(
            FullscreenCircleApp.take_circle_screenshot, a)
        return a

    def _hyprctl_result(self, at, size, pid=None):
        from unittest.mock import MagicMock
        import os
        clients = [{'pid': pid if pid is not None else os.getpid(),
                    'at': list(at), 'size': list(size)}]
        return MagicMock(returncode=0, stdout=json.dumps(clients), stderr='')

    def _ok_grim_result(self):
        from unittest.mock import MagicMock
        return MagicMock(returncode=0, stderr='')

    def _run_side_effect(self, hyprctl_result, grim_result):
        def _run(args, **kwargs):
            if args[0] == 'hyprctl':
                return hyprctl_result
            return grim_result
        return _run

    def test_calls_grim_with_a_square_anchored_to_hyprctls_window(self, qapp, tmp_path):
        from unittest.mock import patch
        a = self._app(qapp, tmp_path)
        hc = self._hyprctl_result(at=(291, 136), size=(1117, 916))
        with patch('io_mixin.subprocess.run',
                   side_effect=self._run_side_effect(hc, self._ok_grim_result())) as run:
            a.take_circle_screenshot()
        grim_call = next(c for c in run.call_args_list if c.args[0][0] == 'grim')
        args = grim_call.args[0]
        geom = args[args.index('-g') + 1]
        # side = min(1117,916) = 916; x = 291 + (1117-916)//2 = 391; y = 136.
        assert geom == '391,136 916x916'

    def test_no_matching_window_is_handled_without_crashing(self, qapp, tmp_path):
        from unittest.mock import patch
        a = self._app(qapp, tmp_path)
        hc = self._hyprctl_result(at=(0, 0), size=(1000, 1000), pid=-1)
        with patch('io_mixin.subprocess.run',
                   side_effect=self._run_side_effect(hc, self._ok_grim_result())) as run:
            a.take_circle_screenshot()
        assert not any(c.args[0][0] == 'grim' for c in run.call_args_list)

    def test_hyprctl_missing_is_handled_without_crashing(self, qapp, tmp_path):
        from unittest.mock import patch
        a = self._app(qapp, tmp_path)
        with patch('io_mixin.subprocess.run', side_effect=FileNotFoundError()):
            a.take_circle_screenshot()   # must not raise

    def test_hyprctl_bad_json_is_handled_without_crashing(self, qapp, tmp_path):
        from unittest.mock import patch, MagicMock
        a = self._app(qapp, tmp_path)
        bad = MagicMock(returncode=0, stdout='not json', stderr='')
        with patch('io_mixin.subprocess.run', return_value=bad):
            a.take_circle_screenshot()   # must not raise

    def test_success_writes_into_covers_with_a_timestamped_name(self, qapp, tmp_path):
        from unittest.mock import patch
        a = self._app(qapp, tmp_path)
        hc = self._hyprctl_result(at=(0, 0), size=(800, 600))
        with patch('io_mixin.subprocess.run',
                   side_effect=self._run_side_effect(hc, self._ok_grim_result())) as run:
            a.take_circle_screenshot()
        grim_call = next(c for c in run.call_args_list if c.args[0][0] == 'grim')
        out_path = grim_call.args[0][-1]
        assert out_path.startswith(str(tmp_path / 'covers' / 'cover_'))
        assert out_path.endswith('.png')

    def test_grim_failure_does_not_crash(self, qapp, tmp_path):
        from unittest.mock import patch, MagicMock
        a = self._app(qapp, tmp_path)
        hc = self._hyprctl_result(at=(0, 0), size=(800, 600))
        bad_grim = MagicMock(returncode=1, stderr='wlr-screencopy failed')
        with patch('io_mixin.subprocess.run',
                   side_effect=self._run_side_effect(hc, bad_grim)):
            a.take_circle_screenshot()   # must not raise

    def test_grim_missing_does_not_crash(self, qapp, tmp_path):
        from unittest.mock import patch
        a = self._app(qapp, tmp_path)
        hc = self._hyprctl_result(at=(0, 0), size=(800, 600))

        def _run(args, **kwargs):
            if args[0] == 'hyprctl':
                return hc
            raise FileNotFoundError()
        with patch('io_mixin.subprocess.run', side_effect=_run):
            a.take_circle_screenshot()   # must not raise

    def test_a_zero_size_window_is_a_noop(self, qapp, tmp_path):
        from unittest.mock import patch
        a = self._app(qapp, tmp_path)
        hc = self._hyprctl_result(at=(0, 0), size=(0, 0))
        with patch('io_mixin.subprocess.run',
                   side_effect=self._run_side_effect(hc, self._ok_grim_result())) as run:
            a.take_circle_screenshot()
        assert not any(c.args[0][0] == 'grim' for c in run.call_args_list)

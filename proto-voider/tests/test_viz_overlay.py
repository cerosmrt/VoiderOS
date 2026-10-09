"""The visualizer draws in the margin around the F1/F2 circle, in three styles,
and stays invisible at rest."""
import math

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPainter, QColor
from PyQt6.QtWidgets import QApplication, QWidget

from viz_overlay import VizOverlay, STYLES, circle_geometry

SIZE = 400


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def _loud():
    return {'level': 1.0,
            'wave': [math.sin(i / 8.0) for i in range(128)],
            'bands': [0.9] * 32}


def _silent():
    return {'level': 0.0, 'wave': [0.0] * 128, 'bands': [0.0] * 32}


def _render(qapp, style, frame, steps=30):
    v = VizOverlay()
    v.resize(SIZE, SIZE)
    v.set_style(style)
    for _ in range(steps):                     # let the smoothing catch up
        v.feed(frame)
    img = QImage(SIZE, SIZE, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    v.paint_on(p, SIZE, SIZE)
    p.end()
    return img, v


def _painted(img):
    return sum(1 for y in range(0, SIZE, 2) for x in range(0, SIZE, 2)
               if img.pixelColor(x, y).alpha() > 0)


def test_styles_are_pulse_wave_bars():
    assert STYLES == ('pulse', 'wave', 'bars')


def test_circle_geometry_matches_the_f1_circle():
    cx, cy, r, margin = circle_geometry(400, 300)
    assert (cx, cy) == (200, 150) and r == 300 // 2 - 35 and margin == 35


@pytest.mark.parametrize("style", STYLES)
def test_silence_paints_nothing(qapp, style):
    img, _ = _render(qapp, style, _silent())
    assert _painted(img) == 0


@pytest.mark.parametrize("style", STYLES)
def test_sound_paints_something(qapp, style):
    img, _ = _render(qapp, style, _loud())
    assert _painted(img) > 50


@pytest.mark.parametrize("style", STYLES)
def test_nothing_is_painted_inside_the_circle(qapp, style):
    img, _ = _render(qapp, style, _loud())
    cx, cy, r, _m = circle_geometry(SIZE, SIZE)
    for y in range(0, SIZE, 2):
        for x in range(0, SIZE, 2):
            if math.hypot(x - cx, y - cy) < r - 3:
                assert img.pixelColor(x, y).alpha() == 0


def test_unknown_style_falls_back_to_pulse(qapp):
    v = VizOverlay()
    v.set_style('nope')
    assert v.style == 'pulse'


def test_overlay_never_takes_the_mouse(qapp):
    v = VizOverlay()
    assert v.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

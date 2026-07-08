"""The F3 send-mode '>' marker: CircularView paints it without error when
send_marker is set."""
import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPixmap

from circular_view import CircularView
from line_ring import LineRing


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def _render(v):
    v.resize(800, 600)
    v.render(QPixmap(800, 600))


def test_circularview_paints_with_send_marker(qapp):
    v = CircularView(LineRing(['.', 'Capitulo A', 'Capitulo B']))
    v.send_marker = True
    _render(v)                      # must not raise


def test_circularview_paints_without_send_marker(qapp):
    v = CircularView(LineRing(['.', 'Capitulo A']))
    _render(v)

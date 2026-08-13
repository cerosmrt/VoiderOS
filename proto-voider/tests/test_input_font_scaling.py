"""Input boxes must grow with the font — at size 33+ the line was clipped. Both
the F1 entry and the F2/F3 doc editor now resize their height to fit the current
font whenever it changes."""
import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont, QFontMetrics

from widgets import CustomLineEdit as F1Edit
from circular_view import CustomLineEdit as DocEdit


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.mark.parametrize("EditCls", [F1Edit, DocEdit])
def test_height_grows_with_font(qapp, EditCls):
    le = EditCls()
    le.setFont(QFont('Consolas', 11))
    small = le.height()
    le.setFont(QFont('Consolas', 40))
    big = le.height()
    assert big > small                        # grew with the font


@pytest.mark.parametrize("EditCls", [F1Edit, DocEdit])
def test_height_fits_the_font_no_clipping(qapp, EditCls):
    le = EditCls()
    le.setFont(QFont('Consolas', 33))
    assert le.height() >= QFontMetrics(QFont('Consolas', 33)).height()

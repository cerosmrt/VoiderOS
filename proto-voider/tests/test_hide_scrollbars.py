"""hide_scrollbars(): both scrollbars go invisible (content still scrolls via
wheel/keys). Used to keep the F9 prose editor clean."""
import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication, QPlainTextEdit
from PyQt6.QtCore import Qt

from widgets import hide_scrollbars


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def test_both_scrollbars_hidden(qapp):
    ed = QPlainTextEdit()
    hide_scrollbars(ed)
    assert ed.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert ed.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff

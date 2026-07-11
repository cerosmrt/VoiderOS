"""Smoke test: the F5 ReorderView paints without crashing for empty, paragraph,
and marker states."""
import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPixmap

from reorder_view import ReorderView


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _render(view):
    view.resize(800, 600)
    pm = QPixmap(800, 600)
    view.render(pm)                 # drives paintEvent


def test_empty_paints(qapp):
    v = ReorderView()
    v.set_state([], 0)
    _render(v)


def test_paragraphs_and_marks_paint(qapp):
    v = ReorderView()
    units = [
        {'kind': 'para', 'ordinal': 0, 'text': 'first paragraph ' * 10},
        {'kind': 'mark', 'name': 'ChapterTwo'},
        {'kind': 'para', 'ordinal': 1, 'text': 'second'},
    ]
    v.set_state(units, 1)
    _render(v)


def test_highlight_index_out_of_visible_range(qapp):
    v = ReorderView()
    units = [{'kind': 'para', 'ordinal': i, 'text': f'p{i} ' * 20}
             for i in range(50)]
    v.set_state(units, 40)
    _render(v)


def test_picker_panel_paints(qapp):
    v = ReorderView()
    v.set_state([{'kind': 'para', 'ordinal': 0, 'text': 'un parrafo'}], 0)
    v.set_picker_state(True, 'log', ['El Logos', 'El Logro'], 0, False, 'El Logos')
    _render(v)
    v.set_picker_state(True, 'Nuevo', [], 0, True, 'Nuevo')   # create-new state
    _render(v)

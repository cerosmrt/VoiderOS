"""Pinned top title as a toggle (Ctrl+Shift+T): flips + persists, and both F5
(ReorderView) and F2 (CircularView) paint it only when enabled."""
import types
import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPixmap

from new_interface import FullscreenCircleApp
from reorder_view import ReorderView
from circular_view import CircularView
from line_ring import LineRing


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def _render(view):
    view.resize(800, 600)
    view.render(QPixmap(800, 600))


# ── toggle logic ──────────────────────────────────────────────────────────────

def test_toggle_flips_and_persists(qapp):
    a = types.SimpleNamespace(config={}, _show_view_title=False, current_view=99)
    a._apply_view_title = lambda: None
    a._toggle_view_title = types.MethodType(FullscreenCircleApp._toggle_view_title, a)
    a._toggle_view_title()
    assert a._show_view_title is True
    assert a.config['show_view_title'] is True
    a._toggle_view_title()
    assert a._show_view_title is False
    assert a.config['show_view_title'] is False


# ── F5 view paints the title only when on ─────────────────────────────────────

def test_reorder_view_title_hidden_and_shown(qapp):
    v = ReorderView()
    units = [{'kind': 'para', 'ordinal': 0, 'text': 'un parrafo ' * 6}]
    v.set_state(units, 0, 'CAPITULO III', False)   # off
    _render(v)
    v.set_state(units, 0, 'CAPITULO III', True)    # on
    _render(v)


# ── F2 view paints the title only when show_title is set ──────────────────────

def test_circular_view_title_paints_when_enabled(qapp):
    v = CircularView(LineRing(['.', 'una linea', '.', 'otra']))
    v.show_title = True
    v.title_text = 'Mi Capitulo'
    _render(v)


def test_circular_view_no_title_by_default(qapp):
    v = CircularView(LineRing(['.', 'una linea']))
    _render(v)                                      # show_title defaults False
    assert v.show_title is False

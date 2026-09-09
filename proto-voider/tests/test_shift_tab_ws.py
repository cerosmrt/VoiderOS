"""Shift+Tab en F2 tiene que traer una línea de los libros del working set (F7).

No andaba, y no era la lógica —el working set se leía bien— sino la tecla: el
editor sólo reconocía el código Key_Backtab. Según el layout y el compositor,
Shift+Tab puede llegar como Key_Tab CON el modificador Shift, y ahí caía en la
rama del Tab normal: sobre una línea insertaba un fragmento de I/ en vez de uno
de los libros, y sobre un punto barajaba el párrafo. Parecía "no hace nada".
"""
import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtCore import Qt, QEvent

from circular_view import CustomLineEdit


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def _fire(le, key, mods):
    le.event(QKeyEvent(QEvent.Type.KeyPress, key, mods, '\t'))


def _wired(qapp):
    le = CustomLineEdit()
    got = []
    le.tabPressed.connect(lambda: got.append('tab'))
    le.altTabPressed.connect(lambda: got.append('ws'))
    return le, got


def test_plain_tab_is_still_the_i_fragment(qapp):
    le, got = _wired(qapp)
    _fire(le, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier)
    assert got == ['tab']


def test_backtab_asks_the_working_set(qapp):
    le, got = _wired(qapp)
    _fire(le, Qt.Key.Key_Backtab, Qt.KeyboardModifier.ShiftModifier)
    assert got == ['ws']


def test_tab_with_shift_also_asks_the_working_set(qapp):
    """La codificación que rompía: Key_Tab + Shift en vez de Key_Backtab."""
    le, got = _wired(qapp)
    _fire(le, Qt.Key.Key_Tab, Qt.KeyboardModifier.ShiftModifier)
    assert got == ['ws']


def test_backtab_without_the_shift_flag_still_counts(qapp):
    """Algunos backends mandan Key_Backtab con el Shift ya consumido."""
    le, got = _wired(qapp)
    _fire(le, Qt.Key.Key_Backtab, Qt.KeyboardModifier.NoModifier)
    assert got == ['ws']

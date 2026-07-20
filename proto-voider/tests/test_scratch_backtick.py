"""Backtick quick-access to 0.txt.

Two behaviours, pure logic (sub-methods stubbed, no widget/display):
- `_f1_goto_end`: F1 Enter on an empty entry jumps to a fresh blank line at the
  end of the ACTIVE file (any file), ready to keep writing.
- `_goto_scratch_toggle`: a round-trip to 0.txt — remembers the file+view you
  came from, lands on the scratch's last line (F1), and returns on a 2nd press.
Plus: the `` ` `` keybinding parses to Key_QuoteLeft.
"""
import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtCore import Qt

from line_ring import LineRing
from f1_mixin import F1Mixin


class FakeEntry:
    def __init__(self):
        self._t = ''
    def text(self): return self._t
    def setText(self, t): self._t = t
    def setCursorPosition(self, i): pass
    def setFocus(self): pass
    def clear(self): self._t = ''


def _app(lines, idx=0, view=0, path='/void/I/Cap.txt', f1='/void/0.txt'):
    class A(F1Mixin):
        pass
    a = A()
    a.line_ring = LineRing(list(lines) or ['.'])
    a.line_ring.index = idx
    a.entry = FakeEntry()
    a.current_file_path = path
    a.f1_file = f1
    a.current_view = view
    a.current_active_line_index = None
    # record calls to the heavy sub-methods we stub out
    a.calls = []
    a._f1_show_current = lambda: a.calls.append(('show', a.line_ring.index))
    a.switch_to_view = lambda v: a.calls.append(('view', v))
    a._f1_scratch_jump = lambda: a.calls.append(('scratch_jump',))
    a._set_active_file = lambda p: a.calls.append(('set_active', p))
    a._set_f2_file = lambda p: a.calls.append(('set_f2', p))
    a._save_last_line = lambda: a.calls.append(('save_last',))
    return a


# ── _f1_goto_end ──────────────────────────────────────────────────────────────

def test_goto_end_appends_blank_and_lands_there():
    a = _app(['.', 'a', '.', 'b'], idx=1)
    a._f1_goto_end()
    assert a.line_ring.lines[-1] == ''                 # fresh blank line at the end
    assert a.line_ring.index == len(a.line_ring.lines) - 1
    assert ('show', a.line_ring.index) in a.calls


def test_goto_end_no_double_blank_when_already_blank():
    a = _app(['.', 'a', ''], idx=0)
    before = len(a.line_ring.lines)
    a._f1_goto_end()
    assert len(a.line_ring.lines) == before            # no extra blank appended
    assert a.line_ring.index == before - 1


def test_goto_end_on_empty_ring():
    a = _app([], idx=0)
    a._f1_goto_end()
    assert a.line_ring.lines[-1] == ''
    assert a.line_ring.index == len(a.line_ring.lines) - 1


# ── _goto_scratch_toggle: going TO the scratch ────────────────────────────────

def test_toggle_from_chapter_remembers_and_jumps():
    a = _app(['.', 'x'], idx=1, view=1, path='/void/I/Cap.txt')
    a._goto_scratch_toggle()
    assert a._scratch_return == {'path': '/void/I/Cap.txt', 'view': 1}
    assert ('save_last',) in a.calls                   # position persisted for return
    assert ('view', 0) in a.calls                      # forced into F1
    assert ('scratch_jump',) in a.calls                # landed on 0.txt (its last line)


def test_toggle_from_f1_does_not_reswitch_view():
    a = _app(['.', 'x'], view=0, path='/void/I/Cap.txt')
    a._goto_scratch_toggle()
    assert ('view', 0) not in a.calls                  # already in F1, no redundant switch
    assert ('scratch_jump',) in a.calls


# ── _goto_scratch_toggle: coming BACK from the scratch ────────────────────────

def test_toggle_back_to_f2_restores_file_and_view():
    a = _app(['.', 's'], view=0, path='/void/0.txt')   # currently on scratch
    a._scratch_return = {'path': '/void/I/Cap.txt', 'view': 1}
    a._goto_scratch_toggle()
    assert ('set_f2', '/void/I/Cap.txt') in a.calls
    assert ('view', 1) in a.calls
    assert a._scratch_return is None                   # consumed


def test_toggle_back_to_f1_restores_active_file():
    a = _app(['.', 's'], view=0, path='/void/0.txt')
    a._scratch_return = {'path': '/void/I/Cap.txt', 'view': 0}
    a._goto_scratch_toggle()
    assert ('set_active', '/void/I/Cap.txt') in a.calls
    assert ('view', 0) in a.calls
    assert a._scratch_return is None


def test_toggle_on_scratch_without_return_is_noop():
    a = _app(['.', 's'], view=0, path='/void/0.txt')
    a._scratch_return = None
    a._goto_scratch_toggle()
    assert a.calls == []                               # nothing happened


# ── keybinding parse ──────────────────────────────────────────────────────────

def test_backtick_parses_to_quoteleft():
    from app_config import _parse_keybinding
    key, mods = _parse_keybinding('`')
    assert key == Qt.Key.Key_QuoteLeft
    assert mods == Qt.KeyboardModifier.NoModifier

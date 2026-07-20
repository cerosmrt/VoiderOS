"""F3 new-file creation, mirroring how a new line works in F2.

Model (pure logic, widget stubbed):
- Enter with the cursor at the END of the name (`splitAtCursor` → `_book_enter_at_end`)
  commits the current entry (creates the file) and opens a fresh empty entry
  below to keep adding. Stays in F3 — never dives into F2.
- Enter with the cursor at the START (pos 0, `returnPressed` → `_book_confirm_edit`)
  opens the file (existing behaviour); a pending entry settles in place.
- An empty entry is never turned into a real file, and leaving a pending entry
  discards it (`_book_discard_pending`).
"""
import os
import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication

from line_ring import LineRing
from f3_mixin import F3Mixin


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


class FakeEditor:
    def __init__(self): self._t = ''; self._ro = False
    def text(self): return self._t
    def setText(self, t): self._t = t
    def setReadOnly(self, b): self._ro = b
    def setCursorPosition(self, i): pass


class FakeView:
    def __init__(self): self.editor = FakeEditor(); self._offset = 0.0
    def update(self): pass


def _app(tmp, lines, libs, idx=0, pending=False, editor=''):
    os.makedirs(os.path.join(tmp, 'I'), exist_ok=True)

    class A(F3Mixin):
        pass
    a = A()
    a.void_dir = tmp
    a.book_ring = LineRing(list(lines))
    a.book_ring.index = idx
    a._library_lines = list(libs)
    a._library_path_cache = {fn: os.path.join(tmp, 'I', fn)
                             for fn in libs if fn not in ('.', '0.txt')}
    a.book_view = FakeView()
    a.book_view.editor.setText(editor)
    a._book_pending_new = pending
    a._book_pending_merge = False
    a.config = {}
    a.f1_file = os.path.join(tmp, '0.txt')
    a.calls = []
    a._save_library = lambda: a.calls.append('save')
    a._set_f2_file = lambda p: a.calls.append(('f2', os.path.basename(p)))
    a.switch_to_view = lambda v: a.calls.append(('view', v))
    a._book_show_editor = lambda: a.calls.append('show')
    a._book_open_concat = lambda: a.calls.append('concat')
    a._book_do_merge = lambda: a.calls.append('merge')
    a._book_try_rename = lambda: (a.calls.append('rename') or True)
    a._library_current_fname = lambda: (
        a._library_lines[a.book_ring.index]
        if 0 <= a.book_ring.index < len(a._library_lines) else None)
    a._dedupe_portals = lambda keep=None: keep     # single-book harness: no dupes
    return a


# ── _book_materialize_pending ─────────────────────────────────────────────────

def test_materialize_name_creates_file(qapp, tmp_path):
    a = _app(str(tmp_path), ['CapA', ''], ['CapA.txt', ''], idx=1,
             pending=True, editor='CapB')
    assert a._book_materialize_pending() is True
    assert a.book_ring.lines == ['CapA', 'CapB']
    assert a._library_lines == ['CapA.txt', 'CapB.txt']
    assert os.path.exists(os.path.join(str(tmp_path), 'I', 'CapB.txt'))
    assert a._book_pending_new is False
    assert ('view', 1) not in a.calls          # stays in F3, no dive to F2


def test_materialize_empty_removes(qapp, tmp_path):
    a = _app(str(tmp_path), ['CapA', ''], ['CapA.txt', ''], idx=1,
             pending=True, editor='')
    assert a._book_materialize_pending() is False
    assert a.book_ring.lines == ['CapA']
    assert a._library_lines == ['CapA.txt']
    assert a._book_pending_new is False


def test_materialize_dot_becomes_separator(qapp, tmp_path):
    a = _app(str(tmp_path), ['CapA', ''], ['CapA.txt', ''], idx=1,
             pending=True, editor='.')
    assert a._book_materialize_pending() is True
    assert a.book_ring.lines[1] == '.'
    assert a._library_lines[1] == '.'


def test_materialize_zero_becomes_portal(qapp, tmp_path):
    a = _app(str(tmp_path), ['CapA', ''], ['CapA.txt', ''], idx=1,
             pending=True, editor='0')
    assert a._book_materialize_pending() is True
    assert a.book_ring.lines[1] == '0'
    assert a._library_lines[1] == '0.txt'


# ── _book_enter_at_end (Enter with cursor at end) ─────────────────────────────

def test_enter_at_end_creates_and_spawns_new(qapp, tmp_path):
    a = _app(str(tmp_path), ['CapA', ''], ['CapA.txt', ''], idx=1,
             pending=True, editor='CapB')
    a._book_enter_at_end()
    # file committed, then a fresh empty entry opened below
    assert a.book_ring.lines == ['CapA', 'CapB', '']
    assert a._library_lines == ['CapA.txt', 'CapB.txt', '']
    assert a.book_ring.index == 2
    assert a._book_pending_new is True
    assert ('view', 1) not in a.calls


def test_enter_at_end_on_existing_spawns_new(qapp, tmp_path):
    a = _app(str(tmp_path), ['CapA'], ['CapA.txt'], idx=0)
    a._book_enter_at_end()
    assert 'rename' in a.calls                  # committed the current entry
    assert a.book_ring.lines == ['CapA', '']
    assert a._book_pending_new is True
    assert a.book_ring.index == 1


def test_enter_at_end_empty_pending_does_not_spawn(qapp, tmp_path):
    a = _app(str(tmp_path), ['CapA', ''], ['CapA.txt', ''], idx=1,
             pending=True, editor='')
    a._book_enter_at_end()
    assert a.book_ring.lines == ['CapA']        # removed, nothing new
    assert a._book_pending_new is False


# ── _book_confirm_edit (Enter at pos 0) ───────────────────────────────────────

def test_confirm_opens_existing_file_in_f2(qapp, tmp_path):
    a = _app(str(tmp_path), ['CapA'], ['CapA.txt'], idx=0)
    a._book_confirm_edit()
    assert ('f2', 'CapA.txt') in a.calls
    assert ('view', 1) in a.calls


def test_confirm_pending_empty_discards_without_f2(qapp, tmp_path):
    a = _app(str(tmp_path), ['CapA', ''], ['CapA.txt', ''], idx=1,
             pending=True, editor='')
    a._book_confirm_edit()
    assert a.book_ring.lines == ['CapA']
    assert a._book_pending_new is False
    assert ('view', 1) not in a.calls


# ── _book_discard_pending ─────────────────────────────────────────────────────

def test_discard_pending_removes_placeholder(qapp, tmp_path):
    a = _app(str(tmp_path), ['CapA', ''], ['CapA.txt', ''], idx=1, pending=True)
    a._book_discard_pending()
    assert a.book_ring.lines == ['CapA']
    assert a._library_lines == ['CapA.txt']
    assert a._book_pending_new is False


def test_discard_noop_when_not_pending(qapp, tmp_path):
    a = _app(str(tmp_path), ['CapA'], ['CapA.txt'], idx=0)
    a._book_discard_pending()
    assert a.book_ring.lines == ['CapA']

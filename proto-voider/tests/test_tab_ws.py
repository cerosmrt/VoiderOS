"""Tests for Alt+Tab (insert from working set) and capital-at-position-0 rule."""
import os
import types
import random
import pytest
from unittest.mock import MagicMock

from line_ring import LineRing
from helpers import make_ring_app


METHODS = (
    '_random_line_from_dir', '_random_line_from_ws',
    '_doc_insert_fragment', '_doc_insert_random_i_line', '_doc_insert_ws_line',
    '_doc_tab', '_doc_shuffle_paragraphs', '_doc_shuffle_para_lines',
    '_doc_refresh_editor',
)


def _tab_app(lines, i_files=None, ws_files=None, o_dir=None):
    from new_interface import FullscreenCircleApp
    import tempfile

    app = make_ring_app(list(lines))
    app.line_ring = LineRing(list(lines))
    app.circular_view.zero_marker = True
    app._doc_tab_cand = None

    for name in METHODS:
        if hasattr(FullscreenCircleApp, name):
            setattr(app, name, types.MethodType(getattr(FullscreenCircleApp, name), app))

    for fname, flines in (i_files or {}).items():
        with open(os.path.join(app.book_dir, fname), 'w', encoding='utf-8') as f:
            f.write('\n'.join(flines) + '\n')

    if o_dir is None:
        o_dir = tempfile.mkdtemp()
    app.o_dir = o_dir

    ws_books = []
    for fname, flines in (ws_files or {}).items():
        fpath = os.path.join(o_dir, fname)
        with open(fpath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(flines) + '\n')
        ws_books.append({'path': fname, 'position': 0})
    app._ws_books = ws_books if ws_books else [{'path': '', 'position': 0}]
    app._ws_loaded = True

    return app


def _setup_editor(app, text, sel_start=None, sel_len=0, cursor=None):
    ed = app.circular_view.editor
    ed.text.return_value = text
    has_sel = sel_start is not None and sel_len > 0
    ed.hasSelectedText.return_value = has_sel
    if has_sel:
        ed.selectedText.return_value = text[sel_start:sel_start + sel_len]
        ed.selectionStart.return_value = sel_start
        ed.cursorPosition.return_value = sel_start + sel_len
    else:
        ed.selectedText.return_value = ''
        ed.selectionStart.return_value = cursor if cursor is not None else len(text)
        ed.cursorPosition.return_value = cursor if cursor is not None else len(text)


# ── Capital rule ──────────────────────────────────────────────────────────────

class TestCapitalRule:

    def test_keeps_capital_at_position_zero(self, monkeypatch):
        """Inserting at position 0 keeps the leading capital."""
        monkeypatch.setattr(random, 'choice', lambda seq: seq[0])
        app = _tab_app(['.', ''], i_files={'s.txt': ['Capital sentence.']})
        app.line_ring.index = 1
        _setup_editor(app, '', cursor=0)
        app._doc_insert_random_i_line()
        new_text = app.circular_view.editor.setText.call_args[0][0]
        assert new_text[0].isupper()

    def test_lowercases_at_mid_sentence(self, monkeypatch):
        """Inserting mid-sentence (cursor > 0) lowercases the first char."""
        monkeypatch.setattr(random, 'choice', lambda seq: seq[0])
        app = _tab_app(['.', 'start '], i_files={'s.txt': ['Capital sentence.']})
        app.line_ring.index = 1
        _setup_editor(app, 'start ', cursor=6)
        app._doc_insert_random_i_line()
        inserted_start = 6
        new_text = app.circular_view.editor.setText.call_args[0][0]
        assert new_text[inserted_start].islower()

    def test_keeps_capital_when_selection_starts_at_zero(self, monkeypatch):
        """Replacing a selection that starts at 0 keeps the capital."""
        monkeypatch.setattr(random, 'choice', lambda seq: seq[0])
        app = _tab_app(['.', 'old text'], i_files={'s.txt': ['Capital sentence.']})
        app.line_ring.index = 1
        _setup_editor(app, 'old text', sel_start=0, sel_len=8)
        app._doc_insert_random_i_line()
        new_text = app.circular_view.editor.setText.call_args[0][0]
        assert new_text[0].isupper()

    def test_lowercases_when_selection_starts_mid(self, monkeypatch):
        """Replacing a selection that starts mid-line lowercases the fragment."""
        monkeypatch.setattr(random, 'choice', lambda seq: seq[0])
        app = _tab_app(['.', 'hello old'], i_files={'s.txt': ['Capital sentence.']})
        app.line_ring.index = 1
        _setup_editor(app, 'hello old', sel_start=6, sel_len=3)
        app._doc_insert_random_i_line()
        new_text = app.circular_view.editor.setText.call_args[0][0]
        # 'Capital' → lowercased → 'capital', inserted at pos 6
        assert new_text[6].islower()


# ── Working set source ────────────────────────────────────────────────────────

class TestRandomLineFromWs:

    def test_returns_line_from_ws_book(self, monkeypatch):
        monkeypatch.setattr(random, 'choice', lambda seq: seq[0])
        app = _tab_app(['.'], ws_files={'book.txt': ['.', 'O line one']})
        line = app._random_line_from_ws()
        assert line == 'O line one'

    def test_returns_none_when_ws_empty(self):
        app = _tab_app(['.'])  # no ws_files → empty slot
        assert app._random_line_from_ws() is None

    def test_skips_dot_lines(self, monkeypatch):
        monkeypatch.setattr(random, 'choice', lambda seq: seq[0])
        app = _tab_app(['.'], ws_files={'book.txt': ['.', 'real line']})
        for _ in range(10):
            line = app._random_line_from_ws()
            assert line != '.'

    def test_draws_from_any_ws_book(self, monkeypatch):
        seen = set()
        monkeypatch.setattr(random, 'choice', lambda seq: seq[0])
        app = _tab_app(['.'], ws_files={
            'book_a.txt': ['Line from A'],
            'book_b.txt': ['Line from B'],
        })
        for _ in range(20):
            line = app._random_line_from_ws()
            seen.add(line)
        assert len(seen) >= 1  # at least picks from one


# ── Alt+Tab inserts from working set ─────────────────────────────────────────

class TestInsertWsLine:

    def test_insert_ws_line_uses_ws_source(self, monkeypatch):
        monkeypatch.setattr(random, 'choice', lambda seq: seq[0])
        monkeypatch.setattr(random, 'shuffle', lambda seq: None)
        app = _tab_app(['.', 'mine'], ws_files={'book.txt': ['O fragment.']})
        app.line_ring.index = 1
        _setup_editor(app, 'mine', cursor=4)
        app._doc_insert_ws_line()
        new_text = app.circular_view.editor.setText.call_args[0][0]
        # 'O fragment.' → stripped → 'O fragment' (capital kept mid... wait cursor=4)
        # cursor=4 (mid), so lowercase: 'o fragment'
        assert 'o fragment' in new_text

    def test_insert_ws_line_noop_when_empty(self):
        app = _tab_app(['.', 'mine'])  # no ws books
        app.line_ring.index = 1
        _setup_editor(app, 'mine', cursor=4)
        before = list(app.line_ring.lines)
        app._doc_insert_ws_line()
        assert app.line_ring.lines == before

"""Tests for Tab in F2 — insert random I/ fragment, select it, re-roll on repeat."""
import os
import types
import random
import pytest
from unittest.mock import MagicMock, call

from line_ring import LineRing
from helpers import make_ring_app


TAB_METHODS = (
    '_random_line_from_dir', '_doc_tab',
    '_doc_shuffle_paragraphs', '_doc_shuffle_para_lines',
    '_doc_insert_random_i_line',
    '_doc_refresh_editor',
)


def _tab_app(lines, i_files=None):
    from new_interface import FullscreenCircleApp
    app = make_ring_app(list(lines))
    app.line_ring = LineRing(list(lines))
    app.circular_view.zero_marker = True
    app._doc_tab_cand = None
    for name in TAB_METHODS:
        setattr(app, name, types.MethodType(getattr(FullscreenCircleApp, name), app))
    for fname, flines in (i_files or {}).items():
        with open(os.path.join(app.book_dir, fname), 'w', encoding='utf-8') as f:
            f.write('\n'.join(flines) + '\n')
    return app


def _setup_editor(app, text, sel_start=None, sel_len=0, cursor=None):
    """Wire the mock editor with realistic return values."""
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


class TestFragmentStripping:

    def test_strips_leading_capital(self, monkeypatch):
        monkeypatch.setattr(random, 'choice', lambda seq: seq[0])
        app = _tab_app(['.', 'my line'], i_files={'s.txt': ['Capital sentence.']})
        app.line_ring.index = 1
        _setup_editor(app, 'my line', cursor=7)
        app._doc_insert_random_i_line()
        inserted = app.circular_view.editor.setText.call_args[0][0]
        assert 'capital sentence' in inserted  # lowercased

    def test_strips_trailing_dot(self, monkeypatch):
        monkeypatch.setattr(random, 'choice', lambda seq: seq[0])
        app = _tab_app(['.', 'my line'], i_files={'s.txt': ['A sentence.']})
        app.line_ring.index = 1
        _setup_editor(app, 'my line', cursor=7)
        app._doc_insert_random_i_line()
        inserted = app.circular_view.editor.setText.call_args[0][0]
        assert not inserted.rstrip().endswith('.')

    def test_strips_both(self, monkeypatch):
        monkeypatch.setattr(random, 'choice', lambda seq: seq[0])
        app = _tab_app(['.', ''], i_files={'s.txt': ['Hello world.']})
        app.line_ring.index = 1
        _setup_editor(app, '', cursor=0)
        app._doc_insert_random_i_line()
        inserted = app.circular_view.editor.setText.call_args[0][0]
        assert inserted == 'hello world'


class TestSelectionBehaviour:

    def test_no_selection_inserts_at_cursor(self, monkeypatch):
        monkeypatch.setattr(random, 'choice', lambda seq: seq[0])
        app = _tab_app(['.', 'mine'], i_files={'s.txt': ['Fragment.']})
        app.line_ring.index = 1
        _setup_editor(app, 'mine', cursor=4)
        app._doc_insert_random_i_line()
        new_text = app.circular_view.editor.setText.call_args[0][0]
        assert new_text == 'minefragment'

    def test_no_selection_selects_inserted_fragment(self, monkeypatch):
        monkeypatch.setattr(random, 'choice', lambda seq: seq[0])
        app = _tab_app(['.', 'mine'], i_files={'s.txt': ['Fragment.']})
        app.line_ring.index = 1
        _setup_editor(app, 'mine', cursor=4)
        app._doc_insert_random_i_line()
        # setSelection(start, length) called with pos=4, len=8 ('fragment')
        app.circular_view.editor.setSelection.assert_called_with(4, len('fragment'))

    def test_selection_is_replaced(self, monkeypatch):
        monkeypatch.setattr(random, 'choice', lambda seq: seq[0])
        app = _tab_app(['.', 'hello world'], i_files={'s.txt': ['Fragment.']})
        app.line_ring.index = 1
        # 'world' is selected (chars 6-11)
        _setup_editor(app, 'hello world', sel_start=6, sel_len=5)
        app._doc_insert_random_i_line()
        new_text = app.circular_view.editor.setText.call_args[0][0]
        assert new_text == 'hello fragment'

    def test_selection_replaced_and_reselected(self, monkeypatch):
        monkeypatch.setattr(random, 'choice', lambda seq: seq[0])
        app = _tab_app(['.', 'hello world'], i_files={'s.txt': ['Fragment.']})
        app.line_ring.index = 1
        _setup_editor(app, 'hello world', sel_start=6, sel_len=5)
        app._doc_insert_random_i_line()
        app.circular_view.editor.setSelection.assert_called_with(6, len('fragment'))

    def test_reroll_replaces_previous_insertion(self, monkeypatch):
        """Second Tab with the fragment selected replaces it with new random line."""
        lines = ['Line one.', 'Line two.']
        it = iter(lines)
        monkeypatch.setattr(random, 'choice', lambda seq: next(it))
        app = _tab_app(['.', 'base'], i_files={'s.txt': lines})
        app.line_ring.index = 1

        # First Tab: no selection, cursor at 4
        _setup_editor(app, 'base', cursor=4)
        app._doc_insert_random_i_line()
        # Fragment 'line one' (stripped) inserted at 4, selected

        # Second Tab: 'line one' is selected at pos 4
        _setup_editor(app, 'baseline one', sel_start=4, sel_len=len('line one'))
        app._doc_insert_random_i_line()
        new_text = app.circular_view.editor.setText.call_args[0][0]
        assert new_text == 'baseline two'

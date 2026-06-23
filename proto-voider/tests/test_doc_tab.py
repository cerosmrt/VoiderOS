"""Tests for the contextual Tab in F2 (and the shared random-line helper).

Tab in F2 does three different things depending on where the cursor sits:
  - on the ø zero-marker (index 0): shuffle paragraph ORDER (lines keep their
    relative order inside each paragraph);
  - on a '.' separator: shuffle the LINES within that paragraph;
  - on a content line: insert (or re-roll) a random I/ line below the cursor.
"""
import os
import types
import random

import pytest
from line_ring import LineRing
from helpers import make_ring_app


DOC_TAB_METHODS = (
    '_random_line_from_dir', '_doc_refresh_editor', '_doc_tab',
    '_doc_shuffle_paragraphs', '_doc_shuffle_para_lines',
    '_doc_insert_random_i_line',
)


def _doc_app(lines, i_files=None):
    from new_interface import FullscreenCircleApp

    app = make_ring_app(list(lines))
    app.line_ring = LineRing(list(lines))
    app.circular_view.zero_marker = True
    app._doc_tab_cand = None
    for name in DOC_TAB_METHODS:
        setattr(app, name, types.MethodType(getattr(FullscreenCircleApp, name), app))
    # Seed I/ (book_dir) with files of known lines.
    for fname, flines in (i_files or {}).items():
        with open(os.path.join(app.book_dir, fname), 'w', encoding='utf-8') as f:
            f.write('\n'.join(flines) + '\n')
    return app


def _blocks(lines):
    """Split a ring into content blocks (tuples) between '.' separators."""
    blocks, cur = [], []
    for l in lines:
        if l == '.':
            if cur:
                blocks.append(tuple(cur))
                cur = []
        else:
            cur.append(l)
    if cur:
        blocks.append(tuple(cur))
    return blocks


# ── Shuffle paragraphs (Tab on ø) ────────────────────────────────────────────

def test_shuffle_paragraphs_preserves_blocks(monkeypatch):
    monkeypatch.setattr(random, 'shuffle', lambda seq: seq.reverse())
    app = _doc_app(['.', 'a1', 'a2', '.', 'b1', '.', 'c1', 'c2'])
    app._doc_shuffle_paragraphs()
    blocks = _blocks(app.line_ring.lines)
    # Same blocks, reordered; each block's internal order is intact.
    assert set(blocks) == {('a1', 'a2'), ('b1',), ('c1', 'c2')}
    assert blocks == [('c1', 'c2'), ('b1',), ('a1', 'a2')]
    assert app.line_ring.index == 0          # stays on the ø


def test_shuffle_paragraphs_noop_single(monkeypatch):
    app = _doc_app(['.', 'only', 'one', 'para'])
    before = list(app.line_ring.lines)
    app._doc_shuffle_paragraphs()
    assert app.line_ring.lines == before


# ── Shuffle lines within a paragraph (Tab on '.') ────────────────────────────

def test_shuffle_para_lines_within(monkeypatch):
    monkeypatch.setattr(random, 'shuffle', lambda seq: seq.reverse())
    app = _doc_app(['.', 'a1', 'a2', 'a3', '.', 'b1'])
    app.line_ring.index = 0                  # the dot before paragraph 0
    app._doc_shuffle_para_lines()
    assert _blocks(app.line_ring.lines) == [('a3', 'a2', 'a1'), ('b1',)]


def test_shuffle_para_lines_single_noop():
    app = _doc_app(['.', 'a1', 'a2', '.', 'solo'])
    app.line_ring.index = 3                  # the dot before ['solo']
    before = list(app.line_ring.lines)
    app._doc_shuffle_para_lines()
    assert app.line_ring.lines == before


# ── Insert random I/ line (Tab on a content line) ────────────────────────────

def test_insert_pulls_from_i(monkeypatch):
    monkeypatch.setattr(random, 'shuffle', lambda seq: None)
    monkeypatch.setattr(random, 'choice', lambda seq: seq[0])
    app = _doc_app(['.', 'mine'], i_files={'src.txt': ['.', 'borrowed line']})
    app.line_ring.index = 1                  # on 'mine'
    app._doc_insert_random_i_line()
    # A new line was inserted below the cursor, taken from I/.
    assert app.line_ring.lines == ['.', 'mine', 'borrowed line']
    assert app.line_ring.index == 2
    assert app._doc_tab_cand == {'idx': 2, 'text': 'borrowed line'}


def test_insert_reroll_replaces_in_place(monkeypatch):
    monkeypatch.setattr(random, 'shuffle', lambda seq: None)
    pool = iter(['first', 'second'])
    monkeypatch.setattr(random, 'choice', lambda seq: next(pool))
    app = _doc_app(['.', 'mine'], i_files={'src.txt': ['x']})
    app.line_ring.index = 1
    app._doc_insert_random_i_line()          # inserts 'first'
    assert app.line_ring.lines == ['.', 'mine', 'first']
    app._doc_insert_random_i_line()          # re-roll → replaces, no growth
    assert app.line_ring.lines == ['.', 'mine', 'second']
    assert app.line_ring.index == 2


def test_insert_no_i_lines_is_noop():
    app = _doc_app(['.', 'mine'])            # empty book_dir
    app.line_ring.index = 1
    app._doc_insert_random_i_line()
    assert app.line_ring.lines == ['.', 'mine']


# ── Dispatcher routing ───────────────────────────────────────────────────────

def test_tab_on_zero_marker_routes_to_paragraphs(monkeypatch):
    app = _doc_app(['.', 'a', '.', 'b'])
    hits = []
    app._doc_shuffle_paragraphs = lambda: hits.append('para')
    app._doc_shuffle_para_lines = lambda: hits.append('lines')
    app._doc_insert_random_i_line = lambda: hits.append('insert')
    app.circular_view.zero_marker = True
    app.line_ring.index = 0
    app._doc_tab()
    assert hits == ['para']


def test_tab_on_separator_routes_to_lines(monkeypatch):
    app = _doc_app(['.', 'a', '.', 'b'])
    hits = []
    app._doc_shuffle_paragraphs = lambda: hits.append('para')
    app._doc_shuffle_para_lines = lambda: hits.append('lines')
    app._doc_insert_random_i_line = lambda: hits.append('insert')
    app.line_ring.index = 2                  # a non-zero '.' separator
    app._doc_tab()
    assert hits == ['lines']


def test_tab_on_content_routes_to_insert():
    app = _doc_app(['.', 'a', '.', 'b'])
    hits = []
    app._doc_shuffle_paragraphs = lambda: hits.append('para')
    app._doc_shuffle_para_lines = lambda: hits.append('lines')
    app._doc_insert_random_i_line = lambda: hits.append('insert')
    app.line_ring.index = 1                  # on content 'a'
    app._doc_tab()
    assert hits == ['insert']


# ── Random-line helper ───────────────────────────────────────────────────────

def test_random_line_from_dir_excludes_active(tmp_path):
    app = _doc_app(['.'], i_files={'a.txt': ['keep'], 'active.txt': ['skip me']})
    active = os.path.join(app.book_dir, 'active.txt')
    # Only a.txt is eligible → must return its line, never 'skip me'.
    for _ in range(10):
        line = app._random_line_from_dir(app.book_dir, exclude_path=active)
        assert line == 'keep'


def test_random_line_from_dir_empty_returns_none(tmp_path):
    app = _doc_app(['.'])                     # empty book_dir
    assert app._random_line_from_dir(app.book_dir) is None


# ── ø marker stays marked while highlighted ──────────────────────────────────

def test_editor_shows_zero_glyph_on_marker():
    app = _doc_app(['.', 'body'])
    app.circular_view.zero_marker = True
    app.line_ring.index = 0                   # parked on the index-0 marker
    assert app._doc_editor_text() == app._ZERO_GLYPH


def test_editor_shows_plain_dot_for_other_separators():
    app = _doc_app(['.', 'a', '.', 'b'])
    app.circular_view.zero_marker = True
    app.line_ring.index = 2                   # a non-zero '.' separator
    assert app._doc_editor_text() == '.'


def test_editor_shows_line_text_on_content():
    app = _doc_app(['.', 'hello'])
    app.circular_view.zero_marker = True
    app.line_ring.index = 1
    assert app._doc_editor_text() == 'hello'

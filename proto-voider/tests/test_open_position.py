"""F4 must open at the user's current position, not the top.

Covers the line-index -> paragraph-ordinal mapping and the F4 reading-HTML
anchors. (F5's own line<->paragraph mapping lives in test_f5_reorder.py.)
"""
import types

from helpers import make_ring_app


# ── shared line -> paragraph ordinal helper ───────────────────────────────────

class TestParaOrdinal:

    def _app(self):
        from new_interface import FullscreenCircleApp
        app = make_ring_app(['.'])
        app._para_ordinal_at = types.MethodType(
            FullscreenCircleApp._para_ordinal_at, app)
        return app

    def test_first_paragraph(self):
        app = self._app()
        lines = ['.', 'a', 'b', '.', 'c', '.', 'd']
        assert app._para_ordinal_at(lines, 1) == 0   # 'a'
        assert app._para_ordinal_at(lines, 2) == 0   # 'b'

    def test_middle_paragraph(self):
        app = self._app()
        lines = ['.', 'a', 'b', '.', 'c', '.', 'd']
        assert app._para_ordinal_at(lines, 4) == 1   # 'c'
        assert app._para_ordinal_at(lines, 6) == 2   # 'd'

    def test_on_separator_maps_to_preceding_paragraph(self):
        app = self._app()
        lines = ['.', 'a', '.', 'b']
        assert app._para_ordinal_at(lines, 2) == 0   # the '.' after 'a'

    def test_leading_separator_maps_to_zero(self):
        app = self._app()
        lines = ['.', 'a', '.', 'b']
        assert app._para_ordinal_at(lines, 0) == 0

    def test_empty_lines_ignored(self):
        app = self._app()
        lines = ['.', 'a', '', 'b', '.', 'c']
        assert app._para_ordinal_at(lines, 5) == 1   # 'c' is 2nd paragraph


# ── F4 reading anchors ────────────────────────────────────────────────────────

class TestReadingAnchors:

    def _app(self):
        from new_interface import FullscreenCircleApp
        app = make_ring_app(['.'])
        for m in ('_build_reading_html',):
            app.__dict__[m] = types.MethodType(getattr(FullscreenCircleApp, m), app)
        return app

    def test_each_paragraph_has_anchor(self):
        app = self._app()
        html = app._build_reading_html(['a', '.', 'b', '.', 'c'], 'T')
        assert 'name="vpara0"' in html
        assert 'name="vpara1"' in html
        assert 'name="vpara2"' in html

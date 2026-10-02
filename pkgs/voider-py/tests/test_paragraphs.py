import types
from helpers import make_ring_app


def _collapse_app(lines):
    from new_interface import FullscreenCircleApp
    app = make_ring_app(list(lines))
    app._doc_collapse_to_one_paragraph = types.MethodType(
        FullscreenCircleApp._doc_collapse_to_one_paragraph, app)
    app._doc_refresh_editor = types.MethodType(
        FullscreenCircleApp._doc_refresh_editor, app)
    app._doc_tab_cand = None
    return app


class TestParagraphHelpers:
    def test_paragraphs_from_ring_two_paras(self):
        app = make_ring_app(['.', 'a', 'b', '.', 'c', 'd'])
        dot_indices, paragraphs = app._paragraphs_from_ring()
        assert dot_indices == [0, 3]
        assert paragraphs[0] == ['a', 'b']
        assert paragraphs[1] == ['c', 'd']

    def test_paragraphs_from_ring_single(self):
        app = make_ring_app(['.', 'x'])
        _, paragraphs = app._paragraphs_from_ring()
        assert paragraphs == [['x']]

    def test_paragraphs_from_ring_empty_para(self):
        """Two consecutive dots → one empty paragraph."""
        app = make_ring_app(['.', '.', 'a'])
        _, paragraphs = app._paragraphs_from_ring()
        assert paragraphs[0] == []
        assert paragraphs[1] == ['a']

    def test_dot_line_index_first(self):
        app = make_ring_app(['.', 'a', 'b', '.', 'c'])
        _, paragraphs = app._paragraphs_from_ring()
        assert app._dot_line_index(0, paragraphs) == 0

    def test_dot_line_index_second(self):
        app = make_ring_app(['.', 'a', 'b', '.', 'c'])
        _, paragraphs = app._paragraphs_from_ring()
        assert app._dot_line_index(1, paragraphs) == 3

    def test_rebuild_ring_from_paragraphs(self):
        app = make_ring_app(['.', 'a'])
        app._rebuild_ring_from_paragraphs([['x', 'y'], ['z']])
        assert app.line_ring.lines == ['.', 'x', 'y', '.', 'z']

    def test_roundtrip_paragraphs(self):
        """Extract then rebuild must produce the same ring."""
        original = ['.', 'a', 'b', '.', 'c', 'd', 'e']
        app = make_ring_app(original[:])
        _, paras = app._paragraphs_from_ring()
        app._rebuild_ring_from_paragraphs(paras)
        assert app.line_ring.lines == original

    def test_roundtrip_three_paras(self):
        original = ['.', 'a', '.', 'b', '.', 'c']
        app = make_ring_app(original[:])
        _, paras = app._paragraphs_from_ring()
        app._rebuild_ring_from_paragraphs(paras)
        assert app.line_ring.lines == original


class TestCollapseToOneParagraph:
    """Ctrl+Shift+. — delete every dot in the document so the whole thing
    becomes one paragraph, and Tab on the single remaining dot
    (_doc_shuffle_para_lines) shuffles every line in the file at once."""

    def test_merges_two_paragraphs_into_one_dot(self):
        app = _collapse_app(['.', 'a', 'b', '.', 'c', 'd'])
        app._doc_collapse_to_one_paragraph()
        assert app.line_ring.lines == ['.', 'a', 'b', 'c', 'd']

    def test_preserves_relative_order_across_three_paragraphs(self):
        app = _collapse_app(['.', 'a', '.', 'b', '.', 'c'])
        app._doc_collapse_to_one_paragraph()
        assert app.line_ring.lines == ['.', 'a', 'b', 'c']

    def test_cursor_lands_on_the_remaining_dot(self):
        app = _collapse_app(['.', 'a', 'b', '.', 'c', 'd'])
        app.line_ring.index = 4
        app._doc_collapse_to_one_paragraph()
        assert app.line_ring.index == 0

    def test_already_single_paragraph_is_unchanged(self):
        app = _collapse_app(['.', 'a', 'b'])
        app._doc_collapse_to_one_paragraph()
        assert app.line_ring.lines == ['.', 'a', 'b']

    def test_saves_to_disk(self):
        app = _collapse_app(['.', 'a', '.', 'b'])
        app._doc_collapse_to_one_paragraph()
        with open(app.current_file_path, encoding='utf-8') as f:
            assert f.read() == '.\na\nb\n'


class TestCollapseParagraphsKeybinding:

    def test_ctrl_shift_dot_is_bound_and_free_of_collisions(self):
        from app_config import DEFAULT_CONFIG, _parse_keybinding
        kb = DEFAULT_CONFIG['keybindings']
        assert kb['collapse_paragraphs'] == 'Ctrl+Shift+.'
        parsed = [_parse_keybinding(v) for v in kb.values()]
        mine = _parse_keybinding(kb['collapse_paragraphs'])
        assert parsed.count(mine) == 1, 'Ctrl+Shift+. ya esta tomada por otra accion'

    def test_f2_routes_ctrl_shift_dot_to_the_collapse(self):
        from app_config import _parse_keybinding
        from key_router_mixin import KeyRouterMixin

        called = []

        class App(KeyRouterMixin):
            current_file_path = '/tmp/x.txt'
            f1_file = '/tmp/other.txt'
            _f2_search_active = False
            _kb = {'collapse_paragraphs': _parse_keybinding('Ctrl+Shift+.')}
            def _doc_collapse_to_one_paragraph(self):
                called.append(True)

        class Ev:
            def accept(self): pass
            def ignore(self): pass

        key, mods = _parse_keybinding('Ctrl+Shift+.')
        App()._handle_f2_keys(key, mods, Ev())
        assert called

from helpers import make_ring_app


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

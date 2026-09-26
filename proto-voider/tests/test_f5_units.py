"""_f5_units(): F5's display units now include '.' separators (matching F2,
which shows a dot between paragraph groups) — previously dropped entirely,
so F5 never showed where one paragraph group ended and the next began."""
from line_ring import LineRing
from f5_reorder_mixin import F5ReorderMixin


def _app(lines, idx=0, para=0):
    class A(F5ReorderMixin):
        pass
    a = A()
    a.line_ring = LineRing(list(lines))
    a.line_ring.index = idx
    a._f5_para_idx = para
    a.current_file_path = '/void/I/Primero.txt'
    return a


def test_units_include_separators_between_paragraphs():
    a = _app(['.', 'a', '.', 'b'])
    kinds = [u['kind'] for u in a._f5_units()]
    assert kinds == ['sep', 'para', 'sep', 'para']


def test_leading_dot_is_a_separator_before_the_first_paragraph():
    a = _app(['.', 'a'])
    units = a._f5_units()
    assert units[0] == {'kind': 'sep'}
    assert units[1] == {'kind': 'para', 'ordinal': 0, 'text': 'a'}


def test_no_separator_without_a_dot_line():
    a = _app(['a', '/Chap', 'b'])
    kinds = [u['kind'] for u in a._f5_units()]
    assert 'sep' not in kinds
    assert kinds == ['para', 'mark', 'para']


def test_marks_and_separators_can_be_adjacent():
    a = _app(['a', '.', '/Chap', 'b'])
    kinds = [u['kind'] for u in a._f5_units()]
    assert kinds == ['para', 'sep', 'mark', 'para']


def test_paragraph_ordinals_unaffected_by_separators():
    a = _app(['.', 'a', '.', 'b', '.', 'c'])
    paras = [u for u in a._f5_units() if u['kind'] == 'para']
    assert [u['ordinal'] for u in paras] == [0, 1, 2]
    assert [u['text'] for u in paras] == ['a', 'b', 'c']

"""F5 reorder engine: linear paragraph swap over the active file, with '/name'
fences that paragraphs cross (fences don't move), plus F2<->F5 line/paragraph
mapping. Pure logic — no widget."""
from line_ring import LineRing
from f5_reorder_mixin import F5ReorderMixin


def _app(lines, idx=0, para=0):
    class A(F5ReorderMixin):
        pass
    a = A()
    a.line_ring = LineRing(list(lines))
    a.line_ring.index = idx
    a._f5_para_idx = para
    a.reorder_view = None
    a.saved = []
    a.auto_save_circular = lambda undo_key=None: a.saved.append(list(a.line_ring.lines))
    a.switched = []
    a.switch_to_view = lambda v: a.switched.append(v)
    a.current_file_path = '/void/I/Primero.txt'
    return a


def test_tokenize_flatten_roundtrip():
    a = _app([])
    lines = ['.', 'a1', 'a2', '.', 'b', '/Chap', 'c']
    assert a._f5_flatten(a._f5_tokens(lines)) == lines


def test_para_count_ignores_marks_and_dots():
    a = _app(['.', 'p1', '.', 'p2', '/A', 'p3'])
    assert a._f5_para_count() == 3


def test_swap_within_chapter():
    a = _app(['.', 'a', '.', 'b'], para=0)
    a._f5_swap_down()
    assert a.line_ring.lines == ['.', 'b', '.', 'a']
    assert a._f5_para_idx == 1              # cursor follows the paragraph
    assert a.saved                          # persisted


def test_swap_crosses_fence_into_next_chapter():
    a = _app(['a', '/A', 'b'], para=0)      # 'a' in chap-before-/A, 'b' after
    a._f5_swap_down()
    assert a.line_ring.lines == ['b', '/A', 'a']   # 'a' crossed the fence
    assert a._f5_para_idx == 1


def test_swap_moves_whole_multiline_paragraph():
    a = _app(['.', 'a1', 'a2', '.', 'b'], para=0)
    a._f5_swap_down()
    assert a.line_ring.lines == ['.', 'b', '.', 'a1', 'a2']


def test_linear_no_wrap_at_edges():
    a = _app(['.', 'a', '.', 'b'], para=0)
    a._f5_swap_up()                          # already at top
    assert a.line_ring.lines == ['.', 'a', '.', 'b']
    assert not a.saved
    a._f5_para_idx = 1
    a._f5_swap_down()                        # already at bottom
    assert a.line_ring.lines == ['.', 'a', '.', 'b']
    assert not a.saved


def test_navigation_clamps():
    a = _app(['.', 'a', '.', 'b'], para=0)
    a._f5_prev_para()
    assert a._f5_para_idx == 0
    a._f5_next_para(); a._f5_next_para()
    assert a._f5_para_idx == 1


def test_para_at_line_maps_f2_to_f5():
    lines = ['.', 'a', '.', 'b', '/A', 'c']
    a = _app(lines)
    assert a._f5_para_at_line(lines, 1) == 0     # 'a'
    assert a._f5_para_at_line(lines, 3) == 1     # 'b'
    assert a._f5_para_at_line(lines, 4) == 1     # '/A' fence → preceding para
    assert a._f5_para_at_line(lines, 5) == 2     # 'c'


def test_line_of_para_maps_f5_to_f2():
    a = _app(['.', 'a', '.', 'b', '/A', 'c'])
    assert a._f5_line_of_para(0) == 1
    assert a._f5_line_of_para(1) == 3
    assert a._f5_line_of_para(2) == 5


def test_tokens_cached_until_invalidated():
    a = _app(['.', 'a', '.', 'b', '/A', 'c'])
    t1 = a._f5_tokens_cached()
    assert a._f5_tokens_cached() is t1        # reused while lines unchanged
    a._f5_invalidate_tokens()
    t2 = a._f5_tokens_cached()
    assert t2 is not t1 and t2 == t1          # recomputed, same content


def test_enter_lands_on_paragraph_of_current_line():
    a = _app(['.', 'a', '.', 'b', '/A', 'c'], idx=5)  # F2 on 'c'
    a._f5_enter()
    assert a._f5_para_idx == 2


def test_enter_to_f2_positions_and_switches():
    a = _app(['.', 'a', '.', 'b', '/A', 'c'], para=2)
    a._f5_enter_to_f2()
    assert a.line_ring.index == 5            # first line of paragraph 'c'
    assert a.switched == [1]                 # jumped to F2


# ── Fixed title header (chapter the current paragraph sits under) ──────────────

def test_current_title_uses_file_name_when_no_fence():
    a = _app(['.', 'a', '.', 'b'], para=1)
    a.current_file_path = '/void/I/Capitulo III.txt'
    assert a._f5_current_title() == 'Capitulo III'   # no fence → active file


def test_current_title_uses_fence_the_paragraph_is_under():
    a = _app(['a', '/Segundo', 'b'], para=1)         # 'b' sits under /Segundo
    a.current_file_path = '/void/I/Primero.txt'
    assert a._f5_current_title() == 'Segundo'


def test_current_title_before_first_fence_uses_file_name():
    a = _app(['a', '/Segundo', 'b'], para=0)         # 'a' precedes the fence
    a.current_file_path = '/void/I/Primero.txt'
    assert a._f5_current_title() == 'Primero'


def test_current_title_empty_file_still_names_the_file():
    a = _app([], para=0)
    a.current_file_path = '/void/I/Vacio.txt'
    assert a._f5_current_title() == 'Vacio'

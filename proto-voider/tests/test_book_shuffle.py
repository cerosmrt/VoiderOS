"""Tab on a separator dot in F3 shuffles that book's files (like F2 shuffles
lines), but numbered titles keep their order: a title starting with a number
(+ '.' or space) is sorted by that number into the slots numbered titles hold;
the rest are shuffled into the remaining slots; the '0' portal stays put."""
import random
import pytest

pytest.importorskip("PyQt6")
from f3_mixin import F3Mixin


class A(F3Mixin):
    pass


def test_title_number_detection():
    assert A._title_number('0. La Marca del Vaciador') == 0
    assert A._title_number('10. Algo') == 10
    assert A._title_number('3 Sustancia') == 3          # digit + space
    assert A._title_number('Epilogo') is None
    assert A._title_number('0') is None                 # portal marker, not numbered
    assert A._title_number('') is None


def test_reorder_sorts_numbered_into_their_slots_and_keeps_portal():
    a = A()
    files = [('0.txt', '0'), ('B.txt', '2. B'), ('A.txt', '1. A'),
             ('E.txt', 'Epilogo'), ('D.txt', 'Dedicatoria')]
    random.seed(0)
    out = a._reorder_group(files)
    assert out[0] == ('0.txt', '0')                     # portal fixed
    assert out[1][1] == '1. A'                          # numbered slots, sorted asc
    assert out[2][1] == '2. B'
    assert {out[3][1], out[4][1]} == {'Epilogo', 'Dedicatoria'}   # unnumbered set


def test_reorder_out_of_place_number_goes_to_its_order():
    a = A()
    files = [('C.txt', '3. C'), ('A.txt', '1. A'), ('B.txt', '2. B')]
    out = a._reorder_group(files)
    assert [d for _, d in out] == ['1. A', '2. B', '3. C']


def test_reorder_unnumbered_stay_in_unnumbered_slots():
    a = A()
    # slot 0 and 2 unnumbered, slot 1 numbered → numbered stays at slot 1
    files = [('X.txt', 'Alpha'), ('N.txt', '5. Five'), ('Y.txt', 'Beta')]
    random.seed(1)
    out = a._reorder_group(files)
    assert out[1] == ('N.txt', '5. Five')               # numbered slot unchanged
    assert {out[0][1], out[2][1]} == {'Alpha', 'Beta'}  # unnumbered shuffled here

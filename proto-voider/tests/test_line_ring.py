from line_ring import LineRing


class TestLineRing:
    def test_empty_init(self):
        ring = LineRing()
        assert ring.lines == ['']
        assert ring.index == 0

    def test_init_with_lines(self):
        ring = LineRing(['a', 'b', 'c'])
        assert ring.lines == ['a', 'b', 'c']
        assert ring.current() == 'a'

    def test_move_forward(self):
        ring = LineRing(['a', 'b', 'c'])
        ring.move(1)
        assert ring.index == 1
        assert ring.current() == 'b'

    def test_move_backward(self):
        ring = LineRing(['a', 'b', 'c'])
        ring.index = 2
        ring.move(-1)
        assert ring.index == 1

    def test_move_wraps_forward(self):
        ring = LineRing(['a', 'b', 'c'])
        ring.index = 2
        ring.move(1)
        assert ring.index == 0

    def test_move_wraps_backward(self):
        ring = LineRing(['a', 'b', 'c'])
        ring.index = 0
        ring.move(-1)
        assert ring.index == 2

    def test_move_multi_step(self):
        ring = LineRing(['a', 'b', 'c'])
        ring.move(5)
        assert ring.index == 5 % 3

    def test_get_offset(self):
        ring = LineRing(['a', 'b', 'c'])
        ring.index = 1
        assert ring.get(0) == 'b'
        assert ring.get(1) == 'c'
        assert ring.get(-1) == 'a'

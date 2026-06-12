from helpers import make_ring_app


class TestParaFocus:
    def test_enter_focus_sets_content(self):
        app = make_ring_app(['.', 'a', 'b', '.', 'c'])
        app.line_ring.index = 0
        app._enter_para_focus()
        assert app._para_focus is True
        assert set(app._para_focus_content) == {1, 2}

    def test_enter_focus_on_second_dot(self):
        app = make_ring_app(['.', 'a', 'b', '.', 'c'])
        app.line_ring.index = 3
        app._enter_para_focus()
        assert app._para_focus_content == [4]

    def test_exit_focus_clears_state(self):
        app = make_ring_app(['.', 'a', 'b'])
        app.line_ring.index = 0
        app._enter_para_focus()
        app.line_ring.index = 2
        app._exit_para_focus()
        assert app._para_focus is False
        assert app._para_focus_content == []
        assert app.circular_view.focus_indices is None

    def test_exit_focus_returns_to_dot(self):
        """After exiting focus, ring index lands on the preceding dot."""
        app = make_ring_app(['.', 'a', 'b'])
        app.line_ring.index = 0
        app._enter_para_focus()
        app.line_ring.index = 2
        app._exit_para_focus()
        assert app.line_ring.lines[app.line_ring.index] == '.'

    def test_swap_in_focus_wraps_circularly(self):
        """_swap_line_in_focus wraps within the focused paragraph only."""
        app = make_ring_app(['.', 'a', 'b', 'c', '.', 'x'])
        app.line_ring.index = 0
        app._enter_para_focus()
        app.line_ring.index = 1
        app._swap_line_in_focus(-1)
        assert app.line_ring.lines[app.line_ring.index] == 'a'
        assert app.line_ring.lines[1] == 'c'


class TestDotNavigation:
    def test_goto_prev_dot(self):
        app = make_ring_app(['.', 'a', 'b', '.', 'c'])
        app.line_ring.index = 4
        app.goto_prev_dot()
        assert app.line_ring.lines[app.line_ring.index] == '.'
        assert app.line_ring.index == 3

    def test_goto_next_dot(self):
        app = make_ring_app(['.', 'a', 'b', '.', 'c'])
        app.line_ring.index = 1
        app.goto_next_dot()
        assert app.line_ring.lines[app.line_ring.index] == '.'
        assert app.line_ring.index == 3

    def test_goto_prev_dot_wraps(self):
        """From before first dot, wraps to last dot."""
        app = make_ring_app(['.', 'a', '.', 'b'])
        app.line_ring.index = 1
        app.goto_prev_dot()
        assert app.line_ring.lines[app.line_ring.index] == '.'
        assert app.line_ring.index == 0

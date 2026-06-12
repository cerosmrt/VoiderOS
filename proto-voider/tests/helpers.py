import os
import tempfile
import types
from unittest.mock import MagicMock

from line_ring import LineRing


def _mock_circular_view():
    cv = MagicMock()
    cv._offset = 0.0
    cv.editor = MagicMock()
    cv.focus_indices = None
    cv.update = MagicMock()
    cv.width.return_value = 800
    cv.height.return_value = 600
    cv.editor.sizeHint.return_value.height.return_value = 30
    return cv


def make_ring_app(lines, tmp_file=None):
    from new_interface import FullscreenCircleApp

    class _App:
        pass

    app = _App()
    app.line_ring = LineRing(lines if lines else ['.'])
    app._para_focus = False
    app._para_focus_content = []
    app.current_view = 1
    app.circular_view = _mock_circular_view()

    if tmp_file:
        app.current_file_path = tmp_file
        app.void_dir = os.path.dirname(tmp_file)
    else:
        _void_dir = tempfile.mkdtemp()
        app.void_dir = _void_dir
        app.current_file_path = os.path.join(_void_dir, '0.txt')
        app._auto_tmp = app.current_file_path
        open(app.current_file_path, 'w').close()

    app.book_dir = tempfile.mkdtemp()
    app.book_files = []
    app.book_ring = LineRing()
    app.book_view = None
    app.config = {}
    app._set_active_file = lambda path: None

    core_methods = [
        '_paragraphs_from_ring', '_rebuild_ring_from_paragraphs',
        '_dot_line_index', '_find_move_target', '_current_para_idx',
        '_move_paragraph',
        'swap_line_up', 'swap_line_down',
        'swap_paragraph_up', 'swap_paragraph_down',
        '_swap_line_in_focus',
        'goto_prev_dot', 'goto_next_dot',
        'rebase_to_index_zero',
        '_enter_para_focus', '_exit_para_focus',
        '_doc_show_editor',
        'load_doc_lines', 'auto_save_circular',
    ]
    optional_methods = [
        '_get_focus_dot_idx',
        '_doc_join_prev', '_doc_split_line',
        '_apply_editor_style',
        '_last_lines_path', '_save_last_line', '_restore_last_line',
        '_load_book_order', '_save_book_order', '_rebuild_book_ring',
        '_book_file_idx', '_book_try_rename',
        '_book_navigate', '_book_swap_up', '_book_swap_down', '_book_rebase',
    ]

    for name in core_methods:
        m = getattr(FullscreenCircleApp, name)
        setattr(app, name, types.MethodType(m, app))

    for name in optional_methods:
        if hasattr(FullscreenCircleApp, name):
            m = getattr(FullscreenCircleApp, name)
            setattr(app, name, types.MethodType(m, app))

    return app


def has(app, method):
    return hasattr(app, method) and callable(getattr(app, method))

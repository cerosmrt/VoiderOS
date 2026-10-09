"""The cursor position must reach _last_lines.json even if the app is killed
(closing the kitty window sends SIGHUP: closeEvent never runs) — a timer saves it
whenever (file, index) changed, and closeEvent saves it too."""
import json
import types

from helpers import make_ring_app


def _app(tmp_path):
    from new_interface import FullscreenCircleApp
    p = tmp_path / 'chap.txt'
    p.write_text('.\na\nb\nc\n', encoding='utf-8')
    app = make_ring_app(['.', 'a', 'b', 'c'], tmp_file=str(p))
    app.book_dir = str(tmp_path)
    app._pos_saved = None
    for nm in ('_save_last_line', '_last_lines_path', '_position_autosave_tick'):
        setattr(app, nm, types.MethodType(getattr(FullscreenCircleApp, nm), app))
    return app


def _saved(tmp_path):
    return json.loads((tmp_path / '_last_lines.json').read_text())


def test_tick_saves_when_index_changed(tmp_path):
    app = _app(tmp_path)
    app.line_ring.index = 2
    app._position_autosave_tick()
    assert _saved(tmp_path) == {'chap.txt': 2}


def test_tick_does_not_rewrite_when_nothing_changed(tmp_path):
    app = _app(tmp_path)
    app.line_ring.index = 2
    app._position_autosave_tick()
    (tmp_path / '_last_lines.json').write_text('{"chap.txt": 99}')
    app._position_autosave_tick()                 # same file, same index
    assert _saved(tmp_path) == {'chap.txt': 99}   # untouched


def test_tick_saves_again_after_the_cursor_moves(tmp_path):
    app = _app(tmp_path)
    app.line_ring.index = 2
    app._position_autosave_tick()
    app.line_ring.index = 3
    app._position_autosave_tick()
    assert _saved(tmp_path) == {'chap.txt': 3}


def test_close_event_saves_position():
    from new_interface import FullscreenCircleApp
    import inspect
    src = inspect.getsource(FullscreenCircleApp.closeEvent)
    assert '_save_last_line' in src

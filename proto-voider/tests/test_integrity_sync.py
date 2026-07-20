"""B3 integrity: (1) cross-instance library reload when another Voider rewrites
I.txt, preserving selection; (2) a save-time rescue copy on a catastrophic shrink."""
import os
import types

from line_ring import LineRing
from helpers import make_ring_app


# ── (1) cross-instance I.txt reload ───────────────────────────────────────────

def _sync_app(tmp_path, disk_library, cur=('.', 'A.txt', 'B.txt'), sel_idx=2):
    from new_interface import FullscreenCircleApp
    app = make_ring_app(['.'])
    app.void_dir = str(tmp_path)
    (tmp_path / 'I').mkdir(exist_ok=True)
    with open(tmp_path / 'I.txt', 'w', encoding='utf-8') as f:
        f.write('\n'.join(disk_library) + '\n')
    for fn in set(disk_library) | set(cur):
        if fn != '.':
            open(tmp_path / 'I' / fn, 'w').close()
    app._library_lines = list(cur)
    app.book_ring = LineRing(['.' if x == '.' else x[:-4] for x in cur])
    app.book_ring.index = sel_idx
    app.book_view = None
    app.current_view = 2
    app._book_pending_new = False
    app._book_pending_merge = False
    for nm in ('_reload_library_from_other', '_load_library', '_library_path',
               '_build_library_path_cache', '_f3_mid_edit', '_generate_library',
               '_book_is_portal', '_dedupe_portals'):
        setattr(app, nm, types.MethodType(getattr(FullscreenCircleApp, nm), app))
    return app


def test_reload_picks_up_other_changes_preserving_selection(tmp_path):
    app = _sync_app(tmp_path, ['.', 'A.txt', 'C.txt', 'B.txt'], sel_idx=2)  # on B
    app._reload_library_from_other()
    assert app._library_lines == ['.', 'A.txt', 'C.txt', 'B.txt']   # matches disk
    assert app._library_lines[app.book_ring.index] == 'B.txt'       # kept selection


def test_reload_skipped_while_naming(tmp_path):
    app = _sync_app(tmp_path, ['.', 'A.txt', 'C.txt', 'B.txt'], sel_idx=2)
    app._book_pending_new = True
    app._reload_library_from_other()
    assert app._library_lines == ['.', 'A.txt', 'B.txt']            # unchanged


# ── (2) save-time rescue on large shrink ──────────────────────────────────────

def _rescue_app():
    from new_interface import FullscreenCircleApp
    app = make_ring_app(['.'])
    for nm in ('_rescue_on_large_shrink', '_read_lines_or_none'):
        setattr(app, nm, types.MethodType(getattr(FullscreenCircleApp, nm), app))
    return app


def _write(p, lines):
    with open(p, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')


def test_rescue_created_on_catastrophic_shrink(tmp_path):
    p = str(tmp_path / 'chap.txt')
    _write(p, ['.'] + [f'l{i}' for i in range(20)])
    _rescue_app()._rescue_on_large_shrink(p, ['.', 'only', 'two'])   # 20 → 2
    assert os.path.exists(p + '.rescue')


def test_no_rescue_on_normal_delete(tmp_path):
    p = str(tmp_path / 'chap.txt')
    _write(p, ['.'] + [f'l{i}' for i in range(20)])
    _rescue_app()._rescue_on_large_shrink(p, ['.'] + [f'l{i}' for i in range(19)])
    assert not os.path.exists(p + '.rescue')                        # 20 → 19 is fine


def test_no_rescue_on_growth_or_new_file(tmp_path):
    p = str(tmp_path / 'chap.txt')
    _write(p, ['.', 'a', 'b'])
    app = _rescue_app()
    app._rescue_on_large_shrink(p, ['.', 'a', 'b', 'c', 'd'])        # grew
    assert not os.path.exists(p + '.rescue')
    app._rescue_on_large_shrink(str(tmp_path / 'nope.txt'), ['x'])   # no old file
    assert not os.path.exists(str(tmp_path / 'nope.txt') + '.rescue')

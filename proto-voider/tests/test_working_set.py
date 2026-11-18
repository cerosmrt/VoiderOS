"""Tests for the redesigned F7 working set — manual, uncapped.

Model: the set is a hand-built list of slots. Each slot is either a filled
book ({'path': 'x.txt', 'position': N}) or an empty slot ({'path': '',...}).
- Start (no JSON) → one empty slot.
- Tab/* → fill the current slot with a random O/ book, never repeating one
  already used by another slot.
- Shift+Enter → insert a new empty slot below the current one.
- Ctrl+Delete → remove the current slot (never below one slot).
- Only filled slots are persisted to .working_set.json.
"""
import os
import json
import types

from line_ring import LineRing
from helpers import make_ring_app, _mock_circular_view


WS_METHODS = (
    '_ws_json_path', '_ws_slot_is_empty', '_load_working_set',
    '_save_working_set', '_ws_slot_display', '_ws_cur_slot',
    '_ws_build_browser_ring', '_ws_refresh_browser', '_ws_tab_randomize',
    '_ws_add_slot', '_ws_remove_slot', '_o_browser_open',
    '_ws_save_position', '_ws_corpus_available', '_ws_backup_previous',
)


def _ws_app(tmp_path, o_files=('a.txt', 'b.txt', 'c.txt', 'd.txt'),
            saved_books=None):
    from new_interface import FullscreenCircleApp

    o_dir = tmp_path / 'O'
    o_dir.mkdir(exist_ok=True)
    for f in o_files:
        (o_dir / f).write_text('.\nbody\n', encoding='utf-8')

    app = make_ring_app(['.'])
    app.o_dir = str(o_dir)
    app.void_dir = str(tmp_path)
    app._ws_all_o_files = list(o_files)
    app._ws_books = []
    app._ws_loaded = False
    app._ws_browser_index = 1
    app.o_browser_ring = LineRing(['.'])
    app.o_browser_view = None
    app.o_reader_file = None
    app.config = {}

    if saved_books is not None:
        with open(os.path.join(str(o_dir), '.working_set.json'), 'w') as f:
            json.dump({'books': saved_books, 'browser_index': 1}, f)

    app._WS_FILE = FullscreenCircleApp._WS_FILE
    app._WS_EMPTY = FullscreenCircleApp._WS_EMPTY
    for name in WS_METHODS:
        setattr(app, name, types.MethodType(getattr(FullscreenCircleApp, name), app))
    return app, o_dir


def _filled_paths(app):
    return [e['path'] for e in app._ws_books if e['path']]


# ── Initial state ────────────────────────────────────────────────────────────

def test_empty_start_is_one_empty_slot(tmp_path):
    app, _ = _ws_app(tmp_path)
    app._load_working_set()
    assert app._ws_books == [{'path': '', 'position': 0}]
    assert app._ws_slot_is_empty(app._ws_books[0])


def test_no_auto_population(tmp_path):
    # Even with many O/ books, an empty set stays a single empty slot.
    app, _ = _ws_app(tmp_path, o_files=tuple(f'{i}.txt' for i in range(50)))
    app._load_working_set()
    assert len(app._ws_books) == 1
    assert _filled_paths(app) == []


def test_loads_saved_books(tmp_path):
    app, _ = _ws_app(tmp_path, saved_books=[{'path': 'a.txt', 'position': 3}])
    app._load_working_set()
    assert app._ws_books == [{'path': 'a.txt', 'position': 3}]


def test_drops_missing_files(tmp_path):
    app, _ = _ws_app(tmp_path, saved_books=[{'path': 'gone.txt', 'position': 0}])
    app._load_working_set()
    # gone.txt isn't on disk → dropped → falls back to one empty slot.
    assert app._ws_books == [{'path': '', 'position': 0}]


# ── Tab / shuffle ────────────────────────────────────────────────────────────

def test_tab_fills_empty_slot(tmp_path):
    app, _ = _ws_app(tmp_path)
    app._load_working_set()
    app._ws_build_browser_ring(slot=0)
    app._ws_tab_randomize()
    assert app._ws_books[0]['path'] in ('a.txt', 'b.txt', 'c.txt', 'd.txt')


def test_tab_never_repeats_across_slots(tmp_path):
    app, _ = _ws_app(tmp_path, o_files=('a.txt', 'b.txt'))
    app._ws_books = [{'path': 'a.txt', 'position': 0}, {'path': '', 'position': 0}]
    app._ws_build_browser_ring(slot=1)   # cursor on the empty second slot
    app._ws_tab_randomize()
    # Only b.txt is unused → must land there, not a.txt.
    assert app._ws_books[1]['path'] == 'b.txt'


def test_tab_noop_when_pool_exhausted(tmp_path):
    app, _ = _ws_app(tmp_path, o_files=('a.txt',))
    app._ws_books = [{'path': 'a.txt', 'position': 0}]
    app._ws_build_browser_ring(slot=0)
    app._ws_tab_randomize()
    # No unused book → slot unchanged.
    assert app._ws_books[0]['path'] == 'a.txt'


# ── Add / remove slots ───────────────────────────────────────────────────────

def test_add_slot_inserts_empty_below(tmp_path):
    app, _ = _ws_app(tmp_path)
    app._ws_books = [{'path': 'a.txt', 'position': 0}]
    app._ws_build_browser_ring(slot=0)
    app._ws_add_slot()
    assert len(app._ws_books) == 2
    assert app._ws_books[1] == {'path': '', 'position': 0}
    # cursor parked on the new slot
    assert app._ws_cur_slot() == 1


def test_remove_slot(tmp_path):
    app, _ = _ws_app(tmp_path)
    app._ws_books = [{'path': 'a.txt', 'position': 0},
                     {'path': 'b.txt', 'position': 0}]
    app._ws_build_browser_ring(slot=1)
    app._ws_remove_slot()
    assert _filled_paths(app) == ['a.txt']


def test_remove_last_slot_leaves_one_empty(tmp_path):
    app, _ = _ws_app(tmp_path)
    app._ws_books = [{'path': 'a.txt', 'position': 0}]
    app._ws_build_browser_ring(slot=0)
    app.o_reader_file = None
    app._ws_remove_slot()
    assert app._ws_books == [{'path': '', 'position': 0}]


def test_cannot_remove_slot_open_in_reader(tmp_path):
    app, o_dir = _ws_app(tmp_path)
    app._ws_books = [{'path': 'a.txt', 'position': 0},
                     {'path': 'b.txt', 'position': 0}]
    app._ws_build_browser_ring(slot=0)
    # a.txt is the book currently loaded in the F6 reader — silently undeletable.
    app.o_reader_file = str(o_dir / 'a.txt')
    app._ws_remove_slot()
    assert _filled_paths(app) == ['a.txt', 'b.txt']


def test_loaded_book_remains_after_deleting_others(tmp_path):
    app, o_dir = _ws_app(tmp_path)
    app._ws_books = [{'path': 'a.txt', 'position': 0},
                     {'path': 'b.txt', 'position': 0}]
    app.o_reader_file = str(o_dir / 'a.txt')   # a.txt loaded in F6
    # Delete b.txt (cursor on slot 1) → only the loaded a.txt remains.
    app._ws_build_browser_ring(slot=1)
    app._ws_remove_slot()
    assert _filled_paths(app) == ['a.txt']
    # Trying to delete the last (loaded) one does nothing — it stays loaded.
    app._ws_build_browser_ring(slot=0)
    app._ws_remove_slot()
    assert _filled_paths(app) == ['a.txt']


# ── Persistence ──────────────────────────────────────────────────────────────

def test_empty_slots_not_persisted(tmp_path):
    app, o_dir = _ws_app(tmp_path)
    app._ws_loaded = True
    app._ws_books = [{'path': 'a.txt', 'position': 0},
                     {'path': '', 'position': 0}]
    app._save_working_set()
    data = json.loads((o_dir / '.working_set.json').read_text())
    assert data['books'] == [{'path': 'a.txt', 'position': 0}]


def test_roundtrip_through_disk(tmp_path):
    app, _ = _ws_app(tmp_path)
    app._ws_loaded = True
    app._ws_books = [{'path': 'a.txt', 'position': 5},
                     {'path': 'c.txt', 'position': 0}]
    app._save_working_set()
    app._ws_loaded = False
    app._load_working_set()
    assert app._ws_books == [{'path': 'a.txt', 'position': 5},
                             {'path': 'c.txt', 'position': 0}]


# ── Ring mapping ─────────────────────────────────────────────────────────────

def test_cur_slot_maps_ring_position(tmp_path):
    app, _ = _ws_app(tmp_path)
    app._ws_books = [{'path': 'a.txt', 'position': 0},
                     {'path': 'b.txt', 'position': 0},
                     {'path': 'c.txt', 'position': 0}]
    app._ws_build_browser_ring(slot=0)
    # ring = ['.', a, '.', b, '.', c]; slot i sits at ring index 2i+1
    app.o_browser_ring.index = 3
    assert app._ws_cur_slot() == 1
    app.o_browser_ring.index = 5
    assert app._ws_cur_slot() == 2
    app.o_browser_ring.index = 2   # a separator
    assert app._ws_cur_slot() is None


def test_empty_slot_shows_marker(tmp_path):
    app, _ = _ws_app(tmp_path)
    app._ws_books = [{'path': '', 'position': 0}]
    app._ws_build_browser_ring(slot=0)
    assert app.o_browser_ring.current() == app._WS_EMPTY


# ── F7 se olvidaba los libros: el cierre pisaba el archivo con una lista vacía ─
#
# closeEvent siempre guardaba el conjunto; en una sesión sin pasar por F7 el
# conjunto nunca se había cargado, y lo que se guardaba era el [] del arranque.

SAVED = [{'path': 'a.txt', 'position': 3}, {'path': 'b.txt', 'position': 0}]


def _on_disk(o_dir):
    return json.loads((o_dir / '.working_set.json').read_text())['books']


def test_saving_before_loading_never_touches_the_file(tmp_path):
    app, o_dir = _ws_app(tmp_path, saved_books=SAVED)
    assert app._ws_loaded is False
    app._save_working_set()                       # lo que hace closeEvent
    assert _on_disk(o_dir) == SAVED


def test_closing_without_visiting_f7_keeps_the_set(tmp_path):
    """La secuencia exacta de closeEvent: _ws_save_position + _save_working_set."""
    app, o_dir = _ws_app(tmp_path, saved_books=SAVED)
    app._ws_save_position()
    app._save_working_set()
    assert _on_disk(o_dir) == SAVED


def test_leaving_f6_without_f7_keeps_the_set_and_saves_the_position(tmp_path):
    app, o_dir = _ws_app(tmp_path, saved_books=SAVED)
    app.o_reader_file = str(o_dir / 'a.txt')
    app.o_reader_ring = LineRing(['x'] * 10)
    app.o_reader_ring.index = 7
    app._ws_save_position()
    assert _on_disk(o_dir) == [{'path': 'a.txt', 'position': 7},
                               {'path': 'b.txt', 'position': 0}]


def test_unavailable_corpus_keeps_the_books_instead_of_dropping_them(tmp_path):
    """/mnt/data sin montar: O/ existe pero está vacío. Descartar todo y guardar
    después dejaba el archivo en []."""
    app, o_dir = _ws_app(tmp_path, o_files=(), saved_books=SAVED)
    assert app._ws_corpus_available() is False
    app._load_working_set()
    assert [e['path'] for e in app._ws_books] == ['a.txt', 'b.txt']
    app._save_working_set()
    assert _on_disk(o_dir) == SAVED


def test_missing_o_dir_is_unavailable_not_a_crash(tmp_path):
    app, _ = _ws_app(tmp_path)
    app.o_dir = str(tmp_path / 'no-existe')
    assert app._ws_corpus_available() is False


def test_hidden_files_do_not_count_as_a_corpus(tmp_path):
    app, o_dir = _ws_app(tmp_path, o_files=(), saved_books=SAVED)
    (o_dir / '.o_files_cache.txt').write_text('x')
    assert app._ws_corpus_available() is False


def test_deleted_books_are_still_dropped_when_the_corpus_is_there(tmp_path):
    app, _ = _ws_app(tmp_path, o_files=('b.txt',),
                     saved_books=[{'path': 'gone.txt', 'position': 0},
                                  {'path': 'b.txt', 'position': 0}])
    app._load_working_set()
    assert [e['path'] for e in app._ws_books] == ['b.txt']


def test_the_previous_version_is_kept_as_a_bak(tmp_path):
    app, o_dir = _ws_app(tmp_path, saved_books=SAVED)
    app._load_working_set()
    app._ws_books.append({'path': 'c.txt', 'position': 0})
    app._save_working_set()
    bak = json.loads((o_dir / '.working_set.json.bak').read_text())
    assert bak['books'] == SAVED
    assert len(_on_disk(o_dir)) == 3


def test_the_bak_keeps_the_last_non_empty_version(tmp_path):
    """Si algo deja el conjunto vacío, el .bak sigue teniendo lo último bueno."""
    app, o_dir = _ws_app(tmp_path, saved_books=SAVED)
    app._load_working_set()
    app._ws_books = [{'path': '', 'position': 0}]
    app._save_working_set()                       # queda vacío en disco
    assert _on_disk(o_dir) == []
    app._save_working_set()                       # otro guardado vacío
    bak = json.loads((o_dir / '.working_set.json.bak').read_text())
    assert bak['books'] == SAVED, 'el vacío pisó la copia buena'


def test_an_unchanged_save_does_not_rewrite_the_bak(tmp_path):
    app, o_dir = _ws_app(tmp_path, saved_books=SAVED)
    app._load_working_set()
    app._save_working_set()
    assert not (o_dir / '.working_set.json.bak').exists()


def test_the_write_is_atomic_no_tmp_left_behind(tmp_path):
    app, o_dir = _ws_app(tmp_path, saved_books=SAVED)
    app._load_working_set()
    app._ws_books.append({'path': 'c.txt', 'position': 0})
    app._save_working_set()
    assert not [n for n in os.listdir(o_dir) if n.endswith('.tmp')]

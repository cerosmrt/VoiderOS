"""Tests for the '0' scratch portal in F3.

A library entry named '0' (raw '0.txt') is a read-only portal: it cannot be
renamed, Enter on it jumps to the scratch 0.txt, it can appear anywhere/multiple
times, and Ctrl+Delete removes only the marker (never the 0.txt file).
"""
import os
import types
import pytest
from unittest.mock import MagicMock

from line_ring import LineRing
from helpers import make_ring_app, _mock_circular_view


def _portal_app(tmp_path, ring_lines, lib_lines):
    """Build an F3 app with given parallel book_ring / _library_lines and the
    book methods needed by the portal tests bound from the real class."""
    from new_interface import FullscreenCircleApp

    app = make_ring_app(['.'])
    app.void_dir = str(tmp_path)
    app.book_dir = str(tmp_path)
    app.book_ring = LineRing(ring_lines)
    app._library_lines = list(lib_lines)
    app.book_view = _mock_circular_view()
    app._save_library = MagicMock()
    app._book_pending_new = False

    # The real scratch file
    i_dir = tmp_path / 'I'
    i_dir.mkdir(exist_ok=True)
    scratch = i_dir / '0.txt'
    scratch.write_text(".\nscratch line\n", encoding='utf-8')
    app.f1_file = str(scratch)
    app.current_file_path = str(scratch)
    app._library_path_cache = {'0.txt': str(scratch)}

    for name in ('_book_is_portal', '_book_try_rename', '_book_confirm_edit',
                 '_book_new_entry', '_book_send_to_zero', '_book_show_editor',
                 '_book_random', '_library_current_fname'):
        setattr(app, name, types.MethodType(getattr(FullscreenCircleApp, name), app))

    # Collaborators invoked by confirm/open paths
    app._set_f2_file = MagicMock()
    app.switch_to_view = MagicMock()
    app._book_open_concat = MagicMock()
    return app, scratch


class TestRenameGuards:
    def test_rename_to_zero_is_refused(self, tmp_path):
        """Renaming a real file to '0' must be refused (would overwrite scratch)."""
        app, scratch = _portal_app(tmp_path, ['Chapter'], ['Chapter.txt'])
        chapter = tmp_path / 'I' / 'Chapter.txt'
        chapter.write_text(".\nbody\n", encoding='utf-8')
        app._library_path_cache['Chapter.txt'] = str(chapter)
        app.book_ring.index = 0
        app.book_view.editor.text.return_value = '0'   # user typed '0' over the title

        assert app._book_try_rename() is True
        assert chapter.exists()                          # not renamed away
        assert app._library_lines[0] == 'Chapter.txt'    # unchanged
        # The scratch 0.txt is intact
        assert scratch.read_text(encoding='utf-8') == ".\nscratch line\n"

    def test_rename_to_existing_file_is_refused(self, tmp_path):
        """Renaming onto an existing filename is refused (os.rename overwrites)."""
        app, _ = _portal_app(tmp_path, ['A', 'B'], ['A.txt', 'B.txt'])
        a = tmp_path / 'I' / 'A.txt'
        b = tmp_path / 'I' / 'B.txt'
        a.write_text("aaa\n", encoding='utf-8')
        b.write_text("bbb\n", encoding='utf-8')
        app._library_path_cache.update({'A.txt': str(a), 'B.txt': str(b)})
        app.book_ring.index = 0                          # on 'A'
        app.book_view.editor.text.return_value = 'B'     # rename A → B (B exists)

        assert app._book_try_rename() is True
        assert a.exists() and b.read_text(encoding='utf-8') == "bbb\n"  # B untouched
        assert app._library_lines[0] == 'A.txt'

    def test_normal_rename_still_works(self, tmp_path):
        app, _ = _portal_app(tmp_path, ['Old'], ['Old.txt'])
        old = tmp_path / 'I' / 'Old.txt'
        old.write_text("text\n", encoding='utf-8')
        app._library_path_cache['Old.txt'] = str(old)
        app.book_ring.index = 0
        app.book_view.editor.text.return_value = 'New'

        assert app._book_try_rename() is True
        assert (tmp_path / 'I' / 'New.txt').exists()
        assert not old.exists()
        assert app._library_lines[0] == 'New.txt'


class TestIsPortal:
    def test_detects_zero_display(self, tmp_path):
        app, _ = _portal_app(tmp_path, ['0'], ['0.txt'])
        app.book_ring.index = 0
        assert app._book_is_portal() is True

    def test_detects_zero_txt_raw(self, tmp_path):
        # display happens to differ but raw is 0.txt
        app, _ = _portal_app(tmp_path, ['anything'], ['0.txt'])
        app.book_ring.index = 0
        assert app._book_is_portal() is True

    def test_false_for_normal_title(self, tmp_path):
        app, _ = _portal_app(tmp_path, ['Chapter'], ['Chapter.txt'])
        app.book_ring.index = 0
        assert app._book_is_portal() is False

    def test_false_for_dot(self, tmp_path):
        app, _ = _portal_app(tmp_path, ['.'], ['.'])
        app.book_ring.index = 0
        assert app._book_is_portal() is False


class TestPortalReadOnly:
    def test_try_rename_skips_portal(self, tmp_path):
        app, scratch = _portal_app(tmp_path, ['0'], ['0.txt'])
        app.book_ring.index = 0
        # Even if the editor somehow reports a different title, no rename happens
        app.book_view.editor.text.return_value = 'hacked'
        result = app._book_try_rename()
        assert result is True
        assert app._library_lines[0] == '0.txt'        # unchanged
        assert os.path.exists(scratch)                  # file untouched
        app._save_library.assert_not_called()

    def test_show_editor_marks_portal_readonly(self, tmp_path):
        app, _ = _portal_app(tmp_path, ['0'], ['0.txt'])
        app.book_ring.index = 0
        app._book_show_editor()
        app.book_view.editor.setText.assert_called_with('0')
        app.book_view.editor.setReadOnly.assert_called_with(True)


class TestPortalEnter:
    def test_confirm_on_portal_opens_scratch(self, tmp_path):
        app, scratch = _portal_app(tmp_path, ['0'], ['0.txt'])
        app.book_ring.index = 0
        app._book_confirm_edit()
        app._set_f2_file.assert_called_once_with(str(scratch))
        app.switch_to_view.assert_called_once_with(1)


class TestPortalCreate:
    def test_pending_new_zero_becomes_portal(self, tmp_path):
        app, _ = _portal_app(tmp_path, ['.', 'Chapter'], ['.', 'Chapter.txt'])
        # Simulate Shift+Enter placeholder at index 1, user typed '0'
        app.book_ring.lines.insert(1, '')
        app._library_lines.insert(1, '')
        app.book_ring.index = 1
        app._book_pending_new = True
        app.book_view.editor.text.return_value = '0'

        app._book_confirm_edit()

        assert app.book_ring.lines[1] == '0'
        assert app._library_lines[1] == '0.txt'
        assert app._book_pending_new is False
        # No new file named '0.txt' created outside the existing scratch
        assert not os.path.exists(tmp_path / '0.txt')

    def test_portal_can_repeat(self, tmp_path):
        # Two '0' portals coexist in the library
        app, _ = _portal_app(tmp_path, ['0', '.', '0'], ['0.txt', '.', '0.txt'])
        app.book_ring.index = 0
        assert app._book_is_portal() is True
        app.book_ring.index = 2
        assert app._book_is_portal() is True


class TestBookRandom:
    def test_random_lands_on_real_title_only(self, tmp_path):
        # Library: portal, dot, real, real, dot, portal
        ring = ['0', '.', 'Alpha', 'Beta', '.', '0']
        lib = ['0.txt', '.', 'Alpha.txt', 'Beta.txt', '.', '0.txt']
        app, _ = _portal_app(tmp_path, ring, lib)
        app.book_view.editor.text.return_value = ''   # no pending rename text
        for _ in range(40):
            app._book_random()
            cur = app.book_ring.lines[app.book_ring.index]
            assert cur in ('Alpha', 'Beta')              # never a dot or a '0' portal

    def test_random_noop_when_no_real_titles(self, tmp_path):
        app, _ = _portal_app(tmp_path, ['0', '.'], ['0.txt', '.'])
        app.book_ring.index = 0
        app._book_random()
        # Nothing to jump to → index unchanged (still on the portal)
        assert app.book_ring.index == 0


class TestPortalDelete:
    def test_send_to_zero_removes_marker_keeps_file(self, tmp_path):
        app, scratch = _portal_app(tmp_path, ['0', '.', 'Chapter'],
                                   ['0.txt', '.', 'Chapter.txt'])
        app.book_ring.index = 0
        app._book_send_to_zero()
        # Marker gone from both parallel lists
        assert '0' not in app.book_ring.lines
        assert '0.txt' not in app._library_lines
        # The real scratch file is untouched
        assert os.path.exists(scratch)
        assert scratch.read_text(encoding='utf-8') == ".\nscratch line\n"

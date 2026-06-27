"""Data-integrity tests: writes must be atomic and never truncate on failure.

These guard the library index (I.txt) and other index/state writes against the
truncate-first failure mode, where a crash/kill/concurrent write mid-save leaves
the file empty or partial and chapters vanish from F3 while their .txt files
remain in I/.
"""
import os
import types

import pytest

from helpers import make_ring_app


def _lib_app(tmp_path, library_lines):
    """A minimal app with a real I.txt on disk and the library methods bound."""
    from new_interface import FullscreenCircleApp
    app = make_ring_app(['.'])
    app.void_dir = str(tmp_path)
    # _save_library now routes through the atomic writer — bind it too.
    app._atomic_write_lines = types.MethodType(
        FullscreenCircleApp._atomic_write_lines, app)
    app._library_lines = list(library_lines)
    # Seed I.txt with the same content so we can prove it survives a failed write.
    with open(os.path.join(str(tmp_path), 'I.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(library_lines))
    return app


def _read_lib(tmp_path):
    with open(os.path.join(str(tmp_path), 'I.txt'), 'r', encoding='utf-8') as f:
        return [l.rstrip('\n') for l in f if l.strip()]


class TestSaveLibraryAtomic:

    def test_save_library_roundtrips(self, tmp_path):
        app = _lib_app(tmp_path, ['a.txt', '.', 'b.txt', 'c.txt'])
        app._library_lines = ['a.txt', '.', 'b.txt', 'c.txt', 'd.txt']
        app._save_library()
        assert _read_lib(tmp_path) == ['a.txt', '.', 'b.txt', 'c.txt', 'd.txt']

    def test_failed_write_leaves_old_index_intact(self, tmp_path, monkeypatch):
        # A write that explodes mid-save must NOT truncate the existing I.txt.
        original = ['a.txt', '.', 'b.txt', 'c.txt']
        app = _lib_app(tmp_path, original)
        app._library_lines = ['a.txt', '.', 'b.txt', 'c.txt', 'NEW.txt']

        import io_mixin
        real_replace = os.replace

        def boom(*a, **k):
            raise OSError('disk full')

        # Fail at the atomic commit step; the original file must be untouched.
        monkeypatch.setattr(io_mixin.os, 'replace', boom)
        app._save_library()  # must swallow the error, not truncate

        # Old index still fully present — no chapter lost.
        assert _read_lib(tmp_path) == original

    def test_no_leftover_tmp_files(self, tmp_path):
        app = _lib_app(tmp_path, ['a.txt', 'b.txt'])
        app._library_lines = ['a.txt', 'b.txt', 'c.txt']
        app._save_library()
        leftovers = [p for p in os.listdir(str(tmp_path)) if p.endswith('.tmp')]
        assert leftovers == []

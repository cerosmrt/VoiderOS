# io_mixin.py — file I/O methods for FullscreenCircleApp
import os
import json
import random
import datetime
import shutil
import subprocess

from PyQt6.QtWidgets import QFileDialog
from PyQt6.QtPrintSupport import QPrinter, QPrintDialog

from app_config import _save_config
from line_ring import LineRing


class IoMixin:

    def load_doc_lines(self):
        """Load active file into the doc ring (ordered, no shuffle). Preserves index."""
        doc_path = self.current_file_path
        lines = []
        read_failed = False
        try:
            with open(doc_path, 'r', encoding='utf-8') as f:
                for raw in f:
                    s = raw.strip()
                    if s:
                        lines.append(s)
        except FileNotFoundError:
            # Genuinely absent file → an empty doc is correct, saving is safe.
            pass
        except Exception as e:
            # Transient/permission/decode error on an EXISTING file. Do NOT load an
            # empty ring — a subsequent save would overwrite the file with just a dot.
            read_failed = True
            print(f"⚠️ Error reading {os.path.basename(doc_path)}: {e}")
        # Block saves whenever a read of an existing file failed, so live-save and
        # auto_save_circular cannot clobber the on-disk content we couldn't read.
        self._doc_load_failed = read_failed
        # Ensure a leading dot so the last paragraph and first paragraph
        # are always separated when wrapping around the ring.
        if lines and lines[0] != '.':
            lines.insert(0, '.')
        self.line_ring = LineRing(lines or ["."])
        self._restore_last_line()
        # Empty doc (only dots) that loaded cleanly: append a blank editable line and
        # park the cursor on it, so F2 shows a blinking cursor to start typing into
        # (otherwise the only line is a read-only dot you can't write on). The blank
        # line isn't persisted until you type — live-save ignores empty text and
        # reload strips blank lines.
        if not read_failed and not any(l != '.' for l in self.line_ring.lines):
            self.line_ring.lines.append('')
            self.line_ring.index = len(self.line_ring.lines) - 1
        if self.circular_view:
            self.circular_view.ring = self.line_ring
            self.circular_view._offset = 0.0
        print(f"📄 {len(lines)} lines loaded from {os.path.basename(doc_path)}")

    def auto_save_circular(self, undo_key=None):
        """Save doc ring state to active file (atomic write)."""
        import tempfile
        if getattr(self, '_doc_load_failed', False):
            print("⛔ Save blocked: active file failed to load; refusing to overwrite it.")
            return
        doc_path = self.current_file_path
        self._undo_capture(doc_path, self.line_ring.lines, key=undo_key)
        # Safety net: if this save would drop a large fraction of the file's
        # content, keep a *.rescue copy of the previous on-disk version first. Never
        # blocks the save (normal deletes are fine) — it just makes a catastrophic
        # silent shrink recoverable.
        self._rescue_on_large_shrink(doc_path, self.line_ring.lines)
        dir_path = os.path.dirname(doc_path) or '.'
        try:
            fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix='.tmp')
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    for line in self.line_ring.lines:
                        f.write(line + '\n')
                os.replace(tmp_path, doc_path)
            except Exception:
                os.unlink(tmp_path)
                raise
            print(f"💾 Saved to 0.txt (index={self.line_ring.index})")
            ipc = getattr(self, '_ipc', None)
            if ipc:
                ipc.notify_saved(doc_path)
        except Exception as e:
            print(f"❌ Save error: {e}")

    def _rescue_on_large_shrink(self, path, new_lines):
        """If `new_lines` loses at least half of the file's content lines (and the
        file was non-trivial), copy the current on-disk file to path+'.rescue' so a
        catastrophic drop is recoverable. Best-effort; never raises."""
        try:
            old = self._read_lines_or_none(path)
            if old is None:
                return
            def nb(ls):
                return sum(1 for l in ls if l.strip() and l.strip() != '.')
            old_n, new_n = nb(old), nb(new_lines)
            if old_n >= 10 and new_n < old_n and (old_n - new_n) >= old_n // 2:
                import shutil
                shutil.copy2(path, path + '.rescue')
                print(f"🛟 Large shrink on {os.path.basename(path)} "
                      f"({old_n}→{new_n} lines); kept a .rescue copy.")
        except Exception:
            pass

    def _atomic_write_lines(self, path, lines, backup=False):
        """Write lines to path crash-safely (temp file + os.replace).

        If backup=True, copy the existing file to path+'.bak' first so a bad
        rewrite (e.g. reformat) can be undone. Each item in `lines` is written
        with a trailing newline. Returns True on success.
        """
        import tempfile, shutil
        if backup and os.path.exists(path):
            try:
                shutil.copy2(path, path + '.bak')
            except Exception as e:
                print(f"⚠️ Could not write backup {os.path.basename(path)}.bak: {e}")
        self._undo_capture(path, lines)
        dir_path = os.path.dirname(path) or '.'
        try:
            fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix='.tmp')
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    for line in lines:
                        f.write(line + '\n')
                os.replace(tmp_path, path)
                ipc = getattr(self, '_ipc', None)
                if ipc:
                    ipc.notify_saved(path)
                return True
            except Exception:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
                raise
        except Exception as e:
            print(f"❌ Write error on {os.path.basename(path)}: {e}")
            return False

    # ── Undo / redo (text content) ─────────────────────────────────────────────

    def _undo_trackable(self, path):
        """Only /void text files (chapters + 0.txt) are undoable — not the library
        index, config, caches, etc."""
        base = os.path.basename(path).lower()
        return base.endswith('.txt') and base != 'i.txt'

    def _undo_capture(self, path, after, key=None):
        """Record a content change for undo. Called from the write primitives;
        no-ops while applying an undo, when undo is uninitialised (tests), or for
        non-trackable files. Coalesces consecutive writes sharing `key`."""
        um = getattr(self, '_undo', None)
        if um is None or getattr(self, '_undo_applying', False):
            return
        # Inside an F3 structural transaction the whole change is captured as one
        # library snapshot — don't also record per-file content steps.
        if getattr(self, '_f3_txn', None) is not None:
            return
        if not self._undo_trackable(path):
            return
        before = self._undo_last.get(path)
        if before is None:
            try:
                with open(path, 'r', encoding='utf-8', errors='replace') as f:
                    before = [l.rstrip('\n') for l in f]
            except FileNotFoundError:
                before = []
            except Exception:
                return
        after = list(after)
        txn = getattr(self, '_undo_txn', None)
        if txn is not None:
            txn.append((path, list(before), after))
        else:
            um.record(path, before, after, key=key)
        self._undo_last[path] = after

    def _undo_begin(self):
        """Group the writes until _undo_commit into ONE undo step (e.g. F5 dispatch
        touches source + target)."""
        self._undo_txn = []

    def _undo_commit(self, key=None):
        txn = getattr(self, '_undo_txn', None)
        self._undo_txn = None
        if txn and getattr(self, '_undo', None) is not None:
            self._undo.record_transaction(txn, key=key)

    # ── F3 library/structural undo (reorder, rename, delete, merge, split) ──────

    def _read_lines_or_none(self, path):
        """File content as a line list, or None if the file is absent."""
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                return [l.rstrip('\n') for l in f]
        except FileNotFoundError:
            return None
        except Exception:
            return None

    def _f3_state(self):
        """Snapshot the F3 library arrays + cursor + path cache (no file bodies)."""
        return {'lib': list(self._library_lines),
                'ring': list(self.book_ring.lines),
                'idx': self.book_ring.index,
                'cache': dict(self._library_path_cache),
                'files': {}}

    def _f3_undo_begin(self):
        """Open an F3 undo transaction; captures library arrays as they are now."""
        self._f3_txn = self._f3_state()

    def _f3_undo_file(self, path):
        """Register a file the pending op will touch, capturing its pre-op content
        (or None if absent). MUST be called before the file is modified/deleted."""
        txn = getattr(self, '_f3_txn', None)
        if txn is None or getattr(self, '_undo_applying', False):
            return
        if path not in txn['files']:
            txn['files'][path] = self._read_lines_or_none(path)

    def _f3_undo_commit(self, key=None):
        """Close the transaction: capture the after-state and record one undo step."""
        txn = getattr(self, '_f3_txn', None)
        self._f3_txn = None
        um = getattr(self, '_undo', None)
        if txn is None or um is None or getattr(self, '_undo_applying', False):
            return
        after = self._f3_state()
        after['files'] = {p: self._read_lines_or_none(p) for p in txn['files']}
        um.record_library(txn, after)

    def _f3_restore(self, snap):
        """Restore a library snapshot: arrays, cursor, cache, touched files, I.txt."""
        self._undo_applying = True
        try:
            self._library_lines = list(snap['lib'])
            self.book_ring.lines = list(snap['ring'])
            self.book_ring.index = max(0, min(snap['idx'],
                                              len(self.book_ring.lines) - 1))
            self._library_path_cache = dict(snap['cache'])
            for path, content in snap['files'].items():
                if content is None:
                    if os.path.exists(path):
                        try:
                            os.remove(path)
                        except OSError:
                            pass
                else:
                    self._atomic_write_lines(path, content)
            self._save_library()
            if self.current_file_path in snap['files']:
                self.load_doc_lines()
        finally:
            self._undo_applying = False
        if getattr(self, 'current_view', None) == 2 and self.book_view:
            self.book_view._offset = 0.0
            if hasattr(self, '_book_show_editor'):
                self._book_show_editor()

    def _undo_apply(self, redo=False):
        """Ctrl+Z / Ctrl+Shift+Z: restore the previous (or next) content of every
        file in the change, atomically, then refresh the active view."""
        um = getattr(self, '_undo', None)
        if um is None:
            return
        entry = um.redo() if redo else um.undo()
        if not entry:
            print("↩️ nothing to " + ("redo" if redo else "undo"))
            return
        if entry.get('kind') == 'library':
            self._f3_restore(entry['after' if redo else 'before'])
            print(("↪️ redo" if redo else "↩️ undo") + " (F3 library)")
            return
        self._undo_applying = True
        try:
            for path, before, after in entry['files']:
                content = after if redo else before
                self._atomic_write_lines(path, content)
                self._undo_last[path] = list(content)
        finally:
            self._undo_applying = False
        self._undo_refresh(entry)
        print(("↪️ redo" if redo else "↩️ undo") + f" ({len(entry['files'])} file/s)")

    def _undo_refresh(self, entry):
        """Reload + redraw the active view if it shows a file we just restored."""
        cur = os.path.abspath(self.current_file_path)
        if not any(os.path.abspath(p) == cur for p, _, _ in entry['files']):
            return
        self.load_doc_lines()
        v = getattr(self, 'current_view', None)
        if v == 1 and hasattr(self, '_doc_show_editor'):
            self._doc_show_editor()
        elif v == 0 and hasattr(self, '_f1_show_current'):
            self._f1_show_current()
        elif v == 4 and hasattr(self, '_f5_enter'):
            self._f5_enter()

    # ── Reformat ─────────────────────────────────────────────────────────────

    def _generate_i_preview(self):
        """On startup: create CAPS title files and write I_preview.txt to I/."""
        i_dir = os.path.join(self.void_dir, 'I')
        preview_fname = 'I_preview.txt'
        preview_path = os.path.join(i_dir, preview_fname)
        skip_lower = {'0.txt', 'i_preview.txt'}

        # Create CAPS prologue files for each direct I/ subfolder (skip 0/ — reserved)
        try:
            for entry in os.scandir(i_dir):
                if not entry.is_dir():
                    continue
                caps_name = entry.name.upper() + '.txt'
                if caps_name.lower() in skip_lower:
                    continue
                caps_path = os.path.join(i_dir, caps_name)
                if not os.path.exists(caps_path):
                    open(caps_path, 'w', encoding='utf-8').close()
        except Exception as e:
            print(f"⚠️ I_preview CAPS error: {e}")

        # Walk every directory in I/ and collect files directly inside each one
        raw = []  # list of (abs_path, [filenames])
        try:
            for dirpath, dirs, files in os.walk(i_dir):
                dirs.sort(key=lambda x: x.lower())
                txts = sorted(
                    [f for f in files
                     if f.lower().endswith('.txt') and f.lower() not in skip_lower],
                    key=lambda x: x.lower()
                )
                if txts:
                    raw.append((dirpath, txts))
        except Exception as e:
            print(f"⚠️ I_preview walk error: {e}")

        if not raw:
            return

        # Skip when structure is flat (only I/ root, no subfolders with .txt files)
        subdir_groups = [(p, f) for p, f in raw if p != i_dir]
        root_group    = [(p, f) for p, f in raw if p == i_dir]
        if not subdir_groups:
            return
        ordered = subdir_groups + root_group

        # Compute labels: leaf folder name; add parent/ prefix on collision
        leaf_names = [os.path.basename(p) for p, _ in ordered]
        counts = {}
        for n in leaf_names:
            counts[n.lower()] = counts.get(n.lower(), 0) + 1

        groups = []
        for path, filenames in ordered:
            leaf = os.path.basename(path)
            if path == i_dir:
                label = 'I/'
            elif counts.get(leaf.lower(), 0) > 1:
                parent = os.path.basename(os.path.dirname(path))
                label = f'{parent}/{leaf}/'
            else:
                label = f'{leaf}/'
            groups.append((label, filenames))

        # Resolve duplicate filenames across groups with _2, _3 … suffix
        seen = {}
        def resolve(fname):
            key = fname.lower()
            if key not in seen:
                seen[key] = True
                return fname
            stem, ext = os.path.splitext(fname)
            i = 2
            while f'{stem}_{i}{ext}'.lower() in seen:
                i += 1
            new = f'{stem}_{i}{ext}'
            seen[new.lower()] = True
            return new

        lines = []
        for label, filenames in groups:
            lines.append('.')
            lines.append(label)
            for f in filenames:
                lines.append(resolve(f))

        try:
            with open(preview_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines) + '\n')
        except Exception as e:
            print(f"⚠️ Could not write I_preview.txt: {e}")
            return

        # Add I_preview.txt + CAPS files to I.txt so they appear in F3
        lib_path = self._library_path()
        if os.path.exists(lib_path):
            try:
                with open(lib_path, 'r', encoding='utf-8') as f:
                    lib_lines = [l.rstrip('\n') for l in f]
                to_add = [preview_fname]
                for entry in os.scandir(i_dir):
                    if not entry.is_dir():
                        continue
                    caps = entry.name.upper() + '.txt'
                    if caps.lower() not in skip_lower:
                        to_add.append(caps)
                changed = False
                for fname in to_add:
                    if fname not in lib_lines:
                        lib_lines.append(fname)
                        changed = True
                if changed:
                    with open(lib_path, 'w', encoding='utf-8') as f:
                        f.write('\n'.join(lib_lines) + '\n')
            except Exception as e:
                print(f"⚠️ Could not update I.txt: {e}")

        n = sum(len(g[1]) for g in groups)
        print(f"📋 I_preview.txt: {n} entries across {len(groups)} groups")

    def _merge_zero_files(self, silent=True):
        """Absorb every I/ subdirectory 0.txt into ~/void/I/0.txt.

        Runs at startup (silent, background) and on Ctrl+Shift+F in F3
        (explicit, refreshes the view after merging).
        """
        root_zero = self.f1_file
        i_dir = os.path.join(self.void_dir, 'I')
        absorbed = []
        deleted_empty = []

        for dirpath, _, filenames in os.walk(i_dir):
            for fname in filenames:
                if not fname.lower().endswith('.txt'):
                    continue
                fpath = os.path.join(dirpath, fname)
                is_root_zero = os.path.abspath(fpath) == os.path.abspath(root_zero)

                if fname.lower() == '0.txt' and not is_root_zero:
                    # Absorb stray 0.txt into root scratch
                    try:
                        with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                            lines = [l.rstrip('\n') for l in f if l.strip()]
                    except Exception as e:
                        print(f"⚠️ Cannot read {fpath}: {e}")
                        continue
                    try:
                        with open(root_zero, 'a', encoding='utf-8') as f:
                            f.write('\n.\n')
                            if lines:
                                f.write('\n'.join(lines) + '\n')
                        os.remove(fpath)
                        absorbed.append(fpath)
                    except Exception as e:
                        print(f"⚠️ Cannot merge {fpath}: {e}")
                        continue

                # NOTE: the previous "delete any .txt with no real content" branch was
                # removed — a dots-only or momentarily-empty file is no longer deleted.
                # Only genuine subfolder 0.txt files are absorbed (above).

                # Remove now-empty parent directories
                parent = os.path.dirname(fpath)
                if os.path.abspath(parent) != os.path.abspath(i_dir):
                    try:
                        if not os.listdir(parent):
                            os.rmdir(parent)
                    except Exception:
                        pass

        changed = absorbed or deleted_empty
        if absorbed:
            print(f"🌀 {'Merged' if not silent else 'Startup merged'} {len(absorbed)} 0.txt file(s) into root")
        if deleted_empty:
            print(f"🗑️ Deleted {len(deleted_empty)} empty document(s)")
        if not silent and not changed:
            print("✓ Nothing to clean up")

        if changed:
            self._append_new_files_to_library()

        if not silent and changed:
            # Remember which title was selected so we can restore after reload
            _saved_title = None
            if self.book_ring.lines and self.book_ring.current() != '.':
                _saved_title = self.book_ring.current()
            if self.current_file_path == self.f1_file:
                self.load_doc_lines()
            self.switch_to_view(2)
            # Restore cursor to the same book title if it still exists
            if _saved_title:
                try:
                    idx = self.book_ring.lines.index(_saved_title)
                    self.book_ring.index = idx
                    if self.book_view:
                        self.book_view._offset = 0.0
                        self.book_view.editor.setText(_saved_title)
                        self.book_view.editor.setReadOnly(False)
                        self.book_view.editor.setCursorPosition(0)
                        self.book_view.update()
                except ValueError:
                    pass

    def reformat_active_file(self):
        """Ctrl+Shift+F: split raw pasted text into one sentence per line.

        Rules:
        - Blank lines (paragraph breaks) → '.' separator line
        - Within a paragraph, split at sentence boundaries:
          period (or ! or ?) followed by a space and an uppercase letter
        - Exceptions (no split):
          * Ellipsis: ...
          * Abbreviations: Mr. Dr. Mrs. Ms. St. Prof. Jr. Sr.
          * Spanish abbrevs: Ud. Vd. pág. núm. art. ed. vol. fig. cap.
          * Latin: e.g. i.e. etc. vs. cf.
          * Initials: single letter followed by dot (e.g. J. K.)
          * Decimal numbers: digit.digit
        """
        import re

        # Abbreviations that should NOT trigger a split
        ABBREVS = {
            'mr', 'dr', 'mrs', 'ms', 'st', 'prof', 'jr', 'sr',
            'ud', 'vd', 'pág', 'núm', 'art', 'ed', 'vol', 'fig', 'cap',
            'e.g', 'i.e', 'etc', 'vs', 'cf', 'no',
        }

        def is_exception(text, dot_pos):
            """Return True if the dot at dot_pos should NOT be a sentence boundary."""
            # Ellipsis
            if text[dot_pos:dot_pos+3] == '...':
                return True
            if dot_pos >= 2 and text[dot_pos-2:dot_pos] == '..':
                return True
            # Decimal number: digit.digit
            if (dot_pos > 0 and text[dot_pos-1].isdigit() and
                    dot_pos+1 < len(text) and text[dot_pos+1].isdigit()):
                return True
            # Single initial: one uppercase letter before dot
            if dot_pos > 0 and text[dot_pos-1].isupper():
                # Check it's a standalone letter (preceded by space or start)
                if dot_pos == 1 or text[dot_pos-2] in (' ', '\t'):
                    return True
            # Known abbreviation: word before dot matches list
            word_start = dot_pos - 1
            while word_start > 0 and text[word_start-1].isalpha():
                word_start -= 1
            word = text[word_start:dot_pos].lower()
            if word in ABBREVS:
                return True
            return False

        def split_sentences(text):
            """Split a single-paragraph text string into a list of sentences."""
            sentences = []
            current_start = 0
            i = 0
            while i < len(text):
                ch = text[i]
                if ch in '.!?':
                    if ch == '.' and is_exception(text, i):
                        i += 1
                        continue
                    # Consume consecutive punctuation (e.g. ?" or .")
                    end = i + 1
                    while end < len(text) and text[end] in '.!?\'"»)':
                        end += 1
                    rest = text[end:]
                    if not rest.strip():
                        sentences.append(text[current_start:end].strip())
                        current_start = end
                        i = end
                        continue
                    m = re.match(r'\s+([A-ZÁÉÍÓÚÜÑ"«¿¡(])', rest)
                    if m:
                        sentences.append(text[current_start:end].strip())
                        current_start = end + m.end() - 1
                        i = current_start
                        continue
                i += 1
            tail = text[current_start:].strip()
            if tail:
                sentences.append(tail)
            return [s for s in sentences if s]

        doc_path = self.current_file_path
        try:
            with open(doc_path, 'r', encoding='utf-8') as f:
                raw = f.read()
        except Exception as e:
            print(f"❌ Reformat read error: {e}")
            return

        # If already in Voider format (starts with '.'), split sentences + collapse dots
        if raw.strip().startswith('.'):
            lines = [l.rstrip() for l in raw.strip().splitlines()]
            result = []
            prev_dot = False
            for line in lines:
                is_dot = line == '.' or (line and all(c == '.' for c in line))
                if is_dot:
                    if not prev_dot:
                        result.append('.')
                    prev_dot = True
                else:
                    text = re.sub(r'\s+', ' ', line.strip())
                    split = split_sentences(text)
                    if split:
                        result.extend(split)
                    elif text:
                        result.append(text)
                    prev_dot = False
            if not self._atomic_write_lines(doc_path, result, backup=True):
                return
            self.load_doc_lines()
            self._doc_show_editor()
            return

        # Split into paragraphs (one or more blank lines)
        paragraphs = re.split(r'\n\s*\n+', raw.strip())

        result_lines = []
        for para_idx, para in enumerate(paragraphs):
            # Collapse internal newlines/whitespace into single spaces
            text = re.sub(r'\s+', ' ', para.strip())

            if not text:
                continue

            # If paragraph is just a dot separator, keep it
            if text == '.':
                result_lines.append('.')
                continue

            # Add dot separator between paragraphs (not before the first)
            if para_idx > 0:
                result_lines.append('.')

            result_lines.extend(split_sentences(text))

        # Ensure leading dot
        if result_lines and result_lines[0] != '.':
            result_lines.insert(0, '.')

        if not self._atomic_write_lines(doc_path, result_lines, backup=True):
            return
        print(f"✅ Reformatted: {len(result_lines)} lines → {doc_path} (backup: {os.path.basename(doc_path)}.bak)")

        # Reload into ring
        self.load_doc_lines()
        self._doc_show_editor()

    def _shuffle_zero(self):
        """Ctrl+Shift+R in F2: randomise all lines of the scratch 0.txt.

        Only acts on 0.txt — the formless chaos that documents are formed from.
        Collects every content line (drops '.' separators), shuffles them, and
        rewrites the file as a single leading dot + the shuffled lines. Writes a
        0.txt.bak first so the shuffle can be undone.
        """
        if os.path.abspath(self.current_file_path) != os.path.abspath(self.f1_file):
            print("⛔ Shuffle only applies to 0.txt (the scratch).")
            return
        content = [l for l in self.line_ring.lines if l.strip() and l.strip() != '.']
        if len(content) < 2:
            print("↩ Nothing to shuffle (need at least 2 lines).")
            return
        random.shuffle(content)
        new_lines = ['.'] + content
        if not self._atomic_write_lines(self.current_file_path, new_lines, backup=True):
            return
        print(f"🎲 Shuffled 0.txt: {len(content)} lines "
              f"(backup: {os.path.basename(self.current_file_path)}.bak)")
        self.load_doc_lines()
        self._doc_show_editor()

    def _zero_blocks(self):
        """Parse the current ring (0.txt) into paragraph blocks.

        Returns a list of blocks; each block is the list of consecutive non-dot
        lines between '.' separators (order preserved)."""
        blocks = []
        cur = []
        for line in self.line_ring.lines:
            if line.strip() == '.':
                if cur:
                    blocks.append(cur)
                    cur = []
            elif line.strip():
                cur.append(line)
        if cur:
            blocks.append(cur)
        return blocks

    def _split_zero_to_docs(self):
        """Ctrl+Shift+F in 0.txt: FORMAT, then SPLIT.

        Formatting is the base operation, splitting is a layer on top:
        1. Reformat the whole scratch into single sentence-lines (also writes the
           0.txt.bak of the original).
        2. Send every block whose LAST line is a '/name' marker to void/I/name.txt
           and remove it from 0.txt (chaos → documents). Because we reformatted
           first, moved blocks arrive already formatted.

        - '/name'  → target name.txt (append if it exists, else create).
        - '/'      → auto name 'YY-M-D_N' (sequential within this run).
        - A newly created doc is inserted in the library right below the '0'
          portal you came from, so it shows up there in F3.
        - Blocks without a trailing '/' marker stay in 0.txt.
        Only acts on 0.txt.
        """
        if os.path.abspath(self.current_file_path) != os.path.abspath(self.f1_file):
            print("⛔ Format/split only applies to 0.txt (the scratch).")
            return

        # 1. Format first (reformat_active_file backs up to 0.txt.bak and reloads).
        self.reformat_active_file()

        # 2. Split the now-formatted scratch by '/name' markers.
        blocks = self._zero_blocks()
        i_dir = os.path.join(self.void_dir, 'I')

        # Auto-name generator: YY-M-D_N, skipping names already taken on disk/this run
        now = datetime.datetime.now()
        date_base = f"{now.year % 100}-{now.month}-{now.day}"
        used = set()
        def _auto_name():
            n = 1
            while True:
                cand = f"{date_base}_{n}"
                if cand not in used and not os.path.exists(os.path.join(i_dir, cand + '.txt')):
                    used.add(cand)
                    return cand
                n += 1

        kept = []          # blocks that stay in 0.txt
        moves = []         # (target_name, content_lines)
        for blk in blocks:
            last = blk[-1].strip()
            if last.startswith('/'):
                content = blk[:-1]
                if not content:
                    kept.append(blk)        # only a marker, nothing to move
                    continue
                name = last[1:].strip()
                if not name:
                    name = _auto_name()
                moves.append((name, content))
            else:
                kept.append(blk)

        if not moves:
            # Formatting already happened above; there's just nothing to split out.
            print("✓ Formatted 0.txt — no '/name' blocks to split.")
            return

        created = []       # (fname, fpath) for new docs to insert in the library
        for name, content in moves:
            fname = name if name.lower().endswith('.txt') else name + '.txt'
            fpath = os.path.join(i_dir, fname)
            if os.path.exists(fpath):
                try:
                    with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                        existing = [l.rstrip('\n') for l in f]
                except Exception as e:
                    print(f"⚠️ Cannot read {fname}, skipping that block: {e}")
                    kept.append(content)   # keep it in 0.txt so it isn't lost
                    continue
                combined = existing + ['.'] + content
            else:
                combined = ['.'] + content
                created.append((fname, fpath))
            if not self._atomic_write_lines(fpath, combined):
                kept.append(content)       # write failed → keep in 0.txt
                if (fname, fpath) in created:
                    created.remove((fname, fpath))
                continue
            print(f"📤 {len(content)} line(s) → {fname}")

        # Rewrite 0.txt from the kept blocks. backup=False: reformat_active_file
        # above already wrote 0.txt.bak holding the original (pre-format) text.
        new_zero = []
        for blk in kept:
            new_zero.append('.')
            new_zero.extend(blk)
        if not new_zero:
            new_zero = ['.']
        if not self._atomic_write_lines(self.current_file_path, new_zero, backup=False):
            return

        # Insert newly created docs into the library, just below the '0' portal
        if created:
            if self._book_is_portal(self.book_ring.index):
                ins = self.book_ring.index + 1
            else:
                ins = next((k + 1 for k, raw in enumerate(self._library_lines)
                            if raw.lower() == '0.txt'), len(self._library_lines))
            for fname, fpath in created:
                display = os.path.splitext(fname)[0]
                self._library_lines.insert(ins, fname)
                self.book_ring.lines.insert(ins, display)
                self._library_path_cache[fname] = fpath
                ins += 1
            self._save_library()

        print(f"✂️ Split 0.txt: {len(moves)} block(s) moved, "
              f"{len(created)} new doc(s) (backup: {os.path.basename(self.current_file_path)}.bak)")
        self.load_doc_lines()
        self._doc_show_editor()

    # ── Slash-split a chapter ──────────────────────────────────────────────────

    def commit_void(self):
        """Ctrl+Shift+G: commit the whole /void repo by hand, with a timestamp
        message. Reports on screen whether it committed, was already up to date,
        or failed."""
        ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        try:
            subprocess.run(['git', '-C', self.void_dir, 'add', '-A'],
                           capture_output=True, timeout=20)
            r = subprocess.run(['git', '-C', self.void_dir, 'commit',
                                '-m', f'snapshot {ts}'],
                               capture_output=True, timeout=20, text=True)
            out = (r.stdout or '') + (r.stderr or '')
            if r.returncode == 0:
                print(f"✅ Void commit: snapshot {ts}")
            elif 'nothing to commit' in out.lower():
                print("✓ Nada para commitear (void ya está al día).")
            else:
                print(f"⚠️ Commit falló: {out.strip()}")
        except Exception as e:
            print(f"⚠️ Commit error: {e}")

    def _git_snapshot_void(self, label='snapshot'):
        """One git snapshot of /void's I/ before a destructive write (safety)."""
        ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        try:
            subprocess.run(['git', '-C', self.void_dir, 'add', '-A', 'I/'],
                           capture_output=True, timeout=10)
            subprocess.run(['git', '-C', self.void_dir, 'commit',
                            '-m', f'{label} {ts}'], capture_output=True, timeout=10)
        except Exception as e:
            print(f"⚠️ Snapshot failed: {e}")

    def _split_chapter_at_slash(self):
        """Split the current file at '/name' markers.

        A line '/name' SEALS everything above it (back to the previous marker or
        the file start) into a chapter called 'name' (the name is right after the
        slash; a bare '/' auto-names). Text after the LAST marker stays in the
        current file; if that remainder is empty, the emptied container chapter is
        removed (so a merged book re-splits cleanly). Sealed chapters are inserted
        in order at the container's slot, preserving reading order. A name clash
        appends into the existing chapter. Atomic writes + a /void snapshot.
        """
        lines = list(self.line_ring.lines)
        markers = [i for i, l in enumerate(lines) if l.strip().startswith('/')]
        if not markers:
            print("✓ No '/name' markers to split.")
            return

        self._f3_undo_begin()
        self._f3_undo_file(self.current_file_path)
        self._git_snapshot_void('split')
        i_dir = os.path.join(self.void_dir, 'I')

        segments, start = [], 0            # (name, content-above-the-marker)
        for m in markers:
            name = lines[m].strip()[1:].strip()
            segments.append((name, lines[start:m]))
            start = m + 1
        trailing = lines[start:]

        cur_fname = os.path.basename(self.current_file_path)
        try:
            cur_idx = self._library_lines.index(cur_fname)
        except ValueError:
            cur_idx = min(self.book_ring.index, max(0, len(self._library_lines) - 1))

        # Container = the trailing remainder. Empty (and not the scratch) → drop it.
        cur = list(trailing)
        while cur and not cur[-1].strip():
            cur.pop()
        is_scratch = os.path.abspath(self.current_file_path) == os.path.abspath(self.f1_file)
        container_removed = False
        if not cur and not is_scratch and cur_fname in self._library_lines:
            self._library_lines.pop(cur_idx)
            self.book_ring.lines.pop(cur_idx)
            self._library_path_cache.pop(cur_fname, None)
            try:
                os.remove(self.current_file_path)
            except OSError:
                pass
            container_removed = True
        else:
            self._atomic_write_lines(self.current_file_path, cur or ['.'])

        ins = cur_idx                      # sealed chapters take the container's slot
        first_fname = None
        created = merged = 0
        for name, body in segments:
            if not name:
                name = datetime.datetime.now().strftime('%y-%m-%d_%H%M%S')
            fname = name + '.txt'
            content = list(body)
            while content and not content[-1].strip():
                content.pop()
            if not content:
                content = ['.']
            exists = (fname in self._library_lines
                      or os.path.exists(os.path.join(i_dir, fname)))
            if exists:
                fpath = self._library_path_cache.get(fname, os.path.join(i_dir, fname))
                self._f3_undo_file(fpath)
                try:
                    with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                        existing = [l.rstrip('\n') for l in f]
                except FileNotFoundError:
                    existing = []
                while existing and not existing[-1].strip():
                    existing.pop()
                combined = (existing + ['.'] + content) if existing else content
                if not self._atomic_write_lines(fpath, combined):
                    continue
                if fname not in self._library_lines:
                    self._library_lines.insert(ins, fname)
                    self.book_ring.lines.insert(ins, os.path.splitext(fname)[0])
                    self._library_path_cache[fname] = fpath
                    ins += 1
                merged += 1
            else:
                fpath = os.path.join(i_dir, fname)
                self._f3_undo_file(fpath)
                if not self._atomic_write_lines(fpath, content):
                    continue
                self._library_lines.insert(ins, fname)
                self.book_ring.lines.insert(ins, os.path.splitext(fname)[0])
                self._library_path_cache[fname] = fpath
                ins += 1
                created += 1
            if first_fname is None:
                first_fname = fname

        self._save_library()
        self._f3_undo_commit('split')
        # Keep the active file / cursor sane after the reshuffle.
        if container_removed:
            if first_fname and first_fname in self._library_lines:
                self.book_ring.index = self._library_lines.index(first_fname)
                self.current_file_path = self._library_path_cache.get(
                    first_fname, self.f1_file)
            else:
                self.current_file_path = self.f1_file
        elif cur_fname in self._library_lines:
            self.book_ring.index = self._library_lines.index(cur_fname)
        self.book_ring.index = max(0, min(self.book_ring.index,
                                          len(self.book_ring.lines) - 1))
        self.load_doc_lines()
        self._doc_show_editor()
        print(f"✂️ Split {cur_fname}: {created} new, {merged} merged"
              + (" (container removed)" if container_removed else "") + ".")

    # ── Book order ────────────────────────────────────────────────────────────

    def _library_path(self):
        return os.path.join(self.void_dir, 'I.txt')

    def _load_library(self):
        """Load ~/void/library.txt into book_ring. Auto-generates on first use."""
        lib_path = self._library_path()
        if not os.path.exists(lib_path):
            self._generate_library(lib_path)
        try:
            with open(lib_path, 'r', encoding='utf-8') as f:
                raw_lines = [l.rstrip('\n') for l in f]
        except Exception:
            raw_lines = []
        # Build parallel structures
        self._library_lines = []
        ring_lines = []
        for raw in raw_lines:
            s = raw.strip()
            if s == '.':
                self._library_lines.append('.')
                ring_lines.append('.')
            elif s:
                self._library_lines.append(s)
                ring_lines.append(os.path.splitext(s)[0])
        if not ring_lines:
            self._library_lines = ['.']
            ring_lines = ['.']
        self.book_ring = LineRing(ring_lines)
        for i, l in enumerate(ring_lines):
            if l != '.':
                self.book_ring.index = i
                break
        if self.book_view:
            self.book_view.ring = self.book_ring
            self.book_view._offset = 0.0
            # Immediately sync editor text to prevent stale text from causing wrong renames
            cur = self.book_ring.current()
            if cur == '.':
                self.book_view.editor.setText('· · ·')
                self.book_view.editor.setReadOnly(True)
            elif self._book_is_portal():
                self.book_view.editor.setText('0')
                self.book_view.editor.setReadOnly(True)
            else:
                self.book_view.editor.setText(cur)
                self.book_view.editor.setReadOnly(False)
            self.book_view.editor.setCursorPosition(0)
        self._build_library_path_cache()
        n_books = sum(1 for l in self._library_lines if l != '.')
        print(f"📚 Library: {n_books} books")

    def _generate_library(self, lib_path):
        """Scan I/ and write all .txt filenames to library.txt."""
        i_dir = os.path.join(self.void_dir, 'I')
        files = []
        try:
            for root, _, fnames in os.walk(i_dir):
                for f in sorted(fnames):
                    if f.lower().endswith('.txt'):
                        files.append(f)
        except Exception:
            pass
        files.sort()
        if files:
            self._atomic_write_lines(lib_path, files)

    def _append_new_files_to_library(self):
        """Add any I/ files not yet in I.txt to the end, preserving existing order."""
        lib_path = self._library_path()
        i_dir = os.path.join(self.void_dir, 'I')
        try:
            existing = set()
            lines = []
            if os.path.exists(lib_path):
                with open(lib_path, 'r', encoding='utf-8') as f:
                    lines = [l.rstrip('\n') for l in f]
                existing = {l.lower() for l in lines if l and l != '.'}
            new_files = []
            for root, _, fnames in os.walk(i_dir):
                for f in sorted(fnames):
                    if f.lower().endswith('.txt') and f.lower() not in existing:
                        new_files.append(f)
                        existing.add(f.lower())
            if new_files:
                lines.extend(new_files)
                self._atomic_write_lines(lib_path, lines)
                print(f"📚 Added {len(new_files)} new file(s) to I.txt")
        except Exception as e:
            print(f"⚠️ Could not update I.txt: {e}")

    def _build_library_path_cache(self):
        """Map filename → absolute path by scanning I/ recursively.

        The library (I.txt / _library_lines) keys on bare filename, so two files
        with the same basename in different folders would collide. Previously the
        last one scanned silently won — opening/deleting one could hit the other.
        Now we keep the FIRST occurrence (deterministic) and warn about the rest,
        so a collision is visible instead of dangerous.
        """
        self._library_path_cache = {}
        i_dir = os.path.join(self.void_dir, 'I')
        try:
            for root, _, fnames in os.walk(i_dir):
                for f in fnames:
                    if not f.lower().endswith('.txt'):
                        continue
                    full = os.path.join(root, f)
                    if f in self._library_path_cache:
                        print(f"⚠️ Duplicate basename {f!r}: keeping "
                              f"{self._library_path_cache[f]!r}, ignoring {full!r}")
                        continue
                    self._library_path_cache[f] = full
        except Exception:
            pass

    def _save_library(self):
        # Never persist an empty index — that can only be a logic bug, and an
        # atomic write of [] would still wipe a good I.txt. The library always
        # keeps at least ['.'] in normal operation.
        if not self._library_lines:
            print("⛔ Refusing to save an empty library index.")
            return
        self._atomic_write_lines(self._library_path(), self._library_lines)

    def _library_current_fname(self):
        """Return the filename.txt at the current ring position, or None."""
        idx = self.book_ring.index
        if idx >= len(self._library_lines):
            return None
        raw = self._library_lines[idx]
        return None if raw == '.' else raw

    def _last_lines_path(self):
        return os.path.join(self.book_dir, '_last_lines.json')

    def _save_last_line(self):
        """Save current line index for the active file into _last_lines.json."""
        fname = os.path.basename(self.current_file_path)
        path = self._last_lines_path()
        try:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                data = {}
            data[fname] = self.line_ring.index
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️ Error saving last line: {e}")

    def _restore_last_line(self):
        """Restore last known line index for the active file from _last_lines.json."""
        fname = os.path.basename(self.current_file_path)
        path = self._last_lines_path()
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            idx = data.get(fname)
            if idx is not None:
                n = len(self.line_ring.lines)
                self.line_ring.index = max(0, min(idx, n - 1))
        except Exception:
            pass  # no saved state yet, stay at 0


    def _set_active_file(self, path):
        """Change active file (and book_dir if it changed), reload doc ring."""
        self.current_file_path = path
        new_book_dir = os.path.dirname(os.path.abspath(path))
        if new_book_dir != self.book_dir:
            self.book_dir = new_book_dir
            self.config['book_dir'] = new_book_dir
        self.config['active_file'] = path
        _save_config(self.config)
        os.makedirs(self.book_dir, exist_ok=True)
        if not os.path.exists(path):
            open(path, 'w', encoding='utf-8').close()
        self.load_doc_lines()
        # Reset navigation state for new file
        self.current_active_line_index = None
        self.last_inserted_index = None
        print(f"📄 Active: {os.path.basename(path)}")

    def _set_f2_file(self, path):
        """Set which file F2 shows. switch_to_view(1) will reload if needed."""
        new_book_dir = os.path.dirname(os.path.abspath(path))
        if new_book_dir != self.book_dir:
            self.book_dir = new_book_dir
            self.config['book_dir'] = new_book_dir
        self.f2_file = path
        self.config['active_file'] = path
        _save_config(self.config)
        if not os.path.exists(path):
            open(path, 'w', encoding='utf-8').close()
        self.current_active_line_index = None
        self.last_inserted_index = None
        print(f"📄 F2 → {os.path.basename(path)}")

    # ── Book directory / file pickers ─────────────────────────────────────────

    def pick_active_file(self):
        """Ctrl+F2: pick any .txt file → sets active file + book folder."""
        path, _ = QFileDialog.getOpenFileName(
            None, "Select Active File",
            self.book_dir,
            "Text files (*.txt)"
        )
        if not path or not os.path.isfile(path):
            return
        self._set_f2_file(path)
        self.switch_to_view(1)

    def pick_book_directory(self):
        """Ctrl+F3: pick book folder, switch active file if it's outside new folder."""
        path = QFileDialog.getExistingDirectory(
            None, "Select Book Folder",
            self.book_dir,
            QFileDialog.Option.ShowDirsOnly
        )
        if not path or not os.path.isdir(path):
            return
        self.book_dir = path
        self.config['book_dir'] = path
        _save_config(self.config)
        print(f"📁 Book dir: {path}")
        self.switch_to_view(self.current_view)

    def scan_txt_files(self):
        """Scan book_dir recursively for .txt files."""
        self.txt_files = sorted(
            os.path.join(root, f)
            for root, _, files in os.walk(self.book_dir)
            for f in files
            if f.lower().endswith('.txt')
        )
        if self.current_file_path not in self.txt_files:
            self.txt_files.append(self.current_file_path)
            self.txt_files.sort()
        self.current_file_index = self.txt_files.index(self.current_file_path)

    def switch_to_file(self, file_path):
        if not os.path.exists(file_path):
            open(file_path, 'w', encoding='utf-8').close()
        self.current_file_path = file_path
        self.current_file_index = self.txt_files.index(file_path)
        print(f"📂 Write target: {os.path.basename(file_path)}")
        if self.current_view == 0:
            self.entry.setText(self.line_ring.current())
            self.entry.setCursorPosition(0)

    def show_previous_file(self):
        if not self.txt_files:
            return
        self.current_file_index = (self.current_file_index - 1) % len(self.txt_files)
        self.switch_to_file(self.txt_files[self.current_file_index])

    def show_next_file(self):
        if not self.txt_files:
            return
        self.current_file_index = (self.current_file_index + 1) % len(self.txt_files)
        self.switch_to_file(self.txt_files[self.current_file_index])

    def _backup_vault(self):
        """Ctrl+B: pick a destination folder, copy void_dir there.
        Folder name: {voidname}_{YY}-{MM}-{DD}({n})
        where n is how many backups of this vault already exist in that destination."""
        dest_root = QFileDialog.getExistingDirectory(
            self, "Backup destination folder", os.path.expanduser("~"))
        if not dest_root:
            return  # cancelled
        try:
            now = datetime.datetime.now()
            src_dir = self.void_dir
            vault_name = os.path.basename(os.path.normpath(src_dir))
            date_str = now.strftime(f'{str(now.year)[2:]}-{now.strftime("%m-%d")}')
            prefix = f"{vault_name}_{date_str}"
            # Count existing backups of this vault on this date
            existing = [d for d in os.listdir(dest_root)
                        if os.path.isdir(os.path.join(dest_root, d))
                        and d.startswith(f"{prefix}")]
            n = len(existing) + 1
            folder_name = f"{prefix}({n})"
            backup_dest = os.path.join(dest_root, folder_name)
            os.makedirs(backup_dest, exist_ok=True)
            count = 0
            for root, dirs, files in os.walk(src_dir):
                for fname in files:
                    if not fname.lower().endswith('.txt'):
                        continue
                    src = os.path.join(root, fname)
                    rel = os.path.relpath(root, src_dir)
                    dst_dir = os.path.join(backup_dest, rel)
                    os.makedirs(dst_dir, exist_ok=True)
                    shutil.copy2(src, os.path.join(dst_dir, fname))
                    count += 1
            print(f"📦 Backup: {count} archivos → {folder_name}")
        except Exception as e:
            print(f"⚠️ Backup error: {e}")

    def take_screenshot(self):
        """F12: Capture the full screen and save to void_dir/screenshots/."""
        screen = self.screen()
        pixmap = screen.grabWindow(0)
        screenshots_dir = os.path.join(self.void_dir, 'screenshots')
        os.makedirs(screenshots_dir, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(screenshots_dir, f"snap_{ts}.png")
        pixmap.save(path)
        print(f"📸 Screenshot: {path}")

    def open_screenshots_folder(self):
        """Ctrl+F12: Open the screenshots folder in the system file explorer."""
        screenshots_dir = os.path.join(self.void_dir, 'screenshots')
        os.makedirs(screenshots_dir, exist_ok=True)
        subprocess.Popen(['xdg-open', screenshots_dir])

    def _printer_from_dialog(self):
        """Show QPrintDialog and return ready printer, or None if cancelled."""
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialog = QPrintDialog(printer, self)
        if dialog.exec() != QPrintDialog.DialogCode.Accepted:
            return None
        return printer

    def _printer_from_save_dialog(self, default_path):
        """Show save-as dialog and return a PDF printer, or None if cancelled."""
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, 'Save as', default_path, 'PDF (*.pdf)')
        if not path:
            return None
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(path)
        return printer

    def _send_to_printer(self, printer, html):
        from PyQt6.QtGui import QTextDocument
        doc = QTextDocument()
        doc.setHtml(html)
        doc.print(printer)

    def print_book(self):
        """Ctrl+P in F3: send all chapters to physical printer."""
        printer = self._printer_from_dialog()
        if printer is None:
            return
        printable = [l for l in self._library_lines if l and l != '.']
        html_parts = []
        for i, fname in enumerate(printable):
            fpath = self._library_path_cache.get(fname, '')
            title = os.path.splitext(fname)[0]
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    lines = [l.strip() for l in f if l.strip()]
            except Exception:
                lines = []
            if i > 0:
                html_parts.append('<div style="page-break-before:always;"></div>')
            html_parts.append(self._build_doc_html(lines, title))
        full_html = ('<html><body style="color:black;background:white;'
                     'font-family:Consolas,monospace;">'
                     + ''.join(html_parts) + '</body></html>')
        self._send_to_printer(printer, full_html)

    def export_book(self):
        """Ctrl+S in F3: save all books from library as PDF."""
        book_name = os.path.basename(os.path.normpath(self.void_dir))
        default_path = os.path.join(self.void_dir, book_name + '.pdf')
        printer = self._printer_from_save_dialog(default_path)
        if printer is None:
            return
        printable = [l for l in self._library_lines if l and l != '.']
        html_parts = []
        for i, fname in enumerate(printable):
            fpath = self._library_path_cache.get(fname, '')
            title = os.path.splitext(fname)[0]
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    lines = [l.strip() for l in f if l.strip()]
            except Exception:
                lines = []
            if i > 0:
                html_parts.append('<div style="page-break-before:always;"></div>')
            html_parts.append(self._build_doc_html(lines, title))
        full_html = ('<html><body style="color:black;background:white;'
                     'font-family:Consolas,monospace;">'
                     + ''.join(html_parts) + '</body></html>')
        self._send_to_printer(printer, full_html)

    def print_doc(self):
        """Ctrl+P in F2: send active file to physical printer."""
        printer = self._printer_from_dialog()
        if printer is None:
            return
        self._render_doc(printer)

    def export_doc(self):
        """Ctrl+S in F2: save active file as PDF, pre-named after the file."""
        doc_path = self.current_file_path
        file_name = os.path.splitext(os.path.basename(doc_path))[0]
        default_path = os.path.join(os.path.dirname(doc_path), file_name + '.pdf')
        printer = self._printer_from_save_dialog(default_path)
        if printer is None:
            return
        self._render_doc(printer)

    def print_vault(self):
        """Ctrl+P in F4: print the current document as prose."""
        printer = self._printer_from_dialog()
        if printer is None:
            return
        self._render_doc(printer)

    def export_vault(self):
        """Ctrl+S in F4: export the current document as prose PDF."""
        title = os.path.splitext(os.path.basename(self.current_file_path))[0]
        default_path = os.path.join(self.void_dir, title + '.pdf')
        printer = self._printer_from_save_dialog(default_path)
        if printer is None:
            return
        self._render_doc(printer)

    def _render_doc(self, printer):
        """Build HTML from the active file and send to printer."""
        doc_path = self.current_file_path
        try:
            with open(doc_path, 'r', encoding='utf-8') as f:
                lines = [l.strip() for l in f if l.strip()]
        except Exception as e:
            print(f"❌ Print error reading file: {e}")
            return
        title = os.path.splitext(os.path.basename(doc_path))[0]
        self._send_to_printer(printer, self._build_doc_html(lines, title))

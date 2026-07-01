"""Text-content undo/redo for Voider.

Pure data structure: each entry is a transaction holding, per affected file, its
`before` and `after` line lists. Consecutive writes that share a coalesce key on
the SAME single file merge into one entry, so a burst of typing on one line is a
single undo step. Recording anything clears the redo stack. Capped, in-memory.

The app captures entries at its write chokepoint and applies `before`/`after`
through the same atomic writer on undo/redo (see io_mixin).
"""


class UndoManager:
    def __init__(self, cap=300):
        self._undo = []   # list of entries: {'files': [(path, before, after)], 'key': key}
        self._redo = []
        self._cap = cap

    def can_undo(self):
        return bool(self._undo)

    def can_redo(self):
        return bool(self._redo)

    def clear(self):
        self._undo.clear()
        self._redo.clear()

    def record(self, path, before, after, key=None):
        """Record a single-file change. Merges into the top entry when `key`
        matches and that entry is the same single file (edit-burst coalescing)."""
        before, after = list(before), list(after)
        if before == after:
            return
        if key is not None and self._undo:
            top = self._undo[-1]
            if (top['key'] == key and len(top['files']) == 1
                    and top['files'][0][0] == path):
                p, b, _ = top['files'][0]
                top['files'][0] = (p, b, after)   # keep original before, new after
                self._redo.clear()
                return
        self._push({'files': [(path, before, after)], 'key': key})

    def record_library(self, before, after):
        """Record a whole F3 library/structural change (reorder, rename, delete,
        merge, split) as ONE step. `before`/`after` are state snapshots (dicts with
        'lib', 'ring', 'idx', 'cache', 'files'); restored wholesale on undo/redo."""
        if before == after:
            return
        self._push({'kind': 'library', 'before': before, 'after': after})

    def record_transaction(self, changes, key=None):
        """Record several files changed as ONE undo step (e.g. F5 dispatch:
        source + target). `changes` = iterable of (path, before, after)."""
        files = [(p, list(b), list(a)) for (p, b, a) in changes if list(b) != list(a)]
        if not files:
            return
        self._push({'files': files, 'key': key})

    def _push(self, entry):
        self._undo.append(entry)
        if len(self._undo) > self._cap:
            self._undo.pop(0)
        self._redo.clear()

    def undo(self):
        """Pop the last change; return its entry so the caller can restore each
        file's `before`. Returns None if nothing to undo."""
        if not self._undo:
            return None
        entry = self._undo.pop()
        self._redo.append(entry)
        return entry

    def redo(self):
        """Re-apply the last undone change; caller restores each file's `after`."""
        if not self._redo:
            return None
        entry = self._redo.pop()
        self._undo.append(entry)
        return entry

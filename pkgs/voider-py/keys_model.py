"""keys_model.py — the F10 keys list as a pure model (no Qt widgets).

A ring of rows like F3: a title row first (the source, not editable), one row per
action with its key, and a last row that opens the settings form. Remaps are kept
as overrides over the defaults; only overrides ever reach keybindings.json."""
from collections import namedtuple

from PyQt6.QtCore import Qt

from app_config import _format_keybinding

TITLE_ROW = '__title__'
SETTINGS_ROW = '__settings__'
PAGE = 10

Row = namedtuple('Row', 'action keytext custom')


class KeysModel:
    def __init__(self, defaults, overrides):
        self.defaults = dict(defaults)
        self._overrides = {a: k for a, k in overrides.items()
                           if self.defaults.get(a) != k}
        self.index = 0
        self.capturing = False
        self.clash = None            # other action sharing the last captured key

    @property
    def overrides(self):
        return dict(self._overrides)

    @property
    def rows(self):
        out = [Row(TITLE_ROW, '', False)]
        for action, default in self.defaults.items():
            custom = action in self._overrides
            out.append(Row(action, self._overrides.get(action, default), custom))
        out.append(Row(SETTINGS_ROW, '', False))
        return out

    def current(self):
        return self.rows[self.index]

    def move(self, delta):
        self.index = (self.index + delta) % len(self.rows)

    def page(self, direction):
        self.index = max(0, min(len(self.rows) - 1, self.index + direction * PAGE))

    def _editable(self):
        return self.current().action not in (TITLE_ROW, SETTINGS_ROW)

    def begin_capture(self):
        if not self._editable():
            return False
        self.capturing = True
        self.clash = None
        return True

    def capture(self, key, mods):
        """Feed the key pressed while capturing. Returns 'ok', 'cancel', 'refused'
        (cannot be stored; stay open) or 'wait' (just a modifier)."""
        if key == Qt.Key.Key_Escape:
            self.capturing = False
            return 'cancel'
        if key in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt,
                   Qt.Key.Key_Meta, Qt.Key.Key_AltGr):
            return 'wait'
        text = _format_keybinding(key, mods)
        if text is None:
            return 'refused'
        action = self.current().action
        self.clash = next((r.action for r in self.rows
                           if r.action != action and r.keytext == text
                           and r.action not in (TITLE_ROW, SETTINGS_ROW)), None)
        if self.defaults.get(action) == text:
            self._overrides.pop(action, None)
        else:
            self._overrides[action] = text
        self.capturing = False
        return 'ok'

    def reset(self):
        """Back to the default for the current row. True if something changed."""
        if not self._editable():
            return False
        return self._overrides.pop(self.current().action, None) is not None

"""keys_model.py — the F10 list as a pure model (no Qt widgets).

A ring of rows like F3: a title row first (the source, not editable), the
settings (font, colours, carousel…), then one row per action with its key. Keys
are remapped by capturing the next key press; settings by typing a value, or by
stepping/cycling it. Remaps are kept as overrides over the defaults; only
overrides ever reach keybindings.json."""
import re
from collections import namedtuple

from PyQt6.QtCore import Qt

from app_config import _format_keybinding

TITLE_ROW = '__title__'
SET_PREFIX = 'set:'
PAGE = 10

Row = namedtuple('Row', 'action keytext custom kind', defaults=('key',))

SettingDef = namedtuple('SettingDef', 'key label kind choices lo hi',
                        defaults=((), None, None))

SETTING_DEFS = (
    SettingDef('font_family', 'font', 'font'),
    SettingDef('font_size', 'font size', 'int', lo=4, hi=999),
    SettingDef('text_color', 'text color', 'color'),
    SettingDef('bg_color', 'background color', 'color'),
    SettingDef('carousel_preset', 'carousel ratio', 'choice',
               choices=('1:1', '4:5', '1.91:1', 'custom')),
    SettingDef('carousel_w', 'carousel width', 'int', lo=100, hi=8000),
    SettingDef('carousel_h', 'carousel height', 'int', lo=100, hi=8000),
    SettingDef('visualizer_source', 'visualizer source', 'choice',
               choices=('off', 'mic', 'output')),
    SettingDef('visualizer_style', 'visualizer style', 'choice',
               choices=('pulse', 'wave', 'bars')),
    SettingDef('dictation_language', 'dictation language', 'choice',
               choices=('es', 'en', 'auto')),
)
_DEF_BY_KEY = {d.key: d for d in SETTING_DEFS}
_HEX = re.compile(r'^#[0-9a-fA-F]{6}$')


class KeysModel:
    def __init__(self, defaults, overrides, values=None, fonts=None):
        self.defaults = dict(defaults)
        self._overrides = {a: k for a, k in overrides.items()
                           if self.defaults.get(a) != k}
        self.values = dict(values or {})
        self.fonts = list(fonts) if fonts else None
        self.index = 0
        self.capturing = False
        self.clash = None            # other action sharing the last captured key
        self.editing = False         # typing a setting value
        self.buffer = ''
        self.error = ''

    @property
    def overrides(self):
        return dict(self._overrides)

    @property
    def rows(self):
        out = [Row(TITLE_ROW, '', False, 'title')]
        for d in SETTING_DEFS:
            out.append(Row(SET_PREFIX + d.key, str(self.values.get(d.key, '')),
                           False, 'setting'))
        for action, default in self.defaults.items():
            custom = action in self._overrides
            out.append(Row(action, self._overrides.get(action, default), custom))
        return out

    def current(self):
        return self.rows[self.index]

    def move(self, delta):
        self.index = (self.index + delta) % len(self.rows)

    def page(self, direction):
        self.index = max(0, min(len(self.rows) - 1, self.index + direction * PAGE))

    # ── keys ────────────────────────────────────────────────────────────────

    def _editable(self):
        return self.current().kind == 'key'

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
                           if r.kind == 'key' and r.action != action
                           and r.keytext == text), None)
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

    # ── settings ────────────────────────────────────────────────────────────

    def _setting(self):
        row = self.current()
        return _DEF_BY_KEY.get(row.action[len(SET_PREFIX):]) if row.kind == 'setting' else None

    def begin_edit(self):
        d = self._setting()
        if d is None or d.kind == 'choice':
            return False
        self.editing = True
        self.buffer = str(self.values.get(d.key, ''))
        self.error = ''
        return True

    def type(self, text):
        if self.editing:
            self.buffer += text

    def backspace(self):
        if self.editing:
            self.buffer = self.buffer[:-1]

    def cancel_edit(self):
        self.editing = False
        self.buffer = ''
        self.error = ''

    def commit(self):
        """('ok', key, value) when the typed value is valid; ('refused', why) and
        the edit stays open otherwise."""
        d = self._setting()
        if not self.editing or d is None:
            return ('refused', 'nothing to commit')
        raw = self.buffer.strip()
        if d.kind == 'int':
            if not raw.isdigit() or not (d.lo <= int(raw) <= d.hi):
                self.error = f"número entre {d.lo} y {d.hi}"
                return ('refused', self.error)
            value = int(raw)
        elif d.kind == 'color':
            if not _HEX.match(raw):
                self.error = 'color como #rrggbb'
                return ('refused', self.error)
            value = raw
        else:                                        # font
            if self.fonts is not None:
                match = next((f for f in self.fonts if f.lower() == raw.lower()), None)
                if match is None:
                    self.error = 'esa fuente no está instalada'
                    return ('refused', self.error)
                raw = match
            if not raw:
                self.error = 'escribí el nombre de una fuente'
                return ('refused', self.error)
            value = raw
        self.values[d.key] = value
        self.cancel_edit()
        return ('ok', d.key, value)

    def cycle(self, direction):
        """Left/Right (or Enter) on a choice or int setting. (key, value) when the
        value changed, else None."""
        d = self._setting()
        if d is None:
            return None
        cur = self.values.get(d.key)
        if d.kind == 'choice':
            opts = list(d.choices)
            i = opts.index(cur) if cur in opts else -1
            value = opts[(i + direction) % len(opts)]
        elif d.kind == 'int':
            value = max(d.lo, min(d.hi, int(cur) + direction))
            if value == cur:
                return None
        else:
            return None
        self.values[d.key] = value
        return (d.key, value)

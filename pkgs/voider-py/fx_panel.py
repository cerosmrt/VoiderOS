# fx_panel.py — in-app parameter panel for Hyprland visual effects
import os
import subprocess
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QColor, QFont
from PyQt6.QtCore import Qt, QRect

# ── Parameter definitions ────────────────────────────────────────────────────

PARAM_DEFS = {
    'crt': [
        {'label': 'Enabled',   'key': 'crt',           'type': 'bool',  'default': 0},
        {'label': 'Intensity', 'key': 'crt_intensity',  'type': 'float',
         'min': 0.0,  'max': 1.0,  'step': 0.05, 'default': 0.3,  'fmt': '.2f'},
        {'label': 'Scanlines', 'key': 'crt_thickness',  'type': 'int',
         'min': 1,    'max': 4,    'step': 1,    'default': 2,    'suffix': 'px'},
        {'label': 'Vignette',  'key': 'crt_vignette',   'type': 'float',
         'min': 0.0,  'max': 1.0,  'step': 0.05, 'default': 0.7,  'fmt': '.2f'},
    ],
    'grain': [
        {'label': 'Enabled',   'key': 'grain',           'type': 'bool',  'default': 0},
        {'label': 'Intensity', 'key': 'grain_intensity',  'type': 'float',
         'min': 0.0,  'max': 1.0,  'step': 0.05, 'default': 0.2,  'fmt': '.2f'},
        {'label': 'Speed',     'key': 'grain_speed',      'type': 'float',
         'min': 1.0,  'max': 20.0, 'step': 1.0,  'default': 5.0,  'fmt': '.0f', 'suffix': 'x'},
        {'label': 'Size',      'key': 'grain_size',       'type': 'enum',
         'options': ['fine', 'medium', 'coarse'], 'default': 'fine'},
    ],
    'bw': [
        {'label': 'Enabled',  'key': 'bw',           'type': 'bool',  'default': 0},
        {'label': 'Blend',    'key': 'bw_blend',     'type': 'float',
         'min': 0.0,  'max': 1.0,  'step': 0.05, 'default': 0.0,  'fmt': '.2f'},
        {'label': 'Contrast', 'key': 'bw_contrast',  'type': 'float',
         'min': 0.5,  'max': 2.0,  'step': 0.1,  'default': 1.0,  'fmt': '.1f'},
    ],
}

TITLES = {
    'crt':   'CRT SCANLINES',
    'grain': 'FILM GRAIN',
    'bw':    'BLACK & WHITE',
}

STATE_FILE = '/tmp/voider-fx'

# Flat map of all parameter defaults (used for initial state)
_ALL_DEFAULTS: dict = {}
for _effect, _defs in PARAM_DEFS.items():
    _ALL_DEFAULTS[_effect] = 0           # all effects off by default
    for _p in _defs:
        if _p['key'] != _effect:
            _ALL_DEFAULTS[_p['key']] = _p['default']


# ── State I/O ─────────────────────────────────────────────────────────────────

def _read_state() -> dict:
    state = dict(_ALL_DEFAULTS)
    try:
        with open(STATE_FILE) as f:
            for line in f:
                line = line.strip()
                if '=' not in line:
                    continue
                k, v = line.split('=', 1)
                if k not in state:
                    continue
                ref = state[k]
                if isinstance(ref, int):
                    state[k] = int(v)
                elif isinstance(ref, float):
                    state[k] = float(v)
                else:
                    state[k] = v
    except OSError:
        pass
    return state


def _write_state(state: dict) -> None:
    lines = []
    for effect in ('crt', 'grain', 'bw'):
        lines.append(f'{effect}={state.get(effect, 0)}')
        for p in PARAM_DEFS.get(effect, []):
            if p['key'] == effect:
                continue
            v = state.get(p['key'], p['default'])
            if isinstance(v, float):
                lines.append(f'{p["key"]}={v:.4f}')
            else:
                lines.append(f'{p["key"]}={v}')
    try:
        with open(STATE_FILE, 'w') as f:
            f.write('\n'.join(lines) + '\n')
    except OSError:
        pass


def _apply_shader() -> None:
    try:
        subprocess.run(
            ['voider-fx-update'],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        pass


# ── Panel widget ──────────────────────────────────────────────────────────────

class FxPanel(QWidget):
    """Full-screen in-app overlay for tuning shader parameters.

    Layout (centered, Voider-style):
        EFFECT TITLE
        ─────────────
        → Label   ← value →
          Label      value
        ─────────────
        ESC  close
    """

    _BG_ALPHA  = 215
    _ROW_H     = 46
    _TITLE_GAP = 52   # px between title and first row

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._effect: str | None = None
        self._row   : int        = 0
        self._state : dict       = {}
        self.hide()

    # ── Public API ────────────────────────────────────────────────────────────

    def open_panel(self, effect: str) -> None:
        if effect not in PARAM_DEFS:
            return
        self._effect = effect
        self._row    = 0
        self._state  = _read_state()
        # Enabling the effect immediately so the user sees real-time feedback
        self._state[effect] = 1
        _write_state(self._state)
        _apply_shader()
        self.show()
        self.raise_()
        self.setFocus()
        self.update()

    def close_panel(self) -> None:
        self._effect = None
        self.hide()
        app = self.parentWidget()
        if app and hasattr(app, '_refocus_active_editor'):
            app._refocus_active_editor()

    @property
    def current_effect(self) -> str | None:
        return self._effect

    # ── Keyboard ──────────────────────────────────────────────────────────────

    def keyPressEvent(self, event):
        k = event.key()
        if k == Qt.Key.Key_Escape:
            self.close_panel()
        elif k == Qt.Key.Key_R:
            self._reset_all()
        elif k == Qt.Key.Key_Up:
            self._row = max(0, self._row - 1)
            self.update()
        elif k == Qt.Key.Key_Down:
            n = len(PARAM_DEFS.get(self._effect, []))
            self._row = min(n - 1, self._row + 1)
            self.update()
        elif k in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            self._adjust(1 if k == Qt.Key.Key_Right else -1)
        # Eat every key so nothing bleeds into the main app
        event.accept()

    def _reset_all(self) -> None:
        self._state = dict(_ALL_DEFAULTS)
        _write_state(self._state)
        _apply_shader()
        self.close_panel()

    # ── Value adjustment ──────────────────────────────────────────────────────

    def _adjust(self, direction: int) -> None:
        defs = PARAM_DEFS.get(self._effect, [])
        if self._row >= len(defs):
            return
        p = defs[self._row]
        k = p['key']
        cur = self._state.get(k, p['default'])

        if p['type'] == 'bool':
            self._state[k] = 0 if cur else 1
        elif p['type'] == 'float':
            self._state[k] = round(
                max(p['min'], min(p['max'], cur + direction * p['step'])), 6)
        elif p['type'] == 'int':
            self._state[k] = max(p['min'], min(p['max'], cur + direction * p['step']))
        elif p['type'] == 'enum':
            opts = p['options']
            idx  = opts.index(cur) if cur in opts else 0
            self._state[k] = opts[(idx + direction) % len(opts)]

        _write_state(self._state)
        _apply_shader()
        self.update()

    # ── Display helpers ───────────────────────────────────────────────────────

    def _display_value(self, p: dict) -> str:
        v = self._state.get(p['key'], p['default'])
        t = p['type']
        if t == 'bool':
            return 'on' if v else 'off'
        if t == 'enum':
            return str(v)
        if t == 'float':
            return f'{v:{p.get("fmt", ".2f")}}{p.get("suffix", "")}'
        if t == 'int':
            return f'{v}{p.get("suffix", "")}'
        return str(v)

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        if not self._effect:
            return
        defs = PARAM_DEFS.get(self._effect, [])

        painter = QPainter(self)
        if not painter.isActive():
            return

        W, H = self.width(), self.height()

        # Semi-transparent black overlay
        painter.fillRect(0, 0, W, H, QColor(0, 0, 0, self._BG_ALPHA))

        app  = self.parentWidget()
        font = app._app_font if hasattr(app, '_app_font') else QFont('Monospace', 14)
        painter.setFont(font)
        fm = painter.fontMetrics()

        title = TITLES.get(self._effect, self._effect.upper())
        n     = len(defs)

        # Vertical layout
        block_h   = fm.height() + self._TITLE_GAP + n * self._ROW_H + 32
        block_top = (H - block_h) // 2

        # ── Title ─────────────────────────────────────────────────────────────
        painter.setPen(QColor(255, 255, 255, 200))
        painter.drawText(
            QRect(0, block_top, W, fm.height()),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
            title,
        )

        # ── Separator ─────────────────────────────────────────────────────────
        sep_y = block_top + fm.height() + 16
        sep_w = 260
        sep_x = (W - sep_w) // 2
        painter.setPen(QColor(60, 60, 60))
        painter.drawLine(sep_x, sep_y, sep_x + sep_w, sep_y)

        # ── Rows ──────────────────────────────────────────────────────────────
        # Figure out column positions from the widest label
        label_w = max(fm.horizontalAdvance(p['label']) for p in defs)
        col_w   = label_w + 20 + 160         # label + gap + value area
        col_x   = (W - col_w) // 2

        params_top = sep_y + 16

        for i, p in enumerate(defs):
            y        = params_top + i * self._ROW_H
            selected = (i == self._row)

            painter.setPen(QColor('white') if selected else QColor(120, 120, 120))

            # Cursor marker
            cursor = '›' if selected else ' '
            painter.drawText(
                QRect(col_x - 20, y, 20, self._ROW_H),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                cursor,
            )

            # Label
            painter.drawText(
                QRect(col_x, y, label_w, self._ROW_H),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                p['label'],
            )

            # Value — show arrows only on selected row
            val = self._display_value(p)
            val_str = f'← {val} →' if selected else f'   {val}'
            painter.drawText(
                QRect(col_x + label_w + 20, y, 160, self._ROW_H),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                val_str,
            )

        # ── Bottom separator ──────────────────────────────────────────────────
        bot_sep_y = params_top + n * self._ROW_H + 8
        painter.setPen(QColor(60, 60, 60))
        painter.drawLine(sep_x, bot_sep_y, sep_x + sep_w, bot_sep_y)

        # ── Footer ────────────────────────────────────────────────────────────
        painter.setPen(QColor(60, 60, 60))
        painter.drawText(
            QRect(0, bot_sep_y + 12, W, fm.height()),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
            'R  reset all   ESC  close',
        )

        painter.end()

"""keys_panel.py — F10: settings and the key map as one list shaped like F3.

First row is the title (this is the configuration), then the settings, then one
row per action with its key. Up/Down and PageUp/PageDown move. On a key row,
Enter waits for the new key and Delete restores its default. On a setting row,
Enter types a value (Enter confirms, Esc cancels), Left/Right step or cycle it."""
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QColor, QFont, QFontMetrics
from PyQt6.QtCore import Qt, QRect, pyqtSignal

from i18n import t
from keys_model import KeysModel, TITLE_ROW
from widgets import row_alpha, LINE_SPACING


class KeysPanel(QWidget):
    remapped = pyqtSignal(dict)            # the full overrides dict, after any change
    setting_changed = pyqtSignal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.model = KeysModel({}, {})
        self._note = ''              # one-line feedback under the list

    def load(self, defaults, overrides, values=None, fonts=None):
        keep = self.model.index
        self.model = KeysModel(defaults, overrides, values, fonts)
        self.model.index = min(keep, len(self.model.rows) - 1)
        self._note = ''
        self.update()

    @property
    def capturing(self):
        return self.model.capturing

    @property
    def busy(self):
        """Waiting for a key, or typing a value: the app must leave every key alone."""
        return self.model.capturing or self.model.editing

    def focusNextPrevChild(self, forward):
        # Tab must reach keyPressEvent while capturing, not move the focus.
        return False if self.model.capturing else super().focusNextPrevChild(forward)

    def _emit_setting(self, change):
        if change is not None:
            self.setting_changed.emit(change[0], change[1])

    def keyPressEvent(self, event):
        m, key, mods = self.model, event.key(), event.modifiers()
        if m.capturing:
            result = m.capture(key, mods)
            if result == 'ok':
                self._note = (t('keys.clash', clash=m.clash) if m.clash else '')
                self.remapped.emit(m.overrides)
            elif result == 'refused':
                self._note = t('keys.refused')
            elif result == 'cancel':
                self._note = ''
            event.accept()
            self.update()
            return
        if m.editing:
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                result = m.commit()
                if result[0] == 'ok':
                    self._note = ''
                    self.setting_changed.emit(result[1], result[2])
                else:
                    self._note = result[1]
            elif key == Qt.Key.Key_Escape:
                m.cancel_edit()
                self._note = ''
            elif key == Qt.Key.Key_Backspace:
                m.backspace()
            elif event.text() and event.text().isprintable():
                m.type(event.text())
            event.accept()
            self.update()
            return
        row = m.current()
        if key == Qt.Key.Key_Down:
            m.move(1)
        elif key == Qt.Key.Key_Up:
            m.move(-1)
        elif key == Qt.Key.Key_PageDown:
            m.page(1)
        elif key == Qt.Key.Key_PageUp:
            m.page(-1)
        elif key == Qt.Key.Key_Right and row.kind == 'setting':
            self._emit_setting(m.cycle(1))
        elif key == Qt.Key.Key_Left and row.kind == 'setting':
            self._emit_setting(m.cycle(-1))
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if row.kind == 'setting':
                if not m.begin_edit():                  # a choice: Enter steps it
                    self._emit_setting(m.cycle(1))
            elif m.begin_capture():
                self._note = ''
        elif key == Qt.Key.Key_Delete:
            if m.reset():
                self._note = ''
                self.remapped.emit(m.overrides)
        else:
            event.ignore()           # Esc, F10, etc. belong to the app
            return
        event.accept()
        self.update()

    def _text(self, row):
        m = self.model
        if row.action == TITLE_ROW:
            return t('keys.title')
        is_cur = row is m.current() or row == m.current()
        if row.kind == 'setting':
            label = row.action.split(':', 1)[1].replace('_', ' ')
            if m.editing and is_cur:
                return f"{label}   —   {m.buffer}▏"
            return f"{label}   —   {row.keytext}"
        label = row.action.replace('_', ' ')
        if m.capturing and is_cur:
            return f"{label}   —   {t('keys.press_new')}"
        mark = ' *' if row.custom else ''
        return f"{label}   —   {row.keytext}{mark}"

    def paintEvent(self, event):
        painter = QPainter(self)
        if not painter.isActive():
            return
        W, H = self.width(), self.height()
        painter.fillRect(0, 0, W, H, QColor(0, 0, 0))
        app = self.window()
        font = QFont(getattr(app, '_app_font', QFont('Consolas', 13)))
        painter.setFont(font)
        lh = int(QFontMetrics(font).height() * LINE_SPACING)
        rows, cur = self.model.rows, self.model.index
        cy = H // 2
        for i, row in enumerate(rows):
            y = cy + (i - cur) * lh
            if y + lh < 0 or y > H:
                continue
            dist = abs(y - cy)
            painter.setOpacity(row_alpha(dist, H / 2) if i != cur else 1.0)
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(QRect(0, y - lh // 2, W, lh), Qt.AlignmentFlag.AlignCenter,
                             self._text(row))
        if self._note:
            painter.setOpacity(0.6)
            painter.drawText(QRect(0, H - 2 * lh, W, lh), Qt.AlignmentFlag.AlignCenter,
                             self._note)
        painter.end()

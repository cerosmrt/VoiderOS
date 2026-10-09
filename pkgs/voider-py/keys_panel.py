"""keys_panel.py — F10: the key map as a list shaped like F3.

First row is the title (this is the configuration), then one row per action with
its key, then a row that opens the settings form. Up/Down and PageUp/PageDown
move; Enter on an action waits for the new key; Delete restores its default."""
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QColor, QFont, QFontMetrics
from PyQt6.QtCore import Qt, QRect, pyqtSignal

from keys_model import KeysModel, TITLE_ROW, SETTINGS_ROW
from widgets import row_alpha, LINE_SPACING


class KeysPanel(QWidget):
    remapped = pyqtSignal(dict)      # the full overrides dict, after any change
    open_settings = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.model = KeysModel({}, {})
        self._note = ''              # one-line feedback under the list

    def load(self, defaults, overrides):
        keep = self.model.index
        self.model = KeysModel(defaults, overrides)
        self.model.index = min(keep, len(self.model.rows) - 1)
        self._note = ''
        self.update()

    @property
    def capturing(self):
        return self.model.capturing

    def focusNextPrevChild(self, forward):
        # Tab must reach keyPressEvent while capturing, not move the focus.
        return False if self.model.capturing else super().focusNextPrevChild(forward)

    def keyPressEvent(self, event):
        m, key, mods = self.model, event.key(), event.modifiers()
        if m.capturing:
            result = m.capture(key, mods)
            if result == 'ok':
                self._note = (f"también usa esa tecla: {m.clash}" if m.clash else '')
                self.remapped.emit(m.overrides)
            elif result == 'refused':
                self._note = 'esa tecla no se puede asignar'
            elif result == 'cancel':
                self._note = ''
            event.accept()
            self.update()
            return
        if key == Qt.Key.Key_Down:
            m.move(1)
        elif key == Qt.Key.Key_Up:
            m.move(-1)
        elif key == Qt.Key.Key_PageDown:
            m.page(1)
        elif key == Qt.Key.Key_PageUp:
            m.page(-1)
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if m.current().action == SETTINGS_ROW:
                self.open_settings.emit()
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
        if row.action == TITLE_ROW:
            return 'Configuración'
        if row.action == SETTINGS_ROW:
            return 'Ajustes…'
        label = row.action.replace('_', ' ')
        if self.model.capturing and row is self.model.current():
            return f"{label}   —   apretá la tecla nueva (Esc cancela)"
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
            dist = abs(y + lh / 2 - cy - lh / 2)
            painter.setOpacity(row_alpha(dist, H / 2) if i != cur else 1.0)
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(QRect(0, y - lh // 2, W, lh), Qt.AlignmentFlag.AlignCenter,
                             self._text(row))
        if self._note:
            painter.setOpacity(0.6)
            painter.drawText(QRect(0, H - 2 * lh, W, lh), Qt.AlignmentFlag.AlignCenter,
                             self._note)
        painter.end()

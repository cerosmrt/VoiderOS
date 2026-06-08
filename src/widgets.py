# widgets.py
import numpy as np
from PyQt6.QtWidgets import QLineEdit, QWidget
from PyQt6.QtGui import QPainter, QPixmap, QImage
from PyQt6.QtCore import Qt, QTimer, pyqtSignal


class CustomLineEdit(QLineEdit):
    """QLineEdit with spacebar-as-void, Ctrl shortcut, and app-launch support."""
    spacePressed   = pyqtSignal()
    launchPressed  = pyqtSignal()   # Ctrl+Enter → launch current text as a command

    _FADE_MS = 180
    _TICK_MS = 16

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self._char_opacities = []
        self._fade_timer = QTimer(self)
        self._fade_timer.timeout.connect(self._fade_tick)
        self.textEdited.connect(self._on_text_edited)

    def _on_text_edited(self, text):
        cur_len = len(text)
        old_len = len(self._char_opacities)
        if cur_len > old_len:
            self._char_opacities.extend([0.0] * (cur_len - old_len))
            if not self._fade_timer.isActive():
                self._fade_timer.start(self._TICK_MS)
        else:
            self._char_opacities = self._char_opacities[:cur_len]

    def _fade_tick(self):
        step = self._TICK_MS / self._FADE_MS
        self._char_opacities = [min(1.0, a + step) for a in self._char_opacities]
        self.update()
        if all(a >= 1.0 for a in self._char_opacities):
            self._fade_timer.stop()

    def setText(self, text):
        super().setText(text)
        self._char_opacities = [1.0] * len(text)
        self._fade_timer.stop()

    def clear(self):
        super().clear()
        self._char_opacities = []
        self._fade_timer.stop()

    def paintEvent(self, event):
        super().paintEvent(event)
        text = self.text()
        if not text:
            return
        opacities = self._char_opacities[:len(text)]
        if not opacities or all(a >= 1.0 for a in opacities):
            return
        fm = self.fontMetrics()
        text_w = fm.horizontalAdvance(text)
        rect = self.contentsRect()
        text_x = rect.left() + (rect.width() - text_w) // 2
        painter = QPainter(self)
        for i, alpha in enumerate(opacities):
            if alpha >= 1.0:
                continue
            x = text_x + fm.horizontalAdvance(text[:i])
            w = fm.horizontalAdvance(text[i])
            painter.setOpacity(1.0 - alpha)
            painter.fillRect(x, rect.top(), max(w, 1), rect.height(), Qt.GlobalColor.black)
        painter.end()

    def keyPressEvent(self, event):
        key = event.key()
        modifiers = event.modifiers()

        # * — recycle a random line into the entry
        if key == Qt.Key.Key_Asterisk or (key == Qt.Key.Key_8 and (modifiers & Qt.KeyboardModifier.ShiftModifier)):
            from controls import recycle_line_to_zero_txt
            recycle_line_to_zero_txt(self.parent, event)
            event.accept()
            return

        # Spacebar void mode
        if key == Qt.Key.Key_Space:
            if self.parent.use_spacebar_for_void:
                self.spacePressed.emit()
                event.accept()
                return
            super().keyPressEvent(event)
            return

        # Ctrl+Enter → launch
        ctrl = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and ctrl:
            self.launchPressed.emit()
            event.accept()
            return

        # Ctrl shortcuts
        if key == Qt.Key.Key_0 and (modifiers & Qt.KeyboardModifier.ControlModifier):
            from controls import show_random_line_from_random_file
            show_random_line_from_random_file(self.parent, event)
            event.accept()
        elif key == Qt.Key.Key_Period and (modifiers & Qt.KeyboardModifier.ControlModifier):
            from controls import show_random_line_from_current_file
            show_random_line_from_current_file(self.parent, event)
            event.accept()
        elif (modifiers & Qt.KeyboardModifier.ControlModifier) and key in (
            Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_F12, Qt.Key.Key_P
        ):
            event.ignore()
        else:
            super().keyPressEvent(event)


class ChannelTransition(QWidget):
    """Full-screen static flash played when switching between F1/F2/F3 views."""

    _FLASH_MS   = 80
    _FADEOUT_MS = 160
    _TICK_MS    = 16

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._opacity  = 0.0
        self._elapsed  = 0
        self._flashing = False
        self._pixmap   = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.hide()

    def trigger(self):
        self._elapsed  = 0
        self._flashing = True
        self._opacity  = 1.0
        self._regen_noise()
        self.show()
        self.raise_()
        if not self._timer.isActive():
            self._timer.start(self._TICK_MS)

    def _regen_noise(self):
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return
        arr = np.random.randint(0, 256, (h, w), dtype=np.uint8)
        img = QImage(arr.data, w, h, w, QImage.Format.Format_Grayscale8)
        self._pixmap = QPixmap.fromImage(img.copy())

    def _tick(self):
        self._elapsed += self._TICK_MS
        if self._flashing:
            self._regen_noise()
            if self._elapsed >= self._FLASH_MS:
                self._flashing = False
                self._elapsed  = 0
        else:
            self._opacity = max(0.0, 1.0 - self._elapsed / self._FADEOUT_MS)
            if self._opacity <= 0.0:
                self._timer.stop()
                self.hide()
                return
        self.update()

    def paintEvent(self, event):
        if not self._pixmap or self._opacity <= 0.0:
            return
        painter = QPainter(self)
        if not painter.isActive():
            return
        painter.setOpacity(self._opacity)
        painter.drawPixmap(0, 0, self._pixmap)
        painter.end()

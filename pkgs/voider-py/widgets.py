# widgets.py - Widgets reutilizables
import numpy as np
from PyQt6.QtWidgets import QLineEdit, QWidget
from PyQt6.QtGui import QPainter, QPixmap, QImage
from PyQt6.QtCore import Qt, QTimer, pyqtSignal

class CustomLineEdit(QLineEdit):
    """QLineEdit personalizado con soporte para spacebar como tecla de void"""
    spacePressed = pyqtSignal()

    _FADE_MS = 180   # time for a new character to reach full opacity
    _TICK_MS = 16    # ~60 fps timer

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self._char_opacities = []   # float per char in current text; 1.0 = fully visible
        self._fade_timer = QTimer(self)
        self._fade_timer.timeout.connect(self._fade_tick)
        self.textEdited.connect(self._on_text_edited)

    # ── opacity tracking ──────────────────────────────────────────────────────

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

    # ── painting ──────────────────────────────────────────────────────────────

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
        # Centered: text starts at the horizontal midpoint minus half text width
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

    # ── key handling ─────────────────────────────────────────────────────────

    def keyPressEvent(self, event):
        key = event.key()
        modifiers = event.modifiers()
        
        # Asterisco * para reciclado (interceptar ANTES de escribir)
        if key == Qt.Key.Key_Asterisk or (key == Qt.Key.Key_8 and (modifiers & Qt.KeyboardModifier.ShiftModifier)):
            from controls import recycle_line_to_zero_txt
            recycle_line_to_zero_txt(self.parent, event)
            event.accept()
            return  # IMPORTANTE: return para no seguir procesando
        
        # Manejo de spacebar para void
        if key == Qt.Key.Key_Space:
            if self.parent.use_spacebar_for_void:
                self.spacePressed.emit()
                event.accept()
                return
            super().keyPressEvent(event)
            return
        
        # Atajos con Ctrl
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
            # Forward these Ctrl combos to parent for global keybindings
            event.ignore()
        else:
            super().keyPressEvent(event)


class NoiseOverlay(QWidget):
    """Overlay de ruido visual generativo en tiempo real"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.noise_pixmap = None
        
        # Timer para generar nuevo ruido cada 50ms
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.generate_noise)
        self.timer.start(50)
    
    def generate_noise(self):
        """Genera un patrón de ruido aleatorio tipo TV sin señal"""
        block_size = 1
        w, h = self.width(), self.height()
        
        if w == 0 or h == 0:
            return
            
        h_blocks, w_blocks = h // block_size, w // block_size
        noise_gray = np.random.randint(0, 256, (h_blocks, w_blocks), dtype=np.uint8)
        
        image = QImage(noise_gray.data, w_blocks, h_blocks, w_blocks, 
                      QImage.Format.Format_Grayscale8)
        image = image.scaled(w, h, 
                           Qt.AspectRatioMode.IgnoreAspectRatio, 
                           Qt.TransformationMode.FastTransformation)
        
        self.noise_pixmap = QPixmap.fromImage(image)
        self.update()
    
    def paintEvent(self, event):
        """Dibuja el ruido con opacidad baja"""
        if not self.noise_pixmap or self.width() == 0 or self.height() == 0:
            return
        painter = QPainter(self)
        if not painter.isActive():
            return
        painter.setOpacity(0.09)
        painter.drawPixmap(0, 0, self.noise_pixmap)


class ChannelTransition(QWidget):
    """Full-screen static flash played when switching between F1/F2/F3 views.

    Visual rhythm:
      0 → FLASH_MS  : full-opacity random noise (the 'channel cut')
      FLASH_MS → end: noise fades to transparent (new view is revealed)
    """

    _FLASH_MS   = 80    # ms of full static before fade begins
    _FADEOUT_MS = 160   # ms to dissolve the static away
    _TICK_MS    = 16    # timer interval (~60 fps)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._opacity  = 0.0
        self._elapsed  = 0
        self._flashing = False   # True during the solid-static phase
        self._pixmap   = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.hide()

    def trigger(self):
        """Start the channel-change animation."""
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
        self._pixmap = QPixmap.fromImage(img.copy())  # .copy() owns the data

    def _tick(self):
        self._elapsed += self._TICK_MS
        if self._flashing:
            self._regen_noise()  # keep static flickering every frame
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
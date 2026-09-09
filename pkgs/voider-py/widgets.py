# widgets.py - Widgets reutilizables
import random
from PyQt6.QtWidgets import QLineEdit, QWidget
from PyQt6.QtGui import QPainter, QPixmap, QImage
from PyQt6.QtCore import Qt, QTimer, QEvent, pyqtSignal


def neutralize_caps(editor, event):
    """Caps Lock must never uppercase — it only toggles scriptio-continua. If the
    app's Caps LED is on (window()._capslock_on), type the letter in its normal
    case by swapping the case back. Returns True if it handled the key. Ctrl/Alt
    combos and non-letters pass through untouched. Shared by the F1 entry and the
    F2/F3 doc editor."""
    if event.modifiers() & (Qt.KeyboardModifier.ControlModifier
                            | Qt.KeyboardModifier.AltModifier):
        return False
    caps = getattr(editor.window(), '_capslock_on', None)
    if not (caps and caps()):
        return False
    t = event.text()
    if t and t.isalpha():
        editor.insert(t.swapcase())
        event.accept()
        return True
    return False


def surface_alphas(widget):
    """Los dos ejes de transparencia, leidos de la ventana: (fondo, tinta).

    Viven en la ventana y no en cada vista porque son una sola decision del
    usuario (Ctrl+± y Ctrl+Shift+±). Con getattr y default 1.0 para que un
    widget suelto —un test, una vista huerfana— siga pintando opaco.
    """
    win = widget.window()
    return (getattr(win, 'opacity', 1.0), getattr(win, 'ink_opacity', 1.0))


def ink_color(widget):
    """El blanco del circulo y las letras, con el alpha del eje TINTA."""
    from PyQt6.QtGui import QColor
    _, ink = surface_alphas(widget)
    return QColor(255, 255, 255, int(round(max(0.0, min(1.0, ink)) * 255)))


def bg_color(widget):
    """El negro del fondo, con el alpha del eje FONDO."""
    from PyQt6.QtGui import QColor
    bg, _ = surface_alphas(widget)
    return QColor(0, 0, 0, int(round(max(0.0, min(1.0, bg)) * 255)))


def caps_blocks_backspace(editor, event):
    """Scriptio continua is writing without going back. While Caps is on, the F1
    line can only be typed forward or released to the void — Backspace erases
    nothing. Returns True if it swallowed the key.

    Sólo el input de F1: F2/F3 es donde se edita, y ahí se borra siempre."""
    if event.key() != Qt.Key.Key_Backspace:
        return False
    caps = getattr(editor.window(), '_capslock_on', None)
    if not (caps and caps()):
        return False
    event.accept()
    return True


def hide_scrollbars(widget):
    """Hide both scrollbars on a scroll-area widget. Content still scrolls via
    the wheel and keys — only the bars go invisible."""
    widget.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)


def draw_pinned_title(painter, base_font, width, title):
    """A pinned, centred, ALL-CAPS title at the top of a view (F5/F2). Nothing if
    empty. No background band — it draws straight over the (black) view."""
    from PyQt6.QtGui import QFont, QFontMetrics, QColor
    from PyQt6.QtCore import QRect
    text = (title or '').upper()
    if not text:
        return
    painter.setOpacity(1.0)          # the caller may have left it dimmed
    hf = QFont(base_font.family(), base_font.pointSize() + 3)
    fm = QFontMetrics(hf)
    top, th = 22, fm.height()
    painter.setFont(hf)
    painter.setPen(QColor(255, 255, 255))
    painter.drawText(QRect(0, top, width, th),
                     Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, text)

class CustomLineEdit(QLineEdit):
    """QLineEdit personalizado con soporte para spacebar como tecla de void"""
    spacePressed = pyqtSignal()
    tabPressed = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent

    def changeEvent(self, e):
        # Grow the line's height to fit the font so large sizes aren't clipped.
        if e.type() == QEvent.Type.FontChange:
            self.setFixedHeight(self.sizeHint().height())
        super().changeEvent(e)

    def keyPressEvent(self, event):
        key = event.key()
        modifiers = event.modifiers()
        
        # Tab and * both recycle a random line into the entry (cut-up). Tab is the
        # primary key now (closer, loop-like glyph); * still works. Intercept
        # BEFORE the char is typed.
        if (key == Qt.Key.Key_Tab or key == Qt.Key.Key_Asterisk
                or (key == Qt.Key.Key_8 and (modifiers & Qt.KeyboardModifier.ShiftModifier))):
            from controls import recycle_line_to_zero_txt
            recycle_line_to_zero_txt(self.parent, event)
            event.accept()
            return  # IMPORTANTE: return para no seguir procesando

        # Manejo de spacebar para void. Suelta la línea al void en modo spacebar
        # global, o (scriptio continua) cuando Caps Lock está prendido — ahí la
        # barra no tipea espacio, sino que manda la línea.
        if key == Qt.Key.Key_Space:
            caps = getattr(self.parent, '_capslock_on', None)
            if self.parent.use_spacebar_for_void or (caps and caps()):
                self.spacePressed.emit()
                event.accept()
                return
            super().keyPressEvent(event)
            return

        # Caps Lock only toggles scriptio-continua (spacebar voids) — never
        # uppercase. While it's on, letters type in their normal case.
        if neutralize_caps(self, event):
            return

        # …y no se borra: la línea se escribe hacia adelante o se suelta.
        if caps_blocks_backspace(self, event):
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
            Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_F12, Qt.Key.Key_P,
            Qt.Key.Key_Return, Qt.Key.Key_Enter,
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
        noise_bytes = bytes(random.getrandbits(8) for _ in range(h_blocks * w_blocks))
        image = QImage(noise_bytes, w_blocks, h_blocks, w_blocks,
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
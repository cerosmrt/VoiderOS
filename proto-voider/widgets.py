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


def draw_chapter_picker(painter, font, x, w, h, filter_str, matches, match_idx,
                        is_new, target):
    """El catalogo de capitulos: escribis para filtrar, flechas para elegir.

    Nacio en F5 y ahora lo usa tambien F2, asi que vive aca en vez de estar dos
    veces. Es pintura pura — recibe el estado y no sabe de que vista viene.
    """
    from PyQt6.QtGui import QFont, QFontMetrics, QColor
    from PyQt6.QtCore import QRect
    small = QFont(font.family(), max(font.pointSize() - 2, 9))
    fm, sfm = QFontMetrics(font), QFontMetrics(small)
    pad = 16
    text_w = w - 2 * pad
    lh = int(sfm.height() * 1.9)
    cy = h // 2

    def elide(t, mw, m):
        return m.elidedText(t, Qt.TextElideMode.ElideRight, mw)

    painter.setFont(small)
    painter.setPen(QColor(150, 150, 150))
    prompt = (filter_str + '▏') if filter_str else 'escribí para filtrar…'
    painter.drawText(QRect(x + pad, pad, text_w, sfm.height() + 4),
                     Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                     elide(prompt, text_w, sfm))

    if is_new and filter_str.strip():
        painter.setFont(font)
        painter.setPen(QColor(235, 235, 235))
        painter.drawText(QRect(x + pad, cy - fm.height() // 2, text_w, fm.height() + 4),
                         Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                         elide('⏎ crear  ' + target, text_w, fm))
    elif matches:
        cur = match_idx % len(matches)
        visible = max(1, h // lh)
        first = max(0, cur - visible // 2)
        for j in range(first, min(len(matches), first + visible)):
            dist = j - cur
            if dist == 0:
                painter.setPen(QColor(235, 235, 235))
            else:
                a = max(45, 110 - abs(dist) * 22)
                painter.setPen(QColor(a, a, a))
            painter.setFont(small)
            painter.drawText(QRect(x + pad, cy + dist * lh - sfm.ascent(), text_w, lh),
                             Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                             elide(matches[j], text_w, sfm))
    else:
        painter.setFont(small)
        painter.setPen(QColor(70, 70, 70))
        painter.drawText(QRect(x, 0, w, h), Qt.AlignmentFlag.AlignCenter, 'ø')

    painter.setFont(small)
    painter.setPen(QColor(70, 70, 70))
    painter.drawText(QRect(x + pad, h - 34, text_w, 22),
                     Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                     '→ enviar   ⏎ nuevo   ⇥ ciclar')


def tab_intent(e):
    """Que significa este evento de teclado: 'tab', 'shift-tab', o None.

    Una sola fuente de verdad, compartida por el entry de F1 y el editor de
    F2/F3. Existe porque Shift+Tab llega de DOS formas segun el layout y el
    compositor: como Key_Backtab, o como Key_Tab con el Shift todavia puesto.
    Mirar solo una de las dos fue el bug original — en un caso caia en la rama
    del Tab normal y traia un fragmento de I/ en vez de uno del working set.
    """
    if e.type() != QEvent.Type.KeyPress:
        return None
    k = e.key()
    if k not in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
        return None
    shifted = (k == Qt.Key.Key_Backtab
               or bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier))
    return 'shift-tab' if shifted else 'tab'


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
    shiftTabPressed = pyqtSignal()   # Shift+Tab: reciclar del working set (F7)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent

    def event(self, e):
        """Agarrar Shift+Tab antes que Qt.

        Qt resuelve Tab y Backtab ACA, en QWidget.event(), antes de llamar a
        keyPressEvent: si hay otro widget al que pasarle el foco, se lo pasa y
        el keyPressEvent nunca corre. Por eso Shift+Tab en F1 no hacia nada —
        no era que estuviera roto, es que nunca llego a implementarse, y encima
        keyPressEvent solo miraba Key_Tab.

        Solo se intercepta el shift-tab: el Tab pelado se sigue manejando en
        keyPressEvent, junto al '*', que es donde ya funcionaba.
        """
        if tab_intent(e) == 'shift-tab':
            self.shiftTabPressed.emit()
            e.accept()
            return True
        return super().event(e)

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
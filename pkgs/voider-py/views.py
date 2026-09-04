# views.py
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtCore import Qt


class NormalView(QWidget):
    """F1 view: minimal white circle with centered text entry"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_app = parent
        self.setStyleSheet("background: black;")

    def paintEvent(self, event):
        if not self.parent_app:
            return
        if self.width() == 0 or self.height() == 0:
            return
        painter = QPainter(self)
        if not painter.isActive():
            return

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor("white"), 10)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        w = self.width()
        h = self.height()
        center_x = w // 2
        center_y = h // 2
        radius = min(w, h) // 2 - 35


class EdgeFade(QWidget):
    """La capa que apaga el texto hacia el borde del círculo (F1, typewriter).

    En modo typewriter el caret queda fijo en el centro y la línea corre hacia la
    izquierda, hasta el borde del círculo. Esto pinta un degradado a negro sobre
    ese recorrido: transparente en el centro, negro contra el borde. Así lo único
    que se lee nítido es lo que estás escribiendo, y lo de atrás se apaga.

    Va POR ENCIMA del texto y no debajo: el entry es un QLineEdit hijo, y los
    hijos se pintan después del paintEvent del padre, así que un degradado
    pintado en NormalView quedaría abajo y no taparía nada.

    Y vuelve a dibujar el círculo ENCIMA del degradado. Sin eso, el rectángulo
    negro tapaba el trazo del círculo por la izquierda y se veía cortado — el
    degradado tiene que apagar el texto, no el borde que lo contiene. Por eso la
    capa ocupa toda la vista y no sólo el renglón: necesita el círculo entero
    para redibujarlo.

    Resuelve de paso el desborde: con la letra grande, los extremos del renglón
    se salían del círculo. Al llegar a negro justo ahí, lo que sobresale deja de
    verse. El degradado ES el recorte.
    """

    # Dónde empieza a apagarse, como fracción del ancho del renglón: 0 = el borde
    # del círculo, 1 = el centro. Con 0.55 la mitad de adentro se lee limpia.
    FADE_START = 0.55
    # El mismo círculo que dibuja NormalView.
    CIRCLE_INSET = 35
    CIRCLE_PEN = 10

    def __init__(self, parent=None):
        super().__init__(parent)
        # Que no se coma los clicks ni el foco: es una capa de pintura, nada más.
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._entry_rect = None      # el renglón a apagar, en coordenadas de la capa
        self.hide()

    def set_entry_rect(self, x, y, w, h):
        """Dónde está el renglón que hay que apagar."""
        self._entry_rect = (x, y, w, h)
        self.update()

    def paintEvent(self, event):
        from PyQt6.QtGui import QLinearGradient, QPainterPath
        from PyQt6.QtCore import QRect, QRectF
        if self.width() == 0 or self.height() == 0:
            return
        painter = QPainter(self)
        if not painter.isActive():
            return

        # 1. El degradado, sólo sobre el renglón.
        if self._entry_rect:
            x, y, w, h = self._entry_rect
            if w > 0 and h > 0:
                grad = QLinearGradient(float(x), 0.0, float(x + w), 0.0)
                grad.setColorAt(0.0, QColor(0, 0, 0, 255))
                grad.setColorAt(self.FADE_START, QColor(0, 0, 0, 0))
                grad.setColorAt(1.0, QColor(0, 0, 0, 0))
                painter.fillRect(QRect(x, y, w, h), grad)

        # 2. Todo lo que queda AFUERA del círculo, en negro. El renglón es un
        # rectángulo y el círculo es redondo: arriba y abajo del centro el
        # círculo se angosta, así que las puntas del renglón caen afuera. Con la
        # letra grande eso se ve como letras desbordando el círculo. Tapar el
        # exterior lo recorta de verdad, a cualquier tamaño de fuente, en vez de
        # confiar en que el degradado llegue a tiempo.
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx0, cy0 = self.width() / 2.0, self.height() / 2.0
        r0 = min(self.width(), self.height()) / 2.0 - self.CIRCLE_INSET
        if r0 > 0:
            afuera = QPainterPath()
            afuera.addRect(QRectF(self.rect()))
            adentro = QPainterPath()
            adentro.addEllipse(cx0 - r0, cy0 - r0, r0 * 2, r0 * 2)
            painter.fillPath(afuera.subtracted(adentro), QColor(0, 0, 0, 255))

        # 3. El círculo ENCIMA, para que el degradado no le coma el trazo.
        painter.setPen(QPen(QColor("white"), self.CIRCLE_PEN))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        cx, cy = self.width() // 2, self.height() // 2
        r = min(self.width(), self.height()) // 2 - self.CIRCLE_INSET
        if r > 0:
            painter.drawEllipse(cx - r, cy - r, r * 2, r * 2)

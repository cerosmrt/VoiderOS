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

        painter.drawEllipse(center_x - radius, center_y - radius, radius * 2, radius * 2)

class EdgeFade(QWidget):
    """La capa que apaga el texto hacia el borde del círculo (F1, typewriter).

    En modo typewriter el caret queda fijo en el centro y la línea corre hacia la
    izquierda, hasta el borde del círculo. Esto pinta un degradado a negro sobre
    ese recorrido: transparente en el centro, negro contra el borde. Así lo único
    que se lee nítido es lo que estás escribiendo ahora, y lo de atrás se apaga.

    Va por encima del texto y no debajo, porque el QLineEdit es un widget hijo y
    los hijos se pintan después del paintEvent del padre. Un degradado pintado
    abajo no taparía nada.

    Resuelve de paso el desborde: con la letra grande, los extremos del renglón
    se salían del círculo. Al llegar a negro justo en el borde, lo que sobresale
    deja de verse. El degradado ES el recorte.
    """

    # Dónde empieza a apagarse, como fracción del ancho: 0 = el borde del
    # círculo, 1 = el centro. Con 0.55 la mitad de adentro se lee limpia y la
    # otra mitad se va apagando.
    FADE_START = 0.55

    def __init__(self, parent=None):
        super().__init__(parent)
        # Que no se coma los clicks ni el foco: es una capa de pintura, nada más.
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.hide()

    def paintEvent(self, event):
        from PyQt6.QtGui import QLinearGradient
        if self.width() == 0 or self.height() == 0:
            return
        painter = QPainter(self)
        if not painter.isActive():
            return
        # De izquierda (borde del círculo, negro) a derecha (centro, limpio).
        grad = QLinearGradient(0, 0, self.width(), 0)
        grad.setColorAt(0.0, QColor(0, 0, 0, 255))
        grad.setColorAt(self.FADE_START, QColor(0, 0, 0, 0))
        grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(self.rect(), grad)

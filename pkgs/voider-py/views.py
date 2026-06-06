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
# views.py
import os
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QColor, QPainter, QPen, QFont
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

        # "PROTO" banner only on the dev sandbox. The Nix wrapper for the system
        # voider-py sets VOIDER_VOID_DIR; proto never does. This keeps the file
        # byte-identical across both copies while diverging by environment, so a
        # proto→voider-py re-sync can't accidentally reintroduce the banner.
        if not os.environ.get("VOIDER_VOID_DIR"):
            font = QFont("Consolas", 72, QFont.Weight.Bold)
            painter.setFont(font)
            painter.setPen(QColor(255, 255, 255, 40))
            painter.drawText(0, 0, w, h // 4, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, "PROTO")
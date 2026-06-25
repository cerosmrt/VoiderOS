import getpass
import os

try:
    import pam
except ImportError:
    pam = None  # real env has python-pam; test env mocks it

from PyQt6.QtWidgets import QWidget, QLabel, QLineEdit, QVBoxLayout
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter, QColor, QFont


class LockScreen(QWidget):
    """Full-screen overlay that locks Voider until the Linux password is entered."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.hide()

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(20)

        name_label = QLabel(f"  {getpass.getuser()}  ")
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_label.setStyleSheet(
            "color: #888888; background: transparent; font: 14pt Consolas;"
        )

        self._password_input = QLineEdit()
        self._password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._password_input.setFixedWidth(300)
        self._password_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._password_input.setStyleSheet(
            "QLineEdit {"
            "  color: white; background: #1a1a1a; border: 1px solid #333;"
            "  font: 13pt Consolas; padding: 6px 10px;"
            "}"
        )
        self._password_input.returnPressed.connect(self._try_unlock)

        self._error_label = QLabel("")
        self._error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._error_label.setStyleSheet(
            "color: #884444; background: transparent; font: 10pt Consolas;"
        )
        self._error_label.hide()

        layout.addWidget(name_label)
        layout.addWidget(self._password_input, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._error_label)

    def show_lock(self):
        self._password_input.clear()
        self._error_label.hide()
        self.show()
        self.raise_()
        self._password_input.setFocus()

    def _try_unlock(self):
        password = self._password_input.text()
        user = getpass.getuser()
        p = pam.pam()
        if p.authenticate(user, password):
            self.hide()
            parent = self.parentWidget()
            if parent and hasattr(parent, '_refocus_active_editor'):
                parent._refocus_active_editor()
        else:
            self._password_input.clear()
            self._error_label.setText("incorrect password")
            self._error_label.show()
            self._password_input.setFocus()

    def paintEvent(self, event):
        painter = QPainter(self)
        if not painter.isActive():
            return
        painter.fillRect(self.rect(), QColor(0, 0, 0, 240))
        painter.end()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            event.accept()
            return
        super().keyPressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        p = self.parentWidget()
        if p:
            self.resize(p.size())

# login_screen.py
from PyQt6.QtWidgets import QMainWindow, QLineEdit
from PyQt6.QtGui import QPainter, QFont, QColor, QCursor, QPalette
from PyQt6.QtCore import Qt, pyqtSignal, QPropertyAnimation, QPoint, QEasingCurve


class VoiderLoginScreen(QMainWindow):
    """
    Fullscreen login shown on boot and when locked.
    Step 1: blinking 'user' caret  — type username, Enter.
    Step 2: blinking 'password' caret — type password, Enter.
    PAM authenticates. On success emits auth_success.
    On failure: shakes and resets to step 1.
    Escape is consumed — no exit without valid credentials.
    """
    auth_success = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setWindowTitle("voider-lock")
        self.setStyleSheet("background-color: black;")
        self.setCursor(QCursor(Qt.CursorShape.BlankCursor))

        self._step = "user"
        self._username = ""

        self.entry = QLineEdit(self)
        self.entry.setFont(QFont("JetBrains Mono", 11))
        self.entry.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.entry.setStyleSheet("""
            QLineEdit {
                background: transparent;
                color: white;
                border: none;
                selection-background-color: white;
                selection-color: black;
            }
        """)
        palette = self.entry.palette()
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(255, 255, 255, 70))
        self.entry.setPalette(palette)
        self.entry.setPlaceholderText("user")
        self.entry.returnPressed.connect(self._handle_submit)

    def reset(self):
        self._step = "user"
        self._username = ""
        self.entry.clear()
        self.entry.setEchoMode(QLineEdit.EchoMode.Normal)
        self.entry.setPlaceholderText("user")
        self.entry.setFocus()

    def _reposition(self):
        w, h = self.width(), self.height()
        if w == 0 or h == 0:
            return
        entry_width = min(w, h) - 90
        self.entry.setFixedWidth(entry_width)
        self.entry.move(
            w // 2 - entry_width // 2,
            h // 2 - self.entry.sizeHint().height() // 2,
        )

    def _handle_submit(self):
        text = self.entry.text()
        self.entry.clear()

        if self._step == "user":
            if not text.strip():
                return
            self._username = text.strip()
            self._step = "password"
            self.entry.setEchoMode(QLineEdit.EchoMode.Password)
            self.entry.setPlaceholderText("password")

        elif self._step == "password":
            self._authenticate(self._username, text)

    def _authenticate(self, username, password):
        try:
            import pam
            p = pam.pam()
            if p.authenticate(username, password):
                self.auth_success.emit()
                return
        except ImportError:
            # Dev mode without python-pam: accept any non-empty password
            if password:
                self.auth_success.emit()
                return
        except Exception as e:
            print(f"Auth error: {e}")
        self._fail()

    def _fail(self):
        self._shake()
        self._step = "user"
        self._username = ""
        self.entry.setEchoMode(QLineEdit.EchoMode.Normal)
        self.entry.setPlaceholderText("user")
        self.entry.clear()

    def _shake(self):
        orig = self.entry.pos()
        anim = QPropertyAnimation(self.entry, b"pos")
        anim.setDuration(300)
        anim.setEasingCurve(QEasingCurve.Type.Linear)
        anim.setKeyValueAt(0.00, orig)
        anim.setKeyValueAt(0.15, QPoint(orig.x() - 14, orig.y()))
        anim.setKeyValueAt(0.35, QPoint(orig.x() + 14, orig.y()))
        anim.setKeyValueAt(0.55, QPoint(orig.x() -  9, orig.y()))
        anim.setKeyValueAt(0.75, QPoint(orig.x() +  9, orig.y()))
        anim.setKeyValueAt(0.90, QPoint(orig.x() -  4, orig.y()))
        anim.setKeyValueAt(1.00, orig)
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            event.accept()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event):
        QPainter(self).fillRect(self.rect(), Qt.GlobalColor.black)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition()

    def showEvent(self, event):
        super().showEvent(event)
        self._reposition()
        self.entry.setFocus()

from PyQt6.QtWidgets import QWidget, QLabel
from PyQt6.QtGui import QPainter, QColor, QFont
from PyQt6.QtCore import Qt, QRect


# (key_label, description)  — None description = section header
HELP = [
    ("I VIEWS  (write)",  None),
    ("F1",                "Write — center entry, active file (0.txt)"),
    ("F2",                "Circular doc — edit / reorder lines"),
    ("F3",                "Book browser — manage chapters"),
    ("F4",                "Reading render — current doc as prose"),
    ("",                  ""),
    ("O VIEWS  (read)",   None),
    ("F5",                "Fork — edit O/ line into I/"),
    ("F6",                "Circular reader — read O/ book"),
    ("F7",                "Working set — up to 8 O/ books"),
    ("F8",                "Oracle O/ — random line from O/"),
    ("",                  ""),
    ("OTHER",             None),
    ("F9",                "Metronome — type BPM, circle pulses"),
    ("F10",               "Settings — font, size, colors"),
    ("F11",               "This help screen"),
    ("Esc",               "Lock screen — PAM password to unlock"),
    ("Ctrl+T",            "TTS — toggle text-to-speech"),
    ("F12",               "Screenshot"),
    ("Ctrl+F12",          "Open screenshots folder"),
    ("",                  ""),
    ("TAB  (contextual)", None),
    ("Tab  (F1)",         "Recycle random line from I/"),
    ("Tab  (F2 content)", "Insert random I/ text at cursor"),
    ("Tab  (F2 dot)",     "Shuffle lines within paragraph"),
    ("Tab  (F2 ø)",       "Shuffle paragraph order"),
    ("Tab  (F5)",         "Random line from O/"),
    ("Tab  (F7)",         "Fill empty working-set slot"),
    ("",                  ""),
    ("FILES",             None),
    ("Ctrl+F2",           "Pick active file"),
    ("Ctrl+F3",           "Pick book folder"),
    ("Ctrl+F4",           "Change void directory"),
    ("Alt+↑/↓",          "Previous / next file (F1)"),
    ("Ctrl+B",            "Backup vault to folder"),
    ("Ctrl+S",            "Export / save as PDF"),
    ("Ctrl+P",            "Print"),
    ("",                  ""),
    ("EDITING  (F2)",     None),
    ("Enter",             "Void line → active file (F1)"),
    ("↑ / ↓",            "Navigate lines"),
    ("Home / End",        "Jump to first / last line"),
    ("PageUp/Down",       "Jump to prev/next paragraph"),
    ("Ctrl+0",            "Rebase: make current line first"),
    ("Ctrl+Shift+R",      "Randomise all lines in 0.txt"),
    ("Ctrl+Shift+D",      "Dispatch: route /name paragraphs to files"),
    ("",                  ""),
    ("HYPRLAND",          None),
    ("Super+J",           "CRT scanlines panel"),
    ("Super+K",           "Film grain panel"),
    ("Super+L",           "Black & white panel"),
    ("Super+P",           "Launch proto-voider (dev sandbox)"),
    ("Super+R",           "Radio — toggle background music"),
    ("Super+T",           "Terminal (kitty)"),
    ("Super+C",           "Claude Code"),
]


class HelpOverlay(QWidget):
    """F11 — full-screen shortcut reference. Any key closes."""

    _BG_ALPHA = 228
    _ROW_H    = 22
    _KEY_W    = 200

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.hide()

    def toggle(self) -> None:
        if self.isVisible():
            self._close()
        else:
            self.show()
            self.raise_()
            self.setFocus()
            self.update()

    def _close(self) -> None:
        self.hide()
        app = self.parentWidget()
        if app and hasattr(app, '_refocus_active_editor'):
            app._refocus_active_editor()

    def keyPressEvent(self, event):
        self._close()
        event.accept()

    def paintEvent(self, event):
        painter = QPainter(self)
        if not painter.isActive():
            return
        W, H = self.width(), self.height()
        painter.fillRect(0, 0, W, H, QColor(0, 0, 0, self._BG_ALPHA))

        app = self.parentWidget()
        base_font = app._app_font if hasattr(app, '_app_font') else QFont('Consolas', 11)
        section_font = QFont(base_font.family(), base_font.pointSize() - 2)
        hint_font    = QFont(base_font.family(), base_font.pointSize() - 3)

        total_rows = len(HELP)
        total_h = total_rows * self._ROW_H
        y0 = max(16, (H - total_h) // 2)

        desc_x = (W - self._KEY_W - 24 - 340) // 2
        key_x  = desc_x
        val_x  = key_x + self._KEY_W + 24

        for i, (key, desc) in enumerate(HELP):
            y = y0 + i * self._ROW_H + self._ROW_H - 5
            if desc is None:
                painter.setFont(section_font)
                painter.setPen(QColor(70, 70, 70))
                painter.drawText(key_x, y, key)
            elif key == "":
                pass  # spacer row
            else:
                painter.setFont(base_font)
                painter.setPen(QColor(185, 185, 185))
                painter.drawText(key_x, y, key)
                painter.setPen(QColor(95, 95, 95))
                painter.drawText(val_x, y, desc)

        painter.setFont(hint_font)
        painter.setPen(QColor(40, 40, 40))
        painter.drawText(
            QRect(0, H - 28, W, 20),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
            'any key  close',
        )
        painter.end()


class RecBadge(QLabel):
    """Small ● REC indicator shown in top-right corner while recording."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            "color: #ff3333;"
            "background: transparent;"
            "font: bold 11pt Consolas;"
            "padding: 4px 8px;"
        )
        self.hide()

    def set_state(self, mic: bool, cam: bool) -> None:
        parts = []
        if mic:
            parts.append("● MIC")
        if cam:
            parts.append("● CAM")
        if parts:
            self.setText("  ".join(parts))
            self.adjustSize()
            self._reposition()
            self.show()
            self.raise_()
        else:
            self.hide()

    def _reposition(self) -> None:
        p = self.parentWidget()
        if p:
            self.move(p.width() - self.width() - 16, 16)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition()

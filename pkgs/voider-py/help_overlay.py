from PyQt6.QtWidgets import QWidget, QLabel
from PyQt6.QtGui import QPainter, QColor, QFont
from PyQt6.QtCore import Qt, QRect


# (key_label, description)  — None description = section header
HELP = [
    ("VIEWS",             None),
    ("F1",                "Write — center entry, active file"),
    ("F2",                "Circular doc — edit / reorder lines"),
    ("F3",                "Book browser — manage chapters"),
    ("F4",                "Vault browser — shuffled vault lines"),
    ("F5",                "Oracle — one random vault line"),
    ("F6",                "Metronome — type BPM, circle pulses"),
    ("",                  ""),
    ("FILES",             None),
    ("Ctrl+F2",           "Pick active file"),
    ("Ctrl+F3",           "Pick book folder"),
    ("Ctrl+F4",           "Change void directory"),
    ("Alt+↑/↓",          "Previous / next file (F1)"),
    ("Ctrl+B",            "Backup vault to folder"),
    ("Ctrl+S",            "Export / save as"),
    ("Ctrl+P",            "Print"),
    ("",                  ""),
    ("EDITING",           None),
    ("Enter / Space",     "Void line → active file (F1)"),
    ("↑ / ↓",            "Navigate lines"),
    ("PageUp/Down",       "Jump to prev/next paragraph"),
    ("Ctrl+0",            "Rebase: make current line first (F2)"),
    ("Ctrl+R",            "Reshuffle vault"),
    ("Ctrl+Shift+F",      "Reformat active file"),
    ("",                  ""),
    ("TOOLS",             None),
    ("Ctrl+M",            "Mic — toggle audio recording"),
    ("Ctrl+K",            "Camera — toggle video recording"),
    ("F12",               "Screenshot"),
    ("F8",                "This help screen"),
    ("",                  ""),
    ("VISUAL EFFECTS  (Hyprland keybinds)", None),
    ("Super+F5",          "CRT scanlines panel"),
    ("Super+F6",          "Film grain panel"),
    ("Super+F7",          "Black & white panel"),
    ("Super+R",           "Radio — toggle background music"),
    ("Super+T",           "Open terminal (kitty)"),
    ("Super+I",           "Open ~/incoming in terminal"),
    ("Super+C",           "Open Claude Code"),
]


class HelpOverlay(QWidget):
    """F8 — full-screen shortcut reference. Any key closes."""

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

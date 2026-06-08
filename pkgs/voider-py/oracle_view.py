import random
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QColor, QFont
from PyQt6.QtCore import Qt, QRect


class OracleView(QWidget):
    """F5 — one random vault line, full-screen. Pull it or skip to the next."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self._pool: list[str] = []
        self._line = ""
        self._flash = False  # brief dim after pulling

    def load(self, vault_lines: list[str]) -> None:
        self._pool = [l for l in vault_lines if l and l != '.']
        self._flash = False
        self._draw_next()

    def _draw_next(self) -> None:
        self._line = random.choice(self._pool) if self._pool else "vault is empty"
        self._flash = False
        self.update()

    def current_line(self) -> str:
        return self._line

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        if not painter.isActive():
            return
        painter.fillRect(self.rect(), Qt.GlobalColor.black)
        W, H = self.width(), self.height()

        app = self.parentWidget()
        base_font = app._app_font if hasattr(app, '_app_font') else QFont('Consolas', 11)
        body_font = QFont(base_font.family(), base_font.pointSize() + 6)
        painter.setFont(body_font)
        fm = painter.fontMetrics()

        text_area_w = min(W - 160, 860)
        alpha = 120 if self._flash else 220
        painter.setPen(QColor(255, 255, 255, alpha))

        # Word-wrap
        words = self._line.split()
        rows: list[str] = []
        current = ""
        for word in words:
            trial = (current + " " + word).strip()
            if fm.horizontalAdvance(trial) <= text_area_w:
                current = trial
            else:
                if current:
                    rows.append(current)
                current = word
        if current:
            rows.append(current)

        row_h = fm.height() + 10
        total_h = len(rows) * row_h
        y = (H - total_h) // 2

        for row in rows:
            rw = fm.horizontalAdvance(row)
            painter.drawText((W - rw) // 2, y + fm.ascent(), row)
            y += row_h

        # Footer hint
        hint_font = QFont(base_font.family(), base_font.pointSize() - 1)
        painter.setFont(hint_font)
        painter.setPen(QColor(55, 55, 55))
        painter.drawText(
            QRect(0, H - 44, W, 28),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
            'SPACE / ENTER  pull into file   ↓  skip   ESC  back',
        )
        painter.end()

    # ── Keys ──────────────────────────────────────────────────────────────────

    def keyPressEvent(self, event):
        k = event.key()
        app = self.parentWidget()

        if k in (Qt.Key.Key_Space, Qt.Key.Key_Return):
            if app and self._line and self._line != "vault is empty":
                app._oracle_pull(self._line)
            self._flash = True
            self.update()
            self._draw_next()
            event.accept()

        elif k in (Qt.Key.Key_Down, Qt.Key.Key_Up,
                   Qt.Key.Key_Right, Qt.Key.Key_N):
            self._draw_next()
            event.accept()

        elif k == Qt.Key.Key_Escape:
            if app:
                app.switch_to_view(0)
            event.accept()

        else:
            # Propagate unhandled keys (F1-F4 etc.) to parent
            super().keyPressEvent(event)

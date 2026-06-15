from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QColor, QFont, QPen
from PyQt6.QtCore import Qt, QTimer, QRect


class MetronomeView(QWidget):
    """F6 — type a BPM and watch the circle pulse to the beat."""

    _MAX_BPM = 300
    _MIN_BPM = 1

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)

        self._bpm    = 0
        self._input  = ""   # digits being typed before start
        self._running = False
        self._pulse   = 0.0  # 0.0 = resting, 1.0 = just beat

        # Single-shot: fires the next beat
        self._beat_timer = QTimer(self)
        self._beat_timer.setSingleShot(True)
        self._beat_timer.timeout.connect(self._on_beat)

        # Smooth decay (~60 fps)
        self._decay_timer = QTimer(self)
        self._decay_timer.setInterval(14)
        self._decay_timer.timeout.connect(self._decay)

    # ── Public API ─────────────────────────────────────────────────────────────

    def activate(self) -> None:
        """Call when switching into this view."""
        self._input = ""
        self._running = False
        self._pulse = 0.0
        self._beat_timer.stop()
        self._decay_timer.stop()
        self.setFocus()
        self.update()

    def deactivate(self) -> None:
        self._stop()

    # ── Beat engine ────────────────────────────────────────────────────────────

    def _beat_ms(self) -> int:
        return int(60_000 / max(self._MIN_BPM, self._bpm))

    def _start(self) -> None:
        if self._bpm <= 0:
            return
        self._running = True
        self._decay_timer.start()
        self._on_beat()   # immediate first beat

    def _stop(self) -> None:
        self._running = False
        self._beat_timer.stop()
        self._decay_timer.stop()
        self._pulse = 0.0
        self.update()

    def _on_beat(self) -> None:
        if not self._running:
            return
        self._pulse = 1.0
        self.update()
        self._beat_timer.start(self._beat_ms())

    def _decay(self) -> None:
        if self._pulse > 0.0:
            self._pulse = max(0.0, self._pulse - 0.055)
            self.update()

    # ── Paint ──────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        if not painter.isActive():
            return
        painter.fillRect(self.rect(), Qt.GlobalColor.black)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        cx, cy = W // 2, H // 2

        app = self.parentWidget()
        base_font = app._app_font if hasattr(app, '_app_font') else QFont('Consolas', 11)

        if self._running:
            self._paint_pulse(painter, cx, cy, W, H, base_font)
        else:
            self._paint_input(painter, cx, cy, W, H, base_font)

        painter.end()

    def _paint_pulse(self, painter, cx, cy, W, H, base_font):
        p = self._pulse
        base_r = min(W, H) // 5
        ring_r  = int(base_r + base_r * 0.4 * p)
        alpha   = int(40 + 200 * p)

        # Outer ring
        pen = QPen(QColor(255, 255, 255, alpha), 1 + int(2 * p))
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(cx - ring_r, cy - ring_r, ring_r * 2, ring_r * 2)

        # Small static centre circle
        static_r = max(4, base_r // 8)
        dot_r = int(static_r + static_r * 1.2 * p)
        painter.setBrush(QColor(255, 255, 255, alpha))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(cx - dot_r, cy - dot_r, dot_r * 2, dot_r * 2)

        # BPM + hint
        hint_font = QFont(base_font.family(), base_font.pointSize() - 1)
        painter.setFont(hint_font)
        painter.setPen(QColor(55, 55, 55))
        painter.drawText(
            QRect(0, H - 44, W, 28),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
            f'{self._bpm} BPM   ↑↓ adjust   ESC stop',
        )

    def _paint_input(self, painter, cx, cy, W, H, base_font):
        display = f"BPM: {self._input}_" if self._input else "BPM: _"
        painter.setFont(base_font)
        fm = painter.fontMetrics()
        painter.setPen(QColor(255, 255, 255, 200))
        tw = fm.horizontalAdvance(display)
        painter.drawText((W - tw) // 2, cy - fm.height() // 2 + fm.ascent(), display)

        hint_font = QFont(base_font.family(), base_font.pointSize() - 1)
        painter.setFont(hint_font)
        painter.setPen(QColor(55, 55, 55))
        hint = f'{self._bpm} BPM   ENTER restart   ESC back' if self._bpm else 'type BPM   ENTER start   ESC back'
        painter.drawText(
            QRect(0, H - 44, W, 28),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
            hint,
        )

    # ── Keys ───────────────────────────────────────────────────────────────────

    def keyPressEvent(self, event):
        k = event.key()
        app = self.parentWidget()

        if self._running:
            if k == Qt.Key.Key_Escape:
                self._stop()
                if app:
                    app.switch_to_view(0)
                event.accept()
            elif k == Qt.Key.Key_Up:
                self._bpm = min(self._MAX_BPM, self._bpm + 1)
                event.accept()
            elif k == Qt.Key.Key_Down:
                self._bpm = max(self._MIN_BPM, self._bpm - 1)
                event.accept()
            else:
                super().keyPressEvent(event)
            return

        # Input mode
        if Qt.Key.Key_0 <= k <= Qt.Key.Key_9:
            self._input = (self._input + str(k - Qt.Key.Key_0))[-3:]
            self.update()
            event.accept()
        elif k == Qt.Key.Key_Backspace:
            self._input = self._input[:-1]
            self.update()
            event.accept()
        elif k == Qt.Key.Key_Return:
            if self._input:
                self._bpm = max(self._MIN_BPM, min(self._MAX_BPM, int(self._input)))
                self._input = ""
            if self._bpm > 0:
                self._start()
            event.accept()
        elif k == Qt.Key.Key_Escape:
            if app:
                app.switch_to_view(0)
            event.accept()
        else:
            super().keyPressEvent(event)

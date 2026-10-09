"""viz_overlay.py — audio visualizer drawn in the margin around the F1/F2 circle.

Three styles over the same smoothed frames:
  pulse — a thin ring that swells outward with the volume
  wave  — an oscilloscope bent around the circle: the edge ripples with the sound
  bars  — a spectrum analyzer: one radial bar per band, growing outward
Nothing is painted inside the circle (the text lives there), and nothing at all
in silence, so the plain circle stays untouched until there is sound."""
import math

from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QPen, QColor, QPolygonF
from PyQt6.QtCore import Qt, QPointF

from audio_analysis import Smoother

STYLES = ('pulse', 'wave', 'bars')
CIRCLE_INSET = 35                   # same circle as NormalView / EdgeFade
GAP = 4                             # air between the circle and the drawing
SILENCE = 0.01                      # below this, draw nothing


def circle_geometry(w, h):
    """(cx, cy, radius, margin) of the F1 circle inside a w×h view."""
    return w // 2, h // 2, min(w, h) // 2 - CIRCLE_INSET, CIRCLE_INSET


class VizOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.style = 'pulse'
        self._level = Smoother(attack=0.6, decay=0.04)
        self._wave = Smoother(attack=0.7, decay=0.2)
        self._bands = Smoother(attack=0.6, decay=0.06)
        self._lv, self._wv, self._bv = [0.0], [0.0] * 128, [0.0] * 32

    def set_style(self, style):
        self.style = style if style in STYLES else 'pulse'
        self.update()

    def feed(self, frame):
        """One analysed audio frame (see AudioMonitor.frame); repaints."""
        self._lv = self._level.update([frame['level']])
        self._wv = self._wave.update(frame['wave'])
        self._bv = self._bands.update(frame['bands'])
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        if not painter.isActive():
            return
        self.paint_on(painter, self.width(), self.height())
        painter.end()

    def paint_on(self, painter, w, h):
        """Draw into any painter (the widget's own, or an image in tests)."""
        if w == 0 or h == 0:
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy, r, margin = circle_geometry(w, h)
        if r <= 0:
            return
        reach = margin - GAP - 2                 # how far out we may draw
        {'pulse': self._pulse, 'wave': self._wavy, 'bars': self._bars}[self.style](
            painter, cx, cy, r, reach)

    def _pulse(self, p, cx, cy, r, reach):
        lv = self._lv[0]
        if lv < SILENCE:
            return
        rr = r + GAP + reach * lv
        p.setPen(QPen(QColor(255, 255, 255, int(40 + 180 * lv)), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), rr, rr)

    def _wavy(self, p, cx, cy, r, reach):
        if self._lv[0] < SILENCE and max(abs(v) for v in self._wv) < SILENCE:
            return
        n = len(self._wv)
        base = r + GAP + reach / 2.0
        pts = []
        for i in range(n + 1):
            a = 2 * math.pi * (i % n) / n - math.pi / 2
            rr = base + (reach / 2.0) * self._wv[i % n]
            pts.append(QPointF(cx + rr * math.cos(a), cy + rr * math.sin(a)))
        p.setPen(QPen(QColor(255, 255, 255, 200), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPolyline(QPolygonF(pts))

    def _bars(self, p, cx, cy, r, reach):
        n = len(self._bv)
        if max(self._bv) < SILENCE:
            return
        p.setPen(QPen(QColor(255, 255, 255, 210), 3, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap))
        for i, v in enumerate(self._bv):
            if v < SILENCE:
                continue
            a = 2 * math.pi * i / n - math.pi / 2
            r0, r1 = r + GAP, r + GAP + reach * v
            p.drawLine(QPointF(cx + r0 * math.cos(a), cy + r0 * math.sin(a)),
                       QPointF(cx + r1 * math.cos(a), cy + r1 * math.sin(a)))

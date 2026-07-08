from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QColor, QFont, QFontMetrics
from PyQt6.QtCore import Qt, QRect, QEvent


class ReorderView(QWidget):
    """F5 — linear, read-only paragraph view of the active file. The current
    paragraph is centred and highlighted; '/name' lines render as fixed chapter
    fences. Reordering is driven by the app (Alt+Up/Down); this widget only paints.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._units = []          # [{'kind':'para','ordinal':i,'text':..} | {'kind':'mark','name':..}]
        self._para_idx = 0
        self._app_font = QFont('Consolas', 13)

    def event(self, e):
        if e.type() == QEvent.Type.KeyPress and e.key() in (
                Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
            self.window().keyPressEvent(e)
            return True
        return super().event(e)

    def keyPressEvent(self, event):
        event.ignore()           # propagate to QMainWindow

    def set_state(self, units, para_idx):
        self._units = list(units)
        self._para_idx = para_idx
        self.update()

    # ── layout helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _wrap(text, max_w, fm):
        """Greedy word-wrap into a list of display lines."""
        if not text:
            return ['']
        out, cur = [], ''
        for word in text.split():
            trial = word if not cur else cur + ' ' + word
            if fm.horizontalAdvance(trial) <= max_w or not cur:
                cur = trial
            else:
                out.append(cur); cur = word
        if cur:
            out.append(cur)
        return out or ['']

    def _unit_lines(self, unit, max_w, fm):
        if unit['kind'] == 'mark':
            return [unit['name'] or '·']
        return self._wrap(unit['text'], max_w, fm)

    # ── paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        if not painter.isActive():
            return
        W, H = self.width(), self.height()
        painter.fillRect(0, 0, W, H, QColor(0, 0, 0))

        app = self.window()
        font = getattr(app, '_app_font', self._app_font)
        painter.setFont(font)
        fm = QFontMetrics(font)
        lh = int(fm.height() * 1.5)
        pad = max(48, int(W * 0.14))
        text_w = W - 2 * pad
        gap = lh                                  # blank line between units

        # Pre-wrap every unit and measure its block height.
        blocks = []
        for u in self._units:
            wl = self._unit_lines(u, text_w, fm)
            blocks.append((u, wl, len(wl) * lh))

        if not blocks:
            painter.setPen(QColor(45, 45, 45))
            painter.drawText(QRect(0, 0, W, H), Qt.AlignmentFlag.AlignCenter, 'ø')
            painter.end()
            return

        # Find the current paragraph block and centre it vertically.
        cur_block = 0
        for bi, (u, _, _) in enumerate(blocks):
            if u['kind'] == 'para' and u['ordinal'] == self._para_idx:
                cur_block = bi
                break
        top_of = [0]
        for _, _, bh in blocks:
            top_of.append(top_of[-1] + bh + gap)
        cur_top = top_of[cur_block]
        cur_h = blocks[cur_block][2]
        y0 = H // 2 - cur_h // 2 - cur_top       # scroll so current is centred

        for bi, (u, wl, bh) in enumerate(blocks):
            by = y0 + top_of[bi]
            if by + bh < -lh or by > H + lh:
                continue                          # off-screen
            if u['kind'] == 'mark':
                self._draw_mark(painter, u['name'], by, W, pad, fm, lh)
            else:
                current = (u['ordinal'] == self._para_idx)
                self._draw_para(painter, wl, by, pad, text_w, lh, fm, current)
                if current:
                    # '>' output cue to the right: Right arrow sends this paragraph.
                    painter.setPen(QColor(255, 255, 255))
                    painter.drawText(QRect(W - pad, by, pad - 12, bh),
                                     Qt.AlignmentFlag.AlignVCenter
                                     | Qt.AlignmentFlag.AlignHCenter, '>')
        painter.end()

    def _draw_para(self, painter, wl, by, pad, text_w, lh, fm, current):
        if current:
            painter.setPen(QColor(255, 255, 255))
        else:
            painter.setPen(QColor(90, 90, 90))
        y = by
        for line in wl:
            painter.drawText(QRect(pad, y, text_w, lh),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                             line)
            y += lh

    def _draw_mark(self, painter, name, by, W, pad, fm, lh):
        # A faint accent rule with the chapter name — a fixed fence.
        painter.setPen(QColor(120, 90, 40))
        label = f"/{name}" if name else "/"
        tw = fm.horizontalAdvance(label)
        cx = W // 2
        mid = by + lh // 2
        painter.drawLine(pad, mid, cx - tw // 2 - 12, mid)
        painter.drawLine(cx + tw // 2 + 12, mid, W - pad, mid)
        painter.setPen(QColor(170, 130, 60))
        painter.drawText(QRect(cx - tw // 2 - 8, by, tw + 16, lh),
                         Qt.AlignmentFlag.AlignCenter, label)

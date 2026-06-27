from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QColor, QFont, QFontMetrics
from PyQt6.QtCore import Qt, QRect, QEvent


class TriageView(QWidget):
    """F5 paragraph triage: left = 0.txt paragraphs (prose), right = type-to-filter picker."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._paragraphs = []     # list of list-of-lines
        self._previews = []       # cached single-line preview per paragraph
        self._para_idx = 0        # -1 = at ø mark
        self._source = '0.txt'
        self._filter = ''
        self._matches = []        # filtered chapter display names
        self._match_idx = 0
        self._is_new = False
        self._target = ''
        self._app_font = QFont('Consolas', 13)

    # Tab/Backtab would otherwise be eaten by focus traversal — forward them.
    def event(self, e):
        if e.type() == QEvent.Type.KeyPress and e.key() in (
                Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
            self.window().keyPressEvent(e)
            return True
        return super().event(e)

    def keyPressEvent(self, event):
        event.ignore()  # propagate to QMainWindow

    def set_para(self, paragraphs, idx, source='0.txt'):
        self._paragraphs = list(paragraphs)
        self._previews = [' '.join(p) for p in self._paragraphs]
        self._para_idx = idx
        self._source = source
        self.update()

    def set_target(self, filter_str, matches, match_idx, is_new, target=''):
        self._filter = filter_str
        self._matches = list(matches)
        self._match_idx = match_idx
        self._is_new = is_new
        self._target = target
        self.update()

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        if not painter.isActive():
            return
        W, H = self.width(), self.height()
        painter.fillRect(0, 0, W, H, QColor(0, 0, 0))

        app = self.parentWidget()
        font = getattr(app, '_app_font', self._app_font)
        small = QFont(font.family(), max(font.pointSize() - 2, 9))

        split = int(W * 0.73)
        painter.setPen(QColor(28, 28, 28))
        painter.drawLine(split, 0, split, H)

        self._draw_para_panel(painter, font, small, 0, split, H)
        self._draw_target_panel(painter, font, small, split, W - split, H)
        painter.end()

    @staticmethod
    def _elide(text, max_w, fm):
        return fm.elidedText(text, Qt.TextElideMode.ElideRight, max_w)

    def _draw_para_panel(self, painter, font, small, x, w, h):
        fm = QFontMetrics(font)
        sfm = QFontMetrics(small)
        pad = 48
        text_w = w - 2 * pad
        slh = int(sfm.height() * 1.6)
        cy = h // 2

        # Source label (faint, top-left)
        painter.setFont(small)
        painter.setPen(QColor(60, 60, 60))
        painter.drawText(x + pad, pad, self._source)

        paras = self._paragraphs
        previews = self._previews
        idx = self._para_idx
        n = len(paras)

        if not paras:
            painter.setFont(small)
            painter.setPen(QColor(45, 45, 45))
            painter.drawText(QRect(x, 0, w, h), Qt.AlignmentFlag.AlignCenter, 'ø')
            return

        if idx == -1:
            painter.setFont(font)
            painter.setPen(QColor(70, 70, 70))
            ow = fm.horizontalAdvance('ø')
            painter.drawText(x + (w - ow) // 2, cy + fm.ascent() // 2, 'ø')
            y = cy + slh
            for i in range(n):
                if y >= h:
                    break
                self._fade_line(painter, small, sfm, x + pad, y, previews[i], text_w, i + 1)
                y += slh
            y = cy - slh
            for i in range(n - 1, -1, -1):
                if y < 0:
                    break
                self._fade_line(painter, small, sfm, x + pad, y, previews[i], text_w, n - i)
                y -= slh
            return

        # Current paragraph as flowing prose
        cur_text = previews[idx]
        br = fm.boundingRect(QRect(0, 0, text_w, 100000),
                             Qt.TextFlag.TextWordWrap, cur_text)
        cur_h = br.height()
        cur_y = cy - cur_h // 2

        # Above
        y = cur_y - slh
        i = idx - 1
        while y + slh > 0:
            if i < 0:
                painter.setFont(small)
                painter.setPen(QColor(45, 45, 45))
                ow = sfm.horizontalAdvance('ø')
                painter.drawText(x + (w - ow) // 2, y, 'ø')
                break
            self._fade_line(painter, small, sfm, x + pad, y, previews[i], text_w, idx - i)
            y -= slh
            i -= 1

        # Current
        painter.setFont(font)
        painter.setPen(QColor(220, 220, 220))
        painter.drawText(QRect(x + pad, cur_y, text_w, cur_h + fm.height()),
                         Qt.TextFlag.TextWordWrap, cur_text)

        # Below
        y = cur_y + cur_h + slh
        i = idx + 1
        while y < h:
            if i >= n:
                painter.setFont(small)
                painter.setPen(QColor(45, 45, 45))
                ow = sfm.horizontalAdvance('ø')
                painter.drawText(x + (w - ow) // 2, y, 'ø')
                break
            self._fade_line(painter, small, sfm, x + pad, y, previews[i], text_w, i - idx)
            y += slh
            i += 1

        # Counter
        painter.setFont(small)
        painter.setPen(QColor(42, 42, 42))
        painter.drawText(QRect(x + pad, h - 36, text_w, 24),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         f'{idx + 1} / {n}')

    def _fade_line(self, painter, small, sfm, x, y, text, text_w, dist):
        alpha = max(28, 75 - dist * 18)
        painter.setFont(small)
        painter.setPen(QColor(alpha, alpha, alpha))
        painter.drawText(x, y, self._elide(text, text_w, sfm))

    def _draw_target_panel(self, painter, font, small, x, w, h):
        fm = QFontMetrics(font)
        sfm = QFontMetrics(small)
        pad = 16
        text_w = w - 2 * pad
        lh = int(sfm.height() * 1.9)
        cy = h // 2

        # Filter prompt (top)
        painter.setFont(small)
        painter.setPen(QColor(90, 90, 90))
        prompt = (self._filter + '▏') if self._filter else 'type to filter / name…'
        painter.drawText(QRect(x + pad, pad, text_w, sfm.height() + 4),
                         Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                         self._elide(prompt, text_w, sfm))

        if self._is_new and self._filter.strip():
            # Create-new affordance, centered — Enter creates this chapter
            painter.setFont(font)
            painter.setPen(QColor(120, 200, 120))
            label = self._elide(f'⏎ create  {self._target}', text_w, fm)
            painter.drawText(QRect(x + pad, cy - fm.height() // 2, text_w, fm.height() + 4),
                             Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                             label)
        else:
            # Visible window of matches, current highlighted at center
            names = self._matches
            cur = self._match_idx
            visible = max(1, h // lh)
            half = visible // 2
            first = max(0, cur - half)
            last = min(len(names), first + visible)
            for j in range(first, last):
                dist = j - cur
                y = cy + dist * lh
                if dist == 0:
                    painter.setPen(QColor(220, 220, 220))
                else:
                    alpha = max(28, 80 - abs(dist) * 20)
                    painter.setPen(QColor(alpha, alpha, alpha))
                painter.setFont(small)
                painter.drawText(QRect(x + pad, y - sfm.ascent(), text_w, lh),
                                 Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                                 self._elide(names[j], text_w, sfm))

        # Hint (bottom)
        painter.setFont(small)
        painter.setPen(QColor(36, 36, 36))
        painter.drawText(QRect(x + pad, h - 36, text_w, 24),
                         Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                         '→ send   ⏎ new   ⇥ cycle')

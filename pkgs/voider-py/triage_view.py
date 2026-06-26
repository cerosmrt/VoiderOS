from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QColor, QFont, QFontMetrics
from PyQt6.QtCore import Qt, QRect


class TriageView(QWidget):
    """F5 paragraph triage: left = paragraphs ring, right = book selector ring."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._paragraphs = []   # list of list-of-lines
        self._para_idx = 0      # -1 = at ø mark
        self._book_names = []
        self._book_idx = 0
        self._app_font = QFont('Consolas', 13)

    def keyPressEvent(self, event):
        event.ignore()  # propagate to QMainWindow

    def set_para(self, paragraphs, idx):
        self._paragraphs = list(paragraphs)
        self._para_idx = idx
        self.update()

    def set_book(self, names, idx):
        self._book_names = list(names)
        self._book_idx = idx
        self.update()

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
        self._draw_book_panel(painter, font, small, split, W - split, H)

        painter.end()

    def _draw_para_panel(self, painter, font, small, x, w, h):
        fm = QFontMetrics(font)
        sfm = QFontMetrics(small)
        pad = 48
        text_w = w - 2 * pad
        slh = int(sfm.height() * 1.6)

        paras = self._paragraphs
        idx = self._para_idx
        n = len(paras)
        cy = h // 2

        if not paras:
            painter.setFont(small)
            painter.setPen(QColor(45, 45, 45))
            painter.drawText(QRect(x, 0, w, h), Qt.AlignmentFlag.AlignCenter, 'ø')
            return

        if idx == -1:
            # ø mark — draw ø centered
            painter.setFont(font)
            painter.setPen(QColor(70, 70, 70))
            ow = fm.horizontalAdvance('ø')
            painter.drawText(x + (w - ow) // 2, cy + fm.ascent() // 2, 'ø')

            # paragraphs below (first is para[0])
            y = cy + slh
            for i in range(n):
                dist = i + 1
                alpha = max(28, 75 - dist * 18)
                painter.setFont(small)
                painter.setPen(QColor(alpha, alpha, alpha))
                painter.drawText(x + pad, y, self._elide(' '.join(paras[i]), text_w, sfm))
                y += slh
                if y >= h:
                    break

            # paragraphs above (last is para[n-1])
            y = cy - slh
            for i in range(n - 1, -1, -1):
                dist = n - i
                alpha = max(28, 75 - dist * 18)
                painter.setFont(small)
                painter.setPen(QColor(alpha, alpha, alpha))
                painter.drawText(x + pad, y, self._elide(' '.join(paras[i]), text_w, sfm))
                y -= slh
                if y < 0:
                    break
            return

        # Current paragraph as flowing prose
        cur_text = ' '.join(paras[idx])
        br = fm.boundingRect(QRect(0, 0, text_w, 100000),
                              Qt.TextFlag.TextWordWrap, cur_text)
        cur_h = br.height()
        cur_y = cy - cur_h // 2

        # Items above
        y = cur_y - slh
        i = idx - 1
        while y + slh > 0:
            if i < 0:
                # ø separator above
                painter.setFont(small)
                painter.setPen(QColor(45, 45, 45))
                ow = sfm.horizontalAdvance('ø')
                painter.drawText(x + (w - ow) // 2, y, 'ø')
                break
            dist = idx - i
            alpha = max(28, 75 - dist * 18)
            painter.setFont(small)
            painter.setPen(QColor(alpha, alpha, alpha))
            painter.drawText(x + pad, y, self._elide(' '.join(paras[i]), text_w, sfm))
            y -= slh
            i -= 1

        # Current paragraph
        painter.setFont(font)
        painter.setPen(QColor(215, 215, 215))
        painter.drawText(QRect(x + pad, cur_y, text_w, cur_h + fm.height()),
                         Qt.TextFlag.TextWordWrap, cur_text)

        # Items below
        y = cur_y + cur_h + slh
        i = idx + 1
        while y < h:
            if i >= n:
                # ø separator below
                painter.setFont(small)
                painter.setPen(QColor(45, 45, 45))
                ow = sfm.horizontalAdvance('ø')
                painter.drawText(x + (w - ow) // 2, y, 'ø')
                break
            dist = i - idx
            alpha = max(28, 75 - dist * 18)
            painter.setFont(small)
            painter.setPen(QColor(alpha, alpha, alpha))
            painter.drawText(x + pad, y, self._elide(' '.join(paras[i]), text_w, sfm))
            y += slh
            i += 1

        # Counter
        counter = f'{idx + 1} / {n}'
        painter.setFont(small)
        painter.setPen(QColor(42, 42, 42))
        painter.drawText(QRect(x + pad, h - 36, text_w, 24),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         counter)

    def _draw_book_panel(self, painter, font, small, x, w, h):
        sfm = QFontMetrics(small)
        pad = 16
        text_w = w - 2 * pad
        lh = int(sfm.height() * 1.8)

        names = self._book_names
        idx = self._book_idx
        cy = h // 2

        for j, name in enumerate(names):
            dist = j - idx
            y = cy + dist * lh
            if y + lh < 0 or y > h:
                continue
            if dist == 0:
                painter.setPen(QColor(215, 215, 215))
            else:
                alpha = max(28, 80 - abs(dist) * 20)
                painter.setPen(QColor(alpha, alpha, alpha))
            painter.setFont(small)
            txt = self._elide(name, text_w, sfm)
            painter.drawText(QRect(x + pad, y - sfm.ascent(), text_w, lh),
                             Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                             txt)

        painter.setFont(small)
        painter.setPen(QColor(36, 36, 36))
        painter.drawText(QRect(x + pad, h - 36, text_w, 24),
                         Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                         '→ send here')

    @staticmethod
    def _elide(text, max_w, fm):
        if fm.horizontalAdvance(text) <= max_w:
            return text
        while text and fm.horizontalAdvance(text + '…') > max_w:
            text = text[:-1]
        return text + '…'

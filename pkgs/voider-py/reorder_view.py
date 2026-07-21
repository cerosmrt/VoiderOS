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
        self._title = ''          # chapter/file name pinned (centred) at the top
        self._show_title = False  # the pinned title is a toggle (Ctrl+Shift+T)
        self._wrap_cache = {}     # (text_w, kind, text) → wrapped lines
        self._app_font = QFont('Consolas', 13)
        # In-view chapter picker (right panel), shown while sending a paragraph.
        self._picker_open = False
        self._pick_filter = ''
        self._pick_matches = []
        self._pick_match_idx = 0
        self._pick_is_new = False
        self._pick_target = ''

    def set_picker_state(self, is_open, filter_str, matches, match_idx, is_new, target):
        self._picker_open = is_open
        self._pick_filter = filter_str
        self._pick_matches = list(matches)
        self._pick_match_idx = match_idx
        self._pick_is_new = is_new
        self._pick_target = target
        self.update()

    def event(self, e):
        if e.type() == QEvent.Type.KeyPress and e.key() in (
                Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
            self.window().keyPressEvent(e)
            return True
        return super().event(e)

    def keyPressEvent(self, event):
        event.ignore()           # propagate to QMainWindow

    def set_state(self, units, para_idx, title='', show_title=False):
        self._units = list(units)
        self._para_idx = para_idx
        self._title = title or ''
        self._show_title = show_title
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

    def _wrap_unit_cached(self, u, text_w, fm):
        """Word-wrap one unit, cached by content+width so a paragraph is wrapped at
        most once per width (the font-metric work is the cost). Only the units
        actually on screen are ever wrapped — see paintEvent's outward walk."""
        key = (text_w, u['kind'],
               u.get('text') if u['kind'] == 'para' else u.get('name'))
        wl = self._wrap_cache.get(key)
        if wl is None:
            wl = self._unit_lines(u, text_w, fm)
            self._wrap_cache[key] = wl
        return wl

    def resizeEvent(self, event):
        self._wrap_cache.clear()          # widths changed → wraps are stale
        super().resizeEvent(event)

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
        # When the picker is open, paragraphs use the left ~62%; the picker the rest.
        PW = int(W * 0.62) if self._picker_open else W
        pad = max(48, int(PW * 0.14))
        text_w = PW - 2 * pad
        gap = lh                                  # blank line between units

        units = self._units
        if not units:
            painter.setPen(QColor(45, 45, 45))
            painter.drawText(QRect(0, 0, W, H), Qt.AlignmentFlag.AlignCenter, 'ø')
            if self._show_title:
                self._draw_header(painter, font, PW)
            painter.end()
            return

        # Index of the current paragraph among the units (cheap; no wrapping).
        cur = 0
        for i, u in enumerate(units):
            if u['kind'] == 'para' and u['ordinal'] == self._para_idx:
                cur = i
                break

        def draw_unit(u, by):
            wl = self._wrap_unit_cached(u, text_w, fm)
            bh = len(wl) * lh
            if u['kind'] == 'mark':
                self._draw_mark(painter, u['name'], by, PW, pad, fm, lh)
            else:
                is_cur = (u['ordinal'] == self._para_idx)
                self._draw_para(painter, wl, by, pad, text_w, lh, fm, is_cur)
                if is_cur:
                    # '>' output cue: Right arrow sends this paragraph.
                    painter.setPen(QColor(255, 255, 255))
                    painter.drawText(QRect(PW - pad, by, pad - 12, bh),
                                     Qt.AlignmentFlag.AlignVCenter
                                     | Qt.AlignmentFlag.AlignHCenter, '>')
            return bh

        # Centre the current paragraph, then draw outward until off-screen —
        # only the visible units are ever wrapped (virtualised, not the whole file).
        cur_h = len(self._wrap_unit_cached(units[cur], text_w, fm)) * lh
        y0 = H // 2 - cur_h // 2
        draw_unit(units[cur], y0)

        y = y0 + cur_h + gap                      # downward
        i = cur + 1
        while i < len(units) and y <= H + lh:
            y += draw_unit(units[i], y) + gap
            i += 1

        top_edge = y0                             # upward
        i = cur - 1
        while i >= 0 and top_edge - gap > -lh:
            wl = self._wrap_unit_cached(units[i], text_w, fm)
            by = top_edge - gap - len(wl) * lh
            draw_unit(units[i], by)
            top_edge = by
            i -= 1

        if self._picker_open:
            painter.setPen(QColor(40, 40, 40))
            painter.drawLine(PW, 0, PW, H)        # divider
            self._draw_picker(painter, font, PW, W - PW, H)
        if self._show_title:
            self._draw_header(painter, font, PW)   # pinned title (over the top)
        painter.end()

    def _draw_header(self, painter, base_font, W):
        """Pin the chapter/file name (ALL CAPS, centred) at the top of the
        paragraph column via the shared helper."""
        from widgets import draw_pinned_title
        draw_pinned_title(painter, base_font, W, self._title)

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
        # A faint grey rule with the chapter name — a fixed fence (black & white).
        painter.setPen(QColor(60, 60, 60))
        label = f"/{name}" if name else "/"
        tw = fm.horizontalAdvance(label)
        cx = W // 2
        mid = by + lh // 2
        painter.drawLine(pad, mid, cx - tw // 2 - 12, mid)
        painter.drawLine(cx + tw // 2 + 12, mid, W - pad, mid)
        painter.setPen(QColor(180, 180, 180))
        painter.drawText(QRect(cx - tw // 2 - 8, by, tw + 16, lh),
                         Qt.AlignmentFlag.AlignCenter, label)

    @staticmethod
    def _elide(text, max_w, fm):
        return fm.elidedText(text, Qt.TextElideMode.ElideRight, max_w)

    def _draw_picker(self, painter, font, x, w, h):
        """Right-side type-to-filter chapter picker (black & white)."""
        small = QFont(font.family(), max(font.pointSize() - 2, 9))
        fm = QFontMetrics(font)
        sfm = QFontMetrics(small)
        pad = 16
        text_w = w - 2 * pad
        lh = int(sfm.height() * 1.9)
        cy = h // 2

        painter.setFont(small)
        painter.setPen(QColor(150, 150, 150))
        prompt = (self._pick_filter + '▏') if self._pick_filter else 'escribí para filtrar…'
        painter.drawText(QRect(x + pad, pad, text_w, sfm.height() + 4),
                         Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                         self._elide(prompt, text_w, sfm))

        if self._pick_is_new and self._pick_filter.strip():
            painter.setFont(font)
            painter.setPen(QColor(235, 235, 235))
            label = self._elide('⏎ crear  ' + self._pick_target, text_w, fm)
            painter.drawText(QRect(x + pad, cy - fm.height() // 2, text_w, fm.height() + 4),
                             Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                             label)
        elif self._pick_matches:
            names = self._pick_matches
            cur = self._pick_match_idx % len(names)
            visible = max(1, h // lh)
            first = max(0, cur - visible // 2)
            for j in range(first, min(len(names), first + visible)):
                dist = j - cur
                yj = cy + dist * lh
                if dist == 0:
                    painter.setPen(QColor(235, 235, 235))
                else:
                    a = max(45, 110 - abs(dist) * 22)
                    painter.setPen(QColor(a, a, a))
                painter.setFont(small)
                painter.drawText(QRect(x + pad, yj - sfm.ascent(), text_w, lh),
                                 Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                                 self._elide(names[j], text_w, sfm))
        else:
            painter.setFont(small)
            painter.setPen(QColor(70, 70, 70))
            painter.drawText(QRect(x, 0, w, h), Qt.AlignmentFlag.AlignCenter, 'ø')

        painter.setFont(small)
        painter.setPen(QColor(70, 70, 70))
        painter.drawText(QRect(x + pad, h - 34, text_w, 22),
                         Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                         '→ enviar   ⏎ nuevo   ⇥ ciclar')

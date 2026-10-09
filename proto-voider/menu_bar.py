"""menu_bar.py — a clickable menu bar for mouse users (accessibility).

Invisible until the mouse moves; any key press hides it again, so it never gets
in the way of writing. Clicking a title opens a dropdown; clicking an entry
emits `triggered(action)` — the name of a keybinding action, which the app then
presses for you."""
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QColor, QFont, QFontMetrics
from PyQt6.QtCore import Qt, QEvent, QRect, pyqtSignal

from menu_model import MENUS, key_hint

PAD = 18
SIZE_PT = 12


class MenuBar(QWidget):
    triggered = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._kb = {}
        self._shown = False
        self.open_index = None
        self._font = QFont('Sans Serif', SIZE_PT)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.hide()

    @property
    def shown(self):
        return self._shown

    def set_keybindings(self, kb):
        self._kb = dict(kb)
        self.update()

    # ── show / hide ─────────────────────────────────────────────────────────

    def handle_event_type(self, etype):
        """Mouse movement shows the bar; a key press hides it. Never consumes."""
        if etype == QEvent.Type.MouseMove:
            self._set_shown(True)
        elif etype == QEvent.Type.KeyPress:
            self.close_menu()
            self._set_shown(False)

    def _set_shown(self, on):
        if on == self._shown:
            return
        self._shown = on
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, not on)
        if on:
            self.show()
            self.raise_()
        else:
            self.hide()

    # ── layout ──────────────────────────────────────────────────────────────

    def _fm(self):
        return QFontMetrics(self._font)

    def bar_height(self):
        return int(self._fm().height() * 1.8)

    def _title_rects(self):
        fm, h, x, out = self._fm(), self.bar_height(), 0, []
        for title, _ in MENUS:
            w = fm.horizontalAdvance(title) + 2 * PAD
            out.append(QRect(x, 0, w, h))
            x += w
        return out

    def _entries(self, m):
        return MENUS[m][1]

    def _dropdown_rect(self, m):
        fm, h = self._fm(), self.bar_height()
        entries = self._entries(m)
        w = max(fm.horizontalAdvance(label) + 30 + fm.horizontalAdvance(key_hint(a, self._kb))
                for label, a in entries) + 2 * PAD
        left = self._title_rects()[m].left()
        return QRect(left, h, w, h * len(entries))

    def title_center(self, m):
        c = self._title_rects()[m].center()
        return c.x(), c.y()

    def entry_center(self, m, i):
        r, h = self._dropdown_rect(m), self.bar_height()
        return r.left() + r.width() // 2, r.top() + i * h + h // 2

    def preferred_height(self):
        if self.open_index is None:
            return self.bar_height()
        return self.bar_height() + self._dropdown_rect(self.open_index).height()

    def _relayout(self):
        g = self.geometry()
        self.setGeometry(g.x(), g.y(), g.width(), self.preferred_height())

    # ── open / close ────────────────────────────────────────────────────────

    def open_menu(self, m):
        self.open_index = m
        self._relayout()
        self.update()

    def close_menu(self):
        if self.open_index is not None:
            self.open_index = None
            self._relayout()
            self.update()

    # ── mouse ───────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        p = event.position().toPoint()
        for m, r in enumerate(self._title_rects()):
            if r.contains(p):
                self.close_menu() if self.open_index == m else self.open_menu(m)
                event.accept()
                return
        if self.open_index is not None:
            r, h = self._dropdown_rect(self.open_index), self.bar_height()
            if r.contains(p):
                action = self._entries(self.open_index)[(p.y() - r.top()) // h][1]
                self.close_menu()
                self.triggered.emit(action)
                event.accept()
                return
        self.close_menu()
        event.accept()

    # ── painting ────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        if not painter.isActive():
            return
        h = self.bar_height()
        painter.setFont(self._font)
        painter.fillRect(0, 0, self.width(), h, QColor(0, 0, 0, 235))
        painter.setPen(QColor(255, 255, 255, 60))
        painter.drawLine(0, h - 1, self.width(), h - 1)
        for m, r in enumerate(self._title_rects()):
            if m == self.open_index:
                painter.fillRect(r, QColor(255, 255, 255, 40))
            painter.setPen(QColor(255, 255, 255, 220))
            painter.drawText(r, Qt.AlignmentFlag.AlignCenter, MENUS[m][0])
        if self.open_index is not None:
            r = self._dropdown_rect(self.open_index)
            painter.fillRect(r, QColor(0, 0, 0, 245))
            painter.setPen(QColor(255, 255, 255, 60))
            painter.drawRect(r.adjusted(0, 0, -1, -1))
            for i, (label, action) in enumerate(self._entries(self.open_index)):
                row = QRect(r.left() + PAD, r.top() + i * h, r.width() - 2 * PAD, h)
                painter.setPen(QColor(255, 255, 255, 230))
                painter.drawText(row, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                                 label)
                painter.setPen(QColor(255, 255, 255, 120))
                painter.drawText(row, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                                 key_hint(action, self._kb))
        painter.end()

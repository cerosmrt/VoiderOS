from PyQt6.QtWidgets import QWidget, QLabel
from PyQt6.QtGui import QPainter, QColor, QFont, QFontMetrics
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
    ("F6",                "Read an O/ book — editable; Ctrl+Delete harvests"),
    ("F7",                "Working set — up to 8 O/ books"),
    ("F8",                "Books — Enter opens the skeleton; Ctrl+P bookbinder"),
    ("",                  ""),
    ("OTHER",             None),
    ("F9",                "Metronome — type BPM, circle pulses"),
    ("F10",               "Settings — font, size, colors"),
    ("F11",               "This help screen"),
    ("Esc",               "Lock screen — PAM password to unlock"),
    ("Alt+F4",            "Quit (saves working-set position first)"),
    ("Ctrl+T",            "TTS — toggle text-to-speech"),
    ("F12",               "Screenshot"),
    ("Ctrl+F12",          "Open screenshots folder"),
    ("",                  ""),
    ("TAB  (contextual)", None),
    ("Tab  (F1)",         "Recycle random line from I/"),
    ("Shift+Tab  (F1)",  "Recycle random line from the working set (O/)"),
    ("Tab  (F2 content)", "Insert random I/ fragment at cursor (selects, re-rolls)"),
    ("Shift+Tab  (F2)",  "Insert random working-set (O/) fragment"),
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
    ("Alt+←/→  (F2 dot)", "Send this paragraph to a chapter (panel opens that side)"),
    ("Alt+Shift+←/→ (F2)","Same, from anywhere — line or paragraph"),
    ("Ctrl+B",            "Backup vault to folder"),
    ("!rem <words>  (F1)", "Command: delete from F2's file every line WITHOUT the words"),
    ("!sinpuntos  (F1)", "Command: remove the separator dots from F2's file (one paragraph); sentence periods stay"),
    ("Ctrl+G  (F3)",     "Gravitor — sentences with these words → a new chapter"),
    ("Ctrl+S",            "Export / save as PDF"),
    ("Ctrl+P",            "Print"),
    ("Ctrl+Shift+V (F4)", "Toggle carousel preview (F10 ratio, title + slides)"),
    ("Ctrl+Shift+C (F4)", "Export as Instagram carousel (chapter, or book if on '.')"),
    ("Ctrl+Shift+B (F4)", "Same, wrapped with a chosen cover + countercover"),
    ("Ctrl+Shift+A (F4)", "Export PDF+EPUB+TXT together → void/gPTA_books/<name>/"),
    ("Shift+F12",         "Screenshot only inside the circle → void/covers/"),
    ("",                  ""),
    ("EDITING  (F2)",     None),
    ("Enter",             "Void line → active file (F1)"),
    ("↑ / ↓",            "Navigate lines"),
    ("Home / End",        "Jump to first / last line"),
    ("PageUp/Down",       "Jump to prev/next paragraph"),
    ("Ctrl+0",            "Rebase: make current line first"),
    ("Ctrl+Shift+R",      "Randomise all lines in 0.txt"),
    ("Ctrl+Shift+D",      "Dispatch: route /name paragraphs to files"),
    ("Ctrl+Shift+E",      "Each space → a line break (a dot already splits too)"),
    ("Ctrl+Shift+Delete (on the first dot)", "Delete all dots, merging the file into one paragraph (so Tab shuffles every line)"),
    ("Alt+Shift+↑/↓",     "Duplicate: line, or the paragraph on a dot"),
    ("Ctrl+Delete",       "Send line to trash.txt (from trash: back to 0.txt)"),
    ("Ctrl+Shift+X",      "Open the trash"),
    ("Ctrl+Delete  (F3)", "On trash.txt: empty it (Ctrl+Z brings it back)"),
    ("Alt+Shift+↑/↓ (F3)","Duplicate the highlighted chapter"),
    ("Ctrl+Delete  (F6)", "Harvest the line into 0.txt — it leaves the book"),
    ("Ctrl+ + / -",       "Background transparency (the white stays white)"),
    ("Ctrl+Shift+ + / -", "Ink transparency (the circle and the letters)"),
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


HELP_MAX_PT = 14     # tope de la letra de la ayuda: con la letra de la app en 33 no entra nada


class HelpOverlay(QWidget):
    """F11 — referencia de atajos a pantalla completa. ↑/↓, PageUp/PageDown, Home/End y la
    rueda desplazan cuando la lista no entra; cualquier otra tecla cierra.

    Antes la altura de fila era fija (22 px) y la letra era la de la app: con letra grande
    las líneas se pisaban. Ahora la fila sale de las métricas de la letra, la letra de la
    ayuda tiene un tope, y si la lista no entra se desplaza."""

    _BG_ALPHA = 228
    _PAD = 16            # margen arriba y abajo

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._scroll = 0
        self.hide()

    # ── medidas ──────────────────────────────────────────────────────────────

    def _metrics(self):
        """→ (letra, letra de sección, letra del pie, alto de fila, ancho de teclas)."""
        app = self.parentWidget()
        base = app._app_font if hasattr(app, '_app_font') else QFont('Consolas', 11)
        pt = max(8, min(base.pointSize() if base.pointSize() > 0 else 11, HELP_MAX_PT))
        font = QFont(base.family(), pt)
        section = QFont(base.family(), max(7, pt - 2))
        hint = QFont(base.family(), max(7, pt - 3))
        fm = QFontMetrics(font)
        row_h = int(fm.height() * 1.35) + 2
        longest = max(fm.horizontalAdvance(k) for k, _ in HELP)
        key_w = min(longest + 24, int(self.width() * 0.45))
        return font, section, hint, row_h, key_w

    def _content_h(self):
        return len(HELP) * self._metrics()[3]

    def _footer_h(self):
        return 32

    def _max_scroll(self):
        total = self._content_h() + 2 * self._PAD + self._footer_h()
        return max(0, total - self.height())

    def _scroll_by(self, delta):
        self._scroll = max(0, min(self._max_scroll(), self._scroll + delta))

    # ── abrir, cerrar, desplazar ─────────────────────────────────────────────

    def toggle(self) -> None:
        if self.isVisible():
            self._close()
        else:
            self._scroll = 0
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
        key = event.key()
        row_h = self._metrics()[3]
        page = max(row_h, self.height() - 2 * row_h)
        moves = {Qt.Key.Key_Down: row_h * 2, Qt.Key.Key_Up: -row_h * 2,
                 Qt.Key.Key_PageDown: page, Qt.Key.Key_PageUp: -page}
        if self._max_scroll() > 0 and (key in moves or key in (Qt.Key.Key_Home, Qt.Key.Key_End)):
            if key == Qt.Key.Key_Home:
                self._scroll = 0
            elif key == Qt.Key.Key_End:
                self._scroll = self._max_scroll()
            else:
                self._scroll_by(moves[key])
            self.update()
            event.accept()
            return
        self._close()
        event.accept()

    def wheelEvent(self, event):
        self._scroll_by(-event.angleDelta().y())
        self.update()
        event.accept()

    # ── dibujo ───────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        if not painter.isActive():
            return
        W, H = self.width(), self.height()
        painter.fillRect(0, 0, W, H, QColor(0, 0, 0, self._BG_ALPHA))
        font, section_font, hint_font, row_h, key_w = self._metrics()

        scrolls = self._max_scroll() > 0
        y0 = self._PAD if scrolls else max(self._PAD, (H - self._content_h()) // 2)
        desc_x = max(self._PAD, (W - key_w - 24 - 340) // 2)
        val_x = desc_x + key_w + 24
        base = QFontMetrics(font).ascent()

        for i, (key, desc) in enumerate(HELP):
            top = y0 + i * row_h - self._scroll
            if top + row_h < 0 or top > H - self._footer_h():
                continue                      # fuera de la pantalla
            y = top + base + (row_h - QFontMetrics(font).height()) // 2
            if desc is None:
                painter.setFont(section_font)
                painter.setPen(QColor(110, 110, 110))
                painter.drawText(desc_x, y, key)
            elif key == "":
                pass                           # fila de aire
            else:
                painter.setFont(font)
                painter.setPen(QColor(185, 185, 185))
                painter.drawText(desc_x, y, key)
                painter.setPen(QColor(120, 120, 120))
                painter.drawText(val_x, y, desc)

        painter.setFont(hint_font)
        painter.setPen(QColor(90, 90, 90))
        pie = 'any key  close' if not scrolls else '↑/↓ PgUp/PgDn  scroll   ·   any other key  close'
        painter.drawText(QRect(0, H - 28, W, 20),
                         Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, pie)
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

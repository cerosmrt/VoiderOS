import math
from PyQt6.QtWidgets import QWidget, QLineEdit

from PyQt6.QtCore import Qt, QPropertyAnimation, pyqtProperty, QEasingCurve, pyqtSignal, QPoint, QEvent
from PyQt6.QtGui import QPainter, QFontMetrics, QFont, QKeyEvent, QColor, QPen

class CircularView(QWidget):
    line_saved = pyqtSignal()
    
    def __init__(self, ring, parent=None):
        super().__init__(parent)
        self.ring = ring
        self._offset = 0.0
        self.line_height = 38
        
        self.max_alpha = 1.0
        self.min_alpha = 0.0
        
        self.circle_radius = 0
        self.current_animation = None
        self.edit_mode = False
        self.insert_mode = False  # Nueva: modo insertar línea debajo
        self.focus_indices = None  # set of absolute ring indices to highlight in focus mode
        self.zero_marker = False   # if True, dot at ring index 0 renders in red
        self.search_mode = False             # if True, clamp rendering — don't wrap beyond list bounds
        self.search_highlight_center = False # if True, full alpha at center, 30% elsewhere
        self.show_title = False              # pinned top title (F2 only, Ctrl+Shift+T)
        self.title_text = ''
        
        # Crear el editor
        self.editor = CustomLineEdit(self)
        # Follow the configured app font so the line you're editing matches the
        # dimmed lines around it. Falls back to Consolas 11 before settings load.
        self.editor.setFont(getattr(parent, '_app_font', None) or QFont("Consolas", 11))
        self.editor.setStyleSheet("""
            QLineEdit {
                background-color: black;
                color: white;
                border: none;
                qproperty-alignment: AlignCenter;
                selection-background-color: white;
                selection-color: black;
            }
        """)
        self.editor.hide()
        self.editor.returnPressed.connect(self.save_edit)
        
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    @pyqtProperty(float)
    def offset(self):
        return self._offset

    @offset.setter
    def offset(self, value):
        self._offset = value
        self.update()

    def animate_move(self, delta):
        if self.edit_mode:
            return
            
        if self.current_animation and self.current_animation.state() == QPropertyAnimation.State.Running:
            return
        
        # Animación simple - el move() del ring ya maneja el skip de puntos
        anim = QPropertyAnimation(self, b"offset")
        anim.setDuration(180)
        anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        anim.setStartValue(self._offset)
        anim.setEndValue(self._offset - delta)
        
        def on_finished():
            self.ring.move(delta)  # Esto ya saltea puntos
            self._offset = 0.0
            self.update()
            self.current_animation = None
        
        anim.finished.connect(on_finished)
        anim.start()
        self.current_animation = anim

    def enter_edit_mode(self):
        """Entra en modo edición de la línea actual"""
        self.edit_mode = True
        self.insert_mode = False
        
        center_y = self.height() // 2
        editor_width = self.width() - 100
        self.editor.setFixedWidth(editor_width)
        self.editor.move((self.width() - editor_width) // 2, 
                         center_y - self.editor.height() // 2)
        
        current_text = self.ring.current()
        self.editor.setText(current_text)
        self.editor.selectAll()
        self.editor.show()
        self.editor.setFocus()
        
        self.update()

    def enter_insert_mode(self):
        """Entra en modo insertar nueva línea DEBAJO de la actual"""
        self.edit_mode = True
        self.insert_mode = True
        
        center_y = self.height() // 2
        editor_width = self.width() - 100
        self.editor.setFixedWidth(editor_width)
        
        # Posicionar editor DEBAJO de la línea central (media línea abajo)
        editor_y = center_y + int(self.line_height * 0.6)
        self.editor.move((self.width() - editor_width) // 2, 
                         editor_y - self.editor.height() // 2)
        
        # Editor vacío para nueva línea
        self.editor.setText("")
        self.editor.show()
        self.editor.setFocus()
        
        print("➕ Modo insertar: Nueva línea debajo")
        self.update()

    def save_edit(self):
        new_text = self.editor.text().strip()
        
        if new_text:
            if self.insert_mode:
                # Insertar NUEVA línea debajo de la actual
                self.ring.lines.insert(self.ring.index + 1, new_text)
                # Mover índice a la nueva línea
                self.ring.index += 1
                print(f"➕ Nueva línea insertada: {new_text}")
            else:
                # Editar línea actual
                self.ring.lines[self.ring.index] = new_text
                print(f"✅ Línea actualizada: {new_text}")
            
            self.line_saved.emit()
        
        self.exit_edit_mode()

    def cancel_edit(self):
        self.exit_edit_mode()

    def exit_edit_mode(self):
        self.edit_mode = False
        self.insert_mode = False
        self.editor.hide()
        self.setFocus()
        self.update()

    def calculate_alpha(self, distance_from_center_px):
        half_h = self.height() / 2
        if half_h == 0:
            return 1.0
        t = distance_from_center_px / half_h  # 0 at center, 1 at screen edge
        alpha = math.cos(t * math.pi / 2) if t < 1.0 else 0.0
        return max(0.0, min(self.max_alpha, alpha))

    def paintEvent(self, event):
        if self.width() == 0 or self.height() == 0:
            return
        painter = QPainter(self)
        if not painter.isActive():
            return
        painter.fillRect(self.rect(), Qt.GlobalColor.black)
        painter.setPen(Qt.GlobalColor.white)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        fm = QFontMetrics(self.font())

        w = self.width()
        h = self.height()
        center_y = h // 2
        # Match the inline editor width (w - 100, no fixed cap) so a line looks the
        # same in and out of edit mode: shown in full when it fits the window, only
        # reaching the edge when it is genuinely too long.
        text_area_w = w - 100
        margin = (w - text_area_w) // 2
        painter.setClipRect(margin, 0, text_area_w, h)

        # When on a dot, find which offsets belong to its paragraph
        on_dot = self.ring.current() == '.'
        highlight_offsets = set()
        if on_dot:
            n = len(self.ring.lines)
            para_size = 0
            for off in range(1, n):
                if self.ring.get(off) == '.':
                    break
                para_size += 1
            highlight_offsets = set(range(0, para_size + 1))  # 0=dot, 1..N=content

        max_lines = self.height() // (2 * self.line_height) + 2 if self.height() > 0 else 20

        line_h = fm.height()
        line_ascent = fm.ascent()
        for i in range(-max_lines, max_lines + 1):
            # In search mode, don't render items that only exist due to circular wrap
            if self.search_mode:
                linear_idx = self.ring.index + i
                if linear_idx < 0 or linear_idx >= len(self.ring.lines):
                    continue
            y_pos = center_y + (i + self._offset) * self.line_height
            text = self.ring.get(i)
            draw_y = int(y_pos - line_h / 2)
            distance_from_center = abs(y_pos - center_y)
            base_alpha = self.calculate_alpha(distance_from_center)

            if self.search_highlight_center:
                alpha = base_alpha if i == 0 else base_alpha * 0.3
            elif self.focus_indices is not None:
                abs_idx = (self.ring.index + i) % len(self.ring.lines)
                alpha = base_alpha if abs_idx in self.focus_indices else base_alpha * 0.1
            elif self.edit_mode:
                if i == 0 and not on_dot:
                    alpha = 0.0  # editor widget renders center line; painting it too causes ghosting on long lines
                elif on_dot and i in highlight_offsets:
                    alpha = base_alpha
                else:
                    alpha = base_alpha * 0.3
            else:
                alpha = base_alpha

            if alpha < 0.01:
                continue

            n = len(self.ring.lines)
            abs_idx = (self.ring.index + i) % n
            is_zero_dot = self.zero_marker and text == '.' and abs_idx == 0

            text_w = fm.horizontalAdvance(text)
            draw_x = max(margin, margin + (text_area_w - text_w) // 2)

            painter.setOpacity(alpha)
            if is_zero_dot:
                # Index-0 marker: the ø glyph (crossed-o). Same font size as body
                # text (no scaling — a bigger glyph overlapped neighbouring lines)
                # and it follows the normal alpha, so it only stands out when it's
                # the line you're actually on, not always.
                glyph = 'ø'
                gx = margin + (text_area_w - fm.horizontalAdvance(glyph)) // 2
                painter.drawText(gx, draw_y + line_ascent, glyph)
            else:
                painter.drawText(draw_x, draw_y + line_ascent, text)

        # Optional pinned title at the top (F2 only; F3/F1 keep show_title False).
        if getattr(self, 'show_title', False) and getattr(self, 'title_text', ''):
            painter.setClipping(False)
            from widgets import draw_pinned_title
            draw_pinned_title(painter, self.font(), w, self.title_text)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        screen_width = self.width()
        screen_height = self.height()
        self.circle_radius = min(screen_width, screen_height) // 2 - 35
        
        if self.edit_mode:
            center_y = self.height() // 2
            # Track the window width (no fixed cap) so the editor grows/shrinks
            # with the window instead of snapping back to a fixed 800px.
            editor_width = self.width() - 100
            self.editor.setFixedWidth(editor_width)
            self.editor.move((self.width() - editor_width) // 2,
                             center_y - self.editor.height() // 2)
        self.update()


class CustomLineEdit(QLineEdit):
    upPressed = pyqtSignal()
    downPressed = pyqtSignal()
    backspaceAtStart = pyqtSignal()
    splitAtCursor = pyqtSignal(int)
    wordSwapLeft = pyqtSignal()
    wordSwapRight = pyqtSignal()
    deleteLineToZero = pyqtSignal()
    deleteAtEnd = pyqtSignal()
    tabPressed = pyqtSignal()
    altTabPressed = pyqtSignal()   # Alt+Tab: insert from working set
    dotPressed = pyqtSignal()      # '.' key when intercept_period is True
    shiftReturnPressed = pyqtSignal()
    ctrlDeletePressed = pyqtSignal()
    homePressed = pyqtSignal()     # Home when home_end_doc is True (doc-wide jump)
    endPressed = pyqtSignal()      # End when home_end_doc is True (doc-wide jump)
    copyContext = pyqtSignal()     # Ctrl+C with no selection → contextual copy

    def __init__(self, parent=None):
        super().__init__(parent)
        self.intercept_period = False  # set True on editors that use '.' as a command key
        self.home_end_doc = False      # set True on editors where Home/End jump the
                                       # whole document (first content line / last line)

    def event(self, e):
        # Qt grabs Tab/Backtab for focus traversal BEFORE keyPressEvent runs (the
        # parent CircularView is Tab-focusable), so without this the editor's Tab
        # handler never fires and Tab just moves focus + selects the text. Catch it
        # here at the event level and treat Tab as the random-jump key (like '*').
        if e.type() == QEvent.Type.KeyPress and e.key() in (
                Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
            if e.key() == Qt.Key.Key_Backtab:
                self.altTabPressed.emit()
            else:
                self.tabPressed.emit()
            return True
        return super().event(e)

    def keyPressEvent(self, event):
        key = event.key()
        mods = event.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)

        # Caps Lock never uppercases (same as F1) — letters type in normal case.
        from widgets import neutralize_caps
        if neutralize_caps(self, event):
            return

        # Ctrl+C: a selection copies normally; with nothing selected, fire a
        # contextual copy (current line / paragraph / chapter — handled by the app).
        if ctrl and not shift and key == Qt.Key.Key_C:
            if self.hasSelectedText():
                super().keyPressEvent(event)
            else:
                self.copyContext.emit()
                event.accept()
            return

        if key == Qt.Key.Key_Period and mods == Qt.KeyboardModifier.NoModifier and self.intercept_period:
            self.dotPressed.emit()
            event.accept()
            return

        if self.home_end_doc and mods == Qt.KeyboardModifier.NoModifier:
            if key == Qt.Key.Key_Home:
                self.homePressed.emit()
                event.accept()
                return
            if key == Qt.Key.Key_End:
                self.endPressed.emit()
                event.accept()
                return

        if key == Qt.Key.Key_Tab:
            self.tabPressed.emit()
            event.accept()
            return

        if key == Qt.Key.Key_Asterisk:
            self.tabPressed.emit()
            event.accept()
            return

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if shift:
                # Always fire on Shift+Enter regardless of cursor position. In F3
                # the cursor sits at column 0, so requiring it at end-of-text meant
                # Shift+Enter silently did nothing (and the user ended up renaming
                # the current title instead of creating a new entry below).
                self.shiftReturnPressed.emit()
                event.accept()
                return
            pos = self.cursorPosition()
            if pos == 0:
                self.returnPressed.emit()
            else:
                self.splitAtCursor.emit(pos)
            event.accept()
        elif key == Qt.Key.Key_Up and mods == Qt.KeyboardModifier.NoModifier:
            self.upPressed.emit()
            event.accept()
        elif key == Qt.Key.Key_Down and mods == Qt.KeyboardModifier.NoModifier:
            self.downPressed.emit()
            event.accept()
        elif key == Qt.Key.Key_Delete and ctrl:
            if self.cursorPosition() == 0:
                self.deleteLineToZero.emit()
            self.ctrlDeletePressed.emit()
            event.accept()
        elif key == Qt.Key.Key_Delete and mods == Qt.KeyboardModifier.NoModifier and self.cursorPosition() == len(self.text()) and not self.hasSelectedText():
            self.deleteAtEnd.emit()
            event.accept()
        elif key == Qt.Key.Key_Backspace and ctrl and self.cursorPosition() == len(self.text()):
            self.deleteLineToZero.emit()
            event.accept()
        elif key == Qt.Key.Key_Left and mods == Qt.KeyboardModifier.AltModifier:
            self.wordSwapLeft.emit()
            event.accept()
        elif key == Qt.Key.Key_Right and mods == Qt.KeyboardModifier.AltModifier:
            self.wordSwapRight.emit()
            event.accept()
        elif key == Qt.Key.Key_Left and mods == Qt.KeyboardModifier.NoModifier and self.cursorPosition() == 0 and not self.hasSelectedText():
            self.setCursorPosition(len(self.text()))
            event.accept()
        elif key == Qt.Key.Key_Right and mods == Qt.KeyboardModifier.NoModifier and self.cursorPosition() == len(self.text()) and not self.hasSelectedText():
            self.setCursorPosition(0)
            event.accept()
        elif key == Qt.Key.Key_Backspace and self.cursorPosition() == 0 and not self.hasSelectedText():
            self.backspaceAtStart.emit()
            event.accept()
        elif key == Qt.Key.Key_Up and ctrl and not (mods & Qt.KeyboardModifier.ShiftModifier):
            self.home(False)
            event.accept()
        elif key == Qt.Key.Key_Down and ctrl and not (mods & Qt.KeyboardModifier.ShiftModifier):
            self.end(False)
            event.accept()
        elif key == Qt.Key.Key_Up and ctrl and (mods & Qt.KeyboardModifier.ShiftModifier):
            self.home(True)
            event.accept()
        elif key == Qt.Key.Key_Down and ctrl and (mods & Qt.KeyboardModifier.ShiftModifier):
            self.end(True)
            event.accept()
        elif ctrl and key == Qt.Key.Key_F12:
            event.ignore()
        else:
            super().keyPressEvent(event)
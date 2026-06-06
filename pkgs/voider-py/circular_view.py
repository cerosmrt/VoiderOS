import math
from PyQt6.QtWidgets import QWidget, QLineEdit

from PyQt6.QtCore import Qt, QPropertyAnimation, pyqtProperty, QEasingCurve, pyqtSignal
from PyQt6.QtGui import QPainter, QFontMetrics, QFont, QKeyEvent, QColor

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
        
        # Crear el editor
        self.editor = CustomLineEdit(self)
        self.editor.setFont(QFont("Consolas", 11))
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
        editor_width = min(self.width() - 100, 800)
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
        editor_width = min(self.width() - 100, 800)
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
        text_area_w = min(w - 100, 800)
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
            y_pos = center_y + (i + self._offset) * self.line_height
            text = self.ring.get(i)
            draw_y = int(y_pos - line_h / 2)
            distance_from_center = abs(y_pos - center_y)
            base_alpha = self.calculate_alpha(distance_from_center)

            if self.focus_indices is not None:
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

            # Zero dot stays visible at full opacity regardless of focus/highlight state
            if is_zero_dot:
                alpha = max(alpha, base_alpha)

            text_w = fm.horizontalAdvance(text)
            draw_x = max(margin, margin + (text_area_w - text_w) // 2)

            painter.setOpacity(alpha)
            if is_zero_dot:
                painter.setPen(QColor(255, 40, 40))
            painter.drawText(draw_x, draw_y + line_ascent, text)
            if is_zero_dot:
                painter.setPen(Qt.GlobalColor.white)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        screen_width = self.width()
        screen_height = self.height()
        self.circle_radius = min(screen_width, screen_height) // 2 - 35
        
        if self.edit_mode:
            center_y = self.height() // 2
            editor_width = min(self.width() - 100, 800)
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

    def keyPressEvent(self, event):
        key = event.key()
        mods = event.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
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
        elif key == Qt.Key.Key_Delete and ctrl and self.cursorPosition() == 0:
            self.deleteLineToZero.emit()
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
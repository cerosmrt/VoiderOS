# widgets.py
from PyQt6.QtWidgets import QLineEdit
from PyQt6.QtCore import Qt, pyqtSignal


class CustomLineEdit(QLineEdit):
    """QLineEdit with spacebar-as-void, Ctrl shortcut, and app-launch support."""
    spacePressed   = pyqtSignal()
    launchPressed  = pyqtSignal()   # Ctrl+Enter → launch current text as a command

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent

    def keyPressEvent(self, event):
        key = event.key()
        modifiers = event.modifiers()

        # * — recycle a random line into the entry
        if key == Qt.Key.Key_Asterisk or (key == Qt.Key.Key_8 and (modifiers & Qt.KeyboardModifier.ShiftModifier)):
            from controls import recycle_line_to_zero_txt
            recycle_line_to_zero_txt(self.parent, event)
            event.accept()
            return

        # Spacebar void mode
        if key == Qt.Key.Key_Space:
            if self.parent.use_spacebar_for_void:
                self.spacePressed.emit()
                event.accept()
                return
            super().keyPressEvent(event)
            return

        # Ctrl+Enter → launch
        ctrl = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and ctrl:
            self.launchPressed.emit()
            event.accept()
            return

        # Ctrl shortcuts
        if key == Qt.Key.Key_0 and (modifiers & Qt.KeyboardModifier.ControlModifier):
            from controls import show_random_line_from_random_file
            show_random_line_from_random_file(self.parent, event)
            event.accept()
        elif key == Qt.Key.Key_Period and (modifiers & Qt.KeyboardModifier.ControlModifier):
            from controls import show_random_line_from_current_file
            show_random_line_from_current_file(self.parent, event)
            event.accept()
        elif (modifiers & Qt.KeyboardModifier.ControlModifier) and key in (
            Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_F12, Qt.Key.Key_P
        ):
            event.ignore()
        else:
            super().keyPressEvent(event)

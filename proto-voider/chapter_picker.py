"""chapter_picker.py — elegir UN capítulo de la biblioteca, con el teclado.

Se usa en F8 para llenar un lugar del esqueleto (Prólogo, Cap 3, …). Escribir
filtra (sin mayúsculas ni acentos), ↑/↓ eligen, Enter acepta y Esc cancela: el
foco queda siempre en el filtro, así no hace falta el mouse."""
from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtWidgets import (QDialog, QLabel, QLineEdit, QListWidget,
                             QListWidgetItem, QVBoxLayout)

import gravitor

ROLE = Qt.ItemDataRole.UserRole
STYLE = '''
QDialog { background: black; }
QLabel { color: #aaa; }
QLineEdit, QListWidget { background: #111; color: white; border: 1px solid #666; padding: 4px; }
QListWidget::item:selected { background: #444; color: white; }
'''


class ChapterPicker(QDialog):

    def __init__(self, parent, names, current=None, title='Elegir capítulo'):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setStyleSheet(STYLE)
        self.resize(460, 520)
        self._names = list(names)
        self._current = current
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel('Escribí para filtrar · ↑/↓ eligen · Enter acepta · Esc cancela'))
        self.filter = QLineEdit()
        lay.addWidget(self.filter)
        self.list = QListWidget()
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)     # el foco queda en el filtro
        lay.addWidget(self.list)
        self.filter.textChanged.connect(self._fill)
        self.filter.installEventFilter(self)
        self.list.itemDoubleClicked.connect(lambda _: self.accept_choice())
        self._fill('')
        self.filter.setFocus()

    def _fill(self, text):
        q = gravitor.fold(text.strip())
        self.list.clear()
        for n in self._names:
            title = n[:-4] if n.lower().endswith('.txt') else n
            if q in gravitor.fold(title):
                it = QListWidgetItem(title)
                it.setData(ROLE, n)
                self.list.addItem(it)
        if not self.list.count():
            return
        row = 0
        if not q and self._current in self._names:
            row = [self.list.item(i).data(ROLE) for i in range(self.list.count())].index(self._current)
        self.list.setCurrentRow(row)

    def chosen(self):
        item = self.list.currentItem()
        return item.data(ROLE) if item is not None else None

    def move_selection(self, delta):
        if not self.list.count():
            return
        row = max(0, min(self.list.count() - 1, self.list.currentRow() + delta))
        self.list.setCurrentRow(row)

    def accept_choice(self):
        if self.chosen() is not None:
            self.accept()

    def eventFilter(self, obj, ev):
        if obj is self.filter and ev.type() == QEvent.Type.KeyPress:
            if ev.key() == Qt.Key.Key_Down:
                self.move_selection(+1)
                return True
            if ev.key() == Qt.Key.Key_Up:
                self.move_selection(-1)
                return True
            if ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.accept_choice()
                return True
        return super().eventFilter(obj, ev)


def pick_chapter(parent, names, current=None):
    """El nombre de archivo elegido, o None si se cancela o no hay nada que ofrecer."""
    if not names:
        return None
    picker = ChapterPicker(parent, names, current)
    return picker.chosen() if picker.exec() else None

"""book_packer_dialog.py — el cuadro del empaquetador de libros (F8).

Se abre con Enter sobre un libro. Ahí se arma el libro (título, autor, capítulos en
orden), se ve cuántas páginas en blanco sobran según las hojas por cuadernillo, y
se exportan los PDF para imprimir y coser. Edita una COPIA del libro: lo que cambies
no se guarda hasta aceptar. Qt puro; el dibujo y los archivos los hacen las
funciones que recibe (renderer_factory y exporter).
"""
import copy

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QAbstractItemView, QApplication, QDialog, QDialogButtonBox, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit,
    QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout)

ROLE = Qt.ItemDataRole.UserRole
STYLE = '''
QDialog { background: black; }
QLabel { color: white; }
QLineEdit, QPlainTextEdit, QListWidget, QTableWidget, QSpinBox {
    background: #111; color: white; border: 1px solid #666; padding: 3px; }
QListWidget::item:selected, QTableWidget::item:selected { background: #444; }
QHeaderView::section { background: #222; color: white; border: 1px solid #444; padding: 3px; }
QPushButton { background: #222; color: white; border: 1px solid #888; padding: 5px 12px; }
QPushButton:disabled { color: #666; border-color: #444; }
QPushButton:hover:!disabled { background: #333; }
'''


class _ChapterPicker(QDialog):
    """Elegir capítulos de la biblioteca para sumar al libro (varios a la vez)."""

    def __init__(self, parent, names):
        super().__init__(parent)
        self.setWindowTitle('Agregar capítulos')
        self.setStyleSheet(STYLE)
        self.resize(460, 520)
        self._names = names
        lay = QVBoxLayout(self)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText('escribí para filtrar…')
        lay.addWidget(self.filter)
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        lay.addWidget(self.list)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.filter.textChanged.connect(self._fill)
        self.list.itemDoubleClicked.connect(lambda _: self.accept())
        self._fill('')
        self.filter.setFocus()

    def _fill(self, text):
        q = text.strip().lower()
        self.list.clear()
        for n in self._names:
            title = n[:-4] if n.lower().endswith('.txt') else n
            if q in title.lower():
                it = QListWidgetItem(title)
                it.setData(ROLE, n)
                self.list.addItem(it)

    def selected(self):
        return [i.data(ROLE) for i in self.list.selectedItems()]


class BookPackerDialog(QDialog):

    def __init__(self, parent, book, available, renderer_factory, exporter,
                 f3_group=None):
        """renderer_factory(libro) → (BookRenderer | None, capítulos que faltan).
        exporter(libro, tipo) → lista de PDF escritos (tipo: duplex, manual, test,
        read). f3_group() → nombres de los capítulos del libro marcado en F3."""
        super().__init__(parent)
        self.setWindowTitle('Empaquetar libro')
        self.setStyleSheet(STYLE)
        self.resize(900, 620)
        self.book = copy.deepcopy(book)
        self.available = list(available)
        self._factory = renderer_factory
        self.exporter = exporter
        self._f3_group = f3_group
        self.renderer = None
        self._missing = []
        self.duplicate_requested = False
        self._build()
        self.refresh_book()

    # ── armado de la ventana ─────────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        cols = QHBoxLayout()
        root.addLayout(cols, 1)

        left = QVBoxLayout()
        cols.addLayout(left, 3)
        left.addWidget(QLabel('Título'))
        self.title_edit = QLineEdit(self.book['titulo'])
        left.addWidget(self.title_edit)
        left.addWidget(QLabel('Autor'))
        self.author_edit = QLineEdit(self.book['autor'])
        left.addWidget(self.author_edit)
        left.addWidget(QLabel('Capítulos, en orden'))
        self.chapters = QListWidget()
        left.addWidget(self.chapters, 1)
        row = QHBoxLayout()
        left.addLayout(row)
        self.add_btn = self._button('Agregar…', row, self._pick)
        self.f3_btn = self._button('Los de F3', row, self.add_from_f3)
        self.f3_btn.setEnabled(self._f3_group is not None)
        self.remove_btn = self._button('Quitar', row, self.remove_selected)
        self.up_btn = self._button('▲', row, lambda: self.move_selected(-1))
        self.down_btn = self._button('▼', row, lambda: self.move_selected(+1))

        right = QVBoxLayout()
        cols.addLayout(right, 2)
        right.addWidget(QLabel('Hojas por cuadernillo (cada hoja doblada = 4 páginas)'))
        self.sheets_spin = QSpinBox()
        self.sheets_spin.setRange(1, 12)
        self.sheets_spin.setValue(self.book['hojas'])
        self.sheets_spin.valueChanged.connect(self._on_sheets)
        right.addWidget(self.sheets_spin)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(['Hojas', 'Pág./cuad.', 'Cuadernillos', 'En blanco'])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        right.addWidget(self.table)
        self.summary = QLabel('')
        self.summary.setWordWrap(True)
        right.addWidget(self.summary)
        right.addWidget(QLabel('Colofón (opcional; vacío = uno automático)'))
        self.colofon_edit = QPlainTextEdit(self.book['colofon'])
        self.colofon_edit.setFixedHeight(70)
        right.addWidget(self.colofon_edit)

        exp = QHBoxLayout()
        root.addLayout(exp)
        self.duplex_btn = self._button('PDF doble cara', exp, lambda: self.export('duplex'))
        self.manual_btn = self._button('PDF manual (caras y dorsos)', exp,
                                       lambda: self.export('manual'))
        self.test_btn = self._button('Hoja de prueba', exp, lambda: self.export('test'))
        self.read_btn = self._button('PDF para leer', exp, lambda: self.export('read'))
        self.status = QLabel('')
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        bottom = QHBoxLayout()
        root.addLayout(bottom)
        self.duplicate_btn = self._button('Duplicar como edición', bottom, self._duplicate)
        bottom.addStretch(1)
        self.cancel_btn = self._button('Cancelar', bottom, self.reject)
        self.ok_btn = self._button('Guardar', bottom, self.accept)
        self.ok_btn.setDefault(True)

    @staticmethod
    def _button(text, layout, slot):
        b = QPushButton(text)
        b.setAutoDefault(False)
        b.clicked.connect(lambda _=False: slot())
        layout.addWidget(b)
        return b

    # ── el libro ─────────────────────────────────────────────────────────────

    def result_book(self):
        """El libro con todo lo que se editó. Un título en blanco conserva el viejo."""
        out = copy.deepcopy(self.book)
        out['titulo'] = self.title_edit.text().strip() or self.book['titulo']
        out['autor'] = self.author_edit.text().strip()
        out['colofon'] = self.colofon_edit.toPlainText().strip()
        out['hojas'] = self.sheets_spin.value()
        return out

    def refresh_book(self, keep_row=None):
        """Rehace el renderizador (cuenta las páginas reales) y las dos vistas."""
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self.renderer, self._missing = self._factory(self.result_book())
        finally:
            QApplication.restoreOverrideCursor()
        if self.renderer is not None:
            self.renderer.set_sheets(self.sheets_spin.value())
        self._fill_chapters(keep_row)
        self._fill_table()

    def _fill_chapters(self, keep_row=None):
        self.chapters.clear()
        for fname in self.book['capitulos']:
            title = fname[:-4] if fname.lower().endswith('.txt') else fname
            falta = fname in self._missing
            it = QListWidgetItem(('⚠ ' if falta else '') + title)
            it.setData(ROLE, fname)
            if falta:
                it.setForeground(QColor('#c88'))
                it.setToolTip('El archivo ya no existe: no se imprime.')
            self.chapters.addItem(it)
        if keep_row is not None and self.chapters.count():
            self.chapters.setCurrentRow(max(0, min(keep_row, self.chapters.count() - 1)))

    def _fill_table(self):
        if self.renderer is None:
            self.table.setRowCount(0)
            self.summary.setText('No hay capítulos para imprimir.')
            return
        rows = self.renderer.signature_table()
        self.table.setRowCount(len(rows))
        bold = QFont(self.font())
        bold.setBold(True)
        for r, row in enumerate(rows):
            cells = [('★ ' if row.best else '') + str(row.sheets), str(row.pages_per_signature),
                     str(row.signatures), str(row.blank)]
            for c, text in enumerate(cells):
                it = QTableWidgetItem(text)
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if row.best:
                    it.setFont(bold)
                if row.sheets == self.sheets_spin.value():
                    it.setBackground(QColor('#333'))
                self.table.setItem(r, c, it)
        self.summary.setText(
            f'{self.renderer.content_pages} páginas de contenido · con '
            f'{self.sheets_spin.value()} hojas por cuadernillo sobran '
            f'{self.renderer.blank} páginas en blanco (★ = la que menos deja).')

    def _on_sheets(self, value):
        if self.renderer is not None:
            self.renderer.set_sheets(value)
        self._fill_table()

    # ── capítulos ────────────────────────────────────────────────────────────

    def add_chapters(self, names):
        for n in names:
            if n not in self.book['capitulos']:
                self.book['capitulos'].append(n)
        self.refresh_book(keep_row=self.chapters.currentRow())

    def _pick(self):
        libres = [n for n in self.available if n not in self.book['capitulos']]
        if not libres:
            self.status.setText('Ya están todos los capítulos de la biblioteca.')
            return
        picker = _ChapterPicker(self, libres)
        if picker.exec() == QDialog.DialogCode.Accepted:
            self.add_chapters(picker.selected())

    def add_from_f3(self):
        if self._f3_group is not None:
            self.add_chapters(self._f3_group())

    def remove_selected(self):
        row = self.chapters.currentRow()
        if not 0 <= row < len(self.book['capitulos']):
            return
        del self.book['capitulos'][row]
        self.refresh_book(keep_row=row)

    def move_selected(self, delta):
        caps = self.book['capitulos']
        row = self.chapters.currentRow()
        j = row + delta
        if not (0 <= row < len(caps) and 0 <= j < len(caps)):
            return
        caps[row], caps[j] = caps[j], caps[row]
        self.refresh_book(keep_row=j)

    # ── exportar y duplicar ──────────────────────────────────────────────────

    def export(self, kind):
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            paths = self.exporter(self.result_book(), kind)
        finally:
            QApplication.restoreOverrideCursor()
        if not paths:
            self.status.setText('No hay nada que imprimir: el libro no tiene capítulos legibles.')
        else:
            self.status.setText('Listo: ' + ' · '.join(paths))

    def _duplicate(self):
        self.duplicate_requested = True
        self.accept()

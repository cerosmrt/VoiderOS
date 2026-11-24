"""bookbinder_dialog.py — el bookbinder: los ajustes previos a imprimir un libro.

Es un paso aparte del armado del libro (que se hace en el esqueleto de F8): acá sólo
se decide cómo se imprime y se cose. Hojas por cuadernillo con la tabla de páginas
en blanco que sobran, el colofón, y los PDF (doble cara automático, manual, hoja de
prueba y lectura). Edita una COPIA: lo que cambies no se guarda hasta aceptar."""
import copy

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QAbstractItemView, QApplication, QDialog, QHBoxLayout, QHeaderView, QLabel,
    QPlainTextEdit, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout)

STYLE = '''
QDialog { background: black; }
QLabel { color: white; }
QPlainTextEdit, QTableWidget, QSpinBox {
    background: #111; color: white; border: 1px solid #666; padding: 3px; }
QHeaderView::section { background: #222; color: white; border: 1px solid #444; padding: 3px; }
QPushButton { background: #222; color: white; border: 1px solid #888; padding: 5px 12px; }
QPushButton:disabled { color: #666; border-color: #444; }
QPushButton:hover:!disabled { background: #333; }
'''
HINT = ('Doble cara: en la impresora elegí «voltear por el borde corto». '
        'Antes de imprimir el libro entero, probá con la hoja de prueba (una sola hoja).')


class BookbinderDialog(QDialog):

    def __init__(self, parent, book, renderer_factory, exporter):
        """renderer_factory(libro) → (BookRenderer | None, archivos que faltan).
        exporter(libro, tipo) → lista de PDF escritos (duplex, manual, test, read)."""
        super().__init__(parent)
        self.book = copy.deepcopy(book)
        self.setWindowTitle(f"Bookbinder · {self.book['titulo']}")
        self.setStyleSheet(STYLE)
        self.resize(720, 560)
        self._factory, self.exporter = renderer_factory, exporter
        self.renderer = None
        self._build()
        self._load()

    def _build(self):
        root = QVBoxLayout(self)
        self.heading = QLabel(self.book['titulo'])
        big = QFont(self.font())
        big.setPointSizeF(big.pointSizeF() * 1.4)
        self.heading.setFont(big)
        root.addWidget(self.heading)
        root.addWidget(QLabel('Hojas por cuadernillo (cada hoja doblada = 4 páginas)'))
        self.sheets_spin = QSpinBox()
        self.sheets_spin.setRange(1, 12)
        self.sheets_spin.setValue(self.book['hojas'])
        self.sheets_spin.valueChanged.connect(self._on_sheets)
        root.addWidget(self.sheets_spin)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(['Hojas', 'Pág./cuad.', 'Cuadernillos', 'En blanco'])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.table, 1)
        self.summary = QLabel('')
        self.summary.setWordWrap(True)
        root.addWidget(self.summary)
        root.addWidget(QLabel('Colofón (opcional; vacío = uno automático)'))
        self.colofon_edit = QPlainTextEdit(self.book['colofon'])
        self.colofon_edit.setFixedHeight(64)
        root.addWidget(self.colofon_edit)

        row = QHBoxLayout()
        root.addLayout(row)
        self.duplex_btn = self._button('PDF doble cara', row, lambda: self.export('duplex'))
        self.manual_btn = self._button('PDF manual (caras y dorsos)', row, lambda: self.export('manual'))
        self.test_btn = self._button('Hoja de prueba', row, lambda: self.export('test'))
        self.read_btn = self._button('PDF para leer', row, lambda: self.export('read'))
        self.hint = QLabel(HINT)
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet('color: #aaa;')
        root.addWidget(self.hint)
        self.status = QLabel('')
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        bottom = QHBoxLayout()
        root.addLayout(bottom)
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
        """El libro con los ajustes de impresión; lo demás queda como estaba."""
        out = copy.deepcopy(self.book)
        out['hojas'] = self.sheets_spin.value()
        out['colofon'] = self.colofon_edit.toPlainText().strip()
        return out

    def _load(self):
        """Arma el libro UNA vez (cuenta las páginas reales) y llena la tabla."""
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self.renderer, missing = self._factory(self.result_book())
        finally:
            QApplication.restoreOverrideCursor()
        if self.renderer is not None:
            self.renderer.set_sheets(self.sheets_spin.value())
        for b in (self.duplex_btn, self.manual_btn, self.test_btn, self.read_btn):
            b.setEnabled(self.renderer is not None)
        if missing:
            self.status.setText('Faltan archivos (no se imprimen): '
                                + ', '.join(m[:-4] if m.lower().endswith('.txt') else m for m in missing))
        self._fill_table()

    def _fill_table(self):
        if self.renderer is None:
            self.table.setRowCount(0)
            self.summary.setText('No hay capítulos legibles para imprimir.')
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

    # ── exportar ─────────────────────────────────────────────────────────────

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

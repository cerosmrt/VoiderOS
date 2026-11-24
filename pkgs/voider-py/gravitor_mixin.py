# gravitor_mixin.py — Ctrl+G en F3: oraciones que tienen tal o tales palabras.
#
# Pide las palabras y la fuente (tus textos, el corpus O/ o los dos), busca en
# un hilo (la muestra de O/ tarda unos segundos) y el resultado es un archivo
# I/<lo que escribiste>.txt que F3 muestra como un capítulo más, justo debajo
# de la fila marcada. El motor (qué coincide, cómo se recorre) está en
# gravitor.py, que no sabe nada de Qt.
import os

import gravitor
from app_config import _save_config
from i18n import t

DEFAULT_BOOKS = 300     # libros de O/ por búsqueda (se cambia en F10)
SOURCES = (('Mis textos', 'i'), ('Corpus', 'o'), ('Los dos', 'both'))


class GravitorMixin:

    # ── sin Qt: se prueba solo ───────────────────────────────────────────────

    def _gravitor_registry_path(self):
        """Los archivos que Gravitor generó, para que no se busque a sí mismo."""
        return os.path.join(self.void_dir, '.gravitor.json')

    def _gravitor_sentences(self, raw):
        """Texto crudo de un libro de O/ → oraciones, con el separador de F6."""
        return self._reformat_raw_to_lines(raw)

    def _gravitor_search(self, text, source, on_progress=None, rng=None):
        """Texto + fuente ('i', 'o', 'both') → gravitor.Result, o None si no hay
        ninguna palabra. No toca nada en disco ni en F3."""
        query = gravitor.parse_query(text)
        if query is None:
            return None
        try:
            books = max(1, int(self.config.get('gravitor_books', DEFAULT_BOOKS)))
        except (TypeError, ValueError):
            books = DEFAULT_BOOKS
        return gravitor.search(
            source, query,
            i_dir=os.path.join(self.void_dir, 'I'), o_dir=self.o_dir,
            n_books=books, to_sentences=self._gravitor_sentences, rng=rng,
            skip=gravitor.load_registry(self._gravitor_registry_path()),
            on_progress=on_progress)

    def _gravitor_add_entry(self, name, lines):
        """Crea I/<name>.txt y lo inserta en F3 justo debajo de la fila marcada,
        dejándolo marcado. Nunca pisa un archivo: si el nombre ya está, usa el
        mismo sufijo -2, -3… que el resto de F3. Devuelve el nombre de archivo."""
        i_dir = os.path.join(self.void_dir, 'I')
        stem = gravitor.sanitize_name(name)
        taken = {l.lower() for l in self._library_lines}
        fname, k = stem + '.txt', 2
        while fname.lower() in taken or os.path.exists(os.path.join(i_dir, fname)):
            fname = f'{stem}-{k}.txt'
            k += 1
        fpath = os.path.join(i_dir, fname)
        os.makedirs(i_dir, exist_ok=True)
        if not self._atomic_write_lines(fpath, lines):
            return None
        at = self.book_ring.index + 1
        self.book_ring.lines.insert(at, os.path.splitext(fname)[0])
        self._library_lines.insert(at, fname)
        self._library_path_cache[fname] = fpath
        self.book_ring.index = at
        self._save_library()
        gravitor.add_to_registry(self._gravitor_registry_path(), fname)
        return fname

    def _gravitor_finish(self, text, result):
        """Con un resultado con oraciones, crea la entrada. Si no hay nada (o se
        canceló), no crea nada. Devuelve el nombre del archivo o None."""
        if result is None or result.cancelled or not result.sentences:
            return None
        return self._gravitor_add_entry(text, gravitor.result_lines(result.sentences))

    def _gravitor_make_entry(self, text, source, on_progress=None, rng=None):
        """Buscar y crear la entrada, sin cuadros. → (Result | None, fname | None)."""
        result = self._gravitor_search(text, source, on_progress=on_progress, rng=rng)
        return result, self._gravitor_finish(text, result)

    def _gravitor_remember_source(self, source):
        self.config['gravitor_source'] = source
        _save_config(self.config)

    # ── con Qt: el cuadro, la barra y los avisos ─────────────────────────────

    def _gravitor_dialog(self):
        """El cuadro: palabras + fuente. → (texto, fuente) o None si se cancela."""
        from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QLineEdit,
                                     QComboBox, QDialogButtonBox)
        d = QDialog(self)
        d.setWindowTitle(t('gravitor.title'))
        d.setFixedWidth(self._BACKUP_DIALOG_WIDTH)
        d.setStyleSheet(
            'QDialog { background: black; } QLabel { color: white; }'
            'QLineEdit, QComboBox { background: #111; color: white;'
            ' border: 1px solid #888; padding: 5px; }'
            'QComboBox QAbstractItemView { background: #111; color: white; }'
            'QPushButton { background: #222; color: white; border: 1px solid #888;'
            ' padding: 5px 14px; }')
        lay = QVBoxLayout(d)
        lay.addWidget(QLabel(t('gravitor.words_help')))
        entry = QLineEdit()
        lay.addWidget(entry)
        lay.addWidget(QLabel(t('gravitor.search_in')))
        combo = QComboBox()
        last = self.config.get('gravitor_source', 'i')
        for label, key in SOURCES:
            combo.addItem(t('gravitor.source.' + key), key)
        combo.setCurrentIndex(max(0, [k for _, k in SOURCES].index(last)
                                  if last in [k for _, k in SOURCES] else 0))
        lay.addWidget(combo)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(d.accept)
        buttons.rejected.connect(d.reject)
        lay.addWidget(buttons)
        entry.setFocus()
        if d.exec() != QDialog.DialogCode.Accepted:
            return None
        text = entry.text().strip()
        return (text, combo.currentData()) if text else None

    def _gravitor_open(self):
        """Ctrl+G en F3: pedir palabras y fuente, buscar y crear el capítulo."""
        from PyQt6.QtWidgets import QMessageBox, QProgressDialog
        from PyQt6.QtCore import Qt

        # Con una fila nueva sin nombrar, un renglón de búsqueda abierto o una
        # unión pendiente, insertar otra fila movería los índices: ignorar.
        if (getattr(self, '_book_pending_new', False)
                or getattr(self, '_book_pending_merge', False)
                or getattr(self, '_f3_search_active', False)):
            return
        asked = self._gravitor_dialog()
        if asked is None:
            return
        text, source = asked
        self._gravitor_remember_source(source)

        # La búsqueda corre en un hilo; la barra se alimenta de `estado`, que el
        # hilo escribe y el tick (en el hilo de la interfaz) lee.
        estado = {'i': 0, 'n': 1, 'name': '', 'cancel': False}
        barra = QProgressDialog(t('gravitor.searching'), t('gravitor.cancel'), 0, 1000, self)
        barra.setWindowTitle(t('gravitor.title'))
        barra.setWindowModality(Qt.WindowModality.WindowModal)
        barra.setMinimumDuration(0)
        barra.setAutoClose(False)
        barra.setAutoReset(False)
        barra.setFixedWidth(self._BACKUP_DIALOG_WIDTH)
        barra.setLabelText(t('gravitor.searching') + '\n ')
        barra.setFixedHeight(barra.sizeHint().height() + 12)

        def avance(i, n, name):
            estado.update(i=i, n=n, name=name)
            return not estado['cancel']

        def tick():
            if barra.wasCanceled():
                estado['cancel'] = True
            barra.setValue(int(1000 * estado['i'] / max(estado['n'], 1)))
            barra.setLabelText(self._progress_label(
                t('gravitor.searching_word'), estado['i'], estado['n'], estado['name']))

        try:
            barra.show()
            result = self._run_in_thread(
                lambda: self._gravitor_search(text, source, on_progress=avance),
                on_tick=tick)
        finally:
            barra.close()

        if result is None:
            return
        if result.cancelled:
            QMessageBox.information(self, t('gravitor.title'), t('gravitor.cancelled'))
            return
        if result.unavailable and not result.sentences:
            QMessageBox.warning(
                self, t('gravitor.title'), t('gravitor.no_corpus'))
            return
        fname = self._gravitor_finish(text, result)
        if fname is None:
            QMessageBox.information(
                self, t('gravitor.title'),
                t('gravitor.nothing_found', summary=result.summary()))
            return
        self.book_view._offset = 0.0
        self._book_show_editor()
        QMessageBox.information(
            self, t('gravitor.title'),
            t('gravitor.created', name=os.path.splitext(fname)[0],
              summary=result.summary()))

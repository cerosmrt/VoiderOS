# books_mixin.py — F8, el empaquetador de libros: lo que no es interfaz.
#
# Cargar y guardar el catálogo (<void>/books.json), armar un libro a partir de sus
# capítulos de I/, exportar los PDF para imprimir y coser (en <void>/book_packer/
# <título>/), y seguir lo que pasa en F3: si un capítulo se renombra o se borra,
# los libros que lo tienen se enteran. El modelo está en books.py y el dibujo en
# book_render.py; la vista y el cuadro están en la parte de Qt de más abajo.
import os

import books
import gravitor
from line_ring import LineRing


BOOKS_HINT = 'Sin libros · Shift+Enter crea uno'


class BooksMixin:

    # ── el catálogo ──────────────────────────────────────────────────────────

    def _books_path(self):
        return os.path.join(self.void_dir, 'books.json')

    def _books_load(self):
        self.books = books.load(self._books_path())
        return self.books

    def _books_save(self):
        books.save(self._books_path(), self.books)

    def _books_chapters_available(self):
        """Los capítulos de la biblioteca de F3, en su orden (sin puntos ni portal)."""
        return [fn for fn in self._library_lines if fn and fn not in ('.', '0.txt')]

    # ── armar y exportar ─────────────────────────────────────────────────────

    def _books_renderer(self, book):
        """→ (BookRenderer | None, capítulos que faltan). Los capítulos cuyo archivo
        ya no existe se saltean y se avisan; sin ninguno legible no hay libro."""
        from PyQt6.QtGui import QFont
        from book_render import BookRenderer
        chapters, missing = [], []
        for fname in book['capitulos']:
            path = (self._library_path_cache.get(fname)
                    or os.path.join(self.void_dir, 'I', fname))
            if not os.path.isfile(path):
                missing.append(fname)
                continue
            chapters.append((os.path.splitext(fname)[0], self._reading_file_lines(path)))
        if not chapters:
            return None, missing
        font = QFont(self.config.get('reading_font', 'EB Garamond'),
                     int(self.config.get('reading_size', 13)))
        r = BookRenderer(book['titulo'], chapters, font, autor=book['autor'],
                         colofon=book['colofon'], sheets=book['hojas'],
                         hyphenate_lang=self.config.get('reading_hyphen_lang', 'auto'))
        return r, missing

    def _books_out_dir(self, book):
        return os.path.join(self.void_dir, 'book_packer',
                            gravitor.sanitize_name(book['titulo']))

    def _books_export(self, book, kind):
        """kind: 'duplex' (doble cara automático), 'manual' (caras y dorsos aparte),
        'test' (hoja de prueba) o 'read' (páginas A5 para leer). → los PDF escritos;
        [] si el libro no tiene nada que imprimir."""
        if kind not in ('duplex', 'manual', 'test', 'read'):
            raise ValueError(f'export desconocido: {kind}')
        r, _ = self._books_renderer(book)
        if r is None:
            return []
        out = self._books_out_dir(book)
        os.makedirs(out, exist_ok=True)
        name = gravitor.sanitize_name(book['titulo'])

        def p(suffix):
            return os.path.join(out, f'{name} - {suffix}.pdf')
        if kind == 'duplex':
            r.write_duplex_pdf(p('doble cara'))
            return [p('doble cara')]
        if kind == 'manual':
            r.write_manual_pdfs(p('caras'), p('dorsos'))
            return [p('caras'), p('dorsos')]
        if kind == 'test':
            r.write_test_pdf(p('hoja de prueba'))
            return [p('hoja de prueba')]
        r.write_reading_pdf(p('lectura'))
        return [p('lectura')]

    # ── seguir lo que pasa en F3 ─────────────────────────────────────────────

    def _books_notify(self, kind, a, b=None):
        """F3 avisa que un capítulo cambió ('renamed': a → b) o se fue ('deleted': a).
        Nunca rompe a F3: un fallo acá sólo se avisa."""
        try:
            if kind == 'renamed':
                self._books_on_chapter_renamed(a, b)
            elif kind == 'deleted':
                self._books_on_chapter_deleted(a)
        except Exception as e:
            print(f"⚠️ Los libros no se enteraron de '{a}': {e}")

    def _books_update_file(self, change):
        """Aplica change(data) al catálogo del disco y lo guarda sólo si cambió algo.
        Sin books.json no se crea nada: F3 no tiene por qué fabricar un catálogo."""
        path = self._books_path()
        if not os.path.exists(path):
            return
        data = books.load(path)
        if change(data):
            books.save(path, data)
            self.books = data

    def _books_on_chapter_renamed(self, old, new):
        self._books_update_file(lambda d: books.rename_chapter_everywhere(d, old, new))

    def _books_on_chapter_deleted(self, fname):
        self._books_update_file(lambda d: books.drop_chapter_everywhere(d, fname))

    # ── la vista de F8: el anillo de libros ──────────────────────────────────
    #
    # F1 es Voider, F2 el anillo de líneas, F3 el de capítulos y esto el de libros.
    # Enter abre el cuadro para empaquetar el libro marcado.

    def _books_rebuild_ring(self, select_id=None):
        libros = self.books['libros'] if self.books else []
        self._books_ids = [x['id'] for x in libros]
        self.books_ring = LineRing([x['titulo'] for x in libros] or [BOOKS_HINT])
        if select_id in self._books_ids:
            self.books_ring.index = self._books_ids.index(select_id)
        if self.books_view is not None:
            self.books_view.ring = self.books_ring
            self.books_view._offset = 0.0

    def _books_current(self):
        """El libro marcado, o None si no hay ninguno."""
        if not self._books_ids:
            return None
        return books.find(self.books, self._books_ids[self.books_ring.index])

    def _books_f3_group(self):
        return books.group_at(self._library_lines, self.book_ring.index)

    def _books_refresh_editor(self):
        view = self.books_view
        view._offset = 0.0
        view.editor.setText(self.books_ring.current())
        view.editor.setCursorPosition(0)
        view.update()

    def _books_navigate(self, delta):
        self.books_ring.move(delta)
        self._books_refresh_editor()

    def _books_show_editor(self):
        view = self.books_view
        view.edit_mode = True
        editor_width = view.width() - 100
        view.editor.setFixedWidth(editor_width)
        view.editor.move((view.width() - editor_width) // 2,
                         view.height() // 2 - view.editor.sizeHint().height() // 2)
        view.editor.setText(self.books_ring.current())
        view.editor.setReadOnly(True)        # el título se cambia en el cuadro
        view.editor.show()
        view.editor.setFocus()
        view.editor.setCursorPosition(0)
        view.update()

    def _books_show(self):
        """Entrar a F8: cargar el catálogo y mostrar el anillo de libros."""
        from circular_view import CircularView
        self._books_load()
        self._books_rebuild_ring()
        if not self.books_view:
            self.books_view = CircularView(self.books_ring, self)
            self.books_view.setFont(self._app_font)
            self.books_view.editor.returnPressed.disconnect()
            self.books_view.editor.returnPressed.connect(self._books_open_packer)
            self.books_view.editor.upPressed.connect(lambda: self._books_navigate(-1))
            self.books_view.editor.downPressed.connect(lambda: self._books_navigate(1))
            self.books_view.editor.shiftReturnPressed.connect(self._books_new)
            self.books_view.editor.ctrlReturnPressed.connect(self._books_new)
            self.books_view.editor.ctrlDeletePressed.connect(self._books_delete)
            self.stack.addWidget(self.books_view)
        else:
            self.books_view.ring = self.books_ring
            self.books_view._offset = 0.0
        self.stack.setCurrentWidget(self.books_view)
        self.entry.hide()
        self.books_view.update()
        self._books_show_editor()

    def _books_new(self):
        """Shift+Enter: un libro nuevo, vacío. Los capítulos se le suman en el cuadro."""
        from PyQt6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, 'Libro nuevo', 'Título del libro:')
        name = name.strip()
        if not ok or not name:
            return
        book = books.new_book(self.books, name)
        self._books_save()
        self._books_rebuild_ring(select_id=book['id'])
        self._books_refresh_editor()

    def _books_delete(self):
        """Ctrl+Delete: borrar el libro marcado. Los capítulos no se tocan."""
        from PyQt6.QtWidgets import QMessageBox
        book = self._books_current()
        if book is None:
            return
        yes = QMessageBox.StandardButton.Yes
        no = QMessageBox.StandardButton.No
        if QMessageBox.question(
                self, 'Borrar libro',
                f"¿Borrar «{book['titulo']}»?\nLos capítulos no se tocan: sólo sale el libro.",
                yes | no, no) != yes:
            return
        idx = self.books_ring.index
        books.delete_book(self.books, book['id'])
        self._books_save()
        self._books_rebuild_ring()
        if self._books_ids:
            self.books_ring.index = min(idx, len(self._books_ids) - 1)
        self._books_refresh_editor()

    def _books_open_packer(self):
        """Enter: el cuadro para empaquetar el libro marcado."""
        from book_packer_dialog import BookPackerDialog
        book = self._books_current()
        if book is None:
            return
        dlg = BookPackerDialog(self, book, self._books_chapters_available(),
                               self._books_renderer, self._books_export,
                               f3_group=self._books_f3_group)
        if not dlg.exec():
            return
        nuevo = dict(dlg.result_book())      # copiar ANTES de vaciar: no depender de alias
        book.clear()
        book.update(nuevo)
        select = book['id']
        if dlg.duplicate_requested:
            copia = books.duplicate_book(self.books, book['id'])
            select = copia['id']
        self._books_save()
        self._books_rebuild_ring(select_id=select)
        self._books_refresh_editor()

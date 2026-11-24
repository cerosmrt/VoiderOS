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
# La referencia al software de la página final: manda al lector a descargar Voider.
DEFAULT_REFERENCE_TEXT = 'Compuesto con Voider'
DEFAULT_REFERENCE_URL = 'www.godplaystheartist.com'


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
        """Los capítulos de la biblioteca de F3, en su orden (sin puntos ni portal). Si en
        esta sesión no se entró a F3 la biblioteca todavía no se leyó: se lee acá."""
        if not getattr(self, '_library_lines', None):
            self._load_library()
        return [fn for fn in self._library_lines if fn and fn not in ('.', '0.txt')]

    # ── armar y exportar ─────────────────────────────────────────────────────

    def _books_renderer(self, book):
        """→ (BookRenderer | None, capítulos que faltan). Los capítulos cuyo archivo
        ya no existe se saltean y se avisan; sin ninguno legible no hay libro."""
        from PyQt6.QtGui import QFont
        from book_render import BookRenderer
        chapters, missing = [], []
        for fname in books.chapters_of(book):
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
                         hyphenate_lang=self.config.get('reading_hyphen_lang', 'auto'),
                         cover=book.get('portada', True),
                         reference=self._books_reference_text() if book.get('referencia', True) else '')
        return r, missing

    def _books_reference_text(self):
        """La referencia al software de la página final: un texto y el link para
        descargar Voider. Los dos se cambian en config.json (book_reference_text,
        book_reference_url); un link vacío ('') es "sin link", no "el de siempre"."""
        text = (self.config.get('book_reference_text') or DEFAULT_REFERENCE_TEXT).strip()
        url = self.config.get('book_reference_url')
        url = DEFAULT_REFERENCE_URL if url is None else str(url).strip()
        return f'{text}\nDescargalo en {url}' if url else text

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

    # ── la vista de F8, como F3 ──────────────────────────────────────────────
    #
    # F1 es Voider, F2 el anillo de líneas, F3 el de capítulos y esto el de libros.
    # Dos niveles sobre el mismo anillo:
    #   libros    — la lista de libros. ↑/↓ navegan SIN cursor; Enter entra al
    #               esqueleto; ←/→ o escribir renombran; Shift+Enter crea;
    #               Ctrl+Delete borra; Alt+Shift+↑/↓ duplica como edición.
    #   esqueleto — Portada · Título · Autor · Prólogo · Dedicatoria · Cap 1…n ·
    #               Epílogo · Referencia · .   Enter llena la fila (capítulo, o
    #               prende/apaga, o pide el texto); Ctrl+Delete la vacía; Esc vuelve.
    # Ctrl+P / Ctrl+S abren el bookbinder: los ajustes de impresión, aparte.

    def _books_rebuild_ring(self, select_id=None, select_key=None):
        if self._books_level == 'skeleton':
            book = books.find(self.books, self._books_open_id) if self.books else None
            if book is not None:
                rows = books.rows(book)
                self._books_row_keys = [r['key'] for r in rows]
                self.books_ring = LineRing([r['text'] for r in rows])
                if select_key in self._books_row_keys:
                    self.books_ring.index = self._books_row_keys.index(select_key)
                if self.books_view is not None:
                    self.books_view.ring = self.books_ring
                    self.books_view._offset = 0.0
                return
            self._books_level = 'books'              # el libro ya no está
        libros = self.books['libros'] if self.books else []
        self._books_ids = [x['id'] for x in libros]
        self.books_ring = LineRing([x['titulo'] for x in libros] or [BOOKS_HINT])
        if select_id in self._books_ids:
            self.books_ring.index = self._books_ids.index(select_id)
        if self.books_view is not None:
            self.books_view.ring = self.books_ring
            self.books_view._offset = 0.0

    def _books_current(self):
        """El libro marcado en la lista de libros, o None si no hay ninguno."""
        if not self._books_ids:
            return None
        return books.find(self.books, self._books_ids[self.books_ring.index])

    def _books_open_book(self):
        """El libro cuyo esqueleto está abierto."""
        return books.find(self.books, self._books_open_id) if self.books else None

    def _books_current_key(self):
        """La fila marcada del esqueleto ('portada', 'cap:2', …), o None."""
        if self._books_level != 'skeleton' or not self._books_row_keys:
            return None
        return self._books_row_keys[self.books_ring.index]

    def _books_f3_group(self):
        return books.group_at(self._library_lines, self.book_ring.index)

    def _books_refresh_editor(self):
        view = self.books_view
        ed = view.editor
        cur = self.books_ring.current()
        view._offset = 0.0
        if self._books_level == 'skeleton':
            ed.setText('· · ·' if cur == '.' else cur)
            ed.setReadOnly(True)         # las filas son «etiqueta · valor»: se llenan con Enter
        else:
            ed.setText(cur)
            ed.setReadOnly(not self._books_ids)
        ed.setCursorPosition(0)
        ed.leave_edit()
        view.update()

    def _books_show_editor(self):
        view = self.books_view
        view.edit_mode = True
        editor_width = view.width() - 100
        view.editor.setFixedWidth(editor_width)
        view.editor.move((view.width() - editor_width) // 2,
                         view.height() // 2 - view.editor.sizeHint().height() // 2)
        view.editor.show()
        view.editor.setFocus()
        self._books_refresh_editor()

    def _books_show(self):
        """Entrar a F8: cargar el catálogo y mostrar el anillo."""
        from circular_view import CircularView
        self._books_load()
        self._books_rebuild_ring(select_key=self._books_current_key())
        if not self.books_view:
            self.books_view = CircularView(self.books_ring, self)
            self.books_view.setFont(self._app_font)
            ed = self.books_view.editor
            ed.set_browse_mode(True)         # sin cursor al navegar, como F3
            ed.returnPressed.disconnect()
            ed.returnPressed.connect(self._books_enter)
            ed.splitAtCursor.connect(lambda _pos: self._books_commit_edit())
            ed.upPressed.connect(lambda: self._books_navigate(-1))
            ed.downPressed.connect(lambda: self._books_navigate(1))
            ed.shiftReturnPressed.connect(self._books_new)
            ed.ctrlReturnPressed.connect(self._books_new)
            ed.ctrlDeletePressed.connect(self._books_ctrl_delete)
            self.stack.addWidget(self.books_view)
        else:
            self.books_view.ring = self.books_ring
            self.books_view._offset = 0.0
        self.stack.setCurrentWidget(self.books_view)
        self.entry.hide()
        self.books_view.update()
        self._books_show_editor()

    # ── moverse y entrar ─────────────────────────────────────────────────────

    def _books_navigate(self, delta):
        self._books_commit_edit()            # si se estaba renombrando, se guarda primero
        self.books_ring.move(delta)
        self._books_refresh_editor()

    def _books_enter(self):
        """Enter. Editando el título de un libro: lo guarda. Si no, en la lista entra
        al esqueleto y en el esqueleto llena la fila."""
        if not self.books_view.editor.browsing:
            self._books_commit_edit()
            return
        if self._books_level == 'books':
            self._books_open_skeleton()
        else:
            self._books_activate()

    def _books_open_skeleton(self):
        book = self._books_current()
        if book is None:
            return
        self._books_level = 'skeleton'
        self._books_open_id = book['id']
        self._books_rebuild_ring(select_key='portada')
        self._books_refresh_editor()

    def _books_back(self):
        open_id = self._books_open_id
        self._books_level = 'books'
        self._books_rebuild_ring(select_id=open_id)
        self._books_refresh_editor()

    def _books_escape(self):
        """Esc: del esqueleto vuelve a la lista (True). En la lista no hace nada acá
        (False): el router lo manda a F1 como en las demás vistas."""
        if self._books_level == 'skeleton':
            self._books_back()
            return True
        return False

    def _books_commit_edit(self):
        """Guarda el nuevo título de un libro que se estaba editando (←/→ o escribir)."""
        ed = self.books_view.editor
        if ed.browsing or self._books_level != 'books':
            return
        book = self._books_current()
        new = ed.text().strip()
        if book is not None and new and new != book['titulo']:
            books.rename_book(book, new)
            self._books_save()
            self._books_rebuild_ring(select_id=book['id'])
        ed.leave_edit()
        self._books_refresh_editor()

    # ── las filas del esqueleto ──────────────────────────────────────────────

    def _books_activate(self):
        """Enter sobre una fila del esqueleto."""
        key = self._books_current_key()
        book = self._books_open_book()
        if book is None or key is None:
            return
        if key in ('portada', 'referencia'):
            books.toggle(book, key)
            self._books_save()
            self._books_rebuild_ring(select_key=key)
            self._books_refresh_editor()
        elif key in ('titulo', 'autor'):
            self._books_edit_meta(key)
        elif key in books.ROLES or key.startswith('cap:'):
            self._books_pick_for(key)

    def _books_pick_for(self, key):
        """Elegir el capítulo que llena un lugar. Se ofrecen los de la biblioteca que el
        libro todavía no usa (más el que ya está en ese lugar, si hay uno)."""
        import chapter_picker
        book = self._books_open_book()
        current = books.slot_file(book, key)
        used = set(books.chapters_of(book))
        names = [n for n in self._books_chapters_available() if n not in used or n == current]
        if not names:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(self, 'Capítulos',
                                    'No hay capítulos para sumar: el libro ya tiene todos los de la '
                                    'biblioteca (o la biblioteca está vacía).')
            return
        fname = chapter_picker.pick_chapter(self, names, current)
        if not fname:
            return
        books.assign(book, key, fname)
        self._books_save()
        self._books_rebuild_ring(select_key=key)
        self._books_refresh_editor()

    def _books_edit_meta(self, key):
        """El título o el autor del libro, con un cuadro de texto."""
        from PyQt6.QtWidgets import QInputDialog
        book = self._books_open_book()
        label = 'Título' if key == 'titulo' else 'Autor'
        current = book['titulo'] if key == 'titulo' else book['autor']
        text, ok = QInputDialog.getText(self, label, f'{label}:', text=current)
        if not ok:
            return
        text = text.strip()
        if key == 'titulo':
            if not text:
                return                       # un libro sin título no existe
            books.rename_book(book, text)
        else:
            book['autor'] = text
        self._books_save()
        self._books_rebuild_ring(select_key=key)
        self._books_refresh_editor()

    def _books_clear_slot(self):
        key = self._books_current_key()
        book = self._books_open_book()
        if book is None or key is None:
            return
        if books.clear_slot(book, key):
            self._books_save()
            self._books_rebuild_ring(select_key=key)
            self._books_refresh_editor()

    def _books_ctrl_delete(self):
        """Ctrl+Delete: en la lista borra el libro; en el esqueleto vacía la fila."""
        if self._books_level == 'skeleton':
            self._books_clear_slot()
        else:
            self._books_delete()

    # ── crear, borrar, duplicar ──────────────────────────────────────────────

    def _books_new(self):
        """Shift+Enter: un libro nuevo, vacío. Se llena en su esqueleto."""
        if self._books_level != 'books':
            return
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
        """Borrar el libro marcado. Los capítulos no se tocan."""
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

    def _books_duplicate(self):
        """Alt+Shift+↑/↓: el libro marcado como edición nueva, justo debajo."""
        book = self._books_current() if self._books_level == 'books' else None
        if book is None:
            return
        copia = books.duplicate_book(self.books, book['id'])
        self._books_save()
        self._books_rebuild_ring(select_id=copia['id'])
        self._books_refresh_editor()

    # ── el bookbinder: los ajustes de impresión ──────────────────────────────

    def _books_open_bookbinder(self):
        """Ctrl+P / Ctrl+S: hojas por cuadernillo, colofón y los PDF. Es un paso aparte
        del armado: sólo se guardan los ajustes de impresión."""
        from bookbinder_dialog import BookbinderDialog
        book = self._books_open_book() if self._books_level == 'skeleton' else self._books_current()
        if book is None:
            return
        dlg = BookbinderDialog(self, book, self._books_renderer, self._books_export)
        if not dlg.exec():
            return
        nuevo = dlg.result_book()
        book['hojas'], book['colofon'] = nuevo['hojas'], nuevo['colofon']
        self._books_save()
        self._books_rebuild_ring(select_id=book['id'], select_key=self._books_current_key())
        self._books_refresh_editor()

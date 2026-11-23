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

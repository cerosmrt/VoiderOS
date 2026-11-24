# f4_mixin.py — F4 reading render methods
import os

from i18n import t
from PyQt6.QtGui import QFont


class F4Mixin:

    def _para_ordinal_at(self, lines, idx):
        """0-based index of the paragraph (dot-model) containing lines[idx].

        Paragraphs are maximal runs of non-empty, non-'.' lines. A line that is
        a '.' separator or blank maps to the paragraph that precedes it (or 0 if
        none precedes). Shared by F4 (scroll target) and F5 (start paragraph)."""
        if not lines:
            return 0
        if idx < 0:
            idx = 0
        if idx >= len(lines):
            idx = len(lines) - 1
        ordinal = -1
        in_para = False
        last_para = 0
        for i, raw in enumerate(lines):
            s = raw.strip()
            is_text = False
            if s == '.':
                # A '.' is the only paragraph separator; blanks are ignored.
                in_para = False
            elif s:
                if not in_para:
                    ordinal += 1
                    in_para = True
                last_para = ordinal
                is_text = True
            if i == idx:
                return max(0, ordinal if is_text else last_para)
        return max(0, last_para)

    def _reading_file_lines(self, path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return [l.rstrip('\n') for l in f]
        except Exception:
            return []

    def _reading_sections(self):
        """Return (sections, at_para). F4 follows the F3 highlight: on a '.'
        separator → the whole book below it (one section per chapter, '0' portals
        skipped); on a chapter → that highlighted chapter's file. `at_para` is True
        only when the shown file is the active one, so 'open on my current line'
        applies; otherwise F4 opens at the first page."""
        ring = getattr(self, 'book_ring', None)
        if ring and ring.lines and ring.current() == '.':
            n = len(self._library_lines)
            secs, i = [], (ring.index + 1) % n
            for _ in range(n - 1):
                fn = self._library_lines[i]
                if fn == '.':
                    break
                if fn != '0.txt':                      # skip scratch portals
                    fpath = self._library_path_cache.get(fn)
                    if fpath and os.path.isfile(fpath):
                        # Every file under the dot is a chapter, the first one
                        # included. The book's own title is asked for when
                        # exporting (_carousel_out_name / _with_book_title).
                        secs.append((os.path.splitext(fn)[0],
                                     self._reading_file_lines(fpath)))
                i = (i + 1) % n
            if secs:
                return secs, False
        # Highlighted chapter (so a move in F3 is reflected immediately).
        fname = self._library_current_fname() if (ring and ring.lines) else None
        if fname:
            fpath = self._library_path_cache.get(fname)
            if fpath and os.path.isfile(fpath):
                at_para = (os.path.abspath(fpath)
                           == os.path.abspath(self.current_file_path))
                return [(os.path.splitext(fname)[0],
                         self._reading_file_lines(fpath))], at_para
        # Fallback: the active file.
        path = self.current_file_path
        title = os.path.splitext(os.path.basename(path))[0]
        return [(title, self._reading_file_lines(path))], True

    def _carousel_dimensions(self):
        """(w_px, h_px) for the F10-configured carousel ratio."""
        from reading_page import CAROUSEL_PRESETS
        preset = self.config.get('carousel_preset', '4:5')
        if preset == 'custom':
            return (int(self.config.get('carousel_w', 1080)),
                    int(self.config.get('carousel_h', 1350)))
        return CAROUSEL_PRESETS.get(preset, CAROUSEL_PRESETS['4:5'])

    def _toggle_f4_carousel_view(self):
        """Ctrl+Shift+V in F4: switch between book view (A5) and carousel
        preview (the F10-configured ratio, paginated slide by slide — exactly
        what export_carousel() would write)."""
        self._f4_carousel_view = not getattr(self, '_f4_carousel_view', False)
        self._reading_refresh()
        print(f"🎠 Carousel preview {'ON' if self._f4_carousel_view else 'OFF'}")

    def _reading_refresh_carousel(self):
        """F4 carousel preview: same content selection as the book view
        (_reading_sections), rendered at the carousel ratio. The first
        section's title becomes a dedicated title slide (page 0); later
        chapters in a whole-book selection keep their title inline, same as
        the book view — only the ratio changes."""
        from reading_page import build_reading_document, carousel_page_pt
        sections, _ = self._reading_sections()
        w_px, h_px = self._carousel_dimensions()
        reading_font = QFont(self.config.get('reading_font', 'EB Garamond'),
                             int(self.config.get('reading_size', 13)))
        page_pt = carousel_page_pt(w_px, h_px)
        title = sections[0][0] if sections else ''
        body_sections = list(sections)
        if body_sections:
            body_sections[0] = ('', body_sections[0][1])
        doc, para_blocks, layout = build_reading_document(
            body_sections, reading_font, page_pt=page_pt,
            hyphenate_lang=self.config.get('reading_hyphen_lang', 'auto'))
        self.reading_view.set_document(doc, para_blocks, layout, title_slide=title)

    def _reading_refresh(self):
        """Rebuild the F4 book pages. A single chapter opens on the page holding
        the line you're on; a whole book opens at the first page."""
        if getattr(self, '_f4_carousel_view', False):
            self._reading_refresh_carousel()
            return
        from reading_page import build_reading_document, A5_PT
        sections, single_file = self._reading_sections()
        reading_font = QFont(self.config.get('reading_font', 'EB Garamond'),
                             int(self.config.get('reading_size', 13)))
        doc, para_blocks, layout = build_reading_document(
            sections, reading_font, page_pt=A5_PT,
            hyphenate_lang=self.config.get('reading_hyphen_lang', 'auto'))
        self.reading_view.set_document(doc, para_blocks, layout)
        if single_file:
            ring = getattr(self, 'line_ring', None)
            if ring and ring.lines:
                p = self._para_ordinal_at(ring.lines, ring.index)
                self.reading_view.goto_paragraph(p)

    def _carousel_out_name(self, sections):
        """Folder name for a carousel export: the chapter's own title when
        there's exactly one, otherwise prompted (a whole-book export has no
        single title to name it with). None means the user cancelled."""
        if len(sections) == 1:
            return sections[0][0] or 'capitulo'
        from PyQt6.QtWidgets import QInputDialog
        out_name, ok = QInputDialog.getText(
            self, t('f4.title'), t('f4.book_title_prompt'))
        out_name = out_name.strip()
        if not ok or not out_name:
            print("✗ Carrusel cancelado (sin nombre).")
            return None
        return out_name

    def _with_book_title(self, sections, title):
        """A whole book (several chapters) opens with a page of its own that
        bears the title the user typed: a title-only section in front. A single
        chapter has no book title — its own title is already its heading."""
        if len(sections) <= 1:
            return sections
        return [(title, [])] + list(sections)

    def _sections_as_txt(self, sections):
        """The TXT half of the sale bundle. A single chapter is just its own
        raw lines — the file exactly as it already exists in void/I/, still
        directly importable into someone else's Voider. Multiple chapters (a
        whole-book export) get joined with '/chapter-title' fences between
        them — the same marker Voider's own dispatch/split already use, not
        a new format."""
        if len(sections) == 1:
            return '\n'.join(sections[0][1]) + '\n'
        parts = []
        for title, lines in sections:
            parts.append(f'/{title}')
            parts.extend(lines)
        return '\n'.join(parts) + '\n'

    def _sale_bundle_dir(self, lang, out_name):
        """Where the bundle for `out_name` lands. lang is 'Español' or
        'English'. Federico configures sale_bundle_dir_es/en to point
        straight at his godplaystheartist checkout (books/ or libros/) —
        those are absolute paths specific to his machine, so unset (anyone
        else's Voider, including a compiled .exe handed to someone else)
        falls back to a local void_dir/gPTA_books/<name>/ instead."""
        key = 'sale_bundle_dir_es' if lang == 'Español' else 'sale_bundle_dir_en'
        base = self.config.get(key, '').strip()
        if not base:
            base = os.path.join(self.void_dir, 'gPTA_books')
        return os.path.join(base, out_name)

    def export_sale_bundle(self):
        """Ctrl+Shift+A (F4): export PDF + EPUB + TXT together — everything
        needed to upload a book for sale in one place. Same scope as
        PDF/carousel export (_reading_sections): the highlighted chapter, or
        the whole book when F3 is highlighted on a '.' separator. Asks which
        language it's in, since the destination (and eventually the site's
        own catalog) is split by language, not something Voider can guess."""
        from PyQt6.QtGui import QColor
        from PyQt6.QtPrintSupport import QPrinter
        from PyQt6.QtWidgets import QInputDialog
        from reading_page import (build_reading_document, compute_page_offsets,
                                  print_reading_document, A5_PT)
        from epub_export import build_epub

        sections, _ = self._reading_sections()
        if not sections:
            print("✓ Nada para exportar.")
            return
        out_name = self._carousel_out_name(sections)
        if out_name is None:
            return
        lang, ok = QInputDialog.getItem(
            self, t('f4.language_title'), t('f4.language_prompt'),
            ['Español', 'English'], 0, False)
        if not ok:
            print("✗ Bundle cancelado (sin idioma).")
            return

        out_dir = self._sale_bundle_dir(lang, out_name)
        os.makedirs(out_dir, exist_ok=True)

        reading_font = QFont(self.config.get('reading_font', 'EB Garamond'),
                             int(self.config.get('reading_size', 13)))
        ink = QColor('#111111')

        # The PDF of a whole book opens with the title on a page of its own;
        # the EPUB carries the title as metadata and the TXT is the chapters.
        doc, para_blocks, layout = build_reading_document(
            self._with_book_title(sections, out_name), reading_font,
            page_pt=A5_PT,
            hyphenate_lang=self.config.get('reading_hyphen_lang', 'auto'), ink=ink)
        offsets = compute_page_offsets(doc, layout.block_h, layout.title_blocks)
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(os.path.join(out_dir, out_name + '.pdf'))
        print_reading_document(doc, layout, offsets, printer, ink=ink)

        build_epub(sections, out_name, os.path.join(out_dir, out_name + '.epub'))

        with open(os.path.join(out_dir, out_name + '.txt'), 'w',
                 encoding='utf-8') as f:
            f.write(self._sections_as_txt(sections))

        print(f'📦 Bundle de venta: {len(sections)} capítulo(s) → {out_dir}')

    def _write_carousel_chapters(self, sections, out_dir, w_px, h_px,
                                 reading_font, page_pt, start_n=1):
        """Write each section's title + body slides into out_dir, numbered
        continuously from start_n. Returns (next_n, total_body_slides)."""
        from reading_page import (
            build_reading_document, compute_page_offsets,
            render_carousel_page, render_title_slide, lines_to_paragraphs,
        )
        from PyQt6.QtWidgets import QApplication
        n = start_n
        total_body = 0
        for title, lines in sections:
            # Empty section title: the title gets its own standalone slide,
            # so build_reading_document must not also draw it atop the body.
            doc, para_blocks, layout = build_reading_document(
                [('', lines)], reading_font, page_pt=page_pt,
                hyphenate_lang=self.config.get('reading_hyphen_lang', 'auto'))
            offsets = compute_page_offsets(doc, layout.block_h, layout.title_blocks)

            render_title_slide(title, reading_font, w_px, h_px).save(
                os.path.join(out_dir, f'{n}_titulo.png'))
            n += 1
            if not lines_to_paragraphs(lines):
                continue          # title-only section (the book's title slide)
            for page in range(len(offsets)):
                render_carousel_page(doc, layout, offsets, page, w_px, h_px).save(
                    os.path.join(out_dir, f'{n}.png'))
                n += 1
                total_body += 1
                # A long export can take many seconds with no native Qt call
                # in the loop to pump the event loop on its own — without
                # this the window manager reports Voider as not responding.
                QApplication.processEvents()
        return n, total_body

    def export_carousel(self):
        """Ctrl+Shift+C (F4): export the current F3 selection as Instagram
        carousel slides — same scope as PDF export (_reading_sections): the
        highlighted chapter, or the whole book when F3 is highlighted on a
        '.' separator. Each chapter gets its own centered title slide, then
        its body paginated to the configured aspect ratio. Written to
        void_dir/carousel/<name>/."""
        from reading_page import carousel_page_pt
        sections, _ = self._reading_sections()
        if not sections:
            print("✓ Nada para exportar.")
            return
        out_name = self._carousel_out_name(sections)
        if out_name is None:
            return

        w_px, h_px = self._carousel_dimensions()
        reading_font = QFont(self.config.get('reading_font', 'EB Garamond'),
                             int(self.config.get('reading_size', 13)))
        page_pt = carousel_page_pt(w_px, h_px)
        out_dir = os.path.join(self.void_dir, 'carousel', out_name)
        os.makedirs(out_dir, exist_ok=True)

        # A whole book opens with a slide bearing the title the user typed.
        n, total_body = self._write_carousel_chapters(
            self._with_book_title(sections, out_name), out_dir, w_px, h_px,
            reading_font, page_pt)
        print(f'🎠 Carrusel: {len(sections)} capítulo(s), {total_body} slides '
              f'+ títulos → {out_dir}')

    def export_carousel_with_cover(self):
        """Ctrl+Shift+B (F4): like export_carousel(), but wrapped with a
        chosen cover image (the 'I' mark centered on top) and a countercover
        slide bearing the chapter's title — a separate, opt-in command so a
        plain Ctrl+Shift+C export never needs a cover picked. The cover image
        comes from void_dir/covers/ (see Shift+F12, take_circle_screenshot)."""
        from reading_page import carousel_page_pt, render_cover_slide, render_title_slide
        sections, _ = self._reading_sections()
        if not sections:
            print("✓ Nada para exportar.")
            return

        from PyQt6.QtWidgets import QFileDialog
        covers_dir = os.path.join(self.void_dir, 'covers')
        cover_path, _ = QFileDialog.getOpenFileName(
            self, t('f4.pick_cover'), covers_dir, t('f4.images_filter'))
        if not cover_path:
            print("✗ Cancelado (sin portada).")
            return

        out_name = self._carousel_out_name(sections)
        if out_name is None:
            return
        back_title = sections[0][0] if len(sections) == 1 else out_name

        w_px, h_px = self._carousel_dimensions()
        reading_font = QFont(self.config.get('reading_font', 'EB Garamond'),
                             int(self.config.get('reading_size', 13)))
        page_pt = carousel_page_pt(w_px, h_px)
        out_dir = os.path.join(self.void_dir, 'carousel', out_name)
        os.makedirs(out_dir, exist_ok=True)

        render_cover_slide(cover_path, w_px, h_px, reading_font).save(
            os.path.join(out_dir, '1_portada.png'))
        n, total_body = self._write_carousel_chapters(
            sections, out_dir, w_px, h_px, reading_font, page_pt, start_n=2)
        render_title_slide(back_title, reading_font, w_px, h_px).save(
            os.path.join(out_dir, f'{n}_contratapa.png'))

        print(f'🎠 Carrusel (con tapa): {len(sections)} capítulo(s), {total_body} '
              f'slides + portada + contratapa → {out_dir}')

    def _build_reading_html(self, lines, title):
        """Convert Voider line format to prose HTML for F4 reading render.

        Rules: consecutive non-'.' lines join into a paragraph (punto y seguido);
        a '.' line becomes a paragraph break (punto y aparte); ø stripped.
        """
        import html as _html
        paragraphs = []
        current = []
        for line in lines:
            if line == '.':
                if current:
                    paragraphs.append(' '.join(current))
                    current = []
            elif line == 'ø':
                pass
            else:
                current.append(_html.escape(line))
        if current:
            paragraphs.append(' '.join(current))

        parts = [
            '<html><body>',
            f'<h2 style="text-align:center;margin:3em 0 2em;">'
            f'{_html.escape(title)}</h2>',
        ]
        for i, para in enumerate(paragraphs):
            parts.append(
                f'<p style="text-align:justify;margin:0 0 1.2em 0;">'
                f'<a name="vpara{i}"></a>{para}</p>')
        parts.append('</body></html>')
        return ''.join(parts)

    def _build_doc_html(self, lines, title):
        """Build centered HTML from a list of lines (dots become spacers)."""
        parts = ['<html><body style="color:black;background:white;'
                 'font-family:Consolas,monospace;">']
        parts.append(f'<h2 style="text-align:center;margin:3em 0 2em;">{title}</h2>')
        for line in lines:
            if line == '.':
                parts.append('<p style="margin:0.8em 0;">&nbsp;</p>')
            else:
                parts.append(f'<p style="text-align:center;margin:0.4em 0;">{line}</p>')
        parts.append('</body></html>')
        return ''.join(parts)

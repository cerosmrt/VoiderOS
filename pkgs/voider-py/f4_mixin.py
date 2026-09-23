# f4_mixin.py — F4 reading render methods
import os

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

    def _reading_refresh(self):
        """Rebuild the F4 book pages. A single chapter opens on the page holding
        the line you're on; a whole book opens at the first page."""
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

    def _carousel_current_chapter(self):
        """(title, lines) of the chapter a carousel export acts on: the F3
        highlight when it's on an actual chapter, else the active file. Unlike
        _reading_sections, this never expands into the whole-book multi-chapter
        view — a carousel export is always exactly one chapter."""
        ring = getattr(self, 'book_ring', None)
        fname = self._library_current_fname() if (ring and ring.lines) else None
        if fname:
            fpath = self._library_path_cache.get(fname)
            if fpath and os.path.isfile(fpath):
                return os.path.splitext(fname)[0], self._reading_file_lines(fpath)
        path = self.current_file_path
        title = os.path.splitext(os.path.basename(path))[0]
        return title, self._reading_file_lines(path)

    def export_carousel(self):
        """Ctrl+Shift+C (F4): export the current chapter as Instagram carousel
        slides — a dedicated centered title slide, then the chapter body
        paginated to the configured aspect ratio. Written to
        void_dir/carousel/<Chapter>/."""
        from reading_page import (
            build_reading_document, compute_page_offsets, carousel_page_pt,
            render_carousel_page, render_title_slide, CAROUSEL_PRESETS,
        )
        title, lines = self._carousel_current_chapter()

        preset = self.config.get('carousel_preset', '4:5')
        if preset == 'custom':
            w_px = int(self.config.get('carousel_w', 1080))
            h_px = int(self.config.get('carousel_h', 1350))
        else:
            w_px, h_px = CAROUSEL_PRESETS.get(preset, CAROUSEL_PRESETS['4:5'])

        reading_font = QFont(self.config.get('reading_font', 'EB Garamond'),
                             int(self.config.get('reading_size', 13)))
        page_pt = carousel_page_pt(w_px, h_px)
        # Empty section title: the title gets its own standalone slide below,
        # so build_reading_document must not also draw it atop the body.
        doc, para_blocks, layout = build_reading_document(
            [('', lines)], reading_font, page_pt=page_pt,
            hyphenate_lang=self.config.get('reading_hyphen_lang', 'auto'))
        offsets = compute_page_offsets(doc, layout.block_h, layout.title_blocks)

        out_dir = os.path.join(self.void_dir, 'carousel', title or 'capitulo')
        os.makedirs(out_dir, exist_ok=True)

        render_title_slide(title, reading_font, w_px, h_px).save(
            os.path.join(out_dir, '1_titulo.png'))
        for i, page in enumerate(range(len(offsets)), start=2):
            render_carousel_page(doc, layout, offsets, page, w_px, h_px).save(
                os.path.join(out_dir, f'{i}.png'))
        print(f'🎠 Carrusel: {len(offsets)} slides + titulo → {out_dir}')

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

# f4_mixin.py — F4 reading render methods
import os


class F4Mixin:

    def _reading_refresh(self):
        """Rebuild the F4 reading render from the current file."""
        path = self.current_file_path
        title = os.path.splitext(os.path.basename(path))[0]
        try:
            with open(path, 'r', encoding='utf-8') as f:
                lines = [l.strip() for l in f if l.strip()]
        except Exception:
            lines = []
        html = self._build_reading_html(lines, title)
        self.reading_view.setHtml(html)
        bg = self.config.get('bg_color', '#000000')
        fg = self.config.get('text_color', '#ffffff')
        font = self.config.get('font_family', 'Georgia')
        size = int(self.config.get('font_size', 13))
        self.reading_view.setStyleSheet(
            f'QTextBrowser {{ background:{bg}; color:{fg}; '
            f'font-family:{font}; font-size:{size}pt; '
            f'padding:60px 120px; border:none; }}'
        )

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
        for para in paragraphs:
            parts.append(f'<p style="text-align:justify;margin:0 0 1.2em 0;">{para}</p>')
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

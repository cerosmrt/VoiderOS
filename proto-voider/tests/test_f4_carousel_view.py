"""F4 carousel preview (Ctrl+Shift+V): toggles ReadingPageView between book
layout (A5) and the carousel ratio configured in F10 — page 1 is the title
slide, page 2+ is the body, matching export_carousel() exactly. Content
selection reuses _reading_sections(), same as PDF export: one chapter, or the
whole book when F3 is highlighted on a '.' separator.
"""
import os
import types
import pytest
from unittest.mock import MagicMock

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication

from line_ring import LineRing
from helpers import make_ring_app


@pytest.fixture(scope='module')
def qapp():
    yield QApplication.instance() or QApplication([])


def _app(tmp_path, library, book_index):
    from new_interface import FullscreenCircleApp
    app = make_ring_app(['.'])
    void = tmp_path
    (void / 'I').mkdir(exist_ok=True)
    app.void_dir = str(void)
    app._library_lines = []
    app._library_path_cache = {}
    ring_names = []
    for name in library:
        if name == '.':
            app._library_lines.append('.')
            ring_names.append('.')
            continue
        fn = name + '.txt'
        app._library_lines.append(fn)
        ring_names.append(name)
        p = str(void / 'I' / fn)
        with open(p, 'w', encoding='utf-8') as f:
            f.write(f'body of {name}\n')
        app._library_path_cache[fn] = p
    app.book_ring = LineRing(ring_names or ['.'])
    app.book_ring.index = book_index
    app.current_file_path = str(void / 'I' / '0.txt')
    open(app.current_file_path, 'w').close()
    app.reading_view = MagicMock()
    app.config = {}
    app._f4_carousel_view = False
    for nm in ('_reading_sections', '_reading_file_lines', '_reading_refresh_carousel',
               '_reading_refresh', '_carousel_dimensions', '_toggle_f4_carousel_view'):
        setattr(app, nm, types.MethodType(getattr(FullscreenCircleApp, nm), app))
    return app


class TestCarouselDimensions:

    def test_preset_returns_its_pixel_size(self, qapp, tmp_path):
        app = _app(tmp_path, ['.', 'A'], 0)
        app.config['carousel_preset'] = '1:1'
        assert app._carousel_dimensions() == (1080, 1080)

    def test_default_preset_is_4_5(self, qapp, tmp_path):
        app = _app(tmp_path, ['.', 'A'], 0)
        assert app._carousel_dimensions() == (1080, 1350)

    def test_custom_uses_configured_dimensions(self, qapp, tmp_path):
        app = _app(tmp_path, ['.', 'A'], 0)
        app.config['carousel_preset'] = 'custom'
        app.config['carousel_w'] = 800
        app.config['carousel_h'] = 600
        assert app._carousel_dimensions() == (800, 600)


class TestToggle:

    def test_toggle_flips_the_flag(self, qapp, tmp_path):
        app = _app(tmp_path, ['.', 'A'], 1)
        app._reading_refresh = MagicMock()
        app._toggle_f4_carousel_view()
        assert app._f4_carousel_view is True
        app._toggle_f4_carousel_view()
        assert app._f4_carousel_view is False

    def test_toggle_refreshes_the_view(self, qapp, tmp_path):
        app = _app(tmp_path, ['.', 'A'], 1)
        app._reading_refresh = MagicMock()
        app._toggle_f4_carousel_view()
        app._reading_refresh.assert_called_once()


class TestRefreshCarousel:

    def test_first_section_title_becomes_the_dedicated_title_slide(self, qapp, tmp_path):
        app = _app(tmp_path, ['.', 'A', 'B'], 1)   # highlight A
        app._reading_refresh_carousel()
        _, kwargs = app.reading_view.set_document.call_args
        assert kwargs['title_slide'] == 'A'

    def test_body_pages_use_the_configured_ratio(self, qapp, tmp_path):
        app = _app(tmp_path, ['.', 'A'], 1)
        app.config['carousel_preset'] = '1:1'
        app._reading_refresh_carousel()
        args, _ = app.reading_view.set_document.call_args
        doc, para_blocks, layout = args[0], args[1], args[2]
        assert layout.page_w == pytest.approx(layout.page_h)

    def test_default_ratio_is_4_5(self, qapp, tmp_path):
        app = _app(tmp_path, ['.', 'A'], 1)
        app._reading_refresh_carousel()
        args, _ = app.reading_view.set_document.call_args
        layout = args[2]
        assert layout.page_h == pytest.approx(layout.page_w * 1350 / 1080)

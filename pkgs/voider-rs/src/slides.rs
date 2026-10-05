//! The slides themselves: a canvas, text drawn onto it, and PNG in and out.
//!
//! A port of `render_carousel_page`, `render_title_slide` and `render_cover_slide`
//! from `reading_page.py`. Black paper and white ink — Voider's own look, not the
//! printed book's white page.

#![allow(dead_code)]

use std::path::Path;

use ab_glyph::{point, Font, PxScale, ScaleFont};

use crate::carousel::{Geometry, LINE_HEIGHT_PCT};
use crate::typeset::{Line, TypeFont};

pub const PAPER: [u8; 3] = [0, 0, 0];
pub const INK: [u8; 3] = [255, 255, 255];

/// The title is set larger than the body, as in the Python (`2.2 ×`).
pub const TITLE_SCALE: f32 = 2.2;
/// Side margin of a title slide, as a share of its width.
pub const TITLE_MARGIN: f32 = 0.12;

/// An RGB image we can draw on.
#[derive(Clone)]
pub struct Canvas {
    pub w: u32,
    pub h: u32,
    rgb: Vec<u8>,
}

impl Canvas {
    pub fn new(w: u32, h: u32, paper: [u8; 3]) -> Canvas {
        let mut rgb = Vec::with_capacity(w as usize * h as usize * 3);
        for _ in 0..w as usize * h as usize {
            rgb.extend_from_slice(&paper);
        }
        Canvas { w, h, rgb }
    }

    fn at(&self, x: u32, y: u32) -> usize {
        (y as usize * self.w as usize + x as usize) * 3
    }

    pub fn pixel(&self, x: u32, y: u32) -> [u8; 3] {
        let i = self.at(x, y);
        [self.rgb[i], self.rgb[i + 1], self.rgb[i + 2]]
    }

    pub fn set_pixel(&mut self, x: u32, y: u32, rgb: [u8; 3]) {
        if x < self.w && y < self.h {
            let i = self.at(x, y);
            self.rgb[i..i + 3].copy_from_slice(&rgb);
        }
    }

    /// Lay `ink` over what is there, as much as `coverage` (0..1) says. Anything
    /// off the canvas is simply not drawn.
    fn blend(&mut self, x: i64, y: i64, ink: [u8; 3], coverage: f32) {
        if x < 0 || y < 0 || x >= self.w as i64 || y >= self.h as i64 {
            return;
        }
        let c = coverage.clamp(0.0, 1.0);
        let i = self.at(x as u32, y as u32);
        for k in 0..3 {
            let under = self.rgb[i + k] as f32;
            self.rgb[i + k] = (under + (ink[k] as f32 - under) * c).round() as u8;
        }
    }

    /// Draw `text` with its baseline at `baseline`, starting at `x`, in `ink` —
    /// coverage-blended, so the edges are smooth.
    pub fn draw_text(&mut self, font: &TypeFont, px: f32, x: f32, baseline: f32, text: &str, ink: [u8; 3]) {
        let scale = PxScale::from(px);
        let scaled = font.font().as_scaled(scale);
        let mut caret = x;
        let mut prev = None;
        for c in text.chars() {
            let id = scaled.glyph_id(c);
            if let Some(p) = prev {
                caret += scaled.kern(p, id);
            }
            let glyph = id.with_scale_and_position(scale, point(caret, baseline));
            if let Some(outlined) = font.font().outline_glyph(glyph) {
                let b = outlined.px_bounds();
                let (ox, oy) = (b.min.x.floor() as i64, b.min.y.floor() as i64);
                outlined.draw(|gx, gy, cov| self.blend(ox + gx as i64, oy + gy as i64, ink, cov));
            }
            caret += scaled.h_advance(id);
            prev = Some(id);
        }
    }

    /// The image as PNG bytes.
    pub fn to_png(&self) -> Vec<u8> {
        let mut out = Vec::new();
        {
            let mut enc = png::Encoder::new(&mut out, self.w.max(1), self.h.max(1));
            enc.set_color(png::ColorType::Rgb);
            enc.set_depth(png::BitDepth::Eight);
            let mut writer = enc.write_header().expect("png header");
            writer.write_image_data(&self.rgb).expect("png data");
        }
        out
    }

    /// Write the PNG whole or not at all: a half-written slide is worse than none.
    pub fn save_png(&self, path: &Path) -> std::io::Result<()> {
        let tmp = path.with_extension("png.tmp");
        std::fs::write(&tmp, self.to_png())?;
        std::fs::rename(&tmp, path)
    }

    /// Whether anything but `paper` has been drawn.
    pub fn is_blank(&self, paper: [u8; 3]) -> bool {
        self.rgb.chunks_exact(3).all(|p| p == paper)
    }
}

/// An image read from disk.
pub struct Image {
    pub w: u32,
    pub h: u32,
    pub rgb: Vec<u8>,
}

/// Read a PNG (palette, grey, 16-bit and alpha all flattened to RGB). `None` for
/// anything that is missing or that is not a PNG we can read.
pub fn read_png(path: &Path) -> Option<Image> {
    let file = std::fs::File::open(path).ok()?;
    let mut decoder = png::Decoder::new(std::io::BufReader::new(file));
    decoder.set_transformations(png::Transformations::EXPAND | png::Transformations::STRIP_16);
    let mut reader = decoder.read_info().ok()?;
    let mut buf = vec![0; reader.output_buffer_size()?];
    let info = reader.next_frame(&mut buf).ok()?;
    let data = &buf[..info.buffer_size()];
    let rgb: Vec<u8> = match info.color_type {
        png::ColorType::Rgb => data.to_vec(),
        png::ColorType::Rgba => data.chunks_exact(4).flat_map(|p| [p[0], p[1], p[2]]).collect(),
        png::ColorType::Grayscale => data.iter().flat_map(|&g| [g, g, g]).collect(),
        png::ColorType::GrayscaleAlpha => data.chunks_exact(2).flat_map(|p| [p[0], p[0], p[0]]).collect(),
        png::ColorType::Indexed => return None, // EXPAND should have removed this
    };
    if rgb.len() != info.width as usize * info.height as usize * 3 {
        return None;
    }
    Some(Image { w: info.width, h: info.height, rgb })
}

/// The line height the slides use: the font's own, at 132 % — the book's leading.
fn leading(font: &TypeFont, px: f32) -> f32 {
    font.natural_height(px) * LINE_HEIGHT_PCT / 100.0
}

/// One page of a book set in `font`, onto a `geo`-sized slide.
pub fn render_body_page(font: &TypeFont, geo: &Geometry, lines: &[Line], paper: [u8; 3], ink: [u8; 3]) -> Canvas {
    let mut canvas = Canvas::new(geo.w, geo.h, paper);
    let line_h = leading(font, geo.font_px);
    // The leading is split above and below the letters, like proportional
    // height in a text document, so a line's baseline sits inside its slot.
    let pad = (line_h - font.natural_height(geo.font_px)) / 2.0;
    for line in lines {
        let baseline = geo.margin_top + line.y + pad + font.ascent(geo.font_px);
        for word in &line.words {
            canvas.draw_text(font, geo.font_px, geo.margin_side + word.x, baseline, &word.text, ink);
        }
    }
    canvas
}

/// Break `text` into lines no wider than `width`, for centring. Greedy, and a
/// word wider than the whole width is cut so nothing runs out.
fn wrap_for_centering(font: &TypeFont, px: f32, width: f32, text: &str) -> Vec<String> {
    let space = font.advance(" ", px);
    let mut lines: Vec<String> = Vec::new();
    let mut cur = String::new();
    let mut cur_w = 0.0;
    for word in text.split_whitespace().flat_map(|w| crate::typeset::split_to_fit(font, px, width, w)) {
        let w = font.advance(&word, px);
        if !cur.is_empty() && cur_w + space + w > width {
            lines.push(std::mem::take(&mut cur));
            cur_w = 0.0;
        }
        if cur.is_empty() {
            cur_w = w;
        } else {
            cur.push(' ');
            cur_w += space + w;
        }
        cur.push_str(&word);
    }
    if !cur.is_empty() {
        lines.push(cur);
    }
    lines
}

/// Centre `text` in the slide: wrapped inside the title margins, each line
/// centred, the whole block centred vertically.
fn draw_title(canvas: &mut Canvas, text: &str, font: &TypeFont, font_px: f32, ink: [u8; 3]) {
    if text.trim().is_empty() {
        return;
    }
    let px = font_px * TITLE_SCALE;
    let width = canvas.w as f32 * (1.0 - 2.0 * TITLE_MARGIN);
    let lines = wrap_for_centering(font, px, width, text);
    let line_h = font.natural_height(px);
    let top = (canvas.h as f32 - lines.len() as f32 * line_h) / 2.0;
    for (i, line) in lines.iter().enumerate() {
        let x = (canvas.w as f32 - font.advance(line, px)) / 2.0;
        canvas.draw_text(font, px, x, top + i as f32 * line_h + font.ascent(px), line, ink);
    }
}

/// A slide holding only a centred title. An empty title leaves it blank.
pub fn render_title_slide(title: &str, font: &TypeFont, w: u32, h: u32, font_px: f32, paper: [u8; 3], ink: [u8; 3]) -> Canvas {
    let mut canvas = Canvas::new(w, h, paper);
    draw_title(&mut canvas, title, font, font_px, ink);
    canvas
}

/// The cover: a picture scaled to fill the frame (centre-cropped, never
/// distorted) with `mark` centred on top. A picture that cannot be read leaves
/// the plain paper under the mark.
pub fn render_cover_slide(image_path: &Path, w: u32, h: u32, font: &TypeFont, font_px: f32, mark: &str, paper: [u8; 3], ink: [u8; 3]) -> Canvas {
    let mut canvas = Canvas::new(w, h, paper);
    if let Some(src) = read_png(image_path).filter(|s| s.w > 0 && s.h > 0) {
        // Scale so the picture covers the frame on both axes, then crop the centre.
        let scale = (w as f32 / src.w as f32).max(h as f32 / src.h as f32);
        let crop_x = (src.w as f32 * scale - w as f32) / 2.0;
        let crop_y = (src.h as f32 * scale - h as f32) / 2.0;
        let at = |x: i64, y: i64, k: usize| -> f32 {
            let (x, y) = (x.clamp(0, src.w as i64 - 1) as usize, y.clamp(0, src.h as i64 - 1) as usize);
            src.rgb[(y * src.w as usize + x) * 3 + k] as f32
        };
        for y in 0..h {
            for x in 0..w {
                // Bilinear: the source point this pixel looks at, and its four neighbours.
                let u = (x as f32 + 0.5 + crop_x) / scale - 0.5;
                let v = (y as f32 + 0.5 + crop_y) / scale - 0.5;
                let (x0, y0) = (u.floor(), v.floor());
                let (fx, fy) = (u - x0, v - y0);
                let mut px = [0u8; 3];
                for k in 0..3 {
                    let top = at(x0 as i64, y0 as i64, k) * (1.0 - fx) + at(x0 as i64 + 1, y0 as i64, k) * fx;
                    let bot = at(x0 as i64, y0 as i64 + 1, k) * (1.0 - fx) + at(x0 as i64 + 1, y0 as i64 + 1, k) * fx;
                    px[k] = (top * (1.0 - fy) + bot * fy).round().clamp(0.0, 255.0) as u8;
                }
                canvas.set_pixel(x, y, px);
            }
        }
    }
    draw_title(&mut canvas, mark, font, font_px, ink);
    canvas
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::carousel::geometry;
    use crate::typeset::{paginate, typeset};

    fn font() -> TypeFont {
        TypeFont::load("__no_such_family__")
    }

    // ── the canvas ───────────────────────────────────────────────────────────

    #[test]
    fn a_canvas_is_the_size_asked_and_the_colour_asked() {
        let c = Canvas::new(40, 30, [10, 20, 30]);
        assert_eq!((c.w, c.h), (40, 30));
        assert_eq!(c.pixel(0, 0), [10, 20, 30]);
        assert_eq!(c.pixel(39, 29), [10, 20, 30]);
    }

    #[test]
    fn drawing_text_changes_pixels_and_only_near_the_text() {
        let mut c = Canvas::new(300, 100, PAPER);
        assert!(c.is_blank(PAPER));
        c.draw_text(&font(), 40.0, 10.0, 60.0, "Hola", INK);
        assert!(!c.is_blank(PAPER));
        assert_eq!(c.pixel(290, 5), PAPER); // far corner untouched
    }

    #[test]
    fn text_is_anti_aliased_not_just_black_and_white() {
        let mut c = Canvas::new(300, 100, PAPER);
        c.draw_text(&font(), 40.0, 10.0, 60.0, "Hola", INK);
        let mut greys = 0;
        for y in 0..100 {
            for x in 0..300 {
                let p = c.pixel(x, y);
                if p != PAPER && p != INK {
                    greys += 1;
                }
            }
        }
        assert!(greys > 20, "edges should be smooth, found {greys} grey pixels");
    }

    #[test]
    fn text_off_the_edge_does_not_panic() {
        let mut c = Canvas::new(50, 50, PAPER);
        c.draw_text(&font(), 40.0, -30.0, 20.0, "Desborda por la izquierda", INK);
        c.draw_text(&font(), 40.0, 30.0, 300.0, "Y por abajo", INK);
    }

    #[test]
    fn png_round_trips_through_bytes_and_disk() {
        let mut c = Canvas::new(64, 48, [5, 6, 7]);
        c.draw_text(&font(), 20.0, 4.0, 30.0, "ab", INK);
        let bytes = c.to_png();
        assert_eq!(&bytes[..8], b"\x89PNG\r\n\x1a\n");
        let d = tempfile::tempdir().unwrap();
        let p = d.path().join("x.png");
        c.save_png(&p).unwrap();
        let back = read_png(&p).expect("reads back");
        assert_eq!((back.w, back.h), (64, 48));
        assert_eq!(&back.rgb[..3], &[5, 6, 7]);
        assert_eq!(back.rgb.len(), 64 * 48 * 3);
        // the pixels are the ones that were drawn
        for y in 0..48 {
            for x in 0..64 {
                let i = ((y * 64 + x) * 3) as usize;
                assert_eq!(&back.rgb[i..i + 3], &c.pixel(x, y), "differs at {x},{y}");
            }
        }
    }

    #[test]
    fn a_missing_or_garbage_file_does_not_read() {
        let d = tempfile::tempdir().unwrap();
        assert!(read_png(&d.path().join("nope.png")).is_none());
        let junk = d.path().join("junk.png");
        std::fs::write(&junk, b"not a png at all").unwrap();
        assert!(read_png(&junk).is_none());
    }

    // ── test_carousel_render.py ──────────────────────────────────────────────

    fn body(lines: &[&str]) -> (Geometry, Vec<Vec<Line>>) {
        let geo = geometry(1080, 1350);
        let f = font();
        let line_h = f.natural_height(geo.font_px) * LINE_HEIGHT_PCT / 100.0;
        let paras: Vec<String> = lines.iter().map(|s| s.to_string()).collect();
        let set = typeset(&f, geo.font_px, geo.block_w, geo.indent, line_h, &paras);
        (geo, paginate(set, line_h, geo.block_h))
    }

    #[test]
    fn a_body_slide_is_exactly_the_size_asked() {
        let (geo, pages) = body(&["Una linea."]);
        let c = render_body_page(&font(), &geo, &pages[0], PAPER, INK);
        assert_eq!((c.w, c.h), (1080, 1350));
    }

    #[test]
    fn a_body_slide_with_text_is_not_left_blank() {
        let (geo, pages) = body(&["Contenido real del capitulo."]);
        let c = render_body_page(&font(), &geo, &pages[0], PAPER, INK);
        assert!(!c.is_blank(PAPER));
    }

    #[test]
    fn the_default_background_is_black() {
        let (geo, pages) = body(&["Una linea."]);
        let c = render_body_page(&font(), &geo, &pages[0], PAPER, INK);
        assert_eq!(c.pixel(5, 5), [0, 0, 0]);
    }

    #[test]
    fn the_text_stays_inside_the_margins() {
        let (geo, pages) = body(&["palabra ".repeat(300).trim()]);
        let c = render_body_page(&font(), &geo, &pages[0], PAPER, INK);
        let (mx, my) = (geo.margin_side as u32 - 2, geo.margin_top as u32 - 2);
        for y in 0..c.h {
            for x in 0..c.w {
                if x < mx || x > c.w - mx || y < my {
                    assert_eq!(c.pixel(x, y), PAPER, "ink in the margin at {x},{y}");
                }
            }
        }
    }

    #[test]
    fn a_long_chapter_fills_each_slide_it_spills_onto() {
        let lines: Vec<String> = (0..120)
            .map(|i| format!("Parrafo numero {i} con texto suficiente para ocupar espacio real en la pagina."))
            .collect();
        let refs: Vec<&str> = lines.iter().map(String::as_str).collect();
        let (geo, pages) = body(&refs);
        assert!(pages.len() > 1);
        for p in &pages {
            assert!(!render_body_page(&font(), &geo, p, PAPER, INK).is_blank(PAPER));
        }
    }

    #[test]
    fn a_title_slide_is_exactly_the_size_asked() {
        let c = render_title_slide("El Titulo", &font(), 1080, 1350, 33.0, PAPER, INK);
        assert_eq!((c.w, c.h), (1080, 1350));
    }

    #[test]
    fn a_real_title_is_not_left_blank_and_an_empty_one_is() {
        assert!(!render_title_slide("El Libro de I", &font(), 1080, 1350, 33.0, PAPER, INK).is_blank(PAPER));
        assert!(render_title_slide("", &font(), 1080, 1350, 33.0, PAPER, INK).is_blank(PAPER));
    }

    #[test]
    fn the_title_slide_is_black_and_the_title_sits_in_the_middle() {
        let c = render_title_slide("TITULO", &font(), 1080, 1350, 33.0, PAPER, INK);
        assert_eq!(c.pixel(5, 5), [0, 0, 0]);
        // ink somewhere around the vertical middle, none near the top or bottom
        let band = |y0: u32, y1: u32| (y0..y1).any(|y| (0..1080).any(|x| c.pixel(x, y) != PAPER));
        assert!(band(600, 760));
        assert!(!band(0, 300));
        assert!(!band(1050, 1350));
    }

    #[test]
    fn a_long_title_wraps_inside_its_margins() {
        let title = "Un titulo muy largo que no cabe en una sola linea del slide ".repeat(3);
        let c = render_title_slide(title.trim(), &font(), 1080, 1350, 33.0, PAPER, INK);
        let m = (1080.0 * TITLE_MARGIN) as u32 - 2;
        for y in 0..1350 {
            for x in (0..m).chain(1080 - m..1080) {
                assert_eq!(c.pixel(x, y), PAPER, "title ink in the margin at {x},{y}");
            }
        }
    }

    // ── test_carousel_cover.py ───────────────────────────────────────────────

    fn source(dir: &Path, name: &str, w: u32, h: u32, colour: [u8; 3]) -> std::path::PathBuf {
        let p = dir.join(name);
        Canvas::new(w, h, colour).save_png(&p).unwrap();
        p
    }

    #[test]
    fn a_cover_is_exactly_the_size_asked() {
        let d = tempfile::tempdir().unwrap();
        let src = source(d.path(), "src.png", 400, 300, [0x20, 0x40, 0x60]);
        let c = render_cover_slide(&src, 1080, 1350, &font(), 33.0, "I", PAPER, INK);
        assert_eq!((c.w, c.h), (1080, 1350));
    }

    #[test]
    fn a_taller_source_still_gives_the_right_size() {
        let d = tempfile::tempdir().unwrap();
        let src = source(d.path(), "tall.png", 200, 900, [0x20, 0x40, 0x60]);
        let c = render_cover_slide(&src, 1080, 1080, &font(), 33.0, "I", PAPER, INK);
        assert_eq!((c.w, c.h), (1080, 1080));
    }

    #[test]
    fn the_picture_fills_the_frame_without_distortion() {
        // A source half red, half blue (left/right) cropped to a wide frame keeps
        // both halves in place: the left edge stays red, the right edge blue.
        let d = tempfile::tempdir().unwrap();
        let mut src = Canvas::new(100, 100, [200, 0, 0]);
        for y in 0..100 {
            for x in 50..100 {
                src.set_pixel(x, y, [0, 0, 200]);
            }
        }
        let p = d.path().join("two.png");
        src.save_png(&p).unwrap();
        let c = render_cover_slide(&p, 400, 200, &font(), 20.0, "", PAPER, INK);
        assert_eq!(c.pixel(2, 100)[0] > 150, true); // left: red
        assert_eq!(c.pixel(397, 100)[2] > 150, true); // right: blue
        assert!(c.pixel(2, 100)[2] < 50 && c.pixel(397, 100)[0] < 50);
    }

    #[test]
    fn a_missing_picture_falls_back_without_crashing() {
        let d = tempfile::tempdir().unwrap();
        let c = render_cover_slide(&d.path().join("nope.png"), 1080, 1350, &font(), 33.0, "I", PAPER, INK);
        assert_eq!((c.w, c.h), (1080, 1350));
        assert_eq!(c.pixel(5, 5), PAPER);
    }

    #[test]
    fn the_mark_is_actually_drawn_over_the_picture() {
        let d = tempfile::tempdir().unwrap();
        let src = source(d.path(), "black.png", 1080, 1350, [0, 0, 0]);
        let c = render_cover_slide(&src, 1080, 1350, &font(), 33.0, "I", PAPER, INK);
        assert!(!c.is_blank([0, 0, 0]), "the mark did not draw");
        let at_centre = (500..580).any(|x| (640..710).any(|y| c.pixel(x, y) != [0, 0, 0]));
        assert!(at_centre, "the mark should sit in the middle");
    }
}

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

    /// The pixels, row by row, three bytes each (R, G, B).
    pub fn rgb(&self) -> &[u8] {
        &self.rgb
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

/// Read an image whatever it is — PNG or JPEG, told apart by what is IN the file, not
/// by its name — flattened to RGB. `None` for anything missing or unreadable.
pub fn read_image(path: &Path) -> Option<Image> {
    let bytes = std::fs::read(path).ok()?;
    if bytes.starts_with(b"\x89PNG") {
        read_png(path)
    } else if bytes.starts_with(&[0xFF, 0xD8]) {
        decode_jpeg(&bytes)
    } else {
        None
    }
}

/// A JPEG, grey or colour, as RGB. CMYK and 16-bit ones are not read.
fn decode_jpeg(bytes: &[u8]) -> Option<Image> {
    let mut decoder = jpeg_decoder::Decoder::new(std::io::Cursor::new(bytes));
    let pixels = decoder.decode().ok()?;
    let info = decoder.info()?;
    let rgb: Vec<u8> = match info.pixel_format {
        jpeg_decoder::PixelFormat::RGB24 => pixels,
        jpeg_decoder::PixelFormat::L8 => pixels.iter().flat_map(|&g| [g, g, g]).collect(),
        _ => return None,
    };
    if rgb.len() != info.width as usize * info.height as usize * 3 {
        return None;
    }
    Some(Image { w: info.width as u32, h: info.height as u32, rgb })
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
    if let Some(src) = read_image(image_path).filter(|s| s.w > 0 && s.h > 0) {
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

/// One slide of a carousel, before it is drawn.
#[derive(Debug, Clone, PartialEq)]
pub enum Slide {
    /// A chapter's title, alone on its slide.
    Title(String),
    /// One page of a chapter's body.
    Body(Vec<Line>),
}

/// Every slide a set of sections makes, in order: each chapter's title slide and
/// then its body pages, set for a `w` × `h` frame. This is the ONE place that
/// decides what a carousel is, so the on-screen preview and the files written to
/// disk cannot disagree.
pub fn plan(sections: &[(String, Vec<String>)], font: &TypeFont, w: u32, h: u32) -> Vec<Slide> {
    let geo = crate::carousel::geometry_for(font, w, h);
    let line_h = leading(font, geo.font_px);
    let mut out = Vec::new();
    for (name, lines) in sections {
        // The title has a slide of its own; the body starts on the next one.
        out.push(Slide::Title(name.clone()));
        let paragraphs = crate::reformat::lines_to_paragraphs(lines);
        let set = crate::typeset::typeset(font, geo.font_px, geo.block_w, geo.indent, line_h, &paragraphs);
        for page in crate::typeset::paginate(set, line_h, geo.block_h) {
            out.push(Slide::Body(page));
        }
    }
    out
}


/// Draw one slide of a plan onto a `w` × `h` canvas.
pub fn render_slide(slide: &Slide, font: &TypeFont, w: u32, h: u32) -> Canvas {
    let geo = crate::carousel::geometry_for(font, w, h);
    match slide {
        Slide::Title(title) => render_title_slide(title, font, w, h, geo.font_px, PAPER, INK),
        Slide::Body(lines) => render_body_page(font, &geo, lines, PAPER, INK),
    }
}


// ── the book page, as F4 shows it ──────────────────────────────────────────

/// F4's page is white paper with near-black ink, like the printed book.
pub const BOOK_PAPER: [u8; 3] = [255, 255, 255];
pub const BOOK_INK: [u8; 3] = [17, 17, 17];

/// A chapter title: 1.5 × the body type, sunk 24 mm below the top of the text
/// block, with 12 mm under it (`build_reading_document`).
pub const BOOK_TITLE_SCALE: f32 = 1.5;
pub const TITLE_SINK_MM: f32 = 24.0;
pub const TITLE_BOTTOM_MM: f32 = 12.0;

/// One page of the book.
#[derive(Debug, Clone, PartialEq)]
pub struct BookPage {
    /// The chapter title, on the first page of its chapter only.
    pub title: Option<String>,
    pub lines: Vec<Line>,
}

/// Every page of the book, and the page each paragraph (counted across all the
/// chapters, in order) begins on.
#[derive(Debug, Clone, PartialEq)]
pub struct BookPlan {
    pub pages: Vec<BookPage>,
    pub para_page: Vec<usize>,
}

/// Set the sections as a book for a `w` × `h` page (an A5 page's proportions): each
/// chapter opens a new page with its title sunk into it, then its paragraphs,
/// justified.
pub fn book_plan(sections: &[(String, Vec<String>)], font: &TypeFont, w: u32, h: u32) -> BookPlan {
    let geo = crate::carousel::geometry_for(font, w, h);
    let line_h = leading(font, geo.font_px);
    let mut plan = BookPlan { pages: Vec::new(), para_page: Vec::new() };
    for (name, lines) in sections {
        let paragraphs = crate::reformat::lines_to_paragraphs(lines);
        let (set, starts) =
            crate::typeset::typeset_marked(font, geo.font_px, geo.block_w, geo.indent, line_h, &paragraphs);
        // The title sinks into the top of the chapter's first page and takes room from it.
        let title = (!name.is_empty()).then(|| name.clone());
        let first_h = match &title {
            Some(t) => (geo.block_h - title_block_h(font, &geo, t)).max(0.0),
            None => geo.block_h,
        };
        let (first_n, per_n) = (
            crate::typeset::lines_that_fit(first_h, line_h),
            crate::typeset::lines_that_fit(geo.block_h, line_h),
        );
        let base = plan.pages.len();
        for (i, page_lines) in crate::typeset::paginate_first(set, line_h, first_h, geo.block_h).into_iter().enumerate() {
            plan.pages.push(BookPage { title: if i == 0 { title.clone() } else { None }, lines: page_lines });
        }
        plan.para_page
            .extend(starts.into_iter().map(|l| base + crate::typeset::page_of_line(l, first_n, per_n)));
    }
    plan
}

/// The title's lines, wrapped to the text block at the title's size.
fn title_lines(font: &TypeFont, geo: &Geometry, title: &str) -> Vec<String> {
    wrap_for_centering(font, geo.font_px * BOOK_TITLE_SCALE, geo.block_w, title)
}

/// The room a title takes at the top of its page: the sink above it, its own
/// lines, and the space under it.
fn title_block_h(font: &TypeFont, geo: &Geometry, title: &str) -> f32 {
    let px = geo.font_px * BOOK_TITLE_SCALE;
    let mm = |v: f32| crate::carousel::mm_to_pt(v) * geo.scale;
    mm(TITLE_SINK_MM) + title_lines(font, geo, title).len() as f32 * font.natural_height(px) + mm(TITLE_BOTTOM_MM)
}


/// One piece of set text on a page: what, where its left edge and baseline
/// fall (pixels of the `w` × `h` page), and at what size.
#[derive(Debug, Clone, PartialEq)]
pub struct Run {
    pub text: String,
    pub x: f32,
    pub baseline: f32,
    pub px: f32,
}

/// Every piece of text one page of a book plan puts down, in place. The screen
/// rasterises these; the PDF writes them as text — so the two can't differ.
pub fn book_page_runs(page: &BookPage, font: &TypeFont, w: u32, h: u32) -> Vec<Run> {
    let geo = crate::carousel::geometry_for(font, w, h);
    let mut runs = Vec::new();
    let mut body_top = 0.0;
    if let Some(title) = &page.title {
        let px = geo.font_px * BOOK_TITLE_SCALE;
        let mm = |v: f32| crate::carousel::mm_to_pt(v) * geo.scale;
        let tl_h = font.natural_height(px);
        let centre = geo.margin_side + geo.block_w / 2.0;
        let top = geo.margin_top + mm(TITLE_SINK_MM);
        for (i, line) in title_lines(font, &geo, title).iter().enumerate() {
            let x = centre - font.advance(line, px) / 2.0;
            runs.push(Run { text: line.clone(), x, baseline: top + i as f32 * tl_h + font.ascent(px), px });
        }
        body_top = title_block_h(font, &geo, title);
    }
    let line_h = leading(font, geo.font_px);
    let pad = (line_h - font.natural_height(geo.font_px)) / 2.0;
    for line in &page.lines {
        let baseline = geo.margin_top + body_top + line.y + pad + font.ascent(geo.font_px);
        for word in &line.words {
            runs.push(Run { text: word.text.clone(), x: geo.margin_side + word.x, baseline, px: geo.font_px });
        }
    }
    runs
}

/// Draw one page of a book plan onto a `w` × `h` canvas.
pub fn render_book_page(page: &BookPage, font: &TypeFont, w: u32, h: u32, paper: [u8; 3], ink: [u8; 3]) -> Canvas {
    let mut canvas = Canvas::new(w, h, paper);
    for run in book_page_runs(page, font, w, h) {
        canvas.draw_text(font, run.px, run.x, run.baseline, &run.text, ink);
    }
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

    // ── the book page (what F4 shows) ────────────────────────────────────────

    fn book(sections: &[(&str, &[&str])]) -> BookPlan {
        let s: Vec<(String, Vec<String>)> = sections.iter().map(|(t, ls)| (t.to_string(), ls.iter().map(|l| l.to_string()).collect())).collect();
        book_plan(&s, &font(), 504, 715)
    }

    fn long(n: usize) -> Vec<String> {
        (0..n).flat_map(|i| [format!("Parrafo numero {i} con texto suficiente para ocupar espacio real en la pagina de verdad."), ".".to_string()]).collect()
    }

    #[test]
    fn a_short_chapter_is_one_page_with_its_title() {
        let p = book(&[("Uno", &[".", "Un parrafo corto."])]);
        assert_eq!(p.pages.len(), 1);
        assert_eq!(p.pages[0].title.as_deref(), Some("Uno"));
        assert_eq!(p.para_page, vec![0]);
    }

    #[test]
    fn only_the_first_page_of_a_chapter_carries_the_title() {
        let lines = long(60);
        let refs: Vec<&str> = lines.iter().map(String::as_str).collect();
        let p = book(&[("Largo", &refs)]);
        assert!(p.pages.len() > 2);
        assert_eq!(p.pages[0].title.as_deref(), Some("Largo"));
        assert!(p.pages[1..].iter().all(|pg| pg.title.is_none()));
    }

    #[test]
    fn the_titled_first_page_holds_fewer_lines_than_the_ones_after_it() {
        let lines = long(60);
        let refs: Vec<&str> = lines.iter().map(String::as_str).collect();
        let p = book(&[("Largo", &refs)]);
        assert!(p.pages[0].lines.len() < p.pages[1].lines.len(), "{} vs {}", p.pages[0].lines.len(), p.pages[1].lines.len());
    }

    #[test]
    fn a_chapter_with_no_title_gets_the_whole_page() {
        let lines = long(60);
        let refs: Vec<&str> = lines.iter().map(String::as_str).collect();
        let p = book(&[("", &refs)]);
        assert!(p.pages[0].title.is_none());
        assert_eq!(p.pages[0].lines.len(), p.pages[1].lines.len());
    }

    #[test]
    fn each_chapter_opens_a_new_page_with_its_own_title() {
        let p = book(&[("Uno", &[".", "a."]), ("Dos", &[".", "b."])]);
        assert_eq!(p.pages.len(), 2);
        assert_eq!(p.pages[0].title.as_deref(), Some("Uno"));
        assert_eq!(p.pages[1].title.as_deref(), Some("Dos"));
        assert_eq!(p.para_page, vec![0, 1]); // one paragraph in each, counted across both
    }

    #[test]
    fn a_paragraph_is_mapped_to_the_page_it_starts_on() {
        let lines = long(60);
        let refs: Vec<&str> = lines.iter().map(String::as_str).collect();
        let p = book(&[("Largo", &refs)]);
        assert_eq!(p.para_page.len(), 60);
        assert_eq!(p.para_page[0], 0);
        assert!(p.para_page.windows(2).all(|w| w[0] <= w[1]), "pages go forward");
        assert!(*p.para_page.last().unwrap() > 0 && *p.para_page.last().unwrap() < p.pages.len());
        // the page it says the paragraph starts on does hold that paragraph's opening words
        for (n, &page) in p.para_page.iter().enumerate() {
            let needle = format!("numero {n} ");
            let text: String = p.pages[page].lines.iter().map(|l| l.text()).collect::<Vec<_>>().join(" ");
            assert!(text.contains(&needle) || text.contains(&format!("Parrafo numero {n}")), "paragraph {n} not on page {page}");
        }
    }

    #[test]
    fn an_empty_chapter_is_still_a_page_with_its_title() {
        let p = book(&[("Vacio", &["."])]);
        assert_eq!(p.pages.len(), 1);
        assert_eq!(p.pages[0].title.as_deref(), Some("Vacio"));
        assert!(p.para_page.is_empty());
    }

    #[test]
    fn no_sections_is_no_pages() {
        let p = book(&[]);
        assert!(p.pages.is_empty() && p.para_page.is_empty());
    }

    #[test]
    fn a_book_page_is_white_paper_with_dark_ink_at_the_size_asked() {
        let p = book(&[("Uno", &[".", "Un parrafo del capitulo, con texto."])]);
        let c = render_book_page(&p.pages[0], &font(), 504, 715, BOOK_PAPER, BOOK_INK);
        assert_eq!((c.w, c.h), (504, 715));
        assert_eq!(c.pixel(5, 5), [255, 255, 255]);
        assert!(!c.is_blank(BOOK_PAPER));
        // ink is dark, never lighter than the paper by accident: some pixel is near the ink colour
        let darkest = (0..715).flat_map(|y| (0..504).map(move |x| (x, y))).map(|(x, y)| c.pixel(x, y)[0]).min().unwrap();
        assert!(darkest < 60, "the darkest pixel is {darkest}");
    }

    #[test]
    fn the_title_sits_above_the_body_and_centred() {
        let p = book(&[("TITULO", &[".", "Un parrafo del capitulo, con texto."])]);
        let c = render_book_page(&p.pages[0], &font(), 504, 715, BOOK_PAPER, BOOK_INK);
        let rows_with_ink: Vec<u32> = (0..715).filter(|&y| (0..504).any(|x| c.pixel(x, y) != BOOK_PAPER)).collect();
        // nothing in the top margin plus the sink
        let first = *rows_with_ink.first().unwrap();
        assert!(first > 60, "ink starts at {first}, inside the margin/sink");
        // the title's ink is centred horizontally
        let title_rows: Vec<u32> = rows_with_ink.iter().copied().filter(|&y| y < first + 20).collect();
        let cr = &c;
        let xs: Vec<u32> = title_rows.iter().flat_map(|&y| (0..504).filter(move |&x| cr.pixel(x, y) != BOOK_PAPER)).collect();
        let (lo, hi) = (*xs.iter().min().unwrap(), *xs.iter().max().unwrap());
        assert!(((lo + hi) as i32 - 504).abs() < 14, "title spans {lo}..{hi}");
    }

    #[test]
    fn a_page_without_a_title_starts_its_text_right_at_the_top_margin() {
        let p = book(&[("", &[".", "Un parrafo del capitulo, con texto."])]);
        let titled = book(&[("X", &[".", "Un parrafo del capitulo, con texto."])]);
        let a = render_book_page(&p.pages[0], &font(), 504, 715, BOOK_PAPER, BOOK_INK);
        let b = render_book_page(&titled.pages[0], &font(), 504, 715, BOOK_PAPER, BOOK_INK);
        let first_ink = |c: &Canvas| (0..715).find(|&y| (0..504).any(|x| c.pixel(x, y) != BOOK_PAPER)).unwrap();
        assert!(first_ink(&a) < first_ink(&b), "the sunk title pushes the text down");
    }

    // ── the plan: what a carousel is, shared by the preview and the export ───

    fn sec(name: &str, lines: &[&str]) -> (String, Vec<String>) {
        (name.to_string(), lines.iter().map(|l| l.to_string()).collect())
    }

    fn kinds(plan: &[Slide]) -> Vec<&'static str> {
        plan.iter().map(|s| match s { Slide::Title(_) => "title", Slide::Body(_) => "body" }).collect()
    }

    #[test]
    fn a_chapter_is_its_title_slide_and_then_its_body() {
        let p = plan(&[sec("Uno", &[".", "Un parrafo corto."])], &font(), 1080, 1350);
        assert_eq!(kinds(&p), vec!["title", "body"]);
        assert_eq!(p[0], Slide::Title("Uno".into()));
    }

    #[test]
    fn several_chapters_each_get_their_own_title_slide_in_order() {
        let p = plan(&[sec("Uno", &[".", "a."]), sec("Dos", &[".", "b."])], &font(), 1080, 1350);
        assert_eq!(kinds(&p), vec!["title", "body", "title", "body"]);
        assert_eq!(p[2], Slide::Title("Dos".into()));
    }

    #[test]
    fn a_long_chapter_spills_onto_several_body_slides() {
        let lines: Vec<String> = (0..120)
            .flat_map(|i| [format!("Parrafo numero {i} con texto suficiente para ocupar espacio real en la pagina."), ".".to_string()])
            .collect();
        let refs: Vec<&str> = lines.iter().map(String::as_str).collect();
        let p = plan(&[sec("Largo", &refs)], &font(), 1080, 1350);
        assert!(kinds(&p).iter().filter(|k| **k == "body").count() > 1);
        assert_eq!(kinds(&p)[0], "title");
    }

    #[test]
    fn a_wider_frame_fits_fewer_lines_per_slide_so_more_slides() {
        let lines: Vec<String> = (0..60).map(|i| format!("Parrafo numero {i} con texto suficiente para ocupar espacio real en la pagina.")).collect();
        let refs: Vec<&str> = lines.iter().map(String::as_str).collect();
        let tall = plan(&[sec("L", &refs)], &font(), 1080, 1350).len();
        let short = plan(&[sec("L", &refs)], &font(), 1080, 566).len();
        assert!(short > tall, "{short} slides at 1.91:1 vs {tall} at 4:5");
    }

    #[test]
    fn no_sections_is_no_slides_and_an_empty_chapter_is_a_title_and_a_blank_body() {
        assert!(plan(&[], &font(), 1080, 1350).is_empty());
        let p = plan(&[sec("Vacio", &["."])], &font(), 1080, 1350);
        assert_eq!(kinds(&p), vec!["title", "body"]);
    }

    #[test]
    fn rendering_a_plan_gives_slides_of_the_frames_size() {
        let p = plan(&[sec("Uno", &[".", "Un parrafo."])], &font(), 800, 600);
        for slide in &p {
            let c = render_slide(slide, &font(), 800, 600);
            assert_eq!((c.w, c.h), (800, 600));
            assert!(!c.is_blank(PAPER));
        }
    }

    #[test]
    fn a_title_slide_renders_as_the_title_slide_does() {
        let f = font();
        let geo = geometry(1080, 1350);
        let a = render_slide(&Slide::Title("Titulo".into()), &f, 1080, 1350);
        let b = render_title_slide("Titulo", &f, 1080, 1350, geo.font_px, PAPER, INK);
        assert_eq!(a.to_png(), b.to_png());
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

    // ── JPEG covers ───────────────────────────────────────────────────────────

    /// 32 × 16, the left half red and the right half blue (quality 95, 4:4:4).
    const RED_BLUE_JPG: &[u8] = &[0xff, 0xd8, 0xff, 0xe0, 0x00, 0x10, 0x4a, 0x46, 0x49, 0x46, 0x00, 0x01, 0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xff, 0xdb, 0x00, 0x43, 0x00, 0x02, 0x01, 0x01, 0x01, 0x01, 0x01, 0x02, 0x01, 0x01, 0x01, 0x02, 0x02, 0x02, 0x02, 0x02, 0x04, 0x03, 0x02, 0x02, 0x02, 0x02, 0x05, 0x04, 0x04, 0x03, 0x04, 0x06, 0x05, 0x06, 0x06, 0x06, 0x05, 0x06, 0x06, 0x06, 0x07, 0x09, 0x08, 0x06, 0x07, 0x09, 0x07, 0x06, 0x06, 0x08, 0x0b, 0x08, 0x09, 0x0a, 0x0a, 0x0a, 0x0a, 0x0a, 0x06, 0x08, 0x0b, 0x0c, 0x0b, 0x0a, 0x0c, 0x09, 0x0a, 0x0a, 0x0a, 0xff, 0xdb, 0x00, 0x43, 0x01, 0x02, 0x02, 0x02, 0x02, 0x02, 0x02, 0x05, 0x03, 0x03, 0x05, 0x0a, 0x07, 0x06, 0x07, 0x0a, 0x0a, 0x0a, 0x0a, 0x0a, 0x0a, 0x0a, 0x0a, 0x0a, 0x0a, 0x0a, 0x0a, 0x0a, 0x0a, 0x0a, 0x0a, 0x0a, 0x0a, 0x0a, 0x0a, 0x0a, 0x0a, 0x0a, 0x0a, 0x0a, 0x0a, 0x0a, 0x0a, 0x0a, 0x0a, 0x0a, 0x0a, 0x0a, 0x0a, 0x0a, 0x0a, 0x0a, 0x0a, 0x0a, 0x0a, 0x0a, 0x0a, 0x0a, 0x0a, 0x0a, 0x0a, 0x0a, 0x0a, 0x0a, 0x0a, 0xff, 0xc0, 0x00, 0x11, 0x08, 0x00, 0x10, 0x00, 0x20, 0x03, 0x01, 0x11, 0x00, 0x02, 0x11, 0x01, 0x03, 0x11, 0x01, 0xff, 0xc4, 0x00, 0x1f, 0x00, 0x00, 0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b, 0xff, 0xc4, 0x00, 0xb5, 0x10, 0x00, 0x02, 0x01, 0x03, 0x03, 0x02, 0x04, 0x03, 0x05, 0x05, 0x04, 0x04, 0x00, 0x00, 0x01, 0x7d, 0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12, 0x21, 0x31, 0x41, 0x06, 0x13, 0x51, 0x61, 0x07, 0x22, 0x71, 0x14, 0x32, 0x81, 0x91, 0xa1, 0x08, 0x23, 0x42, 0xb1, 0xc1, 0x15, 0x52, 0xd1, 0xf0, 0x24, 0x33, 0x62, 0x72, 0x82, 0x09, 0x0a, 0x16, 0x17, 0x18, 0x19, 0x1a, 0x25, 0x26, 0x27, 0x28, 0x29, 0x2a, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3a, 0x43, 0x44, 0x45, 0x46, 0x47, 0x48, 0x49, 0x4a, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59, 0x5a, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69, 0x6a, 0x73, 0x74, 0x75, 0x76, 0x77, 0x78, 0x79, 0x7a, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89, 0x8a, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9a, 0xa2, 0xa3, 0xa4, 0xa5, 0xa6, 0xa7, 0xa8, 0xa9, 0xaa, 0xb2, 0xb3, 0xb4, 0xb5, 0xb6, 0xb7, 0xb8, 0xb9, 0xba, 0xc2, 0xc3, 0xc4, 0xc5, 0xc6, 0xc7, 0xc8, 0xc9, 0xca, 0xd2, 0xd3, 0xd4, 0xd5, 0xd6, 0xd7, 0xd8, 0xd9, 0xda, 0xe1, 0xe2, 0xe3, 0xe4, 0xe5, 0xe6, 0xe7, 0xe8, 0xe9, 0xea, 0xf1, 0xf2, 0xf3, 0xf4, 0xf5, 0xf6, 0xf7, 0xf8, 0xf9, 0xfa, 0xff, 0xc4, 0x00, 0x1f, 0x01, 0x00, 0x03, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b, 0xff, 0xc4, 0x00, 0xb5, 0x11, 0x00, 0x02, 0x01, 0x02, 0x04, 0x04, 0x03, 0x04, 0x07, 0x05, 0x04, 0x04, 0x00, 0x01, 0x02, 0x77, 0x00, 0x01, 0x02, 0x03, 0x11, 0x04, 0x05, 0x21, 0x31, 0x06, 0x12, 0x41, 0x51, 0x07, 0x61, 0x71, 0x13, 0x22, 0x32, 0x81, 0x08, 0x14, 0x42, 0x91, 0xa1, 0xb1, 0xc1, 0x09, 0x23, 0x33, 0x52, 0xf0, 0x15, 0x62, 0x72, 0xd1, 0x0a, 0x16, 0x24, 0x34, 0xe1, 0x25, 0xf1, 0x17, 0x18, 0x19, 0x1a, 0x26, 0x27, 0x28, 0x29, 0x2a, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3a, 0x43, 0x44, 0x45, 0x46, 0x47, 0x48, 0x49, 0x4a, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59, 0x5a, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69, 0x6a, 0x73, 0x74, 0x75, 0x76, 0x77, 0x78, 0x79, 0x7a, 0x82, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89, 0x8a, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9a, 0xa2, 0xa3, 0xa4, 0xa5, 0xa6, 0xa7, 0xa8, 0xa9, 0xaa, 0xb2, 0xb3, 0xb4, 0xb5, 0xb6, 0xb7, 0xb8, 0xb9, 0xba, 0xc2, 0xc3, 0xc4, 0xc5, 0xc6, 0xc7, 0xc8, 0xc9, 0xca, 0xd2, 0xd3, 0xd4, 0xd5, 0xd6, 0xd7, 0xd8, 0xd9, 0xda, 0xe2, 0xe3, 0xe4, 0xe5, 0xe6, 0xe7, 0xe8, 0xe9, 0xea, 0xf2, 0xf3, 0xf4, 0xf5, 0xf6, 0xf7, 0xf8, 0xf9, 0xfa, 0xff, 0xda, 0x00, 0x0c, 0x03, 0x01, 0x00, 0x02, 0x11, 0x03, 0x11, 0x00, 0x3f, 0x00, 0xf8, 0x9e, 0xbf, 0x07, 0x3f, 0xd6, 0x80, 0xa0, 0x0f, 0x9e, 0xeb, 0xfd, 0xe0, 0x3f, 0xc5, 0xb0, 0xa0, 0x0f, 0xa1, 0x2b, 0xfc, 0x1f, 0x3f, 0xda, 0x40, 0xa0, 0x0f, 0x9e, 0xeb, 0xfd, 0xe0, 0x3f, 0xc5, 0xb0, 0xa0, 0x0f, 0xff, 0xd9];
    /// 16 × 16, flat mid-grey, a single-channel JPEG.
    const GREY_JPG: &[u8] = &[0xff, 0xd8, 0xff, 0xe0, 0x00, 0x10, 0x4a, 0x46, 0x49, 0x46, 0x00, 0x01, 0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xff, 0xdb, 0x00, 0x43, 0x00, 0x02, 0x01, 0x01, 0x01, 0x01, 0x01, 0x02, 0x01, 0x01, 0x01, 0x02, 0x02, 0x02, 0x02, 0x02, 0x04, 0x03, 0x02, 0x02, 0x02, 0x02, 0x05, 0x04, 0x04, 0x03, 0x04, 0x06, 0x05, 0x06, 0x06, 0x06, 0x05, 0x06, 0x06, 0x06, 0x07, 0x09, 0x08, 0x06, 0x07, 0x09, 0x07, 0x06, 0x06, 0x08, 0x0b, 0x08, 0x09, 0x0a, 0x0a, 0x0a, 0x0a, 0x0a, 0x06, 0x08, 0x0b, 0x0c, 0x0b, 0x0a, 0x0c, 0x09, 0x0a, 0x0a, 0x0a, 0xff, 0xc0, 0x00, 0x0b, 0x08, 0x00, 0x10, 0x00, 0x10, 0x01, 0x01, 0x11, 0x00, 0xff, 0xc4, 0x00, 0x1f, 0x00, 0x00, 0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b, 0xff, 0xc4, 0x00, 0xb5, 0x10, 0x00, 0x02, 0x01, 0x03, 0x03, 0x02, 0x04, 0x03, 0x05, 0x05, 0x04, 0x04, 0x00, 0x00, 0x01, 0x7d, 0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12, 0x21, 0x31, 0x41, 0x06, 0x13, 0x51, 0x61, 0x07, 0x22, 0x71, 0x14, 0x32, 0x81, 0x91, 0xa1, 0x08, 0x23, 0x42, 0xb1, 0xc1, 0x15, 0x52, 0xd1, 0xf0, 0x24, 0x33, 0x62, 0x72, 0x82, 0x09, 0x0a, 0x16, 0x17, 0x18, 0x19, 0x1a, 0x25, 0x26, 0x27, 0x28, 0x29, 0x2a, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3a, 0x43, 0x44, 0x45, 0x46, 0x47, 0x48, 0x49, 0x4a, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59, 0x5a, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69, 0x6a, 0x73, 0x74, 0x75, 0x76, 0x77, 0x78, 0x79, 0x7a, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89, 0x8a, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9a, 0xa2, 0xa3, 0xa4, 0xa5, 0xa6, 0xa7, 0xa8, 0xa9, 0xaa, 0xb2, 0xb3, 0xb4, 0xb5, 0xb6, 0xb7, 0xb8, 0xb9, 0xba, 0xc2, 0xc3, 0xc4, 0xc5, 0xc6, 0xc7, 0xc8, 0xc9, 0xca, 0xd2, 0xd3, 0xd4, 0xd5, 0xd6, 0xd7, 0xd8, 0xd9, 0xda, 0xe1, 0xe2, 0xe3, 0xe4, 0xe5, 0xe6, 0xe7, 0xe8, 0xe9, 0xea, 0xf1, 0xf2, 0xf3, 0xf4, 0xf5, 0xf6, 0xf7, 0xf8, 0xf9, 0xfa, 0xff, 0xda, 0x00, 0x08, 0x01, 0x01, 0x00, 0x00, 0x3f, 0x00, 0x28, 0xa2, 0x8a, 0xff, 0xd9];

    fn write(dir: &Path, name: &str, bytes: &[u8]) -> std::path::PathBuf {
        let p = dir.join(name);
        std::fs::write(&p, bytes).unwrap();
        p
    }

    fn near(a: [u8; 3], b: [u8; 3], tol: i32) -> bool {
        (0..3).all(|k| (a[k] as i32 - b[k] as i32).abs() <= tol)
    }

    fn px(img: &Image, x: u32, y: u32) -> [u8; 3] {
        let i = ((y * img.w + x) * 3) as usize;
        [img.rgb[i], img.rgb[i + 1], img.rgb[i + 2]]
    }

    #[test]
    fn a_jpeg_is_read_with_its_size_and_colours() {
        let d = tempfile::tempdir().unwrap();
        let img = read_image(&write(d.path(), "a.jpg", RED_BLUE_JPG)).expect("a JPEG reads");
        assert_eq!((img.w, img.h), (32, 16));
        assert_eq!(img.rgb.len(), 32 * 16 * 3);
        assert!(near(px(&img, 4, 8), [200, 20, 20], 14), "{:?}", px(&img, 4, 8));
        assert!(near(px(&img, 28, 8), [20, 20, 200], 14), "{:?}", px(&img, 28, 8));
    }

    #[test]
    fn a_grey_jpeg_becomes_rgb() {
        let d = tempfile::tempdir().unwrap();
        let img = read_image(&write(d.path(), "g.jpeg", GREY_JPG)).expect("a grey JPEG reads");
        assert_eq!((img.w, img.h), (16, 16));
        let p = px(&img, 8, 8);
        assert!(p[0] == p[1] && p[1] == p[2] && (p[0] as i32 - 128).abs() <= 4, "{p:?}");
    }

    #[test]
    fn the_format_is_told_by_the_content_not_the_name() {
        let d = tempfile::tempdir().unwrap();
        // a JPEG called .png, and a PNG called .jpg: both still read
        assert!(read_image(&write(d.path(), "engano.png", RED_BLUE_JPG)).is_some());
        let png = d.path().join("real.jpg");
        Canvas::new(8, 8, [1, 2, 3]).save_png(&png).unwrap();
        assert_eq!(read_image(&png).map(|i| (i.w, i.h)), Some((8, 8)));
    }

    #[test]
    fn png_still_reads_and_junk_does_not() {
        let d = tempfile::tempdir().unwrap();
        let p = d.path().join("x.png");
        Canvas::new(5, 4, [9, 9, 9]).save_png(&p).unwrap();
        assert_eq!(read_image(&p).map(|i| (i.w, i.h)), Some((5, 4)));
        assert!(read_image(&write(d.path(), "junk.jpg", b"not an image")).is_none());
        assert!(read_image(&write(d.path(), "cut.jpg", &RED_BLUE_JPG[..40])).is_none(), "a truncated JPEG");
        assert!(read_image(&d.path().join("nope.jpg")).is_none());
        assert!(read_image(&write(d.path(), "empty.jpg", b"")).is_none());
    }

    #[test]
    fn a_jpeg_cover_fills_the_frame_like_a_png_one() {
        let d = tempfile::tempdir().unwrap();
        let src = write(d.path(), "portada.jpg", RED_BLUE_JPG);
        let c = render_cover_slide(&src, 400, 200, &font(), 20.0, "", PAPER, INK);
        assert_eq!((c.w, c.h), (400, 200));
        assert!(c.pixel(2, 100)[0] > 150 && c.pixel(2, 100)[2] < 70, "left edge should be red");
        assert!(c.pixel(397, 100)[2] > 150 && c.pixel(397, 100)[0] < 70, "right edge should be blue");
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

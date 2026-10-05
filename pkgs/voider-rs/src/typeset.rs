//! Setting text in a column: measuring, breaking into lines, justifying and
//! paginating — what `QTextDocument` did for the Python's carousel, done by hand.
//!
//! The slides are PNGs, and nothing here may touch a window or a GPU: the font is
//! read with `ab_glyph` and a line is just words and the x each one starts at.
//! Paragraphs are set the book's way: justified, every first line indented, no
//! blank line between them.

#![allow(dead_code)]

use ab_glyph::{Font, FontArc, PxScale, ScaleFont};

/// A font, ready to measure.
#[derive(Clone)]
pub struct TypeFont {
    font: FontArc,
}

impl TypeFont {
    /// The writing font if it can be found on this machine; otherwise the plain
    /// face egui ships with, so a slide can always be drawn.
    pub fn load(family: &str) -> TypeFont {
        if let Some(font) = crate::fonts::load_family(family).and_then(TypeFont::from_bytes) {
            return font;
        }
        // egui carries a plain face of its own; it is what draws the interface
        // when no font was found, and it is always there.
        let defs = egui::FontDefinitions::default();
        let data = defs
            .font_data
            .get("Ubuntu-Light")
            .or_else(|| defs.font_data.values().next())
            .expect("egui ships at least one font");
        TypeFont::from_bytes(data.font.to_vec()).expect("egui's own font is valid")
    }

    pub fn from_bytes(bytes: Vec<u8>) -> Option<TypeFont> {
        FontArc::try_from_vec(bytes).ok().map(|font| TypeFont { font })
    }

    pub(crate) fn font(&self) -> &FontArc {
        &self.font
    }

    /// The width of `text` set at `px`, kerning included.
    pub fn advance(&self, text: &str, px: f32) -> f32 {
        let scaled = self.font.as_scaled(PxScale::from(px));
        let mut width = 0.0;
        let mut prev = None;
        for c in text.chars() {
            let g = scaled.glyph_id(c);
            if let Some(p) = prev {
                width += scaled.kern(p, g);
            }
            width += scaled.h_advance(g);
            prev = Some(g);
        }
        width
    }

    /// The font's own line height at `px` (ascent + descent + gap).
    pub fn natural_height(&self, px: f32) -> f32 {
        let scaled = self.font.as_scaled(PxScale::from(px));
        scaled.height() + scaled.line_gap()
    }

    pub fn ascent(&self, px: f32) -> f32 {
        self.font.as_scaled(PxScale::from(px)).ascent()
    }
}

/// A word and where it starts, from the left edge of the text block.
#[derive(Debug, Clone, PartialEq)]
pub struct Placed {
    pub text: String,
    pub x: f32,
}

/// One set line. `y` is the line's top, from the top of the text block.
#[derive(Debug, Clone, PartialEq)]
pub struct Line {
    pub words: Vec<Placed>,
    pub y: f32,
}

impl Line {
    pub fn text(&self) -> String {
        self.words.iter().map(|w| w.text.as_str()).collect::<Vec<_>>().join(" ")
    }
}

/// Set `paragraphs` into a column `width` wide at `px`: every first line indented
/// by `indent`, lines `line_h` apart, all justified but the last of each
/// paragraph. A word wider than the column is broken so nothing runs out of it.
pub fn typeset(
    font: &TypeFont,
    px: f32,
    width: f32,
    indent: f32,
    line_h: f32,
    paragraphs: &[String],
) -> Vec<Line> {
    let space = font.advance(" ", px);
    let mut lines: Vec<Line> = Vec::new();

    for para in paragraphs {
        let words: Vec<String> = para
            .split_whitespace()
            .flat_map(|w| split_to_fit(font, px, width, w))
            .collect();
        if words.is_empty() {
            continue;
        }
        let widths: Vec<f32> = words.iter().map(|w| font.advance(w, px)).collect();

        // Greedy: put words on the line while they still fit.
        let mut start = 0;
        let mut first = true;
        while start < words.len() {
            let lead = if first { indent } else { 0.0 };
            let avail = width - lead;
            let mut end = start;
            let mut used = 0.0;
            while end < words.len() {
                let next = used + if end > start { space } else { 0.0 } + widths[end];
                if end > start && next > avail + 0.001 {
                    break;
                }
                used = next;
                end += 1;
            }
            let n = end - start;
            let last = end == words.len();
            // Justify every line but the paragraph's last: spread the slack
            // evenly between the words so the line ends flush with the column.
            let gap = if !last && n > 1 {
                (avail - widths[start..end].iter().sum::<f32>()) / (n - 1) as f32
            } else {
                space
            };
            let mut x = lead;
            let mut placed = Vec::with_capacity(n);
            for k in start..end {
                placed.push(Placed { text: words[k].clone(), x });
                x += widths[k] + gap;
            }
            lines.push(Line { words: placed, y: lines.len() as f32 * line_h });
            start = end;
            first = false;
        }
    }
    lines
}

/// A word that is wider than the whole column, cut into pieces that each fit —
/// so a line can never run out of the column. Ordinary words come back whole.
pub(crate) fn split_to_fit(font: &TypeFont, px: f32, width: f32, word: &str) -> Vec<String> {
    if font.advance(word, px) <= width || width <= 0.0 {
        return vec![word.to_string()];
    }
    let mut pieces: Vec<String> = Vec::new();
    let mut cur = String::new();
    for c in word.chars() {
        let mut trial = cur.clone();
        trial.push(c);
        if !cur.is_empty() && font.advance(&trial, px) > width {
            pieces.push(std::mem::take(&mut cur));
        }
        cur.push(c);
    }
    if !cur.is_empty() {
        pieces.push(cur);
    }
    pieces
}

/// Cut the set text into pages of `block_h`, never splitting a line, each page's
/// `y` starting again from 0. Always at least one page, even for no text.
pub fn paginate(lines: Vec<Line>, line_h: f32, block_h: f32) -> Vec<Vec<Line>> {
    // Whole lines only: a page holds as many as fit, and at least one, so a
    // block shorter than a line cannot stall the pagination.
    let per_page = ((block_h + 0.01) / line_h.max(0.01)).floor().max(1.0) as usize;
    if lines.is_empty() {
        return vec![Vec::new()];
    }
    lines
        .chunks(per_page)
        .map(|chunk| {
            chunk
                .iter()
                .enumerate()
                .map(|(i, l)| Line { words: l.words.clone(), y: i as f32 * line_h })
                .collect()
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The face egui ships with — always there, so these tests do not depend on what
    /// happens to be installed on the machine.
    fn font() -> TypeFont {
        TypeFont::load("__no_such_family__")
    }

    fn paras(p: &[&str]) -> Vec<String> {
        p.iter().map(|s| s.to_string()).collect()
    }

    const PX: f32 = 30.0;

    fn lorem(n: usize) -> String {
        (0..n).map(|i| format!("palabra{}", i % 17)).collect::<Vec<_>>().join(" ")
    }

    // ── measuring ────────────────────────────────────────────────────────────

    #[test]
    fn the_fallback_font_loads() {
        assert!(font().advance("hola", PX) > 0.0);
    }

    #[test]
    fn an_empty_string_has_no_width() {
        assert_eq!(font().advance("", PX), 0.0);
    }

    #[test]
    fn more_text_is_wider_and_double_the_size_is_double_the_width() {
        let f = font();
        assert!(f.advance("hola mundo", PX) > f.advance("hola", PX));
        let (a, b) = (f.advance("hola mundo", PX), f.advance("hola mundo", PX * 2.0));
        assert!((b - 2.0 * a).abs() < 0.5, "{a} vs {b}");
    }

    #[test]
    fn a_line_has_a_height_and_an_ascent_inside_it() {
        let f = font();
        assert!(f.natural_height(PX) > PX * 0.8);
        assert!(f.ascent(PX) > 0.0 && f.ascent(PX) < f.natural_height(PX));
    }

    #[test]
    fn bytes_that_are_not_a_font_do_not_load() {
        assert!(TypeFont::from_bytes(vec![1, 2, 3]).is_none());
    }

    // ── breaking into lines ──────────────────────────────────────────────────

    #[test]
    fn no_line_runs_wider_than_the_column() {
        let f = font();
        let lines = typeset(&f, PX, 400.0, 0.0, 40.0, &paras(&[&lorem(60)]));
        assert!(lines.len() > 3);
        for l in &lines {
            let right = l.words.last().map(|w| w.x + f.advance(&w.text, PX)).unwrap_or(0.0);
            assert!(right <= 400.5, "a line reaches {right}: {}", l.text());
        }
    }

    #[test]
    fn every_word_survives_in_order() {
        let f = font();
        let text = lorem(80);
        let lines = typeset(&f, PX, 350.0, 20.0, 40.0, &paras(&[&text]));
        let got: Vec<String> = lines.iter().flat_map(|l| l.words.iter().map(|w| w.text.clone())).collect();
        let want: Vec<String> = text.split(' ').map(String::from).collect();
        assert_eq!(got, want);
    }

    #[test]
    fn only_the_first_line_of_a_paragraph_is_indented() {
        let f = font();
        let lines = typeset(&f, PX, 400.0, 25.0, 40.0, &paras(&[&lorem(40)]));
        assert!((lines[0].words[0].x - 25.0).abs() < 0.01);
        assert!(lines[1].words[0].x.abs() < 0.01);
    }

    #[test]
    fn each_paragraph_starts_indented_again_with_no_blank_line_between() {
        let f = font();
        let lines = typeset(&f, PX, 600.0, 25.0, 40.0, &paras(&["uno dos tres.", "cuatro cinco seis."]));
        assert_eq!(lines.len(), 2);
        assert!((lines[0].words[0].x - 25.0).abs() < 0.01);
        assert!((lines[1].words[0].x - 25.0).abs() < 0.01);
        assert!((lines[1].y - lines[0].y - 40.0).abs() < 0.01); // exactly one line apart
    }

    #[test]
    fn the_lines_are_one_line_height_apart_from_the_top() {
        let f = font();
        let lines = typeset(&f, PX, 300.0, 0.0, 44.0, &paras(&[&lorem(50)]));
        for (i, l) in lines.iter().enumerate() {
            assert!((l.y - i as f32 * 44.0).abs() < 0.01);
        }
    }

    #[test]
    fn an_empty_paragraph_and_no_paragraphs_give_no_lines() {
        let f = font();
        assert!(typeset(&f, PX, 300.0, 0.0, 40.0, &paras(&[""])).is_empty());
        assert!(typeset(&f, PX, 300.0, 0.0, 40.0, &[]).is_empty());
        assert!(typeset(&f, PX, 300.0, 0.0, 40.0, &paras(&["   "])).is_empty());
    }

    #[test]
    fn a_word_wider_than_the_column_is_broken_instead_of_running_out() {
        let f = font();
        let long = "x".repeat(200);
        let lines = typeset(&f, PX, 200.0, 0.0, 40.0, &paras(&[&long]));
        assert!(lines.len() > 1);
        let joined: String = lines.iter().flat_map(|l| l.words.iter().map(|w| w.text.clone())).collect();
        assert_eq!(joined, long); // nothing lost
        for l in &lines {
            let w = l.words.last().map(|w| w.x + f.advance(&w.text, PX)).unwrap_or(0.0);
            assert!(w <= 200.5, "{w}");
        }
    }

    // ── justifying ───────────────────────────────────────────────────────────

    #[test]
    fn every_line_but_the_last_fills_the_column_exactly() {
        let f = font();
        let lines = typeset(&f, PX, 420.0, 0.0, 40.0, &paras(&[&lorem(70)]));
        for l in &lines[..lines.len() - 1] {
            if l.words.len() < 2 {
                continue; // a lone word cannot be spread
            }
            let w = l.words.last().unwrap();
            let right = w.x + f.advance(&w.text, PX);
            assert!((right - 420.0).abs() < 0.5, "line ends at {right}: {}", l.text());
        }
    }

    #[test]
    fn the_last_line_of_a_paragraph_is_not_stretched() {
        let f = font();
        let lines = typeset(&f, PX, 420.0, 0.0, 40.0, &paras(&["una frase corta."]));
        let last = lines.last().unwrap();
        let right = last.words.last().map(|w| w.x + f.advance(&w.text, PX)).unwrap();
        assert!(right < 420.0 * 0.9, "a short last line should stay short: {right}");
        // ...and its words sit a natural space apart
        let gap = last.words[1].x - (last.words[0].x + f.advance(&last.words[0].text, PX));
        assert!((gap - f.advance(" ", PX)).abs() < 0.5, "{gap}");
    }

    // ── paginating ───────────────────────────────────────────────────────────

    fn many(n: usize) -> Vec<Line> {
        (0..n)
            .map(|i| Line { words: vec![Placed { text: format!("l{i}"), x: 0.0 }], y: i as f32 * 40.0 })
            .collect()
    }

    #[test]
    fn a_short_text_is_one_page() {
        assert_eq!(paginate(many(5), 40.0, 400.0).len(), 1);
    }

    #[test]
    fn a_long_text_is_several_pages_and_no_page_overflows() {
        let pages = paginate(many(100), 40.0, 400.0);
        assert_eq!(pages.len(), 10); // 10 lines of 40 fit in 400
        for p in &pages {
            let bottom = p.last().unwrap().y + 40.0;
            assert!(bottom <= 400.0 + 0.01, "a page runs to {bottom}");
        }
    }

    #[test]
    fn every_line_lands_on_exactly_one_page_in_order_and_y_restarts() {
        let pages = paginate(many(25), 40.0, 400.0);
        let names: Vec<String> = pages.iter().flatten().map(|l| l.text()).collect();
        assert_eq!(names, (0..25).map(|i| format!("l{i}")).collect::<Vec<_>>());
        for p in &pages {
            assert_eq!(p[0].y, 0.0); // each page starts at the top again
        }
    }

    #[test]
    fn no_text_is_still_one_blank_page() {
        let pages = paginate(Vec::new(), 40.0, 400.0);
        assert_eq!(pages.len(), 1);
        assert!(pages[0].is_empty());
    }

    #[test]
    fn a_page_shorter_than_a_line_still_makes_progress() {
        // never an infinite loop or an empty page that swallows everything
        let pages = paginate(many(3), 40.0, 10.0);
        assert_eq!(pages.iter().map(|p| p.len()).sum::<usize>(), 3);
    }
}

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
    /// The font file itself — a PDF embeds it, so the page prints as it shows.
    bytes: std::sync::Arc<Vec<u8>>,
    /// The family that was asked for and found; empty for the fallback face.
    family: String,
    /// The size the book is set at, in points (the Python's reading_size).
    size_pt: f32,
    /// Whether and how words may be broken across lines. Off until asked.
    hyph: crate::hyphen::Mode,
}

impl TypeFont {
    /// The writing font if it can be found on this machine; otherwise the plain
    /// face egui ships with, so a slide can always be drawn.
    pub fn load(family: &str) -> TypeFont {
        if let Some(mut font) = crate::fonts::load_family(family).and_then(TypeFont::from_bytes) {
            font.family = family.to_string();
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
        let kept = std::sync::Arc::new(bytes.clone());
        FontArc::try_from_vec(bytes).ok().map(|font| TypeFont {
            font,
            bytes: kept,
            family: String::new(),
            size_pt: crate::carousel::BOOK_SIZE_PT,
            hyph: crate::hyphen::Mode::Off,
        })
    }

    /// Whether this is `family` (and not the fallback face).
    pub fn is_named(&self, family: &str) -> bool {
        !self.family.is_empty() && crate::fonts::normalise(&self.family) == crate::fonts::normalise(family)
    }

    /// The font file, for embedding.
    pub fn bytes(&self) -> &[u8] {
        &self.bytes
    }

    /// The same font, set at `pt` points.
    pub fn with_size(mut self, pt: f32) -> TypeFont {
        if pt > 0.0 {
            self.size_pt = pt;
        }
        self
    }

    pub fn size_pt(&self) -> f32 {
        self.size_pt
    }

    /// The same font, set with the given hyphenation.
    pub fn with_hyphenation(mut self, mode: crate::hyphen::Mode) -> TypeFont {
        self.hyph = mode;
        self
    }

    pub fn hyphenation(&self) -> crate::hyphen::Mode {
        self.hyph
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
    typeset_marked(font, px, width, indent, line_h, paragraphs).0
}

/// Like `typeset`, and also the index of the line each paragraph starts on —
/// what a reader needs to open at "the paragraph you were in". A paragraph with
/// no words has no lines and so no entry.
pub fn typeset_marked(
    font: &TypeFont,
    px: f32,
    width: f32,
    indent: f32,
    line_h: f32,
    paragraphs: &[String],
) -> (Vec<Line>, Vec<usize>) {
    let space = font.advance(" ", px);
    let mut lines: Vec<Line> = Vec::new();
    let mut starts: Vec<usize> = Vec::new();

    for para in paragraphs {
        // Each word with the places it may be broken, in the paragraph's language.
        let lang = font.hyph.lang_for(para);
        let mut queue: std::collections::VecDeque<(String, Vec<usize>)> = para
            .split_whitespace()
            .flat_map(|w| {
                let pieces = split_to_fit(font, px, width, w);
                if pieces.len() == 1 {
                    vec![(w.to_string(), crate::hyphen::break_points(w, lang))]
                } else {
                    // wider than the column: cut by letters, nothing left to hyphenate
                    pieces.into_iter().map(|p| (p, Vec::new())).collect()
                }
            })
            .collect();
        if queue.is_empty() {
            continue;
        }
        starts.push(lines.len());

        let mut first = true;
        while !queue.is_empty() {
            let lead = if first { indent } else { 0.0 };
            let avail = width - lead;
            // Greedy: put words on the line while they still fit...
            let mut placed: Vec<(String, f32)> = Vec::new();
            let mut used = 0.0;
            while let Some((text, breaks)) = queue.front().cloned() {
                let w = font.advance(&text, px);
                let gap = if placed.is_empty() { 0.0 } else { space };
                if placed.is_empty() || used + gap + w <= avail + 0.001 {
                    used += gap + w;
                    placed.push((text, w));
                    queue.pop_front();
                    continue;
                }
                // ...and when one does not, break it at the last place that still fits,
                // with a hyphen, and carry the rest to the next line.
                for &k in breaks.iter().rev() {
                    let head: String = text.chars().take(k).chain(std::iter::once('-')).collect();
                    let hw = font.advance(&head, px);
                    if used + gap + hw <= avail + 0.001 {
                        placed.push((head, hw));
                        let rest: String = text.chars().skip(k).collect();
                        let rest_breaks = breaks.iter().filter(|&&b| b > k).map(|&b| b - k).collect();
                        queue.pop_front();
                        queue.push_front((rest, rest_breaks));
                        break;
                    }
                }
                break;
            }
            let n = placed.len();
            let last = queue.is_empty();
            // Justify every line but the paragraph's last: spread the slack
            // evenly between the words so the line ends flush with the column.
            let gap = if !last && n > 1 {
                (avail - placed.iter().map(|(_, w)| w).sum::<f32>()) / (n - 1) as f32
            } else {
                space
            };
            let mut x = lead;
            let mut words = Vec::with_capacity(n);
            for (text, w) in placed {
                words.push(Placed { text, x });
                x += w + gap;
            }
            lines.push(Line { words, y: lines.len() as f32 * line_h });
            first = false;
        }
    }
    (lines, starts)
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
    paginate_first(lines, line_h, block_h, block_h)
}

/// Like `paginate`, but the FIRST page has only `first_h` to fill — a chapter's
/// title takes the top of it. Every later page has `block_h`.
pub fn paginate_first(lines: Vec<Line>, line_h: f32, first_h: f32, block_h: f32) -> Vec<Vec<Line>> {
    if lines.is_empty() {
        return vec![Vec::new()];
    }
    let first = lines_that_fit(first_h, line_h);
    let per_page = lines_that_fit(block_h, line_h);
    let mut pages: Vec<Vec<Line>> = Vec::new();
    let mut at = 0;
    while at < lines.len() {
        let take = if pages.is_empty() { first } else { per_page };
        let end = (at + take).min(lines.len());
        pages.push(
            lines[at..end]
                .iter()
                .enumerate()
                .map(|(i, l)| Line { words: l.words.clone(), y: i as f32 * line_h })
                .collect(),
        );
        at = end;
    }
    pages
}

/// Which page line number `line` falls on, for the page sizes `paginate_first`
/// uses (in lines: `first` on the first page, `per_page` on every later one).
pub fn page_of_line(line: usize, first: usize, per_page: usize) -> usize {
    if line < first {
        0
    } else {
        1 + (line - first) / per_page.max(1)
    }
}

/// How many whole lines fit in `height`, never fewer than one — so a block
/// shorter than a line cannot stall the pagination.
pub fn lines_that_fit(height: f32, line_h: f32) -> usize {
    (((height + 0.01) / line_h.max(0.01)).floor().max(1.0)) as usize
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

    // ── hyphenating (reading_hyphen_lang) ────────────────────────────────────

    use crate::hyphen::{Lang, Mode};

    fn hfont() -> TypeFont {
        font().with_hyphenation(Mode::Fixed(Lang::Es))
    }

    fn es_text(n: usize) -> String {
        "El pensamiento humano transforma extraordinariamente la comprensión universal de cada civilización antigua. "
            .repeat(n)
            .trim()
            .to_string()
    }

    fn right_edge(f: &TypeFont, l: &Line) -> f32 {
        l.words.last().map(|w| w.x + f.advance(&w.text, PX)).unwrap_or(0.0)
    }

    fn letters(lines: &[Line]) -> String {
        lines.iter().flat_map(|l| l.words.iter().map(|w| w.text.clone())).collect::<String>().replace('-', "")
    }

    #[test]
    fn a_font_is_not_hyphenating_until_asked_to() {
        assert_eq!(font().hyphenation(), Mode::Off);
        assert_eq!(hfont().hyphenation(), Mode::Fixed(Lang::Es));
        let plain = typeset(&font(), PX, 300.0, 0.0, 40.0, &paras(&[&es_text(3)]));
        assert!(!plain.iter().any(|l| l.words.iter().any(|w| w.text.ends_with('-'))), "no hyphens unless asked");
    }

    #[test]
    fn hyphenating_breaks_words_across_lines_and_loses_no_letter() {
        let f = hfont();
        let text = es_text(4);
        let lines = typeset(&f, PX, 260.0, 0.0, 40.0, &paras(&[&text]));
        assert!(lines.iter().any(|l| l.words.last().is_some_and(|w| w.text.ends_with('-'))), "a narrow column should break some word");
        assert_eq!(letters(&lines), text.replace(' ', ""));
    }

    #[test]
    fn a_hyphenated_line_still_fits_and_still_ends_flush() {
        let f = hfont();
        let lines = typeset(&f, PX, 300.0, 0.0, 40.0, &paras(&[&es_text(4)]));
        for l in &lines[..lines.len() - 1] {
            if l.words.len() > 1 {
                assert!((right_edge(&f, l) - 300.0).abs() < 0.6, "line ends at {}: {}", right_edge(&f, l), l.text());
            }
        }
        for l in &lines {
            assert!(right_edge(&f, l) <= 300.6);
        }
    }

    #[test]
    fn it_never_needs_more_lines_than_without_hyphenation() {
        for width in [220.0, 260.0, 300.0, 380.0] {
            let plain = typeset(&font(), PX, width, 0.0, 40.0, &paras(&[&es_text(5)])).len();
            let hyph = typeset(&hfont(), PX, width, 0.0, 40.0, &paras(&[&es_text(5)])).len();
            assert!(hyph <= plain, "width {width}: {hyph} lines hyphenated vs {plain}");
        }
    }

    #[test]
    fn a_break_never_leaves_fewer_than_two_letters_on_either_side() {
        let f = hfont();
        let lines = typeset(&f, PX, 240.0, 0.0, 40.0, &paras(&[&es_text(6)]));
        for pair in lines.windows(2) {
            let Some(last) = pair[0].words.last().filter(|w| w.text.ends_with('-')) else { continue };
            let head: String = last.text.trim_end_matches('-').chars().rev().take_while(|c| c.is_alphabetic()).collect();
            assert!(head.chars().count() >= 2, "head of {:?}", last.text);
            let tail: String = pair[1].words[0].text.chars().take_while(|c| c.is_alphabetic()).collect();
            assert!(tail.chars().count() >= 2, "tail {:?}", pair[1].words[0].text);
        }
    }

    #[test]
    fn a_wide_column_breaks_no_word_at_all() {
        let lines = typeset(&hfont(), PX, 4000.0, 0.0, 40.0, &paras(&[&es_text(2)]));
        assert_eq!(lines.len(), 1);
        assert!(!lines[0].words.iter().any(|w| w.text.contains('-')));
    }

    #[test]
    fn auto_hyphenates_each_paragraph_in_its_own_language_and_leaves_the_unknown_alone() {
        let f = font().with_hyphenation(Mode::Auto);
        let es = es_text(3);
        let nonsense = "xyzabcdefgh qrstuvwxyzabc ".repeat(8);
        let en = "The extraordinary philosophy of understanding is a wonderful thing and the beginning of knowledge, ".repeat(3);
        let lines_es = typeset(&f, PX, 250.0, 0.0, 40.0, &paras(&[&es]));
        let lines_none = typeset(&f, PX, 250.0, 0.0, 40.0, &paras(&[nonsense.trim()]));
        let lines_en = typeset(&f, PX, 250.0, 0.0, 40.0, &paras(&[en.trim()]));
        let hyphenated = |ls: &[Line]| ls.iter().any(|l| l.words.last().is_some_and(|w| w.text.ends_with('-')));
        assert!(hyphenated(&lines_es), "Spanish");
        assert!(hyphenated(&lines_en), "English");
        assert!(!hyphenated(&lines_none), "no language signal: not hyphenated");
    }

    #[test]
    fn hyphenation_does_not_disturb_where_paragraphs_start() {
        let f = hfont();
        let (lines, starts) = typeset_marked(&f, PX, 260.0, 0.0, 40.0, &paras(&[&es_text(3), "una linea.", &es_text(2)]));
        assert_eq!(starts.len(), 3);
        assert_eq!(lines[starts[1]].text(), "una linea.");
    }

    #[test]
    fn the_indent_and_a_hyphen_together_still_fit() {
        let f = hfont();
        let lines = typeset(&f, PX, 280.0, 30.0, 40.0, &paras(&[&es_text(3)]));
        assert!((lines[0].words[0].x - 30.0).abs() < 0.01);
        for l in &lines {
            assert!(right_edge(&f, l) <= 280.6);
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

    // ── a first page with less room (the title takes the top of it) ──────────

    #[test]
    fn the_first_page_can_hold_fewer_lines_than_the_rest() {
        // 400 high pages hold 10 lines of 40; the first has only 200: 5 lines
        let pages = paginate_first(many(30), 40.0, 200.0, 400.0);
        let sizes: Vec<usize> = pages.iter().map(|p| p.len()).collect();
        assert_eq!(sizes, vec![5, 10, 10, 5]);
    }

    #[test]
    fn every_line_still_lands_once_in_order_and_y_restarts_on_each_page() {
        let pages = paginate_first(many(23), 40.0, 120.0, 400.0);
        let names: Vec<String> = pages.iter().flatten().map(|l| l.text()).collect();
        assert_eq!(names, (0..23).map(|i| format!("l{i}")).collect::<Vec<_>>());
        for p in &pages {
            assert_eq!(p[0].y, 0.0);
        }
    }

    #[test]
    fn with_a_full_first_page_it_is_the_same_as_paginate() {
        let a = paginate(many(37), 40.0, 400.0);
        let b = paginate_first(many(37), 40.0, 400.0, 400.0);
        assert_eq!(a, b);
    }

    #[test]
    fn a_first_page_with_no_room_still_makes_progress() {
        let pages = paginate_first(many(3), 40.0, 5.0, 400.0);
        assert_eq!(pages.iter().map(|p| p.len()).sum::<usize>(), 3);
        let none = paginate_first(Vec::new(), 40.0, 5.0, 400.0);
        assert_eq!(none.len(), 1);
    }

    #[test]
    fn page_of_line_agrees_with_where_paginate_first_put_it() {
        let pages = paginate_first(many(30), 40.0, 200.0, 400.0);
        let (first, per) = (lines_that_fit(200.0, 40.0), lines_that_fit(400.0, 40.0));
        for (page_no, p) in pages.iter().enumerate() {
            for l in p {
                let n: usize = l.text()[1..].parse().unwrap();
                assert_eq!(page_of_line(n, first, per), page_no, "line {n}");
            }
        }
    }

    #[test]
    fn lines_that_fit_is_whole_lines_and_at_least_one() {
        assert_eq!(lines_that_fit(400.0, 40.0), 10);
        assert_eq!(lines_that_fit(399.0, 40.0), 9);
        assert_eq!(lines_that_fit(5.0, 40.0), 1);
        assert_eq!(lines_that_fit(0.0, 40.0), 1);
    }

    // ── where each paragraph starts ──────────────────────────────────────────

    #[test]
    fn each_paragraph_reports_the_line_it_starts_on() {
        let f = font();
        let (lines, starts) = typeset_marked(&f, PX, 300.0, 0.0, 40.0, &paras(&[&lorem(40), "una linea.", &lorem(30)]));
        assert_eq!(starts.len(), 3);
        assert_eq!(starts[0], 0);
        assert!(starts[1] > 1 && starts[2] > starts[1]);
        assert_eq!(lines[starts[1]].text(), "una linea.");
        assert_eq!(lines.len(), typeset(&f, PX, 300.0, 0.0, 40.0, &paras(&[&lorem(40), "una linea.", &lorem(30)])).len());
    }

    #[test]
    fn a_paragraph_with_no_words_has_no_start() {
        let f = font();
        let (lines, starts) = typeset_marked(&f, PX, 300.0, 0.0, 40.0, &paras(&["", "hola.", "  "]));
        assert_eq!(starts, vec![0]);
        assert_eq!(lines.len(), 1);
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

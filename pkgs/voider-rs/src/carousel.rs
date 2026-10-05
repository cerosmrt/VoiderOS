//! F4 → Instagram carousel: the geometry and the naming, no pixels.
//!
//! A port of the pure half of the carousel code in `reading_page.py` and
//! `f4_mixin.py`. A slide is the book page re-proportioned: it keeps A5's WIDTH —
//! so the type size, the margins and the leading that were tuned for the book
//! carry over unchanged — and only the height changes to match the ratio.

#![allow(dead_code)]

/// A5, in millimetres — the book's own page.
pub const A5_W_MM: f32 = 148.0;
pub const A5_H_MM: f32 = 210.0;

/// Book margins in mm: top, bottom, left/right. The Python's `BOOK_MARGINS_MM`.
pub const MARGIN_TOP_MM: f32 = 21.0;
pub const MARGIN_BOTTOM_MM: f32 = 21.0;
pub const MARGIN_SIDE_MM: f32 = 20.0;

/// First-line indent of every paragraph, and the type size of the book (pt).
pub const INDENT_MM: f32 = 5.0;
pub const BOOK_SIZE_PT: f32 = 13.0;

/// Leading, as the Python sets it: 132 % of the font's own line height.
pub const LINE_HEIGHT_PCT: f32 = 132.0;

/// The three Instagram ratios, in pixels (width, height).
pub const PRESETS: [(&str, (u32, u32)); 3] = [
    ("1:1", (1080, 1080)),
    ("4:5", (1080, 1350)),
    ("1.91:1", (1080, 566)),
];

/// What F10 offers for the frame, in the order Tab steps through them.
pub const FRAMES: [&str; 4] = ["1:1", "4:5", "1.91:1", "custom"];

/// A `custom` frame is nudged in steps of this many pixels, and kept between
/// these bounds — an absurd size would be a gigabyte of slides.
pub const SIZE_STEP: u32 = 10;
pub const SIZE_MIN: u32 = 100;
pub const SIZE_MAX: u32 = 4000;

/// The preset a fresh install uses.
pub const DEFAULT_PRESET: &str = "4:5";

/// Millimetres → PostScript points (1 pt = 1/72 inch).
pub fn mm_to_pt(mm: f32) -> f32 {
    mm * 72.0 / 25.4
}

/// A5's width in points: the width every slide keeps.
pub fn a5_width_pt() -> f32 {
    mm_to_pt(A5_W_MM)
}

/// The slide's size for a configured preset. `"custom"` takes the width and
/// height given; an unknown name falls back to the default rather than failing.
pub fn dimensions(preset: &str, custom_w: u32, custom_h: u32) -> (u32, u32) {
    let default = || {
        PRESETS
            .iter()
            .find(|(k, _)| *k == DEFAULT_PRESET)
            .map(|(_, v)| *v)
            .unwrap_or((1080, 1350))
    };
    if preset == "custom" {
        // A hand-edited zero would make an empty image; take the default instead.
        return if custom_w > 0 && custom_h > 0 { (custom_w, custom_h) } else { default() };
    }
    PRESETS
        .iter()
        .find(|(k, _)| *k == preset)
        .map(|(_, v)| *v)
        .unwrap_or_else(default)
}


/// The physical page (in points) of a slide whose ratio is `w_px : h_px`: A5's
/// width, and whatever height makes the ratio match.
pub fn page_pt(w_px: u32, h_px: u32) -> (f32, f32) {
    let w = a5_width_pt();
    (w, w * h_px as f32 / w_px.max(1) as f32)
}


/// Everything laid out in pixels for one slide size.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Geometry {
    pub w: u32,
    pub h: u32,
    /// Pixels per point: the one uniform scale from the book page to the slide.
    pub scale: f32,
    pub margin_top: f32,
    pub margin_bottom: f32,
    pub margin_side: f32,
    /// The live text area.
    pub block_w: f32,
    pub block_h: f32,
    pub indent: f32,
    /// The book's type size, in pixels.
    pub font_px: f32,
}

pub fn geometry(w_px: u32, h_px: u32) -> Geometry {
    let scale = w_px as f32 / a5_width_pt();
    let px = |mm: f32| mm_to_pt(mm) * scale;
    let margin_side = px(MARGIN_SIDE_MM);
    let margin_top = px(MARGIN_TOP_MM);
    let margin_bottom = px(MARGIN_BOTTOM_MM);
    Geometry {
        w: w_px,
        h: h_px,
        scale,
        margin_top,
        margin_bottom,
        margin_side,
        block_w: w_px as f32 - 2.0 * margin_side,
        block_h: h_px as f32 - margin_top - margin_bottom,
        indent: px(INDENT_MM),
        font_px: BOOK_SIZE_PT * scale,
    }
}


/// What a slide in the carousel is. The file name follows from it and from its
/// place in the numbering.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SlideKind {
    Cover,
    Title,
    Body,
    Back,
}

/// `N_portada.png`, `N_titulo.png`, `N.png` or `N_contratapa.png`.
pub fn file_name(n: usize, kind: &SlideKind) -> String {
    match kind {
        SlideKind::Cover => format!("{n}_portada.png"),
        SlideKind::Title => format!("{n}_titulo.png"),
        SlideKind::Body => format!("{n}.png"),
        SlideKind::Back => format!("{n}_contratapa.png"),
    }
}


#[cfg(test)]
mod tests {
    use super::*;

    fn close(a: f32, b: f32) -> bool {
        (a - b).abs() < 0.01
    }

    // ── test_carousel_geometry.py ────────────────────────────────────────────

    #[test]
    fn the_width_matches_a5() {
        let (w, _) = page_pt(1080, 1350);
        assert!(close(w, a5_width_pt()));
    }

    #[test]
    fn a_square_ratio_is_a_square_page() {
        let (w, h) = page_pt(1080, 1080);
        assert!(close(h, w));
    }

    #[test]
    fn the_4_5_ratio_height() {
        let (w, h) = page_pt(1080, 1350);
        assert!(close(h, w * 1350.0 / 1080.0));
    }

    #[test]
    fn a_landscape_ratio_is_shorter_than_wide() {
        let (w, h) = page_pt(1080, 566);
        assert!(h < w);
    }

    #[test]
    fn the_presets_hold_the_three_instagram_ratios() {
        let get = |n: &str| PRESETS.iter().find(|(k, _)| *k == n).map(|(_, v)| *v);
        assert_eq!(get("1:1"), Some((1080, 1080)));
        assert_eq!(get("4:5"), Some((1080, 1350)));
        assert_eq!(get("1.91:1"), Some((1080, 566)));
    }

    // ── which size a configuration asks for (_carousel_dimensions) ───────────

    #[test]
    fn a_named_preset_gives_its_size() {
        assert_eq!(dimensions("1:1", 0, 0), (1080, 1080));
        assert_eq!(dimensions("1.91:1", 0, 0), (1080, 566));
    }

    #[test]
    fn custom_takes_the_configured_width_and_height() {
        assert_eq!(dimensions("custom", 800, 600), (800, 600));
    }

    #[test]
    fn an_unknown_preset_falls_back_to_the_default() {
        assert_eq!(dimensions("nope", 0, 0), (1080, 1350));
        assert_eq!(dimensions("", 0, 0), (1080, 1350));
    }

    #[test]
    fn a_custom_size_of_zero_does_not_produce_an_empty_slide() {
        // A hand-edited config with a zero must not make a 0×0 image.
        let (w, h) = dimensions("custom", 0, 0);
        assert!(w > 0 && h > 0);
    }

    // ── the slide laid out in pixels ─────────────────────────────────────────

    #[test]
    fn one_uniform_scale_takes_the_book_page_to_the_slide() {
        let g = geometry(1080, 1350);
        assert!(close(g.scale, 1080.0 / a5_width_pt()));
        assert_eq!((g.w, g.h), (1080, 1350));
    }

    #[test]
    fn the_text_block_is_the_page_minus_the_book_margins() {
        let g = geometry(1080, 1350);
        let side = mm_to_pt(MARGIN_SIDE_MM) * g.scale;
        assert!(close(g.margin_side, side));
        assert!(close(g.block_w, 1080.0 - 2.0 * side));
        let v = mm_to_pt(MARGIN_TOP_MM + MARGIN_BOTTOM_MM) * g.scale;
        assert!(close(g.block_h, 1350.0 - v));
    }

    #[test]
    fn the_type_size_scales_with_the_slide_not_with_its_height() {
        let tall = geometry(1080, 1350);
        let square = geometry(1080, 1080);
        assert!(close(tall.font_px, square.font_px)); // same width → same type
        assert!(close(tall.font_px, BOOK_SIZE_PT * tall.scale));
        assert!(tall.block_h > square.block_h);
    }

    #[test]
    fn a_smaller_slide_scales_the_whole_page_down() {
        let big = geometry(1080, 1350);
        let small = geometry(540, 675);
        assert!(close(small.font_px * 2.0, big.font_px));
        assert!(close(small.block_h * 2.0, big.block_h));
    }

    // ── the files ────────────────────────────────────────────────────────────

    #[test]
    fn slide_files_are_named_by_kind_and_place() {
        assert_eq!(file_name(1, &SlideKind::Cover), "1_portada.png");
        assert_eq!(file_name(1, &SlideKind::Title), "1_titulo.png");
        assert_eq!(file_name(2, &SlideKind::Body), "2.png");
        assert_eq!(file_name(7, &SlideKind::Back), "7_contratapa.png");
    }
}

//! How a ring of lines looks: how far apart, how bright, how fast it fades.
//!
//! The numbers are the Python's (`widgets.py` and `circular_view.py`), copied
//! rather than eyeballed, so F2, F3 and F5 read as the same ring in both. One
//! place, because a ring drawn with its own private curve is how F5 came to look
//! different from F2 in the first place.

#![allow(dead_code)]

/// Line spacing, as a multiple of the font's own height (`LINE_SPACING`).
pub const LINE_SPACING: f32 = 1.31;

/// How much of its brightness everything but the chosen line keeps (`DIM_FACTOR`).
/// The ring's curve alone is not enough to mark the chosen line: one row away it
/// is still 97 % bright.
pub const DIM_FACTOR: f32 = 0.3;

/// Qt sizes type in points and the window in pixels: 1 pt = 96/72 px at the
/// usual 96 dpi. The configured size (22) means points, so it is scaled.
pub const PX_PER_PT: f32 = 96.0 / 72.0;

/// A configured size in points, in pixels.
pub fn px_from_pt(pt: f32) -> f32 {
    pt * PX_PER_PT
}

/// The jump between lines for a font whose own line height is `font_h`.
pub fn line_height(font_h: f32) -> f32 {
    // int(), as Qt's `int(fm.height() * LINE_SPACING)`: whole pixels.
    (font_h * LINE_SPACING).floor().max(1.0)
}

/// How visible a line `dist_px` from the centre is, in a window `half_h` tall on
/// each side of it: a cosine, slow near the centre and fast at the edges, zero at
/// the edge of the window. This is what makes it read as a ring and not a list.
pub fn ring_alpha(dist_px: f32, half_h: f32) -> f32 {
    if half_h <= 0.0 {
        return 1.0;
    }
    let t = dist_px.abs() / half_h;
    if t < 1.0 {
        (t * std::f32::consts::FRAC_PI_2).cos().clamp(0.0, 1.0)
    } else {
        0.0
    }
}

/// The brightness of the line `offset` rows from the centre when the centre line
/// is the one being edited (F2, F3): the centre itself is drawn by the editor, so
/// it is full; standing on a dot keeps the paragraph it opens lit (`para_size`
/// lines below it); everything else is dimmed.
pub fn edit_line_alpha(offset: isize, dist_px: f32, half_h: f32, on_dot: bool, para_size: usize) -> f32 {
    if offset == 0 {
        return 1.0;
    }
    let base = ring_alpha(dist_px, half_h);
    if on_dot && offset >= 1 && offset as usize <= para_size {
        base
    } else {
        base * DIM_FACTOR
    }
}

/// Paragraph focus (Enter on a dot): what is in the paragraph keeps its alpha,
/// everything else goes to a tenth of it.
pub fn focus_alpha(base: f32, in_paragraph: bool) -> f32 {
    if in_paragraph { base } else { base * 0.1 }
}

/// A 0..1 brightness as the 0..255 an alpha channel wants.
pub fn to_u8(alpha: f32) -> u8 {
    (alpha.clamp(0.0, 1.0) * 255.0).round() as u8
}

#[cfg(test)]
mod tests {
    use super::*;

    fn close(a: f32, b: f32) -> bool {
        (a - b).abs() < 0.001
    }

    // ── points to pixels ─────────────────────────────────────────────────────

    #[test]
    fn a_configured_22_is_29_pixels() {
        assert!(close(px_from_pt(22.0), 22.0 * 96.0 / 72.0));
        assert!((px_from_pt(22.0) - 29.33).abs() < 0.01);
    }

    #[test]
    fn size_scales_linearly() {
        assert!(close(px_from_pt(44.0), 2.0 * px_from_pt(22.0)));
        assert_eq!(px_from_pt(0.0), 0.0);
    }

    // ── spacing ──────────────────────────────────────────────────────────────

    #[test]
    fn the_line_jump_follows_the_font_height() {
        // The Python takes int(font height * 1.31): a larger font spaces wider.
        assert_eq!(line_height(28.0), 36.0); // 36.68 → 36
        assert_eq!(line_height(40.0), 52.0); // 52.4 → 52
        assert!(line_height(60.0) > line_height(30.0));
    }

    #[test]
    fn the_line_jump_is_never_zero() {
        assert!(line_height(0.0) >= 1.0);
    }

    // ── the ring's curve (widgets.ring_alpha) ────────────────────────────────

    #[test]
    fn the_centre_is_fully_bright_and_the_edge_of_the_window_is_dark() {
        assert!(close(ring_alpha(0.0, 380.0), 1.0));
        assert!(close(ring_alpha(380.0, 380.0), 0.0));
        assert!(close(ring_alpha(1000.0, 380.0), 0.0)); // past the window
    }

    #[test]
    fn it_is_a_cosine_not_a_straight_line() {
        // halfway out: cos(pi/4), not 0.5
        assert!(close(ring_alpha(190.0, 380.0), std::f32::consts::FRAC_1_SQRT_2));
    }

    #[test]
    fn it_falls_slowly_near_the_centre_and_fast_near_the_edge() {
        let a = |d: f32| ring_alpha(d, 380.0);
        let near = a(0.0) - a(38.0);
        let far = a(300.0) - a(338.0);
        assert!(far > near * 3.0, "near {near}, far {far}");
        // one row away is still ~97 %, which is why the dimming exists
        assert!(a(37.0) > 0.95);
    }

    #[test]
    fn it_never_goes_up_with_distance() {
        let mut last = 2.0;
        for d in (0..400).step_by(10) {
            let v = ring_alpha(d as f32, 380.0);
            assert!(v <= last + 1e-6);
            last = v;
        }
    }

    #[test]
    fn a_window_of_no_height_does_not_divide_by_zero() {
        assert_eq!(ring_alpha(0.0, 0.0), 1.0);
        assert!(ring_alpha(5.0, 0.0).is_finite());
    }

    // ── which lines are lit (circular_view.edit_alpha) ───────────────────────

    #[test]
    fn the_line_being_edited_is_full() {
        assert!(close(edit_line_alpha(0, 0.0, 380.0, false, 0), 1.0));
    }

    #[test]
    fn every_other_line_is_a_third_of_the_ring_curve() {
        let base = ring_alpha(74.0, 380.0);
        assert!(close(edit_line_alpha(2, 74.0, 380.0, false, 0), base * DIM_FACTOR));
        assert!(close(edit_line_alpha(-2, 74.0, 380.0, false, 0), base * DIM_FACTOR));
    }

    #[test]
    fn standing_on_a_dot_keeps_its_paragraph_lit_and_the_rest_dim() {
        let base = |d: f32| ring_alpha(d, 380.0);
        // para_size = 3: the three lines below the dot belong to it
        for off in 1..=3 {
            let d = off as f32 * 37.0;
            assert!(close(edit_line_alpha(off, d, 380.0, true, 3), base(d)), "line {off}");
        }
        assert!(close(edit_line_alpha(4, 148.0, 380.0, true, 3), base(148.0) * DIM_FACTOR));
        assert!(close(edit_line_alpha(-1, 37.0, 380.0, true, 3), base(37.0) * DIM_FACTOR)); // above it
    }

    #[test]
    fn off_a_dot_the_paragraph_rule_does_not_apply() {
        let base = ring_alpha(37.0, 380.0);
        assert!(close(edit_line_alpha(1, 37.0, 380.0, false, 3), base * DIM_FACTOR));
    }

    // ── to bytes ─────────────────────────────────────────────────────────────

    #[test]
    fn brightness_maps_to_the_alpha_byte_and_clamps() {
        assert_eq!(to_u8(0.0), 0);
        assert_eq!(to_u8(1.0), 255);
        assert_eq!(to_u8(0.5), 128);
        assert_eq!(to_u8(-1.0), 0);
        assert_eq!(to_u8(7.0), 255);
    }
}

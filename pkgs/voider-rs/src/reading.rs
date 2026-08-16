//! F4 — the book as a book: the text set in a column and turned page by page.
//!
//! Ports the pure half of `f4_mixin.py` and `reading_page.py`. The layout idea
//! is the Python's and worth keeping: the whole text is laid out ONCE as a
//! single tall column, and a page is a window onto it. Paging is then just
//! choosing offsets, and the rule that matters — never cut a line in half
//! across a page break — becomes a property of how those offsets are chosen
//! rather than something the renderer has to worry about.
//!
//! Measuring is left to the caller, which is what makes this testable: it hands
//! in the y-position and height of every laid-out line, and gets back where the
//! pages start.

#![allow(dead_code)]

/// 0-based index of the paragraph containing `lines[idx]`.
///
/// Paragraphs are runs of non-empty, non-`.` lines. A `.` separator or a blank
/// maps to the paragraph BEFORE it (or 0 if none), so landing on the dot above
/// a paragraph opens the page that paragraph is on. Shared by F4 and F5, as in
/// the Python.
pub fn para_ordinal_at(lines: &[String], idx: usize) -> usize {
    if lines.is_empty() {
        return 0;
    }
    let idx = idx.min(lines.len() - 1);
    let mut ordinal: isize = -1;
    let mut in_para = false;
    let mut last_para: isize = 0;

    for (i, raw) in lines.iter().enumerate() {
        let s = raw.trim();
        let mut is_text = false;
        if s == "." {
            in_para = false;
        } else if !s.is_empty() {
            if !in_para {
                ordinal += 1;
                in_para = true;
            }
            last_para = ordinal;
            is_text = true;
        }
        if i == idx {
            let v = if is_text { ordinal } else { last_para };
            return v.max(0) as usize;
        }
    }
    last_para.max(0) as usize
}

/// One laid-out line of the column: where its top sits, and how tall it is.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Line {
    pub top: f32,
    pub height: f32,
}

/// Where each page starts, in column coordinates.
///
/// A page takes as many whole lines as fit in `page_height`; the first line
/// that would hang over the bottom begins the next page instead. A line taller
/// than a whole page still gets a page to itself rather than looping forever.
pub fn page_offsets(lines: &[Line], page_height: f32) -> Vec<f32> {
    if lines.is_empty() || page_height <= 0.0 {
        return vec![0.0];
    }
    let mut offsets = vec![lines[0].top];
    let mut start = lines[0].top;
    for (i, line) in lines.iter().enumerate() {
        if line.top + line.height <= start + page_height {
            continue; // still fits on this page
        }
        // This line hangs over: it opens the next page.
        if line.top <= start {
            // Taller than the page itself — give it its own and move on, or we
            // would sit here forever making zero-progress pages.
            let next = lines.get(i + 1).map(|l| l.top);
            match next {
                Some(t) => {
                    offsets.push(t);
                    start = t;
                }
                None => break,
            }
        } else {
            offsets.push(line.top);
            start = line.top;
        }
    }
    offsets
}

/// Which page a point in the column falls on.
pub fn page_of(offsets: &[f32], y: f32) -> usize {
    offsets
        .iter()
        .rposition(|o| *o <= y + f32::EPSILON)
        .unwrap_or(0)
}

/// What F4 is showing: a title and the paragraphs under it.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Section {
    pub title: String,
    pub paragraphs: Vec<String>,
}

#[cfg(test)]
mod tests {
    use super::*;

    fn v(lines: &[&str]) -> Vec<String> {
        lines.iter().map(|s| s.to_string()).collect()
    }

    // ── paragraph ordinals (the Python's test_open_position, exactly) ──────────

    #[test]
    fn the_first_paragraphs_lines_are_all_paragraph_zero() {
        let lines = v(&[".", "a", "b", ".", "c", ".", "d"]);
        assert_eq!(para_ordinal_at(&lines, 1), 0);
        assert_eq!(para_ordinal_at(&lines, 2), 0);
    }

    #[test]
    fn later_paragraphs_count_up() {
        let lines = v(&[".", "a", "b", ".", "c", ".", "d"]);
        assert_eq!(para_ordinal_at(&lines, 4), 1);
        assert_eq!(para_ordinal_at(&lines, 6), 2);
    }

    #[test]
    fn a_separator_belongs_to_the_paragraph_before_it() {
        let lines = v(&[".", "a", ".", "b"]);
        assert_eq!(para_ordinal_at(&lines, 2), 0);
    }

    #[test]
    fn the_leading_separator_is_paragraph_zero() {
        let lines = v(&[".", "a", ".", "b"]);
        assert_eq!(para_ordinal_at(&lines, 0), 0);
    }

    #[test]
    fn blank_lines_do_not_break_a_paragraph() {
        // Only '.' separates; a blank is nothing at all.
        let lines = v(&[".", "a", "", "b", ".", "c"]);
        assert_eq!(para_ordinal_at(&lines, 5), 1);
    }

    #[test]
    fn an_empty_document_is_paragraph_zero() {
        assert_eq!(para_ordinal_at(&[], 0), 0);
    }

    #[test]
    fn an_index_past_the_end_clamps() {
        let lines = v(&[".", "a", ".", "b"]);
        assert_eq!(para_ordinal_at(&lines, 99), 1);
    }

    // ── paging the column ─────────────────────────────────────────────────────

    fn rows(n: usize, h: f32) -> Vec<Line> {
        (0..n).map(|i| Line { top: i as f32 * h, height: h }).collect()
    }

    #[test]
    fn lines_that_fit_share_a_page() {
        // 10 lines of 10pt, a 50pt page: 5 lines each.
        let offsets = page_offsets(&rows(10, 10.0), 50.0);
        assert_eq!(offsets, vec![0.0, 50.0]);
    }

    #[test]
    fn a_line_is_never_cut_across_a_page_break() {
        // 55pt of page holds 5 whole lines, not 5.5 — the 6th starts page two.
        let offsets = page_offsets(&rows(10, 10.0), 55.0);
        assert_eq!(offsets, vec![0.0, 50.0]);
        // Every page starts exactly on a line top.
        let tops: Vec<f32> = rows(10, 10.0).iter().map(|l| l.top).collect();
        for o in offsets {
            assert!(tops.contains(&o), "page started mid-line at {o}");
        }
    }

    #[test]
    fn one_page_is_enough_when_everything_fits() {
        assert_eq!(page_offsets(&rows(3, 10.0), 1000.0), vec![0.0]);
    }

    #[test]
    fn an_empty_text_still_has_a_page() {
        assert_eq!(page_offsets(&[], 100.0), vec![0.0]);
    }

    #[test]
    fn a_line_taller_than_the_page_gets_its_own_and_does_not_hang() {
        // The loop must make progress even when nothing fits.
        let lines = vec![
            Line { top: 0.0, height: 500.0 },
            Line { top: 500.0, height: 10.0 },
        ];
        let offsets = page_offsets(&lines, 100.0);
        assert!(offsets.len() >= 2);
        assert_eq!(offsets[0], 0.0);
    }

    #[test]
    fn lines_of_differing_heights_page_correctly() {
        let lines = vec![
            Line { top: 0.0, height: 20.0 },
            Line { top: 20.0, height: 20.0 },
            Line { top: 40.0, height: 20.0 },
        ];
        // A 45pt page holds the first two (40pt), not the third.
        assert_eq!(page_offsets(&lines, 45.0), vec![0.0, 40.0]);
    }

    #[test]
    fn a_point_maps_back_to_its_page() {
        let offsets = vec![0.0, 50.0, 100.0];
        assert_eq!(page_of(&offsets, 0.0), 0);
        assert_eq!(page_of(&offsets, 49.0), 0);
        assert_eq!(page_of(&offsets, 50.0), 1);
        assert_eq!(page_of(&offsets, 120.0), 2);
    }

    #[test]
    fn a_point_before_the_start_is_the_first_page() {
        assert_eq!(page_of(&[0.0, 50.0], -10.0), 0);
    }
}

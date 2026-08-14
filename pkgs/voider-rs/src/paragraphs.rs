//! Paragraphs as blocks between `.` separators — what Alt+Up/Down moves when
//! the cursor is sitting on a dot rather than on a line.
//!
//! Ported from the `_paragraphs_from_ring` / `_move_paragraph` family in
//! `f2_mixin.py`, tests included: at the ends a paragraph does not swap, it
//! *moves* — the first one becomes the last, and the last becomes the first.

#![allow(dead_code)]

/// Split the lines into (dot positions, the block of lines after each dot).
/// With no dots at all, everything is one paragraph.
pub fn from_lines(lines: &[String]) -> (Vec<usize>, Vec<Vec<String>>) {
    let dots: Vec<usize> = lines
        .iter()
        .enumerate()
        .filter(|(_, l)| *l == ".")
        .map(|(i, _)| i)
        .collect();
    if dots.is_empty() {
        return (vec![], vec![lines.to_vec()]);
    }
    let mut paragraphs = Vec::new();
    for (k, &d) in dots.iter().enumerate() {
        let next = dots.get(k + 1).copied().unwrap_or(lines.len());
        paragraphs.push(lines[d + 1..next].to_vec());
    }
    (dots, paragraphs)
}

/// Paragraphs → lines, each preceded by its separator.
pub fn to_lines(paragraphs: &[Vec<String>]) -> Vec<String> {
    let mut lines = Vec::new();
    for p in paragraphs {
        lines.push(".".to_string());
        lines.extend(p.iter().cloned());
    }
    lines
}

/// Line index of the dot that opens paragraph `k`.
pub fn dot_line_index(k: usize, paragraphs: &[Vec<String>]) -> usize {
    paragraphs[..k.min(paragraphs.len())]
        .iter()
        .map(|p| p.len() + 1)
        .sum()
}

/// Which paragraph the dot at `line_idx` opens.
pub fn para_at_dot(lines: &[String], line_idx: usize) -> Option<usize> {
    let (dots, _) = from_lines(lines);
    dots.iter().position(|&d| d == line_idx)
}

/// Move paragraph `k`. Between paragraphs it swaps; at either end it moves
/// round to the other side. Returns the new lines and the moved paragraph's
/// new index.
pub fn move_paragraph(
    paragraphs: &[Vec<String>],
    k: usize,
    direction: isize,
) -> Option<(Vec<Vec<String>>, usize)> {
    let n = paragraphs.len();
    if n <= 1 || k >= n {
        return None;
    }
    let mut paras = paragraphs.to_vec();
    let other = k as isize + direction;
    let dest = if other >= 0 && (other as usize) < n {
        let other = other as usize;
        paras.swap(k, other);
        other
    } else {
        let para = paras.remove(k);
        if direction < 0 {
            paras.push(para); // the first becomes the last
            paras.len() - 1
        } else {
            paras.insert(0, para); // the last becomes the first
            0
        }
    };
    Some((paras, dest))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn v(lines: &[&str]) -> Vec<String> {
        lines.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn paragraphs_are_the_blocks_between_dots() {
        let (dots, paras) = from_lines(&v(&[".", "a1", "a2", ".", "b"]));
        assert_eq!(dots, vec![0, 3]);
        assert_eq!(paras, vec![v(&["a1", "a2"]), v(&["b"])]);
    }

    #[test]
    fn without_dots_it_is_all_one_paragraph() {
        let (dots, paras) = from_lines(&v(&["a", "b"]));
        assert!(dots.is_empty());
        assert_eq!(paras, vec![v(&["a", "b"])]);
    }

    #[test]
    fn an_empty_paragraph_is_kept() {
        let (_, paras) = from_lines(&v(&[".", ".", "b"]));
        assert_eq!(paras, vec![Vec::<String>::new(), v(&["b"])]);
    }

    #[test]
    fn lines_and_paragraphs_roundtrip() {
        let lines = v(&[".", "a1", "a2", ".", "b"]);
        let (_, paras) = from_lines(&lines);
        assert_eq!(to_lines(&paras), lines);
    }

    #[test]
    fn the_dot_index_walks_the_blocks() {
        let (_, paras) = from_lines(&v(&[".", "a1", "a2", ".", "b"]));
        assert_eq!(dot_line_index(0, &paras), 0);
        assert_eq!(dot_line_index(1, &paras), 3); // dot, a1, a2 → 3
    }

    #[test]
    fn adjacent_paragraphs_swap() {
        let (_, paras) = from_lines(&v(&[".", "a", ".", "b"]));
        let (moved, dest) = move_paragraph(&paras, 0, 1).unwrap();
        assert_eq!(to_lines(&moved), v(&[".", "b", ".", "a"]));
        assert_eq!(dest, 1);
    }

    #[test]
    fn the_first_paragraph_moved_up_becomes_the_last() {
        let (_, paras) = from_lines(&v(&[".", "a", ".", "b", ".", "c"]));
        let (moved, dest) = move_paragraph(&paras, 0, -1).unwrap();
        assert_eq!(to_lines(&moved), v(&[".", "b", ".", "c", ".", "a"]));
        assert_eq!(dest, 2); // it moved, it did not swap with 'c'
    }

    #[test]
    fn the_last_paragraph_moved_down_becomes_the_first() {
        let (_, paras) = from_lines(&v(&[".", "a", ".", "b", ".", "c"]));
        let (moved, dest) = move_paragraph(&paras, 2, 1).unwrap();
        assert_eq!(to_lines(&moved), v(&[".", "c", ".", "a", ".", "b"]));
        assert_eq!(dest, 0);
    }

    #[test]
    fn a_multi_line_paragraph_moves_whole() {
        let (_, paras) = from_lines(&v(&[".", "a1", "a2", ".", "b"]));
        let (moved, _) = move_paragraph(&paras, 0, 1).unwrap();
        assert_eq!(to_lines(&moved), v(&[".", "b", ".", "a1", "a2"]));
    }

    #[test]
    fn a_lone_paragraph_does_not_move() {
        let (_, paras) = from_lines(&v(&[".", "sola"]));
        assert!(move_paragraph(&paras, 0, 1).is_none());
    }

    #[test]
    fn the_dot_tells_which_paragraph_it_opens() {
        let lines = v(&[".", "a", ".", "b"]);
        assert_eq!(para_at_dot(&lines, 0), Some(0));
        assert_eq!(para_at_dot(&lines, 2), Some(1));
        assert_eq!(para_at_dot(&lines, 1), None); // that's a content line
    }
}

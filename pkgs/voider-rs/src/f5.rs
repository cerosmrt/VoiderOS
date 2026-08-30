//! F5 — the active file seen as paragraphs, in order, so they can be moved.
//!
//! A port of the tokenising half of `f5_reorder_mixin.py`. A file is a sequence
//! of paragraphs, `.` separators and `/name` fences. Reordering swaps paragraphs
//! while separators and fences keep their positions, so a paragraph pushed past
//! a fence crosses into the next chapter and the fence itself never moves.

#![allow(dead_code)]

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Token {
    /// A run of text lines.
    Para(Vec<String>),
    /// A `/name` chapter fence, kept as its raw line.
    Mark(String),
    /// A `.` separator.
    Sep,
}

/// What the view draws: paragraphs (numbered) and fences. Separators are
/// implicit — paragraphs are drawn spaced apart.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Unit {
    Para { ordinal: usize, text: String },
    Mark { name: String },
}

/// Lines → tokens. Blank lines are dropped; a run of text lines is one paragraph.
pub fn tokens(lines: &[String]) -> Vec<Token> {
    let mut toks = Vec::new();
    let mut cur: Vec<String> = Vec::new();
    for raw in lines {
        let s = raw.trim();
        if s.starts_with('/') {
            if !cur.is_empty() {
                toks.push(Token::Para(std::mem::take(&mut cur)));
            }
            toks.push(Token::Mark(raw.clone()));
        } else if s == "." {
            if !cur.is_empty() {
                toks.push(Token::Para(std::mem::take(&mut cur)));
            }
            toks.push(Token::Sep);
        } else if !s.is_empty() {
            cur.push(raw.clone());
        }
    }
    if !cur.is_empty() {
        toks.push(Token::Para(cur));
    }
    toks
}

/// Tokens → lines. The inverse of `tokens`, keeping fences and separators.
pub fn flatten(toks: &[Token]) -> Vec<String> {
    let mut lines = Vec::new();
    for t in toks {
        match t {
            Token::Para(ls) => lines.extend(ls.iter().cloned()),
            Token::Mark(m) => lines.push(m.clone()),
            Token::Sep => lines.push(".".to_string()),
        }
    }
    lines
}

/// Token indices that are paragraphs, in order (position = ordinal).
pub fn para_positions(toks: &[Token]) -> Vec<usize> {
    toks.iter()
        .enumerate()
        .filter(|(_, t)| matches!(t, Token::Para(_)))
        .map(|(i, _)| i)
        .collect()
}

pub fn para_count(lines: &[String]) -> usize {
    para_positions(&tokens(lines)).len()
}

/// Swap the paragraph at `ordinal` with the one `direction` away. Separators and
/// fences keep their slots. Linear: the ends are a no-op. Returns the new lines
/// and the paragraph's new ordinal.
pub fn swap(lines: &[String], ordinal: usize, direction: isize) -> Option<(Vec<String>, usize)> {
    let mut toks = tokens(lines);
    let paras = para_positions(&toks);
    let j = ordinal as isize + direction;
    if j < 0 || ordinal >= paras.len() || j as usize >= paras.len() {
        return None; // linear: the ends don't wrap
    }
    let j = j as usize;
    toks.swap(paras[ordinal], paras[j]);
    Some((flatten(&toks), j))
}

/// The display units for the view.
pub fn units(lines: &[String]) -> Vec<Unit> {
    let mut units = Vec::new();
    let mut ordinal = 0usize;
    for t in tokens(lines) {
        match t {
            Token::Para(ls) => {
                units.push(Unit::Para {
                    ordinal,
                    text: ls.join(" "),
                });
                ordinal += 1;
            }
            Token::Mark(m) => units.push(Unit::Mark {
                name: m.trim().trim_start_matches('/').trim().to_string(),
            }),
            Token::Sep => {}
        }
    }
    units
}

/// Ordinal of the paragraph containing `line_idx`. A `.`/`/name`/blank line maps
/// to the paragraph before it, so entering F5 lands where you were in F2.
pub fn para_at_line(lines: &[String], line_idx: usize) -> usize {
    if lines.is_empty() {
        return 0;
    }
    let target = line_idx.min(lines.len() - 1);
    let mut ordinal: isize = -1;
    let mut last: isize = 0;
    let mut in_para = false;
    for (i, raw) in lines.iter().enumerate() {
        let s = raw.trim();
        let mut is_text = false;
        if s.starts_with('/') || s == "." {
            in_para = false;
        } else if !s.is_empty() {
            if !in_para {
                ordinal += 1;
                in_para = true;
            }
            last = ordinal;
            is_text = true;
        }
        if i == target {
            let v = if is_text { ordinal } else { last };
            return v.max(0) as usize;
        }
    }
    last.max(0) as usize
}

/// First line index of the paragraph with this ordinal.
pub fn line_of_para(lines: &[String], ordinal: usize) -> usize {
    let mut ord: isize = -1;
    let mut in_para = false;
    for (i, raw) in lines.iter().enumerate() {
        let s = raw.trim();
        if s.starts_with('/') || s == "." {
            in_para = false;
        } else if !s.is_empty() {
            if !in_para {
                ord += 1;
                in_para = true;
                if ord == ordinal as isize {
                    return i;
                }
            }
        }
    }
    0
}

/// Take a paragraph out of `lines`, returning it and what's left (leading,
/// doubled and trailing separators collapsed, never an empty file).
pub fn take_para(lines: &[String], ordinal: usize) -> Option<(Vec<String>, Vec<String>)> {
    let mut toks = tokens(lines);
    let paras = para_positions(&toks);
    let at = *paras.get(ordinal)?;
    let para = match toks.remove(at) {
        Token::Para(ls) => ls,
        _ => return None,
    };
    let mut rest = collapse_dots(&flatten(&toks));
    if rest.is_empty() {
        rest.push(".".to_string());
    }
    Some((para, rest))
}

/// Drop leading, doubled and trailing separators left behind by a move.
/// Sacar los separadores que sobran: al principio, al final, y los repetidos.
/// Lo usa F5 al mover párrafos y F2 al mandar texto afuera.
pub fn collapse_dots(lines: &[String]) -> Vec<String> {
    let mut out: Vec<String> = Vec::new();
    for l in lines {
        let is_dot = l.trim() == ".";
        if is_dot && out.last().map(|p: &String| p.trim() == ".").unwrap_or(true) {
            continue; // leading or doubled
        }
        out.push(l.clone());
    }
    while out.last().map(|l| l.trim() == ".").unwrap_or(false) {
        out.pop();
    }
    out
}

/// The chapter the paragraph sits under: the `/name` fence above it, or None
/// when it sits under none (then the view falls back to the file's own name).
pub fn chapter_of_para(lines: &[String], ordinal: usize) -> Option<String> {
    let mut ord: isize = -1;
    let mut mark: Option<String> = None;
    for t in tokens(lines) {
        match t {
            Token::Mark(m) => {
                let name = m.trim().trim_start_matches('/').trim().to_string();
                mark = if name.is_empty() { None } else { Some(name) };
            }
            Token::Para(_) => {
                ord += 1;
                if ord == ordinal as isize {
                    return mark;
                }
            }
            Token::Sep => {}
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    fn v(lines: &[&str]) -> Vec<String> {
        lines.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn tokenise_and_flatten_roundtrip() {
        let lines = v(&[".", "a1", "a2", ".", "b", "/Chap", "c"]);
        assert_eq!(flatten(&tokens(&lines)), lines);
    }

    #[test]
    fn blank_lines_are_dropped_and_runs_group() {
        let toks = tokens(&v(&["a1", "a2", "", ".", "b"]));
        assert_eq!(
            toks,
            vec![
                Token::Para(v(&["a1", "a2"])),
                Token::Sep,
                Token::Para(v(&["b"])),
            ]
        );
    }

    #[test]
    fn paragraphs_are_counted_ignoring_structure() {
        assert_eq!(para_count(&v(&[".", "p1", ".", "p2", "/A", "p3"])), 3);
    }

    #[test]
    fn swapping_within_a_chapter() {
        let (lines, ord) = swap(&v(&[".", "a", ".", "b"]), 0, 1).unwrap();
        assert_eq!(lines, v(&[".", "b", ".", "a"]));
        assert_eq!(ord, 1); // the cursor follows the paragraph
    }

    #[test]
    fn a_paragraph_crosses_the_fence_but_the_fence_stays() {
        let (lines, ord) = swap(&v(&["a", "/A", "b"]), 0, 1).unwrap();
        assert_eq!(lines, v(&["b", "/A", "a"])); // 'a' is now under /A
        assert_eq!(ord, 1);
    }

    #[test]
    fn a_whole_multi_line_paragraph_moves() {
        let (lines, _) = swap(&v(&[".", "a1", "a2", ".", "b"]), 0, 1).unwrap();
        assert_eq!(lines, v(&[".", "b", ".", "a1", "a2"]));
    }

    #[test]
    fn the_ends_do_not_wrap() {
        assert!(swap(&v(&[".", "a", ".", "b"]), 0, -1).is_none());
        assert!(swap(&v(&[".", "a", ".", "b"]), 1, 1).is_none());
    }

    #[test]
    fn units_number_paragraphs_and_name_fences() {
        let u = units(&v(&[".", "a1", "a2", "/Cap", "b"]));
        assert_eq!(
            u,
            vec![
                Unit::Para { ordinal: 0, text: "a1 a2".into() },
                Unit::Mark { name: "Cap".into() },
                Unit::Para { ordinal: 1, text: "b".into() },
            ]
        );
    }

    #[test]
    fn line_and_paragraph_map_onto_each_other() {
        let lines = v(&[".", "a", ".", "b", "/A", "c"]);
        assert_eq!(para_at_line(&lines, 1), 0); // 'a'
        assert_eq!(para_at_line(&lines, 3), 1); // 'b'
        assert_eq!(para_at_line(&lines, 4), 1); // the fence → the para before it
        assert_eq!(para_at_line(&lines, 5), 2); // 'c'
        assert_eq!(line_of_para(&lines, 0), 1);
        assert_eq!(line_of_para(&lines, 2), 5);
    }

    #[test]
    fn taking_a_paragraph_out_leaves_clean_separators() {
        let (para, rest) = take_para(&v(&[".", "a", ".", "b"]), 0).unwrap();
        assert_eq!(para, v(&["a"]));
        // Leading, doubled and trailing dots all go — the loader puts the
        // leading one back, so the file stays well-formed.
        assert_eq!(rest, v(&["b"]));
    }

    #[test]
    fn taking_the_only_paragraph_leaves_a_dot() {
        let (para, rest) = take_para(&v(&[".", "sola"]), 0).unwrap();
        assert_eq!(para, v(&["sola"]));
        assert_eq!(rest, v(&["."])); // never an empty file
    }

    #[test]
    fn the_chapter_is_the_fence_above_the_paragraph() {
        let lines = v(&["a", "/Segundo", "b"]);
        assert_eq!(chapter_of_para(&lines, 0), None); // before any fence
        assert_eq!(chapter_of_para(&lines, 1), Some("Segundo".into()));
    }
}

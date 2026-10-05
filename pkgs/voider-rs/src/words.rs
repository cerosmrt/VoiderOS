//! Alt+Left/Right — move a word along its line.
//!
//! A port of `_swap_words` from `f2_mixin.py`. The word under the caret swaps
//! with its neighbour and the caret follows it, so a word can be walked across
//! the sentence. Trailing sentence punctuation (`.!?…`) stays pinned at the end
//! — the word moves, the full stop doesn't. Moving past either end wraps.

#![allow(dead_code)]

/// Punctuation that belongs to the sentence, not to the last word.
const SENTENCE_END: [char; 4] = ['.', '!', '?', '…'];

/// Ctrl+Shift+E: give the line breaks back to a fused scriptio-continua line.
/// There the space bar RELEASES the line to the void, so a space inside a line
/// is the line break that was lost. A period already in the text also cuts;
/// nothing is ever added to a fragment.
pub fn split_on_spaces(text: &str) -> Vec<String> {
    text.split(|c: char| c.is_whitespace() || c == '.')
        .filter(|p| !p.is_empty())
        .map(str::to_string)
        .collect()
}

/// What a swap produced: the new line, where the caret lands, and — when a
/// block was selected — the selection that follows it.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Swapped {
    pub text: String,
    pub caret: usize,
    pub selection: Option<(usize, usize)>,
}

/// Swap the word at `caret` with its neighbour. Returns the new line and where
/// the caret should land — at the start of the word that moved. `None` when
/// there is nothing to swap.
pub fn swap_words(text: &str, caret: usize, direction: isize) -> Option<(String, usize)> {
    swap_block(text, caret, None, direction).map(|r| (r.text, r.caret))
}

/// Swap a block of words with its neighbour — a port of `_swap_words`.
///
/// With a `selection` (character offsets, start < end) every word it touches
/// moves together; without one, the word under `caret` (or the nearest, when the
/// caret sits in a gap). A word counts if its span OVERLAPS the selection, not
/// only if it fits inside: a selection stops right after the last letter, so
/// punctuation glued to a word (`realidad,`) would otherwise be left behind.
pub fn swap_block(
    text: &str,
    caret: usize,
    selection: Option<(usize, usize)>,
    direction: isize,
) -> Option<Swapped> {
    if text.trim().is_empty() {
        return None;
    }
    let chars: Vec<char> = text.chars().collect();

    // Peel off the sentence's closing punctuation, if any remains a word before it.
    let mut end = chars.len();
    while end > 0 && SENTENCE_END.contains(&chars[end - 1]) {
        end -= 1;
    }
    let (core, trailing): (Vec<char>, String) = if end < chars.len()
        && chars[..end].iter().collect::<String>().trim() != ""
    {
        (chars[..end].to_vec(), chars[end..].iter().collect())
    } else {
        (chars.clone(), String::new())
    };

    // Tokens, and where each sits inside `core` (in characters).
    let mut tokens: Vec<String> = Vec::new();
    let mut spans: Vec<(usize, usize)> = Vec::new();
    let mut i = 0;
    while i < core.len() {
        if core[i].is_whitespace() {
            i += 1;
            continue;
        }
        let start = i;
        while i < core.len() && !core[i].is_whitespace() {
            i += 1;
        }
        tokens.push(core[start..i].iter().collect());
        spans.push((start, i));
    }
    if tokens.len() < 2 {
        return None;
    }

    // The block to move: every word the selection overlaps, or the one under
    // the caret (or the nearest, when it sits in a gap).
    let block: Vec<usize> = match selection {
        Some((s, e)) if s < e => (0..spans.len())
            .filter(|&k| spans[k].0 < e && spans[k].1 > s)
            .collect(),
        _ => {
            let hit = spans.iter().position(|&(s, e)| s <= caret && caret <= e);
            vec![hit.unwrap_or_else(|| {
                (0..spans.len())
                    .min_by_key(|&k| {
                        let (s, e) = spans[k];
                        caret.abs_diff(s).min(caret.abs_diff(e))
                    })
                    .unwrap_or(0)
            })]
        }
    };
    let (b0, b1) = (*block.first()?, *block.last()?);
    let n = tokens.len();
    let moved = tokens[b0..=b1].to_vec();

    let (new_tokens, new_b0): (Vec<String>, usize) = if direction < 0 {
        if b0 == 0 {
            // Wrap: the block goes to the end.
            let mut t: Vec<String> = tokens[b1 + 1..].to_vec();
            let nb = t.len();
            t.extend(moved);
            (t, nb)
        } else {
            let mut t: Vec<String> = tokens[..b0 - 1].to_vec();
            t.extend(moved);
            t.push(tokens[b0 - 1].clone());
            t.extend_from_slice(&tokens[b1 + 1..]);
            (t, b0 - 1)
        }
    } else if b1 == n - 1 {
        // Wrap: the block goes to the start.
        let mut t = moved;
        t.extend_from_slice(&tokens[..b0]);
        (t, 0)
    } else {
        let mut t: Vec<String> = tokens[..b0].to_vec();
        t.push(tokens[b1 + 1].clone());
        t.extend(moved);
        t.extend_from_slice(&tokens[b1 + 2..]);
        (t, b0 + 1)
    };

    let new_text = format!("{}{}", new_tokens.join(" "), trailing);
    let new_b1 = new_b0 + (b1 - b0);
    // The caret (and any selection) lands on the start of the moved block.
    let start: usize = new_tokens[..new_b0].iter().map(|t| t.chars().count() + 1).sum();
    let stop: usize = new_tokens[..=new_b1]
        .iter()
        .map(|t| t.chars().count() + 1)
        .sum::<usize>()
        - 1;
    Some(Swapped {
        text: new_text,
        caret: start,
        selection: selection.filter(|&(s, e)| s < e).map(|_| (start, stop)),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_word_swaps_with_the_one_after_it() {
        let (text, caret) = swap_words("hola mundo cruel", 0, 1).unwrap();
        assert_eq!(text, "mundo hola cruel");
        assert_eq!(caret, 6); // the caret followed 'hola'
    }

    #[test]
    fn a_word_swaps_with_the_one_before_it() {
        // caret inside 'cruel'
        let (text, caret) = swap_words("hola mundo cruel", 12, -1).unwrap();
        assert_eq!(text, "hola cruel mundo");
        assert_eq!(caret, 5); // 'cruel' moved left, caret with it
    }

    #[test]
    fn the_full_stop_stays_at_the_end() {
        let (text, _) = swap_words("hola mundo cruel.", 0, 1).unwrap();
        assert_eq!(text, "mundo hola cruel."); // the '.' never travels
    }

    #[test]
    fn several_closing_marks_stay_too() {
        let (text, _) = swap_words("que decis...", 0, 1).unwrap();
        assert_eq!(text, "decis que...");
    }

    #[test]
    fn moving_past_the_end_wraps_to_the_start() {
        // caret inside 'cruel', the last word
        let (text, caret) = swap_words("hola mundo cruel", 12, 1).unwrap();
        assert_eq!(text, "cruel hola mundo");
        assert_eq!(caret, 0);
    }

    #[test]
    fn moving_past_the_start_wraps_to_the_end() {
        let (text, caret) = swap_words("hola mundo cruel", 0, -1).unwrap();
        assert_eq!(text, "mundo cruel hola");
        assert_eq!(caret, 12);
    }

    #[test]
    fn a_caret_between_words_takes_the_nearest() {
        // caret on the space after 'hola'
        let (text, _) = swap_words("hola mundo", 4, 1).unwrap();
        assert_eq!(text, "mundo hola");
    }

    #[test]
    fn one_word_or_empty_does_nothing() {
        assert!(swap_words("sola", 0, 1).is_none());
        assert!(swap_words("   ", 0, 1).is_none());
        assert!(swap_words("", 0, 1).is_none());
        assert!(swap_words("sola.", 0, 1).is_none());
    }

    #[test]
    fn extra_spaces_are_normalised_like_python() {
        let (text, _) = swap_words("hola   mundo", 0, 1).unwrap();
        assert_eq!(text, "mundo hola"); // join(' ') collapses the run
    }

    #[test]
    fn accents_count_as_single_characters() {
        // caret inside 'frío' (í is two bytes but one char)
        let (text, caret) = swap_words("hace frío hoy", 6, 1).unwrap();
        assert_eq!(text, "hace hoy frío");
        assert_eq!(caret, 9);
    }

    // ── split_on_spaces (test_split_spaces.py) ──────────────────────────────

    fn s(v: &[&str]) -> Vec<String> {
        v.iter().map(|x| x.to_string()).collect()
    }

    #[test]
    fn each_space_becomes_a_line() {
        assert_eq!(
            split_on_spaces("itisagreatmovie agretaactress agreatactor"),
            s(&["itisagreatmovie", "agretaactress", "agreatactor"])
        );
    }

    #[test]
    fn an_existing_period_also_breaks() {
        assert_eq!(split_on_spaces("uno.dos tres"), s(&["uno", "dos", "tres"]));
    }

    #[test]
    fn runs_of_whitespace_collapse_and_edges_are_trimmed() {
        assert_eq!(split_on_spaces("a   b\tc"), s(&["a", "b", "c"]));
        assert_eq!(split_on_spaces("  a b  "), s(&["a", "b"]));
    }

    #[test]
    fn nothing_gets_added_to_a_fragment() {
        assert_eq!(
            split_on_spaces("isthatit? unasolapalabra"),
            s(&["isthatit?", "unasolapalabra"])
        );
        assert_eq!(split_on_spaces("snapback, counterjab"), s(&["snapback,", "counterjab"]));
    }

    #[test]
    fn a_line_with_no_space_is_left_alone_and_an_empty_one_yields_nothing() {
        assert_eq!(split_on_spaces("unasolapalabra"), s(&["unasolapalabra"]));
        assert!(split_on_spaces("   ").is_empty());
    }
    // ── a SELECTED block moves as one (test_swap_words_selection.py) ─────────

    fn block(text: &str, sel: (usize, usize), dir: isize) -> (String, Option<(usize, usize)>) {
        let r = swap_block(text, sel.1, Some(sel), dir).unwrap();
        (r.text, r.selection)
    }

    #[test]
    fn a_selection_stopping_before_glued_punctuation_still_moves_the_whole_word() {
        // "realidad," is ONE token: the comma has no space before it. A selection
        // made by shift-arrow stops after the last letter, never reaching the
        // comma — the word must not be left behind.
        let text = "eje aplica a la realidad, funciona bien";
        let start = text.find("aplica").unwrap();
        let end = start + "aplica a la realidad".chars().count();
        let (new, sel) = block(text, (start, end), -1);
        assert_eq!(new, "aplica a la realidad, eje funciona bien");
        assert_eq!(sel, Some((0, "aplica a la realidad,".chars().count())));
    }

    #[test]
    fn a_selection_reaching_the_comma_works_too() {
        let text = "eje aplica a la realidad, funciona bien";
        let start = text.find("aplica").unwrap();
        let end = start + "aplica a la realidad,".chars().count();
        assert_eq!(block(text, (start, end), -1).0, "aplica a la realidad, eje funciona bien");
    }

    #[test]
    fn a_selected_block_moves_right_past_the_next_word() {
        let (new, sel) = block("a b c d", (2, 5), 1); // "b c"
        assert_eq!(new, "a d b c");
        assert_eq!(sel, Some((4, 7))); // the selection follows the block
    }

    #[test]
    fn a_selected_block_at_the_start_wraps_to_the_end_going_left() {
        assert_eq!(block("a b c", (0, 3), -1).0, "c a b");
    }

    #[test]
    fn a_selected_block_at_the_end_wraps_to_the_start_going_right() {
        assert_eq!(block("a b c", (2, 5), 1).0, "b c a");
    }

    #[test]
    fn closing_punctuation_stays_put_when_a_block_moves() {
        assert_eq!(block("uno dos tres.", (0, 7), 1).0, "tres uno dos.");
    }

    #[test]
    fn with_no_selection_the_word_under_the_caret_moves_alone() {
        let r = swap_block("hola mundo cruel", 0, None, 1).unwrap();
        assert_eq!(r.text, "mundo hola cruel");
        assert_eq!(r.caret, 6);
        assert_eq!(r.selection, None);
    }

}

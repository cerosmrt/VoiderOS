//! Alt+Left/Right — move a word along its line.
//!
//! A port of `_swap_words` from `f2_mixin.py`. The word under the caret swaps
//! with its neighbour and the caret follows it, so a word can be walked across
//! the sentence. Trailing sentence punctuation (`.!?…`) stays pinned at the end
//! — the word moves, the full stop doesn't. Moving past either end wraps.

#![allow(dead_code)]

/// Punctuation that belongs to the sentence, not to the last word.
const SENTENCE_END: [char; 4] = ['.', '!', '?', '…'];

/// Swap the word at `caret` (a character index) with its neighbour.
/// Returns the new line and where the caret should land — at the start of the
/// word that moved. `None` when there is nothing to swap.
pub fn swap_words(text: &str, caret: usize, direction: isize) -> Option<(String, usize)> {
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

    // Which token the caret is on — or the nearest, when it sits in a gap.
    let b = spans
        .iter()
        .position(|&(s, e)| s <= caret && caret <= e)
        .unwrap_or_else(|| {
            (0..spans.len())
                .min_by_key(|&i| {
                    let (s, e) = spans[i];
                    caret.abs_diff(s).min(caret.abs_diff(e))
                })
                .unwrap_or(0)
        });

    let n = tokens.len();
    let (new_tokens, new_b) = if direction < 0 {
        if b == 0 {
            // Wrap: the word goes to the end.
            let mut t: Vec<String> = tokens[1..].to_vec();
            t.push(tokens[0].clone());
            let nb = t.len() - 1;
            (t, nb)
        } else {
            let mut t = tokens.clone();
            t.swap(b - 1, b);
            (t, b - 1)
        }
    } else if b == n - 1 {
        // Wrap: the word goes to the start.
        let mut t = vec![tokens[n - 1].clone()];
        t.extend_from_slice(&tokens[..n - 1]);
        (t, 0)
    } else {
        let mut t = tokens.clone();
        t.swap(b, b + 1);
        (t, b + 1)
    };

    let new_text = format!("{}{}", new_tokens.join(" "), trailing);
    // The caret lands at the start of the word that moved.
    let new_caret: usize = new_tokens[..new_b]
        .iter()
        .map(|t| t.chars().count() + 1)
        .sum();
    Some((new_text, new_caret))
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
}

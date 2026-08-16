//! Reformat — one sentence per line.
//!
//! A port of `reformat_active_file` from `io_mixin.py`. Pasted prose arrives as
//! long paragraphs; Voider wants a line per sentence so lines can be moved,
//! recirculated and read one at a time. Blank lines become `.` separators.
//!
//! A full stop only ends a sentence when what follows starts a new one, and
//! never after an ellipsis, an abbreviation, an initial, or inside a decimal.

#![allow(dead_code)]

/// Abbreviations that do not end a sentence.
const ABBREVS: [&str; 24] = [
    "mr", "dr", "mrs", "ms", "st", "prof", "jr", "sr", "ud", "vd", "pág", "núm", "art", "ed",
    "vol", "fig", "cap", "e.g", "i.e", "etc", "vs", "cf", "no", "sra",
];

/// Punctuation that can trail a sentence's final mark: `.»` `?"` `.)`.
const TRAILING: [char; 8] = ['.', '!', '?', '\'', '"', '»', ')', '…'];

/// Reformat whole lines: blank lines become separators, prose is split into
/// sentences, and a leading separator is guaranteed.
pub fn reformat(lines: &[String]) -> Vec<String> {
    let mut out: Vec<String> = Vec::new();
    let mut para: Vec<String> = Vec::new();

    // A paragraph ends at a blank line or an existing separator; its lines are
    // joined back together before being split into sentences, so a sentence
    // broken across two lines is healed.
    let flush = |para: &mut Vec<String>, out: &mut Vec<String>| {
        if para.is_empty() {
            return;
        }
        let joined = para.join(" ");
        para.clear();
        if out.last().map(|l| l != ".").unwrap_or(true) {
            out.push(".".to_string());
        }
        out.extend(split_sentences(&joined));
    };

    for raw in lines {
        let s = raw.trim();
        if s.is_empty() || s == "." {
            flush(&mut para, &mut out);
        } else {
            para.push(s.to_string());
        }
    }
    flush(&mut para, &mut out);

    if out.is_empty() {
        out.push(".".to_string());
    }
    out
}

/// Split one paragraph's text into sentences.
pub fn split_sentences(text: &str) -> Vec<String> {
    let chars: Vec<char> = text.chars().collect();
    let mut sentences: Vec<String> = Vec::new();
    let mut start = 0usize;
    let mut i = 0usize;

    while i < chars.len() {
        let ch = chars[i];
        if ch != '.' && ch != '!' && ch != '?' {
            i += 1;
            continue;
        }
        if ch == '.' && is_exception(&chars, i) {
            i += 1;
            continue;
        }
        // Swallow the marks that belong to this sentence's ending.
        let mut end = i + 1;
        while end < chars.len() && TRAILING.contains(&chars[end]) {
            end += 1;
        }
        let rest: String = chars[end..].iter().collect();
        if rest.trim().is_empty() {
            let s: String = chars[start..end].iter().collect();
            let s = s.trim().to_string();
            if !s.is_empty() {
                sentences.push(s);
            }
            start = end;
            i = end;
            continue;
        }
        // A new sentence only begins on whitespace followed by an opening.
        let after: Vec<char> = chars[end..].to_vec();
        let spaces = after.iter().take_while(|c| c.is_whitespace()).count();
        let opens = after
            .get(spaces)
            .is_some_and(|c| c.is_uppercase() || ['"', '«', '¿', '¡', '('].contains(c));
        if spaces > 0 && opens {
            let s: String = chars[start..end].iter().collect();
            let s = s.trim().to_string();
            if !s.is_empty() {
                sentences.push(s);
            }
            start = end + spaces;
            i = start;
            continue;
        }
        i += 1;
    }
    let tail: String = chars[start.min(chars.len())..].iter().collect();
    let tail = tail.trim().to_string();
    if !tail.is_empty() {
        sentences.push(tail);
    }
    sentences
}

/// Whether the dot at `pos` (a character index) is *not* a sentence boundary.
pub fn is_exception(chars: &[char], pos: usize) -> bool {
    // An ellipsis, from either side of it.
    if chars.get(pos..pos + 3).is_some_and(|w| w == ['.', '.', '.']) {
        return true;
    }
    if pos >= 2 && chars[pos - 2] == '.' && chars[pos - 1] == '.' {
        return true;
    }
    if pos >= 1 && chars[pos - 1] == '.' {
        return true;
    }
    if chars.get(pos + 1).is_some_and(|c| *c == '.') {
        return true;
    }
    // A decimal number: 3.50
    if pos > 0
        && chars[pos - 1].is_ascii_digit()
        && chars.get(pos + 1).is_some_and(char::is_ascii_digit)
    {
        return true;
    }
    // A standalone initial: J. R.
    if pos > 0 && chars[pos - 1].is_uppercase() && (pos == 1 || chars[pos - 2].is_whitespace()) {
        return true;
    }
    // A known abbreviation.
    let mut word_start = pos;
    while word_start > 0 && chars[word_start - 1].is_alphabetic() {
        word_start -= 1;
    }
    let word: String = chars[word_start..pos]
        .iter()
        .flat_map(|c| c.to_lowercase())
        .collect();
    ABBREVS.contains(&word.as_str())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn v(lines: &[&str]) -> Vec<String> {
        lines.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn a_paragraph_becomes_one_line_per_sentence() {
        assert_eq!(
            split_sentences("Una frase. Otra frase. Y una tercera."),
            v(&["Una frase.", "Otra frase.", "Y una tercera."])
        );
    }

    #[test]
    fn question_and_exclamation_end_sentences_too() {
        assert_eq!(
            split_sentences("¿Quién va? Nadie. ¡Vamos!"),
            v(&["¿Quién va?", "Nadie.", "¡Vamos!"])
        );
    }

    #[test]
    fn an_ellipsis_does_not_split() {
        assert_eq!(
            split_sentences("Pensé... Que no vendrías."),
            v(&["Pensé... Que no vendrías."])
        );
    }

    #[test]
    fn abbreviations_do_not_split() {
        assert_eq!(
            split_sentences("Lo dijo el Dr. Martínez ayer."),
            v(&["Lo dijo el Dr. Martínez ayer."])
        );
        assert_eq!(
            split_sentences("Ver cap. Segundo del libro."),
            v(&["Ver cap. Segundo del libro."])
        );
    }

    #[test]
    fn initials_do_not_split() {
        assert_eq!(
            split_sentences("Escribió J. R. Tolkien entero."),
            v(&["Escribió J. R. Tolkien entero."])
        );
    }

    #[test]
    fn decimals_do_not_split() {
        assert_eq!(
            split_sentences("Costó 3.50 pesos ayer."),
            v(&["Costó 3.50 pesos ayer."])
        );
    }

    #[test]
    fn a_lowercase_start_does_not_split() {
        // ". y" is not a new sentence — it's a list or a stumble
        assert_eq!(
            split_sentences("uno. y dos"),
            v(&["uno. y dos"])
        );
    }

    #[test]
    fn closing_punctuation_stays_with_its_sentence() {
        assert_eq!(
            split_sentences("Dijo «basta». Se fue."),
            v(&["Dijo «basta».", "Se fue."])
        );
    }

    #[test]
    fn an_opening_mark_starts_a_sentence() {
        assert_eq!(
            split_sentences("Se fue. «Basta» dijo."),
            v(&["Se fue.", "«Basta» dijo."])
        );
    }

    #[test]
    fn text_without_a_final_stop_is_still_a_sentence() {
        assert_eq!(split_sentences("Sin punto final"), v(&["Sin punto final"]));
    }

    #[test]
    fn empty_text_gives_nothing() {
        assert!(split_sentences("   ").is_empty());
        assert!(split_sentences("").is_empty());
    }

    #[test]
    fn accents_survive_the_split() {
        assert_eq!(
            split_sentences("Está acá. Él también."),
            v(&["Está acá.", "Él también."])
        );
    }

    // ── whole-file reformat ───────────────────────────────────────────────────

    #[test]
    fn blank_lines_become_separators() {
        let out = reformat(&v(&["Primer parrafo.", "", "Segundo parrafo."]));
        assert_eq!(out, v(&[".", "Primer parrafo.", ".", "Segundo parrafo."]));
    }

    #[test]
    fn a_pasted_block_is_broken_into_lines() {
        let out = reformat(&v(&["Una frase. Otra frase."]));
        assert_eq!(out, v(&[".", "Una frase.", "Otra frase."]));
    }

    #[test]
    fn existing_separators_are_kept() {
        let out = reformat(&v(&[".", "Sola.", ".", "Otra."]));
        assert_eq!(out, v(&[".", "Sola.", ".", "Otra."]));
    }

    #[test]
    fn runs_of_blank_lines_collapse_to_one_separator() {
        let out = reformat(&v(&["Uno.", "", "", "Dos."]));
        assert_eq!(out, v(&[".", "Uno.", ".", "Dos."]));
    }

    #[test]
    fn an_empty_file_becomes_a_single_separator() {
        assert_eq!(reformat(&v(&[])), v(&["."]));
        assert_eq!(reformat(&v(&["", "  "])), v(&["."]));
    }

    #[test]
    fn lines_of_one_paragraph_are_joined_before_splitting() {
        // a paragraph broken mid-sentence across lines is put back together
        let out = reformat(&v(&["Una frase que sigue", "en la linea de abajo. Y otra."]));
        assert_eq!(
            out,
            v(&[".", "Una frase que sigue en la linea de abajo.", "Y otra."])
        );
    }
}

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

/// Reformat lines the way Voider's own format expects: every line is its own
/// unit — NEVER joined with its neighbour, because by the time text reaches
/// `self.ring.lines` (this function's real input) `load_doc` has already
/// dropped blank lines and guaranteed a leading `.`, so there is no paragraph
/// boundary left to detect. This mirrors the "already in Voider format" branch
/// of `reformat_active_file` — the only branch reachable FROM THE RING. The
/// raw-prose branch lives in `reformat_prose` below and fires on text that
/// never passed through `load_doc`: F9 writes what you typed straight to disk
/// and reformats that.
///
/// A run of separator-only lines (blank, `.`, `..`, `...`) collapses to one
/// `.`; a line with several sentences splits into several lines; a line with
/// none (a `/name` marker, an unfinished thought) passes through unchanged —
/// so a marker always lands on its own line without needing special-casing.
pub fn reformat(lines: &[String]) -> Vec<String> {
    let mut out: Vec<String> = Vec::new();
    let mut prev_sep = false;

    for raw in lines {
        let trimmed = raw.trim();
        let is_sep = trimmed.is_empty() || trimmed.chars().all(|c| c == '.');
        if is_sep {
            if !prev_sep && !out.is_empty() {
                out.push(".".to_string());
            }
            prev_sep = true;
            continue;
        }
        let normalised = normalise_spaces(trimmed);
        let split = split_sentences(&normalised);
        if !split.is_empty() {
            out.extend(split);
        } else if !normalised.is_empty() {
            out.push(normalised);
        }
        prev_sep = false;
    }

    if out.first().map(|l| l != ".").unwrap_or(true) {
        out.insert(0, ".".to_string());
    }
    out
}

/// Reformat RAW PROSE — the other branch of `reformat_active_file`, the one
/// that fires on a file whose text does not start with `.`.
///
/// Unreachable from the ring (see `reformat` above), but F9 makes it reachable:
/// the prose editor writes what you typed straight to disk, blank lines and
/// all, and only then reformats it in place. So here a blank line IS a
/// paragraph boundary, and the lines inside one paragraph ARE joined before
/// being split into sentences — a paragraph you typed as flowing prose across
/// several wrapped lines comes back as one sentence per line.
///
/// A `/name` marker still never merges into the prose around it: it flushes
/// whatever came before and takes its own line, so `texto\n/Capitulo` stays
/// split and ready for Ctrl+Shift+S.
pub fn reformat_prose(text: &str) -> Vec<String> {
    let mut out: Vec<String> = Vec::new();

    for para in split_paragraphs(text.trim()) {
        if para.trim().is_empty() {
            continue;
        }
        if !out.is_empty() {
            out.push(".".to_string());
        }
        if para.trim() == "." {
            continue;
        }
        let mut prose: Vec<String> = Vec::new();
        for raw_line in para.lines() {
            let s = raw_line.trim();
            if s.starts_with('/') {
                flush_prose(&mut prose, &mut out);
                out.push(s.to_string());
            } else if !s.is_empty() {
                prose.push(s.to_string());
            }
        }
        flush_prose(&mut prose, &mut out);
    }

    if out.first().map(|l| l != ".").unwrap_or(true) {
        out.insert(0, ".".to_string());
    }
    out
}

/// Join a paragraph's prose lines into one string and split it into sentences.
fn flush_prose(buf: &mut Vec<String>, out: &mut Vec<String>) {
    if buf.is_empty() {
        return;
    }
    let joined = normalise_spaces(&buf.join(" "));
    if !joined.is_empty() {
        out.extend(split_sentences(&joined));
    }
    buf.clear();
}

/// Split on blank lines (a run of them counts once), the Rust of
/// `re.split(r'\n\s*\n+', raw)`.
fn split_paragraphs(text: &str) -> Vec<String> {
    let mut paras = Vec::new();
    let mut cur: Vec<&str> = Vec::new();
    for line in text.lines() {
        if line.trim().is_empty() {
            if !cur.is_empty() {
                paras.push(cur.join("\n"));
                cur.clear();
            }
        } else {
            cur.push(line);
        }
    }
    if !cur.is_empty() {
        paras.push(cur.join("\n"));
    }
    paras
}

/// The dot-model → paragraph strings, for showing a file as flowing prose.
/// A port of `lines_to_paragraphs` from `reading_page.py`.
pub fn lines_to_paragraphs(lines: &[String]) -> Vec<String> {
    let mut paras: Vec<String> = Vec::new();
    let mut cur: Vec<String> = Vec::new();
    for raw in lines {
        let s = raw.trim();
        if s == "." {
            if !cur.is_empty() {
                paras.push(cur.join(" "));
                cur.clear();
            }
        } else if !s.is_empty() && s != "ø" {
            cur.push(s.to_string());
        }
    }
    if !cur.is_empty() {
        paras.push(cur.join(" "));
    }
    paras
}

fn normalise_spaces(s: &str) -> String {
    s.split_whitespace().collect::<Vec<_>>().join(" ")
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
    fn each_line_is_reformatted_on_its_own_never_joined_with_its_neighbour() {
        // Matches the Python's "already in Voider format" branch — the only one
        // reachable once a file has passed through load_doc, which is always,
        // by the time anything reaches the ring. A prior version of this
        // function joined adjacent lines, which does not match that branch.
        let out = reformat(&v(&["Una frase que sigue", "en la linea de abajo. Y otra."]));
        assert_eq!(
            out,
            v(&[".", "Una frase que sigue", "en la linea de abajo.", "Y otra."])
        );
    }

    #[test]
    fn a_slash_marker_line_is_never_absorbed_into_the_prose_around_it() {
        let out = reformat(&v(&[
            ".", "El texto del parrafo.", "/El Logos", ".", "Otro parrafo.", "/El Altar",
        ]));
        assert_eq!(
            out,
            v(&[
                ".", "El texto del parrafo.", "/El Logos", ".", "Otro parrafo.", "/El Altar",
            ])
        );
    }

    #[test]
    fn a_multi_sentence_line_still_splits_on_its_own() {
        let out = reformat(&v(&[".", "One. Two. Three."]));
        assert_eq!(out, v(&[".", "One.", "Two.", "Three."]));
    }

    #[test]
    fn a_run_of_junk_dot_lines_collapses_to_one_separator() {
        let out = reformat(&v(&[".", "A.", "..", ".", "...", "B."]));
        assert_eq!(out, v(&[".", "A.", ".", "B."]));
    }

    #[test]
    fn reformatting_twice_is_stable() {
        let once = reformat(&v(&[".", "One. Two.", ".", "Three."]));
        let twice = reformat(&once);
        assert_eq!(once, twice);
    }

    // ── raw prose (the F9 branch) ─────────────────────────────────────────────

    #[test]
    fn prose_paragraphs_become_dot_groups_and_sentences_become_lines() {
        // The Python's own test_editor_view expectation, exactly.
        let out = reformat_prose("First sentence. Second sentence.\n\nSecond paragraph here.");
        assert_eq!(
            out,
            v(&[
                ".",
                "First sentence.",
                "Second sentence.",
                ".",
                "Second paragraph here.",
            ])
        );
    }

    #[test]
    fn wrapped_lines_of_one_prose_paragraph_are_joined_before_splitting() {
        // The opposite of `reformat`: here a line break inside a paragraph is
        // just wrapping, so the lines join and then split at the sentence.
        let out = reformat_prose("Una frase que sigue\nen la linea de abajo. Y otra.");
        assert_eq!(out, v(&[".", "Una frase que sigue en la linea de abajo.", "Y otra."]));
    }

    #[test]
    fn a_run_of_blank_lines_is_a_single_paragraph_break() {
        let out = reformat_prose("Uno.\n\n\n\nDos.");
        assert_eq!(out, v(&[".", "Uno.", ".", "Dos."]));
    }

    #[test]
    fn a_prose_marker_keeps_its_own_line_and_flushes_what_came_before() {
        let out = reformat_prose("El texto del parrafo.\n/El Logos\n\nOtro parrafo.");
        assert_eq!(
            out,
            v(&[".", "El texto del parrafo.", "/El Logos", ".", "Otro parrafo."])
        );
    }

    #[test]
    fn empty_prose_becomes_a_single_separator() {
        assert_eq!(reformat_prose(""), v(&["."]));
        assert_eq!(reformat_prose("   \n\n  "), v(&["."]));
    }

    #[test]
    fn prose_reformatted_twice_is_stable_through_the_dot_model() {
        let once = reformat_prose("Una frase. Otra frase.\n\nSegundo parrafo.");
        // Round-tripping back out to prose and in again must not drift.
        let prose = lines_to_paragraphs(&once).join("\n\n");
        assert_eq!(reformat_prose(&prose), once);
    }

    // ── the dot model as prose ────────────────────────────────────────────────

    #[test]
    fn lines_join_into_a_paragraph_per_dot_group() {
        let paras = lines_to_paragraphs(&v(&[".", "a", "b", ".", "c"]));
        assert_eq!(paras, v(&["a b", "c"]));
    }

    #[test]
    fn the_zero_glyph_is_never_prose() {
        let paras = lines_to_paragraphs(&v(&[".", "ø", "texto"]));
        assert_eq!(paras, v(&["texto"]));
    }

    #[test]
    fn a_file_of_only_separators_has_no_paragraphs() {
        assert!(lines_to_paragraphs(&v(&[".", ".", "."])).is_empty());
    }
}

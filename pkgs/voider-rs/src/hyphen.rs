//! Hyphenation: Liang's patterns, with the dictionaries the Python's `pyphen` uses.
//!
//! A port of `hyphenate_text` / `guess_lang` from `reading_page.py`. The patterns are
//! pyphen's own dictionaries (copied into `src/hyph/`, with their licences), read
//! and applied with the same algorithm, so a word breaks where it breaks in the
//! Python. The language is guessed per paragraph from its function words, because
//! the book is in two languages and has no single default.

#![allow(dead_code)]

use std::collections::HashMap;
use std::sync::OnceLock;

/// A set of patterns for one language.
pub struct Hyphenator {
    /// Letters of a pattern → the digit before each of them, and one after the last.
    patterns: HashMap<String, Vec<u8>>,
    max_len: usize,
}

impl Hyphenator {
    /// Read a hyphenation dictionary (the `.dic` files of LibreOffice).
    pub fn parse(dic: &str) -> Hyphenator {
        let mut patterns: HashMap<String, Vec<u8>> = HashMap::new();
        let mut max_len = 0;
        for (n, raw) in dic.lines().enumerate() {
            let line = raw.trim();
            // The charset on the first line, comments, and the directives
            // (LEFTHYPHENMIN and the like) are not patterns.
            if line.is_empty()
                || line.starts_with('%')
                || (n == 0 && line.eq_ignore_ascii_case("utf-8"))
                || line.chars().next().is_some_and(|c| c.is_ascii_uppercase())
            {
                continue;
            }
            // A digit before a letter is that letter's weight; one after the last
            // letter is the weight of the gap at its end.
            let (mut letters, mut values, mut pending) = (String::new(), Vec::new(), 0u8);
            for c in line.chars() {
                if let Some(d) = c.to_digit(10) {
                    pending = d as u8;
                } else {
                    values.push(pending);
                    pending = 0;
                    letters.extend(c.to_lowercase());
                }
            }
            values.push(pending);
            max_len = max_len.max(letters.chars().count());
            patterns.insert(letters, values);
        }
        Hyphenator { patterns, max_len }
    }


    /// The Spanish dictionary, read once.
    pub fn es() -> &'static Hyphenator {
        static H: OnceLock<Hyphenator> = OnceLock::new();
        H.get_or_init(|| Hyphenator::parse(include_str!("hyph/hyph_es.dic")))
    }

    /// The American English dictionary, read once.
    pub fn en_us() -> &'static Hyphenator {
        static H: OnceLock<Hyphenator> = OnceLock::new();
        H.get_or_init(|| Hyphenator::parse(include_str!("hyph/hyph_en_US.dic")))
    }

    /// Where `word` may break: character indices, never within `left` characters of the
    /// start or `right` of the end.
    pub fn positions(&self, word: &str, left: usize, right: usize) -> Vec<usize> {
        let n = word.chars().count();
        if n == 0 {
            return Vec::new();
        }
        // Liang: lay the patterns over `.word.` and keep, for every gap, the largest
        // weight any of them gives it; an odd one is a place to break.
        let wrapped: Vec<char> = std::iter::once('.')
            .chain(word.chars().map(|c| c.to_lowercase().next().unwrap_or(c)))
            .chain(std::iter::once('.'))
            .collect();
        let mut weight = vec![0u8; wrapped.len() + 1];
        for i in 0..wrapped.len().saturating_sub(1) {
            for j in (i + 1)..=(i + self.max_len).min(wrapped.len()) {
                let key: String = wrapped[i..j].iter().collect();
                if let Some(values) = self.patterns.get(&key) {
                    for (k, &v) in values.iter().enumerate() {
                        if v > weight[i + k] {
                            weight[i + k] = v;
                        }
                    }
                }
            }
        }
        // Gap `g` of `.word.` sits before character `g - 1` of the word.
        weight
            .iter()
            .enumerate()
            .filter(|(_, w)| **w % 2 == 1)
            .filter_map(|(g, _)| g.checked_sub(1))
            .filter(|&p| p >= left && p + right <= n)
            .collect()
    }


    /// `word` with `hyphen` at every break (pyphen's `inserted`), left and right minimum 2.
    pub fn inserted(&self, word: &str, hyphen: &str) -> String {
        let breaks = self.positions(word, 2, 2);
        let mut out = String::with_capacity(word.len() + breaks.len() * hyphen.len());
        for (i, c) in word.chars().enumerate() {
            if breaks.contains(&i) {
                out.push_str(hyphen);
            }
            out.push(c);
        }
        out
    }

}

/// The languages the book is written in.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Lang {
    Es,
    En,
}

impl Lang {
    pub fn hyphenator(self) -> &'static Hyphenator {
        match self {
            Lang::Es => Hyphenator::es(),
            Lang::En => Hyphenator::en_us(),
        }
    }
}

/// How a book is hyphenated (the config's `reading_hyphen_lang`).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum Mode {
    /// Never.
    Off,
    /// Guess each paragraph's language — the book is in two.
    #[default]
    Auto,
    /// Always this language.
    Fixed(Lang),
}

impl Mode {
    /// Read the config value: `auto`, `es` / `es_ES`, `en` / `en_US`; anything empty
    /// or unknown (including `off`) means no hyphenation, as a falsy value does in
    /// the Python.
    pub fn from_config(value: &str) -> Mode {
        match value.trim().to_lowercase().as_str() {
            "auto" => Mode::Auto,
            "es" | "es_es" => Mode::Fixed(Lang::Es),
            "en" | "en_us" => Mode::Fixed(Lang::En),
            _ => Mode::Off,
        }
    }

    /// What goes in the config file.
    pub fn to_config(self) -> &'static str {
        match self {
            Mode::Off => "",
            Mode::Auto => "auto",
            Mode::Fixed(Lang::Es) => "es_ES",
            Mode::Fixed(Lang::En) => "en_US",
        }
    }

    /// The language to hyphenate `paragraph` in, if any.
    pub fn lang_for(self, paragraph: &str) -> Option<Lang> {
        match self {
            Mode::Off => None,
            Mode::Auto => guess_lang(paragraph),
            Mode::Fixed(l) => Some(l),
        }
    }
}

/// Best-effort language of a paragraph, by function words and Spanish diacritics.
/// `None` when there is no signal — then it is not hyphenated.
pub fn guess_lang(text: &str) -> Option<Lang> {
    const ES: &[&str] = &[
        "el", "la", "de", "que", "y", "en", "los", "las", "un", "una", "por", "con", "no", "se", "su", "lo",
        "le", "del", "al", "es", "son", "como", "para", "más", "pero", "sus", "me", "mi", "te", "ya", "muy",
    ];
    const EN: &[&str] = &[
        "the", "of", "and", "to", "in", "is", "that", "it", "for", "you", "with", "on", "as", "are", "be",
        "this", "his", "was", "from", "they", "not", "but", "have", "had", "your",
    ];
    let strip: &[char] = &['.', ',', ';', ':', '!', '?', '¿', '¡', '"', '\'', '(', ')', '[', ']', '—', '–', '-'];
    let (mut es, mut en) = (0, 0);
    for w in text.split_whitespace() {
        let w = w.trim_matches(strip).to_lowercase();
        if ES.contains(&w.as_str()) {
            es += 1;
        }
        if EN.contains(&w.as_str()) {
            en += 1;
        }
    }
    if text.chars().any(|c| "áéíóúñü¿¡".contains(c)) {
        es += 2;
    }
    match (es, en) {
        (0, 0) => None,
        _ if es >= en => Some(Lang::Es),
        _ => Some(Lang::En),
    }
}


/// The break points (character indices) of a token, in the language of its paragraph;
/// tokens of four letters or fewer are left whole, as in the Python.
pub fn break_points(token: &str, lang: Option<Lang>) -> Vec<usize> {
    match lang {
        Some(l) if token.chars().count() > 4 => l.hyphenator().positions(token, 2, 2),
        _ => Vec::new(),
    }
}


#[cfg(test)]
mod tests {
    use super::*;

    const ES_REF: &[(&str, &str)] = &[
        ("hermosamente", "her-mo-sa-men-te"),
        ("organización", "or-ga-ni-za-ción"),
        ("ejemplo", "ejem-plo"),
        ("constitución", "cons-ti-tu-ción"),
        ("extraordinario", "ex-tra-or-di-na-rio"),
        ("biblioteca", "bi-blio-te-ca"),
        ("desarrollo", "de-sa-rro-llo"),
        ("pensamiento", "pen-sa-mien-to"),
        ("conocimiento", "co-no-ci-mien-to"),
        ("universidad", "uni-ver-si-dad"),
        ("historia", "his-to-ria"),
        ("cuentos", "cuen-tos"),
        ("hombre", "hom-bre"),
        ("siempre", "siem-pre"),
        ("dificultad", "di-fi-cul-tad"),
        ("transformación", "trans-for-ma-ción"),
        ("aprendizaje", "apren-di-za-je"),
        ("tradición", "tra-di-ción"),
        ("metafísica", "me-ta-fí-si-ca"),
        ("hermético", "her-mé-ti-co"),
        ("católico", "ca-tó-li-co"),
        ("contemplación", "con-tem-pla-ción"),
        ("espiritualidad", "es-pi-ri-tua-li-dad"),
        ("sabiduría", "sa-bi-du-ría"),
        ("instrucciones", "ins-truc-cio-nes"),
        ("arquitectura", "ar-qui-tec-tu-ra"),
        ("silencio", "si-len-cio"),
        ("soberanía", "so-be-ra-nía"),
        ("atención", "aten-ción"),
        ("creación", "crea-ción"),
        ("aeroplano", "aero-pla-no"),
        ("construcción", "cons-truc-ción"),
        ("perenne", "pe-ren-ne"),
        ("filosofía", "fi-lo-so-fía"),
        ("ahora", "aho-ra"),
        ("piedra", "pie-dra"),
        ("reino", "reino"),
        ("guion", "guion"),
        ("mitad", "mi-tad"),
        ("humana", "hu-ma-na"),
        ("Organización", "Or-ga-ni-za-ción"),
        ("HERMOSAMENTE", "HER-MO-SA-MEN-TE"),
        ("hermosamente,", "her-mo-sa-men-te,"),
        ("«palabra»", "«pa-la-bra»"),
        ("casa.", "ca-sa."),
        ("niño", "ni-ño"),
        ("pingüino", "pin-güino"),
        ("ñandú", "ñan-dú"),
        ("averiguáis", "ave-ri-guáis"),
        ("abstracción", "abs-trac-ción"),
        ("subrayar", "su-bra-yar"),
        ("alrededor", "al-re-de-dor"),
        ("inhumano", "inhu-ma-no"),
        ("exacto", "exac-to"),
        ("prohibir", "prohi-bir"),
    ];
    const EN_REF: &[(&str, &str)] = &[
        ("hyphenation", "hy-phen-ation"),
        ("extraordinary", "ex-tra-or-di-nary"),
        ("philosophy", "phi-los-o-phy"),
        ("information", "in-for-ma-tion"),
        ("understanding", "un-der-stand-ing"),
        ("beautiful", "beau-ti-ful"),
        ("dictionary", "dic-tio-nary"),
        ("typography", "ty-pog-ra-phy"),
        ("algorithm", "al-go-rithm"),
        ("comfortable", "com-fort-able"),
        ("tradition", "tra-di-tion"),
        ("knowledge", "knowl-edge"),
        ("wonderful", "won-der-ful"),
        ("absolutely", "ab-so-lute-ly"),
        ("metaphysical", "meta-phys-i-cal"),
        ("contemplation", "con-tem-pla-tion"),
        ("spirituality", "spir-i-tu-al-i-ty"),
        ("architecture", "ar-chi-tec-ture"),
        ("silence", "si-lence"),
        ("sovereignty", "sovereign-ty"),
        ("attention", "at-ten-tion"),
        ("creation", "cre-ation"),
        ("construction", "con-struc-tion"),
        ("perennial", "peren-ni-al"),
        ("something", "some-thing"),
        ("together", "to-geth-er"),
        ("however", "how-ev-er"),
        ("religion", "re-li-gion"),
        ("necessary", "nec-es-sary"),
        ("government", "gov-ern-ment"),
        ("development", "de-vel-op-ment"),
        ("chapter", "chap-ter"),
        ("program", "pro-gram"),
        ("another", "an-oth-er"),
        ("different", "dif-fer-ent"),
        ("important", "im-por-tant"),
        ("question", "ques-tion"),
        ("children", "chil-dren"),
        ("everything", "ev-ery-thing"),
        ("mountain", "moun-tain"),
        ("Hyphenation", "Hy-phen-ation"),
        ("PHILOSOPHY", "PHI-LOS-O-PHY"),
        ("wonderful,", "won-der-ful,"),
        ("\"beautiful\"", "\"beau-ti-ful\""),
        ("don't", "don't"),
        ("well-known", "well--known"),
        ("re-entry", "re-en-try"),
    ];

    fn check(h: &Hyphenator, table: &[(&str, &str)]) {
        let mut wrong = Vec::new();
        for (word, want) in table {
            let got = h.inserted(word, "-");
            if got != *want {
                wrong.push(format!("{word}: got {got}, pyphen says {want}"));
            }
        }
        assert!(wrong.is_empty(), "differs from pyphen:\n{}", wrong.join("\n"));
    }

    // ── the same breaks as pyphen, word for word ─────────────────────────────

    #[test]
    fn spanish_breaks_exactly_where_pyphen_breaks() {
        check(Hyphenator::es(), ES_REF);
    }

    #[test]
    fn english_breaks_exactly_where_pyphen_breaks() {
        check(Hyphenator::en_us(), EN_REF);
    }

    #[test]
    fn the_dictionaries_are_actually_loaded() {
        assert!(Hyphenator::es().patterns.len() > 600);
        assert!(Hyphenator::en_us().patterns.len() > 8000);
    }

    #[test]
    fn a_word_is_never_broken_within_two_letters_of_either_end() {
        let h = Hyphenator::es();
        for (word, _) in ES_REF {
            let n = word.chars().count();
            for p in h.positions(word, 2, 2) {
                assert!(p >= 2 && p <= n - 2, "{word} breaks at {p}");
            }
        }
    }

    #[test]
    fn positions_are_character_indices_not_bytes() {
        // "niño" is 4 characters, 5 bytes: it breaks after the second letter
        assert_eq!(Hyphenator::es().positions("niño", 2, 2), vec![2]);
    }

    #[test]
    fn a_short_or_empty_word_has_no_break() {
        assert!(Hyphenator::es().positions("", 2, 2).is_empty());
        assert!(Hyphenator::es().positions("a", 2, 2).is_empty());
        assert_eq!(Hyphenator::en_us().inserted("the", "-"), "the");
    }

    // ── which language (guess_lang) ──────────────────────────────────────────

    #[test]
    fn spanish_text_is_guessed_as_spanish_and_english_as_english() {
        assert_eq!(guess_lang("El principio de todo lo que sigue es un silencio"), Some(Lang::Es));
        assert_eq!(guess_lang("The beginning of everything that follows is a silence"), Some(Lang::En));
    }

    #[test]
    fn spanish_diacritics_count_for_spanish() {
        // no function words at all, but an ñ and accents are a signal
        assert_eq!(guess_lang("Cañón sabiduría"), Some(Lang::Es));
    }

    #[test]
    fn no_signal_is_no_language_and_a_tie_goes_to_spanish() {
        assert_eq!(guess_lang("xyz qrs"), None);
        assert_eq!(guess_lang(""), None);
        assert_eq!(guess_lang("el the"), Some(Lang::Es)); // 1 vs 1: Spanish, as in the Python
    }

    #[test]
    fn punctuation_around_a_function_word_does_not_hide_it() {
        assert_eq!(guess_lang("\"The\" (of) and, to."), Some(Lang::En));
    }

    // ── the mode: off, auto, or one language ─────────────────────────────────

    #[test]
    fn the_config_values_mean_what_the_python_means() {
        assert_eq!(Mode::from_config("auto"), Mode::Auto);
        assert_eq!(Mode::from_config("es"), Mode::Fixed(Lang::Es));
        assert_eq!(Mode::from_config("es_ES"), Mode::Fixed(Lang::Es));
        assert_eq!(Mode::from_config("en_US"), Mode::Fixed(Lang::En));
        assert_eq!(Mode::from_config("EN"), Mode::Fixed(Lang::En));
        assert_eq!(Mode::from_config(""), Mode::Off);
        assert_eq!(Mode::from_config("off"), Mode::Off);
        assert_eq!(Mode::from_config("klingon"), Mode::Off);
    }

    #[test]
    fn a_mode_round_trips_through_the_config() {
        for m in [Mode::Off, Mode::Auto, Mode::Fixed(Lang::Es), Mode::Fixed(Lang::En)] {
            assert_eq!(Mode::from_config(m.to_config()), m, "{m:?}");
        }
    }

    #[test]
    fn auto_guesses_per_paragraph_off_never_and_fixed_always() {
        assert_eq!(Mode::Auto.lang_for("El principio de todo lo que sigue"), Some(Lang::Es));
        assert_eq!(Mode::Auto.lang_for("The beginning of everything"), Some(Lang::En));
        assert_eq!(Mode::Auto.lang_for("xyz qrs"), None); // no signal: not hyphenated
        assert_eq!(Mode::Off.lang_for("El principio de todo"), None);
        assert_eq!(Mode::Fixed(Lang::En).lang_for("El principio de todo"), Some(Lang::En));
        assert_eq!(Mode::Fixed(Lang::Es).lang_for("xyz qrs"), Some(Lang::Es));
    }

    #[test]
    fn auto_is_the_default_as_in_the_pythons_config() {
        assert_eq!(Mode::default(), Mode::Auto);
    }

    // ── what the typesetter asks for (hyphenate_text) ────────────────────────

    #[test]
    fn tokens_of_four_letters_or_fewer_are_left_whole() {
        assert!(break_points("casa", Some(Lang::Es)).is_empty());
        assert!(break_points("hola", Some(Lang::Es)).is_empty());
        assert!(!break_points("hermosa", Some(Lang::Es)).is_empty());
    }

    #[test]
    fn no_language_means_no_breaks() {
        assert!(break_points("hermosamente", None).is_empty());
    }

    #[test]
    fn the_break_points_match_the_hyphenated_form() {
        // her-mo-sa-men-te → breaks after 3, 5, 7, 10
        assert_eq!(break_points("hermosamente", Some(Lang::Es)), vec![3, 5, 7, 10]);
        // the length test counts characters: "niño" (4) is whole, "ñandú" (5) is not
        assert!(break_points("niño", Some(Lang::Es)).is_empty());
    }
}

//! An editable single line of text that we own completely.
//!
//! This is the piece that PyQt6 would not lend us: there, `QLineEdit` owns the
//! caret, which is why typewriter mode (caret pinned, text sliding underneath)
//! is a fight. Here the caret is just a number we keep, so the view can draw it
//! wherever it likes — or not at all.
//!
//! Stored as `Vec<char>` rather than `String` so caret arithmetic is in
//! characters, not bytes: "ñ" and "í" are one step, as a writer expects.

#![allow(dead_code)]

#[derive(Debug, Default, Clone, PartialEq, Eq)]
pub struct TextLine {
    chars: Vec<char>,
    caret: usize,
    /// Where a selection started. The selection is `anchor..caret`, in whichever
    /// order — a caret to the left of its anchor selects backwards. `None`, or
    /// equal to the caret, means nothing is selected.
    anchor: Option<usize>,
}

impl TextLine {
    pub fn new(text: &str) -> Self {
        let chars: Vec<char> = text.chars().collect();
        let caret = chars.len();
        Self { chars, caret, anchor: None }
    }

    pub fn text(&self) -> String {
        self.chars.iter().collect()
    }

    pub fn is_empty(&self) -> bool {
        self.chars.is_empty()
    }

    pub fn caret(&self) -> usize {
        self.caret
    }

    pub fn len(&self) -> usize {
        self.chars.len()
    }

    /// Replace the content, parking the caret at the end (where you keep typing).
    pub fn set_text(&mut self, text: &str) {
        self.chars = text.chars().collect();
        self.caret = self.chars.len();
        self.anchor = None;
    }

    pub fn clear(&mut self) {
        self.chars.clear();
        self.caret = 0;
        self.anchor = None;
    }

    /// Put the caret at a character index, clamped into range.
    pub fn set_caret(&mut self, pos: usize) {
        self.caret = pos.min(self.chars.len());
        self.anchor = None;
    }

    // ── selection ─────────────────────────────────────────────────────────────

    /// The selected range as `(start, end)` in characters, start < end — or
    /// `None` when nothing is selected.
    pub fn selection(&self) -> Option<(usize, usize)> {
        let a = self.anchor?;
        if a == self.caret {
            return None;
        }
        Some((a.min(self.caret), a.max(self.caret)))
    }

    pub fn selected_text(&self) -> String {
        match self.selection() {
            Some((s, e)) => self.chars[s..e].iter().collect(),
            None => String::new(),
        }
    }

    pub fn clear_selection(&mut self) {
        self.anchor = None;
    }

    /// Select `[start, end)`, in either order, clamped into range. The caret
    /// lands at the end.
    pub fn select_range(&mut self, start: usize, end: usize) {
        let n = self.chars.len();
        let (a, b) = (start.min(end).min(n), start.max(end).min(n));
        self.anchor = Some(a);
        self.caret = b;
    }

    pub fn select_all(&mut self) {
        self.select_range(0, self.chars.len());
    }

    /// Shift+arrow: move the caret by `delta`, keeping (or starting) a selection
    /// that runs from where the caret was.
    pub fn extend_caret(&mut self, delta: isize) {
        let anchor = self.anchor.unwrap_or(self.caret);
        let n = self.chars.len() as isize;
        self.caret = (self.caret as isize + delta).clamp(0, n) as usize;
        self.anchor = Some(anchor);
    }

    /// Where Ctrl+→ / Ctrl+← would put the caret, as QLineEdit does on Linux:
    /// forward to the START of the next word, back to the start of the previous.
    pub fn word_target(&self, forward: bool) -> usize {
        let n = self.chars.len();
        let mut i = self.caret;
        if forward {
            if i < n {
                let class = char_class(self.chars[i]);
                if class != CharClass::Space {
                    while i < n && char_class(self.chars[i]) == class {
                        i += 1;
                    }
                }
            }
            while i < n && char_class(self.chars[i]) == CharClass::Space {
                i += 1;
            }
        } else {
            while i > 0 && char_class(self.chars[i - 1]) == CharClass::Space {
                i -= 1;
            }
            if i > 0 {
                let class = char_class(self.chars[i - 1]);
                while i > 0 && char_class(self.chars[i - 1]) == class {
                    i -= 1;
                }
            }
        }
        i
    }

    /// Ctrl+←/→: the caret a word at a time; with a selection it collapses to
    /// where it would have gone.
    pub fn move_word(&mut self, forward: bool) {
        self.anchor = None;
        self.caret = self.word_target(forward);
    }

    /// Ctrl+Shift+←/→: the same, growing the selection.
    pub fn extend_word(&mut self, forward: bool) {
        let anchor = self.anchor.unwrap_or(self.caret);
        self.caret = self.word_target(forward);
        self.anchor = Some(anchor);
    }

    /// Shift+Home / Shift+End.
    pub fn extend_home(&mut self) {
        let anchor = self.anchor.unwrap_or(self.caret);
        self.caret = 0;
        self.anchor = Some(anchor);
    }

    pub fn extend_end(&mut self) {
        let anchor = self.anchor.unwrap_or(self.caret);
        self.caret = self.chars.len();
        self.anchor = Some(anchor);
    }

    /// Delete the selection, leaving the caret where it began. Returns whether
    /// there was one to delete.
    pub fn delete_selection(&mut self) -> bool {
        let Some((s, e)) = self.selection() else {
            self.anchor = None;
            return false;
        };
        self.chars.drain(s..e);
        self.caret = s;
        self.anchor = None;
        true
    }

    // ── editing ───────────────────────────────────────────────────────────────

    /// Typing replaces a selection, as everywhere.
    pub fn insert(&mut self, text: &str) {
        self.delete_selection();
        for c in text.chars() {
            self.chars.insert(self.caret, c);
            self.caret += 1;
        }
    }

    /// Replace `[start, end)` with `text`, leaving the caret at its end — how a
    /// re-rolled cut-up fragment overwrites the one before it.
    pub fn replace_range(&mut self, start: usize, end: usize, text: &str) {
        let start = start.min(self.chars.len());
        let end = end.clamp(start, self.chars.len());
        self.chars.splice(start..end, text.chars());
        self.caret = start + text.chars().count();
        self.anchor = None;
    }

    /// Delete the selection, or else the character before the caret. Returns
    /// whether anything went.
    pub fn backspace(&mut self) -> bool {
        if self.delete_selection() {
            return true;
        }
        if self.caret == 0 {
            return false;
        }
        self.caret -= 1;
        self.chars.remove(self.caret);
        true
    }

    /// Delete the selection, or else the character at the caret. Returns whether
    /// anything went.
    pub fn delete(&mut self) -> bool {
        if self.delete_selection() {
            return true;
        }
        if self.caret >= self.chars.len() {
            return false;
        }
        self.chars.remove(self.caret);
        true
    }

    /// Delete from the caret to the start of the next word, as QLineEdit's
    /// Ctrl+Delete does: the rest of the current word (or punctuation run) and
    /// the spaces after it. A selection is deleted instead. Returns whether
    /// anything went.
    pub fn delete_word_forward(&mut self) -> bool {
        if self.delete_selection() {
            return true;
        }
        let n = self.chars.len();
        if self.caret >= n {
            return false;
        }
        let mut end = self.caret;
        let class = char_class(self.chars[end]);
        if class != CharClass::Space {
            while end < n && char_class(self.chars[end]) == class {
                end += 1;
            }
        }
        while end < n && char_class(self.chars[end]) == CharClass::Space {
            end += 1;
        }
        self.chars.drain(self.caret..end);
        true
    }

    /// Delete from the start of the word before the caret up to the caret, as
    /// QLineEdit's Ctrl+Backspace does: spaces first, then one word (or
    /// punctuation run). Never the whole line. A selection is deleted instead.
    /// Returns whether anything went.
    pub fn delete_word_back(&mut self) -> bool {
        if self.delete_selection() {
            return true;
        }
        if self.caret == 0 {
            return false;
        }
        let mut start = self.caret;
        while start > 0 && char_class(self.chars[start - 1]) == CharClass::Space {
            start -= 1;
        }
        if start > 0 {
            let class = char_class(self.chars[start - 1]);
            while start > 0 && char_class(self.chars[start - 1]) == class {
                start -= 1;
            }
        }
        self.chars.drain(start..self.caret);
        self.caret = start;
        true
    }

    // ── movement ──────────────────────────────────────────────────────────────

    /// Move by `delta` characters, clamped — a line has ends, it doesn't wrap.
    /// With a selection, a plain arrow collapses it to the edge it points at
    /// instead of moving, as QLineEdit does.
    pub fn move_caret(&mut self, delta: isize) {
        if let Some((s, e)) = self.selection() {
            self.caret = if delta < 0 { s } else { e };
            self.anchor = None;
            return;
        }
        self.anchor = None;
        let n = self.chars.len() as isize;
        self.caret = (self.caret as isize + delta).clamp(0, n) as usize;
    }

    pub fn home(&mut self) {
        self.caret = 0;
        self.anchor = None;
    }

    pub fn end(&mut self) {
        self.caret = self.chars.len();
        self.anchor = None;
    }

    /// The text before the caret — what a typewriter view measures to know how
    /// far to slide the line so the caret lands on its fixed point.
    pub fn before_caret(&self) -> String {
        self.chars[..self.caret].iter().collect()
    }
}

/// What a character is for word-wise editing: letters and digits make words,
/// whitespace separates them, everything else is a run of punctuation.
#[derive(Clone, Copy, PartialEq, Eq)]
enum CharClass {
    Word,
    Space,
    Punct,
}

fn char_class(c: char) -> CharClass {
    if c.is_whitespace() {
        CharClass::Space
    } else if c.is_alphanumeric() || c == '_' {
        CharClass::Word
    } else {
        CharClass::Punct
    }
}

/// Caps Lock must never uppercase — it only toggles scriptio continua. The OS
/// has already applied Caps by the time we see the text, so swap the case back.
/// Non-letters are untouched.
pub fn neutralize_caps(text: &str, caps_on: bool) -> String {
    if !caps_on {
        return text.to_string();
    }
    text.chars()
        .flat_map(|c| {
            if c.is_uppercase() {
                c.to_lowercase().collect::<Vec<char>>()
            } else if c.is_lowercase() {
                c.to_uppercase().collect::<Vec<char>>()
            } else {
                vec![c]
            }
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn new_parks_the_caret_at_the_end() {
        let l = TextLine::new("hola");
        assert_eq!(l.text(), "hola");
        assert_eq!(l.caret(), 4);
    }

    #[test]
    fn typing_appends_at_the_caret() {
        let mut l = TextLine::new("");
        l.insert("h");
        l.insert("i");
        assert_eq!(l.text(), "hi");
        assert_eq!(l.caret(), 2);
    }

    #[test]
    fn accents_count_as_one_character() {
        let mut l = TextLine::new("");
        l.insert("frío");
        assert_eq!(l.caret(), 4); // not 5, despite í being two bytes
        assert!(l.backspace());
        assert_eq!(l.text(), "frí");
    }

    #[test]
    fn insert_in_the_middle() {
        let mut l = TextLine::new("hoa");
        l.set_caret(2);
        l.insert("l");
        assert_eq!(l.text(), "hola");
        assert_eq!(l.caret(), 3);
    }

    #[test]
    fn replace_range_overwrites_and_parks_the_caret_at_its_end() {
        let mut l = TextLine::new("una fruta roja");
        l.replace_range(4, 9, "manzana"); // "fruta" -> "manzana"
        assert_eq!(l.text(), "una manzana roja");
        assert_eq!(l.caret(), 11);
    }

    #[test]
    fn replace_range_with_an_empty_span_just_inserts() {
        let mut l = TextLine::new("uno dos");
        l.replace_range(4, 4, "nuevo ");
        assert_eq!(l.text(), "uno nuevo dos");
    }

    #[test]
    fn backspace_at_the_start_does_nothing() {
        let mut l = TextLine::new("hola");
        l.home();
        assert!(!l.backspace());
        assert_eq!(l.text(), "hola");
    }

    #[test]
    fn delete_removes_forward() {
        let mut l = TextLine::new("hola");
        l.set_caret(0);
        assert!(l.delete());
        assert_eq!(l.text(), "ola");
        assert_eq!(l.caret(), 0);
        l.end();
        assert!(!l.delete()); // nothing to the right
    }

    #[test]
    fn caret_moves_and_clamps() {
        let mut l = TextLine::new("abc");
        l.home();
        assert_eq!(l.caret(), 0);
        l.move_caret(-5); // clamped, never wraps
        assert_eq!(l.caret(), 0);
        l.move_caret(2);
        assert_eq!(l.caret(), 2);
        l.move_caret(99);
        assert_eq!(l.caret(), 3);
        l.end();
        assert_eq!(l.caret(), 3);
    }

    #[test]
    fn set_text_replaces_and_goes_to_the_end() {
        let mut l = TextLine::new("viejo");
        l.set_text("nuevo texto");
        assert_eq!(l.text(), "nuevo texto");
        assert_eq!(l.caret(), 11);
    }

    #[test]
    fn clear_empties_it() {
        let mut l = TextLine::new("algo");
        l.clear();
        assert_eq!(l.text(), "");
        assert_eq!(l.caret(), 0);
        assert!(l.is_empty());
    }

    #[test]
    fn before_caret_is_what_the_typewriter_measures() {
        let mut l = TextLine::new("hola mundo");
        l.set_caret(4);
        assert_eq!(l.before_caret(), "hola");
        l.end();
        assert_eq!(l.before_caret(), "hola mundo");
    }

    #[test]
    fn caps_is_neutralised_only_when_on() {
        assert_eq!(neutralize_caps("A", true), "a"); // Caps on → back to normal
        assert_eq!(neutralize_caps("a", true), "A"); // Caps+Shift → uppercase
        assert_eq!(neutralize_caps("A", false), "A"); // untouched
        assert_eq!(neutralize_caps("5-", true), "5-"); // non-letters untouched
        assert_eq!(neutralize_caps("Ñ", true), "ñ"); // accents too
    }

    // ── Ctrl+Delete / Ctrl+Backspace: one word, as QLineEdit does ───────────
    // Mirrors test_ctrl_delete_word.py and test_ctrl_backspace_word.py.

    #[test]
    fn ctrl_right_goes_to_the_start_of_the_next_word_and_ctrl_left_to_the_start_of_the_previous() {
        let mut l = TextLine::new("hola mundo, bonito");
        l.set_caret(0);
        l.move_word(true);
        assert_eq!(l.caret(), 5, "start of 'mundo'");
        l.move_word(true);
        assert_eq!(l.caret(), 10, "the comma is its own stop");
        l.move_word(true);
        assert_eq!(l.caret(), 12);
        l.move_word(true);
        assert_eq!(l.caret(), 18, "the end, and it stays there");
        l.move_word(true);
        assert_eq!(l.caret(), 18);
        l.move_word(false);
        assert_eq!(l.caret(), 12);
        l.set_caret(7); // inside 'mundo'
        l.move_word(false);
        assert_eq!(l.caret(), 5, "back to the start of the word it is in");
        l.set_caret(0);
        l.move_word(false);
        assert_eq!(l.caret(), 0);
    }

    #[test]
    fn ctrl_shift_arrows_select_by_word() {
        let mut l = TextLine::new("hola mundo");
        l.set_caret(0);
        l.extend_word(true);
        assert_eq!(l.selection(), Some((0, 5)));
        l.extend_word(true);
        assert_eq!(l.selection(), Some((0, 10)));
        l.extend_word(false);
        assert_eq!(l.selection(), Some((0, 5)));
    }

    #[test]
    fn delete_word_forward_takes_the_next_word_and_its_trailing_space() {
        let mut l = TextLine::new("hola mundo bonito");
        l.set_caret(5); // right after "hola "
        assert!(l.delete_word_forward());
        assert_eq!(l.text(), "hola bonito");
        assert_eq!(l.caret(), 5);
    }

    #[test]
    fn delete_word_forward_from_inside_a_word_takes_the_rest_of_it() {
        let mut l = TextLine::new("hola mundo");
        l.set_caret(2);
        assert!(l.delete_word_forward());
        assert_eq!(l.text(), "homundo");
        assert_eq!(l.caret(), 2);
    }

    #[test]
    fn delete_word_forward_at_the_end_does_nothing() {
        let mut l = TextLine::new("hola");
        assert!(!l.delete_word_forward());
        assert_eq!(l.text(), "hola");
    }

    #[test]
    fn delete_word_back_takes_the_word_before_the_caret() {
        let mut l = TextLine::new("hola mundo");
        assert!(l.delete_word_back());
        assert_eq!(l.text(), "hola ");
        assert_eq!(l.caret(), 5);
    }

    #[test]
    fn delete_word_back_skips_trailing_spaces_first() {
        let mut l = TextLine::new("hola mundo ");
        assert!(l.delete_word_back());
        assert_eq!(l.text(), "hola ");
        assert_eq!(l.caret(), 5);
    }

    #[test]
    fn delete_word_back_at_the_end_takes_only_the_last_word_not_the_line() {
        // the bug the Python fixed: at the end of the line this used to wipe it all
        let mut l = TextLine::new("una frase entera");
        assert!(l.delete_word_back());
        assert_eq!(l.text(), "una frase ");
    }

    #[test]
    fn delete_word_back_at_the_start_does_nothing() {
        let mut l = TextLine::new("hola");
        l.set_caret(0);
        assert!(!l.delete_word_back());
        assert_eq!(l.text(), "hola");
    }

    #[test]
    fn punctuation_is_a_stop_of_its_own() {
        let mut l = TextLine::new("dijo: hola");
        assert!(l.delete_word_back());
        assert_eq!(l.text(), "dijo: ");
        assert!(l.delete_word_back()); // spaces, then the colon
        assert_eq!(l.text(), "dijo");
    }

    #[test]
    fn accented_words_are_whole_words() {
        let mut l = TextLine::new("el niño");
        assert!(l.delete_word_back());
        assert_eq!(l.text(), "el ");
    }
    // ── selection (what QLineEdit gives Python for free) ─────────────────────

    #[test]
    fn a_fresh_line_has_no_selection() {
        let l = TextLine::new("hola mundo");
        assert_eq!(l.selection(), None);
        assert_eq!(l.selected_text(), "");
    }

    #[test]
    fn shift_arrows_extend_the_selection_from_where_the_caret_started() {
        let mut l = TextLine::new("hola");
        l.set_caret(0);
        l.extend_caret(1);
        l.extend_caret(1);
        assert_eq!(l.selection(), Some((0, 2)));
        assert_eq!(l.selected_text(), "ho");
        assert_eq!(l.caret(), 2);
        l.extend_caret(-1);
        assert_eq!(l.selection(), Some((0, 1)));
    }

    #[test]
    fn extending_leftwards_selects_backwards() {
        let mut l = TextLine::new("hola");
        l.extend_caret(-2);
        assert_eq!(l.selection(), Some((2, 4)));
        assert_eq!(l.selected_text(), "la");
    }

    #[test]
    fn extending_back_to_the_anchor_leaves_no_selection() {
        let mut l = TextLine::new("hola");
        l.extend_caret(-1);
        l.extend_caret(1);
        assert_eq!(l.selection(), None);
    }

    #[test]
    fn select_all_takes_the_whole_line() {
        let mut l = TextLine::new("hola mundo");
        l.select_all();
        assert_eq!(l.selected_text(), "hola mundo");
        assert_eq!(l.caret(), 10);
    }

    #[test]
    fn shift_home_and_end_select_to_the_ends() {
        let mut l = TextLine::new("hola mundo");
        l.set_caret(4);
        l.extend_home();
        assert_eq!(l.selected_text(), "hola");
        l.clear_selection();
        l.set_caret(5);
        l.extend_end();
        assert_eq!(l.selected_text(), "mundo");
    }

    #[test]
    fn a_plain_arrow_collapses_the_selection_to_its_edge() {
        let mut l = TextLine::new("hola mundo");
        l.set_caret(2);
        l.extend_caret(3); // selects "la " ... caret at 5
        l.move_caret(-1); // left → the START of the selection
        assert_eq!((l.selection(), l.caret()), (None, 2));
        l.extend_caret(3);
        l.move_caret(1); // right → the END of the selection
        assert_eq!((l.selection(), l.caret()), (None, 5));
    }

    #[test]
    fn typing_replaces_the_selection() {
        let mut l = TextLine::new("hola mundo");
        l.set_caret(5);
        l.extend_end();
        l.insert("tierra");
        assert_eq!(l.text(), "hola tierra");
        assert_eq!(l.selection(), None);
        assert_eq!(l.caret(), 11);
    }

    #[test]
    fn backspace_and_delete_remove_the_selection_not_a_character() {
        let mut l = TextLine::new("hola mundo");
        l.set_caret(0);
        l.extend_caret(5);
        assert!(l.backspace());
        assert_eq!(l.text(), "mundo");
        assert_eq!(l.caret(), 0);
        l.extend_caret(2);
        assert!(l.delete());
        assert_eq!(l.text(), "ndo");
    }

    #[test]
    fn deleting_a_word_with_a_selection_removes_the_selection() {
        let mut l = TextLine::new("uno dos tres");
        l.set_caret(0);
        l.extend_caret(3);
        assert!(l.delete_word_forward());
        assert_eq!(l.text(), " dos tres");
        l.select_all();
        assert!(l.delete_word_back());
        assert_eq!(l.text(), "");
    }

    #[test]
    fn replacing_the_text_drops_any_selection() {
        let mut l = TextLine::new("hola");
        l.select_all();
        l.set_text("otra");
        assert_eq!(l.selection(), None);
        l.select_all();
        l.clear();
        assert_eq!(l.selection(), None);
    }

    #[test]
    fn select_range_is_clamped_and_ordered() {
        let mut l = TextLine::new("hola");
        l.select_range(3, 1);
        assert_eq!(l.selection(), Some((1, 3)));
        l.select_range(2, 99);
        assert_eq!(l.selection(), Some((2, 4)));
    }

}

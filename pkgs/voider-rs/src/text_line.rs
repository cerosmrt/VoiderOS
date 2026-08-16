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
}

impl TextLine {
    pub fn new(text: &str) -> Self {
        let chars: Vec<char> = text.chars().collect();
        let caret = chars.len();
        Self { chars, caret }
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
    }

    pub fn clear(&mut self) {
        self.chars.clear();
        self.caret = 0;
    }

    /// Put the caret at a character index, clamped into range.
    pub fn set_caret(&mut self, pos: usize) {
        self.caret = pos.min(self.chars.len());
    }

    pub fn insert(&mut self, text: &str) {
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
    }

    /// Delete the character before the caret. Returns whether anything went.
    pub fn backspace(&mut self) -> bool {
        if self.caret == 0 {
            return false;
        }
        self.caret -= 1;
        self.chars.remove(self.caret);
        true
    }

    /// Delete the character at the caret. Returns whether anything went.
    pub fn delete(&mut self) -> bool {
        if self.caret >= self.chars.len() {
            return false;
        }
        self.chars.remove(self.caret);
        true
    }

    /// Move by `delta` characters, clamped — a line has ends, it doesn't wrap.
    pub fn move_caret(&mut self, delta: isize) {
        let n = self.chars.len() as isize;
        self.caret = (self.caret as isize + delta).clamp(0, n) as usize;
    }

    pub fn home(&mut self) {
        self.caret = 0;
    }

    pub fn end(&mut self) {
        self.caret = self.chars.len();
    }

    /// The text before the caret — what a typewriter view measures to know how
    /// far to slide the line so the caret lands on its fixed point.
    pub fn before_caret(&self) -> String {
        self.chars[..self.caret].iter().collect()
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
}

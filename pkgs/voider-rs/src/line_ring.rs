//! Circular list of lines with navigation — a 1:1 port of proto-voider's
//! `line_ring.py`. Pure logic, no UI.
//!
//! Porting note: Python's `%` always returns a non-negative result for a
//! positive modulus, Rust's does not (`-1 % 5 == -1`). Every wrap here uses
//! `rem_euclid` so moving backwards past 0 wraps to the end, as in Python.

// The views that consume this are still being ported (M1 onwards).
#![allow(dead_code)]

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LineRing {
    pub lines: Vec<String>,
    pub index: usize,
}

impl LineRing {
    /// An empty input becomes a single empty line (as in Python).
    pub fn new<I, S>(lines: I) -> Self
    where
        I: IntoIterator<Item = S>,
        S: Into<String>,
    {
        let mut lines: Vec<String> = lines.into_iter().map(Into::into).collect();
        if lines.is_empty() {
            lines.push(String::new());
        }
        Self { lines, index: 0 }
    }

    pub fn current(&self) -> &str {
        self.get(0)
    }

    /// Move the cursor by `delta`, wrapping in both directions.
    pub fn move_by(&mut self, delta: isize) {
        if self.lines.is_empty() {
            return;
        }
        let len = self.lines.len() as isize;
        self.index = (self.index as isize + delta).rem_euclid(len) as usize;
    }

    /// The line `offset` away from the cursor, wrapping. Empty ring → "".
    pub fn get(&self, offset: isize) -> &str {
        if self.lines.is_empty() {
            return "";
        }
        let len = self.lines.len() as isize;
        let i = (self.index as isize + offset).rem_euclid(len) as usize;
        &self.lines[i]
    }

    /// Insert at the cursor, or just after it (and follow it there).
    pub fn insert(&mut self, text: impl Into<String>, after_current: bool) {
        let pos = if after_current {
            self.index + 1
        } else {
            self.index
        };
        let pos = pos.min(self.lines.len());
        self.lines.insert(pos, text.into());
        if after_current {
            self.move_by(1);
        }
    }

    pub fn remove_current(&mut self) {
        if self.lines.len() <= 1 {
            self.lines = vec![String::new()];
            self.index = 0;
            return;
        }
        self.lines.remove(self.index);
        if self.index >= self.lines.len() {
            self.index = self.lines.len() - 1;
        }
    }

    /// The lines with the current one first (for export/print).
    pub fn to_list_from_current(&self) -> Vec<String> {
        let (head, tail) = self.lines.split_at(self.index);
        tail.iter().chain(head.iter()).cloned().collect()
    }

    /// Rotate so the current line becomes index 0.
    pub fn rebase_to_current(&mut self) {
        if self.lines.is_empty() || self.index == 0 {
            return;
        }
        self.lines.rotate_left(self.index);
        self.index = 0;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ring(lines: &[&str]) -> LineRing {
        LineRing::new(lines.iter().copied())
    }

    #[test]
    fn empty_input_becomes_one_empty_line() {
        let r = LineRing::new(Vec::<String>::new());
        assert_eq!(r.lines, vec!["".to_string()]);
        assert_eq!(r.index, 0);
    }

    #[test]
    fn current_is_the_line_at_the_cursor() {
        let mut r = ring(&["a", "b", "c"]);
        assert_eq!(r.current(), "a");
        r.index = 2;
        assert_eq!(r.current(), "c");
    }

    #[test]
    fn move_wraps_forward_and_backward() {
        let mut r = ring(&["a", "b", "c"]);
        r.move_by(1);
        assert_eq!(r.index, 1);
        r.move_by(2); // past the end → wraps
        assert_eq!(r.index, 0);
        r.move_by(-1); // before the start → wraps to the end (Python semantics)
        assert_eq!(r.index, 2);
    }

    #[test]
    fn move_by_large_negative_wraps_like_python() {
        let mut r = ring(&["a", "b", "c", "d", "e"]);
        r.move_by(-7); // (0 - 7) % 5 == 3 in Python
        assert_eq!(r.index, 3);
    }

    #[test]
    fn get_reads_relative_to_the_cursor() {
        let mut r = ring(&["a", "b", "c"]);
        r.index = 1;
        assert_eq!(r.get(0), "b");
        assert_eq!(r.get(1), "c");
        assert_eq!(r.get(-1), "a");
        assert_eq!(r.get(2), "a"); // wraps
    }

    #[test]
    fn insert_at_cursor_pushes_current_down() {
        let mut r = ring(&["a", "b"]);
        r.insert("x", false);
        assert_eq!(r.lines, vec!["x", "a", "b"]);
        assert_eq!(r.index, 0); // cursor stays put
    }

    #[test]
    fn insert_after_current_follows_the_new_line() {
        let mut r = ring(&["a", "b"]);
        r.insert("x", true);
        assert_eq!(r.lines, vec!["a", "x", "b"]);
        assert_eq!(r.index, 1); // moved onto the inserted line
    }

    #[test]
    fn remove_current_clamps_the_cursor() {
        let mut r = ring(&["a", "b", "c"]);
        r.index = 2;
        r.remove_current();
        assert_eq!(r.lines, vec!["a", "b"]);
        assert_eq!(r.index, 1); // clamped to the new end
    }

    #[test]
    fn removing_the_last_line_leaves_one_empty_line() {
        let mut r = ring(&["only"]);
        r.remove_current();
        assert_eq!(r.lines, vec!["".to_string()]);
        assert_eq!(r.index, 0);
    }

    #[test]
    fn to_list_from_current_starts_at_the_cursor() {
        let mut r = ring(&["a", "b", "c", "d"]);
        r.index = 2;
        assert_eq!(r.to_list_from_current(), vec!["c", "d", "a", "b"]);
        assert_eq!(r.index, 2); // non-destructive
    }

    #[test]
    fn rebase_makes_the_current_line_index_zero() {
        let mut r = ring(&["a", "b", "c", "d", "e"]);
        r.index = 2;
        r.rebase_to_current();
        assert_eq!(r.lines, vec!["c", "d", "e", "a", "b"]);
        assert_eq!(r.index, 0);
    }

    #[test]
    fn rebase_at_zero_is_a_noop() {
        let mut r = ring(&["a", "b"]);
        r.rebase_to_current();
        assert_eq!(r.lines, vec!["a", "b"]);
        assert_eq!(r.index, 0);
    }
}

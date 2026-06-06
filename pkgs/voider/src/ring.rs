const CAPACITY: usize = 10_000;

/// Circular line buffer shared across all views.
/// Lines that are exactly "." are paragraph separators — they are stored
/// normally but skipped during move_by() navigation.
pub struct LineRing {
    pub lines: Vec<String>,
    pub index: usize,
}

impl Default for LineRing {
    fn default() -> Self {
        Self { lines: vec![".".to_string()], index: 0 }
    }
}

impl LineRing {
    pub fn from_lines(lines: Vec<String>) -> Self {
        if lines.is_empty() {
            return Self::default();
        }
        Self { lines, index: 0 }
    }

    pub fn len(&self) -> usize { self.lines.len() }

    pub fn is_empty(&self) -> bool { self.lines.is_empty() }

    pub fn current(&self) -> &str {
        &self.lines[self.index]
    }

    pub fn is_dot(&self) -> bool {
        self.lines[self.index].trim() == "."
    }

    /// Get line at (index + offset) % len, wrapping circularly.
    pub fn get(&self, offset: isize) -> &str {
        let n = self.lines.len() as isize;
        if n == 0 { return ""; }
        let idx = ((self.index as isize + offset).rem_euclid(n)) as usize;
        &self.lines[idx]
    }

    /// Move index by delta, skipping dot-only lines.
    pub fn move_by(&mut self, delta: isize) {
        let n = self.lines.len();
        if n == 0 { return; }
        let start = self.index;
        let mut steps = 0usize;
        loop {
            self.index = ((self.index as isize + delta).rem_euclid(n as isize)) as usize;
            steps += 1;
            if self.lines[self.index].trim() != "." {
                return;
            }
            if steps >= n {
                self.index = start; // all dots — stay
                return;
            }
        }
    }

    /// Insert a new line after the current index. Index moves to new line.
    pub fn insert_after(&mut self, text: String) {
        let at = (self.index + 1).min(self.lines.len());
        if self.lines.len() >= CAPACITY {
            self.lines.remove(0);
            let at = at.saturating_sub(1).min(self.lines.len());
            self.lines.insert(at, text);
            self.index = at;
        } else {
            self.lines.insert(at, text);
            self.index = at;
        }
    }

    /// Append line at end. Index moves to new line.
    pub fn push(&mut self, text: String) {
        if self.lines.len() >= CAPACITY {
            self.lines.remove(0);
            self.index = self.index.saturating_sub(1);
        }
        self.lines.push(text);
        self.index = self.lines.len() - 1;
    }

    pub fn replace_current(&mut self, text: String) {
        if !self.lines.is_empty() {
            self.lines[self.index] = text;
        }
    }

    pub fn remove_current(&mut self) {
        if self.lines.len() <= 1 {
            self.lines = vec!["".to_string()];
            self.index = 0;
            return;
        }
        self.lines.remove(self.index);
        if self.index >= self.lines.len() {
            self.index = self.lines.len() - 1;
        }
    }

    /// Split current line at `pos`. Left part stays, right part becomes index+1.
    pub fn split_at(&mut self, pos: usize) {
        let text = self.lines[self.index].clone();
        let pos = pos.min(text.len());
        let left  = text[..pos].to_string();
        let right = text[pos..].to_string();
        self.lines[self.index] = left;
        self.lines.insert(self.index + 1, right);
        self.index += 1;
    }

    /// Join current line with previous (backspace at start). Blocked by dots.
    pub fn join_prev(&mut self) -> Option<usize> {
        let n = self.lines.len();
        if n < 2 { return None; }
        let prev = (self.index + n - 1) % n;
        if self.lines[prev].trim() == "." { return None; }
        let join_pos = self.lines[prev].len();
        let cur_text = self.lines[self.index].clone();
        self.lines[prev].push_str(&cur_text);
        self.lines.remove(self.index);
        self.index = prev;
        Some(join_pos)
    }

    /// Join current line with next (delete at end). Blocked by dots.
    pub fn join_next(&mut self) -> Option<usize> {
        let n = self.lines.len();
        if n < 2 { return None; }
        let next = (self.index + 1) % n;
        if self.lines[next].trim() == "." { return None; }
        let join_pos = self.lines[self.index].len();
        let next_text = self.lines[next].clone();
        self.lines[self.index].push_str(&next_text);
        self.lines.remove(next);
        Some(join_pos)
    }

    /// Swap current line with neighbor. Index follows the moved line.
    pub fn swap_with(&mut self, delta: isize) {
        let n = self.lines.len();
        if n < 2 { return; }
        let other = ((self.index as isize + delta).rem_euclid(n as isize)) as usize;
        self.lines.swap(self.index, other);
        self.index = other;
    }

    /// Rotate ring so current line becomes index 0.
    pub fn rebase(&mut self) {
        if self.index > 0 {
            self.lines.rotate_left(self.index);
            self.index = 0;
        }
    }

    /// Index of the nearest dot backward from current position.
    pub fn prev_dot_idx(&self) -> usize {
        let n = self.lines.len();
        let mut i = (self.index + n - 1) % n;
        for _ in 0..n {
            if self.lines[i].trim() == "." { return i; }
            if i == 0 { i = n - 1; } else { i -= 1; }
        }
        0
    }

    /// Index of the nearest dot forward from current position.
    pub fn next_dot_idx(&self) -> usize {
        let n = self.lines.len();
        for step in 1..n {
            let i = (self.index + step) % n;
            if self.lines[i].trim() == "." { return i; }
        }
        self.index
    }

    pub fn lines(&self) -> &[String] { &self.lines }
    pub fn lines_mut(&mut self) -> &mut Vec<String> { &mut self.lines }
}

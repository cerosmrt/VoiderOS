// Circular line buffer — oldest lines drop when capacity is reached.
const CAPACITY: usize = 10_000;

pub struct Ring {
    lines: Vec<String>,
    // Index of the "current" (newest committed) line for display centering.
    pub head: usize,
}

impl Ring {
    pub fn new() -> Self {
        Self { lines: Vec::new(), head: 0 }
    }

    pub fn push(&mut self, line: String) {
        if self.lines.len() >= CAPACITY {
            self.lines.remove(0);
        }
        self.lines.push(line);
        self.head = self.lines.len().saturating_sub(1);
    }

    pub fn len(&self) -> usize {
        self.lines.len()
    }

    // Get line at offset from head. Positive = older, negative = would go past head.
    // Returns None if out of range.
    pub fn get_from_head(&self, offset: isize) -> Option<&str> {
        let idx = (self.head as isize) - offset;
        if idx < 0 || idx >= self.lines.len() as isize {
            None
        } else {
            Some(&self.lines[idx as usize])
        }
    }

    pub fn lines(&self) -> &[String] {
        &self.lines
    }
}

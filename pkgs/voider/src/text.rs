/// What to do with a line submitted in F1.
pub enum LineAction {
    Insert(Vec<String>),       // formatted sentences to append
    Separator,                 // bare "." — paragraph separator
    SwitchFile(String),        // //filename
    MoveBlock(String),         // /filename  (move whole paragraph)
    MoveLine(String, String),  // content /filename (move one line)
    Empty,
}

pub fn parse_line(raw: &str) -> LineAction {
    let line = raw.trim();
    if line.is_empty() { return LineAction::Empty; }

    // // → switch file
    if let Some(rest) = line.strip_prefix("//") {
        let name = rest.trim();
        let name = if name.is_empty() { "0" } else { name };
        return LineAction::SwitchFile(ensure_txt(name));
    }

    // "content /filename" → move single line
    if let Some((content, fname)) = parse_move_line(line) {
        return LineAction::MoveLine(content, fname);
    }

    // "/filename" alone → move block
    if let Some(rest) = line.strip_prefix('/') {
        let name = rest.trim();
        if !name.is_empty() {
            return LineAction::MoveBlock(ensure_txt(name));
        }
    }

    // Bare dot → paragraph separator
    if line == "." {
        return LineAction::Separator;
    }

    LineAction::Insert(format_sentences(line))
}

fn parse_move_line(text: &str) -> Option<(String, String)> {
    // Find the last " /word" pattern at end of text
    let bytes = text.as_bytes();
    for i in (1..bytes.len()).rev() {
        if bytes[i - 1] == b' ' && bytes[i] == b'/' {
            let content = text[..i - 1].trim();
            let fname   = text[i + 1..].trim();
            if !content.is_empty() && !fname.is_empty() {
                return Some((content.to_string(), ensure_txt(fname)));
            }
        }
    }
    None
}

fn ensure_txt(name: &str) -> String {
    if name.to_lowercase().ends_with(".txt") {
        name.to_string()
    } else {
        format!("{name}.txt")
    }
}

/// Split raw text into Voider-formatted sentences (one per element).
pub fn format_sentences(text: &str) -> Vec<String> {
    // Protect "..."
    let protected = text.replace("...", "\x01");

    let mut sentences: Vec<String> = Vec::new();
    let mut current = String::new();
    let chars: Vec<char> = protected.chars().collect();
    let n = chars.len();
    let mut i = 0;

    while i < n {
        let ch = chars[i];
        current.push(ch);

        if ch == '.' && i + 1 < n {
            // Is the next visible character uppercase? If so, split here.
            let mut j = i + 1;
            while j < n && chars[j] == ' ' { j += 1; }
            if j < n && (chars[j].is_uppercase() || chars[j] == '"' || chars[j] == '\u{ab}') {
                flush_sentence(&mut current, &mut sentences);
                // Skip whitespace before next sentence
                i = j;
                continue;
            }
        }

        i += 1;
    }
    flush_sentence(&mut current, &mut sentences);

    let result: Vec<String> = sentences.into_iter()
        .map(|s| s.replace('\x01', "..."))
        .filter(|s| !s.is_empty())
        .map(|s| capitalize_and_period(&s))
        .collect();

    if result.is_empty() {
        vec![capitalize_and_period(text)]
    } else {
        result
    }
}

fn flush_sentence(current: &mut String, sentences: &mut Vec<String>) {
    let s = current.trim().to_string();
    if !s.is_empty() { sentences.push(s); }
    current.clear();
}

fn capitalize_and_period(s: &str) -> String {
    let s = s.trim();
    if s.is_empty() { return String::new(); }
    let mut result = String::new();
    let mut chars = s.chars();
    if let Some(c) = chars.next() {
        result.extend(c.to_uppercase());
    }
    result.extend(chars);
    if !result.ends_with('.') && !result.ends_with('!') && !result.ends_with('?') {
        result.push('.');
    }
    result
}

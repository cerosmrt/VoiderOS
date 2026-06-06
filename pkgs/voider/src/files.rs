use std::{fs, io::Write, path::{Path, PathBuf}};

// ── FileIndex (fuzzy find) ────────────────────────────────────────────────────

pub struct FileIndex {
    pub entries:  Vec<PathBuf>,
    pub void_dir: PathBuf,
}

impl FileIndex {
    pub fn build(void_dir: &Path) -> Self {
        Self { entries: scan_top(void_dir), void_dir: void_dir.to_path_buf() }
    }
    pub fn rebuild(&mut self) { self.entries = scan_top(&self.void_dir); }
    pub fn filter<'a>(&'a self, query: &str) -> Vec<&'a Path> {
        if query.is_empty() {
            return self.entries.iter().map(PathBuf::as_path).collect();
        }
        let q: Vec<char> = query.to_lowercase().chars().collect();
        self.entries.iter()
            .filter(|p| fuzzy_match(&p.file_stem().unwrap_or_default().to_string_lossy().to_lowercase(), &q))
            .map(PathBuf::as_path)
            .collect()
    }
    pub fn create_new(&mut self, name: &str) -> anyhow::Result<PathBuf> {
        let path = self.void_dir.join(format!("{}.txt", name.trim()));
        fs::write(&path, "")?;
        self.rebuild();
        Ok(path)
    }
}

// ── File I/O ──────────────────────────────────────────────────────────────────

/// Read all non-empty lines from a file.
pub fn read_file(path: &Path) -> Vec<String> {
    fs::read_to_string(path)
        .unwrap_or_default()
        .lines()
        .map(|l| l.to_owned())
        .filter(|l| !l.is_empty())
        .collect()
}

/// Append a single line.
pub fn append_line(path: &Path, line: &str) -> anyhow::Result<()> {
    let mut f = fs::OpenOptions::new().append(true).create(true).open(path)?;
    writeln!(f, "{line}")?;
    Ok(())
}

/// Atomically rewrite whole file from a slice of lines.
pub fn save_file(path: &Path, lines: &[String]) -> anyhow::Result<()> {
    let tmp = path.with_extension("tmp");
    {
        let mut f = fs::File::create(&tmp)?;
        for line in lines {
            writeln!(f, "{line}")?;
        }
    }
    fs::rename(&tmp, path)?;
    Ok(())
}

// ── Book order ────────────────────────────────────────────────────────────────

/// Load ordered chapter filenames from `_book_order.txt` (one name per line).
/// Falls back to alphabetical if the file doesn't exist.
pub fn load_book_order(book_dir: &Path) -> Vec<PathBuf> {
    let order_path = book_dir.join("_book_order.txt");
    let mut actual: Vec<PathBuf> = scan_top(book_dir);
    // Remove metadata files
    actual.retain(|p| {
        let name = p.file_name().unwrap_or_default().to_string_lossy();
        !name.starts_with('_')
    });

    if order_path.exists() {
        if let Ok(content) = fs::read_to_string(&order_path) {
            let saved: Vec<PathBuf> = content.lines()
                .map(|l| book_dir.join(l.trim()))
                .filter(|p| p.exists())
                .collect();
            let saved_set: std::collections::HashSet<_> = saved.iter().cloned().collect();
            let mut remaining: Vec<PathBuf> = actual.into_iter()
                .filter(|p| !saved_set.contains(p))
                .collect();
            let mut result = saved;
            result.append(&mut remaining);
            return result;
        }
    }
    actual
}

pub fn save_book_order(book_dir: &Path, files: &[PathBuf]) -> anyhow::Result<()> {
    let path = book_dir.join("_book_order.txt");
    let mut f = fs::File::create(&path)?;
    for p in files {
        if let Some(name) = p.file_name() {
            writeln!(f, "{}", name.to_string_lossy())?;
        }
    }
    Ok(())
}

// ── Vault (all lines from all files, shuffled) ────────────────────────────────

/// Recursively collect all non-empty, non-dot lines from vault .txt files.
/// Excludes 0.txt and metadata files.
pub fn load_vault_lines(void_dir: &Path) -> Vec<String> {
    let mut lines = Vec::new();
    collect_vault_lines(void_dir, &mut lines);
    shuffle(&mut lines);
    lines
}

fn collect_vault_lines(dir: &Path, out: &mut Vec<String>) {
    let Ok(entries) = fs::read_dir(dir) else { return; };
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_dir() {
            collect_vault_lines(&path, out);
        } else if path.extension().map(|e| e == "txt").unwrap_or(false) {
            let name = path.file_name().unwrap_or_default().to_string_lossy().to_lowercase();
            if name == "0.txt" || name.starts_with('_') { continue; }
            if let Ok(content) = fs::read_to_string(&path) {
                for line in content.lines() {
                    let s = line.trim();
                    if !s.is_empty() && s != "." {
                        out.push(s.to_string());
                    }
                }
            }
        }
    }
}

// ── Top-level .txt scan ───────────────────────────────────────────────────────

fn scan_top(dir: &Path) -> Vec<PathBuf> {
    let Ok(entries) = fs::read_dir(dir) else { return Vec::new(); };
    let mut out: Vec<PathBuf> = entries.flatten()
        .map(|e| e.path())
        .filter(|p| p.is_file() && p.extension().map(|e| e == "txt").unwrap_or(false))
        .collect();
    out.sort();
    out
}

// ── Helpers ───────────────────────────────────────────────────────────────────

fn fuzzy_match(text: &str, query: &[char]) -> bool {
    let mut qi = 0;
    for ch in text.chars() {
        if qi < query.len() && ch == query[qi] { qi += 1; }
    }
    qi == query.len()
}

pub fn shuffle<T>(items: &mut Vec<T>) {
    let n = items.len();
    if n < 2 { return; }
    let mut seed = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_nanos() as u64)
        .unwrap_or(0xdeadbeef);
    for i in (1..n).rev() {
        seed ^= seed << 13;
        seed ^= seed >> 7;
        seed ^= seed << 17;
        let j = (seed as usize) % (i + 1);
        items.swap(i, j);
    }
}

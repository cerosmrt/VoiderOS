use std::{fs, io::Write, path::{Path, PathBuf}};

// In-memory index of all .txt files under void_dir.
pub struct FileIndex {
    pub entries: Vec<PathBuf>,
    pub void_dir: PathBuf,
}

impl FileIndex {
    pub fn build(void_dir: &Path) -> Self {
        let entries = scan(void_dir);
        Self { entries, void_dir: void_dir.to_path_buf() }
    }

    pub fn rebuild(&mut self) {
        self.entries = scan(&self.void_dir);
    }

    // Fuzzy filter: returns entries where query chars appear in order.
    pub fn filter(&self, query: &str) -> Vec<&Path> {
        if query.is_empty() {
            return self.entries.iter().map(PathBuf::as_path).collect();
        }
        let q: Vec<char> = query.to_lowercase().chars().collect();
        self.entries.iter()
            .filter(|p| {
                let name = p.file_stem().unwrap_or_default().to_string_lossy().to_lowercase();
                fuzzy_match(&name, &q)
            })
            .map(PathBuf::as_path)
            .collect()
    }

    pub fn create_new(&mut self, name: &str) -> anyhow::Result<PathBuf> {
        let fname = format!("{}.txt", name.trim());
        let path  = self.void_dir.join(&fname);
        fs::write(&path, "")?;
        self.rebuild();
        Ok(path)
    }

    pub fn delete(&mut self, path: &Path) -> anyhow::Result<()> {
        fs::remove_file(path)?;
        self.rebuild();
        Ok(())
    }
}

// Read all committed lines from a file.
pub fn read_file(path: &Path) -> Vec<String> {
    fs::read_to_string(path)
        .unwrap_or_default()
        .lines()
        .map(|l| l.to_owned())
        .collect()
}

// Append a line to a file atomically-ish (append mode, no full rewrite).
pub fn append_line(path: &Path, line: &str) -> anyhow::Result<()> {
    let mut f = fs::OpenOptions::new().append(true).create(true).open(path)?;
    writeln!(f, "{line}")?;
    Ok(())
}

fn scan(dir: &Path) -> Vec<PathBuf> {
    let mut out = Vec::new();
    scan_recursive(dir, &mut out);
    out.sort();
    out
}

fn scan_recursive(dir: &Path, out: &mut Vec<PathBuf>) {
    let Ok(entries) = fs::read_dir(dir) else { return; };
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_dir() {
            scan_recursive(&path, out);
        } else if path.extension().map(|e| e == "txt").unwrap_or(false) {
            out.push(path);
        }
    }
}

fn fuzzy_match(text: &str, query: &[char]) -> bool {
    let mut qi = 0;
    for ch in text.chars() {
        if qi < query.len() && ch == query[qi] {
            qi += 1;
        }
    }
    qi == query.len()
}

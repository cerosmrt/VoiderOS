//! Where the cursor was left on each file — a port of `_last_lines.json`.
//!
//! One flat sidecar in `I/`, `filename = index` per line, hand-rolled like
//! `config.rs` rather than pulling in a JSON crate for a handful of numbers.
//! Read-modify-write on every save: writes are rare (a navigate, a view
//! change), never a hot loop.

#![allow(dead_code)]

use std::collections::HashMap;
use std::path::{Path, PathBuf};

use crate::void;

fn lines_path(void_dir: &Path) -> PathBuf {
    void_dir.join("I").join("_last_lines.conf")
}

fn load_all(void_dir: &Path) -> HashMap<String, usize> {
    let mut map = HashMap::new();
    if let Ok(text) = std::fs::read_to_string(lines_path(void_dir)) {
        for line in text.lines() {
            let Some((name, idx)) = line.split_once('=') else {
                continue;
            };
            if let Ok(idx) = idx.trim().parse::<usize>() {
                map.insert(name.trim().to_string(), idx);
            }
        }
    }
    map
}

/// Save `filename`'s ring index. Best-effort — a write failure here should
/// never stop the actual work the caller was doing.
pub fn save_last_line(void_dir: &Path, filename: &str, index: usize) {
    let mut map = load_all(void_dir);
    map.insert(filename.to_string(), index);
    let mut entries: Vec<_> = map.into_iter().collect();
    entries.sort();
    let lines: Vec<String> = entries
        .into_iter()
        .map(|(name, idx)| format!("{name} = {idx}"))
        .collect();
    let _ = void::atomic_write(&lines_path(void_dir), &lines, false);
}

/// The saved index for `filename`, if any.
pub fn load_last_line(void_dir: &Path, filename: &str) -> Option<usize> {
    load_all(void_dir).get(filename).copied()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_saved_line_round_trips() {
        let d = tempfile::tempdir().unwrap();
        save_last_line(d.path(), "chap.txt", 7);
        assert_eq!(load_last_line(d.path(), "chap.txt"), Some(7));
    }

    #[test]
    fn an_unknown_file_has_nothing_saved() {
        let d = tempfile::tempdir().unwrap();
        assert_eq!(load_last_line(d.path(), "nobody.txt"), None);
    }

    #[test]
    fn saving_one_file_does_not_disturb_another() {
        let d = tempfile::tempdir().unwrap();
        save_last_line(d.path(), "a.txt", 1);
        save_last_line(d.path(), "b.txt", 2);
        assert_eq!(load_last_line(d.path(), "a.txt"), Some(1));
        assert_eq!(load_last_line(d.path(), "b.txt"), Some(2));
    }

    #[test]
    fn saving_again_overwrites_the_old_value() {
        let d = tempfile::tempdir().unwrap();
        save_last_line(d.path(), "a.txt", 1);
        save_last_line(d.path(), "a.txt", 9);
        assert_eq!(load_last_line(d.path(), "a.txt"), Some(9));
    }
}

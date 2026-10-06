//! Ctrl+B — the physical copy of the void onto external media.
//!
//! Not a port of `_backup_vault`, which opens a folder dialog and copies only
//! the `.txt` files, losing the git history with them. This follows the design
//! written down in `roadmap/pending.txt` instead: commit first, find the drive,
//! SHOW what is about to be written and to where, and only copy once that is
//! accepted. Git is the history on this disk; Ctrl+B is the copy that leaves
//! the machine, history and all.
//!
//! Two deliberate rules about what travels:
//!
//! * Everything is copied, `.git` included — that is the whole point, and what
//!   makes the copy readable directly AND able to carry the version history.
//! * Symlinked directories are recorded but NOT followed. `O/` is a symlink to
//!   `/mnt/data`; following it would silently turn a backup of the writing into
//!   a multi-gigabyte copy of the corpus, and could loop. They are reported as
//!   skipped so the choice is visible rather than hidden.

#![allow(dead_code)]

use std::io;
use std::path::{Path, PathBuf};

/// One file to copy: where it sits relative to the void, and how big it is.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Entry {
    pub rel: PathBuf,
    pub bytes: u64,
}

/// What a backup would do, worked out before anything is written — this is what
/// the confirm step puts on screen.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Plan {
    /// The drive (or folder) the copy is going onto.
    pub dest_root: PathBuf,
    /// The dated folder created inside it.
    pub folder: String,
    pub files: Vec<Entry>,
    /// Symlinked directories left behind, so the report can say so.
    pub skipped_links: Vec<PathBuf>,
}

impl Plan {
    pub fn total_bytes(&self) -> u64 {
        self.files.iter().map(|f| f.bytes).sum()
    }

    pub fn dest(&self) -> PathBuf {
        self.dest_root.join(&self.folder)
    }

    /// The one line the confirm screen lives by.
    pub fn summary(&self) -> String {
        let mut s = format!(
            "{} archivos · {} → {}",
            self.files.len(),
            human_bytes(self.total_bytes()),
            self.dest().display()
        );
        if !self.skipped_links.is_empty() {
            let names: Vec<String> = self
                .skipped_links
                .iter()
                .map(|p| p.to_string_lossy().to_string())
                .collect();
            s.push_str(&format!("   (sin seguir: {})", names.join(", ")));
        }
        s
    }
}

/// Round bytes to something a person reads at a glance.
pub fn human_bytes(n: u64) -> String {
    const K: f64 = 1024.0;
    let n = n as f64;
    if n < K {
        return format!("{n:.0} B");
    }
    for (i, unit) in ["KB", "MB", "GB", "TB"].iter().enumerate() {
        let scale = K.powi(i as i32 + 1);
        if n < scale * K || i == 3 {
            return format!("{:.1} {unit}", n / scale);
        }
    }
    unreachable!()
}

/// Removable media that is actually mounted, newest mount points first.
/// Scans the usual places a desktop mounts a pendrive under.
pub fn detect_drives() -> Vec<PathBuf> {
    let user = std::env::var("USER").unwrap_or_default();
    let mut roots = vec![
        PathBuf::from("/run/media").join(&user),
        PathBuf::from("/media").join(&user),
        PathBuf::from("/run/media"),
        PathBuf::from("/media"),
        // Not /mnt, as in the Python: /mnt/data is where O/ lives, not a pendrive.
    ];
    roots.retain(|r| r.is_dir());

    let mut found = Vec::new();
    for root in roots {
        let Ok(entries) = std::fs::read_dir(&root) else {
            continue;
        };
        for entry in entries.flatten() {
            let path = entry.path();
            // Only real, writable-looking mount points, and never twice.
            if path.is_dir() && !found.contains(&path) {
                found.push(path);
            }
        }
    }
    found
}

/// `{vault}_{YY-MM-DD}({n})`, where n counts what is already there for today —
/// so two backups on one day never land on each other.
pub fn folder_name(void_dir: &Path, dest_root: &Path, date: &str) -> String {
    let vault = void_dir
        .file_name()
        .map(|s| s.to_string_lossy().to_string())
        .unwrap_or_else(|| "void".to_string());
    let prefix = format!("{vault}_{date}");
    let existing = std::fs::read_dir(dest_root)
        .map(|entries| {
            entries
                .flatten()
                .filter(|e| e.path().is_dir())
                .filter(|e| e.file_name().to_string_lossy().starts_with(&prefix))
                .count()
        })
        .unwrap_or(0);
    format!("{prefix}({})", existing + 1)
}

/// Work out everything that would be copied, without writing a thing.
pub fn plan(void_dir: &Path, dest_root: &Path, date: &str) -> Plan {
    let mut files = Vec::new();
    let mut skipped_links = Vec::new();
    walk(void_dir, void_dir, &mut files, &mut skipped_links);
    files.sort_by(|a, b| a.rel.cmp(&b.rel));
    skipped_links.sort();
    Plan {
        dest_root: dest_root.to_path_buf(),
        folder: folder_name(void_dir, dest_root, date),
        files,
        skipped_links,
    }
}

/// Top-level folders that do not travel (the Python's `_BACKUP_SKIP_DIRS`).
const SKIP_DIRS: &[&str] = &["tts"];

fn walk(root: &Path, dir: &Path, files: &mut Vec<Entry>, links: &mut Vec<PathBuf>) {
    let Ok(entries) = std::fs::read_dir(dir) else {
        return;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        let Ok(meta) = entry.metadata() else { continue }; // symlink-aware: does not follow
        let rel = path.strip_prefix(root).unwrap_or(&path).to_path_buf();
        // The voice models at the void's root (309 MB, downloadable again) stay
        // home; a `tts/` deeper down would be text about them, and travels.
        if dir == root && meta.is_dir() && SKIP_DIRS.iter().any(|s| rel == Path::new(s)) {
            links.push(rel);
            continue;
        }
        if meta.is_symlink() {
            links.push(rel);
        } else if meta.is_dir() {
            walk(root, &path, files, links);
        } else if meta.is_file() {
            files.push(Entry { rel, bytes: meta.len() });
        }
    }
}

/// Do the copy the plan describes. Returns how many files landed.
pub fn run(void_dir: &Path, plan: &Plan) -> io::Result<usize> {
    run_with(void_dir, plan, |src, dst| std::fs::copy(src, dst))
}

/// Characters FAT32/exFAT refuse in a file name — pendrives usually come
/// formatted that way, and the void's question titles (`¿…?`) are full of `?`.
const FAT_FORBIDDEN: &[char] = &['\\', '/', ':', '*', '?', '"', '<', '>', '|'];

/// The same path with its FILE NAME made acceptable to FAT (`_` for each
/// forbidden character). The folders are left as they are — the Python's
/// `_fat_sanitize`.
pub fn fat_sanitize(rel: &Path) -> PathBuf {
    let name = rel
        .file_name()
        .map(|n| n.to_string_lossy().replace(FAT_FORBIDDEN, "_"))
        .unwrap_or_default();
    match rel.parent() {
        Some(p) if !p.as_os_str().is_empty() => p.join(name),
        _ => PathBuf::from(name),
    }
}

/// `run`, with the copy itself handed in so a test can play a FAT pendrive.
/// One file that won't copy never stops the rest (the Python's `_backup_copy`);
/// an "invalid argument" (errno 22) is retried once under a FAT-safe name.
pub fn run_with(
    void_dir: &Path,
    plan: &Plan,
    mut copy: impl FnMut(&Path, &Path) -> io::Result<u64>,
) -> io::Result<usize> {
    let dest = plan.dest();
    std::fs::create_dir_all(&dest)?;
    let mut copied = 0usize;
    for entry in &plan.files {
        let src = void_dir.join(&entry.rel);
        let dst = dest.join(&entry.rel);
        if let Some(parent) = dst.parent() {
            if std::fs::create_dir_all(parent).is_err() {
                continue;
            }
        }
        match copy(&src, &dst) {
            Ok(_) => copied += 1,
            Err(e) if e.raw_os_error() == Some(22) => {
                if copy(&src, &dest.join(fat_sanitize(&entry.rel))).is_ok() {
                    copied += 1;
                }
            }
            Err(_) => {}
        }
    }
    Ok(copied)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn void_with(files: &[(&str, &str)]) -> tempfile::TempDir {
        let d = tempfile::tempdir().unwrap();
        for (rel, body) in files {
            let p = d.path().join(rel);
            std::fs::create_dir_all(p.parent().unwrap()).unwrap();
            std::fs::write(p, body).unwrap();
        }
        d
    }

    #[test]
    fn the_plan_lists_every_file_under_the_void() {
        let v = void_with(&[("I/a.txt", "hola"), ("I/b.txt", "chau"), ("0.txt", "x")]);
        let dest = tempfile::tempdir().unwrap();
        let p = plan(v.path(), dest.path(), "25-01-01");
        let rels: Vec<String> = p.files.iter().map(|f| f.rel.to_string_lossy().into()).collect();
        assert_eq!(rels, vec!["0.txt", "I/a.txt", "I/b.txt"]);
        assert_eq!(p.total_bytes(), 4 + 4 + 1);
    }

    #[test]
    fn the_git_history_travels_too() {
        // The whole reason this exists rather than the Python's .txt-only copy.
        let v = void_with(&[("I/a.txt", "hola"), (".git/HEAD", "ref: refs/heads/main")]);
        let dest = tempfile::tempdir().unwrap();
        let p = plan(v.path(), dest.path(), "25-01-01");
        assert!(
            p.files.iter().any(|f| f.rel.starts_with(".git")),
            "the backup dropped the history: {:?}",
            p.files
        );
    }

    #[test]
    fn a_symlinked_directory_is_recorded_but_never_followed() {
        // O/ points at /mnt/data; following it would copy the whole corpus.
        let v = void_with(&[("I/a.txt", "hola")]);
        let outside = tempfile::tempdir().unwrap();
        std::fs::write(outside.path().join("huge.bin"), vec![0u8; 4096]).unwrap();
        std::os::unix::fs::symlink(outside.path(), v.path().join("O")).unwrap();

        let dest = tempfile::tempdir().unwrap();
        let p = plan(v.path(), dest.path(), "25-01-01");
        assert_eq!(p.skipped_links, vec![PathBuf::from("O")]);
        assert!(!p.files.iter().any(|f| f.rel.starts_with("O")));
        assert_eq!(p.total_bytes(), 4); // just the one real file
    }

    #[test]
    fn running_the_plan_reproduces_the_tree() {
        let v = void_with(&[("I/a.txt", "hola"), ("I/sub/b.txt", "chau")]);
        let dest = tempfile::tempdir().unwrap();
        let p = plan(v.path(), dest.path(), "25-01-01");
        assert_eq!(run(v.path(), &p).unwrap(), 2);
        assert_eq!(std::fs::read_to_string(p.dest().join("I/a.txt")).unwrap(), "hola");
        assert_eq!(std::fs::read_to_string(p.dest().join("I/sub/b.txt")).unwrap(), "chau");
    }

    #[test]
    fn a_second_backup_the_same_day_gets_its_own_folder() {
        let v = void_with(&[("a.txt", "x")]);
        let dest = tempfile::tempdir().unwrap();
        let first = plan(v.path(), dest.path(), "25-01-01");
        run(v.path(), &first).unwrap();
        let second = plan(v.path(), dest.path(), "25-01-01");
        assert_ne!(first.folder, second.folder);
        assert!(first.folder.ends_with("(1)"));
        assert!(second.folder.ends_with("(2)"));
    }

    #[test]
    fn the_folder_is_named_after_the_vault_and_the_day() {
        let d = tempfile::tempdir().unwrap();
        let v = d.path().join("void");
        std::fs::create_dir_all(&v).unwrap();
        let dest = tempfile::tempdir().unwrap();
        assert_eq!(folder_name(&v, dest.path(), "25-08-16"), "void_25-08-16(1)");
    }

    #[test]
    fn the_summary_says_what_and_where() {
        let v = void_with(&[("a.txt", "hola")]);
        let dest = tempfile::tempdir().unwrap();
        let p = plan(v.path(), dest.path(), "25-01-01");
        let s = p.summary();
        assert!(s.contains("1 archivos"));
        assert!(s.contains(&p.dest().display().to_string()));
    }

    #[test]
    fn the_summary_names_what_it_did_not_follow() {
        let v = void_with(&[("a.txt", "hola")]);
        let outside = tempfile::tempdir().unwrap();
        std::os::unix::fs::symlink(outside.path(), v.path().join("O")).unwrap();
        let dest = tempfile::tempdir().unwrap();
        assert!(plan(v.path(), dest.path(), "25-01-01").summary().contains("sin seguir: O"));
    }

    #[test]
    fn bytes_are_written_for_a_person() {
        assert_eq!(human_bytes(512), "512 B");
        assert_eq!(human_bytes(2048), "2.0 KB");
        assert_eq!(human_bytes(5 * 1024 * 1024), "5.0 MB");
        assert_eq!(human_bytes(3 * 1024 * 1024 * 1024), "3.0 GB");
    }

    // ── lo que el Python ya hacía y faltaba acá (test_backup_vault.py) ─────────

    #[test]
    fn the_voices_do_not_travel() {
        // tts/ at the void's root: 309 MB of models that can be downloaded again.
        let v = void_with(&[("I/a.txt", "hola"), ("tts/es.onnx", "modelo")]);
        let dest = tempfile::tempdir().unwrap();
        let p = plan(v.path(), dest.path(), "25-01-01");
        assert!(!p.files.iter().any(|f| f.rel.starts_with("tts")));
        assert!(p.skipped_links.contains(&PathBuf::from("tts")));
    }

    #[test]
    fn a_tts_folder_deeper_down_is_text_and_travels() {
        let v = void_with(&[("I/tts/notas.txt", "texto")]);
        let dest = tempfile::tempdir().unwrap();
        let p = plan(v.path(), dest.path(), "25-01-01");
        assert!(p.files.iter().any(|f| f.rel == Path::new("I/tts/notas.txt")));
    }

    #[test]
    fn a_name_fat_refuses_is_copied_under_a_safe_name() {
        let v = void_with(&[("I/¿pregunta?.txt", "hola"), ("I/b.txt", "chau")]);
        let dest = tempfile::tempdir().unwrap();
        let p = plan(v.path(), dest.path(), "25-01-01");
        // Like a FAT32 pendrive: a '?' in the name is EINVAL (errno 22).
        let copied = run_with(v.path(), &p, |src, dst| {
            if dst.file_name().unwrap().to_string_lossy().contains('?') {
                return Err(io::Error::from_raw_os_error(22));
            }
            std::fs::copy(src, dst)
        })
        .unwrap();
        assert_eq!(copied, 2);
        assert_eq!(std::fs::read_to_string(p.dest().join("I/¿pregunta_.txt")).unwrap(), "hola");
    }

    #[test]
    fn one_file_that_will_not_copy_does_not_stop_the_rest() {
        let v = void_with(&[("I/a.txt", "a"), ("I/b.txt", "b")]);
        let dest = tempfile::tempdir().unwrap();
        let p = plan(v.path(), dest.path(), "25-01-01");
        let copied = run_with(v.path(), &p, |src, dst| {
            if src.ends_with("a.txt") {
                return Err(io::Error::from_raw_os_error(13));
            }
            std::fs::copy(src, dst)
        })
        .unwrap();
        assert_eq!(copied, 1);
        assert!(p.dest().join("I/b.txt").exists());
    }

    #[test]
    fn fat_sanitize_only_touches_the_file_name() {
        assert_eq!(fat_sanitize(Path::new("I/¿qué?.txt")), PathBuf::from("I/¿qué_.txt"));
        assert_eq!(fat_sanitize(Path::new("a:b*c.txt")), PathBuf::from("a_b_c.txt"));
    }

    #[test]
    fn an_empty_void_plans_nothing_and_copies_nothing() {
        let v = tempfile::tempdir().unwrap();
        let dest = tempfile::tempdir().unwrap();
        let p = plan(v.path(), dest.path(), "25-01-01");
        assert!(p.files.is_empty());
        assert_eq!(p.total_bytes(), 0);
        assert_eq!(run(v.path(), &p).unwrap(), 0);
    }
}

//! The `/void` data layer — a port of the file half of `io_mixin.py`.
//!
//! `/void` holds real writing: a lost text cannot be recovered. Every write here
//! is atomic (temp file + rename) so a crash can never leave a half-written
//! file, and git is the version history underneath.

#![allow(dead_code)]

use std::fs;
use std::io;
use std::path::{Path, PathBuf};
use std::process::Command;

/// A document loaded from disk.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Doc {
    pub lines: Vec<String>,
    /// True when an existing file failed to read. Saving must be blocked while
    /// this is set, or we'd overwrite content we couldn't read.
    pub read_failed: bool,
}

/// Read a document the way Voider sees it: blank lines dropped, every line
/// trimmed, and a leading `.` separator guaranteed so the last and first
/// paragraphs stay apart when the ring wraps. A missing file is an empty doc
/// (that's legitimate — a new chapter); an unreadable one sets `read_failed`.
pub fn load_doc(path: &Path) -> Doc {
    let mut lines: Vec<String> = Vec::new();
    let mut read_failed = false;
    match fs::read_to_string(path) {
        Ok(text) => {
            for raw in text.lines() {
                let s = raw.trim();
                if !s.is_empty() {
                    lines.push(s.to_string());
                }
            }
        }
        // A genuinely absent file is an empty doc — saving it is safe.
        Err(e) if e.kind() == io::ErrorKind::NotFound => {}
        // A transient/permission/decode error on a file that DOES exist: refuse
        // to report an empty doc, or a later save would clobber what we couldn't read.
        Err(_) => read_failed = true,
    }
    if lines.first().is_some_and(|l| l != ".") {
        lines.insert(0, ".".to_string());
    }
    if lines.is_empty() {
        lines.push(".".to_string());
    }
    Doc { lines, read_failed }
}

/// Write `lines` to `path` crash-safely: a temp file in the same directory,
/// then a rename over the target. With `backup`, the previous contents are
/// copied to `path.bak` first so a bad rewrite can be undone.
pub fn atomic_write(path: &Path, lines: &[String], backup: bool) -> io::Result<()> {
    if backup && path.exists() {
        // Best effort, as in Python: a missing backup must not block the save.
        let _ = fs::copy(path, backup_path(path));
    }
    let dir = match path.parent() {
        Some(p) if !p.as_os_str().is_empty() => p.to_path_buf(),
        _ => PathBuf::from("."),
    };
    fs::create_dir_all(&dir)?;

    let mut body = String::new();
    for line in lines {
        body.push_str(line);
        body.push('\n');
    }
    let tmp = dir.join(format!(
        ".voider-{}-{}.tmp",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_nanos())
            .unwrap_or(0)
    ));
    // Write the whole body, then rename over the target: a reader either sees
    // the old file or the new one, never a half-written one.
    if let Err(e) = fs::write(&tmp, body).and_then(|()| fs::rename(&tmp, path)) {
        let _ = fs::remove_file(&tmp);
        return Err(e);
    }
    Ok(())
}

/// `foo.txt` → `foo.txt.bak` (the Python side appends, it doesn't replace).
pub fn backup_path(path: &Path) -> PathBuf {
    let mut s = path.as_os_str().to_os_string();
    s.push(".bak");
    PathBuf::from(s)
}

/// `git add -A <scope> && git commit` inside `void_dir`. `scope` is a path like
/// `I/` (the snapshot before a destructive write) or `.` (the whole void).
pub fn git_commit(void_dir: &Path, scope: &str, message: &str) -> CommitOutcome {
    let add = Command::new("git")
        .arg("-C")
        .arg(void_dir)
        .args(["add", "-A", scope])
        .output();
    if let Err(e) = add {
        return CommitOutcome::Failed { error: e.to_string() };
    }
    match Command::new("git")
        .arg("-C")
        .arg(void_dir)
        .args(["commit", "-m", message])
        .output()
    {
        Ok(out) => {
            let text = format!(
                "{}{}",
                String::from_utf8_lossy(&out.stdout),
                String::from_utf8_lossy(&out.stderr)
            );
            if out.status.success() {
                CommitOutcome::Committed { stat: commit_stat_line(&text) }
            } else if text.to_lowercase().contains("nothing to commit") {
                CommitOutcome::NothingToCommit
            } else {
                CommitOutcome::Failed { error: text.trim().to_string() }
            }
        }
        Err(e) => CommitOutcome::Failed { error: e.to_string() },
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum CommitOutcome {
    /// Committed, carrying git's own summary line when it gave one.
    Committed { stat: String },
    /// Nothing staged — the void was already up to date.
    NothingToCommit,
    Failed { error: String },
}

/// Pull git's "N files changed, X insertions(+), Y deletions(-)" out of its
/// output, or "" when there isn't one.
pub fn commit_stat_line(text: &str) -> String {
    text.lines()
        .map(str::trim)
        .find(|l| l.contains("changed") && l.contains("file"))
        .unwrap_or("")
        .to_string()
}

/// A timestamp in the `snapshot <ts>` format the Python side writes.
pub fn timestamp() -> String {
    chrono::Local::now().format("%Y-%m-%d %H:%M:%S").to_string()
}

/// Where the sandbox void lives while the mirror is young. The real `/void` is
/// only touched once reads, writes and git are proven here. `VOIDER_RS_VOID`
/// overrides it.
pub fn sandbox_dir() -> PathBuf {
    if let Ok(p) = std::env::var("VOIDER_RS_VOID") {
        if !p.is_empty() {
            return PathBuf::from(p);
        }
    }
    let home = std::env::var("HOME").unwrap_or_else(|_| ".".to_string());
    Path::new(&home).join(".local/share/voider-rs/void")
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    fn write(path: &Path, text: &str) {
        fs::write(path, text).unwrap();
    }

    #[test]
    fn missing_file_is_an_empty_doc() {
        let d = tempfile::tempdir().unwrap();
        let doc = load_doc(&d.path().join("nope.txt"));
        assert_eq!(doc.lines, vec!["."]);
        assert!(!doc.read_failed); // absent is legitimate, saving stays allowed
    }

    #[test]
    fn blank_lines_dropped_and_leading_dot_added() {
        let d = tempfile::tempdir().unwrap();
        let p = d.path().join("c.txt");
        write(&p, "primera\n\n  segunda  \n\n");
        let doc = load_doc(&p);
        assert_eq!(doc.lines, vec![".", "primera", "segunda"]);
    }

    #[test]
    fn existing_leading_dot_is_not_duplicated() {
        let d = tempfile::tempdir().unwrap();
        let p = d.path().join("c.txt");
        write(&p, ".\nuna\n");
        let doc = load_doc(&p);
        assert_eq!(doc.lines, vec![".", "una"]);
    }

    #[test]
    fn atomic_write_roundtrips() {
        let d = tempfile::tempdir().unwrap();
        let p = d.path().join("c.txt");
        let lines = vec![".".to_string(), "una linea".to_string()];
        atomic_write(&p, &lines, false).unwrap();
        assert_eq!(fs::read_to_string(&p).unwrap(), ".\nuna linea\n");
        assert_eq!(load_doc(&p).lines, lines);
    }

    #[test]
    fn atomic_write_leaves_no_temp_files() {
        let d = tempfile::tempdir().unwrap();
        let p = d.path().join("c.txt");
        atomic_write(&p, &["x".to_string()], false).unwrap();
        let names: Vec<_> = fs::read_dir(d.path())
            .unwrap()
            .map(|e| e.unwrap().file_name().to_string_lossy().to_string())
            .collect();
        assert_eq!(names, vec!["c.txt"]); // the temp file was renamed, not left
    }

    #[test]
    fn backup_keeps_the_previous_contents() {
        let d = tempfile::tempdir().unwrap();
        let p = d.path().join("c.txt");
        write(&p, "viejo\n");
        atomic_write(&p, &["nuevo".to_string()], true).unwrap();
        assert_eq!(fs::read_to_string(&p).unwrap(), "nuevo\n");
        assert_eq!(
            fs::read_to_string(p.with_extension("txt.bak")).unwrap(),
            "viejo\n"
        );
    }

    #[test]
    fn writing_creates_the_file_when_absent() {
        let d = tempfile::tempdir().unwrap();
        let p = d.path().join("new.txt");
        atomic_write(&p, &["a".to_string()], true).unwrap(); // backup on a missing file is fine
        assert!(p.exists());
    }

    #[test]
    fn stat_line_is_extracted() {
        let out = "[archive 1a2b3c] snapshot\n 1 file changed, 142 insertions(+), 123 deletions(-)\n";
        assert_eq!(
            commit_stat_line(out),
            "1 file changed, 142 insertions(+), 123 deletions(-)"
        );
        assert_eq!(commit_stat_line("nothing to commit"), "");
    }

    #[test]
    fn git_commit_reports_committed_then_nothing() {
        let d = tempfile::tempdir().unwrap();
        let dir = d.path();
        for args in [
            vec!["init", "-q"],
            vec!["config", "user.email", "t@t"],
            vec!["config", "user.name", "t"],
        ] {
            Command::new("git").arg("-C").arg(dir).args(&args).output().unwrap();
        }
        fs::create_dir_all(dir.join("I")).unwrap();
        write(&dir.join("I/a.txt"), "hola\n");

        match git_commit(dir, "I/", "snapshot test") {
            CommitOutcome::Committed { stat } => assert!(stat.contains("changed"), "stat: {stat}"),
            other => panic!("expected Committed, got {other:?}"),
        }
        // Nothing changed since → git has nothing to stage.
        assert_eq!(git_commit(dir, "I/", "snapshot test"), CommitOutcome::NothingToCommit);
    }

    #[test]
    fn timestamp_looks_like_a_date() {
        let ts = timestamp();
        assert_eq!(ts.len(), 19, "expected YYYY-MM-DD HH:MM:SS, got {ts:?}");
        assert_eq!(&ts[4..5], "-");
        assert_eq!(&ts[10..11], " ");
    }
}

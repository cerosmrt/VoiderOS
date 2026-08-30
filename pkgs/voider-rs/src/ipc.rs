//! Telling the other Voiders that a file changed — a port of `ipc.py`.
//!
//! Voider can be open more than once at a time, on the same void. Without this,
//! two instances holding the same file in memory quietly overwrite each other:
//! whoever saves last wins, and the other's lines are gone. There is no lock —
//! locks would make the second window read-only, which is not what a writer
//! wants — so instead every save announces itself and the others re-read.
//!
//! The shape is the Python's: the first instance to start binds the socket and
//! becomes the hub; later ones connect to it as clients. On save each sends
//! `SAVED:<path>\n`, and the hub forwards it to everyone else. A socket left
//! behind by a crash is reclaimed rather than fatal.
//!
//! Built on `std::os::unix::net`, so it costs no dependency, and polled once a
//! frame from the event loop rather than driven by callbacks.
//!
//! The socket name is voider-rs's own, deliberately NOT shared with the Python.
//! The two point at different voids; a save here must never make the real
//! Voider reload something that isn't its own.

#![allow(dead_code)]

use std::io::{ErrorKind, Read, Write};
#[cfg(unix)]
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::{Path, PathBuf};

const PREFIX: &str = "SAVED:";

/// Where the socket lives: the runtime dir if there is one, else /tmp.
pub fn default_socket_path() -> PathBuf {
    let dir = std::env::var("XDG_RUNTIME_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("/tmp"));
    dir.join("voider-rs.sock")
}

#[cfg(unix)]
enum Role {
    /// First one here: owns the socket and relays between the others.
    Hub {
        listener: UnixListener,
        peers: Vec<(UnixStream, Vec<u8>)>,
    },
    /// Someone else got here first.
    Client { stream: UnixStream, buf: Vec<u8> },
    /// Neither worked; this instance simply runs alone.
    Alone,
}

#[cfg(unix)]
pub struct Ipc {
    role: Role,
    path: PathBuf,
}

#[cfg(unix)]
impl Ipc {
    /// Bind the socket, or connect to whoever already has it. A socket file
    /// left behind by a crashed run refuses connections; that is the signal it
    /// is stale, so it gets removed and rebound rather than blocking startup.
    pub fn start(path: &Path) -> Self {
        if let Ok(listener) = UnixListener::bind(path) {
            let _ = listener.set_nonblocking(true);
            return Self {
                role: Role::Hub { listener, peers: Vec::new() },
                path: path.to_path_buf(),
            };
        }
        if let Ok(stream) = UnixStream::connect(path) {
            let _ = stream.set_nonblocking(true);
            return Self {
                role: Role::Client { stream, buf: Vec::new() },
                path: path.to_path_buf(),
            };
        }
        // Nobody is listening on it: it's a leftover. Reclaim it.
        let _ = std::fs::remove_file(path);
        match UnixListener::bind(path) {
            Ok(listener) => {
                let _ = listener.set_nonblocking(true);
                Self {
                    role: Role::Hub { listener, peers: Vec::new() },
                    path: path.to_path_buf(),
                }
            }
            Err(_) => Self { role: Role::Alone, path: path.to_path_buf() },
        }
    }

    pub fn is_hub(&self) -> bool {
        matches!(self.role, Role::Hub { .. })
    }

    pub fn is_alone(&self) -> bool {
        matches!(self.role, Role::Alone)
    }

    /// Announce a save. Best effort: a sibling that has gone away must never
    /// stop this instance from writing.
    pub fn notify_saved(&mut self, saved: &Path) {
        let raw = format!("{PREFIX}{}\n", saved.display()).into_bytes();
        match &mut self.role {
            Role::Hub { peers, .. } => {
                for (stream, _) in peers.iter_mut() {
                    let _ = stream.write_all(&raw);
                }
            }
            Role::Client { stream, .. } => {
                let _ = stream.write_all(&raw);
            }
            Role::Alone => {}
        }
    }

    /// Take in whatever arrived since last time: the paths other instances
    /// saved. Never blocks.
    pub fn poll(&mut self) -> Vec<PathBuf> {
        let mut out = Vec::new();
        match &mut self.role {
            Role::Hub { listener, peers } => {
                // Anyone new?
                while let Ok((stream, _)) = listener.accept() {
                    let _ = stream.set_nonblocking(true);
                    peers.push((stream, Vec::new()));
                }
                // Read everyone, noting which messages came from whom so they
                // can be relayed onward without echoing back to the sender.
                let mut relay: Vec<(usize, String)> = Vec::new();
                let mut dead = Vec::new();
                for (i, (stream, buf)) in peers.iter_mut().enumerate() {
                    match drain(stream, buf) {
                        Ok(msgs) => {
                            for m in msgs {
                                relay.push((i, m));
                            }
                        }
                        Err(()) => dead.push(i),
                    }
                }
                for (from, msg) in &relay {
                    let raw = format!("{msg}\n").into_bytes();
                    for (i, (stream, _)) in peers.iter_mut().enumerate() {
                        if i != *from {
                            let _ = stream.write_all(&raw);
                        }
                    }
                    if let Some(p) = parse(msg) {
                        out.push(p);
                    }
                }
                for i in dead.into_iter().rev() {
                    peers.remove(i);
                }
            }
            Role::Client { stream, buf } => match drain(stream, buf) {
                Ok(msgs) => {
                    for m in msgs {
                        if let Some(p) = parse(&m) {
                            out.push(p);
                        }
                    }
                }
                // The hub went away. Carry on alone rather than dying.
                Err(()) => self.role = Role::Alone,
            },
            Role::Alone => {}
        }
        out
    }
}

#[cfg(unix)]
impl Drop for Ipc {
    fn drop(&mut self) {
        // Only the hub owns the file, so only the hub clears it.
        if self.is_hub() {
            let _ = std::fs::remove_file(&self.path);
        }
    }
}

/// Read what's available and cut it into whole lines, keeping any partial tail
/// for next time. `Err(())` means the peer is gone.
#[cfg(unix)]
fn drain(stream: &mut UnixStream, buf: &mut Vec<u8>) -> Result<Vec<String>, ()> {
    let mut chunk = [0u8; 4096];
    loop {
        match stream.read(&mut chunk) {
            Ok(0) => return Err(()), // closed
            Ok(n) => buf.extend_from_slice(&chunk[..n]),
            Err(e) if e.kind() == ErrorKind::WouldBlock => break,
            Err(e) if e.kind() == ErrorKind::Interrupted => continue,
            Err(_) => return Err(()),
        }
    }
    let mut msgs = Vec::new();
    while let Some(pos) = buf.iter().position(|b| *b == b'\n') {
        let line: Vec<u8> = buf.drain(..=pos).take(pos).collect();
        msgs.push(String::from_utf8_lossy(&line).to_string());
    }
    Ok(msgs)
}


// ── Sin sockets de Unix (Windows) ───────────────────────────────────────────
//
// La sincronización entre instancias vive sobre sockets de dominio Unix, que en
// Windows no existen (habría que usar named pipes). Acá va un stub inerte con la
// misma interfaz: la aplicación no se entera, y simplemente no hay aviso entre
// ventanas.
//
// Se pierde poco: el escenario que esto protege es tener dos Voider abiertos
// sobre el mismo void, que es una costumbre de la máquina de escritura, no de
// una copia portátil. Vale saberlo igual — en Windows, dos ventanas sobre el
// mismo texto se pisan como lo hacía el Python antes del IPC.

#[cfg(not(unix))]
pub struct Ipc {
    path: PathBuf,
}

#[cfg(not(unix))]
impl Ipc {
    pub fn start(path: &Path) -> Self {
        Self { path: path.to_path_buf() }
    }
    pub fn is_hub(&self) -> bool {
        false
    }
    pub fn is_alone(&self) -> bool {
        true
    }
    pub fn notify_saved(&mut self, _saved: &Path) {}
    pub fn poll(&mut self) -> Vec<PathBuf> {
        Vec::new()
    }
}
fn parse(msg: &str) -> Option<PathBuf> {
    msg.strip_prefix(PREFIX).map(PathBuf::from)
}

#[cfg(unix)]
#[cfg(test)]
mod tests {
    use super::*;

    fn sock(dir: &tempfile::TempDir) -> PathBuf {
        dir.path().join("test.sock")
    }

    /// Give the OS a moment to move bytes across the socket.
    fn settle() {
        std::thread::sleep(std::time::Duration::from_millis(60));
    }

    #[test]
    fn the_first_one_here_becomes_the_hub() {
        let d = tempfile::tempdir().unwrap();
        let a = Ipc::start(&sock(&d));
        assert!(a.is_hub());
        let b = Ipc::start(&sock(&d));
        assert!(!b.is_hub() && !b.is_alone()); // a client
    }

    #[test]
    fn a_client_save_reaches_the_hub() {
        let d = tempfile::tempdir().unwrap();
        let mut hub = Ipc::start(&sock(&d));
        let mut client = Ipc::start(&sock(&d));
        hub.poll(); // accept the connection
        client.notify_saved(Path::new("/void/I/a.txt"));
        settle();
        assert_eq!(hub.poll(), vec![PathBuf::from("/void/I/a.txt")]);
    }

    #[test]
    fn a_hub_save_reaches_the_client() {
        let d = tempfile::tempdir().unwrap();
        let mut hub = Ipc::start(&sock(&d));
        let mut client = Ipc::start(&sock(&d));
        hub.poll();
        hub.notify_saved(Path::new("/void/I/b.txt"));
        settle();
        assert_eq!(client.poll(), vec![PathBuf::from("/void/I/b.txt")]);
    }

    #[test]
    fn the_hub_relays_between_two_clients_without_echoing_back() {
        let d = tempfile::tempdir().unwrap();
        let mut hub = Ipc::start(&sock(&d));
        let mut one = Ipc::start(&sock(&d));
        let mut two = Ipc::start(&sock(&d));
        hub.poll();
        one.notify_saved(Path::new("/void/I/c.txt"));
        settle();
        hub.poll(); // the hub reads and forwards
        settle();
        assert_eq!(two.poll(), vec![PathBuf::from("/void/I/c.txt")]);
        assert!(one.poll().is_empty(), "a save must not come back to its sender");
    }

    #[test]
    fn nothing_arrives_when_nothing_was_saved() {
        let d = tempfile::tempdir().unwrap();
        let mut hub = Ipc::start(&sock(&d));
        let mut client = Ipc::start(&sock(&d));
        hub.poll();
        assert!(hub.poll().is_empty());
        assert!(client.poll().is_empty());
    }

    #[test]
    fn a_socket_left_by_a_crash_is_reclaimed() {
        let d = tempfile::tempdir().unwrap();
        let p = sock(&d);
        // A file sitting at the path that nobody is listening on.
        std::fs::write(&p, b"stale").unwrap();
        let a = Ipc::start(&p);
        assert!(a.is_hub(), "a dead socket must not stop Voider from opening");
    }

    #[test]
    fn several_saves_in_one_go_all_arrive() {
        let d = tempfile::tempdir().unwrap();
        let mut hub = Ipc::start(&sock(&d));
        let mut client = Ipc::start(&sock(&d));
        hub.poll();
        client.notify_saved(Path::new("/a.txt"));
        client.notify_saved(Path::new("/b.txt"));
        settle();
        assert_eq!(hub.poll(), vec![PathBuf::from("/a.txt"), PathBuf::from("/b.txt")]);
    }

    #[test]
    fn a_path_with_spaces_survives_the_trip() {
        let d = tempfile::tempdir().unwrap();
        let mut hub = Ipc::start(&sock(&d));
        let mut client = Ipc::start(&sock(&d));
        hub.poll();
        let path = Path::new("/void/I/Capitulo III — el altar.txt");
        client.notify_saved(path);
        settle();
        assert_eq!(hub.poll(), vec![path.to_path_buf()]);
    }

    #[test]
    fn running_alone_is_harmless() {
        let mut solo = Ipc {
            role: Role::Alone,
            path: PathBuf::from("/nowhere"),
        };
        solo.notify_saved(Path::new("/a.txt")); // must not panic
        assert!(solo.poll().is_empty());
    }

    #[test]
    fn only_saved_messages_are_understood() {
        assert_eq!(parse("SAVED:/a.txt"), Some(PathBuf::from("/a.txt")));
        assert_eq!(parse("HELLO:/a.txt"), None);
        assert_eq!(parse(""), None);
    }
}

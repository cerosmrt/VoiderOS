from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtCore import QObject, pyqtSignal

_SERVER_NAME = "voider_ipc"
_CONNECT_TIMEOUT_MS = 300


class VoiderIPC(QObject):
    """Notifies sibling Voider instances when a file is saved.

    First instance to start becomes the relay hub (QLocalServer).
    All later instances connect as clients (QLocalSocket).
    On save, every instance sends SAVED:<path>\\n; the hub forwards it to all
    other connected instances so they can reload the file from disk.
    """

    file_saved_by_other = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._server = None
        self._client_socket = None
        self._peer_sockets = []
        self._peer_bufs = {}
        self._client_buf = b""
        self._start()

    def _start(self):
        server = QLocalServer(self)
        if server.listen(_SERVER_NAME):
            self._server = server
            server.newConnection.connect(self._on_new_connection)
            return
        # Another instance is already the hub; connect as client.
        sock = QLocalSocket(self)
        sock.connectToServer(_SERVER_NAME)
        if sock.waitForConnected(_CONNECT_TIMEOUT_MS):
            sock.readyRead.connect(self._on_client_ready)
            sock.disconnected.connect(self._on_server_gone)
            self._client_socket = sock
        else:
            # Stale socket from a crashed previous run — reclaim it.
            sock.abort()
            QLocalServer.removeServer(_SERVER_NAME)
            if server.listen(_SERVER_NAME):
                self._server = server
                server.newConnection.connect(self._on_new_connection)

    # ── server side ──────────────────────────────────────────────────────────

    def _on_new_connection(self):
        while self._server.hasPendingConnections():
            sock = self._server.nextPendingConnection()
            self._peer_sockets.append(sock)
            self._peer_bufs[sock] = b""
            sock.readyRead.connect(lambda s=sock: self._on_peer_ready(s))
            sock.disconnected.connect(lambda s=sock: self._drop_peer(s))

    def _drop_peer(self, sock):
        self._peer_sockets = [s for s in self._peer_sockets if s is not sock]
        self._peer_bufs.pop(sock, None)

    def _on_peer_ready(self, sock):
        self._peer_bufs[sock] = self._peer_bufs.get(sock, b"") + sock.readAll().data()
        msgs, self._peer_bufs[sock] = _split_lines(self._peer_bufs[sock])
        if msgs:
            raw = b"".join((m + "\n").encode() for m in msgs)
            for peer in self._peer_sockets:
                if peer is not sock:
                    peer.write(raw)
        for msg in msgs:
            self._dispatch(msg)

    # ── client side ──────────────────────────────────────────────────────────

    def _on_client_ready(self):
        self._client_buf += self._client_socket.readAll().data()
        msgs, self._client_buf = _split_lines(self._client_buf)
        for msg in msgs:
            self._dispatch(msg)

    def _on_server_gone(self):
        if self._client_socket:
            self._client_socket.abort()
            self._client_socket = None

    # ── shared ───────────────────────────────────────────────────────────────

    def _dispatch(self, msg: str):
        if msg.startswith("SAVED:"):
            self.file_saved_by_other.emit(msg[6:])

    def notify_saved(self, path: str):
        """Call after every successful file write."""
        raw = f"SAVED:{path}\n".encode()
        if self._server is not None:
            for peer in self._peer_sockets:
                peer.write(raw)
        elif self._client_socket is not None:
            self._client_socket.write(raw)


def _split_lines(buf: bytes) -> tuple[list[str], bytes]:
    parts = buf.split(b"\n")
    return [p.decode("utf-8", errors="replace") for p in parts[:-1]], parts[-1]

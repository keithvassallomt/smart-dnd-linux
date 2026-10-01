"""IPC Server and Client over Unix Domain Sockets for Smart DND."""

from __future__ import annotations

import json
import logging
import os
import socket
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from smart_dnd.models import CalendarSource, Config, Status

logger = logging.getLogger(__name__)


def get_socket_path() -> Path:
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if runtime_dir:
        base = Path(runtime_dir) / "smart-dnd"
    else:
        base = Path(f"/tmp/smart-dnd-{os.getuid()}")
    base.mkdir(parents=True, exist_ok=True)
    return base / "ipc.sock"


class IpcServer:
    """Unix domain socket JSON-RPC server running inside the daemon."""

    def __init__(self, dispatch_fn: Callable[[str, Dict[str, Any]], Any]) -> None:
        self.dispatch_fn = dispatch_fn
        self.sock_path = get_socket_path()
        self._server_sock: Optional[socket.socket] = None

    def start(self) -> socket.socket:
        if self.sock_path.exists():
            try:
                # Test if another daemon is already responding
                client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                client.connect(str(self.sock_path))
                client.close()
                raise RuntimeError(f"Smart DND socket already in use at {self.sock_path}. Is daemon running?")
            except (ConnectionRefusedError, FileNotFoundError):
                self.sock_path.unlink(missing_ok=True)

        self._server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server_sock.bind(str(self.sock_path))
        self._server_sock.listen(10)
        self._server_sock.setblocking(False)
        logger.info("IPC Server listening on %s", self.sock_path)
        return self._server_sock

    def handle_client(self, client_sock: socket.socket) -> None:
        try:
            data = b""
            while True:
                chunk = client_sock.recv(4096)
                if not chunk:
                    break
                data += chunk
                if b"\n" in data:
                    break
            if not data:
                return

            line = data.decode("utf-8").strip()
            req = json.loads(line)
            method = req.get("method", "")
            params = req.get("params", {})

            try:
                result = self.dispatch_fn(method, params)
                resp = {"result": result, "error": None}
            except Exception as e:
                logger.error("Error handling IPC method %s: %s", method, e)
                resp = {"result": None, "error": str(e)}

            client_sock.sendall((json.dumps(resp) + "\n").encode("utf-8"))
        except (BrokenPipeError, ConnectionResetError):
            logger.debug("Client closed connection before response could be delivered.")
        except Exception as e:
            logger.debug("Client communication error: %s", e)
        finally:
            client_sock.close()

    def close(self) -> None:
        if self._server_sock:
            self._server_sock.close()
            self._server_sock = None
        self.sock_path.unlink(missing_ok=True)


class SmartDndClient:
    """Client to query or control the Smart DND daemon over Unix socket."""

    def __init__(self, sock_path: Optional[Path] = None) -> None:
        self.sock_path = sock_path or get_socket_path()

    def is_daemon_running(self) -> bool:
        if not self.sock_path.exists():
            return False
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(1.0)
                s.connect(str(self.sock_path))
                return True
        except Exception:
            return False

    def call(self, method: str, params: Optional[Dict[str, Any]] = None) -> Any:
        params = params or {}
        payload = json.dumps({"method": method, "params": params}) + "\n"
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(20.0)
            s.connect(str(self.sock_path))
            s.sendall(payload.encode("utf-8"))
            data = b""
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                data += chunk
                if b"\n" in data:
                    break

        resp = json.loads(data.decode("utf-8").strip())
        if resp.get("error"):
            raise RuntimeError(f"Daemon error: {resp['error']}")
        return resp.get("result")

    def get_status(self) -> Status:
        res = self.call("get_status")
        return Status(**res)

    def get_config(self) -> Config:
        res = self.call("get_config")
        return Config.from_dict(res)

    def save_config(self, config: Config) -> bool:
        return bool(self.call("save_config", {"config": config.to_dict()}))

    def evaluate(self) -> Status:
        res = self.call("evaluate")
        return Status(**res)

    def toggle_dnd(self) -> bool:
        return bool(self.call("toggle_dnd"))

    def list_calendars(self) -> List[CalendarSource]:
        res = self.call("list_calendars")
        return [CalendarSource(**c) for c in res]

    def get_events(self) -> List[Any]:
        try:
            from smart_dnd.models import CalendarEvent
            res = self.call("get_events")
            return [CalendarEvent(**e) for e in res]
        except Exception:
            return []

    def list_plugins(self) -> Dict[str, List[str]]:
        return dict(self.call("list_plugins"))

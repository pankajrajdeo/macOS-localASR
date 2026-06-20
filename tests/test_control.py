from __future__ import annotations

import json
import socket
import tempfile
import threading
import unittest
from pathlib import Path

from macos_local_asr import cli


class ControlSocketTests(unittest.TestCase):
    def test_send_control_command_round_trips_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            socket_path = Path(tmp) / "control.sock"
            expected = {"ok": True, "recording": False, "locked": False, "model_loaded": True}
            seen: list[dict[str, object]] = []
            ready = threading.Event()

            def serve_once() -> None:
                server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                try:
                    server.bind(str(socket_path))
                    server.listen(1)
                    server.settimeout(2.0)
                    ready.set()
                    conn, _addr = server.accept()
                    with conn:
                        request = conn.recv(4096).decode("utf-8").strip()
                        seen.append(json.loads(request))
                        conn.sendall((json.dumps(expected) + "\n").encode("utf-8"))
                finally:
                    server.close()

            thread = threading.Thread(target=serve_once, daemon=True)
            thread.start()
            self.assertTrue(ready.wait(timeout=1.0))
            old_path = cli.CONTROL_SOCKET_PATH
            try:
                cli.CONTROL_SOCKET_PATH = socket_path
                response = cli.send_control_command({"command": "status"}, timeout=1.0)
            finally:
                cli.CONTROL_SOCKET_PATH = old_path
                thread.join(timeout=1.0)

            self.assertEqual(response, expected)
            self.assertEqual(seen, [{"command": "status"}])


if __name__ == "__main__":
    unittest.main()

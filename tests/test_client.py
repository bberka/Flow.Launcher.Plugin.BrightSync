import http.server
import json
import os
import secrets
import socket
import sys
import tempfile
import threading
import typing
import unittest

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PLUGIN_DIR)

import brightsync_client as client  # noqa: E402

# Fixed route on the fake server. Tests patch client.COMMANDS_PATH, so this must not read it.
KNOWN_ROUTE = "/v1/commands"


class _FakeBrightSyncServer(http.server.ThreadingHTTPServer):
    def __init__(self, token):
        super().__init__(("127.0.0.1", 0), _FakeBrightSyncHandler)
        self.token = token
        self.seen = []
        self.reply_status = 200
        self.reply_body = {"Success": True, "ExitCode": 0, "Message": "ok"}


class _FakeBrightSyncHandler(http.server.BaseHTTPRequestHandler):
    """Fake command server. Auth is checked against the server's token; state lives on the server."""

    def do_POST(self):
        server = typing.cast(_FakeBrightSyncServer, self.server)
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        server.seen.append({
            "path": self.path,
            "auth": self.headers.get("Authorization"),
            "body": json.loads(raw) if raw else None,
        })

        if self.headers.get("Authorization") != f"Bearer {server.token}":
            self._reply(401, {"Success": False, "ExitCode": 5, "Message": "unauthorized"})
        elif self.path != KNOWN_ROUTE:
            self._reply(404, {"Success": False, "ExitCode": 1, "Message": "unknown route"})
        else:
            self._reply(server.reply_status, server.reply_body)

    def _reply(self, status, obj):
        data = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        # Keep test output quiet.
        pass


class ClientTests(unittest.TestCase):
    def setUp(self):
        # Generated per test run, not a fixed literal.
        self.token = secrets.token_hex(16)
        self.server = _FakeBrightSyncServer(self.token)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

        self.tmp = tempfile.TemporaryDirectory()
        self.metadata = os.path.join(self.tmp.name, "command-server.json")

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def write_metadata(self, base_url, token=None):
        # BrightSync writes the file with a UTF-8 BOM, so write it the same way.
        with open(self.metadata, "w", encoding="utf-8-sig") as handle:
            json.dump({
                "BaseUrl": base_url,
                "BearerToken": self.token if token is None else token,
                "Pid": 1,
                "StartedUtc": "2026-01-01T00:00:00Z",
            }, handle)

    def test_sends_bearer_token_and_pascal_case_body(self):
        self.write_metadata(f"http://127.0.0.1:{self.port}/")

        response = client.call(client.build_request(client.CommandType.BRIGHTNESS_SET, brightness=40),
                               metadata_file=self.metadata)

        self.assertTrue(response["Success"])
        seen = self.server.seen[-1]
        self.assertEqual(seen["path"], "/v1/commands")
        self.assertEqual(seen["auth"], f"Bearer {self.token}")
        self.assertEqual(seen["body"], {"CommandType": 0, "BrightnessValue": 40})

    def test_failed_command_body_is_returned_not_raised(self):
        self.write_metadata(f"http://127.0.0.1:{self.port}/")
        self.server.reply_status = 400
        self.server.reply_body = {
            "Success": False,
            "ExitCode": 4,
            "Message": "Automatic brightness is enabled. Disable it before using manual brightness commands.",
        }

        response = client.call(client.build_request(client.CommandType.BRIGHTNESS_SET, brightness=40),
                               metadata_file=self.metadata)

        self.assertFalse(response["Success"])
        self.assertEqual(response["ExitCode"], 4)

    def test_wrong_token_is_auth_error(self):
        self.write_metadata(f"http://127.0.0.1:{self.port}/", token=secrets.token_hex(16))

        with self.assertRaises(client.BrightSyncAuthError):
            client.call(client.build_request(client.CommandType.STATUS), metadata_file=self.metadata)

    def test_404_route_means_not_running(self):
        self.write_metadata(f"http://127.0.0.1:{self.port}/")
        original = client.COMMANDS_PATH
        try:
            client.COMMANDS_PATH = "/v1/unknown"
            with self.assertRaises(client.BrightSyncUnavailable):
                client.call(client.build_request(client.CommandType.STATUS), metadata_file=self.metadata)
        finally:
            client.COMMANDS_PATH = original

    def test_missing_metadata_is_not_running(self):
        with self.assertRaises(client.BrightSyncUnavailable):
            client.call(client.build_request(client.CommandType.STATUS),
                        metadata_file=os.path.join(self.tmp.name, "missing.json"))

    def test_closed_port_is_not_running(self):
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()

        self.write_metadata(f"http://127.0.0.1:{port}/")
        with self.assertRaises(client.BrightSyncUnavailable):
            client.call(client.build_request(client.CommandType.STATUS), metadata_file=self.metadata)

    def test_non_loopback_base_url_never_gets_token(self):
        for base_url in ("http://example.com:45137/", "https://127.0.0.1:45137/", "http://127.0.0.1/"):
            with self.subTest(base_url=base_url):
                self.write_metadata(base_url)
                with self.assertRaises(client.BrightSyncError) as raised:
                    client.call(client.build_request(client.CommandType.STATUS), metadata_file=self.metadata)
                self.assertNotIsInstance(raised.exception, client.BrightSyncUnavailable)
        self.assertEqual(self.server.seen, [])


if __name__ == "__main__":
    unittest.main()

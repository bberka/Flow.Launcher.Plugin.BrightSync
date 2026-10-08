"""Client for BrightSync's local resident command API.

Talks to the HttpListener started by the tray app on 127.0.0.1. Every request
carries the per-run bearer token from %LocalAppData%\\BrightSync\\command-server.json.
Standard library only, so the plugin runs on any Python Flow Launcher is set to use.
"""

import http.client
import json
import os
import urllib.parse

COMMANDS_PATH = "/v1/commands"
REQUEST_TIMEOUT_SECONDS = 2.0
LOOPBACK_HOSTS = ("127.0.0.1", "localhost")


class CommandType:
    """Mirrors BrightSync.Cli.AppCommandType. Enums serialize as integers."""

    BRIGHTNESS_SET = 0
    BRIGHTNESS_UP = 1
    BRIGHTNESS_DOWN = 2
    SETTINGS_SHOW = 3
    MONITORS_REFRESH = 4
    AUTO_ON = 5
    AUTO_OFF = 6
    EYE_PROTECTION_ON = 7
    EYE_PROTECTION_OFF = 8
    BOOST_ON = 9
    BOOST_OFF = 10
    STATUS = 11


class BrightSyncError(Exception):
    """Base error for anything that prevents a command from completing."""


class BrightSyncUnavailable(BrightSyncError):
    """The tray app is not running, or its command server is not reachable."""


class BrightSyncAuthError(BrightSyncError):
    """The server rejected the token in the metadata file."""


def metadata_path():
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    return os.path.join(base, "BrightSync", "command-server.json")


def read_server_info(path=None):
    """Return (base_url, bearer_token) from the metadata file, or None if unusable.

    The file is written with a UTF-8 BOM, so it is read with utf-8-sig.
    """
    try:
        with open(path or metadata_path(), encoding="utf-8-sig") as handle:
            info = json.load(handle)
    except (OSError, ValueError):
        return None

    base_url = info.get("BaseUrl")
    token = info.get("BearerToken")
    if not base_url or not token:
        return None
    return base_url, token


def build_request(command_type, brightness=None, step=None, enabled=None, hours=None):
    """Build the CommandRequest body. Unset fields are omitted, matching the C# client."""
    body = {"CommandType": int(command_type)}
    if brightness is not None:
        body["BrightnessValue"] = brightness
    if step is not None:
        body["StepValue"] = step
    if enabled is not None:
        body["Enabled"] = bool(enabled)
    if hours is not None:
        body["DurationHours"] = hours
    return body


def loopback_target(base_url):
    """Return (host, port) for the metadata base URL.

    Only plain http to a loopback host is accepted, so the bearer token never leaves the machine.
    """
    try:
        parts = urllib.parse.urlsplit(base_url)
        port = parts.port
    except ValueError as ex:
        raise BrightSyncError("BrightSync metadata has an invalid base URL.") from ex

    if parts.scheme != "http" or parts.hostname not in LOOPBACK_HOSTS or port is None:
        raise BrightSyncError("BrightSync metadata points at a non-loopback address. Refusing to send the token.")
    return parts.hostname, port


def send_command(base_url, token, request_body, timeout=REQUEST_TIMEOUT_SECONDS):
    """POST a command and return the decoded CommandResponse.

    A non-2xx response that still carries a CommandResponse body (for example a
    blocked manual brightness change) is returned as-is so the caller can show its message.
    """
    host, port = loopback_target(base_url)
    body = json.dumps(request_body).encode("utf-8")
    connection = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        connection.request(
            "POST",
            COMMANDS_PATH,
            body=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        response = connection.getresponse()
        status = response.status
        raw = response.read()
    except (OSError, http.client.HTTPException) as ex:
        # Connection refused, timeout, or a stale port after the app exited.
        raise BrightSyncUnavailable("BrightSync is not running.") from ex
    finally:
        connection.close()

    if status in (401, 403):
        raise BrightSyncAuthError("BrightSync rejected the command token. Restart BrightSync.")
    # Same as the C# client: 404 means the port answers but is not BrightSync (or is stale).
    if status == 404:
        raise BrightSyncUnavailable("BrightSync is not running.")

    try:
        return json.loads(raw.decode("utf-8"))
    except ValueError as ex:
        if 200 <= status < 300:
            raise BrightSyncError("BrightSync returned an unreadable response.") from ex
        raise BrightSyncError(f"BrightSync returned HTTP {status}.") from ex


def call(request_body, metadata_file=None):
    """Send one command using the current metadata file. Raises BrightSyncError subclasses."""
    info = read_server_info(metadata_file)
    if info is None:
        raise BrightSyncUnavailable("BrightSync is not running.")

    base_url, token = info
    return send_command(base_url, token, request_body)

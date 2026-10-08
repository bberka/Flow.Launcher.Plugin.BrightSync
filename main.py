"""Flow Launcher plugin for BrightSync (action keyword: bs).

Flow Launcher runs this file once per query or action with a JSON-RPC payload in argv[1].
Query results are printed as JSON. Actions print Flow.Launcher.* requests such as ShowMsg.
"""

from __future__ import annotations

import json
import os
import sys

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PLUGIN_DIR)

import brightsync_client as client  # noqa: E402
from query_parser import ParseError, parse  # noqa: E402

ICON = "icon.png"
ALLOWED_METHODS = ("query", "run_command", "noop")

HINTS = [
    ("bs 50", "Set brightness to a value from 0 to 100"),
    ("bs up 10", "Raise brightness by a step (default 10)"),
    ("bs down 10", "Lower brightness by a step (default 10)"),
    ("bs auto on", "Turn automatic brightness on"),
    ("bs auto off", "Turn automatic brightness off"),
    ("bs eye on 2", "Eye protection on, optional hours from 1 to 24"),
    ("bs eye off", "Eye protection off"),
    ("bs boost on 1", "Brightness boost on, optional hours from 1 to 24"),
    ("bs boost off", "Brightness boost off"),
    ("bs refresh", "Re-detect monitors"),
    ("bs settings", "Open BrightSync settings"),
]


def make_result(title, subtitle, method, parameters=None, keep_open=False):
    return {
        "Title": title,
        "SubTitle": subtitle,
        "IcoPath": ICON,
        "JsonRPCAction": {
            "method": method,
            "parameters": parameters or [],
            "dontHideAfterAction": keep_open,
        },
    }


def format_remaining(seconds):
    if seconds is None:
        return "on"
    minutes = int(seconds) // 60
    if minutes >= 60:
        return f"on ({minutes // 60}h {minutes % 60}m left)"
    return f"on ({minutes}m left)"


def format_status_details(status):
    parts = ["Auto on" if status.get("automaticBrightnessEnabled") else "Auto off"]

    if status.get("eyeProtectionActive"):
        parts.append("Eye protection " + format_remaining(status.get("eyeProtectionRemainingSeconds")))
    else:
        parts.append("Eye protection off")

    if status.get("brightnessBoostActive"):
        parts.append("Boost " + format_remaining(status.get("brightnessBoostRemainingSeconds")))
    else:
        parts.append("Boost off")

    total = status.get("monitorCount")
    if total is not None:
        parts.append(f"{status.get('controllableMonitorCount', 0)}/{total} monitors controllable")

    return " | ".join(parts)


class BrightSyncPlugin:
    def query(self, text=""):
        text = (text or "").strip()

        if not text:
            return self._status_results() + [
                make_result(example, description, "ChangeQuery", [example + " ", False], keep_open=True)
                for example, description in HINTS
            ]

        try:
            command = parse(text)
        except ParseError as ex:
            return [make_result("Invalid command", f"{ex}", "noop", keep_open=True)]

        if command.command_type == client.CommandType.STATUS:
            return self._status_results()

        return [
            make_result(
                command.title,
                "Press Enter to run",
                "run_command",
                [command.to_request(), command.title],
            )
        ]

    def run_command(self, request, title):
        try:
            response = client.call(request)
        except client.BrightSyncError as ex:
            self._show_msg("BrightSync", str(ex))
            return None

        success = bool(response.get("Success"))
        message = response.get("Message") or ("Done." if success else "Command failed.")
        heading = f"BrightSync: {title}" if success else f"BrightSync: {title} failed"
        self._show_msg(heading, message)
        return None

    def noop(self, *_args):
        return None

    def _status_results(self):
        try:
            response = client.call(client.build_request(client.CommandType.STATUS))
        except client.BrightSyncError as ex:
            return [make_result("BrightSync is not running", f"{ex} Start BrightSync, then try again.",
                                "noop", keep_open=True)]

        status = response.get("Status")
        if not response.get("Success") or not status:
            return [make_result("BrightSync", response.get("Message") or "No status returned.",
                                "noop", keep_open=True)]

        return [
            make_result(
                f"Brightness {status.get('masterBrightness')}%",
                format_status_details(status),
                "noop",
                keep_open=True,
            )
        ]

    def _show_msg(self, title, subtitle):
        print(json.dumps({
            "method": "Flow.Launcher.ShowMsg",
            "parameters": [title, subtitle, os.path.join(PLUGIN_DIR, ICON)],
        }))


def main(argv):
    try:
        rpc = json.loads(argv[1]) if len(argv) > 1 else {"method": "query", "parameters": [""]}
    except ValueError:
        return 2

    method = rpc.get("method", "query")
    parameters = rpc.get("parameters", [])
    if method not in ALLOWED_METHODS:
        return 1

    result = getattr(BrightSyncPlugin(), method)(*parameters)
    if method == "query":
        print(json.dumps({"result": result, "debugMessage": ""}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

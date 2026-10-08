import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PLUGIN_DIR)

import main  # noqa: E402


class PluginTests(unittest.TestCase):
    """Runs with LOCALAPPDATA pointed at an empty folder, so BrightSync is always 'not running'."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved_local_app_data = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = self.tmp.name

    def tearDown(self):
        if self.saved_local_app_data is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = self.saved_local_app_data
        self.tmp.cleanup()

    def test_command_query_builds_run_action(self):
        rows = main.BrightSyncPlugin().query("up 5")

        self.assertEqual(len(rows), 1)
        action = rows[0]["JsonRPCAction"]
        self.assertEqual(action["method"], "run_command")
        self.assertEqual(action["parameters"][0], {"CommandType": 1, "StepValue": 5})

    def test_invalid_query_shows_error_row_without_action_side_effects(self):
        rows = main.BrightSyncPlugin().query("999")

        self.assertEqual(rows[0]["Title"], "Invalid command")
        self.assertEqual(rows[0]["JsonRPCAction"]["method"], "noop")

    def test_empty_query_shows_not_running_status_and_hints(self):
        rows = main.BrightSyncPlugin().query("")

        self.assertEqual(rows[0]["Title"], "BrightSync is not running")
        hint_rows = rows[1:]
        self.assertEqual(len(hint_rows), len(main.HINTS))
        self.assertTrue(all(row["JsonRPCAction"]["method"] == "Flow.Launcher.ChangeQuery" for row in hint_rows))

    def test_bare_auto_offers_on_and_off_rows(self):
        rows = main.BrightSyncPlugin().query("auto")

        self.assertEqual([row["JsonRPCAction"]["parameters"][0] for row in rows], [
            {"CommandType": 5, "Enabled": True},
            {"CommandType": 6, "Enabled": False},
        ])
        self.assertTrue(all(row["JsonRPCAction"]["method"] == "run_command" for row in rows))

    def test_brightness_while_auto_on_warns_and_offers_auto_off(self):
        with mock.patch.object(main, "fetch_status", return_value={"automaticBrightnessEnabled": True}):
            rows = main.BrightSyncPlugin().query("40")

        self.assertEqual(rows[0]["JsonRPCAction"]["parameters"][0], {"CommandType": 0, "BrightnessValue": 40})
        self.assertIn("refused", rows[0]["SubTitle"])
        self.assertEqual(rows[1]["JsonRPCAction"]["parameters"][0], {"CommandType": 6, "Enabled": False})

    def test_brightness_while_auto_off_has_no_warning(self):
        with mock.patch.object(main, "fetch_status", return_value={"automaticBrightnessEnabled": False}):
            rows = main.BrightSyncPlugin().query("40")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["SubTitle"], "Press Enter to run")

    def test_run_command_reports_not_running_via_show_msg(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            main.BrightSyncPlugin().run_command({"CommandType": 0, "BrightnessValue": 40}, "Set brightness to 40%")

        message = json.loads(buffer.getvalue())
        self.assertEqual(message["method"], "Flow.Launcher.ShowMsg")
        self.assertEqual(message["parameters"][0], "BrightSync")
        self.assertIn("not running", message["parameters"][1])

    def test_status_details_format(self):
        status = {
            "masterBrightness": 40,
            "automaticBrightnessEnabled": False,
            "eyeProtectionActive": True,
            "eyeProtectionRemainingSeconds": 3725,
            "brightnessBoostActive": False,
            "monitorCount": 2,
            "controllableMonitorCount": 1,
        }

        self.assertEqual(
            main.format_status_details(status),
            "Auto off | Eye protection on (1h 2m left) | Boost off | 1/2 monitors controllable",
        )

    def test_bad_json_payload_returns_error_code(self):
        self.assertEqual(main.main(["main.py", "{not json"]), 2)

    def test_unknown_method_is_rejected(self):
        self.assertEqual(main.main(["main.py", json.dumps({"method": "__init__", "parameters": []})]), 1)


if __name__ == "__main__":
    unittest.main()

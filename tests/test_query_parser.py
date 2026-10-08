import os
import sys
import unittest

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PLUGIN_DIR)

from brightsync_client import CommandType  # noqa: E402
from query_parser import DEFAULT_STEP, ParseError, parse  # noqa: E402


class ParseTests(unittest.TestCase):
    def test_empty_and_status_request_status(self):
        for text in ("", "   ", "status", "STATUS"):
            with self.subTest(text=text):
                self.assertEqual(parse(text).command_type, CommandType.STATUS)

    def test_bare_number_sets_brightness(self):
        command = parse("40")
        self.assertEqual(command.command_type, CommandType.BRIGHTNESS_SET)
        self.assertEqual(command.to_request(), {"CommandType": 0, "BrightnessValue": 40})

    def test_brightness_bounds(self):
        self.assertEqual(parse("0").brightness, 0)
        self.assertEqual(parse("100").brightness, 100)
        with self.assertRaises(ParseError):
            parse("101")

    def test_up_and_down_default_step(self):
        up = parse("up")
        self.assertEqual(up.command_type, CommandType.BRIGHTNESS_UP)
        self.assertEqual(up.to_request(), {"CommandType": 1, "StepValue": DEFAULT_STEP})

        down = parse("down 5")
        self.assertEqual(down.command_type, CommandType.BRIGHTNESS_DOWN)
        self.assertEqual(down.to_request(), {"CommandType": 2, "StepValue": 5})

    def test_step_bounds(self):
        with self.assertRaises(ParseError):
            parse("up 0")
        with self.assertRaises(ParseError):
            parse("down 101")

    def test_auto_on_off_send_enabled_like_cli(self):
        self.assertEqual(parse("auto on").to_request(), {"CommandType": 5, "Enabled": True})
        self.assertEqual(parse("auto off").to_request(), {"CommandType": 6, "Enabled": False})
        with self.assertRaises(ParseError):
            parse("auto")

    def test_eye_protection_optional_hours(self):
        self.assertEqual(parse("eye on").to_request(), {"CommandType": 7, "Enabled": True})
        self.assertEqual(parse("eye on 2").to_request(), {"CommandType": 7, "Enabled": True, "DurationHours": 2})
        self.assertEqual(parse("eye off").to_request(), {"CommandType": 8, "Enabled": False})

    def test_boost_optional_hours(self):
        self.assertEqual(parse("boost on 24").to_request(), {"CommandType": 9, "Enabled": True, "DurationHours": 24})
        self.assertEqual(parse("boost off").to_request(), {"CommandType": 10, "Enabled": False})

    def test_hours_must_be_one_to_twenty_four(self):
        for text in ("eye on 0", "eye on 25", "boost on 0", "boost on x"):
            with self.subTest(text=text), self.assertRaises(ParseError):
                parse(text)

    def test_off_takes_no_hours(self):
        with self.assertRaises(ParseError):
            parse("eye off 2")

    def test_refresh_and_settings(self):
        self.assertEqual(parse("refresh").command_type, CommandType.MONITORS_REFRESH)
        self.assertEqual(parse("settings").command_type, CommandType.SETTINGS_SHOW)

    def test_unknown_command_is_rejected(self):
        with self.assertRaises(ParseError):
            parse("exit")
        with self.assertRaises(ParseError):
            parse("-5")


if __name__ == "__main__":
    unittest.main()

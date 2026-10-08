"""Parse the text typed after the `bs` action keyword into a BrightSync command."""

from __future__ import annotations

from dataclasses import dataclass

from brightsync_client import CommandType, build_request

DEFAULT_STEP = 10
MIN_HOURS = 1
MAX_HOURS = 24
TOGGLE_WORDS = ("auto", "eye", "boost")

USAGE = (
    "<0-100> | up [step] | down [step] | auto on|off | "
    "eye on|off [hours] | boost on|off [hours] | refresh | settings | status"
)


class ParseError(ValueError):
    """The query text is not a valid BrightSync command."""


@dataclass(frozen=True)
class Command:
    title: str
    command_type: int
    brightness: int | None = None
    step: int | None = None
    enabled: bool | None = None
    hours: int | None = None

    def to_request(self):
        return build_request(
            self.command_type,
            brightness=self.brightness,
            step=self.step,
            enabled=self.enabled,
            hours=self.hours,
        )


def parse(text):
    tokens = text.strip().lower().split()
    if not tokens or tokens == ["status"]:
        return Command("Show status", CommandType.STATUS)

    head, rest = tokens[0], tokens[1:]

    if head.isdigit():
        if rest:
            raise ParseError(f"Unexpected text after brightness value: {' '.join(rest)}")
        value = _int_in_range(head, 0, 100, "Brightness must be 0 to 100.")
        return Command(f"Set brightness to {value}%", CommandType.BRIGHTNESS_SET, brightness=value)

    if head in ("up", "down"):
        if len(rest) > 1:
            raise ParseError(f"Usage: {head} [step]")
        step = _int_in_range(rest[0], 1, 100, "Step must be 1 to 100.") if rest else DEFAULT_STEP
        command_type = CommandType.BRIGHTNESS_UP if head == "up" else CommandType.BRIGHTNESS_DOWN
        sign = "+" if head == "up" else "-"
        return Command(f"Brightness {sign}{step}", command_type, step=step)

    if head == "auto":
        enabled = _on_off(rest, "auto on|off")
        command_type = CommandType.AUTO_ON if enabled else CommandType.AUTO_OFF
        return Command(f"Automatic brightness {'on' if enabled else 'off'}", command_type, enabled=enabled)

    if head in ("eye", "boost"):
        return _timed_toggle(head, rest)

    if head == "refresh" and not rest:
        return Command("Refresh monitors", CommandType.MONITORS_REFRESH)

    if head == "settings" and not rest:
        return Command("Open BrightSync settings", CommandType.SETTINGS_SHOW)

    raise ParseError(f"Unknown command '{head}'. Usage: {USAGE}")


def toggle_choices(text):
    """Return the on and off commands for a bare toggle word (`auto`, `eye`, `boost`), else []."""
    tokens = text.strip().lower().split()
    if len(tokens) != 1 or tokens[0] not in TOGGLE_WORDS:
        return []
    return [parse(f"{tokens[0]} on"), parse(f"{tokens[0]} off")]


def _timed_toggle(name, rest):
    enabled = _on_off(rest[:1], f"{name} on|off [hours]")
    if not enabled:
        if len(rest) != 1:
            raise ParseError(f"Usage: {name} off")
        command_type = CommandType.EYE_PROTECTION_OFF if name == "eye" else CommandType.BOOST_OFF
        return Command(f"{_label(name)} off", command_type, enabled=False)

    if len(rest) > 2:
        raise ParseError(f"Usage: {name} on [hours]")
    hours = None
    if len(rest) == 2:
        hours = _int_in_range(rest[1], MIN_HOURS, MAX_HOURS, f"Hours must be {MIN_HOURS} to {MAX_HOURS}.")

    command_type = CommandType.EYE_PROTECTION_ON if name == "eye" else CommandType.BOOST_ON
    suffix = f" for {hours}h" if hours is not None else ""
    return Command(f"{_label(name)} on{suffix}", command_type, enabled=True, hours=hours)


def _label(name):
    return "Eye protection" if name == "eye" else "Brightness boost"


def _on_off(tokens, usage):
    if len(tokens) != 1 or tokens[0] not in ("on", "off"):
        raise ParseError(f"Usage: {usage}")
    return tokens[0] == "on"


def _int_in_range(token, low, high, message):
    if not token.isdigit():
        raise ParseError(message)
    value = int(token)
    if not low <= value <= high:
        raise ParseError(message)
    return value

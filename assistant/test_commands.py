"""Unit tests for the rule-based parser. Run: .venv/bin/python -m pytest assistant

These pin down specific behavior (spellings, rule order, edge cases). The eval
set in evals/commands.jsonl measures overall accuracy instead.
"""

import pytest

from commands import normalize, parse


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Wake me at 7.30 A.M.!", "wake me at 7:30 am"),
        ("set an alarm for 7am", "set an alarm for 7 am"),
        ("twenty-five minutes", "25 minutes"),
        ("seven thirty", "7 30"),
        ("six oh five", "6 05"),
        ("six o'clock", "6 oclock"),
        ("Alarm: 6:45", "alarm 6:45"),
    ],
)
def test_normalize(text, expected):
    assert normalize(text) == expected


@pytest.mark.parametrize(
    "text, time",
    [
        ("Set an alarm for 6:30 a.m.", "06:30"),
        ("wake me up at seven thirty", "07:30"),
        ("wake me at six oh five", "06:05"),
        ("alarm at 6 o'clock", "06:00"),
        ("set an alarm for 9 pm", "21:00"),
        ("set an alarm for 12 am", "00:00"),
        ("set an alarm for 19:00", "19:00"),
        ("set alarm for 7", "07:00"),
    ],
)
def test_alarm_times(text, time):
    assert parse(text) == {"command": "set_alarm", "args": {"time": time}}


@pytest.mark.parametrize(
    "text, minutes",
    [
        ("sleep timer 45 minutes", 45),
        ("turn it off in half an hour", 30),
        ("stop the noise in an hour", 60),
        ("turn it off after an hour and a half", 90),
        ("stop in 1 hour and 15 minutes", 75),
    ],
)
def test_sleep_timer_minutes(text, minutes):
    assert parse(text) == {"command": "sleep_timer", "args": {"minutes": minutes}}


def test_stop_beats_color():
    # Contains "white noise", but it's a stop. The stop rule runs before play.
    assert parse("turn off the white noise") == {"command": "stop", "args": {}}


def test_timer_beats_stop():
    # Contains "turn it off", but the duration makes it a timer.
    assert parse("turn it off in 20 minutes")["command"] == "sleep_timer"


def test_last_color_wins():
    assert parse("switch from white to brown noise")["args"] == {"color": "brown"}


def test_play_without_color_leaves_default_to_device():
    assert parse("play some noise") == {"command": "play", "args": {}}


def test_duration_is_not_alarm_time():
    # "8 hours" mustn't become an 08:00 alarm. Relative alarms aren't supported.
    assert parse("wake me up in 8 hours") is None


@pytest.mark.parametrize(
    "text",
    ["", "thank you", "what time is it", "the brown dog is sleeping", "set an alarm"],
)
def test_not_commands(text):
    assert parse(text) is None

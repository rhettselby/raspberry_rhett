"""Rule-based command parser: transcript text in, structured command out.

A command is a small dict shaped like an LLM tool call (a name plus
arguments), so in milestone 6 an LLM can produce the same thing and the eval
can score both the same way:

    {"command": "play",        "args": {"color": "pink"}}
    {"command": "stop",        "args": {}}
    {"command": "sleep_timer", "args": {"minutes": 30}}
    {"command": "set_alarm",   "args": {"time": "07:30"}}

`play` without a color has empty args; the device picks its default.

parse() returns None when the text isn't a command it understands. On a
device that runs while you sleep, doing nothing beats guessing wrong.
"""

import re

COLORS = ("white", "pink", "brown")


def parse(text: str) -> dict | None:
    t = normalize(text)
    # The first rule that matches wins, so order matters: "turn it off in 20
    # minutes" contains the stop phrase "turn it off", and "turn off the pink
    # noise" contains a color. Commands with arguments go first.
    for rule in (_alarm, _sleep_timer, _stop, _play):
        command = rule(t)
        if command is not None:
            return command
    return None


# --- Normalizing --------------------------------------------------------------

_SMALL_NUMBERS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50}


def normalize(text: str) -> str:
    """Lowercase, drop punctuation and turn number words into digits.

    Whisper writes the same thing several ways ("7:30 a.m.", "7.30am",
    "seven thirty"), so this maps them to one spelling and the rules only
    have to handle that: "Wake me at 7.30 A.M.!" -> "wake me at 7:30 am".
    """
    t = text.lower()
    t = re.sub(r"(?<![a-z])([ap])\.?\s?m\b\.?", r"\1m", t)  # "a.m." -> "am"
    t = re.sub(r"(\d)\s*([ap]m)\b", r"\1 \2", t)  # "7am" -> "7 am"
    t = re.sub(r"\b(\d{1,2})\.(\d{2})\b", r"\1:\2", t)  # "7.30" -> "7:30"
    t = t.replace("'", "").replace("’", "")  # "o'clock" -> "oclock"
    t = re.sub(r"[^a-z0-9:\s]", " ", t)  # "twenty-five" -> "twenty five"
    t = re.sub(r"(?<!\d):|:(?!\d)", " ", t)  # keep ":" only inside times
    return " ".join(_words_to_digits(t.split()))


def _words_to_digits(words: list[str]) -> list[str]:
    """["twenty", "five"] -> ["25"], and ["six", "oh", "five"] -> ["6", "05"]."""
    out = []
    i = 0
    while i < len(words):
        word = words[i]
        next_word = words[i + 1] if i + 1 < len(words) else ""
        next_digit = _SMALL_NUMBERS.get(next_word, 0)
        if word in _TENS:
            n = _TENS[word]
            if 1 <= next_digit <= 9:  # "twenty five", but not "seven thirty"
                n += next_digit
                i += 1
            out.append(str(n))
        elif word == "oh" and out and out[-1].isdigit() and 1 <= next_digit <= 9:
            out.append(f"0{next_digit}")
            i += 1
        elif word in _SMALL_NUMBERS:
            out.append(str(_SMALL_NUMBERS[word]))
        else:
            out.append(word)
        i += 1
    return out


# --- Rules --------------------------------------------------------------------
# Each rule takes normalized text and returns a command or None.


def _alarm(t: str) -> dict | None:
    if not re.search(r"\balarms?\b|\bwake (me|up)\b", t):
        return None
    time = _find_time(t)
    if time is None:
        return None  # "set an alarm" with no time: the parser can't ask back
    return {"command": "set_alarm", "args": {"time": time}}


_STOPPING_WORDS = re.compile(r"\b(timer|sleep|off|stop|shut|silence|quiet|end)\b")


def _sleep_timer(t: str) -> dict | None:
    minutes = _find_minutes(t)
    # A duration alone isn't enough: "play brown noise for 30 minutes" should
    # still play, so a timer also needs a word about stopping.
    if minutes is None or not _STOPPING_WORDS.search(t):
        return None
    return {"command": "sleep_timer", "args": {"minutes": minutes}}


_STOP = re.compile(
    r"\b(stop|pause|silence|enough|mute)\b"
    r"|\bbe quiet\b|\bshut up\b"
    r"|\b(turn|switch|shut)\b.*\boff\b"
)


def _stop(t: str) -> dict | None:
    if _STOP.search(t):
        return {"command": "stop", "args": {}}
    return None


_PLAY_WORDS = re.compile(r"\b(play|start|put on|turn on|switch to|change to|noise)\b")


def _play(t: str) -> dict | None:
    colors = re.findall(r"\b(white|pink|brown)\b", t)
    if colors and _PLAY_WORDS.search(t):
        # The last color named wins: "switch from white to brown" -> brown.
        return {"command": "play", "args": {"color": colors[-1]}}
    if not colors and re.search(r"\b(play|start|put on|turn on)\b.*\b(noise|sound)\b", t):
        return {"command": "play", "args": {}}
    return None


# --- Times and durations --------------------------------------------------------

_TIME = re.compile(r"\b(\d{1,2})(?:[:\s](\d{2}))?(?:\s(am|pm|oclock))?\b")


def _find_time(t: str) -> str | None:
    """Find a clock time and return it as 24-hour "HH:MM".

    Without "am" or "pm" the hour is taken as said, so "7" is 07:00. That's
    the right guess for a wake-up alarm, and "19:00" still works.
    """
    for m in _TIME.finditer(t):
        hour, minute, suffix = int(m[1]), int(m[2] or 0), m[3]
        word_before = t[: m.start()].split()[-1:]
        word_after = t[m.end():].split()[:1]
        if word_after and word_after[0].startswith(("hour", "min")):
            continue  # "in 8 hours" is a duration, not a time
        if m[2] is None and suffix is None and word_before not in (["at"], ["for"]):
            continue  # a bare number only counts after "at" or "for"
        if suffix == "pm" and hour < 12:
            hour += 12
        elif suffix == "am" and hour == 12:
            hour = 0
        if hour <= 23 and minute <= 59:
            return f"{hour:02d}:{minute:02d}"
    return None


_DURATION = re.compile(r"\b(\d+|an?) (hours?|hrs?|minutes?|mins?)\b( and a half)?")


def _find_minutes(t: str) -> int | None:
    """Total minutes: "an hour and a half" -> 90, "1 hour 15 minutes" -> 75."""
    t = t.replace("half an hour", "30 minutes")
    total = 0
    for m in _DURATION.finditer(t):
        amount = 1 if m[1] in ("a", "an") else int(m[1])
        if m[2].startswith("h"):
            total += amount * 60 + (30 if m[3] else 0)
        else:
            total += amount
    return total or None

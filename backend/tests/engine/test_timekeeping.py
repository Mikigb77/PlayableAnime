"""Times of day on the world's clock (W10): reading "19:00" and counting the seconds to it."""

import pytest

from engine.base import HOUR, MINUTE
from engine.samples import cultivation_world, grounded_world
from engine.timekeeping import parse_clock, seconds_until


@pytest.mark.parametrize(
    ("text", "seconds"),
    [
        ("19:00", 19 * HOUR),
        ("7:30", 7 * HOUR + 30 * MINUTE),
        (" 06:05 ", 6 * HOUR + 5 * MINUTE),
        ("6", 6 * HOUR),
        ("18.45", 18 * HOUR + 45 * MINUTE),
        ("24:00", 0),
        ("00:00", 0),
    ],
)
def test_a_time_of_day_on_the_24_hour_clock(text, seconds):
    assert parse_clock(text) == seconds


@pytest.mark.parametrize("text", [None, "", "dusk", "25:00", "12:60", "24:30", "7pm", "-1:00"])
def test_anything_else_is_not_a_time_of_day(text):
    assert parse_clock(text) is None


def test_the_seconds_until_the_clock_next_shows_a_time():
    sect = cultivation_world().bible.calendar  # day count from 07:00
    naples = grounded_world().bible.calendar  # from 21:00

    assert seconds_until(sect, 0, 19 * HOUR) == 12 * HOUR
    assert seconds_until(sect, 0, 6 * HOUR) == 23 * HOUR  # today's dawn has passed
    assert seconds_until(sect, 0, 7 * HOUR) == 0  # the clock shows it now
    assert seconds_until(naples, HOUR, 0) == 2 * HOUR

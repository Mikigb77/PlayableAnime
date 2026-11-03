"""Time in words (W10, W10a): the world's calendar, durations and how long ago."""

import pytest

from engine.base import DAY, HOUR, MINUTE
from engine.labels import (
    ago_label,
    clock_label,
    duration_label,
    in_label,
    part_of_day,
    personal_label,
    scene_time,
    span_label,
)
from engine.samples import cultivation_world, grounded_world
from engine.state import Calendar, CalendarStyle, Month, TimeOfDayStyle


def test_a_day_count_with_parts_of_the_day():
    calendar = cultivation_world().bible.calendar  # day count from 07:00

    assert clock_label(calendar, 0) == "Day 1, morning"
    assert clock_label(calendar, 2 * DAY + 10 * HOUR) == "Day 3, dusk"
    assert clock_label(calendar, 17 * HOUR) == "Day 2, night"


def test_a_day_count_with_a_clock():
    calendar = Calendar(time_of_day=TimeOfDayStyle.CLOCK, start_second_of_day=0)

    assert clock_label(calendar, DAY + 23 * HOUR + 10 * MINUTE) == "Day 2, 23:10"


def test_a_gregorian_date_from_the_epoch():
    calendar = grounded_world().bible.calendar  # 1974-05-14T21:00

    assert clock_label(calendar, 0) == "14 May 1974, 21:00"
    assert clock_label(calendar, 2 * HOUR + 10 * MINUTE) == "14 May 1974, 23:10"
    assert clock_label(calendar, 3 * HOUR + 5 * MINUTE) == "15 May 1974, 00:05"
    assert clock_label(calendar, 400 * DAY) == "18 June 1975, 21:00"


def test_a_calendar_it_cannot_read_falls_back_to_a_day_count():
    no_epoch = Calendar(style=CalendarStyle.GREGORIAN, epoch="not a date")
    no_months = Calendar(style=CalendarStyle.CUSTOM)
    far_future = Calendar(style=CalendarStyle.GREGORIAN, epoch="9999-12-31T00:00")

    assert clock_label(no_epoch, 0) == "Day 1, morning"
    assert clock_label(no_months, 0) == "Day 1, morning"
    assert clock_label(far_future, 2 * DAY) == "Day 3, morning"


def custom() -> Calendar:
    return Calendar(
        style=CalendarStyle.CUSTOM,
        months=[Month(name="the Frost Moon", days=30), Month(name="the Thaw", days=20)],
        start_year=412,
        start_month=2,
        start_day=19,
        era="AE",
        start_second_of_day=17 * HOUR,
    )


def test_a_custom_calendar_rolls_over_months_and_years():
    calendar = custom()

    assert clock_label(calendar, 0) == "19th day of the Thaw, year 412 AE, dusk"
    assert clock_label(calendar, DAY) == "20th day of the Thaw, year 412 AE, dusk"
    assert clock_label(calendar, 2 * DAY) == "1st day of the Frost Moon, year 413 AE, dusk"
    assert clock_label(calendar, 23 * DAY) == "22nd day of the Frost Moon, year 413 AE, dusk"
    assert clock_label(calendar, 52 * DAY) == "1st day of the Frost Moon, year 414 AE, dusk"


@pytest.mark.parametrize(
    ("n", "words"), [(1, "1st"), (2, "2nd"), (3, "3rd"), (11, "11th"), (12, "12th"), (13, "13th")]
)
def test_ordinals(n, words):
    calendar = Calendar(
        style=CalendarStyle.CUSTOM, months=[Month(name="Rain", days=40)], start_second_of_day=0
    )

    assert clock_label(calendar, (n - 1) * DAY).startswith(f"{words} day of Rain")


@pytest.mark.parametrize(
    ("hour", "part"),
    [
        (0, "night"),
        (4, "night"),
        (5, "dawn"),
        (7, "morning"),
        (12, "midday"),
        (15, "afternoon"),
        (18, "dusk"),
        (20, "evening"),
        (23, "night"),
    ],
)
def test_parts_of_the_day(hour, part):
    assert part_of_day(hour * HOUR) == part


@pytest.mark.parametrize(
    ("seconds", "label"),
    [
        (0, "0 s"),
        (40, "40 s"),
        (90, "1 min 30 s"),
        (HOUR, "1 h"),
        (HOUR + 20 * MINUTE, "1 h 20 min"),
        (8 * HOUR, "8 h"),
        (2 * DAY + 5 * MINUTE, "2 d"),
        (2 * DAY + 4 * HOUR, "2 d 4 h"),
        (400 * DAY, "1 y 35 d"),
        (-5, "0 s"),
    ],
)
def test_spans_use_at_most_two_units(seconds, label):
    assert span_label(seconds) == label


def test_durations_and_both_clocks():
    assert duration_label(8 * HOUR) == "+8 h"
    assert personal_label(0, 40) == "World: +0 s. You: +40 s."
    assert personal_label(60, 60) is None


@pytest.mark.parametrize(
    ("seconds", "ago"),
    [
        (30, "moments ago"),
        (MINUTE, "a minute ago"),
        (5 * MINUTE, "5 minutes ago"),
        (HOUR, "an hour ago"),
        (2 * DAY, "2 days ago"),
        (3 * 7 * DAY, "3 weeks ago"),
        (90 * DAY, "3 months ago"),
        (800 * DAY, "2 years ago"),
    ],
)
def test_how_long_ago(seconds, ago):
    assert ago_label(seconds) == ago


def test_how_long_until():
    assert in_label(10) == "in moments"
    assert in_label(3 * HOUR) == "in 3 hours"


def test_the_scene_time_bar():
    calendar = grounded_world().bible.calendar

    bar = scene_time(calendar, 0, 2 * HOUR + 10 * MINUTE, 2 * HOUR + 10 * MINUTE)
    stopped = scene_time(calendar, 0, 0, 40)

    assert bar.label == "14 May 1974, 23:10"
    assert (bar.duration_label, bar.personal_label) == ("+2 h 10 min", None)
    assert stopped.personal_label == "World: +0 s. You: +40 s."

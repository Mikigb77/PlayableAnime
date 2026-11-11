"""Time in words (W10, W10a): the world's calendar, durations and how long ago."""

import pytest

from engine.base import DAY, HOUR, MINUTE
from engine.context import Language
from engine.labels import (
    Moment,
    ago_label,
    clock_label,
    clock_time,
    duration_label,
    in_label,
    moment,
    of_name,
    only_the_clock,
    part_of_day,
    passage_label,
    personal_label,
    scene_time,
    second_of_day,
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


def test_the_clock_reads_the_time_of_day_the_label_shows():
    sect = cultivation_world().bible.calendar  # day count from 07:00
    naples = grounded_world().bible.calendar  # from 21:00 on 14 May 1974
    far_future = Calendar(style=CalendarStyle.GREGORIAN, epoch="9999-12-31T00:00")

    assert second_of_day(sect, 2 * DAY + 10 * HOUR) == 17 * HOUR
    assert second_of_day(naples, 3 * HOUR + 5 * MINUTE) == 5 * MINUTE
    # Past what a date can hold, the label falls back to a day count, and so does the clock.
    assert second_of_day(far_future, 2 * DAY) == 8 * HOUR
    assert second_of_day(custom(), 9 * HOUR) == 2 * HOUR


def test_the_models_read_the_moment_on_a_24_hour_clock():
    sect = cultivation_world().bible.calendar

    assert clock_time(7 * HOUR + 5 * MINUTE) == "07:05"
    assert clock_time(DAY + 30 * MINUTE) == "00:30"
    # A calendar that names parts of the day still gives the models the exact time (W10).
    assert moment(sect, 12 * HOUR + 15 * MINUTE) == Moment(
        date="Day 1, evening", clock="19:15", part_of_day="evening"
    )


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


# --- the heading over a scene that hours or days passed in (W10) ---------------------------------


def heading(hours: float, start_hour: int = 7, language: Language = Language.EN) -> str | None:
    """The heading over a scene of `hours` that began at `start_hour` o'clock."""
    calendar = Calendar(time_of_day=TimeOfDayStyle.CLOCK, start_second_of_day=0)
    start = start_hour * HOUR
    return passage_label(calendar, start, start + int(hours * HOUR), language)


def test_a_short_scene_has_no_heading():
    assert heading(0) is None
    assert heading(1) is None
    assert heading(1.99) is None
    assert heading(-3) is None  # a clock that went back marks nothing (W10a)


@pytest.mark.parametrize(
    ("hours", "told"),
    [
        (2, "Two hours later"),
        (2.4, "Two hours later"),
        (2.5, "Three hours later"),
        (6, "Six hours later"),
        (12, "Twelve hours later"),
        (20, "Twenty hours later"),
        (21, "21 hours later"),  # from 07:00 to 04:00: no morning came
    ],
)
def test_hours_inside_one_day_are_told_in_hours(hours, told):
    assert heading(hours) == told


def test_days_are_counted_by_the_mornings_that_came():
    # A night's sleep ends on the next day, though only eight hours passed.
    assert heading(8, start_hour=22) == "The next day"
    # A watch past midnight is the same night.
    assert heading(5, start_hour=22) == "Five hours later"
    # A short stretch is told in hours even across a dawn.
    assert heading(5, start_hour=3) == "Five hours later"
    assert heading(6, start_hour=3) == "The next day"
    assert heading(24) == heading(30) == "The next day"
    assert heading(45) == "The next day"
    assert heading(46) == heading(48) == "Two days later"


@pytest.mark.parametrize(
    ("days", "told"),
    [
        (2, "Two days later"),
        (3, "Three days later"),
        (6, "Six days later"),
        (7, "A week later"),
        (8, "Eight days later"),
        (13, "Thirteen days later"),
        (14, "Two weeks later"),
        (17, "Two weeks later"),
        (18, "Three weeks later"),  # to the nearest week
        (27, "Four weeks later"),
        (28, "A month later"),
        (31, "A month later"),
        (32, "Five weeks later"),
        (59, "Eight weeks later"),
        (60, "Two months later"),
        (74, "Two months later"),
        (75, "Three months later"),  # to the nearest month
        (200, "Seven months later"),
        (344, "Eleven months later"),
        (345, "A year later"),
        (365, "A year later"),
        (374, "A year later"),
        (375, "Thirteen months later"),
        (547, "Eighteen months later"),
        (548, "Two years later"),  # to the nearest year
        (800, "Two years later"),
        (913, "Three years later"),
        (20 * 365, "Twenty years later"),
        (30 * 365, "30 years later"),
        (1000 * 365, "1000 years later"),
    ],
)
def test_longer_stretches_are_told_in_days_weeks_months_and_years(days, told):
    assert heading(24 * days) == told


def test_the_heading_in_spanish_and_catalan():
    spans = [2, 3, 24, 72, 7 * 24, 14 * 24, 30 * 24, 60 * 24, 365 * 24]
    es = [heading(h, language=Language.ES) for h in spans]
    ca = [heading(h, language=Language.CA) for h in spans]

    assert es == [
        "Dos horas después",
        "Tres horas después",
        "Al día siguiente",
        "Tres días después",
        "Una semana después",
        "Dos semanas después",
        "Un mes después",
        "Dos meses después",
        "Un año después",
    ]
    assert ca == [
        "Dues hores després",  # two takes the gender of what it counts
        "Tres hores després",
        "L'endemà",
        "Tres dies després",
        "Una setmana després",
        "Dues setmanes després",
        "Un mes després",
        "Dos mesos després",
        "Un any després",
    ]
    assert heading(21, language=Language.ES) == "21 horas después"
    assert heading(1, language=Language.CA) is None


def test_the_scene_time_bar_carries_the_heading():
    calendar = grounded_world().bible.calendar  # 21:00

    assert scene_time(calendar, 0, 40 * MINUTE, 40 * MINUTE).passage_label is None
    assert scene_time(calendar, 0, 3 * DAY, 3 * DAY).passage_label == "Three days later"
    assert scene_time(calendar, 0, 9 * HOUR, 9 * HOUR, Language.ES).passage_label == (
        "Al día siguiente"
    )


ES = Language.ES


def test_the_world_s_dates_in_spanish():
    # S10: a Spanish story's clock, whatever its calendar.
    sect = cultivation_world().bible.calendar  # day count from 07:00
    naples = grounded_world().bible.calendar  # 1974-05-14T21:00
    frost = Calendar(
        style=CalendarStyle.CUSTOM,
        months=[Month(name="Luna de Escarcha", days=30)],
        start_year=412,
        start_second_of_day=17 * HOUR,
    )

    assert clock_label(sect, 2 * DAY + 10 * HOUR, ES) == "Día 3, atardecer"
    assert clock_label(sect, 17 * HOUR, ES) == "Día 2, noche"
    assert clock_label(naples, 2 * HOUR + 10 * MINUTE, ES) == "14 de mayo de 1974, 23:10"
    assert clock_label(frost, 2 * DAY, ES) == "Día 3 de Luna de Escarcha, año 412, atardecer"
    # What the models read stays English: they write in the story's language anyway.
    assert moment(sect, 2 * DAY + 10 * HOUR).part_of_day == "dusk"


def test_spans_and_rough_times_in_spanish():
    assert span_label(400 * DAY, ES) == "1 a 35 d"
    assert duration_label(2 * HOUR + 10 * MINUTE, ES) == "+2 h 10 min"
    assert personal_label(0, 40, ES) == "Mundo: +0 s. Tú: +40 s."
    assert ago_label(30, ES) == "hace un momento"
    assert ago_label(HOUR, ES) == "hace una hora"
    assert ago_label(2 * DAY, ES) == "hace 2 días"
    assert ago_label(90 * DAY, ES) == "hace 3 meses"
    assert in_label(10, ES) == "en un momento"
    assert in_label(3 * HOUR, ES) == "en 3 horas"
    assert in_label(800 * DAY, ES) == "en 2 años"


def test_the_scene_time_bar_in_spanish():
    bar = scene_time(grounded_world().bible.calendar, 0, 0, 40, ES)

    assert (bar.label, bar.duration_label) == ("14 de mayo de 1974, 21:00", "+0 s")
    assert bar.personal_label == "Mundo: +0 s. Tú: +40 s."


CA = Language.CA


def test_the_world_s_dates_in_catalan():
    # S10: a Catalan story's clock, with "d'" before a vowel sound.
    sect = cultivation_world().bible.calendar
    naples = grounded_world().bible.calendar
    winter = Calendar(
        style=CalendarStyle.CUSTOM,
        months=[Month(name="Hivern", days=30)],
        start_year=412,
        start_second_of_day=17 * HOUR,
    )
    frost = winter.model_copy(update={"months": [Month(name="Lluna de Gebre", days=30)]})
    april = naples.model_copy(update={"epoch": "1974-04-14T21:00:00"})

    assert clock_label(sect, 2 * DAY + 10 * HOUR, CA) == "Dia 3, capvespre"
    assert clock_label(sect, 17 * HOUR, CA) == "Dia 2, nit"
    assert clock_label(naples, 2 * HOUR + 10 * MINUTE, CA) == "14 de maig de 1974, 23:10"
    assert clock_label(april, 2 * HOUR + 10 * MINUTE, CA) == "14 d'abril de 1974, 23:10"
    assert clock_label(frost, 2 * DAY, CA) == "Dia 3 de Lluna de Gebre, any 412, capvespre"
    assert clock_label(winter, 2 * DAY, CA) == "Dia 3 d'Hivern, any 412, capvespre"


def test_a_name_after_of_takes_its_article_in():
    assert of_name("abril", ES) == "de abril"
    assert of_name("la maestra Wen", ES) == "de la maestra Wen"
    assert of_name("el viejo herrero", ES) == "del viejo herrero"
    assert of_name("El Cid", ES) == "de El Cid"  # part of the name
    assert of_name("el", ES) == "de el"  # a word alone is a name, not an article
    assert of_name("el vell ferrer", CA) == "del vell ferrer"
    assert of_name("els germans Roca", CA) == "dels germans Roca"
    assert of_name("Elna", CA) == "d'Elna"
    assert of_name("els", CA) == "d'els"


def test_spans_and_rough_times_in_catalan():
    assert span_label(400 * DAY, CA) == "1 a 35 d"
    assert personal_label(0, 40, CA) == "Món: +0 s. Tu: +40 s."
    assert ago_label(30, CA) == "fa un moment"
    assert ago_label(HOUR, CA) == "fa una hora"
    assert ago_label(2 * DAY, CA) == "fa 2 dies"
    assert ago_label(90 * DAY, CA) == "fa 3 mesos"
    assert in_label(10, CA) == "d'aquí a un moment"
    assert in_label(3 * HOUR, CA) == "d'aquí a 3 hores"
    assert in_label(800 * DAY, CA) == "d'aquí a 2 anys"


@pytest.mark.parametrize(
    "text",
    [
        "Day 1, morning, 07:00",
        "day 1, dusk",
        "07:00",
        "Morning.",
        "Día 3, atardecer",
        "Dia 2, capvespre, 19:30",
        "Day 1 at 07:00",
    ],
)
def test_a_text_that_gives_only_the_date_or_the_hour_is_only_the_clock(text):
    """R3: so a scene end that names a time where it should say what is happening is caught."""
    assert only_the_clock(Calendar(), 7 * HOUR, text)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "Elder Mo lowers his sword and waits for your answer.",
        "Day 1, morning: Lin stands at the well.",
        "At dawn the gate opens.",
    ],
)
def test_a_text_that_says_what_happens_is_not_only_the_clock(text):
    assert not only_the_clock(Calendar(), 7 * HOUR, text)


def test_the_worlds_own_date_is_only_the_clock_too():
    calendar = custom()
    for language in Language:
        label = clock_label(calendar, 2 * DAY, language)
        assert only_the_clock(calendar, 2 * DAY, label), label
    assert not only_the_clock(calendar, 2 * DAY, "The frost thickens on the well.")

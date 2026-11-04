"""Time in words (W10, W10a, G16): dates in the world's own calendar, durations and how long ago.

The server sends these ready-made, so the app never formats an in-world date itself (API.md).
Labels are English for now.
"""

from datetime import datetime, timedelta

from engine.base import DAY, HOUR, MINUTE, EngineModel
from engine.state.bible import Calendar, CalendarStyle, TimeOfDayStyle

LABEL_YEAR = 365 * DAY
LABEL_MONTH = 30 * DAY
LABEL_WEEK = 7 * DAY

# Parts of the day by the hour they start, for calendars that name them instead of a clock.
DAY_PARTS: tuple[tuple[int, str], ...] = (
    (0, "night"),
    (5, "dawn"),
    (7, "morning"),
    (11, "midday"),
    (14, "afternoon"),
    (17, "dusk"),
    (19, "evening"),
    (22, "night"),
)

MONTH_NAMES = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def part_of_day(second_of_day: int) -> str:
    hour = (second_of_day % DAY) // HOUR
    name = DAY_PARTS[0][1]
    for start, part in DAY_PARTS:
        if hour >= start:
            name = part
    return name


def _time_of_day(calendar: Calendar, second_of_day: int) -> str:
    if calendar.time_of_day is TimeOfDayStyle.CLOCK:
        return clock_time(second_of_day)
    return part_of_day(second_of_day)


def _ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _day_count(calendar: Calendar, world_s: int) -> str:
    since_midnight = calendar.start_second_of_day + world_s
    day = since_midnight // DAY + 1
    return f"Day {day}, {_time_of_day(calendar, since_midnight)}"


def _gregorian(calendar: Calendar, world_s: int) -> str | None:
    try:
        start = datetime.fromisoformat(calendar.epoch or "")
        moment = start + timedelta(seconds=world_s)
    except (ValueError, OverflowError):
        return None
    second_of_day = moment.hour * HOUR + moment.minute * MINUTE + moment.second
    date = f"{moment.day} {MONTH_NAMES[moment.month - 1]} {moment.year}"
    return f"{date}, {_time_of_day(calendar, second_of_day)}"


def _custom(calendar: Calendar, world_s: int) -> str | None:
    months = calendar.months
    if not months:
        return None
    year_days = sum(m.days for m in months)
    first = min(calendar.start_month, len(months)) - 1
    start_day = min(calendar.start_day, months[first].days) - 1
    since_midnight = calendar.start_second_of_day + world_s
    day_of_year = sum(m.days for m in months[:first]) + start_day + since_midnight // DAY
    year = calendar.start_year + day_of_year // year_days
    day_of_year %= year_days
    for month in months:
        if day_of_year < month.days:
            break
        day_of_year -= month.days
    era = f" {calendar.era}" if calendar.era else ""
    when = _time_of_day(calendar, since_midnight)
    return f"{_ordinal(day_of_year + 1)} day of {month.name}, year {year}{era}, {when}"


def second_of_day(calendar: Calendar, world_s: int) -> int:
    """W10. Seconds since midnight on the world's clock at `world_s`, as `clock_label` shows
    it: from a Gregorian epoch's own time of day, or from the opening hour otherwise."""
    if calendar.style is CalendarStyle.GREGORIAN:
        try:
            at = datetime.fromisoformat(calendar.epoch or "") + timedelta(seconds=world_s)
        except (ValueError, OverflowError):
            pass
        else:
            return at.hour * HOUR + at.minute * MINUTE + at.second
    return (calendar.start_second_of_day + world_s) % DAY


def clock_time(seconds_of_day: int) -> str:
    """A time of day on the 24-hour clock: "07:05"."""
    seconds_of_day %= DAY
    return f"{seconds_of_day // HOUR:02d}:{seconds_of_day % HOUR // MINUTE:02d}"


class Moment(EngineModel):
    """A moment on the world's clock, as the turn's models read it (W10): the date as the player
    sees it, the 24-hour time whatever the calendar shows, and the part of the day."""

    date: str
    clock: str
    part_of_day: str


def moment(calendar: Calendar, world_s: int) -> Moment:
    """Where the world's clock stands at `world_s`."""
    of_day = second_of_day(calendar, world_s)
    return Moment(
        date=clock_label(calendar, world_s),
        clock=clock_time(of_day),
        part_of_day=part_of_day(of_day),
    )


def clock_label(calendar: Calendar, world_s: int) -> str:
    """The date and time of day in the world's calendar: "Day 3, dusk", "14 May 1974, 23:10" or
    "3rd day of the Frost Moon, year 412, dusk". A calendar it can't read falls back to a day
    count, so a label is never missing."""
    if calendar.style is CalendarStyle.GREGORIAN:
        label = _gregorian(calendar, world_s)
    elif calendar.style is CalendarStyle.CUSTOM:
        label = _custom(calendar, world_s)
    else:
        label = None
    return label or _day_count(calendar, world_s)


_UNITS = (
    (LABEL_YEAR, "y"),
    (DAY, "d"),
    (HOUR, "h"),
    (MINUTE, "min"),
    (1, "s"),
)


def span_label(seconds: int) -> str:
    """A span in at most two units: "40 s", "3 min", "1 h 20 min", "2 d 4 h", "3 y 12 d"."""
    seconds = max(0, int(seconds))
    if seconds == 0:
        return "0 s"
    parts: list[str] = []
    for size, unit in _UNITS:
        if seconds >= size:
            parts.append(f"{seconds // size} {unit}")
            seconds %= size
        elif parts:
            # A gap in the units ends the label: "2 d" rather than "2 d 0 h 5 min".
            break
        if len(parts) == 2:
            break
    return " ".join(parts)


def duration_label(seconds: int) -> str:
    """How long an action took, for the scene's time bar: "+8 h" (W10)."""
    return f"+{span_label(seconds)}"


def personal_label(world_s: int, personal_s: int) -> str | None:
    """Both clocks when a time power split them: "World: +0 s. You: +40 s." (W10a). None when
    the user lived the same time as the world."""
    if world_s == personal_s:
        return None
    return f"World: {duration_label(world_s)}. You: {duration_label(personal_s)}."


def _amount(count: int, unit: str) -> str:
    if count == 1:
        return f"an {unit}" if unit == "hour" else f"a {unit}"
    return f"{count} {unit}s"


def _rough(seconds: int) -> str:
    if seconds < HOUR:
        return _amount(max(1, seconds // MINUTE), "minute")
    if seconds < DAY:
        return _amount(seconds // HOUR, "hour")
    if seconds < 2 * LABEL_WEEK:
        return _amount(seconds // DAY, "day")
    if seconds < 2 * LABEL_MONTH:
        return _amount(seconds // LABEL_WEEK, "week")
    if seconds < LABEL_YEAR:
        return _amount(seconds // LABEL_MONTH, "month")
    return _amount(seconds // LABEL_YEAR, "year")


def ago_label(seconds: int) -> str:
    """How long ago, in rough words: "moments ago", "2 days ago" (W10, `/status`)."""
    if seconds < MINUTE:
        return "moments ago"
    return f"{_rough(seconds)} ago"


def in_label(seconds: int) -> str:
    """How long until, in rough words: "in moments", "in 3 hours"."""
    if seconds < MINUTE:
        return "in moments"
    return f"in {_rough(seconds)}"


class SceneTime(EngineModel):
    """The scene's time bar, in the shape of API.md's `Scene.time`."""

    world_start_s: int
    world_end_s: int
    label: str
    duration_label: str
    personal_label: str | None = None


def scene_time(calendar: Calendar, start_s: int, end_s: int, personal_s: int) -> SceneTime:
    """The time bar for a scene that ran from `start_s` to `end_s` world seconds, in which the
    player character lived `personal_s` seconds."""
    return SceneTime(
        world_start_s=start_s,
        world_end_s=end_s,
        label=clock_label(calendar, end_s),
        duration_label=duration_label(end_s - start_s),
        personal_label=personal_label(end_s - start_s, personal_s),
    )

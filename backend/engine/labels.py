"""Time in words (W10, W10a, G16): dates in the world's own calendar, durations and how long ago.

The server sends these ready-made, so the app never formats an in-world date itself (API.md),
in the story's language (S10): English by default, or Spanish. What the turn's models read stays
English: they write in the story's language whatever their brief is in.
"""

from datetime import datetime, timedelta

from engine.base import DAY, HOUR, MINUTE, EngineModel
from engine.context import Language
from engine.state.bible import Calendar, CalendarStyle, TimeOfDayStyle

EN = Language.EN
ES = Language.ES

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

# S10: the parts of the day and the months as a Spanish story shows them.
_PART_NAMES_ES = {
    "night": "noche",
    "dawn": "amanecer",
    "morning": "mañana",
    "midday": "mediodía",
    "afternoon": "tarde",
    "dusk": "atardecer",
    "evening": "anochecer",
}
_MONTH_NAMES_ES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


def part_of_day(second_of_day: int) -> str:
    """The part of the day by its English name, as `DAY_PARTS` has it: "dusk"."""
    hour = (second_of_day % DAY) // HOUR
    name = DAY_PARTS[0][1]
    for start, part in DAY_PARTS:
        if hour >= start:
            name = part
    return name


def _time_of_day(calendar: Calendar, second_of_day: int, language: Language) -> str:
    if calendar.time_of_day is TimeOfDayStyle.CLOCK:
        return clock_time(second_of_day)
    part = part_of_day(second_of_day)
    return _PART_NAMES_ES[part] if language is ES else part


def _ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _day_count(calendar: Calendar, world_s: int, language: Language) -> str:
    since_midnight = calendar.start_second_of_day + world_s
    day = since_midnight // DAY + 1
    word = "Día" if language is ES else "Day"
    return f"{word} {day}, {_time_of_day(calendar, since_midnight, language)}"


def _gregorian(calendar: Calendar, world_s: int, language: Language) -> str | None:
    try:
        start = datetime.fromisoformat(calendar.epoch or "")
        moment = start + timedelta(seconds=world_s)
    except (ValueError, OverflowError):
        return None
    second_of_day = moment.hour * HOUR + moment.minute * MINUTE + moment.second
    if language is ES:
        date = f"{moment.day} de {_MONTH_NAMES_ES[moment.month - 1]} de {moment.year}"
    else:
        date = f"{moment.day} {MONTH_NAMES[moment.month - 1]} {moment.year}"
    return f"{date}, {_time_of_day(calendar, second_of_day, language)}"


def _custom(calendar: Calendar, world_s: int, language: Language) -> str | None:
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
    when = _time_of_day(calendar, since_midnight, language)
    if language is ES:
        return f"Día {day_of_year + 1} de {month.name}, año {year}{era}, {when}"
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


def clock_label(calendar: Calendar, world_s: int, language: Language = EN) -> str:
    """The date and time of day in the world's calendar: "Day 3, dusk", "14 May 1974, 23:10" or
    "3rd day of the Frost Moon, year 412, dusk"; in Spanish "Día 3, atardecer", "14 de mayo de
    1974, 23:10" or "Día 3 de Luna de Escarcha, año 412, atardecer" (S10). A calendar it can't
    read falls back to a day count, so a label is never missing."""
    if calendar.style is CalendarStyle.GREGORIAN:
        label = _gregorian(calendar, world_s, language)
    elif calendar.style is CalendarStyle.CUSTOM:
        label = _custom(calendar, world_s, language)
    else:
        label = None
    return label or _day_count(calendar, world_s, language)


_UNITS = (
    (LABEL_YEAR, "y"),
    (DAY, "d"),
    (HOUR, "h"),
    (MINUTE, "min"),
    (1, "s"),
)
# S10: only the year has its own letter in Spanish ("a" for "año").
_UNITS_ES = {"y": "a"}


def span_label(seconds: int, language: Language = EN) -> str:
    """A span in at most two units: "40 s", "3 min", "1 h 20 min", "2 d 4 h", "3 y 12 d" (in
    Spanish "3 a 12 d")."""
    seconds = max(0, int(seconds))
    if seconds == 0:
        return "0 s"
    parts: list[str] = []
    for size, unit in _UNITS:
        if language is ES:
            unit = _UNITS_ES.get(unit, unit)
        if seconds >= size:
            parts.append(f"{seconds // size} {unit}")
            seconds %= size
        elif parts:
            # A gap in the units ends the label: "2 d" rather than "2 d 0 h 5 min".
            break
        if len(parts) == 2:
            break
    return " ".join(parts)


def duration_label(seconds: int, language: Language = EN) -> str:
    """How long an action took, for the scene's time bar: "+8 h" (W10)."""
    return f"+{span_label(seconds, language)}"


def personal_label(world_s: int, personal_s: int, language: Language = EN) -> str | None:
    """Both clocks when a time power split them: "World: +0 s. You: +40 s." (W10a), in Spanish
    "Mundo: +0 s. Tú: +40 s.". None when the user lived the same time as the world."""
    if world_s == personal_s:
        return None
    world, you = ("Mundo", "Tú") if language is ES else ("World", "You")
    return (
        f"{world}: {duration_label(world_s, language)}. "
        f"{you}: {duration_label(personal_s, language)}."
    )


# S10: each unit's Spanish as one and as many, the one with its article ("un día", "una hora").
_AMOUNTS_ES = {
    "minute": ("un minuto", "minutos"),
    "hour": ("una hora", "horas"),
    "day": ("un día", "días"),
    "week": ("una semana", "semanas"),
    "month": ("un mes", "meses"),
    "year": ("un año", "años"),
}


def _amount(count: int, unit: str, language: Language) -> str:
    if language is ES:
        one, many = _AMOUNTS_ES[unit]
        return one if count == 1 else f"{count} {many}"
    if count == 1:
        return f"an {unit}" if unit == "hour" else f"a {unit}"
    return f"{count} {unit}s"


def _rough(seconds: int, language: Language) -> str:
    if seconds < HOUR:
        return _amount(max(1, seconds // MINUTE), "minute", language)
    if seconds < DAY:
        return _amount(seconds // HOUR, "hour", language)
    if seconds < 2 * LABEL_WEEK:
        return _amount(seconds // DAY, "day", language)
    if seconds < 2 * LABEL_MONTH:
        return _amount(seconds // LABEL_WEEK, "week", language)
    if seconds < LABEL_YEAR:
        return _amount(seconds // LABEL_MONTH, "month", language)
    return _amount(seconds // LABEL_YEAR, "year", language)


def ago_label(seconds: int, language: Language = EN) -> str:
    """How long ago, in rough words: "moments ago", "2 days ago" (W10, `/status`); in Spanish
    "hace un momento", "hace 2 días"."""
    if language is ES:
        return "hace un momento" if seconds < MINUTE else f"hace {_rough(seconds, language)}"
    if seconds < MINUTE:
        return "moments ago"
    return f"{_rough(seconds, language)} ago"


def in_label(seconds: int, language: Language = EN) -> str:
    """How long until, in rough words: "in moments", "in 3 hours"; in Spanish "en un momento",
    "en 3 horas"."""
    if seconds < MINUTE:
        return "en un momento" if language is ES else "in moments"
    return f"{'en' if language is ES else 'in'} {_rough(seconds, language)}"


class SceneTime(EngineModel):
    """The scene's time bar, in the shape of API.md's `Scene.time`."""

    world_start_s: int
    world_end_s: int
    label: str
    duration_label: str
    personal_label: str | None = None


def scene_time(
    calendar: Calendar, start_s: int, end_s: int, personal_s: int, language: Language = EN
) -> SceneTime:
    """The time bar for a scene that ran from `start_s` to `end_s` world seconds, in which the
    player character lived `personal_s` seconds, in the story's language (S10)."""
    return SceneTime(
        world_start_s=start_s,
        world_end_s=end_s,
        label=clock_label(calendar, end_s, language),
        duration_label=duration_label(end_s - start_s, language),
        personal_label=personal_label(end_s - start_s, personal_s, language),
    )

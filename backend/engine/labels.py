"""Time in words (W10, W10a, G16): dates in the world's own calendar, durations and how long ago.

The server sends these ready-made, so the app never formats an in-world date itself (API.md),
in the story's language (S10): English by default, Spanish or Catalan. What the turn's models
read stays English: they write in the story's language whatever their brief is in.
"""

import re
from datetime import datetime, timedelta

from engine.base import DAY, HOUR, MINUTE, EngineModel
from engine.context import Language
from engine.state.bible import Calendar, CalendarStyle, TimeOfDayStyle

EN = Language.EN
ES = Language.ES
CA = Language.CA

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

# S10: the parts of the day and the months as a Spanish or Catalan story shows them.
_PART_NAMES = {
    ES: {
        "night": "noche",
        "dawn": "amanecer",
        "morning": "mañana",
        "midday": "mediodía",
        "afternoon": "tarde",
        "dusk": "atardecer",
        "evening": "anochecer",
    },
    CA: {
        "night": "nit",
        "dawn": "alba",
        "morning": "matí",
        "midday": "migdia",
        "afternoon": "tarda",
        "dusk": "capvespre",
        "evening": "vespre",
    },
}
_MONTH_NAMES = {
    ES: (
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
    ),
    CA: (
        "gener",
        "febrer",
        "març",
        "abril",
        "maig",
        "juny",
        "juliol",
        "agost",
        "setembre",
        "octubre",
        "novembre",
        "desembre",
    ),
}
_DAY_WORD = {EN: "Day", ES: "Día", CA: "Dia"}
_YEAR_WORD = {ES: "año", CA: "any"}
_CATALAN_VOWELS = frozenset("aeiouàèéíïòóúü")


def of_name(name: str, language: Language) -> str:
    """ "de abril" in Spanish; in Catalan "de maig", but "d'abril" and "d'Hivern" before a
    vowel sound, though not before an "i" or "u" that leads into another vowel ("de Iuna").
    A name that opens with a small "el" takes it in, as both languages do: "del viejo
    herrero", "dels germans Roca". A capital one is part of the name and stays: "de El Cid"."""
    article, _, rest = name.partition(" ")
    if rest and language in (ES, CA) and article == "el":
        return f"del {rest}"
    if rest and language is CA and article == "els":
        return f"dels {rest}"
    if language is CA:
        sound = name.lower().removeprefix("h")
        glide = sound[:1] in "iu" and sound[1:2] in _CATALAN_VOWELS
        if sound[:1] in _CATALAN_VOWELS and not glide:
            return f"d'{name}"
    return f"de {name}"


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
    return _PART_NAMES[language][part] if language in _PART_NAMES else part


def _ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _day_count(calendar: Calendar, world_s: int, language: Language) -> tuple[str, str]:
    """The date and the time of day, apart, as the two below give them."""
    since_midnight = calendar.start_second_of_day + world_s
    day = since_midnight // DAY + 1
    return f"{_DAY_WORD[language]} {day}", _time_of_day(calendar, since_midnight, language)


def _gregorian(calendar: Calendar, world_s: int, language: Language) -> tuple[str, str] | None:
    try:
        start = datetime.fromisoformat(calendar.epoch or "")
        moment = start + timedelta(seconds=world_s)
    except (ValueError, OverflowError):
        return None
    second_of_day = moment.hour * HOUR + moment.minute * MINUTE + moment.second
    if language in _MONTH_NAMES:
        month = _MONTH_NAMES[language][moment.month - 1]
        date = f"{moment.day} {of_name(month, language)} de {moment.year}"
    else:
        date = f"{moment.day} {MONTH_NAMES[moment.month - 1]} {moment.year}"
    return date, _time_of_day(calendar, second_of_day, language)


def _custom(calendar: Calendar, world_s: int, language: Language) -> tuple[str, str] | None:
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
    if language in _YEAR_WORD:
        day = f"{_DAY_WORD[language]} {day_of_year + 1} {of_name(month.name, language)}"
        return f"{day}, {_YEAR_WORD[language]} {year}{era}", when
    return f"{_ordinal(day_of_year + 1)} day of {month.name}, year {year}{era}", when


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
    1974, 23:10" or "Día 3 de Luna de Escarcha, año 412, atardecer", and in Catalan "Dia 3,
    capvespre", "14 d'abril de 1974, 23:10" or "Dia 3 de Lluna de Gebre, any 412, capvespre"
    (S10). A calendar it can't read falls back to a day count, so a label is never missing."""
    return ", ".join(_date_and_time(calendar, world_s, language))


def date_label(calendar: Calendar, world_s: int, language: Language = EN) -> str:
    """The date alone, as `clock_label` tells it: "Day 3", "14 May 1974" or "3rd day of the
    Frost Moon, year 412"."""
    return _date_and_time(calendar, world_s, language)[0]


def _date_and_time(calendar: Calendar, world_s: int, language: Language) -> tuple[str, str]:
    if calendar.style is CalendarStyle.GREGORIAN:
        label = _gregorian(calendar, world_s, language)
    elif calendar.style is CalendarStyle.CUSTOM:
        label = _custom(calendar, world_s, language)
    else:
        label = None
    return label or _day_count(calendar, world_s, language)


# Words a date or a time of day is made of besides its numbers, in any of the app's languages.
_CLOCK_WORDS = frozenset(
    {"of", "the", "at", "year", "de", "del", "d", "a", "las", "les", "h"}
    | {part for _, part in DAY_PARTS}
    | {name for names in _PART_NAMES.values() for name in names.values()}
    | {word.lower() for word in (*_DAY_WORD.values(), *_YEAR_WORD.values())}
)
# The letters a number written as an ordinal ends in: "3rd", "1r", "2a", "4t", "1º".
_ORDINAL_LETTERS = "adhnrstèºª"


def only_the_clock(calendar: Calendar, world_s: int, text: str) -> bool:
    """Whether `text` says nothing but a date or a time of day ("Day 1, morning, 07:00", "Día 3,
    atardecer"), in any of the app's languages: every word of it is a number or a word the
    world's clock is told with around `world_s`. A text with no word at all isn't one."""
    words = re.findall(r"[^\W_]+", text.lower())
    if not words:
        return False
    told = set(_CLOCK_WORDS)
    for language in Language:
        told.update(re.findall(r"[^\W_]+", clock_label(calendar, world_s, language).lower()))
    for word in words:
        if word not in told and not word.rstrip(_ORDINAL_LETTERS).isdigit():
            return False
    return True


_UNITS = (
    (LABEL_YEAR, "y"),
    (DAY, "d"),
    (HOUR, "h"),
    (MINUTE, "min"),
    (1, "s"),
)
# S10: only the year has its own letter in Spanish and Catalan ("a" for "año" and "any").
_YEAR_UNIT = {ES: "a", CA: "a"}


def span_label(seconds: int, language: Language = EN) -> str:
    """A span in at most two units: "40 s", "3 min", "1 h 20 min", "2 d 4 h", "3 y 12 d" (in
    Spanish and Catalan "3 a 12 d")."""
    seconds = max(0, int(seconds))
    if seconds == 0:
        return "0 s"
    parts: list[str] = []
    for size, unit in _UNITS:
        if unit == "y":
            unit = _YEAR_UNIT.get(language, unit)
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
    "Mundo: +0 s. Tú: +40 s.", in Catalan "Món: +0 s. Tu: +40 s.". None when the user lived the
    same time as the world."""
    if world_s == personal_s:
        return None
    world, you = _CLOCKS[language]
    return (
        f"{world}: {duration_label(world_s, language)}. "
        f"{you}: {duration_label(personal_s, language)}."
    )


_CLOCKS = {EN: ("World", "You"), ES: ("Mundo", "Tú"), CA: ("Món", "Tu")}

# S10: each unit's Spanish and Catalan as one and as many, the one with its article ("un día",
# "una hora").
_AMOUNTS = {
    ES: {
        "minute": ("un minuto", "minutos"),
        "hour": ("una hora", "horas"),
        "day": ("un día", "días"),
        "week": ("una semana", "semanas"),
        "month": ("un mes", "meses"),
        "year": ("un año", "años"),
    },
    CA: {
        "minute": ("un minut", "minuts"),
        "hour": ("una hora", "hores"),
        "day": ("un dia", "dies"),
        "week": ("una setmana", "setmanes"),
        "month": ("un mes", "mesos"),
        "year": ("un any", "anys"),
    },
}


def amount(count: int, unit: str, language: Language = EN) -> str:
    """A count of a time unit (`minute`, `hour`, `day`, `week`, `month` or `year`) in words: "an
    hour", "3 days"; in Spanish "una hora", "3 días"; in Catalan "una hora", "3 dies"."""
    if language in _AMOUNTS:
        one, many = _AMOUNTS[language][unit]
        return one if count == 1 else f"{count} {many}"
    if count == 1:
        return f"an {unit}" if unit == "hour" else f"a {unit}"
    return f"{count} {unit}s"


def number_label(number: int, language: Language = EN) -> str:
    """A whole number with its thousands grouped the language's way: 12,500 in English, 12.500 in
    Spanish and Catalan (S10)."""
    return f"{number:,}".replace(",", _THOUSANDS[language])


_THOUSANDS = {EN: ",", ES: ".", CA: "."}


def _rough(seconds: int, language: Language) -> str:
    if seconds < HOUR:
        return amount(max(1, seconds // MINUTE), "minute", language)
    if seconds < DAY:
        return amount(seconds // HOUR, "hour", language)
    if seconds < 2 * LABEL_WEEK:
        return amount(seconds // DAY, "day", language)
    if seconds < 2 * LABEL_MONTH:
        return amount(seconds // LABEL_WEEK, "week", language)
    if seconds < LABEL_YEAR:
        return amount(seconds // LABEL_MONTH, "month", language)
    return amount(seconds // LABEL_YEAR, "year", language)


def ago_label(seconds: int, language: Language = EN) -> str:
    """How long ago, in rough words: "moments ago", "2 days ago" (W10, `/status`); in Spanish
    "hace un momento", "hace 2 días"; in Catalan "fa un moment", "fa 2 dies"."""
    just_now, ago = _AGO[language]
    if seconds < MINUTE:
        return just_now
    return ago.format(_rough(seconds, language))


_AGO = {
    EN: ("moments ago", "{} ago"),
    ES: ("hace un momento", "hace {}"),
    CA: ("fa un moment", "fa {}"),
}


def in_label(seconds: int, language: Language = EN) -> str:
    """How long until, in rough words: "in moments", "in 3 hours"; in Spanish "en un momento",
    "en 3 horas"; in Catalan "d'aquí a un moment", "d'aquí a 3 hores"."""
    soon, until = _UNTIL[language]
    if seconds < MINUTE:
        return soon
    return f"{until} {_rough(seconds, language)}"


_UNTIL = {
    EN: ("in moments", "in"),
    ES: ("en un momento", "en"),
    CA: ("d'aquí a un moment", "d'aquí a"),
}


# W10: the shortest scene whose passing the story marks, and the hour a new day starts for
# someone living it. A night ends when it gets light, not at midnight, so a scene that runs past
# midnight is still the same night and a night's sleep ends on the next day.
PASSAGE_MIN_S = 2 * HOUR
PASSAGE_NIGHT_S = 6 * HOUR
NEW_DAY_HOUR = DAY_PARTS[1][0]

# Small counts in words, from two to twenty, as a story's page would have them (S10).
_COUNT_WORDS = {
    EN: (
        "two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
        "sixteen seventeen eighteen nineteen twenty"
    ).split(),
    ES: (
        "dos tres cuatro cinco seis siete ocho nueve diez once doce trece catorce quince "
        "dieciséis diecisiete dieciocho diecinueve veinte"
    ).split(),
    CA: (
        "dos tres quatre cinc sis set vuit nou deu onze dotze tretze catorze quinze setze "
        "disset divuit dinou vint"
    ).split(),
}
# Catalan's two takes the gender of what it counts: "dues hores", "dues setmanes".
_FEMININE_UNITS = frozenset({"hour", "week"})
_NEXT_DAY = {EN: "The next day", ES: "Al día siguiente", CA: "L'endemà"}
_LATER = {EN: "{} later", ES: "{} después", CA: "{} després"}


def _count(count: int, unit: str, language: Language) -> str:
    """A count of a time unit with a small number in words: "three days", "dos semanas", "dues
    setmanes". One, and anything over twenty, reads as `amount` has it: "a year", "30 years"."""
    if not 2 <= count <= len(_COUNT_WORDS[language]) + 1:
        return amount(count, unit, language)
    word = _COUNT_WORDS[language][count - 2]
    if language is CA and count == 2 and unit in _FEMININE_UNITS:
        word = "dues"
    many = _AMOUNTS[language][unit][1] if language in _AMOUNTS else f"{unit}s"
    return f"{word} {many}"


def passage_label(
    calendar: Calendar, start_s: int, end_s: int, language: Language = EN
) -> str | None:
    """W10. The heading over a scene that hours or days passed in, as a book marks a cut:
    "Three hours later", "The next day", "Three days later", "A week later", "Two weeks later",
    "A year later"; in Spanish "Tres horas después", "Al día siguiente", "Tres días después"; in
    Catalan "Tres hores després", "L'endemà", "Tres dies després" (S10). None for a scene under
    two hours, which the time bar alone tells.

    Days are counted as someone living them counts: by the mornings that came (`NEW_DAY_HOUR`),
    so a night's sleep ends on the next day and a watch past midnight doesn't. A stretch under
    six hours is told in hours even across a dawn. From two weeks on it is told in weeks, from
    two months in months and from a year and a half in years, each to the nearest one, and a
    week, a month and a year are called that.
    """
    span = end_s - start_s
    if span < PASSAGE_MIN_S:
        return None
    since_dawn = second_of_day(calendar, start_s) - NEW_DAY_HOUR * HOUR
    days = (since_dawn + span) // DAY - since_dawn // DAY
    if days == 0 or span < PASSAGE_NIGHT_S:
        told = _count((span + HOUR // 2) // HOUR, "hour", language)
    elif days == 1:
        return _NEXT_DAY[language]
    else:
        told = _count(*_days_told(days), language)
    told = _LATER[language].format(told)
    return told[:1].upper() + told[1:]


_WEEK, _MONTH, _YEAR = LABEL_WEEK // DAY, LABEL_MONTH // DAY, LABEL_YEAR // DAY


def _days_told(days: int) -> tuple[int, str]:
    """Two days or more as a count of the unit a storyteller would use, to the nearest one."""
    if days < 2 * _WEEK:
        return (1, "week") if days == _WEEK else (days, "day")
    if days < 2 * _MONTH:
        whole_month = 4 * _WEEK <= days <= _MONTH + 1
        return (1, "month") if whole_month else ((days + _WEEK // 2) // _WEEK, "week")
    if days < _YEAR + _YEAR // 2 + 1:
        months = (days + _MONTH // 2) // _MONTH
        return (1, "year") if months == 12 else (months, "month")
    return ((days + _YEAR // 2) // _YEAR, "year")


class SceneTime(EngineModel):
    """The scene's time bar, in the shape of API.md's `Scene.time`."""

    world_start_s: int
    world_end_s: int
    label: str
    duration_label: str
    personal_label: str | None = None
    passage_label: str | None = None


def scene_time(
    calendar: Calendar, start_s: int, end_s: int, personal_s: int, language: Language = EN
) -> SceneTime:
    """The time bar for a scene that ran from `start_s` to `end_s` world seconds, in which the
    player character lived `personal_s` seconds, in the story's language (S10), with the heading
    that marks the hours or days that passed in it (`passage_label`)."""
    return SceneTime(
        world_start_s=start_s,
        world_end_s=end_s,
        label=clock_label(calendar, end_s, language),
        duration_label=duration_label(end_s - start_s, language),
        personal_label=personal_label(end_s - start_s, personal_s, language),
        passage_label=passage_label(calendar, start_s, end_s, language),
    )

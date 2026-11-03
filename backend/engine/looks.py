"""M1, M4, M5: when a place or a face changes for good, so its picture is drawn once more.

A place's picture and a character's portrait are keyed by their subject and a look version (M4).
The version moves only when the look changes for good, so a changed place or face is drawn once
more, and every later scene reuses that picture until it changes again.

- **A place** changes for good when it becomes ruined or occupied, or stops being so, such as a
  town rebuilt or freed (W7, C1). Its version counts those changes in its status history, so it
  needs no field of its own, and every way a place changes counts the same: a narrated
  occupation, a ruin resolve recorded, a burning hall at the end of a chain (A9). A place that was
  only damaged keeps its picture.
- **A character** changes for good when the appearance kept for their portrait (C9) shows
  something new, such as a lost eye or a scar (G17), or their age moves on to another stage of
  life, such as old age. `engine.apply` counts these in `Character.look_version`. The same look
  in other words, or an appearance written for the first time, is no change.
"""

import re

from engine.state.cast import Character, Place, PlaceStatus
from engine.state.records import StatusChange

LASTING_PLACE_STATUSES = frozenset({PlaceStatus.RUINED, PlaceStatus.OCCUPIED})
_LASTING = frozenset(status.value for status in LASTING_PLACE_STATUSES)

# The first age of each stage of life a portrait shows: child, teenager, young adult, adult,
# middle age, old age.
LIFE_STAGES = (13, 18, 30, 45, 60)

# Words that change how an appearance reads but not what it shows.
_FILLER = frozenset(
    """a an and are as at be but by for from has have he her his in is it its of on or she
    the their them they to with who whose""".split()
)
_WORD = re.compile(r"[^\W_]+")


def place_changed_for_good(entry: StatusChange) -> bool:
    """A status change that makes or unmakes a ruin or an occupation (W7)."""
    if entry.from_status == entry.status:
        return False
    return entry.status in _LASTING or entry.from_status in _LASTING


def place_version(place: Place) -> int:
    """The place's look version: 1, plus one for each change for good in its history."""
    return 1 + sum(place_changed_for_good(entry) for entry in place.status_history)


def appearance_words(text: str) -> frozenset[str]:
    """What an appearance shows, without the filler words or the order they come in."""
    return frozenset(w for w in _WORD.findall(text.casefold()) if w not in _FILLER)


def appearance_changed(before: str, after: str) -> bool:
    """Whether a new appearance shows something the kept one didn't, or no longer shows something
    it did. Writing one for the first time, or the same look in other words, is no change."""
    old, new = appearance_words(before), appearance_words(after)
    return bool(old) and bool(new) and old != new


def life_stage(age: int | None) -> int | None:
    if age is None:
        return None
    return sum(age >= start for start in LIFE_STAGES)


def changes_look(character: Character, *, appearance: str | None, age: int | None) -> bool:
    """Whether setting this appearance or age (None: unchanged) changes the character's look for
    good (M5)."""
    if appearance is not None and appearance_changed(character.appearance, appearance):
        return True
    before, after = life_stage(character.age), life_stage(age)
    return before is not None and after is not None and before != after


def place_looks(place: Place) -> str:
    """How a place looks for its picture: its description, and its state when it isn't
    thriving, so a ruined or occupied place is drawn as it is now (M1, W7)."""
    if place.status is PlaceStatus.THRIVING:
        return place.description
    return f"{place.description} It is {place.status.value} now.".strip()

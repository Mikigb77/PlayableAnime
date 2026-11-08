"""M1, M4, M5: when a place or a face changes for good, so its picture is drawn once more.

A place's picture and a character's portrait are keyed by their subject and a look version (M4).
The version moves only when the look changes for good, so a changed place or face is drawn once
more, and every later scene reuses that picture until it changes again.

- **A place** changes for good when it becomes ruined or occupied, or stops being so, such as a
  town rebuilt or freed (W7, C1). Its version counts those changes in its status history, so it
  needs no field of its own, and every way a place changes counts the same: a narrated
  occupation, a ruin resolve recorded, a burning hall at the end of a chain (A9). A place that was
  only damaged keeps its picture.
- **A character** changes for good when a change states a lasting difference to how they look
  (`CharacterChange.look_change`), such as a lost eye, a scar or grey hair with the years (G17).
  The narrator or the engine proposes it; `engine.apply` decides: the change must name something,
  the kept appearance (C9) is made to show it, and `Character.look_version` moves on once. An
  appearance written again without one, in the same words or others, never redraws a portrait.
"""

import re

from engine.state.cast import Character, Place, PlaceSetting, PlaceStatus
from engine.state.records import StatusChange

LASTING_PLACE_STATUSES = frozenset({PlaceStatus.RUINED, PlaceStatus.OCCUPIED})
# R8, M5: a place's setting in a picture's words, so a crypt is never drawn under the sky.
SETTING_LOOKS = {
    PlaceSetting.OUTDOORS: "Outdoors, under the open sky.",
    PlaceSetting.INDOORS: "Indoors, under a roof.",
    PlaceSetting.UNDERGROUND: "Underground, with no sky above.",
    PlaceSetting.UNDERWATER: "Underwater.",
}
_LASTING = frozenset(status.value for status in LASTING_PLACE_STATUSES)

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


def look_after(
    character: Character, *, appearance: str | None, look_change: str | None
) -> str | None:
    """M5: the appearance a lasting change leaves the character with, or None when the change
    isn't one. A change that names nothing is none. The appearance written with it is kept when it
    shows something the old one didn't, or no longer shows something it did; otherwise the change
    is added to the old appearance, so the kept look always shows it."""
    change = " ".join((look_change or "").split()).strip(" .")
    if not appearance_words(change):
        return None
    before = character.appearance.strip()
    written = (appearance or "").strip()
    if written and appearance_words(written) != appearance_words(before):
        return written
    kept = written or before
    sentence = change[0].upper() + change[1:] + "."
    return f"{kept} {sentence}" if kept else sentence


def place_looks(place: Place) -> str:
    """How a place looks for its picture: its description, whether it is under the sky (R8), and
    its state when it is ruined or occupied, so it is drawn as it is now (M1, W7). Damage mends,
    so a picture doesn't keep it."""
    parts = [place.description.strip()]
    if place.setting is not None:
        parts.append(SETTING_LOOKS[place.setting])
    if place.status in LASTING_PLACE_STATUSES:
        parts.append(f"It is {place.status.value} now.")
    return " ".join(part for part in parts if part)

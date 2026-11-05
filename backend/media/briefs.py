"""Who a scene picture shows, from the world state (M1, M5). Plain Python, no Django, so the turn
(`stories.turns`), Illustrate (`media.plans`) and the picture evals (`evals.pictures`) choose alike.

A scene picture shows the people its description names, not everyone who happens to be there, so
the picture follows the narration. The picture's subject comes first, whoever the director chose
it for (M1): the one who dies, the foe of a fight, the one whose strength shows, the doer of a
deed. A subject is shown even when they died in the scene or the player hasn't met them, since the
moment is theirs. The player character is in it when the description says "you" or names them,
or when it names no one else. A description that names no one falls back to the subject, the
player and the people the player knows there, as before. Each person's portrait then goes along
as a reference image (M5), in this order, the first `MAX_REFERENCES` of them.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from engine.contracts import PictureTrigger
from engine.labels import part_of_day, second_of_day
from engine.state.bible import Calendar
from engine.state.cast import Character
from engine.state.world import WorldState
from media.prompts import MAX_FIGURES, SAYS_YOU, Figure

# Words in a name that say nothing about who is meant on their own, such as "the" in "Mei of the
# Willows". A name's other words count on their own when written with a capital, as in the
# narration: "Brother Jo" names "Senior Brother Jo".
_PARTICLES = frozenset({"the", "of", "and", "von", "van", "der", "de", "del", "da", "la", "le"})

# Pictures whose subject is a thread, not a person (`engine.director.pictures`).
THREAD_SUBJECTS = frozenset({PictureTrigger.ARC_END, PictureTrigger.EVENT})


def figure(character: Character) -> Figure:
    """A person in a picture, with the appearance kept in their entry (C9)."""
    return Figure(
        id=character.id,
        name=character.name,
        appearance=character.appearance or character.description,
    )


def known_cast(
    state: WorldState, *, present: Sequence[str] | None = None, player_id: str | None = None
) -> list[Character]:
    """The living characters in the scene whom the player knows, the player left out (M4, M5).
    `present` is who is there, the scene's end by default."""
    player = player_id or state.player_id
    found = []
    for character_id in dict.fromkeys(state.scene.present_ids if present is None else present):
        character = state.characters.get(character_id)
        if character is None or character_id == player or not character.alive:
            continue
        if player in character.known_by or player in character.met_by:
            found.append(character)
    return found


def scene_figures(
    state: WorldState,
    description: str,
    *,
    subject_id: str | None = None,
    player_id: str | None = None,
    present: Sequence[str] | None = None,
) -> tuple[Figure, ...]:
    """The people a scene picture or cover shows, the subject first, then the player character,
    then the others the description names. `subject_id` is the character or deed the director
    chose the picture for (M1). `present` is who is there: the scene's end by default, or a past
    scene's saved cast for Illustrate, with that scene's `player_id`."""
    player = player_id or state.player_id
    subjects, involved = _subjects(state, subject_id)
    there = list(state.scene.present_ids if present is None else present)
    pool = dict.fromkeys([*subjects, player, *involved, *there])
    named = [i for i in pool if i in state.characters and names(description, state.characters[i])]
    says_you = bool(SAYS_YOU.search(description))
    if named or says_you:
        others = [i for i in named if i != player and i not in subjects]
        shown = (
            player in subjects
            or player in named
            or says_you
            or not [i for i in (*subjects, *others) if i != player]
        )
        people = [*subjects, *([player] if shown else []), *others]
    elif present is None:
        people = [*subjects, player, *(c.id for c in known_cast(state, player_id=player))]
    else:
        people = [*subjects, player, *there]
    chosen = [state.characters[i] for i in dict.fromkeys(people) if i in state.characters]
    return tuple(figure(character) for character in chosen[:MAX_FIGURES])


def names(text: str, character: Character) -> bool:
    """Whether `text` names `character`: their name or an alias in full, in any case, or a word of
    their name written with a capital, such as "Rosa" for "Rosa Esposito"."""
    for name in (character.name, *character.aliases):
        name = " ".join(name.split())
        if len(name) >= 2 and re.search(_whole(name), text, re.IGNORECASE):
            return True
    for word in character.name.split():
        if len(word) >= 3 and word[0].isupper() and word.casefold() not in _PARTICLES:
            if re.search(_whole(word), text):
                return True
    return False


def time_of_day(calendar: Calendar, world_s: int) -> str:
    """The part of the day at `world_s` on the world's clock, such as "dusk" (W10)."""
    return part_of_day(second_of_day(calendar, world_s))


def player_at(state: WorldState, turn: int) -> str:
    """Who the player character was in scene `turn`: an earlier player character up to the scene
    their story ended in, then whoever carried it on (N6)."""
    for fallen in sorted(state.fallen, key=lambda f: f.turn):
        if turn <= fallen.turn and fallen.character_id in state.characters:
            return fallen.character_id
    return state.player_id


def _subjects(state: WorldState, subject_id: str | None) -> tuple[list[str], list[str]]:
    """Who the picture is about, and the others its subject involves: a deed's doer, and the
    people it was done to, who are in the picture when the description names them."""
    if not subject_id:
        return [], []
    if subject_id in state.characters:
        return [subject_id], []
    deed = state.deeds.get(subject_id)
    if deed is None:
        return [], []
    doer = [deed.actor_id] if deed.actor_id in state.characters else []
    return doer, [*deed.target_ids, *deed.victim_ids]


def _whole(words: str) -> str:
    """A pattern for `words` standing on their own, not inside a longer word."""
    return rf"(?<!\w){re.escape(words)}(?!\w)"

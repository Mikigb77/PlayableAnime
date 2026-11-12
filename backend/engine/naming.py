"""Who words name, among the people on record (V3, W1, F3).

The interpret step gives a person's id where it can and words where it can't, and the real model
often leaves the id out: "I cut Han's throat" was read as a killing aimed at no one (2026-11-11),
and "I kiss Mei" played unchecked though the story had Mei on record, aged sixteen
(2026-11-12). So code reads names itself, the same way wherever it needs them: the check of the
reading (`graph.turn.check`), which never picks someone the words don't single out
(`named_in`), and the hard limits (`engine.limits`), which hold everyone the words could mean
(`everyone_called`, `everyone_named`).

A name is read as it is written, not by what it means: a name or alias of several words
wherever the words carry it, and one word of a name only where it has a capital that doesn't
just open a sentence: "Mo" for Elder Mo, never the "sol" of "under the sun" for someone called
Sol, nor the "Old" a sentence opens with for Old Bram. Nothing here knows a language or a genre
(G5), and a name in a script `normalize` can't fold is never found.
"""

import re
from collections.abc import Iterable, Sequence

from engine.state.world import WorldState
from engine.text import normalize

# A word of letters, in any script.
_WORD = r"[^\W\d_]+"
# What a sentence can open after: its capital is no sign of a name.
_OPENS_AFTER = '.!?:;\u00a1\u00bf"\u201c\u00ab(\u2014'
# The small words a few words for someone open with, capital or not: "The barmaid", "La Mei".
_OPENERS = frozenset("the a an el la los las els les lo un una uns unes en na l".split())


def names(state: WorldState, character_id: str) -> list[str]:
    """A character's name and aliases, folded (`normalize`), without any that folds to nothing."""
    character = state.characters[character_id]
    return [n for n in (normalize(name) for name in (character.name, *character.aliases)) if n]


def called(state: WorldState, said: str, among: Sequence[str]) -> str | None:
    """The one person of `among` whose name or alias is exactly these words, whatever their
    case, accents or punctuation. None when nobody is, or more than one."""
    words = normalize(said)
    found = [i for i in among if words and words in names(state, i)]
    return found[0] if len(found) == 1 else None


def capitals(text: str, *, opening: bool = False) -> set[str]:
    """The words of a text written with a capital that doesn't just open a sentence, folded.
    With `opening` its first word counts too, unless it is an article: the text is a few words
    for someone, such as a step's `targets`, and not a sentence."""
    found = set()
    for match in re.finditer(_WORD, text):
        before = text[: match.start()].rstrip()
        folded = normalize(match.group())
        inside = before and before[-1] not in _OPENS_AFTER
        first = opening and not before and folded not in _OPENERS
        if match.group()[:1].isupper() and (inside or first):
            found.add(folded)
    return found - {""}


def named_in(state: WorldState, texts: Iterable[str], among: Sequence[str]) -> list[str]:
    """Those of `among` some text names: by a name or alias of several words, or by one word
    that is theirs alone there (a one-word name, or a word of their name nobody else shares),
    written with a capital inside a sentence, as names are."""
    whole, spoken = _read(texts)
    parts = _parts(state, among)
    found = []
    for character_id in among:
        own = {word for word, whose in parts.items() if whose == {character_id}}
        if _in_full(state, character_id, whole) or own & spoken:
            found.append(character_id)
    return found


def everyone_called(
    state: WorldState, circles: Sequence[Sequence[str]], labels: Iterable[str]
) -> list[str]:
    """Everyone a few words for someone could be, such as a step's `targets`: the words, with
    or without an article that opens them, are a name or alias of theirs whole, or one word of
    their name with its capital. Each label names those of the nearest circle who answer to
    it. Words that only hold a name name nobody here: "the Jade Pavilion" is not Jade."""
    found: list[str] = []
    for label in labels:
        words = re.findall(_WORD, label)
        bare = words[1:] if words and normalize(words[0]) in _OPENERS else words
        # Several words are a name in any case, one word only with its capital.
        forms = {normalize(" ".join(form)) for form in (words, bare) if len(form) > 1}
        word = normalize(bare[0]) if len(bare) == 1 and bare[0][:1].isupper() else ""
        forms = (forms | {word}) - {""}
        for circle in circles:
            carry = _parts(state, circle).get(word, set()) if word else set()
            answer = [i for i in circle if i in carry or forms & set(names(state, i))]
            if answer:
                found += [i for i in answer if i not in found]
                break
    return found


def everyone_named(
    state: WorldState,
    circles: Sequence[Sequence[str]],
    texts: Iterable[str] = (),
    labels: Iterable[str] = (),
) -> list[str]:
    """Everyone the words could mean, for a check that must not miss anyone. `circles` are the
    people on record from the nearest to the story's moment to the farthest, and `labels` are a
    few words for someone rather than a sentence (`capitals`).

    Whoever the words give a full name or alias of several words is named, wherever they are,
    and the words of that name are theirs: the "Old" of "Old Tess" isn't Old Bram. One word of
    a name then names those of the nearest circle who carry it, each of them when they share
    it: "Mei" is the Mei of the scene rather than one a day's ride away, and Mei Lin and Mei
    Hua both when both are there, since either could be meant. Someone named for another's
    sake counts too ("Mei's mother" names Mei): code can't tell her from "Mei's lips"."""
    whole, spoken = _read(texts, labels)
    found = [i for circle in circles for i in circle if _in_full(state, i, whole)]
    spoken -= {word for i in found for name in _in_full(state, i, whole) for word in name.split()}
    for circle in circles:
        heard = {word: whose for word, whose in _parts(state, circle).items() if word in spoken}
        found += [i for i in circle if i not in found and any(i in w for w in heard.values())]
        spoken -= heard.keys()
    return found


def _read(texts: Iterable[str], labels: Iterable[str] = ()) -> tuple[list[str], set[str]]:
    """The texts folded whole, each between spaces, and the capitals they carry."""
    texts, labels = [t for t in texts if t], [t for t in labels if t]
    whole = [f" {normalize(text)} " for text in (*texts, *labels)]
    spoken = {word for text in texts for word in capitals(text)}
    spoken |= {word for label in labels for word in capitals(label, opening=True)}
    return whole, spoken


def _parts(state: WorldState, among: Sequence[str]) -> dict[str, set[str]]:
    """Each word the names of `among` are written with a capital in, folded, and whose it is."""
    parts: dict[str, set[str]] = {}
    for character_id in among:
        character = state.characters[character_id]
        for name in (character.name, *character.aliases):
            for word in re.findall(_WORD, name):
                if word[:1].isupper():
                    parts.setdefault(normalize(word), set()).add(character_id)
    return parts


def _in_full(state: WorldState, character_id: str, whole: list[str]) -> list[str]:
    """Their names and aliases of several words that some text carries whole."""
    several = [name for name in names(state, character_id) if " " in name]
    return [name for name in several if any(f" {name} " in text for text in whole)]

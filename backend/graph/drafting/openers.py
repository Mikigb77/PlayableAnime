"""G1, G2: how the story starts, which a draft's summary keeps a surprise.

An opener is one of the things that give a story's start away: a deadline, an open question, a
key person, a connection of the character's, or a goal or a want of theirs. The drafter writes
them and the story tells them in play; the summary shows one only when the player's own words
name it (`graph.drafting.named`).

The premise is the player's own words, and the draft keeps it, so it is read each time. A change
they ask for later is not kept: when it is made, code notes which openers its words named
(`named_by`), and the draft keeps those as keys (`Said.told`): a clock's, a question's or a
person's id, a connection's name, a goal's or a want's text, all of it already in the draft's
own records.

A deadline their words set a time for comes at that time (`clock_times`, E2): the drafter splits
it into steps, and code makes the steps add up to what the player said.
"""

from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass

from engine.context import Language
from engine.state import Character, Clock, Connection, Goal, GoalStatus, Mystery, WorldState
from graph.drafting.named import called, named, timed, times_ahead
from graph.words import WORD, core

# The openers a draft keeps by their words, since they have no id of their own.
_BY_WORDS = ("connection", "goal", "want")


@dataclass(frozen=True)
class Opener:
    """One thing of how the story starts. `text` is what tells of it, in the words that are its
    own: what a faction, a place or a people of the world is called says nothing of it, so a
    premise that speaks of the Azure Cloud Sect doesn't name "the Azure Cloud Sect's
    tournament". `name` is the own name of the person it is or is about; a person has no
    `text`, since only their name names them. A `deadline` is also named by a time set for
    it."""

    key: str
    text: str
    name: str = ""
    deadline: bool = False


@dataclass(frozen=True)
class Said:
    """The player's say in how the story starts: their premise, and the keys of the openers a
    change they asked for later named."""

    premise: str
    told: frozenset[str] = frozenset()

    def names(self, opener: Opener, language: Language) -> bool:
        return opener.key in self.told or names(self.premise, opener, language)


def names(words: str, opener: Opener, language: Language) -> bool:
    """Whether `words`, the player's own, name the opener: they call its person by name, say
    what it tells of, or set a time for it when it is a deadline."""
    if called(words, opener.name, language) or named(words, opener.text, language):
        return True
    return opener.deadline and timed(words, opener.text, language)


def of_clock(state: WorldState, clock: Clock) -> Opener:
    return Opener(f"clock:{clock.id}", _own_words(state, clock.name), deadline=True)


def of_question(state: WorldState, mystery: Mystery) -> Opener:
    return Opener(f"mystery:{mystery.id}", _own_words(state, mystery.question))


def of_person(state: WorldState, character: Character) -> Opener:
    return Opener(f"person:{character.id}", "", own_names(state, character))


def of_connection(state: WorldState, connection: Connection) -> Opener:
    who = state.characters.get(connection.character_id or "")
    told = _own_words(state, connection.name)
    return Opener(_worded("connection", connection.name), told, own_names(state, who))


def of_goal(state: WorldState, goal: Goal) -> Opener:
    return Opener(_worded("goal", goal.text), _own_words(state, goal.text))


def of_want(state: WorldState, want: str) -> Opener:
    """What the character wants is a goal by another name: "Wants to prove that the sword can
    stand equal to aura" is the drafter's, and the player's only once their own words say it."""
    return Opener(_worded("want", want), _own_words(state, want))


def openers(state: WorldState) -> Iterator[Opener]:
    """Every opener of the draft, hidden or not."""
    for clock in state.clocks.values():
        yield of_clock(state, clock)
    for mystery in state.bible.mysteries:
        yield of_question(state, mystery)
    for character in state.npcs():
        yield of_person(state, character)
    for connection in state.player.sheet.resources.connections:
        yield of_connection(state, connection)
    for goal in state.goals.values():
        if goal.status is GoalStatus.ACTIVE:
            yield of_goal(state, goal)
    for want in state.player.sheet.disposition.temperament.wants:
        yield of_want(state, want)


def named_by(state: WorldState, words: str, language: Language) -> frozenset[str]:
    """The keys of the openers that `words`, the player's own, name."""
    if not words.strip():
        return frozenset()
    return frozenset(o.key for o in openers(state) if names(words, o, language))


def clock_times(state: WorldState, words: str, language: Language) -> dict[str, int]:
    """E2, G1: how far ahead `words`, the player's own, set each deadline they give a time, in
    seconds by clock id: "the knight exam is in 3 days" sets three days for "The knight exam",
    whatever the drafter's steps add up to. Each time goes to the one deadline it says most of,
    and to none where two share that or code can't read its length ("in a few days")."""
    found: dict[str, int] = {}
    for time in times_ahead(words, language):
        if time.seconds is None:
            continue
        said = {
            clock.id: count
            for clock in state.clocks.values()
            if (count := time.says(of_clock(state, clock).text, language))
        }
        most = max(said.values(), default=0)
        best = [clock_id for clock_id, count in said.items() if count == most]
        if len(best) == 1:
            found[best[0]] = time.seconds
    return found


def carried(state: WorldState, told: frozenset[str], language: Language) -> frozenset[str]:
    """`told` after a change to the draft: the keys of the openers that are still there. A
    goal, a want and a connection are kept by their words, so one the change only reworded
    keeps its place under its new words."""
    now = list(openers(state))
    kept = told & {o.key for o in now}
    for key in sorted(told - kept):
        kind, _, words = key.partition(":")
        if kind not in _BY_WORDS:
            continue
        reworded = next(
            (
                o.key
                for o in now
                if o.key.startswith(f"{kind}:")
                and o.key not in kept
                and named(words, o.text, language)
            ),
            None,
        )
        if reworded is not None:
            kept |= {reworded}
    return kept


def moved(
    before: WorldState, after: WorldState, told: frozenset[str], language: Language
) -> frozenset[str]:
    """`told` after a change that only rewords records, such as a new name for the character,
    which a goal of theirs may say: each key follows its opener to the words it has now. A
    change that adds or removes an opener is read as any other (`carried`)."""
    was = [opener.key for opener in openers(before)]
    now = [opener.key for opener in openers(after)]
    if len(was) != len(now):
        return carried(after, told, language)
    follows = dict(zip(was, now, strict=True))
    return frozenset(follows[key] for key in told if key in follows)


def own_names(state: WorldState, character: Character | None) -> str:
    """What a person is called that is theirs alone: their name and aliases without the words
    someone else is called by too, so Salvatore Esposito of the Esposito family is named by
    "Salvatore", never by the family the premise speaks of, and Elder Mo never by "Elder" where
    there are two elders. "" for nobody on record."""
    if character is None:
        return ""
    count = Counter(word for other in state.characters.values() for word in _called(other))
    return " ".join(
        word
        for name in (character.name, *character.aliases)
        for word in WORD.findall(name)
        if count[core(word)] < 2
    )


def _called(character: Character) -> set[str]:
    return {core(w) for name in (character.name, *character.aliases) for w in WORD.findall(name)}


def _own_words(state: WorldState, text: str) -> str:
    """`text` without the words a faction, a place or a people of the world is called by, or
    whole when those are all it has."""
    groups = [f.name for f in state.factions.values()]
    groups += [p.name for p in state.places.values()]
    groups += [p.name for p in state.bible.peoples]
    shared = {core(word) for name in groups for word in WORD.findall(name)}
    own = " ".join(word for word in WORD.findall(text) if core(word) not in shared)
    return own or text


def _worded(kind: str, text: str) -> str:
    return f"{kind}:{' '.join(text.casefold().split())}"

"""G1, G2: how the story starts, which a draft's summary keeps a surprise.

An opener is one of the things that give a story's start away: a deadline, an open question, a
key person, a connection of the character's, or a goal or a want of theirs. The drafter writes
them and the story tells them in play; the summary shows one only when the player's own words
name it (`graph.drafting.named`). A goal or a want is named only where those words say it as
something the character is after: "the knight exam is in 3 days" sets a deadline, and the goal a
drafter makes of it ("Pass the knight exam") is the story's to tell.

The premise is the player's own words, and the draft keeps it, so it is read each time. A change
they ask for later is not kept: when it is made, code notes which openers its words named
(`named_by`), and the draft keeps those as keys (`Said.told`): a clock's, a question's or a
person's id, a connection's name, a goal's or a want's text, all of it already in the draft's
own records.

A deadline their words set a time for comes at that time (`clock_times`, E2): the drafter splits
it into steps, and code makes the steps add up to what the player said.

What the summary kept a surprise, the story's own screens keep back too (C6, `engine.untold`):
the people the character knows, their goals and the threads already running that the player's
words don't name (`kept_back`) stay off Memory until a scene's own words name them (`told_by`).
"""

import re
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass

from engine import untold
from engine.context import Language
from engine.state import (
    Character,
    Clock,
    Connection,
    Goal,
    GoalStatus,
    Mystery,
    Thread,
    WorldState,
)
from graph.drafting.named import aimed, called, named, timed, times_ahead, told_of
from graph.words import FILLER, WORD, core

# The openers a draft keeps by their words, since they have no id of their own.
_BY_WORDS = ("connection", "goal", "want")


@dataclass(frozen=True)
class Opener:
    """One thing of how the story starts. `text` is what tells of it, in the words that are its
    own: what a faction, a place or a people of the world is called says nothing of it, so a
    premise that speaks of the Azure Cloud Sect doesn't name "the Azure Cloud Sect's
    tournament". `name` is the own name of the person it is or is about; a person has no
    `text`, since only their name names them. A `deadline` is also named by a time set for
    it. An `aim` is what the character is after, a goal or a want: the player's words name it
    only where they say it as one."""

    key: str
    text: str
    name: str = ""
    deadline: bool = False
    aim: bool = False


@dataclass(frozen=True)
class Said:
    """The player's say in how the story starts: their premise, and the keys of the openers a
    change they asked for later named."""

    premise: str
    told: frozenset[str] = frozenset()

    def names(self, opener: Opener, language: Language) -> bool:
        return opener.key in self.told or names(self.premise, opener, language)


def names(words: str, opener: Opener, language: Language, *, plainly: bool = False) -> bool:
    """Whether `words`, the player's own, name the opener: they call its person by name, say
    what it tells of, or set a time for it when it is a deadline. An aim has to be said as one
    (`aimed`): "I must pass the knight exam" names the goal, and "the knight exam is in 3 days"
    names the deadline alone. `plainly` is for words already known to speak of what the
    character is after, such as a change asked at the goal's own row: there, saying what the
    aim tells of names it."""
    if called(words, opener.name, language):
        return True
    if opener.aim and not plainly:
        return aimed(words, opener.text, language)
    if named(words, opener.text, language):
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
    return Opener(_worded("goal", goal.text), _own_words(state, goal.text), aim=True)


def of_want(state: WorldState, want: str) -> Opener:
    """What the character wants is a goal by another name: "Wants to prove that the sword can
    stand equal to aura" is the drafter's, and the player's only once their own words say it."""
    return Opener(_worded("want", want), _own_words(state, want), aim=True)


def of_thread(state: WorldState, thread: Thread) -> Opener:
    """A thread already running when the story starts. The summary never lists one, but its
    title says what is coming as its deadline does, so the story's screens keep it back the
    same way (`kept_back`)."""
    return Opener(f"thread:{thread.id}", _own_words(state, thread.title))


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


def named_by(
    state: WorldState, words: str, language: Language, *, plainly: bool = False
) -> frozenset[str]:
    """The keys of the openers that `words`, the player's own, name. `plainly` is for words
    asked at the row of what the character is after (`names`)."""
    if not words.strip():
        return frozenset()
    return frozenset(o.key for o in openers(state) if names(words, o, language, plainly=plainly))


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


def kept_back(state: WorldState, language: Language, said: Said) -> list[str]:
    """G1, C6: what a story holds back from the player's screens when it starts, as the keys of
    `engine.untold`: of the people the character knows, their goals and the threads they know
    of, each one the player's own words don't name. It is what the draft's summary kept a
    surprise, so a story never shows on its first screen what the draft wouldn't."""
    you = state.player_id
    keys = [untold.key(untold.PERSON, c.id) for c in state.npcs() if you in c.known_by]
    keys += [
        untold.key(untold.GOAL, goal.id)
        for goal in state.goals.values()
        if goal.status is GoalStatus.ACTIVE
    ]
    keys += [untold.key(untold.THREAD, t.id) for t in state.threads.values() if you in t.known_by]
    return sorted(
        key
        for key in keys
        if not any(said.names(opener, language) for opener in _behind(state, key))
    )


def told_by(state: WorldState, scene: str, language: Language) -> list[str]:
    """C6: of what the story still holds back (`WorldState.untold`), the keys the words of a
    turn name (`scene`: what the player wrote, the scene and the choices it offers), so the
    player's screens show it from then on. A thread is read as in a premise (`names`): the
    words say most of what it says, or set a time for its deadline. A goal is told once the
    words say most of what it says, with no need to say it as an aim: a scene that tells of the
    knight exam has told the player what "Pass the knight exam" is about. A person is named
    when the words call them by a name of their own as prose does (`told_of`), and what a place
    or a faction is called doesn't: a scene that opens in "Carmine's bar" has named the bar,
    and Carmine only once it calls him too."""
    if not state.untold or not scene.strip():
        return []
    people = _without_groups(state, scene, language)
    found = []
    for key in state.untold:
        person = key.startswith(f"{untold.PERSON}:")
        for opener in _behind(state, key):
            if person:
                told = told_of(people, opener.name, language)
            else:
                told = names(scene, opener, language, plainly=True)
            if told:
                found.append(key)
                break
    return found


def _behind(state: WorldState, key: str) -> list[Opener]:
    """The openers that stand for a record the story's screens hold back: the person, the
    goal, or the thread with the deadline it follows and the questions it carries, since words
    that name the tournament have named its thread."""
    kind, _, record_id = key.partition(":")
    if kind == untold.PERSON:
        character = state.characters.get(record_id)
        return [of_person(state, character)] if character is not None else []
    if kind == untold.GOAL:
        goal = state.goals.get(record_id)
        return [of_goal(state, goal)] if goal is not None else []
    thread = state.threads.get(record_id) if kind == untold.THREAD else None
    if thread is None:
        return []
    found = [of_thread(state, thread)]
    clock = state.clocks.get(thread.clock_id or "")
    if clock is not None:
        found.append(of_clock(state, clock))
    found += [of_question(state, m) for m in state.bible.mysteries if m.thread_id == thread.id]
    return found


def _without_groups(state: WorldState, text: str, language: Language) -> str:
    """`text` without what a faction, a place or a people of the world is called, where that is
    two words or more after its article: "Carmine's bar" and "the Zhao clan" say nothing of
    Carmine or of Zhao Kun."""
    names = [f.name for f in state.factions.values()]
    names += [p.name for p in state.places.values()]
    names += [p.name for p in state.bible.peoples]
    filler = FILLER[language]
    phrases = set()
    for name in names:
        words = WORD.findall(name)
        while words and core(words[0]) in filler:
            words = words[1:]
        phrases.add(tuple(words))
    for words in sorted(phrases, key=lambda words: (-len(" ".join(words)), words)):
        if len(words) < 2:
            continue
        pattern = r"[\s'’-]+".join(re.escape(word).replace("'", "['’]") for word in words)
        text = re.sub(rf"(?<!\w){pattern}(?!\w)", " ", text, flags=re.IGNORECASE)
    return text


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

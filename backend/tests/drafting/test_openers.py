"""G1: the openers of a draft (its deadlines, questions, people, connections, goals and wants),
which ones the player's own words name, what a draft keeps of that, the time their words set
for a deadline (E2), and what a story holds back from Memory until a scene names it (C6). Every
premise and scene is made up."""

from engine.base import DAY, WEEK
from engine.context import Language
from engine.state import GoalStatus
from graph.drafting import samples
from graph.drafting.assemble import DraftOptions, assemble
from graph.drafting.openers import (
    Said,
    carried,
    clock_times,
    kept_back,
    named_by,
    names,
    of_clock,
    of_want,
    openers,
    own_aims,
    own_names,
    told_by,
)

EN = Language.EN


def _state(proposal, premise):
    return assemble(proposal.world, proposal.character, DraftOptions(premise=premise))


def _naples():
    return _state(samples.naples(), samples.NAPLES_PREMISE)


def _cultivation():
    return _state(samples.cultivation(), samples.CULTIVATION_PREMISE)


def test_every_deadline_question_person_connection_goal_and_want_is_an_opener():
    keys = {opener.key for opener in openers(_naples())}

    assert {"clock:council", "person:carmine", "goal:find out who killed my father."} <= keys
    assert "connection:three loyal soldiers" in keys
    assert "want:revenge for his father" in keys
    assert any(key.startswith("mystery:") for key in keys)


def test_what_the_character_wants_is_theirs_once_their_words_say_it():
    state = _naples()
    want = of_want(state, "revenge for his father")

    # The premise speaks of a father who was killed, never of revenge.
    assert not Said(samples.NAPLES_PREMISE).names(want, EN)
    assert named_by(state, "I want revenge for my father.", EN) >= {"want:revenge for his father"}
    # Kept by its words, as a goal is: the same want in other words keeps its place.
    told = frozenset({"want:revenge for my dead father"})
    assert carried(state, told, EN) == {"want:revenge for his father"}


def test_words_name_openers_by_what_they_say_a_name_or_a_time_ahead():
    state = _cultivation()

    # The deadline alone: a time set for the tournament says nothing of what the character is
    # after, so the goal the drafter made of it stays the story's.
    assert named_by(state, "The ranking tournament is in two days.", EN) == {"clock:tournament"}
    # Said as an aim, the goal is the player's too.
    assert named_by(state, "I have to survive the ranking tournament in two days.", EN) == {
        "clock:tournament",
        "goal:survive the ranking tournament.",
    }
    assert named_by(state, "Zhao Kun has hated me since I arrived.", EN) == {"person:zhao"}
    # One word of the deadline is enough in a sentence that sets a time for it.
    assert named_by(state, "I fight in the tournament tomorrow.", EN) == {"clock:tournament"}
    assert named_by(state, "I love tournaments.", EN) == frozenset()
    assert named_by(state, "Make it rain more.", EN) == frozenset()
    assert named_by(state, "  ", EN) == frozenset()


def test_what_the_world_s_groups_and_places_are_called_names_nothing_of_an_opener():
    state = _cultivation()
    sect = next(iter(state.factions.values())).name
    clock = state.clocks["tournament"].model_copy(update={"name": f"{sect} tournament"})

    opener = of_clock(state, clock)

    assert opener.text == "tournament"
    # The premise speaks of the sect, which names no event in it.
    assert not names(f"I join {sect} tomorrow.", opener, EN)
    assert names("The tournament is tomorrow.", opener, EN)
    # A deadline called only by a group's name keeps its words.
    assert of_clock(state, clock.model_copy(update={"name": sect})).text == sect


def test_the_players_say_is_the_premise_and_what_their_changes_named():
    state = _cultivation()
    tournament = of_clock(state, state.clocks["tournament"])

    assert not Said(samples.CULTIVATION_PREMISE).names(tournament, EN)
    assert Said(samples.CULTIVATION_PREMISE, frozenset({"clock:tournament"})).names(tournament, EN)
    assert Said("The ranking tournament is in two days.").names(tournament, EN)


def test_a_draft_keeps_the_keys_of_what_is_still_there():
    state = _naples()
    told = frozenset({"clock:council", "clock:gone", "person:nobody", "goal:leave naples"})

    assert carried(state, told, EN) == {"clock:council"}
    # A goal is kept by its words, so the same goal in other words keeps its place.
    reworded = frozenset({"goal:find who killed my father"})
    assert carried(state, reworded, EN) == {"goal:find out who killed my father."}


def test_a_person_is_called_by_what_is_theirs_alone():
    state = _naples()

    # Carmine's crew is called after him, and he is still Carmine.
    assert any("Carmine" in faction.name for faction in state.factions.values())
    assert own_names(state, state.characters["carmine"]) == "Carmine Russo"
    assert own_names(state, None) == ""
    # A name two people carry is a family's.
    state.characters["carmine"].name = f"Carmine {state.player.name.split()[-1]}"
    assert own_names(state, state.characters["carmine"]) == "Carmine"


def test_a_deadline_comes_when_the_players_words_say():
    state = _cultivation()

    # E2: whatever the drafter's steps add up to, the player said five days.
    assert clock_times(state, "The ranking tournament is in five days.", EN) == {
        "tournament": 5 * DAY
    }
    assert clock_times(state, "I fight in the tournament in a week, ready or not.", EN) == {
        "tournament": WEEK
    }
    # A time for something else, a time gone by and a length code can't read set nothing.
    assert clock_times(state, "The exam is in three days.", EN) == {}
    assert clock_times(state, "The tournament was three days ago.", EN) == {}
    assert clock_times(state, "The tournament is in a few days.", EN) == {}
    assert clock_times(state, samples.CULTIVATION_PREMISE, EN) == {}


def test_a_time_goes_to_the_one_deadline_it_says_most_of():
    state = _cultivation()
    tournament = state.clocks["tournament"]
    state.clocks["exam"] = tournament.model_copy(update={"id": "exam", "name": "The ranking exam"})

    # "ranking tournament" is two words of one and one of the other.
    assert clock_times(state, "The ranking tournament is in five days.", EN) == {
        "tournament": 5 * DAY
    }
    # "ranking" alone is as much of one as of the other: neither is set.
    assert clock_times(state, "The ranking is in five days.", EN) == {}


def _holding(state, premise, told=frozenset(), also=()):
    held = sorted([*kept_back(state, EN, Said(premise, told)), *also])
    return state.model_copy(update={"untold": held})


def _aims(state) -> tuple[list[str], list[str]]:
    """What the character is after on record: their goals, and what they want."""
    goals = [goal.text for goal in state.goals.values()]
    return goals, state.player.sheet.disposition.temperament.wants


def test_a_story_starts_with_the_aims_the_players_words_say_and_no_other():
    # G1, G2, N2 (the first plays on the real models, 2026-11-14: "Win the miller's wife's
    # heart" for a smith in love with her, kept out of sight and steering every scene). The
    # bare premise says no aim, so the goal and the want the drafter wrote are no surprise the
    # story keeps: it starts without them.
    state = _cultivation()
    assert _aims(state) == (["Survive the ranking tournament."], ["to climb"])

    assert _aims(own_aims(state, EN, Said(samples.CULTIVATION_PREMISE))) == ([], [])
    # The draft's own state is never changed.
    assert _aims(state) == (["Survive the ranking tournament."], ["to climb"])

    # An aim their premise says is theirs, and the rest still goes.
    sworn = Said(f"{samples.CULTIVATION_PREMISE} I must survive the ranking tournament.")
    assert _aims(own_aims(state, EN, sworn)) == (["Survive the ranking tournament."], [])
    # So is one a change they asked for named, which the draft keeps by its key.
    asked = Said(samples.CULTIVATION_PREMISE, frozenset({"want:to climb"}))
    assert _aims(own_aims(state, EN, asked)) == ([], ["to climb"])
    # A state whose every aim is theirs comes back as it is.
    both = Said(sworn.premise, asked.told)
    assert own_aims(state, EN, both) is state

    # What happened is no aim: the Naples premise keeps its open question and gives no goal.
    naples = own_aims(_naples(), EN, Said(samples.NAPLES_PREMISE))
    assert _aims(naples) == ([], [])
    assert [m.question for m in naples.bible.mysteries] == [
        m.question for m in _naples().bible.mysteries
    ]


def test_a_goal_that_is_over_is_not_an_aim_to_drop():
    # Only what the character is after now is read: a goal on record as over stays there.
    state = _cultivation()
    state.goals["goal-1"].status = GoalStatus.ABANDONED

    assert list(own_aims(state, EN, Said(samples.CULTIVATION_PREMISE)).goals) == ["goal-1"]


def test_a_story_holds_back_what_the_players_words_never_named():
    # The bare premise names nobody and nothing that is coming: the rival, the elder and the
    # tournament's thread are all the story's to tell. A goal is never held back: the story
    # starts with the player's own alone (`own_aims`).
    state = _cultivation()
    assert kept_back(state, EN, Said(samples.CULTIVATION_PREMISE)) == [
        "person:elder-mo",
        "person:zhao",
        "thread:tournament",
    ]

    # A premise that names the tournament has named its thread, and one that calls the rival
    # by name has named him.
    spoken = "I must survive the ranking tournament, and Zhao Kun wants me gone before it."
    assert kept_back(state, EN, Said(spoken)) == ["person:elder-mo"]

    # A change they asked for counts as their words do, by the keys the draft kept of it.
    asked = Said(samples.CULTIVATION_PREMISE, frozenset({"person:elder-mo", "clock:tournament"}))
    assert kept_back(state, EN, asked) == ["person:zhao"]


def test_a_thread_is_named_by_the_question_it_carries():
    # "Someone inside the family killed my father" is the open question of the Naples thread,
    # which shows from the start. The two men don't.
    state = _naples()

    assert kept_back(state, EN, Said(samples.NAPLES_PREMISE)) == [
        "person:bartender",
        "person:carmine",
    ]
    # Someone the character doesn't know is never on the list: Memory doesn't show them anyway.
    state.characters["bartender"].known_by = []
    assert kept_back(state, EN, Said(samples.NAPLES_PREMISE)) == ["person:carmine"]


def test_a_scene_tells_what_its_own_words_name():
    # A story started before 2026-11-14 holds back the goal its drafter wrote, too.
    state = _holding(_cultivation(), samples.CULTIVATION_PREMISE, also=["goal:goal-1"])

    def told(scene: str) -> list[str]:
        return told_by(state, scene, EN)

    # A deadline's thread and the goal about it, by what they say or by a time set for it.
    dawn = "Dawn over the peak. The ranking tournament is two days away, and the court hums."
    assert told(dawn) == ["goal:goal-1", "thread:tournament"]
    assert told("In two days the tournament begins.") == ["thread:tournament"]
    assert told("In two days you fight.") == []
    # A person, by a name of their own inside a sentence, or by all of it at its start.
    assert told("A broad-shouldered senior kicks your bucket over. “Move,” says Zhao.") == [
        "person:zhao"
    ]
    assert told("Zhao Kun kicks your bucket over.") == ["person:zhao"]
    assert told("“Elder Mo is watching,” someone whispers.") == ["person:elder-mo"]
    # What only starts a sentence may be no name at all, and lower case never is one.
    assert told("Elder disciples laugh by the well. An elder dozes in the sun.") == []
    assert told("A senior brother shoves past you.") == []
    assert told("") == []
    # A story that holds nothing back is told nothing.
    assert told_by(_cultivation(), dawn, EN) == []


def test_what_a_place_or_a_faction_is_called_tells_of_nobody():
    state = _holding(_naples(), samples.NAPLES_PREMISE)

    # The scene opens in the bar that carries his name, among his crew: neither is him.
    assert told_by(state, "You push open the door of Carmine's bar.", EN) == []
    assert told_by(state, "Two men of Carmine’s crew look up from their cards.", EN) == []
    assert told_by(state, "You push open the door of Carmine's bar, and Carmine looks up.", EN) == [
        "person:carmine"
    ]
    assert told_by(state, "Behind the counter, Gennaro polishes a glass.", EN) == [
        "person:bartender"
    ]

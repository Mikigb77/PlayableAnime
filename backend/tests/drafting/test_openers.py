"""G1: the openers of a draft (its deadlines, questions, people, connections and goals), which
ones the player's own words name, and what a draft keeps of that. Every premise is made up."""

from engine.context import Language
from graph.drafting import samples
from graph.drafting.assemble import DraftOptions, assemble
from graph.drafting.openers import Said, carried, named_by, names, of_clock, openers, own_names

EN = Language.EN


def _state(proposal, premise):
    return assemble(proposal.world, proposal.character, DraftOptions(premise=premise))


def _naples():
    return _state(samples.naples(), samples.NAPLES_PREMISE)


def _cultivation():
    return _state(samples.cultivation(), samples.CULTIVATION_PREMISE)


def test_every_deadline_question_person_connection_and_goal_is_an_opener():
    keys = {opener.key for opener in openers(_naples())}

    assert {"clock:council", "person:carmine", "goal:find out who killed my father."} <= keys
    assert "connection:three loyal soldiers" in keys
    assert any(key.startswith("mystery:") for key in keys)


def test_words_name_openers_by_what_they_say_a_name_or_a_time_ahead():
    state = _cultivation()

    # The deadline, and the goal that is about it.
    assert named_by(state, "The ranking tournament is in two days.", EN) == {
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

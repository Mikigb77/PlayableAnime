"""Who sees a deed (W2). What is done by or to someone in the player character's scene is seen
by the people in the scene, not by everyone the record puts at the place: a place can be a
forest or a whole city, and being somewhere in it is not seeing what happens in one corner of
it. What is done before a crowd is public, and everyone there saw it."""

from engine.base import HOUR
from engine.contracts import ProposedDeed, Trip
from engine.samples import grounded_world
from engine.state import Character, Encounter, EncounterKind, PassingState, Visibility, WorldState
from engine.world import Kind
from engine.world.geography import onlookers, scene_ids

from .test_world import deed_step, idle, moved_on, pending_of, play, the_deed


def bar() -> WorldState:
    """Luca in the bar with Carmine and the bartender, as the last scene left it. The record
    also puts Nico at the bar, whom no scene has shown, and Rosa at the questura."""
    state = grounded_world()
    state.characters["nico"] = Character(id="nico", name="Nico Greco", location_id="bar")
    state.characters["rosa"] = Character(id="rosa", name="Rosa Marino", location_id="questura")
    return state


def punch(**more) -> ProposedDeed:
    return ProposedDeed(
        kind="punch", text="Luca punches Carmine", victim_ids=["carmine"], severity=2, **more
    )


def seen_by(state: WorldState, step) -> list[str]:
    return the_deed(play(state, step).state).witness_ids


def test_only_the_people_in_the_scene_see_what_is_done_there():
    after = play(bar(), deed_step(punch())).state

    deed = the_deed(after)
    assert deed.witness_ids == ["bartender", "carmine"]
    assert deed.visibility is Visibility.WITNESSED
    assert "nico" not in deed.known_by
    # Nico saw nothing, so he has nothing to report and feels as he did.
    assert not any(e.payload.get("witness_id") == "nico" for e in pending_of(after, Kind.REPORT))
    assert "luca" not in after.characters["nico"].sheet.disposition.attitudes


def test_with_nobody_else_in_the_scene_a_deed_is_secret_whoever_the_record_puts_there():
    state = bar()
    state.scene.present_ids = ["luca"]
    state.characters["carmine"].sheet.condition.states.append(PassingState(name="asleep"))

    deed = the_deed(play(state, deed_step(punch())).state)

    assert (deed.witness_ids, deed.visibility) == ([], Visibility.SECRET)


def test_whoever_the_deed_fell_on_saw_it_though_the_scene_never_listed_them():
    state = bar()
    state.scene.present_ids = ["luca"]

    assert seen_by(state, deed_step(punch())) == ["carmine"]
    # Someone it is aimed at and misses is there too.
    missed = ProposedDeed(kind="punch", text="Luca swings at Nico", target_ids=["nico"])
    assert seen_by(state, deed_step(missed)) == ["nico"]


def test_whoever_the_step_faced_or_made_real_is_in_the_scene():
    faced = deed_step(punch()).model_copy(update={"opponent_ids": ["nico"]})
    made = deed_step(punch()).model_copy(update={"strangers": ["nico"]})

    assert seen_by(bar(), faced) == ["bartender", "carmine", "nico"]
    assert seen_by(bar(), made) == ["bartender", "carmine", "nico"]


def test_those_in_the_scenes_fight_are_in_the_scene_whatever_its_end_listed():
    state = bar()
    state.scene.encounter = Encounter(
        kind=EncounterKind.FIGHT, opponent_ids=["nico"], started_turn=1, started_s=0
    )

    assert scene_ids(state) == ["luca", "carmine", "bartender", "nico"]
    assert seen_by(state, deed_step(punch())) == ["bartender", "carmine", "nico"]


def test_someone_struck_from_afar_is_not_there_to_see_who_did_it():
    letter = ProposedDeed(kind="poison", text="Luca has Rosa's wine poisoned", victim_ids=["rosa"])

    assert seen_by(bar(), deed_step(letter)) == ["bartender", "carmine"]
    assert [c.id for c in onlookers(bar(), "bar", ["luca", "rosa"])] == [
        "bartender",
        "carmine",
        "luca",
    ]


def test_where_no_scene_has_shown_who_is_around_everyone_there_saw_it():
    """The player character has only just walked in: nothing says who of the place is around
    them, so it is everyone the record puts there."""
    arrived = deed_step(punch()).model_copy(
        update={"trip": Trip(from_id="naples", to_id="bar", arrived=True)}
    )

    assert seen_by(bar(), arrived) == ["bartender", "carmine", "nico"]


def test_what_someone_does_elsewhere_is_seen_by_everyone_the_record_puts_there():
    state = bar()
    state.characters["ugo"] = Character(id="ugo", name="Ugo Bassi", location_id="questura")
    state.characters["pia"] = Character(id="pia", name="Pia Conti", location_id="questura")
    slap = ProposedDeed(kind="punch", text="Ugo punches Rosa", actor_id="ugo", victim_ids=["rosa"])

    after = play(state, deed_step(slap), actor_id="ugo").state

    assert the_deed(after).witness_ids == ["pia", "rosa"]


def test_what_others_do_at_the_same_place_outside_the_scene_is_not_seen_by_the_scene():
    """The bar is one place on the map. What Nico does to Ugo there while the scene is Luca's
    talk with Carmine is seen by whoever else the record puts there, and by nobody in the
    scene: no scene showed it, so Luca's memory doesn't hold it."""
    state = bar()
    state.characters["ugo"] = Character(id="ugo", name="Ugo Bassi", location_id="bar")
    state.characters["pia"] = Character(id="pia", name="Pia Conti", location_id="bar")
    slap = ProposedDeed(kind="punch", text="Nico punches Ugo", actor_id="nico", victim_ids=["ugo"])

    deed = the_deed(play(state, deed_step(slap), actor_id="nico").state)

    assert deed.witness_ids == ["pia", "ugo"]
    assert "luca" not in deed.known_by


def test_what_an_outsider_does_to_someone_in_the_scene_is_seen_by_the_scene():
    state = bar()
    slap = ProposedDeed(
        kind="punch", text="Nico punches Carmine", actor_id="nico", victim_ids=["carmine"]
    )

    deed = the_deed(play(state, deed_step(slap), actor_id="nico").state)

    assert deed.witness_ids == ["bartender", "carmine", "luca"]


def test_what_is_done_before_a_crowd_is_public_and_everyone_there_saw_it():
    """A crowd is the people the scene doesn't name. Everyone the record puts there is one of
    them, word starts at once, and it is told as it happened."""
    after = play(bar(), deed_step(punch(visibility=Visibility.PUBLIC))).state

    deed = the_deed(after)
    assert deed.visibility is Visibility.PUBLIC
    assert deed.witness_ids == ["bartender", "carmine", "nico"]
    (rumor,) = after.rumors.values()
    assert (rumor.deed_id, rumor.accuracy) == (deed.id, 100)
    assert sorted(rumor.heard_at) == ["bartender", "carmine", "nico"]
    # Seen by a few and not public, nobody speaks of the same punch while Luca stands there.
    # Once he has moved on they do, less exactly, and to Nico too.
    seen = play(bar(), deed_step(punch())).state
    assert seen.rumors == {} and the_deed(seen).word_out_s is None
    later, _ = idle(moved_on(seen), seen.world_s + HOUR)
    (told,) = later.rumors.values()
    first = [c for c, heard_s in told.heard_at.items() if heard_s == the_deed(later).word_out_s]
    assert told.accuracy < 100 and sorted(first) == ["bartender", "carmine", "nico"]

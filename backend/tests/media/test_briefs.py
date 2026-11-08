"""Who a scene picture shows: the people its description names, the subject first (M1, M5)."""

from engine.samples import grounded_world
from engine.state.cast import Character, CharacterStatus, DeathCertainty, Prominence
from engine.state.records import Deed, Fallen
from engine.state.sheet import Item, ItemKind
from media.briefs import (
    belongings,
    figure,
    known_cast,
    names,
    player_at,
    scene_figures,
    time_of_day,
)

# grounded_world(): Luca Esposito is the player, at the bar with Carmine Russo, whom he knows, and
# Gennaro the bartender, whom he doesn't.


def _ids(figures):
    return [f.id for f in figures]


def _with_stranger(state, *, dead=False):
    stranger = Character(
        id="sal",
        name="Sal the Knife",
        prominence=Prominence.KEY,
        appearance="Thin, a white suit, a gold tooth.",
        location_id="bar",
    )
    if dead:
        stranger.status = CharacterStatus.DEAD
        stranger.death_certainty = DeathCertainty.CONFIRMED
    state.characters["sal"] = stranger
    state.scene.present_ids = [*state.scene.present_ids, "sal"]
    return state


def test_only_the_people_the_description_names_are_in_it():
    state = grounded_world()

    shown = scene_figures(state, "Carmine slams the ledger on the bar.")

    # Not Luca, who isn't in this moment, and not the bartender.
    assert _ids(shown) == ["carmine"]
    assert shown[0].appearance == "Fifties, broad, grey moustache, gold rings."


def test_you_puts_the_player_character_in_it_first():
    state = grounded_world()

    shown = scene_figures(state, "Carmine leans in close to you, smiling.")

    assert _ids(shown) == ["luca", "carmine"]


def test_the_player_character_is_in_it_when_named():
    state = grounded_world()

    assert _ids(scene_figures(state, "Luca and Gennaro trade a look.")) == ["luca", "bartender"]


def test_the_subject_comes_first_even_dead_or_never_met():
    """A key character who dies, or a foe felled by the decisive blow, is no longer alive at the
    scene's end, and a foe may be a stranger: the picture is still theirs (M1)."""
    state = _with_stranger(grounded_world(), dead=True)
    assert "sal" not in [c.id for c in known_cast(state)]

    shown = scene_figures(state, "Sal falls across the pool table.", subject_id="sal")

    assert _ids(shown) == ["sal"]
    assert shown[0].appearance == "Thin, a white suit, a gold tooth."


def test_a_subject_named_by_no_one_still_leads_the_fallback():
    state = _with_stranger(grounded_world())

    shown = scene_figures(state, "The last blow lands in the smoke.", subject_id="sal")

    # Nobody named: the subject, then the player and the people the player knows, as before.
    assert _ids(shown) == ["sal", "luca", "carmine"]


def test_a_description_that_names_no_one_keeps_the_known_cast():
    state = grounded_world()

    assert _ids(scene_figures(state, "Smoke curls under the lamps.")) == ["luca", "carmine"]


def test_a_deed_is_pictured_with_its_doer_and_the_people_named():
    state = _with_stranger(grounded_world())
    state.deeds["d1"] = Deed(
        id="d1", actor_id="luca", kind="kill", text="Luca shoots Sal.", turn=3, world_s=60,
        victim_ids=["sal"],
    )  # fmt: skip

    shown = scene_figures(state, "Sal reels back from the shot.", subject_id="d1")

    assert _ids(shown) == ["luca", "sal"]


def test_a_thread_or_unknown_subject_adds_no_one():
    state = grounded_world()

    assert _ids(scene_figures(state, "Carmine smiles.", subject_id="the_council")) == ["carmine"]


def test_at_most_four_people_are_described():
    state = grounded_world()
    for n in range(5):
        state.characters[f"guard{n}"] = Character(id=f"guard{n}", name=f"Guard Number{n}")
        state.scene.present_ids.append(f"guard{n}")
    text = "You face " + ", ".join(f"Number{n}" for n in range(5)) + "."

    assert len(scene_figures(state, text)) == 4


def test_names_match_whole_names_aliases_and_capitalised_words():
    state = grounded_world()
    carmine = state.characters["carmine"]
    carmine.aliases = ["the underboss"]

    assert names("Carmine Russo waits.", carmine)
    assert names("Russo waits.", carmine)
    assert names("The Underboss waits.", carmine)
    assert not names("Carmineo waits.", carmine)  # never inside a longer word
    assert not names("russo is a common word here.", carmine)  # a lone word needs its capital
    mei = Character(id="mei", name="Mei of the Willows")
    assert names("Mei bows.", mei)
    assert not names("The river runs.", mei)  # "the" and "of" say nothing alone


def test_an_illustrated_past_scene_uses_its_own_cast_and_player():
    """N6: after a story is carried on as someone else, a scene from before shows its own player
    character, and Illustrate's cast is the one saved with that scene."""
    state = _with_stranger(grounded_world())
    state.fallen = [
        Fallen(
            character_id="luca", name="Luca Esposito", ending="death", turn=5, world_s=100,
            successor_id="sal",
        )
    ]  # fmt: skip
    state.player_id = "sal"

    assert player_at(state, 3) == "luca"
    assert player_at(state, 5) == "luca"
    assert player_at(state, 6) == "sal"
    shown = scene_figures(state, "Nobody speaks.", player_id="luca", present=["carmine"])
    assert _ids(shown) == ["luca", "carmine"]


def test_the_time_of_day_comes_from_the_worlds_clock():
    calendar = grounded_world().bible.calendar  # opens at 21:00

    assert time_of_day(calendar, 0) == "evening"
    assert time_of_day(calendar, 2 * 3600) == "night"
    assert time_of_day(calendar, 10 * 3600) == "morning"


def test_a_figure_falls_back_on_the_description():
    gennaro = grounded_world().characters["bartender"]

    assert figure(gennaro).appearance == gennaro.description


def test_a_figure_has_the_age_the_story_gives_them():
    """S7: everyone is drawn as old as they are now, so the age goes with them, or none."""
    state = grounded_world()
    luca = state.characters[state.player_id]
    luca.age = 25

    assert figure(luca).age == 25
    state.characters["bartender"].age = None
    assert figure(state.characters["bartender"]).age is None


def test_the_player_character_goes_in_with_what_they_carry():
    """C10: what Luca has on him, from the record, and nothing he keeps elsewhere, such as his
    car. Carmine's belongings are on record only as far as the story told them, so the picture
    isn't told his."""
    state = grounded_world()

    shown = scene_figures(state, "Carmine leans in close to you, smiling.")

    assert [(f.id, f.carries) for f in shown] == [
        ("luca", ("Beretta pistol", "flick knife")),
        ("carmine", None),
    ]
    # A past scene, which the record of now can't speak for (Illustrate).
    past = scene_figures(
        state, "Carmine leans in close to you.", present=["carmine"], carried=False
    )
    assert [f.carries for f in past] == [None, None]


def test_belongings_are_what_is_on_them_with_how_many():
    state = grounded_world()
    luca = state.player
    luca.sheet.resources.items = [
        Item(id="knives", name="throwing knives", kind=ItemKind.WEAPON, quantity=3),
        Item(id="coins", name="12 copper coins", kind=ItemKind.TREASURE, quantity=12),
        # Named for the count it started with: the count on record is what goes.
        Item(id="arrows", name="3 arrows", kind=ItemKind.WEAPON, quantity=20),
        Item(id="spent", name="smoke bomb", kind=ItemKind.CONSUMABLE, quantity=0),
        Item(id="robe", name="spare robe", carried=False),
        Item(id="house", name="the old house", kind=ItemKind.PROPERTY),
        Item(id="horse", name="grey mare", kind=ItemKind.VEHICLE),
    ]

    assert belongings(luca) == ("3 throwing knives", "12 copper coins", "20 arrows")
    luca.sheet.resources.items = []
    assert belongings(luca) == ()
    assert figure(luca).carries is None  # only a picture's player character is told

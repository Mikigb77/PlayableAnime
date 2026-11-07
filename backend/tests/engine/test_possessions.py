"""C10: what everyone has, gains and loses. Every change moves a thing from someone to someone,
nobody gives what they don't have, and a loss is never forgotten (Miki, 2026-11-07: Milo stole the
player's 12 copper coins, and later scenes still let the player pay with them)."""

from engine import possessions
from engine.apply import DeltaSource, apply_delta
from engine.context import TurnContext
from engine.contracts import CharacterChange, ItemChange, StateDelta
from engine.samples import grounded_world
from engine.state import Character, CharacterSheet, Item, ItemKind, Resources, WorldState

ENGINE = DeltaSource.ENGINE
NARRATOR = DeltaSource.NARRATOR


def ctx(turn: int = 3) -> TurnContext:
    return TurnContext(story_id="s1", turn=turn)


def street(money: int = 12, currency: str = "copper coins") -> WorldState:
    """Luca with a purse of coins, and Milo, a pickpocket, beside him."""
    state = grounded_world()
    purse = state.player.sheet.resources
    purse.money, purse.currency = money, currency
    milo = Character(
        id="milo",
        name="Milo",
        description="A quick-fingered street kid.",
        age=19,
        location_id="bar",
        known_by=["luca"],
        met_by=["luca"],
        sheet=CharacterSheet(),
    )
    state.characters["milo"] = milo
    state.scene.present_ids.append("milo")
    return state


def move(state: WorldState, *changes: ItemChange, source=NARRATOR, turn: int = 3):
    return apply_delta(state, StateDelta(items=list(changes)), ctx(turn), source=source)


def purse(state: WorldState, character_id: str) -> tuple[int, str]:
    resources = state.characters[character_id].sheet.resources
    return resources.money, resources.currency


def names(state: WorldState, character_id: str) -> dict[str, int]:
    return {i.name: i.quantity for i in state.characters[character_id].sheet.resources.items}


def test_a_theft_moves_the_coins_to_the_thief_and_the_player_has_none_left():
    # The narrator wrote the coins as an item, as it did in Miki's story: they are still money.
    stolen = move(
        street(), ItemChange(name="12 copper coins", from_id="luca", to_id="milo", how="stolen")
    )

    assert not stolen.rejected
    assert purse(stolen.state, "luca") == (0, "copper coins")
    assert purse(stolen.state, "milo") == (12, "copper coins")
    (record,) = stolen.state.transfers
    assert (record.from_id, record.to_id, record.quantity, record.money) == (
        "luca",
        "milo",
        12,
        True,
    )
    assert record.how == "stolen" and record.turn == 3
    assert {"luca", "milo"} <= set(record.known_by)


def test_nobody_pays_with_coins_they_no_longer_have():
    stolen = move(
        street(), ItemChange(name="copper coins", quantity=12, from_id="luca", to_id="milo")
    )

    paid = move(
        stolen.state,
        ItemChange(name="copper coins", money=True, quantity=12, from_id="luca", to_id="milo"),
    )

    assert [r.reason for r in paid.rejected] == ["they don't have it"]
    assert purse(paid.state, "milo") == (12, "copper coins")  # never 24
    assert len(paid.state.transfers) == 1


def test_a_loss_is_cut_to_what_the_player_character_holds():
    taken = move(
        street(money=5),
        ItemChange(name="coins", money=True, quantity=20, from_id="luca", to_id="milo"),
    )

    assert purse(taken.state, "luca") == (0, "copper coins")
    assert purse(taken.state, "milo") == (5, "copper coins")
    assert taken.state.transfers[-1].quantity == 5


def test_someone_else_can_hand_over_what_the_story_never_listed():
    # N7: a character's belongings are on record only as far as the story told them.
    given = move(street(), ItemChange(name="a rusty key", from_id="milo", to_id="luca"))

    assert not given.rejected
    assert names(given.state, "luca")["rusty key"] == 1


def test_what_someone_got_from_the_player_goes_down_when_they_hand_it_back():
    stolen = move(
        street(), ItemChange(name="copper coins", quantity=12, from_id="luca", to_id="milo")
    )

    back = move(
        stolen.state,
        ItemChange(name="copper coins", money=True, quantity=12, from_id="milo", to_id="luca"),
    )

    assert purse(back.state, "luca") == (12, "copper coins")
    assert purse(back.state, "milo") == (0, "copper coins")


def test_an_item_is_never_in_two_places():
    given = move(
        street(), ItemChange(name="the pistol", item_id="pistol", from_id="luca", to_id="milo")
    )

    assert "Beretta pistol" not in names(given.state, "luca")
    assert names(given.state, "milo") == {"Beretta pistol": 1}
    assert given.state.characters["milo"].sheet.item("pistol") is not None
    # Someone who doesn't hold it can't give it, while someone else has it.
    again = move(
        given.state, ItemChange(name="pistol", item_id="pistol", from_id="carmine", to_id="luca")
    )
    assert [r.reason for r in again.rejected] == ["someone else has it"]


def test_the_player_character_loses_only_what_they_carry_by_its_name_or_its_words():
    used = move(street(), ItemChange(name="the knife", from_id="luca", to_id="world", how="lost"))
    missing = move(street(), ItemChange(name="a grenade", from_id="luca", to_id="world"))

    assert "flick knife" not in names(used.state, "luca")
    assert used.state.transfers[-1].to_id is None
    assert [r.reason for r in missing.rejected] == ["they don't have it"]


def test_money_in_a_currency_they_dont_count_in_is_kept_as_it_is():
    state = street()
    state.characters["milo"].sheet.resources = Resources(money=3, currency="silver crowns")

    paid = move(
        state,
        ItemChange(name="silver crowns", money=True, quantity=3, from_id="milo", to_id="luca"),
    )

    assert purse(paid.state, "luca") == (12, "copper coins")
    coins = next(i for i in paid.state.player.sheet.resources.items if i.name == "silver crowns")
    assert (coins.quantity, coins.kind) == (3, ItemKind.TREASURE)


def test_money_found_by_someone_with_none_starts_their_purse():
    state = street(money=0, currency="")

    found = move(
        state,
        ItemChange(name="5 silver coins", money=True, quantity=5, from_id="world", to_id="luca"),
    )

    assert purse(found.state, "luca") == (5, "silver coins")


def test_the_same_holder_on_both_sides_only_restyles_it():
    left = move(
        street(),
        ItemChange(name="pistol", item_id="pistol", from_id="luca", to_id="luca", carried=False),
    )

    assert not left.rejected and not left.state.transfers
    assert left.state.player.sheet.item("pistol").carried is False


def test_changes_that_name_nobody_are_refused():
    state = street()

    refused = move(
        state,
        ItemChange(name="coins", from_id="ghost", to_id="luca"),
        ItemChange(name="coins", from_id="world", to_id="world"),
        ItemChange(name="coins", quantity=0, from_id="luca", to_id="milo"),
    )

    assert [r.reason for r in refused.rejected] == [
        "no such character",
        "nothing changes hands",
        "nothing changes hands",
    ]
    assert purse(refused.state, "luca") == (12, "copper coins")


def test_a_new_character_in_the_same_scene_can_take_something():
    thief = CharacterChange(id="cutpurse", name="A cutpurse", description="Thin, fast.")
    delta = StateDelta(
        characters=[thief],
        items=[ItemChange(name="money", money=True, quantity=4, from_id="luca", to_id="cutpurse")],
    )

    applied = apply_delta(street(), delta, ctx(), source=NARRATOR)

    assert not applied.rejected
    assert purse(applied.state, "cutpurse") == (4, "copper coins")


def test_only_the_latest_transfers_are_kept():
    state = street(money=1000)
    changes = [
        ItemChange(name="coins", money=True, quantity=1, from_id="luca", to_id="milo")
        for _ in range(possessions.TRANSFERS_KEPT + 5)
    ]

    moved = move(state, *changes)

    assert len(moved.state.transfers) == possessions.TRANSFERS_KEPT
    assert purse(moved.state, "milo")[0] == possessions.TRANSFERS_KEPT + 5


def test_the_models_read_where_the_coins_went():
    stolen = move(
        street(), ItemChange(name="12 copper coins", from_id="luca", to_id="milo", how="stolen")
    )

    assert possessions.prompt_lines(stolen.state) == [
        "12 copper coins went from you to Milo (milo), stolen, moments ago."
    ]


def test_words_decide_what_counts_as_money():
    assert possessions.is_money("12 copper coins", "copper coins")
    assert possessions.is_money("coins", "copper coins")
    assert possessions.is_money("money", "lire")
    assert possessions.is_money("monedas", "")
    assert not possessions.is_money("gold coins", "copper coins")
    assert not possessions.is_money("a purse", "copper coins")
    assert possessions.bare("12 copper coins") == "copper coins"
    assert possessions.bare("the rusty key") == "rusty key"
    assert possessions.count("12 copper coins", 1) == 12
    assert possessions.count("12 copper coins", 3) == 3
    assert possessions.count("copper coins", -5) == 5
    assert possessions.count("1,000 lire", 1) == 1000
    assert possessions.count("a key", 1) == 1


def test_coins_kept_as_an_item_are_used_when_the_purse_is_empty():
    state = street(money=0)
    state.player.sheet.resources.items.append(
        Item(id="coins", name="copper coins", kind=ItemKind.TREASURE, quantity=7)
    )

    paid = move(
        state,
        ItemChange(name="copper coins", money=True, quantity=7, from_id="luca", to_id="milo"),
    )

    assert not paid.rejected
    assert "copper coins" not in names(paid.state, "luca")
    assert names(paid.state, "milo") == {"copper coins": 7}

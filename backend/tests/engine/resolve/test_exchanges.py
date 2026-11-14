"""C10, R2: a step that pays, gives or uses up something is checked against what the character
holds before it is tried, and what it moves is the engine's own change, applied before anything is
told. The case behind it (Miki, 2026-11-07): Milo stole the player's 12 copper coins, and a later
scene let the player pay him with them again."""

from engine import pipeline
from engine.apply import DeltaSource, apply_delta
from engine.contracts import (
    ActionKind,
    Beat,
    BeatUse,
    BeatVerdict,
    Exchange,
    ExchangeKind,
    Intent,
    ItemChange,
    OutcomeClass,
    Plausibility,
    SheetPart,
    SheetUse,
    StateDelta,
    StopReason,
    UseSource,
)
from engine.samples import grounded_world
from engine.state import Character, CharacterSheet, Item, StepResult, WorldState

from .worlds import SEEDS, ctx, facts, resolve, rng, step


def street(money: int = 12) -> WorldState:
    state = grounded_world()
    resources = state.player.sheet.resources
    resources.money, resources.currency = money, "copper coins"
    state.characters["milo"] = Character(
        id="milo",
        name="Milo",
        description="A quick-fingered street kid.",
        age=19,
        location_id="bar",
        known_by=["luca"],
        met_by=["luca"],
        sheet=CharacterSheet(),
    )
    state.scene.present_ids.append("milo")
    return state


def robbed() -> WorldState:
    """Milo has taken all twelve coins."""
    theft = ItemChange(name="12 copper coins", from_id="luca", to_id="milo", how="stolen")
    applied = apply_delta(street(), StateDelta(items=[theft]), ctx(), source=DeltaSource.NARRATOR)
    assert not applied.rejected
    return applied.state


def pay(amount: int = 12, to: str = "milo", **kw) -> Exchange:
    return Exchange(
        kind=ExchangeKind.GIVE,
        thing=f"{amount} copper coins",
        money=True,
        amount=amount,
        with_id=to,
        **kw,
    )


def paying(*exchanges: Exchange, text: str = "pay Milo for the lesson"):
    return step(text, ActionKind.INSTANT, 3, verb="pay", exchanges=list(exchanges))


def test_paying_with_coins_that_were_stolen_is_ruled_out_and_says_where_they_went():
    intent = Intent(
        steps=[paying(pay(to="carmine"), text="pay Carmine"), step("leave", ActionKind.MOVE, 20)]
    )

    resolution = resolve(robbed(), intent)

    (settled,) = resolution.steps
    assert (settled.outcome_class, settled.result) == (OutcomeClass.RULED_OUT, StepResult.FAILURE)
    assert settled.roll is None
    assert settled.reason == "You have no copper coins. They went to Milo."
    assert settled.effects.items == []
    assert resolution.stop_reason is StopReason.RULED_OUT


def test_letting_milo_keep_what_he_took_moves_nothing_and_never_fails():
    intent = Intent(steps=[paying(pay(), text="tell Milo to keep the coins as payment")])

    (settled,) = resolve(robbed(), intent).steps

    assert settled.outcome_class is not OutcomeClass.RULED_OUT
    assert settled.result is StepResult.SUCCESS
    assert settled.effects.items == []


def test_letting_milo_keep_his_haul_never_tops_it_up_from_new_coins():
    state = robbed()
    state.player.sheet.resources.money = 5  # earned since
    intent = Intent(steps=[paying(pay(), text="tell Milo to keep the 12 coins as payment")])

    (settled,) = resolve(state, intent).steps

    assert settled.result is StepResult.SUCCESS
    assert settled.effects.items == []


def test_a_payment_that_works_moves_the_coins_before_the_scene_is_told():
    state = street()
    intent = Intent(steps=[paying(pay(5))])

    resolution = resolve(state, intent)
    played = pipeline.play_out(state, resolution, ctx(), rng())

    (move,) = resolution.steps[0].effects.items
    assert (move.from_id, move.to_id, move.quantity, move.money) == ("luca", "milo", 5, True)
    assert played.state.player.sheet.resources.money == 7
    assert played.state.characters["milo"].sheet.resources.money == 5
    assert played.state.transfers[-1].how == "pay"


def test_paying_more_than_the_purse_holds_says_how_much_there_is():
    (settled,) = resolve(street(money=5), Intent(steps=[paying(pay(12))])).steps

    assert settled.outcome_class is OutcomeClass.RULED_OUT
    assert settled.reason == "You have only 5 copper coins."


def test_a_plan_cant_spend_the_same_coins_twice():
    intent = Intent(
        steps=[
            paying(pay(8), text="pay Milo"),
            paying(pay(8, to="carmine"), text="pay Carmine"),
        ]
    )

    resolution = resolve(street(), intent)

    first, second = resolution.steps
    assert first.result is StepResult.SUCCESS and first.effects.items[0].quantity == 8
    assert second.outcome_class is OutcomeClass.RULED_OUT
    assert second.reason == "You have only 4 copper coins."


def test_a_bribe_that_fails_keeps_the_coins_but_a_thrown_knife_is_gone_whatever_happens():
    bribe = step(
        "bribe Carmine to look away",
        ActionKind.CONVERSATION,
        30,
        verb="bribe",
        target_ids=["carmine"],
        facts=facts(opposition_ids=["carmine"], can_respond=True, challenge="hard"),
        exchanges=[pay(5, to="carmine")],
    )
    throw = step(
        "throw the knife at Carmine",
        verb="throw",
        target_ids=["carmine"],
        facts=facts(opposition_ids=["carmine"], can_respond=True, challenge="hard"),
        exchanges=[Exchange(kind=ExchangeKind.SPEND, thing="flick knife", item_id="knife")],
    )

    bribes = [resolve(street(), Intent(steps=[bribe]), seed).steps[0] for seed in SEEDS]
    throws = [resolve(street(), Intent(steps=[throw]), seed).steps[0] for seed in SEEDS]

    failed = [s for s in bribes if s.result is StepResult.FAILURE]
    worked = [s for s in bribes if s.result is not StepResult.FAILURE]
    assert failed and worked
    assert all(s.effects.items == [] for s in failed)
    assert all(s.effects.items[0].to_id == "carmine" for s in worked)
    missed = [s for s in throws if s.result is StepResult.FAILURE]
    assert missed
    assert all(s.effects.items[0].to_id == "world" for s in missed)


def test_taking_back_what_milo_holds_moves_it_to_the_player():
    take = step(
        "snatch my coins back from Milo",
        verb="snatch",
        exchanges=[
            Exchange(
                kind=ExchangeKind.TAKE, thing="copper coins", money=True, amount=0, with_id="milo"
            )
        ],
    )
    state = robbed()

    resolution = resolve(state, Intent(steps=[take]))
    played = pipeline.play_out(state, resolution, ctx(), rng())

    (move,) = resolution.steps[0].effects.items
    assert (move.from_id, move.to_id, move.quantity) == ("milo", "luca", 12)
    assert played.state.player.sheet.resources.money == 12
    assert played.state.characters["milo"].sheet.resources.money == 0


def test_a_beat_that_reaches_for_money_checks_the_purse():
    beat = Beat(
        text="count out the coins",
        uses=[BeatUse(source=UseSource.CARRIED, thing="copper coins")],
    )
    counting = step("count out the coins", ActionKind.INSTANT, 3, beats=[beat])

    (held,) = resolve(street(), Intent(steps=[counting])).steps
    (gone,) = resolve(robbed(), Intent(steps=[counting])).steps

    assert held.beats[0].verdict is BeatVerdict.HOLDS and held.result is StepResult.SUCCESS
    assert gone.beats[0].verdict is BeatVerdict.EMPTY
    assert gone.reason == "You have no copper coins left. They went to Milo."


def test_money_named_as_an_item_on_the_step_is_the_purse():
    counting = step(
        "flash the coins", ActionKind.INSTANT, 3, uses=[SheetUse(part=SheetPart.ITEM, ref="coins")]
    )

    (held,) = resolve(street(), Intent(steps=[counting])).steps
    (gone,) = resolve(robbed(), Intent(steps=[counting])).steps

    assert held.outcome_class is not OutcomeClass.RULED_OUT
    assert gone.outcome_class is OutcomeClass.RULED_OUT
    assert gone.reason == "You have no copper coins left. They went to Milo."


def test_an_old_payment_never_covers_a_new_one_the_purse_cant():
    state = street(money=20)
    first = apply_delta(
        state,
        StateDelta(
            items=[ItemChange(name="coins", money=True, quantity=3, from_id="luca", to_id="milo")]
        ),
        ctx(),
        source=DeltaSource.NARRATOR,
    ).state

    (settled,) = resolve(first, Intent(steps=[paying(pay(1000))])).steps

    assert settled.outcome_class is OutcomeClass.RULED_OUT
    assert settled.reason == "You have only 17 copper coins."


def test_two_payments_in_one_step_must_both_fit_the_purse():
    both = paying(pay(5), pay(5, to="carmine"), text="pay Milo and Carmine five each")

    (short,) = resolve(street(money=6), Intent(steps=[both])).steps
    (paid,) = resolve(street(money=10), Intent(steps=[both])).steps

    assert short.outcome_class is OutcomeClass.RULED_OUT
    assert short.reason == "You have only one of your copper coins left."
    assert [(m.to_id, m.quantity) for m in paid.effects.items] == [("milo", 5), ("carmine", 5)]


def pouring(*uses: BeatUse, thing: str = "a glass of grappa", to: str = "milo"):
    """Handing Milo a drink, as a reading may file it: a gift, with the beats it takes."""
    gift = Exchange(kind=ExchangeKind.GIVE, thing=thing, with_id=to)
    beats = [Beat(text="pour it and hold it out", uses=list(uses))] if uses else []
    return step(
        "pour Milo a drink", ActionKind.INSTANT, 20, verb="give", exchanges=[gift], beats=beats
    )


def of_the_place(thing: str = "a glass of grappa", plausibility=Plausibility.PLAUSIBLE):
    return BeatUse(source=UseSource.NEW, thing=thing, plausibility=plausibility)


def test_a_drink_poured_for_a_guest_is_the_places_and_never_fails_for_want_of_it():
    """In play (2026-11-14) a fisherman poured a frightened neighbour a glass of brandy in his
    own kitchen, as the scene before had offered. He was told "You have no glass of brandy",
    and the question he asked with it was never played: no sheet lists what a kitchen holds."""
    asking = step("ask Milo what happened", ActionKind.CONVERSATION, 60, verb="ask")

    played = resolve(street(), Intent(steps=[pouring(of_the_place()), asking]))

    poured, asked = played.steps
    assert poured.outcome_class is not OutcomeClass.RULED_OUT
    assert poured.beats[0].verdict is BeatVerdict.MADE_CANON
    assert poured.effects.items == []  # nothing of theirs moved
    assert asked.outcome_class is not OutcomeClass.RULED_OUT


def test_whether_a_thing_of_the_place_is_there_is_the_beats_to_say():
    absent = of_the_place(plausibility=Plausibility.ABSENT)

    (missing,) = resolve(street(), Intent(steps=[pouring(absent)])).steps

    assert missing.beats[0].verdict is BeatVerdict.EMPTY
    assert missing.reason == "There is no glass of grappa to be found here."


def test_a_gift_no_beat_reaches_for_in_the_place_must_be_theirs():
    (bare,) = resolve(street(), Intent(steps=[pouring()])).steps
    carried = BeatUse(source=UseSource.CARRIED, thing="a glass of grappa")
    (claimed,) = resolve(street(), Intent(steps=[pouring(carried)])).steps

    assert bare.outcome_class is OutcomeClass.RULED_OUT
    assert bare.reason == "You have no glass of grappa."
    assert claimed.outcome_class is OutcomeClass.RULED_OUT


def test_money_and_what_was_theirs_or_is_someone_elses_is_never_the_places_to_give():
    # Coins on the table are still the purse's to pay.
    coins = pay(to="carmine")
    paid = step(
        "pay Carmine",
        ActionKind.INSTANT,
        3,
        exchanges=[coins],
        beats=[Beat(text="slide the coins over", uses=[of_the_place("12 copper coins")])],
    )
    (short,) = resolve(robbed(), Intent(steps=[paid])).steps
    assert short.reason == "You have no copper coins. They went to Milo."

    # What Milo holds has to be taken from him before it is given away.
    state = street()
    state.characters["milo"].sheet.resources.items.append(Item(id="ring", name="silver ring"))
    ring = of_the_place("the silver ring")
    (his,) = resolve(
        state, Intent(steps=[pouring(ring, thing="the silver ring", to="carmine")])
    ).steps
    assert his.outcome_class is OutcomeClass.RULED_OUT and his.reason == "You have no silver ring."


def buying(*, price: int = 12, seller: str | None = None):
    """Buying a healing draught: a give of the price and a take of the thing (C10)."""
    paid = Exchange(kind=ExchangeKind.GIVE, thing=f"{price} copper coins", money=True, amount=price)
    got = Exchange(kind=ExchangeKind.TAKE, thing="a healing draught", with_id=seller)
    return step(
        "buy a healing draught at the market", ActionKind.INSTANT, 60, exchanges=[paid, got]
    )


def test_what_is_bought_from_a_seller_nobody_named_arrives_with_its_price():
    """In play (2026-11-14) a cultivator paid his last spirit stones for a pill at a market.
    The stones left his purse and the pill never reached his belongings."""
    state = street()

    resolution = resolve(state, Intent(steps=[buying()]))
    played = pipeline.play_out(state, resolution, ctx(), rng())

    (bought,) = resolution.steps
    assert [(c.name, c.from_id, c.to_id) for c in bought.effects.items] == [
        ("12 copper coins", "luca", "world"),
        ("a healing draught", "world", "luca"),
    ]
    after = played.state.player.sheet.resources
    assert after.money == 0
    assert [(i.name, i.quantity) for i in after.items if "draught" in i.name] == [
        ("healing draught", 1)
    ]


def test_what_is_taken_with_nothing_paid_is_still_the_scenes_to_tell():
    found = Exchange(kind=ExchangeKind.TAKE, thing="a healing draught")
    taking = step("take a draught off the stall", ActionKind.INSTANT, 5, exchanges=[found])

    (taken,) = resolve(street(), Intent(steps=[taking])).steps

    assert taken.effects.items == []


def test_a_purchase_the_purse_cant_pay_buys_nothing():
    (short,) = resolve(street(money=5), Intent(steps=[buying()])).steps

    assert short.outcome_class is OutcomeClass.RULED_OUT
    assert short.reason == "You have only 5 copper coins."
    assert short.effects.items == []

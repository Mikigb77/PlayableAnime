"""C10, R2: what a step pays, gives, spends or takes, checked before the step is tried and moved by
the engine when it works, so the narrator never shows the character paying with money or handing
over something they don't hold.

- **Before the step.** Everything the actor gives or spends must be theirs, counting what earlier
  steps of the same plan moved: short of it, the step is ruled out with no roll, and the reason
  says where it went ("You have no copper coins. They went to Milo."). Letting someone keep what
  they already took from the actor moves nothing, so it never fails for want of it.
- **When it works.** What is given or taken moves on a success or a partial success; what is
  spent is gone whenever the step is tried, since a thrown knife leaves the hand whether it hits
  or not. Each move is an `ItemChange` in the step's effects, applied by `engine.possessions`
  before narration (F4), and the narrator is told it happened.
"""

from engine.contracts.delta import WORLD, ItemChange
from engine.contracts.intent import Exchange, ExchangeKind, IntentStep, OutcomeClass
from engine.possessions import already_given, bare, count, gone_to, holding, is_money
from engine.resolve.checks import Settled
from engine.resolve.words import cap, name, possessive
from engine.state.cast import Character
from engine.state.records import StepResult
from engine.state.world import WorldState

_WHERE_IT_STANDS = ("vehicle", "property")


def check(
    state: WorldState, actor: Character, step: IntentStep, moved: list[ItemChange]
) -> Settled | None:
    """The step settled at once when the actor doesn't hold what it gives or spends."""
    for exchange in step.exchanges:
        if exchange.kind is ExchangeKind.TAKE:
            continue
        held = _held(actor, exchange, moved)
        need = count(exchange.thing, exchange.amount) or 1  # all of it needs something
        found = holding(actor, exchange.thing, money=exchange.money, item_id=exchange.item_id)
        away = (
            found.item is not None
            and not found.item.carried
            and found.item.kind.value not in _WHERE_IT_STANDS
        )
        if held >= need and not away:
            continue
        if _kept(state, actor, exchange):
            continue  # they already have it: letting them keep it moves nothing
        return Settled(
            OutcomeClass.RULED_OUT, StepResult.FAILURE, _short(state, actor, exchange, held, away)
        )
    return None


def changes(
    state: WorldState,
    actor: Character,
    step: IntentStep,
    outcome_class: OutcomeClass,
    result: StepResult,
    moved: list[ItemChange],
) -> list[ItemChange]:
    """What the settled step moves: given and taken on a success or a partial success, spent
    whenever it was tried."""
    if outcome_class is OutcomeClass.RULED_OUT:
        return []
    works = result is not StepResult.FAILURE
    out: list[ItemChange] = []
    for exchange in step.exchanges:
        if exchange.kind is not ExchangeKind.SPEND and not works:
            continue
        change = _change(state, actor, step, exchange, [*moved, *out])
        if change is not None:
            out.append(change)
    return out


def _change(
    state: WorldState,
    actor: Character,
    step: IntentStep,
    exchange: Exchange,
    moved: list[ItemChange],
) -> ItemChange | None:
    money = _money(actor, exchange)
    how = " ".join(step.verb.split())[:60]
    if exchange.kind is ExchangeKind.TAKE:
        other = state.characters.get(exchange.with_id or "")
        if other is None or other.id == actor.id:
            return None  # what the world holds is found by the beats, and told by the narrator
        amount = count(exchange.thing, exchange.amount)
        if amount <= 0:
            amount = holding(other, exchange.thing, money=money, item_id=exchange.item_id).amount
        if amount <= 0:
            return None  # all of something nobody counted: the narrator tells what it was
        return ItemChange(
            name=exchange.thing,
            from_id=other.id,
            to_id=actor.id,
            money=money,
            quantity=amount,
            item_id=exchange.item_id,
            how=how,
        )
    held = _held(actor, exchange, moved)
    wanted = count(exchange.thing, exchange.amount)
    if held < max(wanted, 1) and _kept(state, actor, exchange):
        return None  # a payment someone already holds: never topped up from what is left
    amount = min(wanted, held) if wanted > 0 else held
    if amount <= 0:
        return None
    recipient = _recipient(state, actor, exchange) if exchange.kind is ExchangeKind.GIVE else None
    return ItemChange(
        name=exchange.thing,
        from_id=actor.id,
        to_id=recipient or WORLD,
        money=money,
        quantity=amount,
        item_id=exchange.item_id,
        how=how,
    )


def _kept(state: WorldState, actor: Character, exchange: Exchange) -> bool:
    """Whether a gift the actor can't make in full is one its recipient already holds, as when
    Milo is told to keep the coins he stole: it moves nothing, and so never fails for want of
    it."""
    recipient = _recipient(state, actor, exchange)
    if exchange.kind is not ExchangeKind.GIVE or recipient is None:
        return False
    return already_given(state, actor, exchange.thing, recipient, money=_money(actor, exchange))


def _money(actor: Character, exchange: Exchange) -> bool:
    return exchange.money or (
        not exchange.item_id and is_money(exchange.thing, actor.sheet.resources.currency)
    )


def _recipient(state: WorldState, actor: Character, exchange: Exchange) -> str | None:
    """Who a gift goes to: a character the story holds, other than the actor. Anyone else, such
    as a stallholder nobody named, takes it out of the record."""
    other = exchange.with_id
    return other if other in state.characters and other != actor.id else None


def _held(actor: Character, exchange: Exchange, moved: list[ItemChange]) -> int:
    """What the actor holds of the thing now, after what earlier steps of the plan moved."""
    money = _money(actor, exchange)
    held = holding(actor, exchange.thing, money=money, item_id=exchange.item_id).amount
    for change in moved:
        if not _same(change, exchange, money):
            continue
        if change.from_id == actor.id:
            held -= abs(change.quantity)
        if change.to_id == actor.id:
            held += abs(change.quantity)
    return max(0, held)


def _same(change: ItemChange, exchange: Exchange, money: bool) -> bool:
    if money or change.money:
        return money and change.money
    if exchange.item_id and change.item_id:
        return exchange.item_id == change.item_id
    return bare(change.name).casefold() == bare(exchange.thing).casefold()


def _short(state: WorldState, actor: Character, exchange: Exchange, held: int, away: bool) -> str:
    """Why the actor can't give or spend it, in the world's words (A8)."""
    who = cap(name(state, actor.id))
    have = "have" if actor.id == state.player_id else "has"
    money = _money(actor, exchange)
    unit = actor.sheet.resources.currency if money and actor.sheet.resources.currency else ""
    thing = unit or bare(exchange.thing)
    if away:
        return f"{cap(possessive(state, actor.id))} {thing} isn't on {_them(state, actor)}."
    if held > 0:
        return f"{who} {have} only {held} {thing}."
    went = gone_to(state, actor, exchange.thing, money=money)
    return " ".join(filter(None, [f"{who} {have} no {thing}.", went]))


def _them(state: WorldState, actor: Character) -> str:
    return "you" if actor.id == state.player_id else "them"

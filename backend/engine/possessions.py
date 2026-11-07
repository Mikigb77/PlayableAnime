"""C10: what everyone has, gains and loses (Miki, 2026-11-07).

What a character holds is engine state: the money and the items on their sheet (G13). Every change
to it is one `ItemChange` that moves a thing from someone to someone, the world included, and is
recorded as a `Transfer`, so a loss is never forgotten and a thing is never in two places at once.
The same rules hold for the narrator's update and for the engine's own changes:

- **Nobody gives what they don't have.** The player character's belongings are all on record, so
  they never pay, give, lose or use up more than they hold: a loss is cut to what they hold, and
  one of something they don't hold is refused. Another character's belongings are on record only
  as far as the story has told them (N7), so they can still hand over something the story never
  listed, and what they are recorded holding goes down by what they hand over.
- **What leaves one side reaches the other.** The receiver gets what the giver gave, as money in
  the giver's currency or as the thing itself, so a thief who takes your 12 coins has them and you
  don't.
- **Money is counted in its holder's currency.** Coins named in the currency count as money even
  when a model writes them as an item ("12 copper coins"). Money in a currency the receiver doesn't
  use becomes an item of its own, so it is never converted at a rate nobody set.

A step the player character takes is checked before anything is told (`engine.resolve.exchanges`):
one that pays, gives or uses up what they don't hold is ruled out, and one that works moves what it
moves as the engine's own change (F4). Plain Python, with no Django or model imports (B4).
"""

import re
from dataclasses import dataclass

from engine.contracts.delta import WORLD, ItemChange
from engine.labels import ago_label
from engine.state.cast import Character
from engine.state.records import OriginKind, Transfer
from engine.state.sheet import Item, ItemKind
from engine.state.world import WorldState
from engine.text import stems

# How many transfers the state keeps, newest last. Older ones leave the prompts long before this.
TRANSFERS_KEPT = 200
# How many of the player character's latest transfers the models read (K8).
PROMPT_TRANSFERS = 8

# Words for money in general, in every language a story can be told in (S10), so "coins" or
# "dinero" counts as the holder's money whatever their currency is called.
_MONEY_WORDS = stems("money coin coins cash dinero moneda monedas diners monedes")
# A whole number, with thousands grouped by "," or "." ("1,000 lire", "1.000 liras"), never a
# decimal: "1.5 liters" counts as given.
_COUNT = re.compile(r"^(\d{1,3}(?:[,.]\d{3})+|\d+)\s")
_LEADING = re.compile(r"^(?:(?:\d[\d,.]*|a|an|the|some|my|your|his|her|their)\s+)+", re.IGNORECASE)


def _words(text: str) -> frozenset[str]:
    """The meaningful word stems of a name, numbers aside: '12 copper coins' is 'copper coin'."""
    return frozenset(w for w in stems(text) if not w.isdigit())


def bare(name: str) -> str:
    """A name without its count or article: '12 copper coins' is 'copper coins'."""
    text = name.strip()
    return _LEADING.sub("", text).strip() or text


def count(name: str, quantity: int) -> int:
    """How many a change moves: its quantity, or the number its name starts with when it gives
    none of its own, so '12 copper coins' moves twelve."""
    if abs(quantity) > 1:
        return abs(quantity)
    found = _COUNT.match(name.strip())
    if quantity and found:
        return int(found.group(1).replace(",", "").replace(".", ""))
    return abs(quantity)


def is_money(name: str, currency: str) -> bool:
    """Whether a thing named so is money in this currency: every word of it is the currency's or
    a word for money in general, numbers aside. '12 copper coins' is money to someone who counts
    in copper coins, and 'gold coins' isn't."""
    words = _words(name)
    return bool(words) and words <= (_words(currency) | _MONEY_WORDS)


def same_currency(a: str, b: str) -> bool:
    return a.strip().casefold() == b.strip().casefold() or (
        bool(_words(a)) and _words(a) == _words(b)
    )


def same_thing(name: str, other: str) -> bool:
    """Whether a name means the thing another names: the same words, counts and articles aside,
    or every word of it in the other ('the knife' is the 'flick knife')."""
    if bare(name).casefold() == bare(other).casefold():
        return True
    words = _words(name)
    return bool(words) and words <= _words(other)


def find_item(character: Character, name: str, item_id: str | None = None) -> Item | None:
    """The item a change or a step names: by id, then by its exact name, then by words, what
    they carry first. Matching by words goes one way only: every word given must be in the item's
    name or description, so 'the dagger' finds 'a rusty dagger'."""
    items = [i for i in character.sheet.resources.items if i.quantity > 0]
    if item_id:
        found = next((i for i in items if i.id == item_id), None)
        if found is not None:
            return found
    wanted = bare(name).casefold()
    exact = next((i for i in items if bare(i.name).casefold() == wanted), None)
    if exact is not None:
        return exact
    words = _words(name)
    if not words:
        return None
    ordered = sorted(items, key=lambda i: not i.carried)
    return next((i for i in ordered if words <= _words(i.name)), None) or next(
        (i for i in ordered if words <= _words(f"{i.name} {i.description}")), None
    )


@dataclass
class Holding:
    """How much of something a character holds: money in their purse (`item` None), or an item."""

    amount: int
    item: Item | None = None
    money: bool = False


def holding(
    character: Character, name: str, *, money: bool = False, item_id: str | None = None
) -> Holding:
    """What a character holds of a thing. Money is their purse, in their currency, and a name in
    that currency counts as money too; coins they keep as an item count when the purse is empty."""
    resources = character.sheet.resources
    as_money = money or (not item_id and is_money(name, resources.currency))
    if as_money and resources.money > 0:
        return Holding(resources.money, money=True)
    item = find_item(character, name, item_id)
    if item is not None:
        return Holding(item.quantity, item)
    return Holding(0, money=as_money)


def holder_of(state: WorldState, item_id: str) -> Character | None:
    """Who holds the item with this id, if anyone does."""
    return next((c for c in state.characters.values() if c.sheet.item(item_id) is not None), None)


def move(state: WorldState, change: ItemChange, *, turn: int, origin: OriginKind) -> str | None:
    """C10. Moves what `change` names from its giver to its receiver, in place, and records the
    transfer. Returns why it was refused, or None when it applied."""
    giver_id, receiver_id = side(change.from_id), side(change.to_id)
    giver = state.characters.get(giver_id) if giver_id else None
    receiver = state.characters.get(receiver_id) if receiver_id else None
    if (giver_id and giver is None) or (receiver_id and receiver is None):
        return "no such character"
    if giver is None and receiver is None:
        return "nothing changes hands"
    if giver is not None and giver is receiver:
        return _restyle(giver, change)
    wanted = count(change.name, change.quantity)
    if wanted == 0:
        return "nothing changes hands"

    as_money = _counts_as_money(change, giver, receiver)
    moved, item = wanted, None
    if giver is not None:
        held = holding(giver, change.name, money=as_money, item_id=change.item_id)
        complete = giver.id == state.player_id  # only their belongings are all on record
        if held.amount == 0:
            elsewhere = holder_of(state, change.item_id) if change.item_id else None
            if elsewhere is not None and elsewhere is not giver:
                return "someone else has it"
            if complete:
                return "they don't have it"
        else:
            taken = min(wanted, held.amount)
            moved = taken if complete else wanted
            _take(giver, held, taken)
        item = held.item
        as_money = held.money if held.amount else as_money
    unit = _unit(change, giver, receiver) if as_money else ""
    name = unit if as_money else (item.name if item is not None else bare(change.name))
    if receiver is not None:
        if as_money:
            _add_money(state, receiver, moved, unit)
        else:
            _add_item(state, receiver, moved, name, item, change)
    state.transfers.append(
        Transfer(
            name=name,
            quantity=moved,
            money=as_money,
            currency=unit,
            item_id=item.id if item is not None else change.item_id,
            from_id=giver.id if giver is not None else None,
            to_id=receiver.id if receiver is not None else None,
            how=" ".join(change.how.split())[:60],
            known_by=_witnesses(state, giver, receiver),
            turn=turn,
            world_s=state.world_s,
            timeline_id=state.timeline_id,
            origin=origin,
        )
    )
    del state.transfers[:-TRANSFERS_KEPT]
    return None


def side(character_id: str | None) -> str | None:
    """A side of a change as a character id, or None for the world."""
    text = (character_id or "").strip()
    return None if not text or text.casefold() == WORLD else text


def _counts_as_money(change: ItemChange, *sides: Character | None) -> bool:
    """Money is money, and so are coins named in either side's currency; an item on record by
    its id is the item."""
    present = [c for c in sides if c is not None]
    if change.item_id and any(c.sheet.item(change.item_id) is not None for c in present):
        return False
    return change.money or any(is_money(change.name, c.sheet.resources.currency) for c in present)


def _restyle(character: Character, change: ItemChange) -> str | None:
    """The same id on both sides: the thing stays where it is, described anew or set down."""
    item = find_item(character, change.name, change.item_id)
    if item is None:
        return "they don't have it"
    _describe(item, change)
    return None


def _describe(item: Item, change: ItemChange) -> None:
    if change.description is not None:
        item.description = change.description
    if change.kind is not None:
        item.kind = change.kind
    if change.carried is not None:
        item.carried = change.carried


def _take(giver: Character, held: Holding, amount: int) -> None:
    resources = giver.sheet.resources
    if held.item is None:
        resources.money -= min(amount, resources.money)
        return
    held.item.quantity -= amount
    if held.item.quantity <= 0:
        resources.items.remove(held.item)


def _unit(change: ItemChange, giver: Character | None, receiver: Character | None) -> str:
    """The currency money is counted in: the giver's, or the receiver's when the world gives it,
    or the change's own name when nobody has one."""
    for character in (giver, receiver):
        if character is not None and character.sheet.resources.currency:
            return character.sheet.resources.currency
    return bare(change.name)


def _add_money(state: WorldState, receiver: Character, amount: int, unit: str) -> None:
    resources = receiver.sheet.resources
    if not resources.currency and resources.money == 0:
        resources.currency = unit
    if not resources.currency or same_currency(resources.currency, unit):
        resources.money += amount
        return
    # Money in a currency they don't count in is kept as it is, never converted.
    coins = next(
        (i for i in resources.items if same_currency(i.name, unit) and i.kind is ItemKind.TREASURE),
        None,
    )
    if coins is None:
        coins = Item(
            id=_fresh_id(state, _held_ids(state)), name=unit, kind=ItemKind.TREASURE, quantity=0
        )
        resources.items.append(coins)
    coins.quantity += amount


def _add_item(
    state: WorldState,
    receiver: Character,
    amount: int,
    name: str,
    source: Item | None,
    change: ItemChange,
) -> None:
    """What the receiver gets is on them, unless it stands where it is (a car, a house), or it
    joins a stack of the same thing that they keep elsewhere."""
    items = receiver.sheet.resources.items
    wanted = bare(name).casefold()
    same = next((i for i in items if bare(i.name).casefold() == wanted), None)
    if same is None:
        held_ids = _held_ids(state)
        ids = [source.id if source is not None else None, change.item_id]
        item_id = next((i for i in ids if i and i not in held_ids), None)
        kind = source.kind if source is not None else (change.kind or ItemKind.OTHER)
        same = Item(
            id=item_id or _fresh_id(state, held_ids),
            name=name,
            kind=kind,
            description=source.description if source is not None else "",
            history=source.history if source is not None else "",
            quantity=0,
            carried=kind not in WHERE_IT_STANDS,
        )
        items.append(same)
    same.quantity += amount
    _describe(same, change)


# Things used where they stand, never carried (G14), nor drawn on anyone (M5).
WHERE_IT_STANDS = (ItemKind.VEHICLE, ItemKind.PROPERTY)


def _held_ids(state: WorldState) -> set[str]:
    return {i.id for c in state.characters.values() for i in c.sheet.resources.items}


def _fresh_id(state: WorldState, held: set[str]) -> str:
    while True:
        item_id = state.new_id("item")
        if item_id not in held:
            return item_id


def _witnesses(state: WorldState, *sides: Character | None) -> list[str]:
    ids = [state.player_id, *(c.id for c in sides if c is not None), *state.scene.present_ids]
    return [i for i in dict.fromkeys(ids) if i in state.characters]


# --- reading what changed hands ---------------------------------------------------------------


def amount_text(transfer: Transfer) -> str:
    """'12 copper coins', 'a rusty key', '3 arrows'."""
    if transfer.money or transfer.quantity > 1:
        return f"{transfer.quantity} {transfer.name}"
    return transfer.name


def involving(state: WorldState, character_id: str) -> list[Transfer]:
    """The transfers on this timeline that a character gave or got, oldest first."""
    return [
        t
        for t in state.transfers
        if t.timeline_id == state.timeline_id and character_id in (t.from_id, t.to_id)
    ]


def prompt_lines(state: WorldState, limit: int = PROMPT_TRANSFERS) -> list[str]:
    """The player character's latest transfers, oldest first, for the models: what they gained,
    gave, lost or used up, and who has it now (C10)."""
    you = state.player_id
    lines = []
    for t in involving(state, you)[-limit:]:
        what = amount_text(t)
        if t.from_id == you and t.to_id:
            line = f"{what} went from you to {_who(state, t.to_id)}"
        elif t.from_id == you:
            line = f"{what} left you for good"
        elif t.from_id:
            line = f"{what} came to you from {_who(state, t.from_id)}"
        else:
            line = f"{what} came to you"
        how = f", {t.how}" if t.how else ""
        lines.append(f"{line}{how}, {ago_label(max(0, state.world_s - t.world_s))}.")
    return lines


def _who(state: WorldState, character_id: str) -> str:
    """Who the other side was, for the models, marked when the player character doesn't know them
    (C6), so the telling never names them."""
    character = state.characters.get(character_id)
    if character is None:
        return character_id
    you = state.player_id
    known = you in character.known_by or you in character.met_by
    return f"{character.name} ({character_id}{'' if known else ', unknown to you'})"


def gone_to(state: WorldState, actor: Character, name: str, *, money: bool) -> str:
    """Why the actor no longer holds something, from the last time it left them, as a sentence:
    'They went to Milo.' Empty when nothing on record says."""
    words = _words(name)
    for t in reversed(involving(state, actor.id)):
        if t.from_id != actor.id:
            continue
        if not (money and t.money) and not (words and words <= _words(t.name)):
            continue
        plural = t.money or t.quantity > 1 or _plural(t.name)
        pronoun = "They" if plural else "It"
        if t.to_id is None:
            return f"{pronoun} {'are' if plural else 'is'} gone."
        return f"{pronoun} went to {_known_name(state, t.to_id)}."
    return ""


def _plural(name: str) -> bool:
    last = bare(name).split()[-1:] or [""]
    return last[0].casefold().endswith("s")


def _known_name(state: WorldState, character_id: str) -> str:
    character = state.characters.get(character_id)
    if character is None:
        return "someone"
    you = state.player_id
    return character.name if you in character.known_by or you in character.met_by else "someone"


def already_given(
    state: WorldState, actor: Character, name: str, to_id: str, *, money: bool
) -> int:
    """How much of it went to `to_id` the last time something like this left the actor, or 0
    when it went elsewhere: letting someone keep what they already took moves nothing (C10)."""
    words = _words(name)
    for t in reversed(involving(state, actor.id)):
        if t.from_id != actor.id:
            continue
        if (money and t.money) or (words and words <= _words(t.name)):
            return t.quantity if t.to_id == to_id else 0
    return 0

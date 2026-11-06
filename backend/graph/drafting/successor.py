"""N6: the person the story carries on with, after its ending.

Code draws who they are by the world's population odds (`engine.succession.draw`); the drafter
fills in someone who fits the draw, in one call; code builds the character and holds it to the
draw: where they live, their station, their might, their age and their people. The model can't
make them a ruler, a god or someone the story already has, and has no say in their power.

    lot = succession.draw(state, rng)
    proposal = await propose(llm, state, lot, rating="teen")
    character, situation = build(state, lot, proposal)
    state = succession.carry_on(state, character, situation, ending="death", turn=12)
"""

from __future__ import annotations

from pydantic import Field

from engine.context import Language
from engine.heirs import RELATIONS
from engine.invariants import is_real_name
from engine.kin import descendants
from engine.limits import real_entity
from engine.resolve.strangers import ORDINARY_TIER
from engine.state import (
    BackstoryClaim,
    Character,
    CharacterSheet,
    Disposition,
    Item,
    LadderPosition,
    Origin,
    OriginKind,
    PowerAxes,
    PowerAxis,
    Prominence,
    Resources,
    Trait,
    WorldState,
)
from engine.succession import STANDING, Lot, Station
from engine.world.births import is_placeholder
from graph.drafting.assemble import (
    HUMAN_PEAK,
    MAX,
    NAME_LIMIT,
    PLAYER_FALLBACK_NAME,
    _clamp,
    _Ids,
    _name,
    _skills,
    _temperament,
    _text,
    _texts,
)
from graph.drafting.prompts import RATINGS
from graph.drafting.schema import (
    AttributesP,
    ItemP,
    Proposal,
    SkillP,
    TemperamentP,
    TraitP,
)
from graph.language import language_line
from graph.llm import ModelClient, Node, Prompt

SITUATION_LIMIT = 300
# How many names already in the story the drafter is shown.
NAMES_SHOWN = 120


class SuccessorProposal(Proposal):
    """Who the drawn person is, in the world's words."""

    name: str
    aliases: list[str] = Field(default_factory=list)
    description: str = Field(default="", description="How they come across to anyone who meets.")
    appearance: str = Field(default="", description="For portraits.")
    attributes: AttributesP = Field(default_factory=AttributesP)
    skills: list[SkillP] = Field(default_factory=list, description="Up to eight.")
    traits: list[TraitP] = Field(default_factory=list, description="Up to four.")
    temperament: TemperamentP = Field(default_factory=TemperamentP)
    items: list[ItemP] = Field(default_factory=list, description="What they own, up to eight.")
    money: int = 0
    currency: str = ""
    title: str = ""
    rank: str = Field(default="", description="Their trade or standing, in the world's words.")
    family_name: str = ""
    backstory: list[str] = Field(default_factory=list, description="Up to four lines.")
    situation: str = Field(
        description="The moment their first scene opens on, in one sentence: where they are and "
        "what they are doing, with something at hand to act on."
    )


SYSTEM = """\
You draft the next player character for Lucid Saga, an endless story game where the player can do \
anything and the world remembers it. The story's last player character has reached their ending, \
and the player carries on as someone else in the same world: a person code has already drawn at \
random, by the world's own population odds. Fill in a person who fits the draw exactly, as JSON \
that follows the schema. Code checks every field.

- Keep to the draw: where they live, their station, how strong they are, their age and their \
people. Most people are ordinary, and that is fine: give them a life worth playing, a trade, \
people around them and wants of their own.
- They are someone new, never a character the world already has, never its ruler, a god or a \
chosen one. A hidden master hides it: others see an ordinary person.
- Attributes: 3 is an average person and 5 the peak of what a person can be. Only a world with \
something extraordinary goes past 5, and only for someone strong.
- Skills, traits (gifts and flaws), temperament, what they own and their money fit their station.
- The situation is an ordinary moment of their life, now, where they live, ending on something to \
act on. Nothing that happened to the last player character needs to touch them.

Every person and organisation is fictional, with no real living person. There is no sexual \
content in any rating. Write in plain words, in the world's own voice.\
"""

STATIONS = {
    Station.COMMON: "common folk: a labourer, a farmer, a servant, someone poor",
    Station.SKILLED: "someone with a trade or a craft: a smith, a trader, a soldier, a clerk",
    Station.NOTABLE: "a notable: a rich merchant, a local official, an officer, an elder",
    Station.NOBLE: "a member of a noble house, or someone in high office",
    Station.ROYAL: "a member of the ruling family, but not its ruler",
}


async def propose(
    llm: ModelClient,
    state: WorldState,
    lot: Lot,
    *,
    rating: str,
    language: Language = Language.EN,
) -> SuccessorProposal:
    """The drafter's person for the draw, written in the story's language (S10)."""
    system = _system(SYSTEM, rating, language)
    return await llm.structured(
        Node.DRAFTER, Prompt.build(system, successor_prompt(state, lot)), SuccessorProposal
    )


HEIR_SYSTEM = """\
You draft the next player character for Lucid Saga, an endless story game where the player can do \
anything and the world remembers it. The story's last player character has reached their ending, \
and the player carries on as their heir: a child or grandchild the story already has. Fill in who \
the heir is now, as JSON that follows the schema. Code checks every field.

- Keep to what the story has: their parents, age, people and home. When they grew up in the years \
since the ending, decide who they became: a trade, skills, wants of their own, what they own. \
Someone who was a child in the story keeps that past.
- Give them a name only when they have none yet; otherwise repeat the name given.
- Attributes: 3 is an average person and 5 the peak of what a person can be. An heir is a person, \
however strong their parent was.
- Their standing follows their family's, as the world would treat a child of theirs.
- The situation is a moment of their life now, where they live, ending on something to act on. \
They know their family as family does, and the rest of the world only as anyone there would.

Every person and organisation is fictional, with no real living person. There is no sexual \
content in any rating. Write in plain words, in the world's own voice.\
"""


async def propose_heir(
    llm: ModelClient,
    state: WorldState,
    heir: Character,
    *,
    years: int,
    rating: str,
    language: Language = Language.EN,
) -> SuccessorProposal:
    """The drafter's heir, as they are now, written in the story's language (S10). `state` is
    the world now, `years` how long it ran on since the ending."""
    system = _system(HEIR_SYSTEM, rating, language)
    return await llm.structured(
        Node.DRAFTER, Prompt.build(system, heir_prompt(state, heir, years=years)), SuccessorProposal
    )


def _system(base: str, rating: str, language: Language) -> str:
    words = language_line(language, "every text field the player reads")
    return f"{base}\n\n{words}\n\n{RATINGS.get(rating, RATINGS['teen'])}"


def heir_prompt(state: WorldState, heir: Character, *, years: int) -> str:
    fallen = state.characters.get(state.player_id)
    who = []
    if is_placeholder(heir):
        who.append("Name: none yet; give them one.")
    else:
        who.append(f"Name: {heir.name}.")
    if heir.age is not None:
        who.append(f"Age: {heir.age}.")
    parents = [state.characters[p] for p in heir.parent_ids if p in state.characters]
    for parent in parents:
        role = "the last player character" if parent.id == state.player_id else "a parent"
        status = "" if parent.alive else ", now dead"
        line = f"Parent: {parent.name} ({role}{status})"
        detail = parent.sheet.resources.title or parent.sheet.resources.rank
        who.append(f"{line}, {detail}." if detail else f"{line}.")
    if fallen is not None and fallen.id not in heir.parent_ids:
        generation = descendants(state, fallen.id).get(heir.id)
        if generation is not None:
            relation = RELATIONS.get(generation, "descendant").capitalize()
            who.append(f"{relation} of {fallen.name}, the last player character.")
    if years:
        who.append(f"They grew up in the {years} years since the last story ended.")
    if heir.description:
        who.append(f"As the story knew them: {heir.description}")
    people = next((p for p in state.bible.peoples if p.id == heir.people_id), None)
    if people is not None:
        who.append(f"People: {people.name}. {people.description}".strip())
    where = _where(state, heir.location_id)
    if where:
        who.append("Lives in: " + where)
    return "\n\n".join(
        [
            "THE WORLD\n" + "\n".join(_world_lines(state)),
            "THE HEIR\n" + "\n".join(who),
            "NAMES ALREADY IN THE STORY\n" + ", ".join(_taken(state)),
            "Draft this person as they are now.",
        ]
    )


def _world_lines(state: WorldState) -> list[str]:
    bible = state.bible
    world = [f"Genre: {bible.genre}.", f"Tone: {bible.tone}."]
    if bible.era:
        world.append(f"Era: {bible.era}")
    world += [f"- {rule.text}" for rule in bible.rules[:8]]
    if state.summary:
        world.append(f"Situation: {state.summary}")
    return world


def _where(state: WorldState, place_id: str | None) -> str:
    place = state.places.get(place_id or "")
    if place is None:
        return ""
    where = [place.name + (f", a {place.kind}" if place.kind else "")]
    parent = state.places.get(place.parent_id or "")
    if parent is not None:
        where.append(f"in {parent.name}")
    lines = [", ".join(where) + "."]
    if place.description:
        lines.append(place.description)
    return " ".join(lines)


def _taken(state: WorldState) -> list[str]:
    """The names that matter most, so the prompt stays small in a long story; `build` refuses
    any name the story has."""
    named = sorted(
        state.characters.values(), key=lambda c: (c.prominence is not Prominence.KEY, c.name)
    )
    return [c.name for c in named][:NAMES_SHOWN]


def successor_prompt(state: WorldState, lot: Lot) -> str:
    world = _world_lines(state)
    bible = state.bible
    who = [f"Station: {STATIONS[lot.station]}.", f"Age: {lot.age}.", f"Might: {_might(lot)}."]
    rung = _rung(state, lot.might)
    if rung is not None:
        ladder, index = rung
        who.append(f"On the {ladder.name}: {ladder.rungs[index].name}.")
    people = next((p for p in bible.peoples if p.id == lot.people_id), None)
    if people is not None:
        who.append(f"People: {people.name}. {people.description}".strip())
    where = _where(state, lot.place_id)
    if where:
        who.append("Lives in: " + where)
    return "\n\n".join(
        [
            "THE WORLD\n" + "\n".join(world),
            "THE DRAW\n" + "\n".join(who),
            "NAMES ALREADY IN THE STORY\n" + ", ".join(_taken(state)),
            "Draft this person.",
        ]
    )


def build(state: WorldState, lot: Lot, proposal: SuccessorProposal) -> tuple[Character, str]:
    """The character code makes of the proposal, held to the draw, and the moment their first
    scene opens on."""
    # Only a hidden master in a world with something extraordinary goes past a person's peak
    # (A4, G8, G13).
    peak = 10 if lot.master and not state.bible.grounded else HUMAN_PEAK
    influence, wealth = STANDING[lot.station]
    sheet = _sheet(
        state,
        proposal,
        peak=peak,
        axes=PowerAxes(might=lot.might, influence=influence, wealth=wealth),
        titled=lot.station is not Station.COMMON,
    )
    character = Character(
        id=_new_id(state),
        name=_new_name(state, proposal),
        aliases=[a for a in _texts(proposal.aliases, 4, NAME_LIMIT) if _fictional(a)],
        prominence=Prominence.KEY,
        description=_text(proposal.description),
        appearance=_text(proposal.appearance),
        age=lot.age,
        people_id=lot.people_id,
        location_id=lot.place_id,
        sheet=sheet,
        origin=Origin(kind=OriginKind.EMERGENCE),
    )
    situation = _text(proposal.situation, SITUATION_LIMIT) or ordinary_day(state, character)
    return character, situation


def build_heir(
    state: WorldState, heir: Character, proposal: SuccessorProposal, *, grown: bool
) -> tuple[Character, str]:
    """An heir as the player will play them, from the drafter's proposal, and the moment their
    first scene opens on. `state` is the world as it is when they start, and `grown` says they
    grew up off-screen, in a time jump: then who they became is the drafter's, held to their
    parents' standing and a person's might. Otherwise the story already has them, and the
    proposal only fills in what it lacks. They keep their id, family, place, people, age, ties
    and memberships, and a name the story gave them."""
    parents = [state.characters[p] for p in heir.parent_ids if p in state.characters]
    fresh = grown or not heir.sheet.skills
    update: dict = {"prominence": Prominence.KEY}
    if is_placeholder(heir):
        update["name"] = _new_name(state, proposal)
    if grown or not heir.description:
        update["description"] = _text(proposal.description)
    if grown or not heir.appearance:
        update["appearance"] = _text(proposal.appearance)
        if heir.appearance:
            update["look_version"] = heir.look_version + 1  # M5: drawn again, grown up
    if fresh:
        might = heir.sheet.axes.might if not grown else ORDINARY_TIER
        axes = PowerAxes(
            might=might,
            influence=max([heir.sheet.axes.influence, *(p.sheet.axes.influence for p in parents)]),
            wealth=max([heir.sheet.axes.wealth, *(p.sheet.axes.wealth for p in parents)]),
        )
        sheet = _sheet(
            state,
            proposal,
            peak=HUMAN_PEAK,
            axes=axes,
            titled=any(p.sheet.resources.title for p in parents),
        )
        update["sheet"] = _kept(heir.sheet, sheet, grown=grown)
    character = heir.model_copy(deep=True, update=update)
    situation = _text(proposal.situation, SITUATION_LIMIT) or ordinary_day(state, character)
    return character, situation


def _kept(old: CharacterSheet, new: CharacterSheet, *, grown: bool) -> CharacterSheet:
    """A drafted sheet for an heir, keeping what the world already holds of them: how they feel
    about people and who they are tied to, their powers and what they learned, their traits and
    belongings, their standing, and their condition. Years of growing up heal all but a lasting
    wound."""
    sheet = new.model_copy(deep=True)
    sheet.disposition.attitudes = dict(old.disposition.attitudes)
    sheet.traits = _merged(old.traits, new.traits)
    for field in ("powers", "techniques", "rulings", "growth", "practice", "backstory"):
        if getattr(old, field):
            setattr(sheet, field, list(getattr(old, field)))
    if old.ladders and not grown:
        sheet.ladders = list(old.ladders)
    held, drafted = old.resources, new.resources
    ids = {item.id for item in held.items}
    items = list(held.items)
    for item in _merged(held.items, drafted.items)[len(held.items) :]:
        item_id, n = item.id, 2
        while item_id in ids:
            item_id, n = f"{item.id}-{n}", n + 1
        ids.add(item_id)
        items.append(item.model_copy(update={"id": item_id}))
    sheet.resources = drafted.model_copy(
        update={
            "items": items,
            "money": held.money or drafted.money,
            "currency": held.currency or drafted.currency,
            "title": held.title or drafted.title,
            "rank": held.rank or drafted.rank,
            "family_name": held.family_name or drafted.family_name,
            "connections": list(held.connections),
        }
    )
    if grown:
        lasting = [w for w in old.condition.wounds if w.lasting]
        sheet.condition = sheet.condition.model_copy(update={"wounds": lasting})
    else:
        sheet.condition = old.condition.model_copy(deep=True)
    return sheet


def _merged[T: (Trait, Item)](held: list[T], drafted: list[T]) -> list[T]:
    """What they hold, then what the drafter gave them that they don't, by name."""
    names = {t.name.casefold() for t in held}
    return [*held, *(t for t in drafted if t.name.casefold() not in names)]


def _sheet(
    state: WorldState,
    proposal: SuccessorProposal,
    *,
    peak: int,
    axes: PowerAxes,
    titled: bool,
) -> CharacterSheet:
    attributes = {
        name: _clamp(value, 0, peak, 3) for name, value in proposal.attributes.model_dump().items()
    }
    rung = _rung(state, axes.might)
    item_ids = _Ids("item")
    return CharacterSheet(
        attributes=attributes,
        skills=_skills(proposal.skills),
        traits=[
            Trait(name=_name(t.name), kind=t.kind, description=_text(t.description, 300))
            for t in proposal.traits[:4]
            if _name(t.name)
        ],
        disposition=Disposition(temperament=_temperament(proposal.temperament)),
        axes=axes,
        ladders=[LadderPosition(ladder_id=rung[0].id, rung=rung[1])] if rung else [],
        resources=Resources(
            items=[
                Item(
                    id=item_ids.add("", item.name),
                    name=_name(item.name),
                    kind=item.kind,
                    description=_text(item.description, 300),
                    quantity=_clamp(item.quantity, 0, 1_000_000, 1),
                    carried=item.carried,
                )
                for item in proposal.items[: MAX["items"]]
                if _name(item.name)
            ],
            money=_clamp(proposal.money, 0, 10**12, 0),
            currency=_text(proposal.currency, 40),
            title=_text(proposal.title, 120) if titled else "",
            rank=_text(proposal.rank, 120),
            family_name=_fictional(_text(proposal.family_name, 120)),
        ),
        backstory=[BackstoryClaim(text=t) for t in _texts(proposal.backstory, 4)],
    )


def _new_name(state: WorldState, proposal: SuccessorProposal) -> str:
    """The proposal's name, unless it is a real person's (G12), a placeholder or one the story
    already has: then the default name, numbered."""
    name = _fictional(_name(proposal.name))
    taken = {c.name.casefold() for c in state.characters.values()}
    if not is_real_name(name) or name.casefold() in taken:
        name = _fallback_name(taken)
    return name


def ordinary_day(state: WorldState, character: Character) -> str:
    """The moment a first scene opens on when the drafter gave none that can be shown."""
    place = state.places.get(character.location_id or "")
    return f"An ordinary day for {character.name}" + (f" in {place.name}." if place else ".")


def _fallback_name(taken: set[str]) -> str:
    """The default name, numbered when the story already has someone by it."""
    name, n = PLAYER_FALLBACK_NAME, 1
    while name.casefold() in taken:
        n += 1
        name = f"{PLAYER_FALLBACK_NAME} {n}"
    return name


def _might(lot: Lot) -> str:
    if lot.master:
        return "a hidden master, far stronger than anyone would guess"
    if lot.might > 1:
        return "knows how to fight, a step above an ordinary person"
    return "an ordinary person"


def _rung(state: WorldState, might: int):
    """The highest rung of the world's ladder of might that a might reaches (G18)."""
    ladder = next((lad for lad in state.bible.ladders if lad.axis is PowerAxis.MIGHT), None)
    if ladder is None:
        return None
    reached = [i for i, rung in enumerate(ladder.rungs) if rung.tier <= might]
    return (ladder, reached[-1]) if reached else None


def _fictional(name: str) -> str:
    """G12: no real person's name."""
    return "" if name and real_entity(name) is not None else name


def _new_id(state: WorldState) -> str:
    number = len(state.fallen) + 2
    while f"pc-{number}" in state.characters:
        number += 1
    return f"pc-{number}"

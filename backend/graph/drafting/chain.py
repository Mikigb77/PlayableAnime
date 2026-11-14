"""Drafting a world and a character from a premise, revising it in plain words and editing it
directly (G1, G2, S1). Plain Python on the model layer, with no Django (B4).

A `Draft` holds only inputs: the model's latest proposal and what the player set up. Its world
state is a pure function of them (`Draft.state()`), so a revision changes one part of the
proposal and code re-decides everything else, the same way every time. A change comes back
as only what it touches, and code merges it in: a `WorldChange` into the world (`apply_change`)
and a `CharacterChange` into the character (`apply_character_change`), so nothing the change
leaves out is ever lost or shifted by a model that copies it back badly. Every proposal is
cleaned of real people and organisations before it is kept (G12, `real_names`).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import Literal, get_args

from pydantic import ValidationError

from engine import pipeline
from engine.base import HOUR
from engine.context import Language
from engine.state import GiftStrength, PhysicsMode, WorldState
from graph.drafting import direct
from graph.drafting.assemble import DraftOptions, assemble, drafted_clocks, slug
from graph.drafting.catalog import PremiseTemplate, starter, wordings
from graph.drafting.openers import Said, carried, clock_times, kept_back, moved, named_by
from graph.drafting.prompts import (
    current_rules,
    draft_prompt,
    gift_instruction,
    lines_instruction,
    rating_instruction,
    revise_prompt,
    rules_instruction,
    system_prompt,
)
from graph.drafting.real_names import without_real_names
from graph.drafting.schema import (
    CHARACTER_KEYS,
    CHARACTER_SECTIONS,
    CHARACTER_TEXTS,
    WORLD_SECTIONS,
    CharacterChange,
    CharacterProposal,
    ClockP,
    DraftProposal,
    RuleP,
    WorldChange,
    WorldProposal,
)
from graph.drafting.view import (
    PartKind,
    character_lines,
    character_parts,
    gift_strength,
    public_rules,
    shown,
    world_lines,
    world_parts,
)
from graph.llm import CallOptions, ModelClient, Node, Prompt
from graph.words import WORD, core

Target = Literal["world", "character"]


@dataclass(frozen=True)
class Draft:
    """A draft's inputs. `released_rules` are the starter template's rules the player let go of
    while setting up the story (G7). `language` is what the drafter writes in (S10)."""

    premise: str
    proposal: DraftProposal
    rating: str = "teen"
    premise_id: str | None = None
    physics: PhysicsMode = PhysicsMode.FUN_FIRST
    gift: GiftStrength | None = None
    released_rules: frozenset[str] = frozenset()
    language: Language = Language.EN
    # G1: the keys of the openers (a deadline, a question, a person, a connection, a goal) that
    # a change the player asked for since the premise named. The words of the change are not
    # kept (`graph.drafting.openers`).
    told: frozenset[str] = frozenset()

    @property
    def said(self) -> Said:
        """The player's say in how the story starts: the premise, and what their later changes
        named. The summary shows a goal, a deadline, a question or a person only when these
        name it."""
        return Said(self.premise, self.told)

    @property
    def template(self) -> PremiseTemplate | None:
        """The starter's template, in the words of the draft's language (S10)."""
        found = starter(self.premise_id) if self.premise_id else None
        return found.template.in_language(self.language) if found is not None else None

    def options(self) -> DraftOptions:
        return DraftOptions(
            premise=self.premise,
            physics=self.physics,
            gift=self.gift,
            template=self.template,
            released_rules=self.released_rules,
            language=self.language,
        )

    def state(self) -> WorldState:
        """The assembled state, built once per draft. Read it; never change it."""
        built = self.__dict__.get("_state")
        if built is None:
            built = assemble(self.proposal.world, self.proposal.character, self.options())
            object.__setattr__(self, "_state", built)
        return built


def opening(draft: Draft) -> WorldState:
    """The state a story starts on, which is the draft's with what the player has and hasn't
    read by then (G1, G18, C6). What they read before starting, the character knows from the
    first moment: a rung their own premise or the draft's screen named is one they have heard
    of (`engine.path`). What the screen kept a surprise, the story's own screens hold back
    until a scene tells it (`engine.untold`). The draft's own state is never changed."""
    state = draft.state()
    read = f"{draft.premise}\n{shown(state, draft.language, draft.said)}"
    state, _ = pipeline.settle_path(state, read)
    kept = kept_back(state, draft.language, draft.said)
    return state.model_copy(update={"untold": kept}) if kept else state


@dataclass(frozen=True)
class RuleEdit:
    """A rule as the player set it in the advanced fields. A rule without an id is new."""

    text: str
    fixed: bool
    id: str | None = None


@dataclass(frozen=True)
class Edits:
    """Direct edits (API.md `PATCH /v1/drafts/{id}`). `None` leaves a part as it is. `fields`
    are the plain fields, which code writes in without the model (`graph.drafting.direct`)."""

    world_lines: list[str] | None = None
    character_lines: list[str] | None = None
    rules: list[RuleEdit] | None = None
    physics: PhysicsMode | None = None
    gift: GiftStrength | None = None
    rating: str | None = None
    fields: direct.Fields | None = None


async def create(
    llm: ModelClient,
    premise: str,
    *,
    rating: str,
    premise_id: str | None = None,
    physics: PhysicsMode = PhysicsMode.FUN_FIRST,
    gift: GiftStrength | None = None,
    rules: list[RuleEdit] | None = None,
    language: Language = Language.EN,
) -> Draft:
    """The first draft: the world, then the character in it, in one model call, written in
    `language` (S10). `rules` are rules the player set before drafting: they join the drafted
    ones word for word, and one with the id of a drafted rule replaces it."""
    draft = Draft(
        premise=premise,
        proposal=DraftProposal(
            world=WorldProposal(title="", genre="", tone="", era=""),
            character=CharacterProposal(name=""),
        ),
        rating=rating,
        premise_id=premise_id,
        physics=physics,
        gift=gift,
        language=language,
    )
    prompt = Prompt.build(
        system_prompt(rating, language),
        draft_prompt(
            premise,
            template=draft.template,
            gift=_gift_hint(draft),
            player_rules=[" ".join(r.text.split()) for r in rules or []],
        ),
    )
    proposal = without_real_names(await llm.structured(Node.DRAFTER, prompt, DraftProposal))
    world = proposal.world.model_copy(update={"dropped_rule_ids": []})
    draft = replace(draft, proposal=proposal.model_copy(update={"world": world}))
    draft = _on_time(draft, [premise])
    if rules:
        current = current_rules(draft.state())
        chosen = {r.id: r for r in rules if r.id}
        merged = [chosen.pop(r.id, None) or RuleEdit(r.text, r.fixed, r.id) for r in current]
        merged += [r for r in rules if not r.id or r.id in chosen]
        forced = _player_rules(merged, current)
        draft = replace(
            draft,
            proposal=_with_world(draft.proposal, rules=forced),
            released_rules=_released_by(draft.template, forced),
        )
    return draft


# A change to a draft the player is looking at thinks at `low`. The first draft keeps the
# model's own thinking (`graph.llm.config`): nobody has read it yet, and it sets everything. A
# change says in the player's own words what to change, and they wait on it at the row they
# changed. Production's changes from 2026-11-04 to 2026-11-11 spent 4,100 to 8,300 tokens
# thinking for about 1,400 of answer, which was 18 to 46 s of every one and 111 s of the
# slowest, long enough for the phone to drop the request.
CHANGE = CallOptions(thinking="low")
# A change to the character is a few records at most, and a whole character is about 1,400
# tokens. On 2026-11-14 an answer to "she is also a decent cook" ran to the drafter's whole
# limit of 16,384 before it failed, which the player waited through for 87 s with the second
# try. So an answer that runs away is cut here, with room for the thinking it shares.
CHARACTER_CHANGE = replace(CHANGE, max_output_tokens=6000)


def asked_at(draft: Draft, target: Target, kind: PartKind | None) -> str:
    """The lines of the summary that tell of `kind`, as the player read them, or "" for none:
    the `about` of a change asked at one row of the draft."""
    if kind is None:
        return ""
    parts = world_parts if target == "world" else character_parts
    lines = parts(draft.state(), draft.language, draft.said)
    return "\n".join(part.text for part in lines if part.kind is kind)


def asks_an_aim(kind: PartKind | None) -> bool:
    """G1: a change asked at the goal or at the nature row speaks of what the character is
    after, so the goal or the want it names shows from here on."""
    return kind in (PartKind.GOAL, PartKind.NATURE)


async def revise(
    llm: ModelClient,
    draft: Draft,
    target: Target,
    instruction: str,
    about: str = "",
    aim: bool = False,
) -> Draft:
    """A change in plain words, such as "add hidden vampires" (G1, G2). The request is the
    player's own words, so what it names of how the story starts shows in the summary from
    here on. `about` is the part of the summary they asked it at, in the summary's own words,
    so "make me better at this" says what "this" is; it is the drafter's text, and names
    nothing. `aim` says they asked it at the row of what the character is after, their goal
    or their nature, so a goal or a want the request names is theirs with no "I want to"."""
    if target == "world":
        revised = await _revise_world(llm, draft, instruction, about)
    else:
        revised = await _revise_character(llm, draft, instruction, about)
    return _noting(_on_time(revised, [instruction]), [instruction], plainly=aim)


@dataclass(frozen=True)
class EditPlan:
    """Direct edits with the code-only changes made (`plan_edit`), and what is left for the
    model: the requests that make the world or the character match the player's edits.
    `written` is what the player wrote into the summary lines themselves (`own_words`)."""

    draft: Draft
    world_asks: tuple[str, ...] = ()
    character_asks: tuple[str, ...] = ()
    forced_rules: tuple[RuleP, ...] | None = None
    written: tuple[str, ...] = ()

    @property
    def needs_model(self) -> bool:
        return bool(self.world_asks or self.character_asks)


def plan_edit(draft: Draft, edits: Edits) -> EditPlan:
    """The plain fields (`direct`), physics, a rule's fixed flag, `gift: none` and raising the
    rating are code alone; rewritten summary lines, rewritten rules, a new gift strength and
    lowering the rating to Teen need the model to make the world or the character match, in one
    call for each (`finish_edit`)."""
    read = draft
    if edits.fields:
        before = draft.state()
        draft = replace(draft, proposal=direct.apply(draft.proposal, edits.fields))
        # A goal that said the old name is the same goal under the new one (G1).
        draft = _telling(draft, moved(before, draft.state(), draft.told, draft.language))
    state = draft.state()
    world_asks: list[str] = []
    character_asks: list[str] = []
    forced_rules: list[RuleP] | None = None

    if edits.physics is not None:
        draft = replace(draft, physics=edits.physics)
    if edits.rating is not None and edits.rating != draft.rating:
        lowered = edits.rating == "teen"
        draft = replace(draft, rating=edits.rating)
        if lowered:
            # F2: what was drafted for Mature 17+ is redrafted within Teen.
            world_asks.append(rating_instruction(edits.rating))
            character_asks.append(rating_instruction(edits.rating))
    if edits.rules is not None:
        current = current_rules(state)
        # The player edits the rules they can see; a rule the leak guard hides stays (C6).
        shown = [r for r in current if r.id in {p.id for p in public_rules(state)}]
        hidden = [r for r in current if r not in shown]
        forced_rules = _player_rules(edits.rules, current)
        forced_rules += [r for r in hidden if r.id not in {f.id for f in forced_rules}]
        draft = replace(
            draft,
            proposal=_with_world(draft.proposal, rules=forced_rules),
            # The player's list says which of the starter's rules hold, so restoring one word
            # for word holds it again (G7).
            released_rules=_released_by(draft.template, forced_rules),
        )
        if [(r.id, r.text) for r in forced_rules] != [(r.id, r.text) for r in shown + hidden]:
            world_asks.append(rules_instruction(forced_rules))
    written: list[str] = []
    for lines, sent, asks, target in (
        (world_lines, edits.world_lines, world_asks, "world"),
        (character_lines, edits.character_lines, character_asks, "character"),
    ):
        if sent is None:
            continue
        before = lines(state, draft.language, draft.said)
        after = _clean_lines(sent)
        # Lines sent back as the player read them, before the plain fields of the same edit
        # changed a name in them, are no rewriting.
        if after == before or (read is not draft and after == _read(read, lines)):
            continue
        asks.append(lines_instruction(target, before, after))
        written += own_words(before, after)
    if edits.gift is not None:
        changed = edits.gift is not gift_strength(state)
        draft = replace(draft, gift=edits.gift)
        # `none` is code alone: the gift goes (G22). A stronger or weaker gift needs a new one.
        if changed and edits.gift is not GiftStrength.NONE:
            character_asks.append(gift_instruction(edits.gift))
    return EditPlan(
        draft,
        tuple(world_asks),
        tuple(character_asks),
        tuple(forced_rules) if forced_rules is not None else None,
        tuple(written),
    )


def _read(draft: Draft, lines) -> list[str]:
    """The summary lines of `draft` as its screen shows them."""
    return lines(draft.state(), draft.language, draft.said)


async def finish_edit(llm: ModelClient, plan: EditPlan) -> Draft:
    """The model's part of a direct edit. Makes no call when the plan doesn't need one. What
    the player wrote into a line is their own words, so what it names of how the story starts
    shows in the summary from here on (G1)."""
    draft = plan.draft
    if not plan.needs_model:
        return draft
    if plan.world_asks:
        draft = await _revise_world(llm, draft, "\n\n".join(plan.world_asks))
        if plan.forced_rules is not None:
            # A direct edit is the player's own words: the rules stay exactly as written, and
            # the model can't release a starter rule the player kept.
            about = {r.id: r.about for r in draft.proposal.world.rules}
            rules = [
                r.model_copy(update={"about": about.get(r.id, r.about)}) for r in plan.forced_rules
            ]
            draft = replace(
                draft,
                proposal=_with_world(draft.proposal, rules=rules),
                released_rules=plan.draft.released_rules,
            )
    if plan.character_asks:
        draft = await _revise_character(llm, draft, "\n\n".join(plan.character_asks))
    return _noting(_on_time(draft, plan.written), plan.written)


async def edit(llm: ModelClient, draft: Draft, edits: Edits) -> Draft:
    """Direct edits (API.md `PATCH /v1/drafts/{id}`): `plan_edit`, then `finish_edit`."""
    return await finish_edit(llm, plan_edit(draft, edits))


async def _revise_world(llm: ModelClient, draft: Draft, instruction: str, about: str = "") -> Draft:
    state = draft.state()
    change = await llm.structured(
        Node.DRAFTER,
        _revise_prompt(draft, state, "world", instruction, about),
        WorldChange,
        options=CHANGE,
    )
    world, let_go = apply_change(draft.proposal.world, current_rules(state), change)
    world = without_real_names(world)
    template_ids = draft.template.rule_ids if draft.template else frozenset()
    return replace(
        draft,
        proposal=DraftProposal(world=world, character=draft.proposal.character),
        released_rules=draft.released_rules | (let_go & template_ids),
    )


async def _revise_character(
    llm: ModelClient, draft: Draft, instruction: str, about: str = ""
) -> Draft:
    state = draft.state()
    change = await llm.structured(
        Node.DRAFTER,
        _revise_prompt(draft, state, "character", instruction, about),
        CharacterChange,
        options=CHARACTER_CHANGE,
    )
    if change.name.strip():
        # A new name takes the old one's place wherever the draft says it, as one the player
        # types does (`direct.renamed`): their past, a key character's notes and a goal that
        # said the old name are theirs under the new one (G1), with nothing for the model to
        # write again.
        named = replace(draft, proposal=direct.renamed(draft.proposal, change.name))
        draft = _telling(named, moved(state, named.state(), draft.told, draft.language))
    character = without_real_names(apply_character_change(draft.proposal.character, change))
    return replace(draft, proposal=DraftProposal(world=draft.proposal.world, character=character))


def _revise_prompt(
    draft: Draft, state: WorldState, target: Target, instruction: str, about: str = ""
) -> Prompt:
    return Prompt.build(
        system_prompt(draft.rating, draft.language),
        revise_prompt(
            draft.premise,
            draft.proposal,
            state,
            target=target,
            instruction=instruction,
            about=about,
            template=draft.template,
            gift=_gift_hint(draft),
            released=draft.released_rules,
        ),
    )


def apply_change(
    world: WorldProposal, rules: list[RuleP], change: WorldChange
) -> tuple[WorldProposal, frozenset[str]]:
    """Merges a change into the world (G1). Each record it gives replaces the one with its id
    and is otherwise added; each record it removes goes; and everything it leaves out stays
    exactly as it was, so no secret or clue is lost to a model that copies the world back badly
    (N7). `rules` are the rules as they hold now (`current_rules`), as the model saw them.

    G7: a fixed rule goes only when the change lists it in `dropped_rule_ids`, however the rest
    of the change reads. An open rule also goes when the change removes it, or removes every kind
    it is about. A text or list the change leaves empty is unchanged, so a change can't clear one.

    Returns the merged world and the ids of the rules the change dropped, so a starter's rule
    among them is released for this story (G7)."""
    change = _with_old_ids(world, rules, change)
    removed: dict[str, set[str]] = {}
    for removal in change.removed:
        if key := slug(removal.id):
            for section in _sections(world, rules, removal.section, key):
                removed.setdefault(section, set()).add(key)
    dropped = {key for rule_id in change.dropped_rule_ids if (key := slug(rule_id))}
    gone_kinds = removed.get("extraordinary", set())
    removed["rules"] = dropped | {
        slug(rule.id)
        for rule in rules
        if not rule.fixed
        and (
            slug(rule.id) in removed.get("rules", set())
            or (rule.about and {slug(kind) for kind in rule.about} <= gone_kinds)
        )
    }

    merged: dict[str, object] = {}
    for section in WORLD_SECTIONS:
        merged[section] = _merged(
            _records(world, rules, section), getattr(change, section), removed.get(section, set())
        )
    for name in ("title", "genre", "tone", "era", "summary"):
        if text := getattr(change, name).strip():
            merged[name] = text
    for name in ("nature", "norms", "known_facts"):
        if lines := [line for line in getattr(change, name) if line.strip()]:
            merged[name] = lines
    for name in ("calendar", "travel", "medicine", "opening", "several_partners", "unions"):
        if (part := getattr(change, name)) is not None:
            merged[name] = part
    merged["dropped_rule_ids"] = []
    let_go = frozenset(rule.id for rule in rules if slug(rule.id) in dropped)
    return world.model_copy(update=merged), let_go


def _records(world: WorldProposal, rules: list[RuleP], section: str) -> list:
    return rules if section == "rules" else getattr(world, section)


def _merged(current: list, given: list, gone: set[str]) -> list:
    """One list with the change's records merged in by id, keeping the order. A record both
    removed and given again is changed in place, as a rewritten fixed rule is."""
    gone = gone - {slug(record.id) for record in given}
    records = [record for record in current if slug(record.id) not in gone]
    for record in given:
        at = _find(records, slug(record.id))
        if at is None:
            records.append(record)
        else:
            records[at] = record
    return records


def _find(records: list, key: str, label=lambda record: record.id) -> int | None:
    if not key:
        return None
    for at, record in enumerate(records):
        if slug(label(record)) == key:
            return at
    return None


def _label(record) -> str:
    """What a record is called, in the lists whose records have a name of some kind."""
    for field in ("name", "kind", "title", "question"):
        if text := getattr(record, field, ""):
            return text
    return ""


def _with_old_ids(world: WorldProposal, rules: list[RuleP], change: WorldChange) -> WorldChange:
    """The change with each record it gives under a new id, but with the name of a record the
    world has, back on that record's id, and every reference in the change to the new id moved
    with it. So a record the model re-ids by mistake replaces the one it means, instead of
    joining it as a twin, and references to it, old and new, still hold."""
    known = {slug(r.id) for section in WORLD_SECTIONS for r in _records(world, rules, section)}
    aliases: dict[str, str] = {}
    for section in WORLD_SECTIONS:
        current = _records(world, rules, section)
        for record in getattr(change, section):
            key = slug(record.id)
            if not key or key in known:
                continue
            at = _find(current, slug(_label(record)), _label)
            if at is not None:
                aliases[key] = current[at].id
    if not aliases:
        return change
    return WorldChange.model_validate(_remapped(change.model_dump(mode="json"), aliases))


def _remapped(value, aliases: dict[str, str], key: str = ""):
    """`value` with every id in it, and every reference to one, renamed by `aliases`."""
    if isinstance(value, dict):
        return {k: _remapped(v, aliases, k) for k, v in value.items()}
    if isinstance(value, list):
        return [_remapped(item, aliases, key) for item in value]
    is_reference = key == "id" or key == "about" or key.endswith(("_id", "_ids"))
    if is_reference and isinstance(value, str):
        return aliases.get(slug(value), value)
    return value


def _sections(world: WorldProposal, rules: list[RuleP], named: str, key: str) -> tuple[str, ...]:
    """The list a removal names, also in the singular ("place"). Failing that, the one list
    that has a record with this id; when none or several do, the removal names nothing."""
    named = slug(named)
    for section in (named, f"{named}s"):
        if section in WORLD_SECTIONS:
            return (section,)
    holding = tuple(
        section
        for section in WORLD_SECTIONS
        if _find(_records(world, rules, section), key) is not None
    )
    return holding if len(holding) == 1 else ()


# The kind of record each of the character's lists holds.
_RECORD = {
    section: get_args(CharacterProposal.model_fields[section].annotation)[0]
    for section in CHARACTER_SECTIONS
}


def apply_character_change(
    character: CharacterProposal, change: CharacterChange
) -> CharacterProposal:
    """Merges a change into the character (G2), as `apply_change` does for the world: whatever
    the change leaves out stays exactly as it was, so a model that answers "call her Nora" with
    a name and nothing else renames her and loses nothing.

    A text the change leaves empty is unchanged, unless it lists it in `cleared`; a number or
    a whole list it leaves null is unchanged; and of the attributes, the tiers and the
    temperament only the parts it gives change. In the lists of records, one the change gives
    under a name the character already has (`CHARACTER_KEYS`) changes that record, and only in
    the fields it gives; one under a new name is added, when it has what a new record needs;
    and one it lists in `removed` goes, unless it gives it again."""
    merged: dict[str, object] = {}
    cleared = {slug(name).replace("-", "_") for name in change.cleared}
    for name in ("name", *CHARACTER_TEXTS):
        if text := getattr(change, name).strip():
            merged[name] = text
        elif name in cleared and name in CHARACTER_TEXTS:
            merged[name] = ""
    for name in (
        "age",
        "lifespan_years",
        "money",
        "aliases",
        "parent_ids",
        "goals",
        "backstory",
        "hidden_past",
    ):
        if (value := getattr(change, name)) is not None:
            merged[name] = value
    for name in ("attributes", "axes", "temperament"):
        if (part := getattr(change, name)) is not None:
            given = {
                field: value
                for field in type(part).model_fields
                if (value := getattr(part, field)) is not None and value != ""
            }
            merged[name] = getattr(character, name).model_copy(update=given)

    removed: dict[str, set[str]] = {}
    for removal in change.removed:
        if key := slug(removal.name):
            for section in _character_sections(character, removal.section, key):
                removed.setdefault(section, set()).add(key)
    for section in CHARACTER_SECTIONS:
        merged[section] = _merged_records(
            getattr(character, section),
            getattr(change, section),
            CHARACTER_KEYS[section],
            removed.get(section, set()),
            _RECORD[section],
        )
    return character.model_copy(update=merged)


def _merged_records(
    current: list, given: list, keys: tuple[str, ...], gone: set[str], kind: type
) -> list:
    """One of the character's lists with the change's records merged in, keeping the order."""
    again = {slug(getattr(record, key)) for record in given for key in keys}
    records = [
        record
        for record in current
        if not any(
            slug(getattr(record, key)) in gone and slug(getattr(record, key)) not in again
            for key in keys
        )
    ]
    for record in given:
        at = _held(records, record, keys)
        if at is not None:
            records[at] = _overlaid(records[at], record, kind, keys)
        elif (new := _new_record(record, kind, keys)) is not None:
            records.append(new)
    return records


def _held(records: list, record, keys: tuple[str, ...]) -> int | None:
    """Where the character holds the record a change gives: by the first of its keys that
    finds one, so a power is found by its id and, failing that, by its name."""
    for key in keys:
        at = _find(records, slug(getattr(record, key)), lambda held, key=key: getattr(held, key))
        if at is not None:
            return at
    return None


def _overlaid(held, given, kind: type, keys: tuple[str, ...]):
    """The record the character holds with the fields the change gives. A field the change
    leaves out keeps its value, and so does one a record can't be without when the change
    gives it empty. A power found by its name keeps its id."""
    fields = {
        field: value
        for field in given.model_fields_set
        if field in kind.model_fields
        and not (
            (value := getattr(given, field)) == ""
            and (kind.model_fields[field].is_required() or field in keys)
        )
    }
    if len(keys) > 1 and slug(getattr(given, keys[0])) != slug(getattr(held, keys[0])):
        fields.pop(keys[0], None)
    return held.model_copy(update=fields)


def _new_record(given, kind: type, keys: tuple[str, ...]):
    """A record the change adds, or None when it lacks what a new record needs: a power with
    no name or no kind, a ladder position with no rung."""
    fields = {field: getattr(given, field) for field in given.model_fields_set}
    if len(keys) > 1 and not fields.get(keys[0]):
        fields[keys[0]] = slug(getattr(given, keys[-1]))
    if any(
        fields.get(name) == "" for name, field in kind.model_fields.items() if field.is_required()
    ):
        return None
    try:
        return kind(**fields)
    except ValidationError:
        return None


def _character_sections(character: CharacterProposal, named: str, key: str) -> tuple[str, ...]:
    """The list a removal names, also in the singular ("skill"). Failing that, the one list
    that holds a record by this name; when none or several do, the removal names nothing."""
    named = slug(named)
    for section in (named, f"{named}s"):
        if section in CHARACTER_SECTIONS:
            return (section,)
    holding = tuple(
        section
        for section in CHARACTER_SECTIONS
        if any(
            slug(getattr(record, field)) == key
            for record in getattr(character, section)
            for field in CHARACTER_KEYS[section]
        )
    )
    return holding if len(holding) == 1 else ()


def _player_rules(edits: list[RuleEdit], current: list[RuleP]) -> list[RuleP]:
    by_id = {r.id: r for r in current}
    used: set[str] = set()
    rules = []
    for edit in edits:
        text = " ".join(edit.text.split())
        if not text:
            continue
        known = by_id.get(edit.id or "")
        rule_id = known.id if known is not None and known.id not in used else None
        if rule_id is None:
            base = slug(edit.id or "") or slug(text)[:40].strip("-") or "rule"
            rule_id, n = base, 2
            while rule_id in used or rule_id in by_id:
                rule_id, n = f"{base}-{n}", n + 1
        used.add(rule_id)
        rules.append(
            RuleP(
                id=rule_id,
                text=text,
                fixed=edit.fixed,
                topic=known.topic if known is not None else RuleP.model_fields["topic"].default,
                about=known.about if known is not None else [],
            )
        )
    return rules


def _released_by(template: PremiseTemplate | None, rules: list[RuleP]) -> frozenset[str]:
    """G7: the template rules the player removed, rewrote or opened up. A rule that says the
    template's own words in another of the app's languages isn't rewritten (S10): a draft made
    before the template spoke its language holds it in English."""
    if template is None:
        return frozenset()
    by_id = {r.id: r for r in rules}
    return frozenset(
        rule.id
        for rule in template.rules
        if rule.id not in by_id
        or not by_id[rule.id].fixed
        or " ".join(by_id[rule.id].text.split()) not in wordings(rule.text)
    )


def _with_world(proposal: DraftProposal, **changes: object) -> DraftProposal:
    return DraftProposal(
        world=proposal.world.model_copy(update=changes), character=proposal.character
    )


def own_words(before: list[str], after: list[str]) -> list[str]:
    """What the player wrote themselves when they rewrote a summary: a line that is new, whole,
    and of a line they only changed, the words it didn't have. The drafter's words in a line
    the player touched are still the drafter's, so they name nothing (G1)."""
    had = [{core(word) for word in WORD.findall(line)} for line in before]
    theirs: list[str] = []
    for line in after:
        if line in before:
            continue
        words = WORD.findall(line)
        cores = {core(word) for word in words}
        kept = max(had, key=lambda old: len(cores & old), default=set())
        if 2 * len(cores & kept) > len(cores):
            words = [word for word in words if core(word) not in kept]
        if words:
            theirs.append(" ".join(words))
    return theirs


def _on_time(draft: Draft, words: Iterable[str]) -> Draft:
    """E2, G1: a deadline comes when the player's own words say it does. The drafter splits a
    deadline into steps of so many hours, and their sum can miss the time the player gave ("in
    3 days", drafted as four steps of a day); so where `words` set a time for a deadline
    (`clock_times`), that time is spread over the steps the drafter wrote. It is done once, as
    the words are said, on the draft's own record: the premise at the first draft and a
    request at its change, so a deadline the player moves later stays where they moved it."""
    state = draft.state()
    times: dict[str, int] = {}
    for text in words:
        times |= clock_times(state, text, draft.language)
    world = draft.proposal.world
    paced: dict[int, ClockP] = {}
    for clock, proposed in zip(state.clocks.values(), drafted_clocks(world), strict=True):
        if clock.id in times and clock.remaining:
            hours = times[clock.id] / HOUR / clock.remaining
            paced[id(proposed)] = proposed.model_copy(update={"step_every_hours": hours})
    if not paced:
        return draft
    clocks = [paced.get(id(clock), clock) for clock in world.clocks]
    return replace(draft, proposal=_with_world(draft.proposal, clocks=clocks))


def _noting(draft: Draft, words: Iterable[str], plainly: bool = False) -> Draft:
    """G1: the draft after a change the player asked for in `words`, their own. It keeps the
    keys of the openers those words named and of the ones it had that are still there. The
    words themselves are not kept. `plainly` is for words asked at the row of what the
    character is after (`openers.names`)."""
    state = draft.state()
    told = carried(state, draft.told, draft.language)
    named = named_by(state, "\n".join(words), draft.language, plainly=plainly)
    return _telling(draft, told | named)


def _telling(draft: Draft, told: frozenset[str]) -> Draft:
    """The draft keeping `told`, the keys of the openers the player's words named, with the
    state it has already built."""
    if told == draft.told:
        return draft
    noted = replace(draft, told=told)
    object.__setattr__(noted, "_state", draft.state())
    return noted


def _clean_lines(lines: list[str]) -> list[str]:
    return [" ".join(line.split()) for line in lines if line.strip()]


def _gift_hint(draft: Draft) -> GiftStrength | None:
    if draft.gift is not None:
        return draft.gift
    template = draft.template
    return template.gift if template is not None else None

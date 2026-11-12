"""Drafting a world and a character from a premise, revising it in plain words and editing it
directly (G1, G2, S1). Plain Python on the model layer, with no Django (B4).

A `Draft` holds only inputs: the model's latest proposal and what the player set up. Its world
state is a pure function of them (`Draft.state()`), so a revision changes one part of the
proposal and code re-decides everything else, the same way every time. A change to the world
comes back as only what it touches (`WorldChange`), which code merges in (`apply_change`); a
change to the character comes back as the whole character, which is small. Every proposal is
cleaned of real people and organisations before it is kept (G12, `real_names`).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from engine.context import Language
from engine.state import GiftStrength, PhysicsMode, WorldState
from graph.drafting.assemble import DraftOptions, assemble, slug
from graph.drafting.catalog import PremiseTemplate, starter, wordings
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
    WORLD_SECTIONS,
    CharacterProposal,
    DraftProposal,
    RuleP,
    WorldChange,
    WorldProposal,
)
from graph.drafting.view import character_lines, gift_strength, public_rules, world_lines
from graph.llm import ModelClient, Node, Prompt

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


@dataclass(frozen=True)
class RuleEdit:
    """A rule as the player set it in the advanced fields. A rule without an id is new."""

    text: str
    fixed: bool
    id: str | None = None


@dataclass(frozen=True)
class Edits:
    """Direct edits (API.md `PATCH /v1/drafts/{id}`). `None` leaves a part as it is."""

    world_lines: list[str] | None = None
    character_lines: list[str] | None = None
    rules: list[RuleEdit] | None = None
    physics: PhysicsMode | None = None
    gift: GiftStrength | None = None
    rating: str | None = None


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


async def revise(llm: ModelClient, draft: Draft, target: Target, instruction: str) -> Draft:
    """A change in plain words, such as "add hidden vampires" (G1, G2)."""
    if target == "world":
        return await _revise_world(llm, draft, instruction)
    return await _revise_character(llm, draft, instruction)


@dataclass(frozen=True)
class EditPlan:
    """Direct edits with the code-only changes made (`plan_edit`), and what is left for the
    model: the requests that make the world or the character match the player's edits."""

    draft: Draft
    world_asks: tuple[str, ...] = ()
    character_asks: tuple[str, ...] = ()
    forced_rules: tuple[RuleP, ...] | None = None

    @property
    def needs_model(self) -> bool:
        return bool(self.world_asks or self.character_asks)


def plan_edit(draft: Draft, edits: Edits) -> EditPlan:
    """Physics, a rule's fixed flag, `gift: none` and raising the rating are code alone;
    rewritten summary lines, rewritten rules, a new gift strength and lowering the rating to Teen
    need the model to make the world or the character match, in one call for each
    (`finish_edit`)."""
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
    if edits.world_lines is not None:
        before = world_lines(state, draft.language)
        after = _clean_lines(edits.world_lines)
        if after != before:
            world_asks.append(lines_instruction("world", before, after))
    if edits.character_lines is not None:
        before = character_lines(state, draft.language)
        after = _clean_lines(edits.character_lines)
        if after != before:
            character_asks.append(lines_instruction("character", before, after))
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
    )


async def finish_edit(llm: ModelClient, plan: EditPlan) -> Draft:
    """The model's part of a direct edit. Makes no call when the plan doesn't need one."""
    draft = plan.draft
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
    return draft


async def edit(llm: ModelClient, draft: Draft, edits: Edits) -> Draft:
    """Direct edits (API.md `PATCH /v1/drafts/{id}`): `plan_edit`, then `finish_edit`."""
    return await finish_edit(llm, plan_edit(draft, edits))


async def _revise_world(llm: ModelClient, draft: Draft, instruction: str) -> Draft:
    state = draft.state()
    change = await llm.structured(
        Node.DRAFTER, _revise_prompt(draft, state, "world", instruction), WorldChange
    )
    world, let_go = apply_change(draft.proposal.world, current_rules(state), change)
    world = without_real_names(world)
    template_ids = draft.template.rule_ids if draft.template else frozenset()
    return replace(
        draft,
        proposal=DraftProposal(world=world, character=draft.proposal.character),
        released_rules=draft.released_rules | (let_go & template_ids),
    )


async def _revise_character(llm: ModelClient, draft: Draft, instruction: str) -> Draft:
    state = draft.state()
    character = await llm.structured(
        Node.DRAFTER, _revise_prompt(draft, state, "character", instruction), CharacterProposal
    )
    character = without_real_names(character)
    return replace(draft, proposal=DraftProposal(world=draft.proposal.world, character=character))


def _revise_prompt(draft: Draft, state: WorldState, target: Target, instruction: str) -> Prompt:
    return Prompt.build(
        system_prompt(draft.rating, draft.language),
        revise_prompt(
            draft.premise,
            draft.proposal,
            state,
            target=target,
            instruction=instruction,
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
    for name in ("calendar", "travel", "medicine", "opening"):
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


def _clean_lines(lines: list[str]) -> list[str]:
    return [" ".join(line.split()) for line in lines if line.strip()]


def _gift_hint(draft: Draft) -> GiftStrength | None:
    if draft.gift is not None:
        return draft.gift
    template = draft.template
    return template.gift if template is not None else None

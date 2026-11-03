"""Drafting a world and a character from a premise, revising it in plain words and editing it
directly (G1, G2, S1). Plain Python on the model layer, with no Django (B4).

A `Draft` holds only inputs: the model's latest proposal and what the player set up. Its world
state is a pure function of them (`Draft.state()`), so a revision replaces one part of the
proposal and code re-decides everything else, the same way every time.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from engine.state import GiftStrength, PhysicsMode, WorldState
from graph.drafting.assemble import DraftOptions, assemble, slug
from graph.drafting.catalog import PremiseTemplate, starter
from graph.drafting.prompts import (
    current_rules,
    draft_prompt,
    gift_instruction,
    lines_instruction,
    revise_prompt,
    rules_instruction,
    system_prompt,
)
from graph.drafting.schema import CharacterProposal, DraftProposal, RuleP, WorldProposal
from graph.drafting.view import character_lines, gift_strength, world_lines
from graph.llm import ModelClient, Node, Prompt

Target = Literal["world", "character"]


@dataclass(frozen=True)
class Draft:
    """A draft's inputs. `released_rules` are the starter template's rules the player let go of
    while setting up the story (G7)."""

    premise: str
    proposal: DraftProposal
    rating: str = "teen"
    premise_id: str | None = None
    physics: PhysicsMode = PhysicsMode.FUN_FIRST
    gift: GiftStrength | None = None
    released_rules: frozenset[str] = frozenset()

    @property
    def template(self) -> PremiseTemplate | None:
        found = starter(self.premise_id) if self.premise_id else None
        return found.template if found is not None else None

    def options(self) -> DraftOptions:
        return DraftOptions(
            premise=self.premise,
            physics=self.physics,
            gift=self.gift,
            template=self.template,
            released_rules=self.released_rules,
        )

    def state(self) -> WorldState:
        return assemble(self.proposal.world, self.proposal.character, self.options())


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


async def create(
    llm: ModelClient,
    premise: str,
    *,
    rating: str,
    premise_id: str | None = None,
    physics: PhysicsMode = PhysicsMode.FUN_FIRST,
    gift: GiftStrength | None = None,
) -> Draft:
    """The first draft: the world, then the character in it, in one model call."""
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
    )
    prompt = Prompt.build(
        system_prompt(rating),
        draft_prompt(premise, template=draft.template, gift=_gift_hint(draft)),
    )
    proposal = await llm.structured(Node.DRAFTER, prompt, DraftProposal)
    world = proposal.world.model_copy(update={"dropped_rule_ids": []})
    return replace(draft, proposal=proposal.model_copy(update={"world": world}))


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
    """Physics, a rule's fixed flag and `gift: none` are code alone; rewritten summary lines,
    rewritten rules and a new gift strength need the model to make the world or the character
    match, in one call for each (`finish_edit`)."""
    state = draft.state()
    world_asks: list[str] = []
    character_asks: list[str] = []
    forced_rules: list[RuleP] | None = None

    if edits.physics is not None:
        draft = replace(draft, physics=edits.physics)
    if edits.rules is not None:
        current = current_rules(state)
        forced_rules = _player_rules(edits.rules, current)
        draft = replace(
            draft,
            proposal=_with_world(draft.proposal, rules=forced_rules),
            released_rules=draft.released_rules | _released_by(draft.template, forced_rules),
        )
        if [(r.id, r.text) for r in forced_rules] != [(r.id, r.text) for r in current]:
            world_asks.append(rules_instruction(forced_rules))
    if edits.world_lines is not None:
        before = world_lines(state)
        after = _clean_lines(edits.world_lines)
        if after != before:
            world_asks.append(lines_instruction("world", before, after))
    if edits.character_lines is not None:
        before = character_lines(state)
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
            # A direct edit is the player's own words: the rules stay exactly as written.
            about = {r.id: r.about for r in draft.proposal.world.rules}
            rules = [
                r.model_copy(update={"about": about.get(r.id, r.about)}) for r in plan.forced_rules
            ]
            draft = replace(draft, proposal=_with_world(draft.proposal, rules=rules))
    if plan.character_asks:
        draft = await _revise_character(llm, draft, "\n\n".join(plan.character_asks))
    return draft


async def edit(llm: ModelClient, draft: Draft, edits: Edits) -> Draft:
    """Direct edits (API.md `PATCH /v1/drafts/{id}`): `plan_edit`, then `finish_edit`."""
    return await finish_edit(llm, plan_edit(draft, edits))


async def _revise_world(llm: ModelClient, draft: Draft, instruction: str) -> Draft:
    state = draft.state()
    world = await llm.structured(
        Node.DRAFTER, _revise_prompt(draft, state, "world", instruction), WorldProposal
    )
    world = keep_fixed_rules(current_rules(state), world)
    dropped = frozenset(world.dropped_rule_ids)
    template_ids = draft.template.rule_ids if draft.template else frozenset()
    world = world.model_copy(update={"dropped_rule_ids": []})
    return replace(
        draft,
        proposal=DraftProposal(world=world, character=draft.proposal.character),
        released_rules=draft.released_rules | (dropped & template_ids),
    )


async def _revise_character(llm: ModelClient, draft: Draft, instruction: str) -> Draft:
    state = draft.state()
    character = await llm.structured(
        Node.DRAFTER, _revise_prompt(draft, state, "character", instruction), CharacterProposal
    )
    return replace(draft, proposal=DraftProposal(world=draft.proposal.world, character=character))


def _revise_prompt(draft: Draft, state: WorldState, target: Target, instruction: str) -> Prompt:
    return Prompt.build(
        system_prompt(draft.rating),
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


def keep_fixed_rules(previous: list[RuleP], world: WorldProposal) -> WorldProposal:
    """G7: a revision keeps every fixed rule it doesn't explicitly drop, however forgetful the
    model is."""
    ids = {r.id for r in world.rules}
    dropped = set(world.dropped_rule_ids)
    kept = [r for r in previous if r.fixed and r.id not in ids and r.id not in dropped]
    if not kept:
        return world
    return world.model_copy(update={"rules": [*world.rules, *kept]})


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
    """G7: the template rules the player removed, rewrote or opened up."""
    if template is None:
        return frozenset()
    by_id = {r.id: r for r in rules}
    return frozenset(
        rule.id
        for rule in template.rules
        if rule.id not in by_id
        or not by_id[rule.id].fixed
        or " ".join(by_id[rule.id].text.split()) != rule.text
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

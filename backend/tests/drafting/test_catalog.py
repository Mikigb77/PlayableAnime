"""The starter premises (S1) and the rules their genres fix (G7, G8, G18, G22, G23).

Whatever the model proposes for a starter premise, the drafted bible keeps the genre: here every
starter is drafted from the opposite genre's sample, from a bare schema filler, and from a
proposal that tries to drop every rule.
"""

import re

import pytest

from engine.state import GiftStrength, Prevalence
from graph.drafting import samples
from graph.drafting.assemble import HUMAN_PEAK, DraftOptions, assemble
from graph.drafting.catalog import STARTER_PREMISES, starter
from graph.drafting.schema import DraftProposal, ExtraordinaryP, RuleP
from graph.drafting.view import gift_strength, world_lines
from graph.llm import fill_schema

FLAGSHIP_GENRES = {"Cultivation", "Knights and aura", "Races and monsters", "Reincarnation"}


def _filler() -> DraftProposal:
    return DraftProposal.model_validate(fill_schema(DraftProposal.model_json_schema()))


def _rebel(grounded: bool) -> DraftProposal:
    """A proposal that drops every rule and claims the opposite of the genre."""
    proposal = samples.cultivation() if grounded else samples.naples()
    world = proposal.world.model_copy(
        update={
            "rules": [RuleP(id="anything-goes", text="Anything goes.", fixed=False)],
            "extraordinary": [ExtraordinaryP(id="qi", kind="qi", prevalence="common")]
            if grounded
            else [
                ExtraordinaryP(
                    id="nothing", kind="magic or anything supernatural", prevalence="none"
                )
            ],
            "dropped_rule_ids": [r.id for p in STARTER_PREMISES for r in p.template.rules],
        }
    )
    return DraftProposal(world=world, character=proposal.character)


def _proposals(grounded: bool) -> dict[str, DraftProposal]:
    return {
        "opposite sample": samples.cultivation() if grounded else samples.naples(),
        "filler": _filler(),
        "rebel": _rebel(grounded),
    }


def test_flagship_genres_come_first():
    flags = [p.flagship for p in STARTER_PREMISES]

    assert flags == sorted(flags, reverse=True)
    assert {p.genre for p in STARTER_PREMISES if p.flagship} == FLAGSHIP_GENRES


def test_every_flagship_genre_has_more_than_one_starter():
    for genre in FLAGSHIP_GENRES:
        assert sum(p.genre == genre for p in STARTER_PREMISES) >= 2, genre


def test_every_starter_speaks_to_the_player_as_you():
    # The cover's brief says the premise calls the main character "you" (media.premise_covers).
    for premise in STARTER_PREMISES:
        assert re.search(r"\byou\b", premise.premise, re.IGNORECASE), premise.id


def test_the_catalog_covers_the_genres_beyond_the_flagship():
    genres = {p.genre for p in STARTER_PREMISES if not p.flagship}

    assert {"Grounded crime", "Science fiction", "Hidden supernatural"} <= genres
    naples = starter("naples-vendetta")
    assert naples is not None and "Naples" in naples.premise
    assert naples.template.grounded_rule_id is not None


def test_premises_have_the_api_shape_and_unique_ids():
    ids = [p.id for p in STARTER_PREMISES]

    assert len(ids) == len(set(ids))
    for premise in STARTER_PREMISES:
        public = premise.public()
        assert set(public) == {
            "id",
            "title",
            "genre",
            "tagline",
            "premise",
            "flagship",
            "cover_url",
        }
        assert all(public[k] for k in ("id", "title", "genre", "tagline", "premise"))
        assert starter(premise.id) is premise
    assert starter("no-such-premise") is None


def test_template_rules_are_fixed_and_their_kinds_point_at_them():
    for premise in STARTER_PREMISES:
        template = premise.template
        assert all(rule.fixed for rule in template.rules), premise.id
        for kind in template.extraordinary:
            assert set(kind.rule_ids) <= template.rule_ids, premise.id
        if template.grounded_rule_id is not None:
            assert template.grounded_rule_id in template.rule_ids


@pytest.mark.parametrize("premise", STARTER_PREMISES, ids=lambda p: p.id)
def test_every_starter_drafts_into_a_bible_that_keeps_its_genre(premise):
    template = premise.template
    grounded = template.grounded_rule_id is not None
    for name, proposal in _proposals(grounded).items():
        state = assemble(
            proposal.world,
            proposal.character,
            DraftOptions(premise=premise.premise, template=template),
        )
        bible = state.bible
        rules = {r.id: r for r in bible.rules}
        where = f"{premise.id}, {name}"

        # G7: the genre's fixed rules, word for word.
        for rule in template.rules:
            assert rule.id in rules, where
            assert (rules[rule.id].text, rules[rule.id].fixed) == (rule.text, True), where
        # G6, G7: the kinds the genre fixes, at its prevalence, tied to its rules.
        kinds = {k.id: k for k in bible.extraordinary}
        for required in template.extraordinary:
            assert kinds[required.id].prevalence is required.prevalence, where
            assert set(required.rule_ids) <= set(kinds[required.id].rule_ids), where
        # G8: a grounded genre has nothing extraordinary, nobody with a power, nobody past a
        # real person, and no power ladder.
        if grounded:
            assert bible.grounded, where
            assert all(k.prevalence is Prevalence.NONE for k in bible.extraordinary), where
            for character in state.characters.values():
                assert character.sheet.powers == [], where
                attributes = character.sheet.attributes.model_dump().values()
                assert max(attributes) <= HUMAN_PEAK, where
            assert bible.ladders == [], where
        elif any(k.prevalence is not Prevalence.NONE for k in template.extraordinary):
            assert not bible.grounded, where
            assert not any("Grounded" in r.text for r in bible.rules), where
        # G18: the genre's ladder when the proposal brings none.
        if template.ladder is not None and not proposal.world.ladders:
            assert [ladder.id for ladder in bible.ladders] == [template.ladder.id], where
        # G23: the genre's peoples.
        people = {p.name for p in bible.peoples}
        assert {p.name for p in template.peoples} <= people, where
        # G1: the summary leads with what the genre fixes.
        assert world_lines(state), where


@pytest.mark.parametrize("premise_id", ["old-net", "war-frame"])
def test_science_past_human_limits_has_no_magic_and_is_not_grounded(premise_id):
    # G8: implants or a bonded war-frame go past what a real person could do, so the world isn't
    # grounded, but magic still doesn't exist in it, whatever a grounded proposal says.
    template = starter(premise_id).template
    proposal = samples.naples()
    state = assemble(proposal.world, proposal.character, DraftOptions(template=template))
    kinds = {k.id: k.prevalence for k in state.bible.extraordinary}

    assert kinds["supernatural"] is Prevalence.NONE
    assert [k for k, prevalence in kinds.items() if prevalence is not Prevalence.NONE] == [
        next(k.id for k in template.extraordinary if k.prevalence is not Prevalence.NONE)
    ]
    assert not state.bible.grounded
    assert template.grounded_rule_id is None


def test_a_starter_that_grants_a_gift_sets_its_strength():
    proposal = samples.cultivation()
    for premise_id, strength in (
        ("three-heartbeats", GiftStrength.OVERPOWERED),
        ("demon-lord-accountant", GiftStrength.SMALL),
        ("seven-day-villainess", GiftStrength.SMALL),
        ("what-things-remember", GiftStrength.RARE),
    ):
        template = starter(premise_id).template
        state = assemble(proposal.world, proposal.character, DraftOptions(template=template))
        assert gift_strength(state) is strength, premise_id

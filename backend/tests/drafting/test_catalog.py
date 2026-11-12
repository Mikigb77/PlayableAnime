"""The starter premises (S1) and the rules their genres fix (G7, G8, G18, G22, G23).

Whatever the model proposes for a starter premise, the drafted bible keeps the genre: here every
starter is drafted from the opposite genre's sample, from a bare schema filler, and from a
proposal that tries to drop every rule.
"""

import re

import pytest

from engine.context import Language
from engine.state import GiftStrength, Prevalence
from graph.drafting import samples
from graph.drafting.assemble import GROUNDED_RULE_TEXTS, HUMAN_PEAK, DraftOptions, assemble
from graph.drafting.catalog import STARTER_PREMISES, starter, worded, wordings
from graph.drafting.catalog_ca import CATALAN, TEMPLATE_CATALAN
from graph.drafting.catalog_es import SPANISH, TEMPLATE_SPANISH
from graph.drafting.prompts import template_block
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
    """`grounded`: the genre has no magic, so the opposite sample and the rebel bring qi."""
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


@pytest.mark.parametrize("language", list(Language), ids=lambda language: language.value)
@pytest.mark.parametrize("premise", STARTER_PREMISES, ids=lambda p: p.id)
def test_every_starter_drafts_into_a_bible_that_keeps_its_genre(premise, language):
    # S10: in the language the story is drafted in, as `chain.Draft.template` gives it.
    template = premise.template.in_language(language)
    grounded = template.grounded_rule_id is not None
    exclusive = template.exclusive_rule_id is not None
    for name, proposal in _proposals(grounded or exclusive).items():
        state = assemble(
            proposal.world,
            proposal.character,
            DraftOptions(premise=premise.premise, template=template, language=language),
        )
        bible = state.bible
        rules = {r.id: r for r in bible.rules}
        where = f"{premise.id}, {name}"

        # G7: the genre's fixed rules, word for word, in the story's language.
        for rule, english in zip(template.rules, premise.template.rules, strict=True):
            assert rule.id in rules, where
            assert (rules[rule.id].text, rules[rule.id].fixed) == (rule.text, True), where
            assert rule.text == worded(english.text, language), where
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
            said = set(GROUNDED_RULE_TEXTS.values())
            assert not any(r.text in said or "Grounded" in r.text for r in bible.rules), where
        # G8: where the genre's kinds are the only ones, the model's own kinds, their powers and
        # any power ladder of theirs go.
        if exclusive:
            assert set(kinds) == {k.id for k in template.extraordinary}, where
            if template.ladder is None:
                assert bible.ladders == [], where
        # G18: the genre's ladder when the proposal brings none.
        if template.ladder is not None and not proposal.world.ladders:
            assert bible.ladders == [template.ladder], where
        # G23: the genre's peoples.
        people = {p.name for p in bible.peoples}
        assert {p.name for p in template.peoples} <= people, where
        # G1: the summary leads with what the genre fixes.
        assert world_lines(state), where


@pytest.mark.parametrize("premise_id", ["old-net", "war-frame"])
@pytest.mark.parametrize("sample", ["naples", "cultivation"])
def test_science_past_human_limits_has_no_magic_and_is_not_grounded(premise_id, sample):
    # G8: implants or a bonded war-frame go past what a real person could do, so the world isn't
    # grounded, but nothing else extraordinary exists in it, whether the proposal is grounded or
    # brings qi cultivation, realms and a time power.
    template = starter(premise_id).template
    proposal = getattr(samples, sample)()
    state = assemble(proposal.world, proposal.character, DraftOptions(template=template))
    kinds = {k.id: k.prevalence for k in state.bible.extraordinary}
    own = next(k.id for k in template.extraordinary if k.prevalence is not Prevalence.NONE)

    assert kinds == {"supernatural": Prevalence.NONE, own: kinds[own]}
    assert kinds[own] is not Prevalence.NONE
    assert not state.bible.grounded
    assert state.bible.ladders == []
    # The sample's time stop came from a kind that doesn't exist here.
    assert state.characters["player"].sheet.powers == []
    assert not any("Qi" in rule.text for rule in state.bible.rules)


def test_letting_the_no_magic_rule_go_lets_other_kinds_in():
    # G7: once the player lets the rule go, the genre no longer limits what exists.
    template = starter("old-net").template
    proposal = samples.cultivation()
    options = DraftOptions(template=template, released_rules=frozenset({"no-supernatural"}))
    state = assemble(proposal.world, proposal.character, options)

    kinds = {k.id: k.prevalence for k in state.bible.extraordinary}
    assert kinds["qi"] is Prevalence.COMMON and kinds["cybernetics"] is Prevalence.COMMON
    assert "supernatural" not in kinds


def test_the_prompt_says_a_genres_kinds_are_the_only_ones():
    old_net = starter("old-net").template
    assert "and no other extraordinary kinds." in template_block(old_net, frozenset())
    released = template_block(old_net, frozenset({"no-supernatural"}))
    assert "no other extraordinary kinds" not in released
    beast_tide = starter("beast-tide").template
    assert "no other extraordinary kinds" not in template_block(beast_tide, frozenset())


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


def _template_texts() -> set[str]:
    """Every text of a starter's template that the player reads."""
    texts: set[str] = set()
    for premise in STARTER_PREMISES:
        template = premise.template
        texts |= {rule.text for rule in template.rules}
        texts |= {kind.kind for kind in template.extraordinary}
        texts |= {kind.reach for kind in template.extraordinary if kind.reach}
        if template.ladder is not None:
            texts |= {template.ladder.name, *(rung.name for rung in template.ladder.rungs)}
        texts |= {people.name for people in template.peoples}
    return texts


@pytest.mark.parametrize(
    ("language", "words"), [(Language.ES, TEMPLATE_SPANISH), (Language.CA, TEMPLATE_CATALAN)]
)
def test_every_template_text_has_its_spanish_and_catalan(language, words):
    """S10: a starter's fixed rules, kinds, ladder and peoples are in the story's language like
    the rest of its world, so a new starter's template needs its Spanish in
    `graph.drafting.catalog_es` and its Catalan in `graph.drafting.catalog_ca`."""
    shared = {"aura", "Mithril", "humans", "Bronze"}  # words a language shares with English
    assert set(words) == _template_texts()
    for english, said in words.items():
        assert said.strip() and said == " ".join(said.split()), english
        assert said != english or english in shared, english
        assert worded(english, language) == said
        assert {english, said} <= wordings(said)
    # What isn't a template's stays as it is.
    assert worded("Anything goes.", language) == "Anything goes."
    assert wordings("Anything goes.") == {"Anything goes."}


def test_a_template_speaks_the_language_its_story_is_drafted_in():
    template = starter("beast-tide").template
    assert template.in_language(Language.EN) is template

    spanish = template.in_language(Language.ES)
    assert [r.text for r in spanish.rules] == [
        "Humanos, elfos, enanos y hombres bestia comparten este mundo, y los monstruos recorren "
        "sus tierras salvajes.",
        "La magia es real, y los monstruos la llevan en sus núcleos.",
    ]
    assert [k.kind for k in spanish.extraordinary] == ["magia"]
    assert spanish.ladder.name == "rangos de cazador"
    assert [r.name for r in spanish.ladder.rungs] == ["Hierro", "Bronce", "Plata", "Oro", "Mithril"]
    assert [p.name for p in spanish.peoples] == ["humanos", "elfos", "enanos", "hombres bestia"]
    catalan = starter("outer-disciple").template.in_language(Language.CA)
    assert [r.name for r in catalan.ladder.rungs][:2] == [
        "Condensació del Qi",
        "Establiment de la Base",
    ]
    assert catalan.extraordinary[0].reach == (
        "Reialmes des de la Condensació del Qi fins a l'Ànima Naixent i més enllà."
    )

    # Only the words change: ids, topics, tiers and everything else code goes by are the same.
    def bare(t):
        return (
            [(r.id, r.fixed, r.topic) for r in t.rules],
            [(k.id, k.prevalence, k.rule_ids) for k in t.extraordinary],
            t.ladder.model_dump(exclude={"name": True, "rungs": {"__all__": {"name"}}}),
            [p.model_dump(exclude={"name"}) for p in t.peoples],
            (t.grounded_rule_id, t.exclusive_rule_id, t.gift, t.notes),
        )

    assert bare(spanish) == bare(template)
    # The starter's own template is as it was.
    assert template.ladder.rungs[0].name == "Iron" and template.peoples[1].name == "elves"


def test_the_drafter_is_given_the_template_in_the_storys_language():
    template = starter("ashen-squire").template
    english = template_block(template, frozenset())
    assert "aura-exists: Aura is real: trained knights draw it" in english
    assert "The aura ranks (id aura-ranks): Squire, Knight, Aura Master, Sword Saint." in english

    spanish = template_block(template.in_language(Language.ES), frozenset())
    assert "aura-exists: El aura es real: los caballeros entrenados la invocan" in spanish
    assert "(id aura-ranks): Escudero, Caballero, Maestro del Aura, Santo de la Espada." in spanish
    assert "Aura is real" not in spanish and "Squire" not in spanish


@pytest.mark.parametrize(
    ("language", "translations"), [(Language.ES, SPANISH), (Language.CA, CATALAN)]
)
def test_every_starter_has_its_spanish_and_catalan(language, translations):
    """S10: Discover shows each starter in the app's language, so a new starter needs its Spanish
    in `graph.drafting.catalog_es` and its Catalan in `graph.drafting.catalog_ca`."""
    shared = {"Mecha", "Cyberpunk"}  # the genre names both borrow as they are
    assert set(translations) == {premise.id for premise in STARTER_PREMISES}
    for premise in STARTER_PREMISES:
        translated = premise.text(language)
        assert translated == translations[premise.id]
        for field in ("title", "genre", "tagline", "premise"):
            words = getattr(translated, field)
            assert words.strip(), (premise.id, field)
            assert words != getattr(premise, field) or words in shared, (premise.id, field)
            if language is Language.CA:
                assert words != getattr(SPANISH[premise.id], field) or words in shared
        assert premise.text(Language.EN).premise == premise.premise

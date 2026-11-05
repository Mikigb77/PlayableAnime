"""F3, G12 and the ratings table's lines, enforced in code (`engine.limits`)."""

import pytest

from engine import limits
from engine.context import Rating
from engine.contracts import ActionKind, Intent, IntentStep, StateDelta
from engine.contracts.delta import CharacterChange, FactionChange
from engine.contracts.intent import Aim, Beat, Plausibility, StepFacts, Stranger
from engine.limits import Intimacy, LimitCategory
from engine.samples import cultivation_world, grounded_world
from engine.state.cast import Character


def step(text: str, verb: str = "act", **fields) -> IntentStep:
    return IntentStep(
        text=text, verb=verb, kind=ActionKind.INSTANT, proposed_duration_s=2, **fields
    )


def person(**fields) -> Character:
    fields.setdefault("id", "lia")
    fields.setdefault("name", "Lia")
    return Character(**fields)


def with_character(state, character: Character):
    state = state.model_copy(deep=True)
    state.characters[character.id] = character
    return state


# --- Who counts as an adult (F3) --------------------------------------------------------


def test_only_a_recorded_age_of_eighteen_or_more_counts():
    assert limits.is_adult(person(age=18))
    assert limits.adult_problem(person(age=17)) == "aged 17"
    assert limits.adult_problem(person()) == "no age recorded"


@pytest.mark.parametrize(
    "appearance",
    [
        "Looks about twelve, with a ribbon in her hair.",
        "A childlike body and a high voice.",
        "16, slight, black hair tied back.",
        "Wears a school uniform and pigtails.",
        "The body of a ten-year-old, the eyes of an old woman.",
        "A girl of fourteen in a red coat.",
        "A loli vampire with a parasol.",
        "She is 15 years old and small for it.",
        "Lia's fifteen, and quick with a knife.",
        "He just turned sixteen.",
    ],
)
def test_a_childlike_look_rules_out_romance_whatever_age_is_recorded(appearance):
    # A 500-year-old in a child's body is still a child's body (F3).
    assert limits.adult_problem(person(age=500, appearance=appearance)) == "described as childlike"


@pytest.mark.parametrize(
    "text",
    [
        "24, lean, dark hair combed back, a scar through one eyebrow.",
        "Fifties, broad, grey moustache, gold rings.",
        "A widow raising two children above the bakery.",
        "A ten-year-old scar runs across her jaw.",
        "A high school teacher with ink on her fingers.",
        "2 swords on her back, a mother of ten.",
        "In her late teens, quick to laugh.",
        "Appears 7 feet tall in her armour.",
        "Her daughter is 6 years old.",
        "Leads a body of 12 riders.",
        "She was 15 when the war came.",
        "Seems 3 times stronger than she looks.",
        "A face of 40 winters.",
    ],
)
def test_ordinary_adult_descriptions_pass(text):
    assert limits.is_adult(person(age=30, appearance=text, description=text))


# --- Romantic and sexual steps ----------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("kiss Mei", Intimacy.ROMANCE),
        ("flirt with the barmaid", Intimacy.ROMANCE),
        ("seduce the guard to get the key", Intimacy.ROMANCE),
        ("ask her to marry me", Intimacy.ROMANCE),
        ("have sex with Lia", Intimacy.SEXUAL),
        ("undress her slowly", Intimacy.SEXUAL),
        ("drag her into the alley and force myself on her", Intimacy.SEXUAL_VIOLENCE),
        ("rape the captive", Intimacy.SEXUAL_VIOLENCE),
        ("kneel and kiss the elder's hand", None),
        ("kiss the ring of the don", None),
        ("let my blade kiss his throat", None),
        ("visit my married sister", None),
        ("throw a stone at Zhao", None),
        ("grope her in the dark", Intimacy.SEXUAL),
        ("strip her naked", Intimacy.SEXUAL),
        ("fondle Lia", Intimacy.SEXUAL),
        ("strip them of their weapons", None),
        ("grope in the dark for the lever", None),
        ("grope my way along the wall", None),
        ("check the sex of the foal", None),
        ("bed them down in the barn", None),
        ("fondle the hilt of my sword", None),
    ],
)
def test_romantic_and_sexual_steps_are_recognised(text, kind):
    assert limits.intimacy(step(text)) is kind


def test_the_verb_and_beats_count_as_much_as_the_text():
    assert limits.intimacy(step("go over to her", verb="kiss")) is Intimacy.ROMANCE
    beats = [Beat(text="lean in"), Beat(text="kiss her")]
    assert limits.intimacy(step("go over to her", beats=beats)) is Intimacy.ROMANCE


def test_romance_with_a_known_minor_never_plays():
    state = cultivation_world()  # Zhao is 19, the player character Lin is 16
    state = with_character(state, person(id="mei", name="Mei", age=15))
    lin_player = state.player_id
    intent = Intent(steps=[step("kiss Mei", target_ids=["mei"])])

    hits = limits.check_action(state, intent, Rating.MATURE)

    assert {(h.category, h.subject) for h in hits} == {
        (LimitCategory.MINOR, lin_player),
        (LimitCategory.MINOR, "mei"),
    }


def test_a_minor_player_character_never_plays_romance_even_with_an_adult():
    state = cultivation_world()
    intent = Intent(steps=[step("kiss Zhao", target_ids=["zhao"])])

    hits = limits.check_action(state, intent, Rating.MATURE)

    assert [(h.category, h.subject) for h in hits] == [(LimitCategory.MINOR, state.player_id)]


def test_a_partner_with_no_recorded_age_never_plays_romance():
    state = with_character(grounded_world(), person(appearance="Thirties, red coat."))
    intent = Intent(steps=[step("kiss Lia", target_ids=["lia"])])

    [hit] = limits.check_action(state, intent, Rating.MATURE)

    assert hit.category is LimitCategory.MINOR and hit.detail == "no age recorded"


def test_an_opponent_counts_as_a_partner():
    state = with_character(grounded_world(), person(age=16))
    facts = StepFacts(opposition_ids=["lia"])
    intent = Intent(steps=[step("seduce the girl at the bar", facts=facts)])

    [hit] = limits.check_action(state, intent, Rating.MATURE)

    assert hit.subject == "lia"


def test_romance_between_recorded_adults_plays_in_both_ratings():
    state = with_character(grounded_world(), person(age=27, appearance="27, freckles."))
    intent = Intent(steps=[step("kiss Lia", target_ids=["lia"])])

    assert limits.check_action(state, intent, Rating.TEEN) == []
    assert limits.check_action(state, intent, Rating.MATURE) == []


def test_a_partner_the_story_doesnt_know_yet_is_left_to_the_narrator():
    # The narrator introduces them as an adult with an age; once known, the check holds them.
    intent = Intent(steps=[step("flirt with the barmaid", targets=["the barmaid"])])
    assert limits.check_action(grounded_world(), intent, Rating.MATURE) == []


def test_a_teen_story_goes_as_far_as_a_kiss():
    state = with_character(grounded_world(), person(age=27))
    sex = Intent(steps=[step("sleep with Lia", target_ids=["lia"])])
    assault = Intent(steps=[step("force myself on Lia", target_ids=["lia"])])

    [teen_sex] = limits.check_action(state, sex, Rating.TEEN)
    [teen_assault] = limits.check_action(state, assault, Rating.TEEN)

    assert teen_sex.category is LimitCategory.SEXUAL
    assert teen_assault.category is LimitCategory.SEXUAL_VIOLENCE
    # Mature plays both: sex fades out and sexual violence happens off the page (F2's table).
    assert limits.check_action(state, sex, Rating.MATURE) == []
    assert limits.check_action(state, assault, Rating.MATURE) == []


def test_the_gravest_hit_is_reported_first():
    hits = [
        limits.LimitHit(LimitCategory.REAL_PERSON),
        limits.LimitHit(LimitCategory.MINOR),
        limits.LimitHit(LimitCategory.SEXUAL),
    ]
    assert limits.gravest(hits).category is LimitCategory.MINOR
    assert limits.gravest([]) is None


def test_every_category_has_a_message_for_the_player():
    assert set(limits.MESSAGES) == set(LimitCategory)


# --- Real people and organisations (G12) ------------------------------------------------


@pytest.mark.parametrize(
    ("name", "entity"),
    [
        ("Taylor Swift", "Taylor Swift"),
        ("taylor swift's bodyguard", "Taylor Swift"),
        ("BEYONCÉ", "Beyonce"),
        ("Putin's guard", "Putin"),
        ("Kim Kardashian", "Kim Kardashian"),
        ("the FBI", "FBI"),
        ("the Gambino family", "Gambino family"),
        ("Google", "Google"),
        ("Microsoft founder Bill Gates", "Bill Gates"),  # the person wins over the company
    ],
)
def test_real_people_and_organisations_are_recognised(name, entity):
    assert limits.real_entity(name).name == entity


@pytest.mark.parametrize(
    "name",
    [
        "Elder Mo",
        "the Esposito family",
        "the Democratic Party of Mars",  # a story's own party, not the real one
        "FBI field office",  # a name that only mentions an agency is a story's own
        "Tesla's workshop",
        "Disneyland",
        "Napoleon",  # long-dead historical figures can appear (G12)
        "the Camorra",  # a kind of crime world, like "the mafia"
    ],
)
def test_fictional_and_historical_names_pass(name):
    assert limits.real_entity(name) is None


def test_a_step_at_a_real_person_never_plays():
    intent = Intent(steps=[step("punch Elon Musk", targets=["Elon Musk"])])

    [hit] = limits.check_action(grounded_world(), intent, Rating.MATURE)

    assert hit.category is LimitCategory.REAL_PERSON and hit.subject == "Elon Musk"


def test_a_stranger_who_is_a_real_person_never_plays():
    # F1, W1: a victim the scene hasn't named is made real, so a real name there is held too.
    stranger = Stranger(who="Elon Musk", plausibility=Plausibility.PLAUSIBLE)
    intent = Intent(steps=[step("stab a random man", aim=Aim.KILL, stranger=stranger)])

    [hit] = limits.check_action(grounded_world(), intent, Rating.MATURE)

    assert hit.category is LimitCategory.REAL_PERSON and hit.subject == "Elon Musk"


def test_a_real_person_named_after_their_company_never_plays():
    target = "the Google boss Sundar Pichai"
    intent = Intent(steps=[step(f"rob {target}", targets=[target])])

    [hit] = limits.check_action(grounded_world(), intent, Rating.MATURE)

    assert hit.subject == "Sundar Pichai"


def test_naming_a_real_organisation_in_an_action_is_a_backdrop():
    intent = Intent(steps=[step("call the FBI", targets=["the FBI"])])
    assert limits.check_action(grounded_world(), intent, Rating.MATURE) == []


def test_real_people_and_organisations_are_left_out_of_the_update():
    state = grounded_world()
    delta = StateDelta(
        characters=[
            CharacterChange(id="swift", name="Taylor Swift"),
            CharacterChange(id="carmine", name="Carmine Russo", aliases=["Joe Biden"]),
            CharacterChange(id="nino", name="Nino Greco", age=31),
        ],
        factions=[
            FactionChange(id="gambino", name="the Gambino family"),
            FactionChange(id="esposito", name="the FBI"),
            FactionChange(id="greco", name="the Greco crew"),
        ],
    )

    stripped, hits = limits.strip_real_entities(delta, state)

    assert [c.id for c in stripped.characters] == ["carmine", "nino"]
    assert stripped.characters[0].aliases == [] and stripped.characters[0].name == "Carmine Russo"
    assert [f.id for f in stripped.factions] == ["esposito", "greco"]
    assert stripped.factions[0].name is None  # a known faction keeps its old name
    assert [h.detail for h in hits] == [
        "a new character",
        "a renamed character",
        "a new faction",
        "a renamed faction",
    ]
    assert delta.characters[0].name == "Taylor Swift"  # the proposal itself is untouched


# --- Real-world harm instructions (F3) --------------------------------------------------


@pytest.mark.parametrize(
    ("text", "domain"),
    [
        (
            "Crush 500 grams of pseudoephedrine tablets, dissolve them in 200 ml of methanol, "
            "add red phosphorus and heat to 80°C.",
            "drugs",
        ),
        ("1. Get ammonium nitrate\n2. Mix it with fuel oil\n3. Pack it into a pipe", "weapons"),
        (
            "You type ' OR '1'='1 into the login and the exploit hands you the admin panel.",
            "hacking",
        ),
        ("```\nnmap -sS 10.0.0.1\n```\nThe scan lights up.", "hacking"),
    ],
)
def test_working_instructions_are_caught(text, domain):
    assert limits.harm_instructions(text) == domain


@pytest.mark.parametrize(
    "text",
    [
        "You cook a batch through the night; by dawn the trays glitter.",
        "You cook a 50 kg batch of meth, 90% pure, and the cartel pays double.",
        "You wire the bomb under the car and walk away. At noon the street shakes.",
        "From the ridge you watch the black powder smoke drift over 2 kg of rubble.",
        "Mix 3 grams of spirit grass with 20 ml of dew, heat it until it glows, and stir.",
        "You run the exploit and the bank's firewall folds like wet paper.",
        "- Run! she shouts.\n- Not without the payload.",
    ],
)
def test_know_how_told_as_an_outcome_passes(text):
    assert limits.harm_instructions(text) is None

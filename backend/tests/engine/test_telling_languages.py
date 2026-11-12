"""S10, G16, C6: the world tells a deed in the story's language.

The same facts pick the same kind of sentence in English, Spanish and Catalan, and each
language says it its own way. Rumors and grudges are kept as they were told, so a Spanish
story's are in Spanish from the day they start.
"""

import pytest

from engine import pipeline
from engine.base import HOUR
from engine.context import Language, StorySettings, TurnContext
from engine.contracts import ProposedDeed, Resolution
from engine.samples import cultivation_world
from engine.state import Character, CharacterStatus, DeathCertainty, Deed, Membership, Place
from engine.state.scene import Terms
from engine.world import telling
from engine.world.telling import (
    SOMEONE,
    account,
    bounty,
    found,
    garbled,
    listing,
    number,
    own_words,
    unexplained,
    with_word,
    wound_said,
)

from .test_world import deed_step, moved_on, rng, the_deed

EN, ES, CA = Language.EN, Language.ES, Language.CA
WELL = {EN: "the outer-court well", ES: "el pozo", CA: "el pou"}
HU = {EN: "Old Hu", ES: "el viejo Hu", CA: "el vell Hu"}
GRANARY = {EN: "the granary", ES: "el granero", CA: "el graner"}


def world(language: Language):
    """The sect's well, with names as a story in that language would have them: Old Hu, and
    Ilya, who is dead."""
    state = cultivation_world()
    state.places["well"].name = WELL[language]
    state.places["granary"] = Place(id="granary", name=GRANARY[language], kind="granary")
    state.characters["hu"] = Character(id="hu", name=HU[language], location_id="well")
    state.characters["ilya"] = Character(
        id="ilya",
        name="Ilya",
        location_id="well",
        status=CharacterStatus.DEAD,
        death_certainty=DeathCertainty.CONFIRMED,
    )
    return state


def deed(**facts) -> Deed:
    told = {"actor_id": "lin", "text": "x (it worked)", "turn": 1, "world_s": 0, "severity": 3}
    return Deed(id="d1", **(told | {"place_id": "well"} | facts))


def test_every_language_has_the_same_book():
    kinds = set(telling._BOOK[EN])
    for language in (ES, CA):
        assert set(telling._BOOK[language]) == kinds, language
        assert set(telling._WORDS[language]) == set(telling._WORDS[EN]), language
        assert len(telling._NUMBERS[language]) == len(telling._NUMBERS[EN]), language
        # "You" is said with the verb, so every kind of deed has its second person.
        assert all(verb.you for verb in telling._BOOK[language].values()), language
        assert set(telling.GARBLED_LEADS) == set(Language)


TOLD = [
    (
        {"kind": "kill", "victim_ids": ["ilya"]},
        "Lin Feng mató a Ilya en el pozo.",
        "Lin Feng va matar Ilya al pou.",
    ),
    (
        {"kind": "kill", "target_ids": ["zhao"]},  # nobody was harmed: an attempt
        "Lin Feng intentó matar a Zhao Kun en el pozo.",
        "Lin Feng va intentar matar Zhao Kun al pou.",
    ),
    (
        {"kind": "assault", "victim_ids": ["ilya", "zhao"]},  # one died of it and one lived
        "Lin Feng mató a Ilya e hirió a Zhao Kun en el pozo.",
        "Lin Feng va matar Ilya i va ferir Zhao Kun al pou.",
    ),
    (
        {"kind": "massacre", "victim_ids": ["v1", "v2", "v3"]},  # nobody the world can name
        "Lin Feng masacró a tres personas en el pozo.",
        "Lin Feng va massacrar tres persones al pou.",
    ),
    (
        {"kind": "massacre", "victim_ids": ["zhao", "hu", "v1", "v2"]},
        "Lin Feng masacró a Zhao Kun, al viejo Hu y a otras dos personas en el pozo.",
        "Lin Feng va massacrar Zhao Kun, el vell Hu i dues persones més al pou.",
    ),
    (
        {"kind": "burn", "target_ids": ["granary"], "place_id": None},  # told by the place
        "Lin Feng quemó el granero.",
        "Lin Feng va cremar el graner.",
    ),
    (
        {"kind": "give", "target_ids": ["hu"]},
        "Lin Feng hizo regalos al viejo Hu en el pozo.",
        "Lin Feng va fer regals al vell Hu al pou.",
    ),
    (
        {"kind": "steal", "victim_ids": ["hu"]},
        "Lin Feng robó al viejo Hu en el pozo.",
        "Lin Feng va robar al vell Hu al pou.",
    ),
    (
        {"kind": "spare", "target_ids": ["zhao"]},
        "Lin Feng perdonó la vida a Zhao Kun en el pozo.",
        "Lin Feng va perdonar la vida a Zhao Kun al pou.",
    ),
    (
        {"kind": "wound", "victim_ids": ["lin"]},  # their own deed fell on them
        "Lin Feng se hirió en el pozo.",
        "Lin Feng es va ferir al pou.",
    ),
    (
        {"kind": "wound", "victim_ids": ["lin", "zhao"]},
        "Lin Feng se hirió e hirió a Zhao Kun en el pozo.",
        "Lin Feng es va ferir i va ferir Zhao Kun al pou.",
    ),
    (
        {"kind": "bout", "target_ids": ["zhao"], "terms": Terms.NO_HARM},  # W1
        "Lin Feng midió fuerzas con Zhao Kun en el pozo.",
        "Lin Feng va mesurar forces amb Zhao Kun al pou.",
    ),
    (
        {"kind": "bout", "target_ids": ["zhao"], "terms": Terms.WOUNDS},
        "Lin Feng se batió en duelo con Zhao Kun en el pozo.",
        "Lin Feng es va batre en duel amb Zhao Kun al pou.",
    ),
    (
        {"kind": "kill", "victim_ids": ["ilya"], "terms": Terms.DEATH},  # a death both accepted
        "Lin Feng mató a Ilya en duelo en el pozo.",
        "Lin Feng va matar Ilya en duel al pou.",
    ),
    (
        {"kind": "breakthrough", "text": "broke through to el Núcleo Dorado"},  # A4, G19
        "Lin Feng dio el salto al Núcleo Dorado en el pozo.",
        "Lin Feng va fer el salt al Núcleo Dorado al pou.",
    ),
    (
        {"kind": "reveal", "text": "Lin Feng showed their true strength: Núcleo Dorado"},  # G20
        "La verdadera fuerza de Lin Feng salió a la luz: Núcleo Dorado en el pozo.",
        "La veritable força de Lin Feng va sortir a la llum: Núcleo Dorado al pou.",
    ),
    (
        {"kind": "display", "text": "a show"},
        "Lin Feng hizo una demostración de poder en el pozo.",
        "Lin Feng va fer una demostració de poder al pou.",
    ),
]


@pytest.mark.parametrize(("facts", "spanish", "catalan"), TOLD)
def test_a_deed_is_told_in_spanish_and_in_catalan(facts, spanish, catalan):
    assert account(world(ES), deed(**facts), language=ES) == spanish
    assert account(world(CA), deed(**facts), language=CA) == catalan


def test_english_tells_them_as_it_always_did():
    state = world(EN)
    assert account(state, deed(kind="kill", victim_ids=["ilya"])) == (
        "Lin Feng killed Ilya at the outer-court well."
    )
    assert account(state, deed(kind="wound", victim_ids=["lin", "zhao"])) == (
        "Lin Feng wounded themselves and Zhao Kun at the outer-court well."
    )
    assert account(state, deed(kind="give", target_ids=["hu"])) == (
        "Lin Feng gave gifts to Old Hu at the outer-court well."
    )
    assert account(state, deed(kind="bout", target_ids=["zhao"], terms=Terms.NO_HARM)) == (
        "Lin Feng sparred with Zhao Kun at the outer-court well."
    )


def test_a_doer_nobody_can_name_is_someone():
    kill = deed(kind="kill", victim_ids=["ilya"])
    assert account(world(ES), kill, doer=SOMEONE, language=ES) == "Alguien mató a Ilya en el pozo."
    assert account(world(CA), kill, doer=SOMEONE, language=CA) == "Algú va matar Ilya al pou."
    told = account(world(ES), kill, doer=SOMEONE, language=ES)
    assert garbled(told, ES) == "Corre una versión confusa: Alguien mató a Ilya en el pozo."
    assert garbled("x", CA) == "Corre una versió confusa: x"
    assert garbled("x") == "A garbled account goes round: x"


def test_a_deed_the_world_has_no_words_for_keeps_its_own():
    bow = deed(kind="bow", text="Bowed to the elder (it worked)", severity=1)
    assert account(world(ES), bow, language=ES) == "Lin Feng: bowed to the elder."
    assert own_words(bow) == "Bowed to the elder (it worked)"
    assert own_words(bow, ES) == "Bowed to the elder (salió bien)"
    partly = bow.model_copy(update={"text": "saludo al anciano (it partly worked)"})
    assert own_words(partly, CA) == "Saludo al anciano (va sortir a mitges)"
    failed = bow.model_copy(update={"text": "saludo al anciano (it failed)"})
    assert own_words(failed, ES) == "Saludo al anciano (salió mal)"
    assert own_words(bow.model_copy(update={"text": "saludo al anciano"}), ES) == (
        "Saludo al anciano"
    )


def test_what_people_found_of_a_deed_nobody_saw():
    """W13: who was found dead or harmed, and what people make of it."""
    kill = deed(kind="kill", victim_ids=["ilya"])
    hurt = deed(kind="wound", victim_ids=["zhao", "hu"])
    spanish, catalan = world(ES), world(CA)

    dead = found(spanish, kill, ES)
    assert dead == "Ilya apareció sin vida en el pozo"
    assert unexplained(dead, "unknown", language=ES) == f"{dead}, y nadie sabe quién lo hizo."
    assert unexplained(dead, "accident", language=ES) == f"{dead}: un accidente, dicen."
    assert unexplained(dead, "blamed", "el Loto Negro", ES) == (
        f"{dead}. La gente culpa al Loto Negro."
    )
    assert found(spanish, hurt, ES) == "Zhao Kun y el viejo Hu sufrieron daños en el pozo"
    assert found(spanish, deed(kind="burn"), ES) == "Algo pasó en el pozo"

    dead = found(catalan, kill, CA)
    assert dead == "Ilya va aparèixer sense vida al pou"
    assert unexplained(dead, "unknown", language=CA) == f"{dead}, i ningú no sap qui ho va fer."
    assert unexplained(dead, "accident", language=CA) == f"{dead}: un accident, diuen."
    assert unexplained(dead, "blamed", "el Lotus Negre", CA) == (
        f"{dead}. La gent culpa el Lotus Negre."
    )
    assert found(catalan, hurt, CA) == "Zhao Kun i el vell Hu van patir danys al pou"
    assert found(catalan, deed(kind="burn"), CA) == "Alguna cosa va passar al pou"

    english = found(world(EN), kill)
    assert unexplained(english, "blamed", "the Black Lotus") == (
        "Ilya was found dead at the outer-court well. The Black Lotus did it, people say."
    )


def test_word_of_a_price_on_someones_head():
    """W5: the rumor a bounty starts."""
    assert bounty("the Azure Sect", "Lin Feng") == (
        "The Azure Sect puts a price on Lin Feng's head."
    )
    assert bounty("la Secta Azur", "Lin Feng", ES) == (
        "La Secta Azur pone precio a la cabeza de Lin Feng."
    )
    assert bounty("la Secta Atzur", "el vell Hu", CA) == (
        "La Secta Atzur posa preu al cap del vell Hu."
    )


def test_names_are_listed_as_each_language_says_them():
    assert listing(["Old Pan", "Hua"], language=ES) == "Old Pan y Hua"
    assert listing(["A", "B", "C"], language=CA) == "A, B i C"
    assert listing(["A", "B", "C", "D", "E", "F"], language=ES) == "A, B y otras cuatro personas"
    assert listing(["A", "B", "C", "D", "E", "F"], language=CA) == "A, B i quatre persones més"
    # Those the teller can't name are counted, never named (C6).
    assert [listing([], more=1, language=lang) for lang in (ES, CA)] == ["alguien", "algú"]
    assert [listing([], more=3, language=lang) for lang in (ES, CA)] == [
        "tres personas",
        "tres persones",
    ]
    assert listing(["Old Pan"], more=1, language=ES) == "Old Pan y otra persona"
    assert listing(["Old Pan"], more=1, language=CA) == "Old Pan i una altra persona"
    assert [number(2, lang) for lang in Language] == ["two", "dos", "dues"]
    assert number(40, ES) == "40"
    # Spanish "y" is "e" before the sound of an i, and stays before "hie" and "hia".
    assert listing(["Han Jie", "Ilya"], language=ES) == "Han Jie e Ilya"
    assert listing(["Han Jie", "Hilda"], language=ES) == "Han Jie e Hilda"
    assert listing(["Han Jie", "Hiedra"], language=ES) == "Han Jie y Hiedra"


def test_a_small_word_runs_into_the_name_s_article():
    assert with_word(ES, "a", "el viejo Hu") == "al viejo Hu"
    assert with_word(ES, "de", "el viejo Hu") == "del viejo Hu"
    assert with_word(ES, "de", "los Lobos") == "de los Lobos"
    assert with_word(ES, "a", "El Paso") == "a El Paso"  # the name's own capital stays apart
    assert with_word(CA, "a", "els turons") == "als turons"
    assert with_word(CA, "de", "el vell Hu") == "del vell Hu"
    assert with_word(CA, "de", "Olot") == "d'Olot"
    assert with_word(CA, "de", "Zhao Kun") == "de Zhao Kun"
    assert with_word(EN, "to", "the elder") == "to the elder"
    assert with_word(ES, "", "Hua") == "Hua"


def test_a_beast_nobody_named_is_told_by_its_kind():
    assert [telling._article(kind, ES) for kind in ("lobo", "serpiente", "fantasma", "araña")] == [
        "un",
        "una",
        "un",
        "una",
    ]
    assert [telling._article(kind, CA) for kind in ("llop", "serp", "aranya")] == [
        "un",
        "un",
        "una",
    ]
    assert [telling._article(kind) for kind in ("wolf", "ash wolf")] == ["a", "an"]


def test_the_wounds_the_engine_names_are_said_in_the_storys_language():
    assert wound_said("a breakthrough gone wrong", ES) == "un salto que salió mal"
    assert wound_said("a breakthrough that stalled", CA) == "un salt que es va quedar a mitges"
    assert wound_said("caught in the blast", ES) == "golpe de la explosión"
    assert wound_said("a breakthrough gone wrong") == "a breakthrough gone wrong"
    assert wound_said("un corte en el brazo", ES) == "un corte en el brazo"  # the story's own
    for english, said in telling._WOUNDS.items():
        assert all(said) and english not in said


# --- What the story keeps is kept as it was told (W2, W4) ---------------------------------------


def spanish(turn: int = 2) -> TurnContext:
    return TurnContext(story_id="s1", turn=turn, settings=StorySettings(language=ES))


def test_a_spanish_storys_rumor_and_grudge_are_kept_in_spanish():
    state = world(ES)
    state.characters["wei"] = Character(
        id="wei",
        name="Wei",
        location_id="well",
        memberships=[Membership(faction_id="outer-court", rank="outer disciple")],
    )
    state.scene.present_ids.append("wei")
    kill = ProposedDeed(kind="kill", text="le corto el cuello (it worked)", victim_ids=["zhao"])
    step = deed_step(kill, dead=("zhao",))

    after = pipeline.play_out(state, Resolution(steps=[step]), spanish(), rng()).state
    done = the_deed(after)
    after = moved_on(after)  # once Wei can talk
    until, turn = after.world_s + 2 * HOUR, 3
    while after.world_s < until:
        after = pipeline.catch_up(after, until, spanish(turn), rng(turn)).state
        turn += 1
    (rumor,) = [r for r in after.rumors.values() if r.deed_id == done.id]

    assert rumor.text == "Lin Feng mató a Zhao Kun en el pozo."
    (grudge,) = after.characters["wei"].attitude_toward("lin").grudges
    assert grudge.reason == rumor.text

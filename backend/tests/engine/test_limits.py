"""F3, G12 and the ratings table's lines, enforced in code (`engine.limits`)."""

import pytest

from engine import limits
from engine.context import Language, Rating
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
    "appearance",
    [
        "Aparenta unos doce años, con una cinta en el pelo.",
        "Un cuerpo infantil y una voz aguda.",
        "16, delgado, pelo negro recogido.",
        "Lleva uniforme escolar y coletas.",
        "El cuerpo de una niña de diez años, los ojos de una anciana.",
        "Una chica de catorce años con un abrigo rojo.",
        "Tiene 15 años y es pequeña para su edad.",
        "Delgada, tiene 15 años.",
        "Lia tiene quince años y es rápida con el cuchillo.",
        "Lia, de 15 años, pelirroja.",
        "Acaba de cumplir dieciséis años.",
        "Una niña de ojos grandes.",
        "Parece una niña, aunque dice tener quinientos años.",
        "Una colegiala con trenzas.",
        "Cara de niño y manos de herrero.",
        "Una joven de 16.",
        "Menor de edad.",
        "12 años, pálida, con una sombrilla.",
        "Es una niña de voz fina.",
        "Alta para su edad; es una chica de 15 años.",
        "Lia es una niña.",
        "Pálida; doce años; una sombrilla.",
        "Aparenta uns dotze anys, amb una cinta als cabells.",
        "Un cos infantil i una veu aguda.",
        "Porta uniforme d'escola i cuetes.",
        "El cos d'una nena de deu anys, els ulls d'una vella.",
        "Una noia de catorze anys amb un abric vermell.",
        "Té 15 anys i és petita per l'edat.",
        "La Lia té quinze anys.",
        "Lia, de 15 anys, pèl-roja.",
        "Acaba de fer setze anys.",
        "Una nena d'ulls grossos.",
        "Sembla una nena, tot i que diu que té cinc-cents anys.",
        "Una col·legiala amb trenes.",
        "Cara de nen i mans de ferrer.",
        "Una noia de 16.",
        "Menor d’edat.",
        "16 anys, una cartera d'escola.",
        "Un al·lot de quinze anys.",
        "Encara és un nen.",
        "La Lia és una nena.",
        "Prima, de quinze anys d'edat.",
    ],
)
def test_a_childlike_look_is_read_in_spanish_and_in_catalan(appearance):
    """S10: a story's world is written in its language, and a description may be in any."""
    assert limits.adult_problem(person(age=500, appearance=appearance)) == "described as childlike"


@pytest.mark.parametrize(
    "text",
    [
        "24, delgado, pelo oscuro peinado hacia atrás, una cicatriz en la ceja.",
        "Cincuentona, ancha, bigote gris, anillos de oro.",
        "Una viuda que cría a dos hijos sobre la panadería.",
        "Una cicatriz de diez años le cruza la mandíbula.",
        "Maestra de instituto con tinta en los dedos.",
        "Maestra de educación infantil.",
        "2 espadas a la espalda, madre de diez.",
        "Su hija tiene 6 años.",
        "Dirige un cuerpo de 12 jinetes.",
        "Tenía 15 años cuando llegó la guerra.",
        "Hace 10 años que no ve el mar.",
        "Lleva 12 años en la guardia.",
        "Una joven de 2 metros.",
        "Aparenta una calma que no siente.",
        "30 años, un delantal de camarera.",
        "Viuda, madre de un niño de cinco años.",
        "Su hija es una niña de 6 años.",
        "Lleva a su niñita en brazos.",
        "Madre de dos niños pequeños.",
        "Parecía un niño cuando llegó a la secta; hoy es un guerrero curtido.",
        "Aparentaba doce años cuando la conocí; de eso hace ya dos décadas.",
        "Diez años en el frente, una cicatriz en la ceja.",
        "Tras 12 años, sigue en la guardia.",
        "Parece 3 veces más fuerte de lo que es.",
        "Cría caballos en el valle.",
        "24, prim, cabells foscos pentinats enrere, una cicatriu a la cella.",
        "Una vídua que cria dos fills sobre el forn.",
        "Una cicatriu de deu anys li creua la mandíbula.",
        "Mestra d'institut amb tinta als dits.",
        "Mestra d'educació infantil.",
        "La seva filla té 6 anys.",
        "Tenia 15 anys quan va arribar la guerra.",
        "Fa 10 anys que no veu el mar.",
        "Fa 12 anys que és a la guàrdia.",
        "Una jove de 2 metres.",
        "Sembla nou a la ciutat.",
        "30 anys, un davantal de cambrera.",
        "Vídua, mare d'un nen de cinc anys.",
        "La seva filla és una nena de 6 anys.",
        "Mare de dos nens petits.",
        "Semblava un nen quan va arribar; avui és un guerrer.",
        "Deu anys al front, una cicatriu a la cella.",
        "Sembla set vegades més fort.",
        "Té set i gana.",
        "Deu diners a tothom.",
    ],
)
def test_ordinary_adult_descriptions_pass_in_spanish_and_in_catalan(text):
    assert limits.is_adult(person(age=30, appearance=text, description=text))


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
        ("sleep with her", Intimacy.SEXUAL),
        ("sleep with the barmaid", Intimacy.SEXUAL),
        ("sleep with one eye open", None),
        ("sleep with my sword under the pillow", None),
        ("sleep with her knife in reach", None),
        ("slept with the window open", None),
    ],
)
def test_romantic_and_sexual_steps_are_recognised(text, kind):
    assert limits.intimacy(step(text)) is kind


SPANISH_STEPS = [
    ("besar a Mei", Intimacy.ROMANCE),
    ("le doy un beso a Lia", Intimacy.ROMANCE),
    ("coquetear con la camarera", Intimacy.ROMANCE),
    ("seducir al guardia para conseguir la llave", Intimacy.ROMANCE),
    ("pedirle matrimonio", Intimacy.ROMANCE),
    ("la invito a salir", Intimacy.ROMANCE),
    ("le acaricio la mejilla", Intimacy.ROMANCE),
    ("me declaro a Lia", Intimacy.ROMANCE),
    ("cortejo a la hija del posadero", Intimacy.ROMANCE),
    ("le pido salir conmigo", Intimacy.ROMANCE),
    ("acariciarle el cabello", Intimacy.ROMANCE),
    ("me acuesto con Lia", Intimacy.SEXUAL),
    ("hacer el amor con ella", Intimacy.SEXUAL),
    ("tener sexo con Lia", Intimacy.SEXUAL),
    ("la desnudo despacio", Intimacy.SEXUAL),
    ("le quito la ropa", Intimacy.SEXUAL),
    ("la manoseo en la oscuridad", Intimacy.SEXUAL),
    ("violar a la prisionera", Intimacy.SEXUAL_VIOLENCE),
    ("la arrastro al callejón y la violo", Intimacy.SEXUAL_VIOLENCE),
    ("abusar sexualmente de ella", Intimacy.SEXUAL_VIOLENCE),
    ("forzarla a acostarse conmigo", Intimacy.SEXUAL_VIOLENCE),
    ("la violación de la prisionera", Intimacy.SEXUAL_VIOLENCE),
    # A greeting, an oath or a cut, as in English.
    ("me arrodillo y beso la mano del anciano", None),
    ("beso el anillo del don", None),
    ("dejo que mi hoja bese su garganta", None),
    ("le doy un beso en la mejilla", None),
    # Words with an everyday sense.
    ("molesto al guardia hasta que se va", None),
    ("no quiero molestar al tabernero", None),
    ("violar la ley del clan", None),
    ("violo la tregua", None),
    ("una violación flagrante de la ley", None),
    ("me acuesto con fiebre", None),
    ("me acurruco junto al fuego", None),
    ("acaricio la empuñadura de mi espada", None),
    ("acaricio al perro", None),
    ("le invito a salir de la habitación", None),
    ("me corto el pelo al rape", None),
    ("pesco un rape en el puerto", None),
    ("toco la viola a diario", None),
    ("me acostumbro con el tiempo", None),
    ("quito el peto al guardia caído", None),
    ("me declaro a favor del consejo", None),
    ("duermo con el cuchillo bajo la almohada", None),
    ("compruebo el sexo del potro", None),
    ("lanzo una piedra a Zhao", None),
    ("sigo al cortejo fúnebre", None),
    ("el juglar canta un viejo romance", None),
    ("tengo un romance con Lia", Intimacy.ROMANCE),
    ("pido salir a tomar el aire", None),
    ("acaricio a mi lobo", None),
    ("le acaricio el lomo al caballo", None),
    ("cargo una viola al hombro", None),
    ("recojo las violas del jardín", None),
    ("le violan sus derechos", None),
    ("la ciudad no se rinde, así que decido tomarla por la fuerza", None),
    ("camino bajo las desnudas ramas del roble", None),
    ("se declara a sí mismo emperador", None),
    ("mantengo una relación íntima con la corte", None),
]
CATALAN_STEPS = [
    ("besar la Mei", Intimacy.ROMANCE),
    ("li faig un petó a la Lia", Intimacy.ROMANCE),
    ("omplir-la de petons", Intimacy.ROMANCE),
    ("flirtejar amb la cambrera", Intimacy.ROMANCE),
    ("seduir el guardià per aconseguir la clau", Intimacy.ROMANCE),
    ("demanar-li matrimoni", Intimacy.ROMANCE),
    ("la convido a sortir", Intimacy.ROMANCE),
    ("li acarono la galta", Intimacy.ROMANCE),
    ("em declaro a la Lia", Intimacy.ROMANCE),
    ("festejar amb la Mei", Intimacy.ROMANCE),
    ("li demano per sortir", Intimacy.ROMANCE),
    ("acariciar-li els cabells", Intimacy.ROMANCE),
    ("anar-me'n al llit amb ella", Intimacy.SEXUAL),
    ("fer l’amor amb ella", Intimacy.SEXUAL),
    ("tenir sexe amb la Lia", Intimacy.SEXUAL),
    ("la despullo a poc a poc", Intimacy.SEXUAL),
    ("li trec la roba", Intimacy.SEXUAL),
    ("la grapejo a les fosques", Intimacy.SEXUAL),
    ("violar la presonera", Intimacy.SEXUAL_VIOLENCE),
    ("l'arrossego al carreró i la violo", Intimacy.SEXUAL_VIOLENCE),
    ("abusar sexualment d'ella", Intimacy.SEXUAL_VIOLENCE),
    ("forçar-la a allitar-se amb mi", Intimacy.SEXUAL_VIOLENCE),
    ("la violació de la presonera", Intimacy.SEXUAL_VIOLENCE),
    ("m'agenollo i beso la mà de l'ancià", None),
    ("beso l'anell del senyor", None),
    ("deixo que la meva fulla besi el seu coll", None),
    ("li faig un petó a la galta", None),
    ("molesto el guardià fins que se'n va", None),
    ("violar la llei del clan", None),
    ("violar aquesta sagrada llei", None),
    ("violo la treva", None),
    ("denuncio la violació de la treva", None),
    ("m'allito amb febre", None),
    ("m'embolico amb la manta", None),
    ("acarono el gos", None),
    ("el convido a sortir de la cambra", None),
    ("et rapes el cap", None),
    ("toco la viola cada dia", None),
    ("una cursa folla pel bosc", None),
    ("peto la porta d'una coça", None),
    ("dormo amb la finestra oberta", None),
    ("comprovo el sexe del poltre", None),
    ("llanço una pedra a en Zhao", None),
    ("festejo la victòria amb la colla", None),
    ("li dic que es deixi de romanços", None),
    ("tinc un romanç amb la Lia", Intimacy.ROMANCE),
    ("demano per sortir un moment", None),
    ("l'acarono darrere les orelles", None),
    ("toco el violí a la plaça", None),
    ("cullo les violes del marge", None),
    ("saludo la Violant", None),
    ("la ciutat no es rendeix, així que decideixo prendre-la per la força", None),
    ("regiro les despulles del drac", None),
    ("agafo el gerro i el peto contra terra", None),
    ("la folla idea de saltar el mur", None),
    ("es declara a si mateix emperador", None),
]


@pytest.mark.parametrize(("text", "kind"), SPANISH_STEPS)
def test_a_spanish_storys_steps_are_read_in_spanish(text, kind):
    """S10: the reading of a Spanish story may word a step in Spanish."""
    assert limits.intimacy(step(text), Language.ES) is kind


@pytest.mark.parametrize(("text", "kind"), CATALAN_STEPS)
def test_a_catalan_storys_steps_are_read_in_catalan(text, kind):
    assert limits.intimacy(step(text), Language.CA) is kind


@pytest.mark.parametrize("language", [Language.ES, Language.CA])
def test_english_words_still_count_in_a_story_in_another_language(language):
    """The reading may word a step in English whatever the story speaks, and the graver
    reading of the two stands."""
    assert limits.intimacy(step("kiss Mei"), language) is Intimacy.ROMANCE
    assert limits.intimacy(step("sleep with Lia"), language) is Intimacy.SEXUAL
    assert limits.intimacy(step("rape the captive"), language) is Intimacy.SEXUAL_VIOLENCE
    assert limits.intimacy(step("molest the girl"), language) is Intimacy.SEXUAL_VIOLENCE
    mixed = step("besar a Lia", verb="force myself on her")
    assert limits.intimacy(mixed, language) is Intimacy.SEXUAL_VIOLENCE


@pytest.mark.parametrize(
    ("language", "greeting", "kiss"),
    [
        (Language.ES, "besar la mano del anciano", "besar la mano de Lia y luego besarla"),
        (Language.CA, "besar la mà de l'ancià", "besar la mà de la Lia i després besar-la"),
    ],
)
def test_a_greetings_kiss_stays_one_when_the_reading_names_the_verb_in_english(
    language, greeting, kiss
):
    """B5: the reading names a step's verb in English, so "kiss" stands beside the story's
    words for the hand or the ring it is given to."""
    assert limits.intimacy(step(greeting, verb="kiss"), language) is None
    assert limits.intimacy(step(kiss, verb="kiss"), language) is Intimacy.ROMANCE
    assert limits.intimacy(step("Lia", verb="kiss"), language) is Intimacy.ROMANCE


def test_each_language_has_its_own_words():
    """Catalan "petó" is a kiss and Spanish "peto" is a breastplate, so a story's words are
    read only in its own language, and an English story reads as it always did."""
    armour = step("quito el peto al guardia")
    assert limits.intimacy(armour) is None and limits.intimacy(armour, Language.ES) is None
    kiss = step("li faig un petó")
    assert limits.intimacy(kiss, Language.CA) is Intimacy.ROMANCE
    assert limits.intimacy(kiss) is None and limits.intimacy(kiss, Language.ES) is None
    # English alone has "molest" in any form.
    assert limits.intimacy(step("molestation")) is Intimacy.SEXUAL_VIOLENCE
    assert limits.intimacy(step("besar a Mei")) is None


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


# --- What a reading leaves out (F3, F2) -------------------------------------------------
# On the real model (2026-11-12) "I kiss Mei" played though the story had Mei at the bar, aged
# sixteen, and a sexual assault in a Teen story became a step the engine let play. A reading
# gives a partner only by id and words a step as it likes, so the check reads the rest itself.


def at_the_bar(ref: str = "mei", name: str = "Mei", **fields) -> Character:
    """Someone the record has where the scene plays, whom the scene doesn't show and the player
    character hasn't met: the interpret step isn't shown them, so it has no id to give."""
    return Character(id=ref, name=name, location_id="bar", **fields)


@pytest.mark.parametrize(
    ("reading", "action"),
    [
        (step("kiss Mei", verb="kiss"), ""),  # the step's own words name her
        (step("kiss her", verb="kiss"), "I kiss Mei"),  # only the player's do
        (step("kiss her", verb="kiss", targets=["Mei"]), ""),  # she is left in words
        (step("fer-li un petó", verb="kiss", targets=["la Mei"]), "Faig un petó a la Mei"),
        (step("besar a Mei", verb="kiss"), "Beso a Mei"),
        (
            step(
                "kiss the girl",
                verb="kiss",
                stranger=Stranger(
                    who="Mei, a girl at the bar", plausibility=Plausibility.PLAUSIBLE
                ),
            ),
            "",
        ),
    ],
)
def test_a_kiss_the_reading_aimed_at_nobody_is_held_to_whom_its_words_name(reading, action):
    state = with_character(grounded_world(), at_the_bar(age=16))

    [hit] = limits.check_action(state, Intent(steps=[reading]), Rating.MATURE, action=action)

    assert (hit.category, hit.subject, hit.detail) == (LimitCategory.MINOR, "mei", "aged 16")


def test_a_childlike_adult_named_only_in_words_is_held_too():
    ysolde = at_the_bar("ysolde", "Ysolde", age=300, appearance="Looks about twelve, pale.")
    state = with_character(grounded_world(), ysolde)
    intent = Intent(steps=[step("seduce Ysolde", verb="seduce")])

    [hit] = limits.check_action(state, intent, Rating.MATURE, action="I seduce Ysolde")

    assert (hit.subject, hit.detail) == ("ysolde", "described as childlike")


def test_a_named_adult_plays_and_so_does_someone_the_story_doesnt_know():
    state = with_character(grounded_world(), at_the_bar("lia", "Lia Conti", age=27))
    for name in ("Lia", "Lia Conti", "Anna"):
        intent = Intent(steps=[step(f"kiss {name}", verb="kiss", targets=[name])])
        assert limits.check_action(state, intent, Rating.MATURE, action=f"I kiss {name}") == []


def test_whom_the_reading_aimed_the_step_at_is_its_partner():
    state = with_character(grounded_world(), at_the_bar("lia", "Lia", age=27))
    state = with_character(state, at_the_bar(age=16))
    # A kiss between adults is one whoever else the words name: Mei only watches.
    action = "I kiss Lia while Mei watches"
    watched = Intent(steps=[step("kiss Lia while Mei watches", verb="kiss", target_ids=["lia"])])
    assert limits.check_action(state, watched, Rating.MATURE, action=action) == []
    # Nor is a place whose name holds hers: the Mei Garden is where they kiss.
    garden = step("kiss Lia", verb="kiss", target_ids=["lia"], targets=["the Mei Garden"])
    assert limits.check_action(state, Intent(steps=[garden]), Rating.MATURE) == []
    # Someone the reading left in words beside her is a partner too.
    both = Intent(steps=[step("kiss them both", verb="kiss", target_ids=["lia"], targets=["Mei"])])
    [hit] = limits.check_action(state, both, Rating.MATURE)
    assert hit.subject == "mei"


def test_the_nearest_of_a_name_is_the_one_meant():
    state = with_character(grounded_world(), person(id="mei", name="Mei", age=30))
    state.scene.present_ids.append("mei")
    state = with_character(state, person(id="mei-2", name="Mei", age=16))  # somewhere else
    intent = Intent(steps=[step("kiss Mei", verb="kiss")])

    assert limits.check_action(state, intent, Rating.MATURE, action="I kiss Mei") == []

    # With both in the scene either could be meant, so both are held.
    state.scene.present_ids.append("mei-2")
    [hit] = limits.check_action(state, intent, Rating.MATURE, action="I kiss Mei")
    assert hit.subject == "mei-2"


def test_the_players_words_are_the_steps_words_when_the_action_is_one_step():
    state = with_character(grounded_world(), at_the_bar(age=16))
    softened = Intent(steps=[step("lean in close to Mei", verb="approach", target_ids=["mei"])])
    assert limits.check_action(state, softened, Rating.MATURE) == []  # the reading alone
    [hit] = limits.check_action(state, softened, Rating.MATURE, action="I kiss Mei")
    assert (hit.category, hit.subject) == (LimitCategory.MINOR, "mei")

    adults = with_character(grounded_world(), at_the_bar("lia", "Lia", age=27))
    rest = Intent(steps=[step("rest beside Lia", verb="rest", target_ids=["lia"])])
    [hit] = limits.check_action(adults, rest, Rating.TEEN, action="I sleep with Lia")
    assert hit.category is LimitCategory.SEXUAL
    assert limits.check_action(adults, rest, Rating.MATURE, action="I sleep with Lia") == []
    for language, action in (
        (Language.ES, "Me acuesto con Lia"),
        (Language.CA, "Faig l'amor amb la Lia"),
    ):
        [hit] = limits.check_action(adults, rest, Rating.TEEN, language, action)
        assert hit.category is LimitCategory.SEXUAL


def test_romance_in_one_step_doesnt_make_the_others_romantic():
    state = with_character(grounded_world(), at_the_bar(age=16))
    intent = Intent(
        steps=[
            step("kiss my wife goodbye", verb="kiss", targets=["my wife"]),
            step("ask Mei to mind the shop", verb="ask", target_ids=["mei"]),
        ]
    )
    action = "I kiss my wife goodbye and ask Mei to mind the shop"

    assert limits.check_action(state, intent, Rating.MATURE, action=action) == []


def test_sexual_violence_in_the_players_words_counts_for_every_step():
    action = "I drag Mei into the alley and force myself on her"
    softened = Intent(
        steps=[
            step("drag Mei into the alley", verb="drag", targets=["Mei"]),
            step("overpower her", verb="overpower"),
        ]
    )
    state = with_character(grounded_world(), at_the_bar(age=16))

    hits = limits.check_action(state, softened, Rating.MATURE, action=action)

    # Each step is held to her: the second says "her", and the player's words say who.
    assert [(h.category, h.subject, h.step) for h in hits] == [
        (LimitCategory.MINOR, "mei", 0),
        (LimitCategory.MINOR, "mei", 1),
    ]
    # With an adult, Mature plays it as the table says, and Teen never does.
    adults = with_character(grounded_world(), at_the_bar(age=30))
    assert limits.check_action(adults, softened, Rating.MATURE, action=action) == []
    teen = limits.check_action(adults, softened, Rating.TEEN, action=action)
    assert {h.category for h in teen} == {LimitCategory.SEXUAL_VIOLENCE}


@pytest.mark.parametrize(
    ("language", "action"),
    [
        (Language.EN, "I drag Rosa into the alley and force myself on her"),
        (Language.ES, "Arrastro a Rosa al callejón y la violo"),
        (Language.CA, "Arrossego la Rosa al carreró i la violo"),
    ],
)
def test_a_teen_story_refuses_sexual_violence_on_the_players_own_words(language, action):
    [hit] = limits.check_words(action, Rating.TEEN, language)
    assert hit.category is LimitCategory.SEXUAL_VIOLENCE
    # Mature plays it off the page, so there the reading says who it is with first.
    assert limits.check_words(action, Rating.MATURE, language) == []


@pytest.mark.parametrize(
    ("language", "action"),
    [
        (Language.EN, "I kiss Lia"),
        (Language.EN, "I sleep with Lia"),  # talked about or done: the reading's to say
        (Language.EN, "I punch Rosa and drag her into the alley"),
        (Language.ES, "Molesto al guardia hasta que me deja pasar"),
        (Language.ES, "Violo la ley del toque de queda"),
        (Language.CA, "Toco la viola a la plaça"),
    ],
)
def test_nothing_else_is_refused_before_the_reading(language, action):
    assert limits.check_words(action, Rating.TEEN, language) == []


def test_the_limits_hold_in_a_spanish_and_a_catalan_story():
    """F2, F3, S10: the same lines, read in the story's language."""
    state = with_character(cultivation_world(), person(id="mei", name="Mei", age=15))
    adults = with_character(grounded_world(), person(age=27))
    for language, kiss, sex, assault, bother in (
        (Language.ES, "besar a Mei", "me acuesto con Lia", "violar a Lia", "molestar a Mei"),
        (Language.CA, "besar la Mei", "fer l'amor amb la Lia", "violar la Lia", "molestar la Mei"),
    ):
        hits = limits.check_action(
            state, Intent(steps=[step(kiss, target_ids=["mei"])]), Rating.MATURE, language
        )
        assert {(h.category, h.subject) for h in hits} == {
            (LimitCategory.MINOR, state.player_id),
            (LimitCategory.MINOR, "mei"),
        }
        teen_sex = Intent(steps=[step(sex, target_ids=["lia"])])
        teen_assault = Intent(steps=[step(assault, target_ids=["lia"])])
        [hit] = limits.check_action(adults, teen_sex, Rating.TEEN, language)
        assert hit.category is LimitCategory.SEXUAL
        [hit] = limits.check_action(adults, teen_assault, Rating.TEEN, language)
        assert hit.category is LimitCategory.SEXUAL_VIOLENCE
        assert limits.check_action(adults, teen_sex, Rating.MATURE, language) == []
        # Bothering someone is no limit, for a minor or in a Teen story.
        nagging = Intent(steps=[step(bother, target_ids=["mei"])])
        assert limits.check_action(state, nagging, Rating.TEEN, language) == []
        # Read as an English story, the same words cross nothing and stop nothing.
        assert limits.check_action(adults, teen_sex, Rating.TEEN) == []


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
    # S10: in each language a story is written in, each in its own words.
    for category in LimitCategory:
        said = [limits.message(category, language) for language in Language]
        assert said[0] == limits.message(category) == limits.MESSAGES[category]
        assert len(set(said)) == len(Language) and all(line.strip() for line in said)


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

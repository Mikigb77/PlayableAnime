"""G1: whether the player's own words name a goal, a deadline, a question or a person of a
draft, and whether a scene's words call someone by name (C6), read by code. Every premise and
scene here is made up or a starter's own."""

import pytest

from engine.base import DAY, HOUR, WEEK, YEAR
from engine.context import Language
from graph.drafting import samples
from graph.drafting.catalog import starter
from graph.drafting.named import (
    MONTH,
    aimed,
    called,
    named,
    one_aim,
    stated_aim,
    timed,
    times_ahead,
    told_of,
)
from graph.words import alike, content

EN, ES, CA = Language.EN, Language.ES, Language.CA
NAPLES, CULTIVATION = samples.NAPLES_PREMISE, samples.CULTIVATION_PREMISE
SQUIRE = "I'm a squire, and there are 3 days for the selection test for knighthood."


def test_words_that_say_something_and_words_in_two_forms():
    assert content("I'm the son of a mafia boss in 1970s Naples.", EN) == [
        "son",
        "mafia",
        "boss",
        "naples",
    ]
    assert content("Sents que l'espasa de ferro et pesa.", CA) == [
        "sents",
        "espasa",
        "ferro",
        "pesa",
    ]
    assert alike("killed", "killing") and alike("torneo", "torneos") and alike("test", "tests")
    assert alike("knight", "knighthood")
    assert not alike("council", "country") and not alike("boss", "boat")


@pytest.mark.parametrize(
    ("said", "text"),
    [
        # Most of what it says is in the player's words.
        (NAPLES, "Who inside the family ordered the killing of my father?"),
        (NAPLES, "Find out who killed my father"),
        (SQUIRE, "The knighthood selection test"),
        (SQUIRE, "Pass the selection test"),
        ("The tournament is tomorrow.", "The tournament"),
        # A starter's own premise names its deadline.
        (starter("outer-disciple").premise, "The ranking tournament"),
        (starter("outer-disciple").premise, "Survive the ranking tournament"),
        (starter("naples-vendetta").premise, "The council picks the next boss"),
        (starter("ashen-squire").premise, "The trial of knighthood"),
    ],
)
def test_the_players_words_name_what_they_speak_of(said, text):
    assert named(said, text, EN)


@pytest.mark.parametrize(
    ("said", "text"),
    [
        # Both speak of a boss, and the premise never mentions a council or a vote.
        (NAPLES, "The council picks the next boss"),
        (NAPLES, "Three loyal soldiers"),
        (CULTIVATION, "The ranking tournament"),
        (CULTIVATION, "Survive the ranking tournament"),
        (starter("ashen-squire").premise, "Old Bram's creditors come for the forge"),
        # The premise speaks of who is in it, and never of what they do here.
        (starter("seven-day-villainess").premise, "The heroine tells the prince"),
        (starter("outer-disciple").premise, "Zhao Kun's patience with the outer disciples"),
        (NAPLES, ""),
    ],
)
def test_what_the_drafter_added_is_not_named(said, text):
    assert not named(said, text, EN)


def test_a_person_is_named_by_their_name_alone():
    assert called("I must rescue Mei from the palace.", "Mei", EN)
    assert called("Zhao has hated me since the day I arrived.", "Zhao Kun", EN)
    # Typed without capitals, the whole name calls them.
    assert called("my rival is zhao kun", "Zhao Kun", EN)
    assert not called("my rival is from the zhao clan", "Zhao Kun", EN)
    assert not called("my old master taught me the sword", "Old Hu", EN)
    assert called("old hu sold me a draught", "Old Hu", EN)
    assert called("Hope is all I have left of my family.", "Hope", EN)
    assert not called("I hope to win the tournament.", "Hope", EN)
    # Someone the premise never speaks of is the story's to bring in.
    assert not called(NAPLES, "Carmine Russo", EN)
    assert not called(CULTIVATION, "Zhao Kun", EN)
    assert not called(CULTIVATION, "", EN)
    # What the words say of their own character fits half the people around them, so a
    # description names nobody.
    assert named(CULTIVATION, "An outer disciple of the Azure Cloud Sect.", EN)
    assert called("El meu germà Pau em va trair.", "Pau", CA)
    assert not called("El meu germà em va trair.", "Pau", CA)


def test_names_are_read_in_spanish_and_catalan():
    es = "Soy escudero, y la prueba de selección para caballero es dentro de tres días."
    assert named(es, "La prueba de selección de los caballeros", ES)
    assert not named(es, "El recaudador llega con la primera nieve", ES)
    mafia = "Soy el hijo de un jefe de la mafia, y alguien de la familia mató a mi padre."
    assert named(mafia, "Descubrir quién mató a mi padre", ES)
    ca = "Soc escuder, i la prova de selecció per ser cavaller és d'aquí a tres dies."
    assert named(ca, "La prova de selecció dels cavallers", CA)
    assert not named(ca, "El recaptador arriba amb la primera neu", CA)


@pytest.mark.parametrize(
    ("said", "event", "language"),
    [
        # One word of the event, in a clause that sets a time ahead.
        ("I'm a squire about to take the knight exam in 3 days.", "The trial of knighthood", EN),
        ("There are 3 days for the selection test.", "The knighthood test", EN),
        ("Nine days left until the trial.", "The trial of knighthood", EN),
        ("The tournament starts tomorrow, and I am not ready.", "The ranking tournament", EN),
        ("Next week the elders choose.", "The elders' choice", EN),
        # The time stands alone, so it is for the clause beside it.
        ("The tax collector comes with the first snow, in thirty days.", "The collector", EN),
        (starter("seven-day-villainess").premise, "The engagement is broken off", EN),
        (starter("old-net").premise, "The server is wiped", EN),
        (starter("kestrel-debt").premise, "The debt comes due", EN),
        (starter("war-frame").premise, "The next wave", EN),
        ("Soy escudero y el examen es dentro de tres días.", "El examen de caballero", ES),
        ("Faltan nueve días para la prueba.", "La prueba de caballería", ES),
        ("Estoy a dos días del torneo.", "El torneo de clasificación", ES),
        ("Soc escuder i l'examen és d'aquí a tres dies.", "L'examen de cavaller", CA),
        ("Falten nou dies per a la prova.", "La prova de cavalleria", CA),
        ("Demà comença el torneig.", "El torneig de classificació", CA),
        ("Mañana empieza el torneo.", "El torneo de clasificación", ES),
        ("Three days before the exam, my master vanished.", "The knight exam", EN),
        ("Quedan tres días para el examen.", "El examen de caballero", ES),
    ],
)
def test_a_sentence_that_sets_a_time_ahead_names_the_deadline(said, event, language):
    assert timed(said, event, language)


@pytest.mark.parametrize(
    ("said", "event", "language"),
    [
        # A time gone by is no deadline.
        (NAPLES + " He was the boss until three days ago.", "The council picks the next boss", EN),
        ("My father, the boss, was killed three days ago.", "The council picks the next boss", EN),
        ("Mataron a mi padre, el jefe, hace tres días.", "El consejo elige al nuevo jefe", ES),
        ("Van matar el meu pare, el cap, fa tres dies.", "El consell tria el nou cap", CA),
        # A time ahead in one sentence and the word in another name nothing.
        ("I am the boss's son. In three days I leave Naples.", "The council picks the boss", EN),
        # Nor does the rest of the sentence, when the time's own clause says what it is for.
        (starter("naples-vendetta").premise, "The killer strikes again", EN),
        (starter("outer-disciple").premise, "Zhao Kun's patience with the disciples", EN),
        # A time that counts down to something is that thing's, not what comes before it.
        ("The caravan left a day before you.", "The lost caravan runs dry", EN),
        ("La caravana salió un día antes que vosotros.", "La caravana perdida", ES),
        ("La caravana va sortir un dia abans que vosaltres.", "La caravana perduda", CA),
        # "esta mañana" is this morning.
        ("Esta mañana han encontrado a tu maestro muerto.", "El asesino del maestro", ES),
        ("Por la mañana entrenas con el maestro.", "El maestro se marcha", ES),
        # A time ahead with no word of the event.
        ("The exam is in three days.", "The ranking tournament", EN),
        ("The exam is in three days.", "", EN),
    ],
)
def test_a_time_gone_by_or_another_event_names_no_deadline(said, event, language):
    assert not timed(said, event, language)


@pytest.mark.parametrize(
    ("said", "seconds", "language"),
    [
        ("I'm a squire about to take the knight exam in 3 days.", 3 * DAY, EN),
        ("The tax collector comes with the first snow, in thirty days.", 30 * DAY, EN),
        ("Only nine days left until the trial.", 9 * DAY, EN),
        ("I have nine days left until the trial.", 9 * DAY, EN),
        ("The fleet sails in 3 more days.", 3 * DAY, EN),
        ("The seal on the vault breaks in a hundred days.", 100 * DAY, EN),
        ("The ship sails within 48 hours.", 48 * HOUR, EN),
        ("The tournament is in about two weeks.", 2 * WEEK, EN),
        ("The tournament is in twenty-one days.", 21 * DAY, EN),
        ("The fleet arrives in a month.", MONTH, EN),
        ("The comet returns in a year.", YEAR, EN),
        ("El examen de ingreso al gremio es dentro de cinco días.", 5 * DAY, ES),
        ("Faltan nueve días para la prueba.", 9 * DAY, ES),
        ("Estoy a dos semanas del torneo.", 2 * WEEK, ES),
        ("El juicio es en veintiún días.", 21 * DAY, ES),
        ("El juicio es en unos diez días.", 10 * DAY, ES),
        ("D'aquí a dos dies arriba el recaptador del rei.", 2 * DAY, CA),
        ("Falten dues setmanes per al torneig.", 2 * WEEK, CA),
        ("El judici és d'aquí a vint-i-un dies.", 21 * DAY, CA),
    ],
)
def test_a_time_ahead_is_read_as_its_length(said, seconds, language):
    [time] = times_ahead(said, language)

    assert time.seconds == seconds


@pytest.mark.parametrize(
    ("said", "language"),
    [
        # An amount that is no number.
        ("The exam is in a few days.", EN),
        ("The exam is in three long days.", EN),
        ("The fleet arrives next month.", EN),
        ("El torneo es en unos días.", ES),
        # How long until tomorrow or tonight hangs on the hour the story opens at.
        ("The tournament starts tomorrow, and I am not ready.", EN),
        ("The duel is tonight.", EN),
        ("El torneo empieza mañana.", ES),
        ("Demà comença el torneig.", CA),
        # Two times in one clause: code can't tell whose each is.
        ("The exam in three days and the wedding in a week.", EN),
    ],
)
def test_a_time_ahead_code_cant_read_has_no_length(said, language):
    [time] = times_ahead(said, language)

    assert time.seconds is None and time.about


def test_a_time_ahead_says_what_it_is_for():
    [time] = times_ahead("I take the knight exam in 3 days, and I have no aura.", EN)

    assert time.about == ("take", "knight", "exam")
    assert time.says("The knight exam", EN) == 2
    assert time.says("The trial of knighthood", EN) == 1
    assert time.says("The harvest fair", EN) == 0
    assert list(times_ahead("My father was killed three days ago.", EN)) == []


@pytest.mark.parametrize(
    ("said", "aim", "language"),
    [
        # A word for wanting, having to, meaning to or looking for, beside the aim's own words.
        ("I'm a squire and I must pass the knight exam in 3 days.", "Pass the knight exam", EN),
        ("I want to become the Pirate King.", "Become the Pirate King", EN),
        ("You must find your sister before the snow.", "Find your sister", EN),
        ("I'm looking for the man who killed my master.", "Find the man who killed my master", EN),
        ("My dream is to be the strongest swordsman alive.", "Be the strongest swordsman", EN),
        ("Quiero aprobar el examen de ingreso al gremio.", "Aprobar el examen de ingreso", ES),
        ("He jurado vengar a mi familia.", "Vengar a mi familia", ES),
        ("Tienes que encontrar a tu hermana.", "Encontrar a tu hermana", ES),
        ("Busco al asesino de mi padre.", "Encontrar al asesino de mi padre", ES),
        ("Vull pagar el deute al recaptador del rei.", "Pagar el deute al recaptador del rei", CA),
        ("He de trobar la meva germana.", "Trobar la meva germana", CA),
        ("Has de trobar la teva germana.", "Trobar la teva germana", CA),
        # What something is done for, said with the aim's own first word.
        ("I came to the capital to become a knight.", "Become a knight", EN),
        ("You dive the old net for scrap, to pay off the clinic.", "Pay off the clinic", EN),
        ("He venido a la capital para vengar a mi padre.", "Vengar a mi padre", ES),
        ("He vingut a la capital per venjar el meu pare.", "Venjar el meu pare", CA),
        # The aim said in a sentence of its own, about what the one before it told.
        (f"{NAPLES} I will find out who.", "Find out who killed my father", EN),
        (
            "Mi padre fue asesinado. Voy a descubrir quién lo hizo.",
            "Descubrir quién asesinó a mi padre",
            ES,
        ),
        # The summary's own labels, in a line of it the player wrote.
        ("Goal: Protect my sister", "Protect my sister", EN),
        ("Hot-headed and loyal. Wants to take over the family.", "to take over the family", EN),
        ("Objetivo: Proteger a mi hermana", "Proteger a mi hermana", ES),
        ("Objectiu: Protegir la meva germana", "Protegir la meva germana", CA),
    ],
)
def test_the_players_words_say_an_aim(said, aim, language):
    assert named(said, aim, language)
    assert aimed(said, aim, language)


@pytest.mark.parametrize(
    ("said", "aim", "language"),
    [
        # G1 (a live check, 2026-11-12): a time set for an event says what is coming, not what
        # the character is after.
        (
            "I'm a squire about to take the knight exam in 3 days, and I have never once "
            "summoned aura.",
            "Pass the knight exam",
            EN,
        ),
        (
            "Soy la aprendiz más torpe de una academia de magia, y el examen de ingreso al "
            "gremio es dentro de cinco días.",
            "Aprobar el examen de ingreso al gremio",
            ES,
        ),
        (
            "Soc un pescador d'un poble de la costa, i d'aquí a dos dies arriba el recaptador "
            "del rei a cobrar un deute que no puc pagar.",
            "Pagar el deute al recaptador del rei",
            CA,
        ),
        (starter("outer-disciple").premise, "Survive the ranking tournament", EN),
        # What happened is no aim either.
        (NAPLES, "Find out who killed my father", EN),
        # An aim about something else, in another sentence.
        ("I'm going to the market. The knight exam is in 3 days.", "Pass the knight exam", EN),
        # "To" after what is no purpose.
        ("I'm a squire about to take the knight exam in 3 days.", "Take the knight exam", EN),
        ("I have never been able to summon aura.", "Summon aura", EN),
        ("Estic a punt de fer l'examen de cavaller.", "Fer l'examen de cavaller", CA),
    ],
)
def test_words_that_only_tell_of_it_say_no_aim(said, aim, language):
    # Each of these names the aim's words, which is why a goal made of them used to show.
    assert named(said, aim, language)
    assert not aimed(said, aim, language)


@pytest.mark.parametrize(
    ("said", "aim", "language"),
    [
        # The first plays on the real models (2026-11-14): "I want to be a pirate" showed no
        # goal, since the drafter says the deed in a verb of its own.
        ("I want to be a pirate.", "Become a pirate", EN),
        ("I'm seeking revenge on the clan that burned my village.", "Avenge my village", EN),
        ("Quiero ser caballero.", "Convertirme en caballero", ES),
        ("Vull ser cavaller.", "Esdevenir cavaller", CA),
    ],
)
def test_an_aim_said_in_another_verb_is_the_players_too(said, aim, language):
    # The sentence says an aim and what follows the aim's first word, the deed.
    assert not named(said, aim, language)
    assert aimed(said, aim, language)


@pytest.mark.parametrize(
    ("said", "aim", "language"),
    [
        (
            "My lifespan of 150 years is almost spent: I break through to Core Formation or I die.",
            "Break through to Core Formation or I die.",
            EN,
        ),
        ("We hold the pass or we'll die here.", "Hold the pass", EN),
        ("O encuentro a mi hermana o muero.", "Encontrar a mi hermana", ES),
        ("O trobo la meva germana o moro.", "Trobar la meva germana", CA),
    ],
)
def test_what_it_is_to_them_says_an_aim(said, aim, language):
    # "I do it or I die" says what the character is after as surely as "I must".
    assert aimed(said, aim, language)


@pytest.mark.parametrize(
    ("said", "aim", "language"),
    [
        # What the real drafter made of premises that say no aim (2026-11-14).
        (
            "I'm a young blacksmith in a small medieval village, hopelessly in love with the "
            "miller's wife.",
            "Win the miller's wife's heart",
            EN,
        ),
        (
            "A 17-year-old chess prodigy who just enrolled in an elite academy where "
            "everything, even your rank, is decided by strategy games.",
            "Climb to the rank of King",
            EN,
        ),
        (
            "A beautiful courtesan and spy in the imperial capital. She can make almost anyone "
            "fall for her, and she uses it to steal secrets for the rebellion.",
            "Steal the palace guard schedules from Minister Gong",
            EN,
        ),
        (
            "A 300-year-old elf ranger, still young for her kind, guarding a forest that humans "
            "have started to cut down.",
            "Guard the forest from the human lumberjacks.",
            EN,
        ),
        (
            "Sóc un pescador vell de Cadaqués, de setanta-vuit anys. Un matí trobo una sirena "
            "ferida a la xarxa.",
            "Curar la sirena ferida",
            CA,
        ),
        # An aim the premise says, made into more than it said.
        (
            "I want to be a pirate.",
            "Become a legendary pirate captain and sail the open ocean.",
            EN,
        ),
        # The deed alone is no aim's name: another verb needs the rest of it said.
        ("I want to win.", "Win the tournament", EN),
        ("I pay the debt every month.", "Pay the debt", EN),
    ],
)
def test_what_a_drafter_makes_of_a_premise_is_no_aim_of_the_players(said, aim, language):
    assert not aimed(said, aim, language)


@pytest.mark.parametrize(
    ("said", "language"),
    [
        ("I want to be a pirate.", EN),
        ("i want to become the strongest swordsman in the world", EN),
        ("My dream is to open a bakery!", EN),
        ("Quiero ser pirata.", ES),
        ("Vull ser pirata.", CA),
    ],
)
def test_one_short_sentence_that_says_an_aim_is_one_aim(said, language):
    assert one_aim(said, language)
    # Handed back whole, it is the player's own aim (`aimed`), so a story starts with it.
    assert aimed(said, said, language)


@pytest.mark.parametrize(
    ("said", "language"),
    [
        # No aim said.
        ("A pirate with a cursed map.", EN),
        ("I'm a squire about to take the knight exam in 3 days.", EN),
        # More than the aim: a second sentence, or a sentence too long to be only an aim.
        ("I'm a squire. I want to pass the knight exam.", EN),
        (
            "I'm the last disciple of a fallen sect and I want to find the man who burned "
            "our mountain.",
            EN,
        ),
        ("Soy un pirata con un mapa maldito.", ES),
        ("", EN),
    ],
)
def test_words_that_say_more_or_less_than_an_aim_are_not_one_aim(said, language):
    assert not one_aim(said, language)
    assert stated_aim(said, language) == ""


@pytest.mark.parametrize(
    ("said", "language"),
    [
        ("I want to be a pirate.", EN),
        ("i want to become the strongest swordsman in the world", EN),
        ("My dream is to open a bakery!", EN),
        ("I must survive the tournament.", EN),
        ("I'm looking for my sister.", EN),
        ("I just want to see the sea", EN),
        ("¡Quiero ser el rey de los piratas!", ES),
        ("Mi sueño es abrir una panadería.", ES),
        ("Vull ser la millor cuinera del regne.", CA),
        ("He de trobar la meva germana.", CA),
    ],
)
def test_one_short_sentence_that_opens_on_an_aim_states_it(said, language):
    # G2: the player's own words are the goal, whatever a drafter made of them.
    assert stated_aim(said, language) == said
    assert aimed(said, said, language)


@pytest.mark.parametrize(
    ("said", "language"),
    [
        # An aim's word in a sentence that is after nothing.
        ("My dream died with her.", EN),
        ("I decided to stay home.", EN),
        # What is only to come, or only supposed.
        ("I will die in three days.", EN),
        ("I'll never be a knight.", EN),
        ("I must have been cursed.", EN),
        # What they don't want says no goal a story can follow.
        ("I must not fail.", EN),
        ("No quiero morir.", ES),
        ("No vull morir.", CA),
    ],
)
def test_one_short_sentence_with_an_aims_word_in_it_states_none(said, language):
    assert stated_aim(said, language) == ""


def test_a_stated_aim_is_given_as_one_line():
    assert stated_aim("  I want  to be a pirate. ", EN) == "I want to be a pirate."


def test_an_aim_is_said_about_what_it_names():
    # A word for wanting says an aim only of what its own words name.
    assert not aimed("I want to win the tournament.", "Find out who killed my father", EN)
    assert not aimed("Someone wants me dead.", "", EN)
    # Someone else's want, in a sentence that doesn't name the aim, gives none.
    premise = starter("won-at-cards").premise
    assert "wants his ship back" in premise
    assert not aimed(premise, "Find the island on the chart", EN)


@pytest.mark.parametrize(
    ("scene", "name"),
    [
        # Inside a sentence, one word of the name written with a capital.
        ("“Move,” says Zhao.", "Zhao Kun Senior Brother Zhao"),
        ("You bow to Senior Brother Zhao and step aside.", "Zhao Kun Senior Brother Zhao"),
        ("The bucket is Carmine's, and so is the bar.", "Carmine Russo"),
        # At the start of one, all the name has, or two of its words together.
        ("Gennaro polishes a glass.", "Gennaro"),
        ("Elder Mo opens one eye.", "Elder Mo"),
        ("“Zhao Kun!” someone shouts.", "Zhao Kun"),
        # Or the same word starting two sentences: a name comes back, a plain word rarely.
        ("Carmine smiles. You sit.\nCarmine pours two glasses.", "Carmine Russo"),
        ("Dentro del bar, el viejo Gennaro seca un vaso.", "Gennaro"),
        ("—Ara no, Mo —diu l'ancià.", "Elder Mo"),
    ],
)
def test_a_scene_calls_someone_by_name(scene, name):
    language = ES if "viejo" in scene else CA if "ancià" in scene else EN
    assert told_of(scene, name, language)


@pytest.mark.parametrize(
    ("scene", "name"),
    [
        # The word that starts a sentence has a capital whatever it is.
        ("Old habits die hard.", "Old Hu"),
        ("Elder disciples laugh by the well.", "Elder Mo"),
        ("“Master the breath first,” she says.", "Master Wen"),
        ("He turns away.\nHope is a thin thing here: hope and rice.", "Hope Ward"),
        # Lower case is no name in prose.
        ("An elder dozes in the sun, and a senior brother shoves past.", "Elder Mo"),
        ("You hope the old master is asleep.", "Old Hu"),
        # The small words of a name call nobody.
        ("The gate is shut. You wait by The Anchor.", "Jon the Younger"),
        ("Nobody is named here.", ""),
    ],
)
def test_a_scene_that_only_looks_like_it_calls_nobody(scene, name):
    assert not told_of(scene, name, EN)

"""G1: whether the player's own words name a goal, a deadline, a question or a person of a
draft, read by code. Every premise here is made up or a starter's own."""

import pytest

from engine.base import DAY, HOUR, WEEK, YEAR
from engine.context import Language
from graph.drafting import samples
from graph.drafting.catalog import starter
from graph.drafting.named import MONTH, called, named, timed, times_ahead
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

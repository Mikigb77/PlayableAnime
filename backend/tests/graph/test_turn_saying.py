"""S10: the engine's own lines of a turn come out in the story's language.

The fixed lines from a book in code, the rest from the cheapest model beside the narrator, with
the decided steps held until their lines are said (A3, B8). Code keeps a said line only when its
numbers and names are the engine's.
"""

import asyncio
import inspect

import pytest

from engine.context import Language, Rating, StorySettings, TurnContext
from engine.contracts import (
    Aim,
    BeatVerdict,
    DirectorPlan,
    EventKind,
    EventSource,
    Harm,
    OutcomeClass,
    Peril,
    PlannedEvent,
    Resolution,
    StepResolution,
)
from engine.resolve import chain, core
from engine.resolve.core import NOTHING_IN_THE_WAY
from engine.resolve.perils import MISS_COSTS
from engine.resolve.throw import told
from engine.resolve.words import cap
from engine.samples import grounded_world
from engine.state.records import Mark, Origin, PendingEvent, StepResult, Thread, ThreadKind
from engine.state.world import EventSize
from graph.llm import Block, Fail, Hang, Node, Reply
from graph.turn import (
    EndingRefused,
    NarrationDelta,
    StepsDecided,
    TurnInput,
    TurnKind,
    run_turn,
    saying,
)
from graph.turn.ending import CLAIMED
from graph.turn.scene import without_throw
from graph.turn.types import (
    BeatDetail,
    DieDetail,
    LinkDetail,
    NumberPartDetail,
    RollDetail,
    SceneDetails,
    StepDetail,
    StruckDetail,
    ThrowDetail,
)
from tests.graph.conftest import collect, run
from tests.graph.test_turn_graph import (
    CLIMB,
    FARMING,
    QUIET_SCENE,
    SCENE,
    play,
    quiet_farm,
    streamed,
    turn_input,
)

SPANISH = StorySettings(language=Language.ES)
CATALAN = StorySettings(language=Language.CA)
# What the engine writes around CLIMB's throw, and how the scripted model says it.
HAND, TASK = "Speed, 2 dice", "a hard task, level 3"
SAID = {HAND: "Velocidad, 2 dados", TASK: "una tarea difícil, nivel 3"}


def says(fake, said=SAID):
    """Scripts the wording model to answer each line it is asked for from `said`, and to leave
    out a line `said` doesn't hold."""

    def reply(request):
        assert request.node is Node.WORDING, f"no scripted reply left for {request.node.value!r}"
        lines = [
            {"n": n, "text": said[text]}
            for n, text in saying.lines_asked(request.prompt)
            if text in said
        ]
        return Reply(json={"lines": lines})

    fake.default = reply


def thrown(**changes) -> ThrowDetail:
    fields = {
        "dice": [DieDetail(kind="plain", face=9), DieDetail(kind="plain", face=9)],
        "hand": 2,
        "hand_why": HAND,
        "greens": ["the high ground"],
        "number": 27,
        "made_of": [
            NumberPartDetail(text=TASK, points=27),
            NumberPartDetail(text="you are wounded", points=5),
        ],
        "total": 18,
        "most": 40,
        "mark": Mark.MISSED,
        "against": "A veteran guard, awake and facing you.",
        "miss_costs": MISS_COSTS[next(iter(MISS_COSTS))],
    }
    return ThrowDetail(**(fields | changes))


def every_line() -> saying.Lines:
    roll = RollDetail(
        odds_label="18 against 27", result=StepResult.FAILURE, seed="s", throw=thrown()
    )
    plain = RollDetail(odds_label="certain", result=StepResult.SUCCESS, seed="s")
    step = StepDetail(
        text="vault the wall",
        outcome_class=OutcomeClass.CONTESTED,
        reason="The wall is slick.",
        roll=roll,
        beats=[
            BeatDetail(
                beat="grab the rope",
                thing="a rope",
                verdict=BeatVerdict.MADE_CANON,
                reason="There is a rope here.",
                roll=plain,
            )
        ],
        struck=[
            StruckDetail(
                by="The guard",
                outcome_class=OutcomeClass.CERTAIN,
                harm=Harm.HURT,
                reason="The guard strikes back. It hurts you.",
            )
        ],
    )
    link = LinkDetail(
        link="oil burns", outcome_class=OutcomeClass.CERTAIN, reason="It follows from oil."
    )
    return saying.Lines(SceneDetails(steps=[step], chain=[link]), "A stranger appears")


def test_the_lines_are_the_engines_and_never_the_players_words():
    lines = every_line()

    assert lines.texts() == [
        "The wall is slick.",
        HAND,
        "the high ground",
        TASK,
        "you are wounded",
        "A veteran guard, awake and facing you.",
        MISS_COSTS[next(iter(MISS_COSTS))],
        "There is a rope here.",
        "certain",
        "The guard",
        "The guard strikes back. It hurts you.",
        "It follows from oil.",
        "A stranger appears",
    ]
    loud = lines.reworded(str.upper)
    [step] = loud.details.steps
    # What the player or a model wrote in the story's language is left as it was.
    assert (step.text, step.beats[0].beat, step.beats[0].thing) == (
        "vault the wall",
        "grab the rope",
        "a rope",
    )
    assert loud.details.chain[0].link == "oil burns"
    assert step.roll.odds_label == "18 against 27"  # the dice show a throw's own numbers
    assert loud.texts() == [text.upper() for text in lines.texts()]
    assert step.roll.throw.dice == lines.details.steps[0].roll.throw.dice
    assert lines.details.steps[0].reason == "The wall is slick."  # the lines given are untouched


def test_the_book_holds_the_engines_own_lines_in_both_languages():
    fixed = {NOTHING_IN_THE_WAY, "It follows.", "A close call.", "certain", CLAIMED}
    fixed |= set(MISS_COSTS.values())
    assert set(saying.BOOK) == {Language.ES, Language.CA}
    for book in saying.BOOK.values():
        assert set(book) == fixed
        assert all(said.strip() and said != english for english, said in book.items())
    # The lines code writes inline are still worded as the book has them.
    assert '"It follows."' in inspect.getsource(chain)
    assert '"A close call."' in inspect.getsource(core)
    assert 'odds_label="certain"' in inspect.getsource(core)


@pytest.mark.parametrize(
    ("english", "said", "kept"),
    [
        ("Speed, 2 dice", "Velocidad, 2 dados", True),
        ("Speed, 2 dice", "Velocidad, dos dados", False),  # a number in words
        ("Speed, 2 dice", "Velocidad, 3 dados", False),
        ("18 against 37: 2 short", "18 contra 37: faltan 2", True),
        ("Elder Mo strikes back. It kills you.", "Elder Mo contraataca. Te mata.", True),
        ("Elder Mo strikes back. It kills you.", "El anciano Mo contraataca. Te mata.", True),
        ("Elder Mo strikes back. It kills you.", "El anciano contraataca. Te mata.", False),
        (
            "one rung above you, Foundation Establishment over Qi Condensation (+10)",
            "un peldaño por encima de ti, Foundation Establishment sobre Qi Condensation (+10)",
            True,
        ),
        (
            "one rung above you, Foundation Establishment over Qi Condensation (+10)",
            "un peldaño por encima de ti, Establecimiento de la Base sobre Qi Condensation (+10)",
            False,
        ),
        ("Zhao Kun's strength and speed, level 3", "fuerza y velocidad de Zhao Kun, nivel 3", True),
        ("You find it: Falling Star Release.", "Lo encuentras: Falling Star Release.", True),
        ("You find it: Falling Star Release.", "Lo encuentras: Liberación de Estrella.", False),
        (
            "Nothing stands in the way. The road is dry.",
            "Nada lo impide. El camino está seco.",
            True,
        ),
        (  # what follows a semicolon starts a sentence of its own
            "It follows from oil; The hall has a single door.",
            "Se sigue del aceite; la sala tiene una sola puerta.",
            True,
        ),
        ("It follows.", "", False),
        ("It follows.", "Se sostiene. " + "Y además llueve. " * 6, False),  # it runs on
        # The English line handed back is no wording of it, however it is spaced or cased.
        ("The guard strikes back.", "The guard strikes back.", False),
        ("There is una piedra suelta here.", "there is  una piedra suelta here.", False),
        ("Speed, 2 dice", "Speed, 2 dice", False),
        ("There is una piedra suelta here.", "Aquí hay una piedra suelta.", True),
        # What was the story's own already comes back as it stood, and that is its wording.
        ("el derrumbe del techo", "el derrumbe del techo", True),
        ("Zhao Kun", "Zhao Kun", True),
        ("Falling Star Release", "Falling Star Release", True),
    ],
)
def test_a_said_line_keeps_the_engines_numbers_and_names(english, said, kept):
    assert saying.faithful(english, said) is kept


def test_an_english_line_handed_back_counts_as_kept_and_is_asked_again(fake, make_client):
    """S10: the log's `lines_kept` shows it, and the next turn asks for the line again."""
    danger = "el derrumbe del techo"
    says(fake, {HAND: HAND, TASK: "una tarea difícil, nivel 3", danger: danger})

    async def said():
        wording = saying.begin(make_client(), [HAND, TASK, danger], Language.ES)
        issues = await wording.settle()
        return wording, issues, saying.begin(make_client(), [HAND, TASK, danger], Language.ES)

    wording, issues, again = run(said())

    assert [(i.code, i.detail) for i in issues] == [(saying.KEPT, "1 of 3")]
    assert wording.word(HAND) == HAND and wording.word(danger) == danger
    assert again.asked == 1 and again.word(TASK) == "una tarea difícil, nivel 3"
    assert saying.lines_asked(fake.calls(Node.WORDING)[-1].prompt) == [(1, HAND)]
    again.task.cancel()


def struck_back(by: str, *foe_ids: str) -> Resolution:
    blow = Peril(
        by_ids=list(foe_ids),
        by=by,
        aim=Aim.WOUND,
        outcome_class=OutcomeClass.CERTAIN,
        reason=f"{cap(by)} strikes back. It hurts you.",
        result=StepResult.SUCCESS,
        harm=Harm.HURT,
    )
    step = StepResolution(
        index=0,
        text="aguantar la puerta",
        outcome_class=OutcomeClass.CERTAIN,
        reason=NOTHING_IN_THE_WAY,
        result=StepResult.SUCCESS,
        duration_s=30,
        perils=[blow],
    )
    return Resolution(steps=[step])


def test_the_name_of_a_lone_foe_stands_and_the_rest_of_who_struck_is_said():
    """S10: a name is the story's own, so nothing says it again. Several foes are joined by
    the engine's "and", and a danger may be one the engine worded."""
    troll = "el trol de las cavernas"
    alone = saying.lines_of(struck_back(troll, "troll"), DirectorPlan(), Language.ES)

    assert alone.kept == {troll}
    assert alone.texts() == [
        NOTHING_IN_THE_WAY,
        "El trol de las cavernas strikes back. It hurts you.",
    ]
    assert alone.reworded(str.upper).details.steps[0].struck[0].by == troll

    for by, ids in (("Zhao Kun and Elder Mo", ("zhao", "mo")), ("the long drop", ())):
        told_by = saying.lines_of(struck_back(by, *ids), DirectorPlan(), Language.ES)
        assert not told_by.kept and by in told_by.texts()


def test_an_english_story_says_nothing_again(fake, make_client):
    async def begun():
        return saying.begin(make_client(), [HAND, NOTHING_IN_THE_WAY], Language.EN)

    wording = run(begun())

    assert wording.task is None and wording.said == {}
    assert wording.word(HAND) == HAND and fake.requests == []


def test_the_book_says_its_lines_with_no_model(fake, make_client):
    async def begun():
        return saying.begin(make_client(), [NOTHING_IN_THE_WAY, "certain", "65%", ""], Language.CA)

    wording = run(begun())

    assert wording.task is None and fake.requests == []
    assert wording.word(NOTHING_IN_THE_WAY) == "Res no ho impedeix."
    assert wording.word("certain") == "segura"
    assert wording.word("65%") == "65%"  # nothing to say in a line with no words


def test_the_model_says_the_rest_once_and_it_is_remembered(fake, make_client):
    says(fake)

    async def said_twice():
        first = saying.begin(make_client(), [HAND, TASK, HAND, NOTHING_IN_THE_WAY], Language.ES)
        issues = await first.settle()
        again = saying.begin(make_client(), [TASK, HAND], Language.ES)
        other = saying.begin(make_client(), [HAND], Language.CA)
        await other.settle()
        return first, issues, again, other

    first, issues, again, other = run(said_twice())

    assert issues == []
    assert [first.word(text) for text in (HAND, TASK, NOTHING_IN_THE_WAY)] == [
        "Velocidad, 2 dados",
        "una tarea difícil, nivel 3",
        "Nada lo impide.",
    ]
    # Asked for once, each line once, and never the book's.
    asked, catalan = fake.calls(Node.WORDING)
    assert saying.lines_asked(asked.prompt) == [(1, HAND), (2, TASK)]
    assert again.task is None and again.word(TASK) == "una tarea difícil, nivel 3"
    # A line said in Spanish is still to be said in Catalan.
    assert saying.lines_asked(catalan.prompt) == [(1, HAND)]
    prompt = asked.prompt.messages[-1].text
    assert "## LANGUAGE\nSpanish from Spain, speaking to the player as tú" in prompt
    assert "dice: dados" in prompt and "dice: daus" in catalan.prompt.messages[-1].text
    # Health is said so that it fits a man or a woman, since nothing on record says which.
    assert "you are wounded: tienes heridas." in prompt and "con heridas" not in prompt
    assert "you are wounded: tens ferides." in catalan.prompt.messages[-1].text
    system = asked.prompt.system
    assert "never with an adjective that takes a gender" in system
    assert "none comes back in English" in system


def test_a_line_the_model_changed_or_left_out_stays_in_english(fake, make_client):
    says(fake, {HAND: "Velocidad, dos dados", "It kills you.": "Te mata."})

    async def said():
        wording = saying.begin(make_client(), [HAND, TASK, "It kills you."], Language.ES)
        return wording, await wording.settle(), saying.begin(make_client(), [HAND], Language.ES)

    wording, issues, again = run(said())

    assert [wording.word(text) for text in (HAND, TASK, "It kills you.")] == [
        HAND,
        TASK,
        "Te mata.",
    ]
    assert [(i.code, i.detail) for i in issues] == [(saying.KEPT, "2 of 3")]
    assert again.task is not None  # a wording that was dropped is never remembered
    again.task.cancel()


@pytest.mark.parametrize(
    ("steps", "area"),
    [
        ((Hang(),), "late"),
        ((Fail(), Fail()), "llm_unavailable"),
        ((Block(), Block()), "blocked"),
    ],
)
def test_lines_the_model_cant_say_in_time_stay_in_english(
    fake, make_client, monkeypatch, steps, area
):
    monkeypatch.setattr(saying, "GRACE_S", 0.05)
    fake.script(Node.WORDING, *steps)

    async def said():
        wording = saying.begin(make_client(), [HAND, NOTHING_IN_THE_WAY], Language.ES)
        return wording, await wording.settle(), await wording.settle()

    wording, issues, again = run(said())

    assert [(i.code, i.area) for i in issues] == [(saying.UNSAID, area)]
    assert again == []  # settled once
    assert wording.word(HAND) == HAND
    assert wording.word(NOTHING_IN_THE_WAY) == "Nada lo impide."  # the book still speaks


def test_a_wording_that_comes_late_is_remembered_for_the_next_turn(fake, make_client, monkeypatch):
    monkeypatch.setattr(saying, "GRACE_S", 0.01)
    says(fake)
    say = saying.say

    async def said():
        answered = asyncio.Event()

        async def slow(llm, texts, language):
            await answered.wait()
            return await say(llm, texts, language)

        monkeypatch.setattr(saying, "say", slow)
        first = saying.begin(make_client(), [HAND], Language.ES)
        asked = first.task
        issues = await first.settle()
        answered.set()
        await asked
        return first, issues, saying.begin(make_client(), [HAND], Language.ES)

    first, issues, again = run(said())

    assert [(i.code, i.area) for i in issues] == [(saying.UNSAID, "late")]
    assert first.word(HAND) == HAND  # as it was shown
    assert again.task is None and again.word(HAND) == "Velocidad, 2 dados"


def test_a_reason_loses_only_the_sentence_that_tells_its_throw(fake, make_client):
    fake.script(Node.INTERPRET, Reply(json=CLIMB))
    fake.script(Node.NARRATOR, Reply(json=SCENE))
    events, result = play(make_client(), turn_input(action="I climb the wall and get away"))
    roll = result.resolution.steps[0].roll
    sentence = cap(told(roll))

    # A8: an English story's reason tells the throw in words, and the app leaves it out.
    assert events[0].details.steps[0].reason == f"{sentence}."
    assert sentence.startswith("Speed, 2 dice, against a hard task, level 3: ")
    assert without_throw(f"{sentence}.", roll) == ""
    struck = f"Zhao strikes back. {sentence}. It kills you."
    assert without_throw(struck, roll) == "Zhao strikes back. It kills you."
    assert without_throw("Nothing stands in the way.", roll) == "Nothing stands in the way."
    assert without_throw(struck, None) == struck


def test_a_spanish_storys_dice_wait_for_their_lines_and_the_scene_keeps_them(
    fake, make_client, telemetry
):
    """S10, A3, B8: the narrator starts at once, its words wait for the decided steps, and the
    steps go out in the story's language as soon as the cheapest model has said them."""
    says(fake)
    fake.script(Node.INTERPRET, Reply(json=CLIMB))
    fake.script(Node.NARRATOR, Reply(json=SCENE))
    turn = turn_input(action="Trepo por el muro y me escapo", settings=SPANISH)

    events, result = play(make_client(), turn)

    decided, *narrated = events
    assert isinstance(decided, StepsDecided)
    assert narrated and all(isinstance(e, NarrationDelta) for e in narrated)
    assert streamed(events) == SCENE["narration"]
    climb, *walked = decided.details.steps
    throw = climb.roll.throw
    assert throw.hand_why == "Velocidad, 2 dados"
    assert [part.text for part in throw.made_of] == ["una tarea difícil, nivel 3"]
    assert throw.against == "Va a ir justo."
    assert climb.reason == ""  # only the throw, which the dice show
    assert climb.text == "climb the wet wall of the well"  # as the turn was read
    assert {step.reason for step in walked} == {"Nada lo impide."}
    # The dice themselves are the engine's, whatever they are called.
    engine_throw = result.resolution.steps[0].roll.throw
    assert (throw.total, throw.number, throw.mark) == (
        engine_throw.total,
        engine_throw.number,
        engine_throw.mark,
    )
    assert result.scene.details == decided.details
    assert not [i for i in result.issues if i.code in (saying.UNSAID, saying.KEPT)]
    assert [call.node for call in telemetry.calls] == ["interpret", "wording", "narrator"]
    [asked] = fake.calls(Node.WORDING)
    assert saying.lines_asked(asked.prompt) == [(1, HAND), (2, TASK)]
    # The narrator is briefed on what the engine decided, in the engine's own words.
    brief = fake.calls(Node.NARRATOR)[0].prompt.messages[-1].text
    assert "Speed, 2 dice" in brief and "Velocidad" not in brief


def test_a_kept_turn_played_out_again_says_its_lines_the_same_way(fake, make_client, telemetry):
    says(fake)
    fake.script(Node.INTERPRET, Reply(json=CLIMB))
    fake.script(Node.NARRATOR, Reply(json=SCENE), Reply(json=SCENE))
    first, _ = play(make_client(), turn_input(action="Trepo por el muro", settings=SPANISH))
    telemetry.calls.clear()

    again, _ = play(
        make_client(),
        turn_input(action="Trepo por el muro", settings=SPANISH, reading=first[0].reading),
    )

    # A3: what was shown is what plays, and its lines come from memory with no model.
    assert again[0].details == first[0].details
    assert [call.node for call in telemetry.calls] == ["narrator"]


def test_a_turn_nothing_stood_in_the_way_of_calls_no_wording_model(fake, make_client, telemetry):
    fake.script(Node.INTERPRET, Reply(json=FARMING))
    fake.script(Node.NARRATOR, Reply(json=QUIET_SCENE))
    state = quiet_farm()
    state.director.turns_without_stakes = 0  # a quiet turn, with no event

    events, result = play(
        make_client(), turn_input(state, action="Trabajo los campos", settings=CATALAN)
    )

    assert isinstance(events[0], StepsDecided)
    assert [step.reason for step in events[0].details.steps] == ["Res no ho impedeix."]
    assert result.scene.details == events[0].details and result.scene.event is None
    assert [call.node for call in telemetry.calls] == ["interpret", "narrator"]


@pytest.mark.parametrize(
    ("steps", "area"), [((Hang(),), "late"), ((Fail(), Fail()), "llm_unavailable")]
)
def test_dice_whose_lines_cant_be_said_go_out_in_english_before_the_telling(
    fake, make_client, monkeypatch, steps, area
):
    """A turn never waits long for its wording and never fails for it."""
    monkeypatch.setattr(saying, "GRACE_S", 0.05)
    fake.script(Node.WORDING, *steps)
    fake.script(Node.INTERPRET, Reply(json=CLIMB))
    fake.script(Node.NARRATOR, Reply(json=SCENE))

    events, result = play(make_client(), turn_input(action="Trepo por el muro", settings=SPANISH))

    decided, *narrated = events
    assert isinstance(decided, StepsDecided)
    assert streamed(narrated) == SCENE["narration"]  # held back, never lost
    throw = decided.details.steps[0].roll.throw
    assert throw.hand_why == HAND and throw.made_of[0].text == TASK
    assert throw.against == "Va a ir justo."  # the book still speaks
    assert decided.details.steps[0].reason == ""  # the app can't find a throw's sentence here
    assert result.scene.details == decided.details
    assert [(i.code, i.area) for i in result.issues if i.code == saying.UNSAID] == [
        (saying.UNSAID, area)
    ]


def in_guillemets(request):
    """The wording model, scripted to say each line as it stands between « and »."""
    asked = saying.lines_asked(request.prompt)
    return Reply(json={"lines": [{"n": n, "text": f"«{text}»"} for n, text in asked]})


def test_the_directors_title_comes_from_its_book_and_the_scene_carries_it(fake, make_client):
    """W16: a card's title, and the thread it opens, with no model."""
    fake.script(Node.INTERPRET, Reply(json=FARMING))
    fake.script(Node.NARRATOR, Reply(json=QUIET_SCENE))

    events, result = play(
        make_client(), turn_input(quiet_farm(), action="Trabajo los campos", settings=SPANISH)
    )

    title = result.plan.event.title
    assert (title, result.scene.event.title) == ("A rival", "Una rivalidad")
    assert isinstance(events[0], StepsDecided) and fake.calls(Node.WORDING) == []
    assert [step.reason for step in result.scene.details.steps] == ["Nada lo impide."]
    assert result.state.threads[result.plan.event.thread_id].title == "Una rivalidad"
    # The narrator is briefed with the event as the director wrote it.
    assert title in fake.calls(Node.NARRATOR)[0].prompt.messages[-1].text


def test_an_event_the_world_titled_is_said_by_the_model(fake, make_client):
    fake.script(Node.INTERPRET, Reply(json=FARMING))
    fake.script(Node.NARRATOR, Reply(json=QUIET_SCENE))
    fake.default = in_guillemets
    state = quiet_farm()
    state.pending_events["e1"] = PendingEvent(
        id="e1", kind="arrival", title="The bailiff comes", due_s=state.world_s, needs_player=True
    )

    _, result = play(
        make_client(), turn_input(state, action="Trabajo los campos", settings=SPANISH)
    )

    assert result.plan.event.title == "The bailiff comes"
    assert result.scene.event.title == "«The bailiff comes»"
    brief = fake.calls(Node.NARRATOR)[0].prompt.messages[-1].text
    assert "The bailiff comes" in brief and "«The bailiff comes»" not in brief


def test_a_thread_of_the_storys_own_comes_back_under_the_title_it_keeps(fake, make_client):
    """N1: its title is in the story's words already, so nothing says it again. A thread the
    director titled itself, before a story kept its titles in its language, goes by the book."""

    def returning(title: str) -> saying.Lines:
        feud = Thread(id="feud", title=title, kind=ThreadKind.RIVALRY, origin=Origin(kind="event"))
        event = PlannedEvent(
            size=EventSize.PERSONAL,
            kind=EventKind.RIVAL,
            source=EventSource.THREAD,
            source_id="feud",
            title=title,
            brief="It comes back.",
            thread_id="feud",
        )
        plan = DirectorPlan(event=event)
        return saying.lines_of(Resolution(steps=[]), plan, Language.ES, {"feud": feud})

    own = returning("La valla de Bram")
    assert own.kept == {"La valla de Bram"} and own.texts() == []
    assert own.reworded(str.upper).event_title == "La valla de Bram"

    old = returning("A rival")
    assert not old.kept and old.texts() == ["A rival"]

    async def begun():
        return saying.begin(make_client(), old.texts(), Language.ES)

    wording = run(begun())
    assert wording.task is None and fake.requests == []
    assert old.reworded(wording.word).event_title == "Una rivalidad"


def test_an_opening_with_nothing_decided_shows_no_steps(fake, make_client, telemetry):
    fake.script(Node.NARRATOR, Reply(json=SCENE))

    events, result = play(make_client(), turn_input(kind=TurnKind.OPENING, settings=SPANISH))

    assert not any(isinstance(e, StepsDecided) for e in events)
    assert result.scene.details.steps == []
    assert [call.node for call in telemetry.calls] == ["narrator"]


def test_what_the_world_refuses_of_an_ending_is_said_in_the_storys_language(fake, make_client):
    """N6, S10: the reasons the ending card shows."""
    walk = {
        "text": "walk out of the bar for the last time",
        "verb": "walk",
        "kind": "move",
        "proposed_duration_s": 600,
    }
    crown = walk | {"text": "become the king of Italy", "verb": "rule"}
    crown["facts"] = {"means": "clearly_not"}
    note = {"summary": "end", "steps": [crown, walk], "outcome_claims": ["the city mourns me"]}
    fake.script(Node.INTERPRET, Reply(json=note))
    fake.default = lambda request: Reply(
        json={
            "lines": [
                {"n": n, "text": f"«{text}»"} for n, text in saying.lines_asked(request.prompt)
            ]
        }
    )
    state = grounded_world()
    state.turn = 3
    ctx = TurnContext(story_id="story-1", turn=4, rating=Rating.MATURE, settings=SPANISH)
    turn = TurnInput(state=state, ctx=ctx, kind=TurnKind.END, action="Me hago rey")

    with pytest.raises(EndingRefused) as refusal:
        run(collect(run_turn(turn, make_client())))

    crowned, mourned = refusal.value.refused
    assert crowned.text == "become the king of Italy"
    assert crowned.reason.startswith("«") and crowned.reason.endswith("»")
    assert mourned.reason == saying.BOOK[Language.ES][CLAIMED]
    assert fake.calls(Node.NARRATOR) == []

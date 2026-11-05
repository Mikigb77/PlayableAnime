"""N6 on the turn graph: someone new carries the story on with an opening of their own, and the
people who knew an earlier player character can remember them."""

from engine.base import YEAR
from engine.context import Rating, TurnContext
from engine.samples import grounded_world
from engine.state import Character, CharacterStatus, DeathCertainty, Deed, StatusChange
from engine.succession import carry_on
from graph.llm import Node, Reply
from graph.turn import TurnCompleted, TurnInput, TurnKind, prompts, run_turn
from tests.graph.conftest import collect, run

OPENING = {
    "narration": "The wagon's axle groans as Mara heaves the first crate.",
    "suggestions": [{"label": "Brace the axle", "kind": "personal"}],
}


def carried(*, gennaro_saw_it: bool = False, deed: Deed | None = None):
    """Luca, who had met Gennaro, died at turn 3, seen by Gennaro if asked; Mara carries the story
    on."""
    state = grounded_world()
    state.turn = 3
    luca = state.player
    luca.status = CharacterStatus.DEAD
    luca.death_certainty = DeathCertainty.CONFIRMED
    state.characters["bartender"].met_by = ["luca"]
    # Luca died alone; who knew of it is as asked.
    state.scene.present_ids = ["luca"]
    if deed is not None:
        state.deeds[deed.id] = deed
    luca.status_history.append(
        StatusChange(
            status="dead",
            from_status="alive",
            turn=3,
            world_s=state.world_s,
            known_by=["bartender"] if gennaro_saw_it else [],
        )
    )
    mara = Character(id="pc-2", name="Mara Venn", location_id="naples")
    return carry_on(state, mara, "Dawn at the docks.", ending="death", turn=3)


def opening_of(state):
    ctx = TurnContext(story_id="story-1", turn=state.turn + 1, rating=Rating.MATURE)
    return TurnInput(state=state, ctx=ctx, kind=TurnKind.OPENING)


def told(fake) -> str:
    [request] = fake.calls(Node.NARRATOR)
    return request.prompt.messages[-1].text


def test_someone_new_gets_an_opening_of_their_own(fake, make_client):
    fake.script(Node.NARRATOR, Reply(json=OPENING))

    events = run(collect(run_turn(opening_of(carried()), make_client())))

    result = events[-1].result
    assert isinstance(events[-1], TurnCompleted)
    assert result.scene.kind is TurnKind.OPENING and result.scene.player_action is None
    assert result.state.turn == 4 and not result.state.opening_due
    assert result.state.player_id == "pc-2"
    prompt = told(fake)
    assert prompts.SUCCESSION_TASK in prompt and prompts.OPENING_TASK not in prompt
    assert "Dawn at the docks." in prompt


def test_people_who_knew_the_fallen_remember_them(fake, make_client):
    state = carried(gennaro_saw_it=True)
    state.scene.present_ids.append("bartender")
    fake.script(Node.NARRATOR, Reply(json=OPENING))

    run(collect(run_turn(opening_of(state), make_client())))

    prompt = told(fake)
    assert "FALLEN" in prompt and "Luca Esposito" in prompt
    assert '"name":"Gennaro","knows_how_it_ended":true' in prompt


def test_someone_who_never_heard_of_the_death_doesnt_know_it(fake, make_client):
    state = carried(gennaro_saw_it=False)
    state.scene.present_ids.append("bartender")
    fake.script(Node.NARRATOR, Reply(json=OPENING))

    run(collect(run_turn(opening_of(state), make_client())))

    assert '"name":"Gennaro","knows_how_it_ended":false' in told(fake)


def test_word_of_the_killing_tells_someone_how_it_ended(fake, make_client):
    killing = Deed(
        id="deed-1",
        actor_id="carmine",
        kind="kill",
        text="Carmine shot Luca on the quay",
        turn=3,
        world_s=0,
        victim_ids=["luca"],
        known_by=["bartender"],
    )
    state = carried(deed=killing)
    state.scene.present_ids.append("bartender")
    fake.script(Node.NARRATOR, Reply(json=OPENING))

    run(collect(run_turn(opening_of(state), make_client())))

    assert '"name":"Gennaro","knows_how_it_ended":true' in told(fake)


def test_someone_the_fallen_never_met_doesnt_remember_them(fake, make_client):
    state = carried()
    state.characters["bartender"].met_by = []
    state.scene.present_ids.append("bartender")
    fake.script(Node.NARRATOR, Reply(json=OPENING))

    run(collect(run_turn(opening_of(state), make_client())))

    assert "FALLEN" not in told(fake)


def test_nobody_brings_up_the_fallen_when_nobody_there_knew_them(fake, make_client):
    fake.script(Node.NARRATOR, Reply(json=OPENING))

    run(collect(run_turn(opening_of(carried()), make_client())))

    assert "FALLEN" not in told(fake)


def test_an_heirs_opening_is_told_how_long_ago_the_last_story_ended(fake, make_client):
    """N6: an heir too young to act starts years after the ending, and the narrator knows it."""
    state = carried()
    fake.script(Node.NARRATOR, Reply(json=OPENING))
    state.world_s += 16 * YEAR

    run(collect(run_turn(opening_of(state), make_client())))

    assert "## ENDED\nLuca Esposito's story ended 16 years ago." in told(fake)


def test_an_opening_right_after_the_ending_says_nothing_of_time_gone_by(fake, make_client):
    fake.script(Node.NARRATOR, Reply(json=OPENING))

    run(collect(run_turn(opening_of(carried()), make_client())))

    assert "## ENDED" not in told(fake)

"""R3: how much a scene holds, which its length follows.

Every scene used to come out about the same size. In Miki's long story, read on 2026-11-10, the
typical scene was 258 words and nine in ten were under 315, whether one question was asked or a
duel was fought. So code weighs each scene from what the engine recorded, and the narrator is
told the length that weight gets within the player's own setting (S6, `graph.turn.prompts`).

- **A turning point** gets room: one of the key scenes a picture may mark (M1,
  `pictures.key_moment`), whether or not it gets one, or the player character left badly
  wounded or dying.
- **A passing moment** is told short: one small step, played whole, with nothing at stake and
  nothing thrown, under an hour long and outside any encounter, in a scene that has nothing
  else to tell. A small step is a few things done and a line or two said (`PASSING_BEATS`,
  `PASSING_WORDS`): the scene tells each thing the player described and says their lines word
  for word (R1, R7), so a long action needs the room. Something else to tell is what the
  director planned for it (an event, a small thing of the moment, a happening, the talk of the
  place), something the world did within sight (`due.in_sight`), someone met for the first
  time, a trip, a deed, growth, or anyone hurt. A thread offered to call back to is not: the
  narrator may leave it.
- Anything else is an ordinary scene, at the setting's own length.

The opening scene is ordinary: it has no action to weigh. A story's ending is a turning point
whatever the turn held (`told`), since the director plans no ending.
"""

from engine.base import HOUR
from engine.contracts.direction import DirectorPlan, SceneWeight
from engine.contracts.intent import Intent, OutcomeClass
from engine.contracts.resolution import Resolution
from engine.director.pressure import Pressure
from engine.director.turn import TurnFacts, player_deeds
from engine.state.records import StepResult
from engine.state.world import WorldState

# A passing moment is over well inside this: a word, a look, a coin held out.
PASSING_S = HOUR
# And the player told it in as much: up to three things done, and a line or two said.
PASSING_BEATS = 3
PASSING_WORDS = 30


def weigh(
    state: WorldState,
    resolution: Resolution,
    facts: TurnFacts,
    pressure: Pressure,
    intent: Intent | None = None,
    *,
    key: bool,
    planned: bool,
) -> SceneWeight:
    """The scene's weight. `key` says the turn is one of M1's key scenes, and `planned` that
    the scene has something besides the action to tell: what the director gave it, or what the
    world did within sight. `intent` is the turn as it was read, for the player's own lines."""
    player = state.player_id
    if key or player in facts.gravely_hurt or player in facts.died:
        return SceneWeight.HEAVY
    if planned or pressure.stakes or pressure.encounter or not _passing(resolution, intent):
        return SceneWeight.ORDINARY
    more = (
        player_deeds(state, facts)
        or facts.died
        or facts.gravely_hurt
        or facts.subdued
        or facts.changed_places
        or any(who == player for who, _ in facts.gains)
        or state.journey is not None
    )
    return SceneWeight.ORDINARY if more else SceneWeight.LIGHT


def told(plan: DirectorPlan, *, ending: bool) -> SceneWeight:
    """The weight of the scene as it is told: what the director weighed, or a turning point when
    the scene ends the player character's story (N6)."""
    return SceneWeight.HEAVY if ending else plan.weight


def _passing(resolution: Resolution, intent: Intent | None) -> bool:
    """Whether what was played is one small step that simply went through: nothing thrown, for
    the step or for a thing it looked for, no chain of cause and effect, nothing striking back,
    nobody new met, nowhere gone, nothing of the plan left unplayed, and no more done or said
    in it than a short scene can tell."""
    if len(resolution.steps) != 1 or resolution.unplayed or resolution.stop_reason is not None:
        return False
    step = resolution.steps[0]
    reads = intent.steps if intent is not None else ()
    done = sum(len(read.beats) for read in reads)
    said = sum(len(line.split()) for read in reads for line in read.lines)
    return (
        step.outcome_class is OutcomeClass.CERTAIN
        and step.result is StepResult.SUCCESS
        and step.roll is None
        and not step.chain
        and not step.interrupted
        and not step.perils
        and not step.strangers
        and step.trip is None
        and step.duration_s < PASSING_S
        and all(beat.roll is None for beat in step.beats)
        and done <= PASSING_BEATS
        and said <= PASSING_WORDS
    )

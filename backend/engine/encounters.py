"""W10: encounters. A fight, a chase, a duel of words or a negotiation is an encounter, and code
starts and ends it. The interpret step may propose a kind; it never decides one.

While an encounter is on, its turns don't count as quiet and the director brings in nothing
unrelated (W16), a day-long stretch rolls no montage events (E7), and a fight with a key NPC or a
strong monster gets its start and its decisive blow pictured (M1, M2). `pipeline.play_out` calls
these on its working copy before and after each step, and `settle` once the plan is over:

- **Start.** A step that aims harm at a living character starts a fight with them and with
  whoever pushes back on it. A step the interpret step proposed as a chase, a duel of words or a
  negotiation starts one with whoever faces it and can respond (`StepResolution.encounter`, set by
  resolve). A step settled before it was tried, such as reaching for a sword that isn't there,
  starts nothing: it met no one. An NPC's step starts one only when it is aimed at the player
  character, with that NPC as the opponent.
- **Carry on.** A later step that fights someone new brings them in, and one that starts some
  other kind brings in whoever it faces unless a fight is on. A step that faces one of its
  opponents, starts one, or is an exchange (a blow, a shot, a spell) is one of its exchanges.
  Something that isn't a fight turns into one when a step fights; a fight stays a fight whatever
  else is proposed, since a chase inside a fight is the same fight.
- **A bout.** A fight both sides agreed to has terms (W1, `engine.resolve.bouts`). Resolve
  decides the bout a step was fought in (`StepResolution.bout`); here it is kept on the
  encounter (`Encounter.bout`) with whom it was agreed, from the step that began it until the
  encounter ends or a blow goes beyond its terms (`StepResolution.broke_terms`). A fight in
  which someone was harmed outside any terms, or whose terms were broken, is fought in earnest
  (`Encounter.in_earnest`) and never becomes a bout: an attack isn't relabelled as one.
- **End.** It ends when none of its opponents is still in it (each is dead, missing, helpless, or
  somewhere the player character isn't), when a step of the player character's got cleanly away
  from all of those still in it (N6), when the player character is dead or helpless, or when
  `LAPSE_S` of in-world time pass with no exchange: a truce, a surrender or walking away. A time
  skip, or a step as long as that which doesn't fight or carry on the encounter itself, such as a
  night's sleep, ends it before it plays, so the stretch gets its events (E7). A time skip is a
  montage and never starts one. Nothing here is timed in turns (W10).

Plain Python, like the rest of the engine (B4).
"""

from engine.base import MINUTE
from engine.context import TurnContext
from engine.contracts.intent import ActionKind
from engine.contracts.resolution import StepResolution
from engine.resolve.power import helpless_state, in_the_fray
from engine.state.cast import Prominence
from engine.state.scene import Encounter, EncounterKind
from engine.state.world import WorldState

# An encounter with no exchange for this long in in-world time is over (W10).
LAPSE_S = 10 * MINUTE
# How far a strong monster or foe stands above the player on the might axis (A8), for M1's fight
# pictures, when the encounter doesn't say.
STRONG_FOE_TIERS = 2


def strong_foe(state: WorldState, character_id: str) -> bool:
    """M1. A key NPC, or a foe well above the player character on the might axis (A8)."""
    foe = state.characters.get(character_id)
    if foe is None:
        return False
    if foe.prominence is Prominence.KEY:
        return True
    return _might(state, character_id) >= _might(state, state.player_id) + STRONG_FOE_TIERS


def _might(state: WorldState, character_id: str) -> int:
    sheet = state.characters[character_id].sheet
    return sheet.axes.might - sheet.condition.weakened_tiers


def before_step(state: WorldState, step: StepResolution, actor_id: str) -> None:
    """A time skip, or a step of `LAPSE_S` or more that isn't itself part of the encounter, such
    as a night's sleep, a day's work or a week on the road beside a foe, ends it before it plays:
    nobody sleeps through a fight, and the stretch gets its events (E7, W10). A long step stays
    part of it only when it fights or carries on the encounter itself, such as an hours-long
    chase."""
    encounter = state.scene.encounter
    if encounter is None:
        return
    if step.kind is ActionKind.TIME_SKIP:
        state.scene.encounter = None
    elif step.duration_s >= LAPSE_S and not (
        step.encounter is not None and _opponents(state, step, actor_id)
    ):
        state.scene.encounter = None


def follow(state: WorldState, step: StepResolution, actor_id: str, ctx: TurnContext) -> None:
    """After a step played out in full: start an encounter, bring someone new into it, count an
    exchange, or end it when the player character got away from everyone still in it (N6). A
    step cut short by an event didn't happen as resolved, and a time skip is a montage, never an
    encounter (E7), so they do none of these."""
    if step.interrupted or step.kind is ActionKind.TIME_SKIP:
        return
    opponents = _opponents(state, step, actor_id)
    end_s = step.end_s if step.end_s is not None else state.world_s
    encounter = state.scene.encounter
    if encounter is None:
        if step.encounter is None or not opponents:
            return
        start_s = step.start_s if step.start_s is not None else end_s
        state.scene.encounter = Encounter(
            kind=step.encounter,
            opponent_ids=opponents,
            started_turn=ctx.turn,
            started_s=start_s,
            last_s=end_s,
            key=any(strong_foe(state, i) for i in opponents),
            bout=step.bout,
            in_earnest=step.broke_terms or _drew_blood(step),
        )
        return
    if step.escaped and actor_id == state.player_id:
        behind = set(step.escaped)
        if not any(still_in_it(state, i) for i in encounter.opponent_ids if i not in behind):
            state.scene.encounter = None  # N6: they got away from everyone still in it
            return
    exchange = _exchange(state, encounter, step, actor_id, opponents)
    fight = encounter.kind is EncounterKind.FIGHT
    _keep_terms(encounter, step)
    # A fight takes in only those a step fights; anything else takes in whoever its steps face,
    # and turns into whatever they make it, a fight included.
    joins = step.encounter is EncounterKind.FIGHT or (step.encounter is not None and not fight)
    if joins and opponents:
        new = [i for i in opponents if i not in encounter.opponent_ids]
        encounter.opponent_ids = [*encounter.opponent_ids, *new]
        encounter.key = encounter.key or any(strong_foe(state, i) for i in new)
        if not fight:
            encounter.kind = step.encounter
    if exchange:
        encounter.last_s = end_s


def _keep_terms(encounter: Encounter, step: StepResolution) -> None:
    """W1. The bout as the step leaves it: over once a blow went beyond its terms, else as the
    step was fought in it (its terms only get milder, and someone new may have joined). A step
    that harmed someone outside any terms, or broke them, makes the fight one in earnest, which
    never becomes a bout."""
    if step.broke_terms:
        encounter.bout, encounter.in_earnest = None, True
    elif step.bout is not None and (encounter.bout is not None or not encounter.in_earnest):
        encounter.bout = step.bout
    if _drew_blood(step):
        encounter.in_earnest = True


def _drew_blood(step: StepResolution) -> bool:
    """W1. Whether a blow of the step harmed someone outside the terms of any bout."""
    return any(deed.victim_ids and deed.terms is None for deed in step.deeds)


def settle(state: WorldState) -> None:
    """End the encounter when nothing keeps it on: none of its opponents is still in it, the
    player character is dead or helpless, or `LAPSE_S` passed with no exchange."""
    encounter = state.scene.encounter
    if encounter is None:
        return
    player = state.player
    since = encounter.last_s if encounter.last_s is not None else encounter.started_s
    over = (
        not player.alive
        or helpless_state(player) is not None
        or state.world_s - since >= LAPSE_S
        or not any(still_in_it(state, i) for i in encounter.opponent_ids)
    )
    if over:
        state.scene.encounter = None


def still_in_it(state: WorldState, character_id: str) -> bool:
    """Whether an opponent is still in the encounter: alive and not missing, able to act (not
    asleep, bound, subdued or dying), and with the player character, which means in the scene or
    at the player character's place. Someone the state doesn't place stays in it."""
    character = state.characters.get(character_id)
    return character is not None and in_the_fray(state, character)


def _opponents(state: WorldState, step: StepResolution, actor_id: str) -> list[str]:
    """Whom the step pits the player character against: whoever the player's step fought or
    faced, or the NPC whose step was aimed at the player character."""
    player = state.player_id
    if actor_id != player:
        return [actor_id] if player in step.opponent_ids and actor_id in state.characters else []
    return [i for i in dict.fromkeys(step.opponent_ids) if i != player and i in state.characters]


def _exchange(
    state: WorldState,
    encounter: Encounter,
    step: StepResolution,
    actor_id: str,
    opponents: list[str],
) -> bool:
    """Whether a step is one of the encounter's exchanges: it faces one of its opponents (whom the
    step pits the player against, from `_opponents`), fights or proposes it with someone, or is a
    blow, a shot or a spell."""
    if step.encounter is not None and opponents:
        return True
    if set(opponents) & set(encounter.opponent_ids):
        return True
    return step.kind is ActionKind.EXCHANGE and actor_id == state.player_id

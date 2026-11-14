"""Someone near walks into the scene (W10, W4).

Only the world moves people between places, and a narrated scene has the people the record
puts where it plays (`engine.apply.Door`). The narrator is told as much, and now and then
tells someone in all the same: a commander whose boots were on the path arrives, a miller
brings the smith a broken brace. In the first plays by hand on the real models (2026-11-14)
it did so in four scenes of ninety-nine, the record kept them where it had them, and the story
and its Memory parted ways: the commander stood in the yard and had never been met.

So a scene may have someone it knows walk in when the world allows it (`within_reach`), and the
record follows: they are at the scene's place, and they go back where they were after a while
(`settle`, by `engine.world.returns`). Code decides who may, never the scene:

- the scene's own words name them, so the player read that they came. A list of who is
  present that names someone the scene never told puts nobody there;
- the map has them near enough to have come in the time the turn took, with an hour's start
  (`WALK_IN_S`) and a day's way at most (`WALK_IN_MAX_S`), so nobody crosses a kingdom to
  stand in a doorway;
- nothing holds them: they are alive and not missing, in a state to walk, and on no errand or
  round trip of the world's making, whose comings and goings are the world's to time (W4,
  W6, W11). Someone who came for the character to another place and found them gone is
  there, looking (the husband of the first stories about an affair, 2026-11-13);
- no romance of the player character's wrongs them, nor one between two people of the scene
  (`bonds.wronged`): who walks in on one is the engine's to decide, by who sees a move (W17).
  The wronged wife of the same stories stays at her farm;
- the turn did nothing for them to walk in on. Who saw a deed or a move in a romance was
  decided before the scene was told (W2, W17), so on a turn with either, or with a fight, a
  chase or talks running, nobody comes.
"""

from engine import bonds
from engine.contracts.resolution import Resolution
from engine.naming import named_in
from engine.resolve.power import helpless_state
from engine.state.cast import Character, CharacterStatus
from engine.state.world import WorldState
from engine.world.geography import scene_ids, ways_from
from engine.world.returns import errands_of, left, trip_of
from engine.world.scheduling import World
from engine.world.tuning import VISIT_STAY_S, WALK_IN_MAX_S, WALK_IN_S


def within_reach(state: WorldState, resolution: Resolution, turn: int, told: str) -> list[str]:
    """Whom a narrated scene may have walk in from where the record has them, by id. `state`
    is the world the steps left, `turn` the turn being played and `told` the scene's words."""
    if state.scene.encounter is not None or _done(state, turn):
        return []
    ways = ways_from(state, state.player.location_id or state.scene.place_id)
    reach_s = min(WALK_IN_S + max(0, resolution.duration_s), WALK_IN_MAX_S)
    wronged = _wronged(state)
    near = [
        character.id
        for character in state.npcs()
        if ways.get(character.location_id or "", reach_s + 1) <= reach_s
        and character.id not in wronged
        and _free(state, character)
    ]
    if not near:
        return []
    # A word of a name that someone in the scene shares names nobody new: "Zhao" is the Zhao
    # who is there.
    named = named_in(state, [told], [*scene_ids(state), *near], anywhere=True)
    return [character_id for character_id in near if character_id in named]


def _free(state: WorldState, character: Character) -> bool:
    """Whether nothing holds someone where they are: they live and aren't missing, can walk,
    and are on no errand and no round trip of the world's making."""
    if not character.alive or character.status is not CharacterStatus.ALIVE:
        return False
    if helpless_state(character) is not None:
        return False
    return not errands_of(state, character.id) and trip_of(state, character.id) is None


def _wronged(state: WorldState) -> set[str]:
    """Whom a romance that isn't over wrongs (W17): one of the player character's, with
    whomever it is and wherever they are, or one between two people of the scene."""
    scene = set(scene_ids(state))
    return {
        who
        for bond in state.bonds.values()
        if bond.stage.live
        and (bond.holds(state.player_id) or (bond.a_id in scene and bond.b_id in scene))
        for who in bonds.wronged(state, bond.a_id, bond.b_id)
    }


def _done(state: WorldState, turn: int) -> bool:
    """Whether the turn put a deed on record: something done that people saw or didn't (W2),
    a move in a romance among them (W17)."""
    return any(
        deed.turn == turn and deed.timeline_id == state.timeline_id for deed in state.deeds.values()
    )


def settle(w: World, came: list[tuple[str, str]]) -> None:
    """Whoever walked into the scene (`engine.apply.Applied.came`, each with the place the
    record had them at) is on a round trip from there: they stay a while and go back, once
    the scene no longer has them (`returns.on_return`)."""
    for character_id, from_id in came:
        who = w.state.characters.get(character_id)
        if who is not None and who.alive:
            left(w, who, from_id, VISIT_STAY_S)

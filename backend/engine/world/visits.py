"""Someone near walks into the scene (W10, W4).

Only the world moves people between places, and a narrated scene has the people the record
puts where it plays (`engine.apply.Door`). The narrator is told as much, and now and then
tells someone in all the same. In the first plays by hand on the real models (2026-11-14) it
did so in four scenes of ninety-nine: a commander whose boots the opening had heard on the
path steps into the yard, a miller brings the smith a broken brace, a mermaid the old
fisherman calls from the beach rises from the water. The record kept each where it had them,
and the story and its Memory parted ways: the commander stood in the yard and had never been
met, and the next scene was told as if he were not there.

So a scene may have someone it knows walk in when the world allows it (`within_reach`), and the
record follows: they are at the scene's place, and they go back where they were after a while
(`settle`, by `engine.world.returns`). Code decides who may, never the scene:

- the scene tells them: its own words name them, or its update has them meet the player
  character, as it does for someone shown by their look alone (C6). A list of who is present
  that names someone the scene neither named nor had them meet puts nobody there;
- the map has them within a day's way (`WALK_IN_MAX_S`), so nobody crosses a kingdom to stand
  in a doorway, and the player character wasn't with them too lately for them to have made
  that way since, with an hour's start (`WALK_IN_S`). Where someone the story hasn't shown
  is at this very hour is nobody's knowledge: the record has where they keep;
- nothing holds them: they are alive and not missing, in a state to walk, and on no errand or
  round trip of the world's making, whose comings and goings are the world's to time (W4,
  W6, W11). Someone who came for the character to another place and found them gone is
  there, looking (the husband of the first stories about an affair, 2026-11-13);
- no romance between two people who are in the scene or where it plays wrongs them
  (`bonds.wronged`): who walks in on one is the engine's to decide, by who sees a move (W17).
  The wronged wife of the same stories stays at her farm;
- the turn did nothing for them to walk in on. Who saw a harm done or a move in a romance was
  decided before the scene was told (W2, W17), so on a turn with either, or with a fight, a
  chase or talks running, nobody comes.
"""

from collections.abc import Iterable

from engine import bonds
from engine.naming import named_in
from engine.resolve.power import helpless_state
from engine.state.cast import Character, CharacterStatus
from engine.state.world import WorldState
from engine.world.geography import scene_ids, together, ways_from
from engine.world.norms import Nature, deed_nature
from engine.world.returns import errands_of, left, trip_of
from engine.world.scheduling import World
from engine.world.tuning import VISIT_STAY_S, WALK_IN_MAX_S, WALK_IN_S


def within_reach(state: WorldState, turn: int, told: str, meets: Iterable[str] = ()) -> list[str]:
    """Whom a narrated scene may have walk in from where the record has them, by id. `state`
    is the world the steps left, `turn` the turn being played, `told` the scene's words and
    `meets` whom its update has meet the player character."""
    if state.scene.encounter is not None or _walked_in_on(state, turn):
        return []
    ways = ways_from(state, state.player.location_id or state.scene.place_id)
    wronged = _wronged(state)
    near = [
        character.id
        for character in state.npcs()
        if _near(state, character, ways) and character.id not in wronged and _free(state, character)
    ]
    if not near:
        return []
    # A word of a name that someone in the scene shares names nobody new: "Zhao" is the Zhao
    # who is there.
    told_of = {*named_in(state, [told], [*scene_ids(state), *near], anywhere=True), *meets}
    return [character_id for character_id in near if character_id in told_of]


def _near(state: WorldState, character: Character, ways: dict[str, int]) -> bool:
    """Whether the map has someone within a day's way of the scene, and the player character
    wasn't with them too lately for them to have made it."""
    way_s = ways.get(character.location_id or "")
    if way_s is None or way_s > WALK_IN_MAX_S:
        return False
    return character.seen_s is None or way_s <= WALK_IN_S + state.world_s - character.seen_s


def _free(state: WorldState, character: Character) -> bool:
    """Whether nothing holds someone where they are: they live and aren't missing, can walk,
    and are on no errand and no round trip of the world's making."""
    if not character.alive or character.status is not CharacterStatus.ALIVE:
        return False
    if helpless_state(character) is not None:
        return False
    return not errands_of(state, character.id) and trip_of(state, character.id) is None


def _wronged(state: WorldState) -> set[str]:
    """Whom a romance that isn't over wrongs, between two people who are in the scene or
    where it plays (W17): its people, and whoever the record has at the place, whom the scene
    may bring in as it likes."""
    spot = state.player.location_id or state.scene.place_id
    here = set(scene_ids(state))
    if spot in state.places:
        here |= {c.id for c in state.npcs() if together(state, c.location_id, spot)}
    return {
        who
        for bond in state.bonds.values()
        if bond.stage.live and bond.a_id in here and bond.b_id in here
        for who in bonds.wronged(state, bond.a_id, bond.b_id)
    }


def _walked_in_on(state: WorldState, turn: int) -> bool:
    """Whether the turn put on record a harm done or a move in a romance (W2, W17): who saw
    it is settled, and nobody arrives in time to have seen it."""
    return any(
        deed.turn == turn
        and deed.timeline_id == state.timeline_id
        and deed_nature(state, deed) in (Nature.HARM, Nature.ROMANCE)
        for deed in state.deeds.values()
    )


def settle(w: World, came: list[tuple[str, str]]) -> None:
    """Whoever walked into the scene (`engine.apply.Applied.came`, each with the place the
    record had them at) is on a round trip from there: they stay a while and go back, once
    the scene no longer has them (`returns.on_return`)."""
    for character_id, from_id in came:
        who = w.state.characters.get(character_id)
        if who is not None and who.alive:
            left(w, who, from_id, VISIT_STAY_S)

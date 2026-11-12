"""Word needs someone to carry it (W2, W3, W11, W13).

Those who saw a deed know of it at once and feel about it (`deeds.react`). Everyone else learns
of it through one of them, so what the world makes of a deed depends on what becomes of its
witnesses, and the player can change that: a witness who is killed, bound, won over or cowed
tells nobody.

- **A report** (W11). A witness with someone to tell (the faction that holds the place, those
  who keep the law there, their own when it is serious) sets off after `FLEE_S`, and the faction
  learns when they get there (W10). From the moment they set off they are gone from the player
  character's scene (`settle`), and until then they are in it and it shows them going
  (`runners`, `keep`): code decides who runs, whatever a scene's end listed. The report
  lands only if they can still bring it when it is due: alive, able to act, still willing, and
  not in a fight or a chase with the player character. If they can't, another witness who can
  takes it up from then, and where one who would is only kept from it, it waits for them. What
  was done before a crowd is reported whatever becomes of the witness on record: someone else of
  the crowd goes.
- **Talk** (W2). Word of a witnessed deed gets out once people have had their time to talk
  (`CHATTER_S`) and a witness is free to: alive, able, willing, and no longer with the player
  character who did it. Only then does the rumor start, among the people of the place, the
  region's opinion of the player move (W3), word set out to the victims' kin and factions (W4,
  W5) and the place remember it (W8). A public deed is out at once: nobody stops a crowd.
- **Neither** (W13). While a witness who would talk lives, the world asks again, at longer and
  longer intervals and whenever a scene ends without them (`settle`), so a prisoner set free or
  a companion who walks away can still tell. Once nobody who would talk is able to, because
  they are dead, bound or keeping quiet, the deed is kept among those who saw it, and the world
  can still find it from what it left behind, as it finds a secret one.

All of it runs on in-world time, and nothing is counted in turns (W10).
"""

from collections.abc import Collection
from dataclasses import dataclass

from engine.encounters import still_in_it
from engine.resolve.power import helpless_state
from engine.state.cast import Character
from engine.state.records import Deed, EventStatus, PendingEvent, TraceKind, Visibility
from engine.state.world import WorldState, natural_key
from engine.world.aftermath import on_attributed
from engine.world.answers import law_at
from engine.world.discovery import body_trace, schedule_look, ties_trace
from engine.world.geography import (
    ancestors,
    characters_at,
    faction_seat,
    is_within,
    region_of,
    together,
    travel_s,
)
from engine.world.knowledge import faction_learns, protects, region_learns, would_talk
from engine.world.norms import Nature, deed_nature, is_beast, is_crime
from engine.world.rumors import start_rumor
from engine.world.scheduling import Kind, World, by_id, cancel, pending, schedule
from engine.world.telling import account
from engine.world.tuning import (
    CALL_S,
    CHATTER_S,
    FLEE_S,
    RUMOR_HOPS,
    RUMOR_MIN_SEVERITY,
    SILENT_FEAR,
    UNKNOWN_TRIP_S,
)

# --- Who can carry word -------------------------------------------------------------------------


def able(character: Character | None) -> bool:
    """Alive and able to act: not dead, bound, knocked out or dying."""
    return character is not None and character.alive and helpless_state(character) is None


def _engaged(state: WorldState, character_id: str) -> bool:
    """In a fight, a chase or talks with the player character that they are still in: whether
    they get away is the encounter's to settle."""
    encounter = state.scene.encounter
    return (
        encounter is not None
        and character_id in encounter.opponent_ids
        and still_in_it(state, character_id)
    )


def would_report(state: WorldState, witness: Character, faction_id: str, deed: Deed) -> bool:
    """Whether a witness tells this faction (W11): not if they are devoted to the doer, too
    afraid of them (unless it is their own faction), or of a faction at odds with it, such as a
    crime family's people with the police. The player's character never reports by itself, and
    a beast tells nobody but its own pack (G24)."""
    if witness.id == state.player_id or not witness.alive:
        return False
    if is_beast(state, witness.id) and not witness.member_of(faction_id):
        return False
    if protects(state, witness, deed):
        return False
    if witness.member_of(faction_id):
        return True
    toward = witness.sheet.disposition.attitudes.get(deed.actor_id)
    if toward is not None and toward.fear >= SILENT_FEAR:
        return False
    for membership in witness.memberships:
        own = state.factions.get(membership.faction_id)
        if own is not None and own.relations.get(faction_id, 0) <= -30:
            return False
    return True


def carries(state: WorldState, witness: Character | None, faction_id: str, deed: Deed) -> bool:
    """Whether a witness can bring a faction word of a deed now: able to act, still willing, and
    not held in a fight or a chase with the player character."""
    return (
        witness is not None
        and able(witness)
        and would_report(state, witness, faction_id, deed)
        and not _engaged(state, witness.id)
    )


def tellers(state: WorldState, deed: Deed) -> tuple[list[str], list[str]]:
    """The witnesses free to talk of a deed, and those who would but are kept from it: bound or
    knocked out, or still with the player character who did it, in their scene or their fight."""
    free: list[str] = []
    kept: list[str] = []
    mine = deed.actor_id == state.player_id
    for witness_id in sorted(deed.witness_ids, key=natural_key):
        witness = state.characters.get(witness_id)
        if witness is None or not would_talk(state, witness, deed):
            continue
        with_doer = mine and (witness_id in state.scene.present_ids or _engaged(state, witness_id))
        (free if able(witness) and not with_doer else kept).append(witness_id)
    return free, kept


# --- Reports (W11) ------------------------------------------------------------------------------


def _report_targets(state: WorldState, deed: Deed) -> list[str]:
    """Factions a witness would tell (W11): whoever holds the place, those who keep the law
    there against a crime, and the witnesses' own factions when it is serious. Nobody reports a
    hunt too small to be news (G24)."""
    targets: list[str] = []
    if deed.agreed:
        return targets  # W1: what both sides agreed to is nobody's to report
    if deed_nature(state, deed) is Nature.HUNT and deed.severity < RUMOR_MIN_SEVERITY:
        return targets
    for place_id in ancestors(state, deed.place_id):
        holder = state.places[place_id].controller_id
        if holder in state.factions:
            targets.append(holder)
            break
    if is_crime(state, deed):
        targets.extend(f for f in sorted(state.factions) if law_at(state, f, deed.place_id))
    if deed.severity >= 2:
        for witness_id in deed.witness_ids:
            witness = state.characters.get(witness_id)
            if witness is not None:
                targets.extend(m.faction_id for m in witness.memberships)
    return [f for f in dict.fromkeys(targets) if f in state.factions]


def schedule_reports(w: World, deed: Deed) -> None:
    """Each faction to tell gets one report (`_send`), unless the doer leads it."""
    state = w.state
    for faction_id in _report_targets(state, deed):
        if deed.actor_id not in state.factions[faction_id].leader_ids:
            _send(w, deed, faction_id)


def _send(w: World, deed: Deed, faction_id: str) -> None:
    """One report to a faction, from the witness who can bring it soonest: at once if the
    faction is right there, after a call where the world has phones, else after the witness has
    got there on foot or by whatever people use, and about an hour where the map doesn't say
    where the faction is (W10, G6). Whoever has to get away first sets off after `FLEE_S`
    (`sets_off_s`), once, whoever they go on to tell. When everyone who would tell is kept from
    it, bound or still in a fight with the player character, the report waits for them
    (`waits`) and is asked for again later."""
    state = w.state
    faction = state.factions[faction_id]
    instant = state.bible.travel.instant_messages
    seat = faction_seat(state, faction)
    trip = travel_s(state, deed.place_id, seat)
    struck = {*deed.victim_ids, *deed.target_ids}
    best: tuple[bool, int, str, bool, int | None] | None = None
    kept: str | None = None
    for witness_id in sorted(deed.witness_ids, key=natural_key):
        witness = state.characters.get(witness_id)
        if witness is None or not would_report(state, witness, faction_id, deed):
            continue
        if not carries(state, witness, faction_id, deed):
            kept = kept or witness_id
            continue
        labels = ("report", deed.id, faction_id, witness_id)
        flee: int | None = None
        if trip == 0:
            delay, moves = w.between(CALL_S, *labels), False
        elif instant:
            flee = w.between(FLEE_S, "flee", deed.id, witness_id)
            delay, moves = flee + w.between(CALL_S, *labels), False
        else:
            flee = w.between(FLEE_S, "flee", deed.id, witness_id)
            way = UNKNOWN_TRIP_S if trip is None else trip
            delay, moves = flee + way, trip is not None
        # Whoever it fell on has the doer to deal with: someone who only looked on is away first.
        if best is None or (witness_id in struck, delay) < best[:2]:
            best = (witness_id in struck, delay, witness_id, moves, flee)
    payload: dict = {"deed_id": deed.id, "faction_id": faction_id}
    if best is None:
        if kept is None:
            return
        # Nothing of this is something the player character could notice, so they are no
        # subject of it (C6).
        schedule(
            w,
            Kind.REPORT,
            w.at_s + max(FLEE_S[1], w.at_s - deed.world_s),
            title=f"{state.characters[kept].name} may yet tell {faction.name}",
            subject_ids=[kept, faction_id],
            payload=payload | {"witness_id": kept, "moves": False, "waits": True},
        )
        return
    _, delay, witness_id, moves, flee = best
    payload |= {"witness_id": witness_id, "moves": moves}
    if flee is not None:
        payload["sets_off_s"] = w.at_s + flee
    schedule(
        w,
        Kind.REPORT,
        w.at_s + delay,
        title=f"{state.characters[witness_id].name} tells {faction.name}",
        subject_ids=[witness_id, faction_id, deed.actor_id],
        place_id=seat if moves else None,
        payload=payload,
    )


def on_report(w: World, event: PendingEvent) -> None:
    """A witness reaches a faction with what they saw (W11), if they can still bring it: they
    have left the player character's scene and, where they went there, are there now. A report
    of what was done before a crowd arrives whatever became of them. Otherwise it comes to
    nothing, and another witness who can takes it up, or it waits for one who is kept from it
    (`_send`)."""
    state = w.state
    deed = state.deeds.get(str(event.payload.get("deed_id")))
    faction_id = str(event.payload.get("faction_id"))
    witness = state.characters.get(str(event.payload.get("witness_id")))
    if deed is None or faction_id not in state.factions:
        return
    brings = not event.payload.get("waits") and carries(state, witness, faction_id, deed)
    if brings and witness is not None:
        moves = bool(event.payload.get("moves") and event.place_id)
        if "sets_off_s" in event.payload or moves:
            # They got away to bring it. Where the faction is right there, nobody had to leave.
            if _in_scene(state, deed, witness.id, w.ctx.turn):
                _seen_going(deed, witness.id, faction_id)
            _out_of_scene(state, [witness.id])
        if moves:
            witness.location_id = event.place_id
    if brings or (deed.visibility is Visibility.PUBLIC and not event.payload.get("waits")):
        faction_learns(w, faction_id, deed)
        return
    cancel(w, event)
    if faction_id not in deed.known_by_factions:
        _send(w, deed, faction_id)


# --- Who is leaving the scene (W11) -------------------------------------------------------------


@dataclass(frozen=True)
class Runner:
    """Someone in the player character's scene who is off to tell a faction what they saw."""

    witness_id: str
    faction_id: str
    deed_id: str
    sets_off_s: int


def runners(
    state: WorldState, *, turn: int | None = None, scene: Collection[str] = ()
) -> list[Runner]:
    """W11. Who is off to tell a faction what they saw, where the player character can see them
    go, each with the report they set off on first. The scene shows them going, and the player
    has until they set off to stop them. Whoever can't bring it any more (dead, bound, won over,
    cowed, in a fight with the player character) is not going anywhere.

    Between scenes they are those the scene's record lists, and whoever saw a deed of the scene
    just told, done where it is, and hasn't set off yet: still within reach, whatever its end
    listed. With `turn`, for the scene that tells that turn, they are those the record lists or
    listed when the turn began (`scene`), and whoever saw a deed of that turn done where the
    scene is, since no scene has listed them yet. Those of them who have already told are
    among them: the scene shows them gone."""
    here = state.scene.place_id or state.player.location_id
    found: dict[str, Runner] = {}
    for event in by_id(state.pending_events.values()):
        sets_off = event.payload.get("sets_off_s")
        if event.kind != Kind.REPORT or event.timeline_id != state.timeline_id or sets_off is None:
            continue
        witness_id = str(event.payload.get("witness_id"))
        faction_id = str(event.payload.get("faction_id"))
        deed = state.deeds.get(str(event.payload.get("deed_id")))
        if deed is None or faction_id not in state.factions or witness_id not in state.characters:
            continue
        fresh = deed.place_id == here and deed.turn == (state.turn if turn is None else turn)
        if turn is None:
            shown = witness_id in state.scene.present_ids or (fresh and sets_off > state.world_s)
        else:
            shown = witness_id in state.scene.present_ids or witness_id in scene or fresh
        if not shown:
            continue
        if event.status is EventStatus.PENDING:
            if not carries(state, state.characters[witness_id], faction_id, deed):
                continue
        elif turn is None or event.status is not EventStatus.APPLIED or event.applied_turn != turn:
            continue
        runner = Runner(witness_id, faction_id, deed.id, int(sets_off))
        first = found.get(witness_id)
        if first is None or runner.sets_off_s < first.sets_off_s:
            found[witness_id] = runner
    return sorted(found.values(), key=lambda r: (r.sets_off_s, natural_key(r.witness_id)))


def leave(state: WorldState) -> list[str]:
    """Whoever has set off by now to tell what they saw is out of the player character's scene,
    whatever its record lists: code decides who runs (W11). Asked wherever it matters who is in
    the scene: when a deed is recorded, when the world asks whether word is out, and when a
    scene ends. The deed keeps whom the character saw go, and to whom (`Deed.went_to_tell`): it
    is theirs to remember, and whether the runner gets there is nothing they know (C6). Returns
    who left, in order."""
    left = [r for r in runners(state) if r.sets_off_s <= state.world_s]
    for runner in left:
        _seen_going(state.deeds[runner.deed_id], runner.witness_id, runner.faction_id)
    gone = [r.witness_id for r in left]
    _out_of_scene(state, gone)
    return gone


def held(state: WorldState) -> list[Runner]:
    """W11. Who would be off to tell a faction what they saw and is kept from it by a fight, a
    chase or talks with the player character that they are still in: they are going nowhere
    while it lasts, and the scene shows them still there. Each with the report they would set
    off on first."""
    found: dict[str, Runner] = {}
    for event in pending(state, Kind.REPORT):
        runner = _would_run(state, event)
        if runner is None or not _engaged(state, runner.witness_id):
            continue
        first = found.get(runner.witness_id)
        if first is None or runner.sets_off_s < first.sets_off_s:
            found[runner.witness_id] = runner
    return sorted(found.values(), key=lambda r: (r.sets_off_s, natural_key(r.witness_id)))


def _would_run(state: WorldState, event: PendingEvent) -> Runner | None:
    """The runner a pending report has: a witness the player character noticed who set off, or
    is to, and who would still bring it, alive, able and willing."""
    sets_off = event.payload.get("sets_off_s")
    witness_id = str(event.payload.get("witness_id"))
    faction_id = str(event.payload.get("faction_id"))
    deed = state.deeds.get(str(event.payload.get("deed_id")))
    witness = state.characters.get(witness_id)
    if sets_off is None or deed is None or witness is None or faction_id not in state.factions:
        return None
    if witness_id in deed.unnoticed_witness_ids:
        return None  # a watcher nobody noticed is nobody the scene keeps or sees go
    if not able(witness) or not would_report(state, witness, faction_id, deed):
        return None
    return Runner(witness_id, faction_id, deed.id, int(sets_off))


def keep(state: WorldState, played: WorldState, turn: int) -> list[str]:
    """Once a scene has ended, before `settle`. Who runs is code's to decide (W11), so a scene's
    end takes nobody out of the scene who has word to bring and hasn't gone, and nobody leaves
    it unseen. `played` is the state the turn's steps left, before the narrator's update: its
    scene had those its record listed, those in its fight, and whoever saw a deed of that turn
    done where it is. Of them, while the scene is still where it was, or at a spot inside it:

    - whoever is yet to set off and still there, or is held in a fight with the player
      character, is in the scene whatever its end listed: within reach, and the next scene
      shows them;
    - whoever its end left out and has set off by now, or was sent somewhere else by it, went
      in front of the player character (`Deed.went_to_tell`, C6).

    A scene that ended somewhere else, even out in the place around the one it was in, left
    them behind, and what they did then is nothing the player character saw. Returns who was
    put back in the scene, in order."""
    here = state.scene.place_id or state.player.location_id
    before = played.scene.place_id or played.player.location_id
    if before is not None and not is_within(state, here, before):
        return []
    kept: list[str] = []
    for event in pending(state, Kind.REPORT):
        runner = _would_run(state, event)
        if runner is None:
            continue
        witness_id = runner.witness_id
        deed = state.deeds[runner.deed_id]
        if not (_in_scene(played, deed, witness_id, turn) or _engaged(played, witness_id)):
            continue  # they weren't in the scene as it played
        listed = witness_id in state.scene.present_ids
        there = together(state, state.characters[witness_id].location_id, here)
        if _engaged(state, witness_id) or (runner.sets_off_s > state.world_s and there):
            if not listed:
                state.scene.present_ids.append(witness_id)
                kept.append(witness_id)
        elif not listed:
            _seen_going(deed, witness_id, runner.faction_id)
    return list(dict.fromkeys(kept))


def unsettled(state: WorldState) -> bool:
    """Whether `settle` could have anything to do: someone is setting off, or waiting to."""
    return any(
        "sets_off_s" in e.payload or e.payload.get("waits") for e in pending(state, Kind.REPORT)
    ) or any(e.payload.get("again") for e in pending(state, Kind.WORD))


def settle(state: WorldState) -> list[str]:
    """Once a scene has ended, after `keep`. Whoever has set off by now to tell what they saw is
    out of it, whatever its end listed: code decides who runs (W11). And where it let go of a
    witness who was kept from telling, the world asks again now instead of at its next time, so
    word gets out when they get away and not hours later (W2). Returns who left, in order."""
    gone = leave(state)
    for event in pending(state, Kind.WORD):
        deed = state.deeds.get(str(event.payload.get("deed_id")))
        if event.payload.get("again") and deed is not None and tellers(state, deed)[0]:
            event.due_s = min(event.due_s, state.world_s)
    for event in pending(state, Kind.REPORT):
        deed = state.deeds.get(str(event.payload.get("deed_id")))
        witness = state.characters.get(str(event.payload.get("witness_id")))
        faction_id = str(event.payload.get("faction_id"))
        if event.payload.get("waits") and deed is not None and faction_id in state.factions:
            if carries(state, witness, faction_id, deed):
                event.due_s = min(event.due_s, state.world_s)
    return gone


def _in_scene(state: WorldState, deed: Deed, witness_id: str, turn: int) -> bool:
    """Whether the player character's scene has this witness of a deed in it: its record lists
    them, or they saw a deed of this turn done where the scene is, which no scene has listed
    yet."""
    here = state.scene.place_id or state.player.location_id
    return witness_id in state.scene.present_ids or (deed.turn == turn and deed.place_id == here)


def _seen_going(deed: Deed, witness_id: str, faction_id: str) -> None:
    """C6: the player character saw this witness set off to tell a faction, the first one they
    went to. Not one they never noticed, such as a hidden watcher."""
    if witness_id not in deed.unnoticed_witness_ids:
        deed.went_to_tell.setdefault(witness_id, faction_id)


def _out_of_scene(state: WorldState, ids: list[str]) -> None:
    if any(i in state.scene.present_ids for i in ids):
        state.scene.present_ids = [i for i in state.scene.present_ids if i not in ids]


# --- Talk (W2) ----------------------------------------------------------------------------------


def schedule_word(w: World, deed: Deed) -> None:
    """Once people have had their time to talk, the world asks whether a witness is free to
    (`on_word`). Nothing the player character could notice, so they are no subject of it."""
    _ask(w, deed, w.between(CHATTER_S, "word", deed.id), again=False)


def _ask(w: World, deed: Deed, delay: int, *, again: bool) -> None:
    schedule(
        w,
        Kind.WORD,
        w.at_s + delay,
        title="Word of a deed may get out",
        payload={"deed_id": deed.id, "again": again},
    )


def on_word(w: World, event: PendingEvent) -> None:
    """Whether word of a witnessed deed gets out now (W2): it does when a witness is free to
    talk. While someone who would is kept from it, the world asks again, each time after as
    long again as has passed since the deed. Once nobody who would talk is able to, it stays
    among those who saw it, where the world can still find it from what it left (W13)."""
    state = w.state
    deed = state.deeds.get(str(event.payload.get("deed_id")))
    if deed is None or deed.word_out_s is not None:
        return
    leave(state)
    free, kept = tellers(state, deed)
    if free:
        word_out(w, deed)
        return
    if not any(able(state.characters.get(i)) for i in kept):
        _hush(w, deed)
    if kept:
        _ask(w, deed, max(CHATTER_S[0], w.at_s - deed.world_s), again=True)


def word_out(w: World, deed: Deed) -> None:
    """Word of a deed gets out beyond those who saw it (W2): the people of the place hear it and
    it travels on as a rumor when it is news, the region's opinion of the player moves (W3),
    word sets out to the victims' kin and factions (W4, W5), and a place that saw something
    terrible remembers it (W8)."""
    state = w.state
    deed.word_out_s = w.at_s
    public = deed.visibility is Visibility.PUBLIC
    # Word sent to those close to the victims sets off first, so it is ahead of the talk that
    # travels the same road, and they hear it from someone who knows.
    on_attributed(w, deed)
    if deed.severity >= RUMOR_MIN_SEVERITY or public:
        there = [c.id for c in characters_at(state, deed.place_id) if c.id != deed.actor_id]
        start_rumor(
            w,
            text=account(state, deed),
            is_true=True,
            place_id=deed.place_id,
            hops=RUMOR_HOPS[deed.severity] + (1 if public else 0),
            deed=deed,
            about_ids=[deed.actor_id, *deed.victim_ids, *deed.target_ids],
            accuracy=100 if public else 90,
            heard_by=list(dict.fromkeys([*deed.witness_ids, *there])),
            # A witnessed deed's word is out only once people have had their time to talk.
            chatter=public,
        )
    region_learns(w, region_of(state, deed.place_id), deed)
    _shaken(w, deed)


def _hush(w: World, deed: Deed) -> None:
    """W13. Nobody is free to tell of it, so it is the world's to find from what it left behind:
    the dead where they fell and the people who will miss them, looked for as a secret deed's
    traces are. Once per deed."""
    state = w.state
    looked = any(
        e.kind == Kind.DISCOVERY and e.payload.get("deed_id") == deed.id
        for e in state.pending_events.values()
    )
    if deed.discovered or looked:
        return  # the world is already looking, or has looked its fill
    body = body_trace(state, deed)
    if body is not None:
        deed.traces.append(body)
    if not any(t.kind is TraceKind.TIES for t in deed.traces):
        ties = ties_trace(state, deed)
        if ties is not None:
            deed.traces.append(ties)
    crowd = any(
        c.id != deed.actor_id and c.id not in deed.victim_ids
        for c in characters_at(state, deed.place_id)
    )
    schedule_look(w, deed, crowd=crowd)


def _shaken(w: World, deed: Deed) -> None:
    """W8: a place where something terrible was done, and is known to have been, remembers it
    in its mood."""
    state = w.state
    if (
        deed.severity >= 4
        and deed_nature(state, deed) is Nature.HARM
        and not deed.agreed  # W1: a death both accepted leaves no place shaken
        and deed.place_id in state.places
    ):
        actor = state.characters.get(deed.actor_id)
        who = actor.name if actor else "someone"
        state.places[deed.place_id].mood = f"shaken; people remember what {who} did here"

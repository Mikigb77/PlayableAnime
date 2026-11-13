"""A step that is a move in a romance (W17).

The interpret step proposes the move (`IntentStep.romance`), and the step's own words count
beside it: a kiss, a flirt or a night together is an advance whatever the reading left out
(`engine.limits.intimacy`). Code decides what the move does, from the bond on record and from
the other person's own heart (`engine.bonds`), logic first (A2):

- An **advance** on a partner whose heart is in it is certain, so nobody throws to kiss their
  own wife. Beyond a kiss it is certain with a partner whose heart is in it or with anyone drawn
  enough, and ruled out with someone barely drawn who is no partner. Anything else is thrown
  like any step of words, and someone drawn to the character is easier to move.
- Asking to be a couple (**declare**), or to be promised to each other (**propose**, which
  takes a couple), is answered by their heart: yes with nothing thrown when it is surely there,
  no when it surely isn't, and thrown for in between.
- A **wedding** takes two who are promised. **Parting** is always the character's to do.
- Someone whose heart is closed (family, someone who wants nothing to do with the character,
  someone too afraid of them, someone who ended it with them not long ago) is moved by nothing
  of the kind.

An advance that was answered moves their heart, at their own pace, and the bond comes to the
stage the story has earned. The romance opens at interest with the first move made, whatever
came of it, save toward close family, where nothing of the kind is ever on record. Courting
that an event cut short keeps what the time it ran earned (`cut_short`, E7). Only the player
character's own steps are read here, toward someone on record, and everyone in one is a
recorded adult (F3).

A move that wrongs someone is a deed (`deed`, W1): whoever is a couple with either of the two
may see it or come to hear of it, and what they make of it is the world's (`engine.world`).

The other has to be there (`_reach`, W10): in the scene, or on record at the place the step
plays, where the scene can bring them in. Toward someone who is elsewhere and not far, the step
goes to them first (`Wooing.goes`), and the way is made whatever they answer. Toward anyone
further off it is ruled out with nothing on record. Parting needs nobody there.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from engine import bonds
from engine.context import Language
from engine.contracts.delta import AttitudeShift, BondChange, CharacterChange, StateDelta
from engine.contracts.intent import IntentStep, OutcomeClass, RomanceMove
from engine.contracts.resolution import ProposedDeed, StepResolution, Trip, WooingSoFar
from engine.limits import Intimacy, intimacy, is_adult, partners
from engine.resolve.checks import Settled
from engine.state.cast import Character
from engine.state.records import BondStage, StepResult
from engine.state.world import WorldState
from engine.world import journeys
from engine.world.geography import scene_ids, together
from engine.world.norms import COURT, LIE_WITH, WED

# W10. How far a move in a romance goes to find someone who is elsewhere: an errand of under an
# hour, or a way that takes no more than this part of the time the step gives it, so a week of
# courting goes to someone a day's ride off and a kiss doesn't.
NEAR_S = journeys.NEARBY_S
REACH = 4

_STANDS = {
    BondStage.TOGETHER: "are together",
    BondStage.PROMISED: "are promised to each other",
    BondStage.MARRIED: "are married",
}
_CLOSED = {
    bonds.Closed.FAMILY: "{them} is family, and nothing in them answers this.",
    bonds.Closed.AVERSE: "{them} wants nothing of the kind from you.",
    bonds.Closed.AFRAID: "{them} is too afraid of you for anything to be freely given.",
    bonds.Closed.ENDED: "{them} ended it with you, and it is too soon for anything to mend it.",
}


@dataclass(frozen=True)
class Heart:
    """Where a romance stands as a step starts: the bond's stage, if a live one is on record,
    how drawn the other is, and when their heart last moved. The state's own record, or what
    the earlier steps of this plan made of it."""

    stage: BondStage | None = None
    attraction: int = 0
    moved_s: int | None = None


@dataclass(frozen=True)
class Wooing:
    """A step read as a move in a romance, with what logic alone settles of it (`settled`,
    None where the outcome is open and the step is thrown for)."""

    move: RomanceMove
    other: Character
    intimate: bool  # the step goes beyond a kiss
    heart: Heart
    step: IntentStep
    settled: Settled | None = None
    family: bool = False  # the two are close family, so nothing of this is ever on record
    away: bool = False  # they aren't where the step plays, so nothing of it reached them
    goes: Trip | None = None  # the way to them, when the step goes to them first (W10)


def heart_of(state: WorldState, actor: Character, other: Character) -> Heart:
    bond = bonds.live(state, actor.id, other.id)
    attitude = other.attitude_toward(actor.id)
    return Heart(
        stage=bond.stage if bond is not None else None,
        attraction=attitude.attraction,
        moved_s=attitude.heart_moved_s,
    )


def read(
    state: WorldState,
    actor: Character,
    step: IntentStep,
    language: Language,
    hearts: dict[str, Heart],
    place_id: str | None = None,
    trip: Trip | None = None,
    *,
    held: bool = False,
) -> Wooing | None:
    """The step as a move in a romance, or None when it is none: a step that aims harm, one
    whose words are sexual violence, one with nobody on record to be with, and anything
    between people who aren't both recorded adults (F3). `hearts` is what this plan's earlier
    steps made of the romances they moved and `place_id` where they took the actor. `trip` is
    where the step itself goes, and `held` whether the actor can't walk off to anyone now."""
    if actor.id != state.player_id or step.aim.harmful:
        return None
    words = intimacy(step, language)
    if words is Intimacy.SEXUAL_VIOLENCE:
        return None
    move = step.romance or (RomanceMove.ADVANCE if words is not None else None)
    if move is None:
        return None
    other = _with(state, actor, step)
    if other is None or not (is_adult(actor) and is_adult(other)):
        return None
    heart = hearts.get(other.id) or heart_of(state, actor, other)
    away, goes = False, None
    if move is not RomanceMove.PART:
        away, goes = _reach(state, actor, other, step, place_id, trip, held)
    wooing = Wooing(
        move=move,
        other=other,
        intimate=words is Intimacy.SEXUAL,
        heart=heart,
        step=step.model_copy(update={"romance": move}),
        away=away,
        goes=goes,
    )
    family = bonds.kin(state.characters, actor.id, other.id)
    return replace(wooing, settled=_ruling(state, actor, wooing), family=family)


def _reach(
    state: WorldState,
    actor: Character,
    other: Character,
    step: IntentStep,
    place_id: str | None,
    trip: Trip | None,
    held: bool,
) -> tuple[bool, Trip | None]:
    """W10. Whether the other is out of the step's reach, and the trip that takes the actor to
    them when the step has to go to them first.

    They are within reach when the scene has them, or the record has them at the place the
    step plays: where its own trip goes, else where the plan has brought the actor. There the
    scene can bring them in (W4). Someone the record doesn't place is the scene's to place.
    Anyone else is elsewhere, and the step goes to them when the actor can find the way
    (`journeys.to_someone`) and it is short: an errand of under an hour, or no more than a
    part of the time the step takes (`REACH`). It doesn't when the step already goes somewhere
    else, or while the actor can't walk off (`held`): then nothing of it reaches them."""
    if other.id in scene_ids(state):
        return False, None
    spot = place_id or actor.location_id or state.scene.place_id
    if trip is not None:
        spot = trip.to_id
    where = other.location_id
    if spot not in state.places or where not in state.places or together(state, where, spot):
        return False, None
    if trip is not None or held:
        return True, None
    way = journeys.to_someone(state, actor, other, spot)
    if way is None or way.route_s is None:
        return True, None
    if way.route_s > max(NEAR_S, step.proposed_duration_s // REACH):
        return True, None
    return False, way


def _with(state: WorldState, actor: Character, step: IntentStep) -> Character | None:
    """Whom the step is with: the first living person on record it is aimed at or names."""
    for ref in partners(state, step, actor.id):
        other = state.characters.get(ref)
        if other is not None and other.id != actor.id and other.alive:
            return other
    return None


def _yes(reason: str) -> Settled:
    return Settled(OutcomeClass.CERTAIN, StepResult.SUCCESS, reason)


def _no(reason: str) -> Settled:
    return Settled(OutcomeClass.RULED_OUT, StepResult.FAILURE, reason)


def _ruling(state: WorldState, actor: Character, wooing: Wooing) -> Settled | None:
    """What the record alone settles of the move (A2), or None where it is open."""
    them = wooing.other.name
    stage, drawn = wooing.heart.stage, wooing.heart.attraction
    couple = stage is not None and stage.couple
    stands = f"You and {them} {_STANDS[stage]}" if couple else ""
    if wooing.move is RomanceMove.PART:
        if stage is None:
            return _no(f"There is nothing between you and {them} to end.")
        return _yes("Ending it is yours to do.")
    if wooing.away:
        return _no(f"{them} isn't here.")
    closed = bonds.closed_to(state, wooing.other, actor.id)
    if wooing.move is RomanceMove.WED:
        if stage is BondStage.MARRIED:
            return _yes(f"{stands} already.")
        if stage is not BondStage.PROMISED:
            return _no(f"You and {them} aren't promised to each other.")
        if closed is not None:
            return _no(_CLOSED[closed].format(them=them))
        return _yes(f"{stands}: nothing stands in the way.")
    if closed is not None:
        return _no(_CLOSED[closed].format(them=them))
    if wooing.move is RomanceMove.DECLARE:
        if couple:
            return _yes(f"{stands} already.")
        return _answer(them, drawn, bonds.DECLARE_NO, bonds.DECLARE_SURE)
    if wooing.move is RomanceMove.PROPOSE:
        if stage in (BondStage.PROMISED, BondStage.MARRIED):
            return _yes(f"{stands} already.")
        if stage is not BondStage.TOGETHER:
            return _no(f"You and {them} aren't together.")
        return _answer(them, drawn, bonds.PROPOSE_NO, bonds.PROPOSE_SURE)
    # An advance.
    if wooing.intimate:
        if (couple and drawn >= bonds.INTIMATE_PARTNER) or drawn >= bonds.INTIMATE_SURE:
            return _yes(f"{stands}: nothing stands in the way." if couple else _WANTS.format(them))
        if not couple and drawn < bonds.INTIMATE_NO:
            return _no(f"{_possessive(them)} heart isn't there.")
        return None
    if couple and drawn >= bonds.TENDER_SURE:
        return _yes(f"{stands}: nothing stands in the way.")
    return None


_WANTS = "{} wants this too."


def _answer(them: str, drawn: int, no: int, sure: int) -> Settled | None:
    """An ask their heart answers: yes at `sure` or more, no under `no`, open between."""
    if drawn >= sure:
        return _yes(_WANTS.format(them))
    if drawn < no:
        return _no(f"{_possessive(them)} heart isn't there yet.")
    return None


def _possessive(who: str) -> str:
    return f"{who}'" if who.endswith("s") else f"{who}'s"


@dataclass
class _Told:
    """What a move does to a romance, as it is worked out: where the romance stands, what is
    said of it after the step's reason, and the engine's changes."""

    actor: Character
    other: Character
    stage: BondStage | None
    drawn: int
    moved_s: int | None
    said: list[str] = field(default_factory=list)
    moves: list[BondChange] = field(default_factory=list)
    felt: dict[str, int] = field(default_factory=dict)

    def to(self, new: BondStage, how: str) -> None:
        by = self.actor.id
        self.moves.append(BondChange(a_id=by, b_id=self.other.id, stage=new, by_id=by, how=how))
        self.stage = None if new is BondStage.OVER else new

    def done(self) -> tuple[list[str], StateDelta, Heart]:
        changes = StateDelta(bonds=self.moves)
        if self.felt:
            shift = AttitudeShift(toward_id=self.actor.id, **self.felt)
            changes = changes.model_copy(
                update={"characters": [CharacterChange(id=self.other.id, attitudes=[shift])]}
            )
        return self.said, changes, Heart(self.stage, self.drawn, self.moved_s)


def settle(
    actor: Character,
    wooing: Wooing,
    settled: Settled,
    *,
    over_the_top: bool,
    now_s: int,
    lasted_s: int,
) -> tuple[list[str], StateDelta, Heart]:
    """What the move, settled, does to the romance: what follows in words, after the step's
    reason, the engine's changes, and where the romance stands for the rest of the plan. An
    advance that was answered moves the other's heart (`bonds.gain`), and the bond comes to
    the stage this earned. The first move opens the romance, whatever came of it."""
    heart = wooing.heart
    told = _Told(actor, wooing.other, heart.stage, heart.attraction, heart.moved_s)
    if (wooing.family or wooing.away) and wooing.move is not RomanceMove.PART:
        # Nothing of the kind is ever between close family, and nothing reached someone who
        # wasn't there.
        return told.done()
    them, mover = wooing.other.name, actor.name
    happened = settled.outcome_class is not OutcomeClass.RULED_OUT
    won = happened and settled.result is StepResult.SUCCESS
    half = happened and settled.result is StepResult.PARTIAL
    thrown = settled.roll is not None
    ends_s = now_s + max(0, lasted_s)
    if wooing.move is RomanceMove.PART:
        if won and told.stage is not None:
            cost, heart_cost = 0, 0
            if told.stage.couple:
                cost, heart_cost = bonds.PARTED_COUPLE, bonds.PARTED_HEART_COUPLE
            elif told.stage is BondStage.COURTING:
                cost, heart_cost = bonds.PARTED_COURTING, bonds.PARTED_HEART_COURTING
            lost = min(told.drawn, heart_cost)
            told.drawn -= lost
            told.felt = {"affinity": -cost, "trust": -cost, "attraction": -lost}
            told.felt = {k: v for k, v in told.felt.items() if v}
            told.to(BondStage.OVER, f"{mover} ended it.")
            told.said.append(f"It is over between you and {them}")
        return told.done()
    if wooing.move is RomanceMove.WED:
        if won and told.stage is BondStage.PROMISED:
            told.to(BondStage.MARRIED, f"{mover} and {them} were wed.")
            told.said.append(f"You and {them} are married now")
        return told.done()
    if wooing.move is RomanceMove.ADVANCE:
        more = _gain(told, won or half, won, over_the_top, now_s, lasted_s)
        _advance(told, more, won, ends_s)
        return told.done()
    # An ask: to be a couple, or to be promised to each other.
    if told.stage is None:
        told.to(BondStage.INTEREST, f"{mover} made it plain to {them}.")
    if won and wooing.move is RomanceMove.DECLARE:
        if told.stage in (BondStage.INTEREST, BondStage.COURTING):
            told.to(BondStage.TOGETHER, f"{mover} asked, and {them} said yes.")
            told.said.append(f"You and {them} are together now")
    elif won:
        if told.stage is BondStage.TOGETHER:
            told.to(BondStage.PROMISED, f"{mover} asked for a promise, and {them} gave it.")
            told.said.append(f"You and {them} are promised to each other now")
    elif thrown and half:
        told.said.append(f"{them} asks for time")
    elif thrown:
        # Asked too soon, it sets things back.
        lost = min(told.drawn, bonds.TURNED_DOWN)
        told.drawn, told.moved_s = told.drawn - lost, ends_s
        if lost:
            told.felt = {"attraction": -lost}
        told.said.append(f"{them} says no, and it sets things back between you")
    return told.done()


def _gain(
    told: _Told,
    answered: bool,
    whole: bool,
    over_the_top: bool,
    now_s: int,
    lasted_s: int,
    *,
    cut: bool = False,
) -> int:
    """How far an advance moves the other's heart: nothing unless it was answered."""
    if not answered:
        return 0
    more = bonds.gain(
        told.other,
        told.actor.id,
        whole=whole,
        over_the_top=over_the_top,
        now_s=now_s,
        lasted_s=lasted_s,
        moved_s=told.moved_s,
        cut=cut,
    )
    return max(0, min(more, 100 - told.drawn))


def _advance(told: _Told, more: int, won: bool, ends_s: int) -> None:
    """An advance, made: the romance opens with it, their heart moves by `more`, and one that
    came off with their heart far enough along makes it a courtship."""
    them, mover = told.other.name, told.actor.name
    if told.stage is None:
        told.to(BondStage.INTEREST, f"{mover} made it plain to {them}.")
    if more > 0:
        told.drawn, told.moved_s = told.drawn + more, ends_s
        told.felt = {"attraction": more}
        told.said.append(f"{them} is more drawn to you than before")
    if won and told.stage is BondStage.INTEREST and told.drawn >= bonds.COURTING_AT:
        told.to(BondStage.COURTING, f"{them} answered {_possessive(mover)} advances.")
        told.said.append(f"{them} answers it, and the two of you are courting now")


_OUTCOME = {
    StepResult.SUCCESS: "it worked",
    StepResult.PARTIAL: "it partly worked",
    StepResult.FAILURE: "it failed",
}


def deed(
    state: WorldState,
    actor: Character,
    wooing: Wooing,
    settled: Settled,
    now: Heart,
    hearts: dict[str, Heart],
    *,
    in_stopped_time: bool = False,
) -> ProposedDeed | None:
    """The move as a deed (W1), where it wrongs someone: whoever is a couple with either of the
    two (`bonds.wronged`). None where it wrongs nobody. A move that was made counts whatever
    came of it, since the asking was the wrong; a wedding only once the two are wed; ending a
    romance, and anything toward close family, never. How grave it is follows what was done
    and where it took the two (`bonds.gravity`, `now` being where the romance stands after
    it). `hearts` is where this plan's earlier steps left the actor's other romances: a
    partner the actor has just left isn't wronged by what comes after."""
    if wooing.family or wooing.away or wooing.move is RomanceMove.PART:
        return None
    before, after = wooing.heart.stage, now.stage
    wed = wooing.move is RomanceMove.WED
    if wed and not (before is BondStage.PROMISED and after is BondStage.MARRIED):
        return None
    wronged = [
        who
        for who in bonds.wronged(state, actor.id, wooing.other.id)
        if who not in hearts or (hearts[who].stage is not None and hearts[who].stage.couple)
    ]
    if not wronged:
        return None
    answered = settled.outcome_class is not OutcomeClass.RULED_OUT and (
        settled.result is not StepResult.FAILURE
    )
    severity = bonds.gravity(
        asked=wooing.move in (RomanceMove.DECLARE, RomanceMove.PROPOSE),
        intimate=wooing.intimate,
        answered=answered,
        before=before,
        after=after,
    )
    kind = WED if wed else LIE_WITH if wooing.intimate and answered else COURT
    return ProposedDeed(
        kind=kind,
        text=f"{wooing.step.text} ({_OUTCOME[settled.result]})",
        actor_id=None if actor.id == state.player_id else actor.id,
        target_ids=[wooing.other.id],
        wronged_ids=wronged,
        severity=severity,
        in_stopped_time=in_stopped_time,
    )


def so_far(
    wooing: Wooing, settled: Settled, said: list[str], *, over_the_top: bool
) -> WooingSoFar | None:
    """What a step's resolution keeps of an advance that was answered, so that one an event
    cuts short keeps what the time it ran earned (`cut_short`). `said` is what the step's
    reason tells of the romance, as it stands there."""
    happened = settled.outcome_class is not OutcomeClass.RULED_OUT
    if wooing.move is not RomanceMove.ADVANCE or not happened:
        return None
    if settled.result not in (StepResult.SUCCESS, StepResult.PARTIAL):
        return None
    return WooingSoFar(
        other_id=wooing.other.id,
        whole=settled.result is StepResult.SUCCESS,
        over_the_top=over_the_top,
        stage=wooing.heart.stage,
        attraction=wooing.heart.attraction,
        moved_s=wooing.heart.moved_s,
        said=said,
    )


def cut_short(
    state: WorldState, actor_id: str, step: StepResolution, start_s: int, ran_s: int
) -> tuple[str, StateDelta]:
    """An advance that an event cut short (E7): the step's reason and the engine's changes for
    the time it ran. A step an event cuts short didn't happen, and courting someone for weeks
    is no single moment: their heart moved each time it had rested while the courting ran
    (`bonds.gain`), so a fortnight of it stopped on the fourth day keeps four days of it, and
    one stopped before their heart had the time to move once keeps nothing."""
    kept = step.wooing
    assert kept is not None
    reason = step.reason
    for line in kept.said:
        reason = reason.replace(line, "")
    reason = " ".join(reason.split())
    actor, other = state.characters.get(actor_id), state.characters.get(kept.other_id)
    if actor is None or other is None or not other.alive:
        return reason, StateDelta()
    told = _Told(actor, other, kept.stage, kept.attraction, kept.moved_s)
    more = _gain(told, True, kept.whole, kept.over_the_top, start_s, ran_s, cut=True)
    if more <= 0:
        return reason, StateDelta()
    _advance(told, more, kept.whole, start_s + ran_s)
    said, changes, _ = told.done()
    return " ".join([reason, *(sentence(line) for line in said)]).strip(), changes


def sentence(text: str) -> str:
    text = text.strip()
    return text if not text or text.endswith((".", "!", "?")) else f"{text}."

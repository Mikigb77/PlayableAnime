"""Rulings on talent, and bridges (A4, A9).

`engine.talent` reads how fast a character learns each thing. This module makes the two records
it reads, from what the interpret step proposes:

- **The ruling.** The first time a character sets out to learn, train or use something new, the
  engine rules once on how each of their talents stands to it: inside, related or outside. The
  interpret step proposes it with a reason (`IntentStep.talent_cases`), weighing the case the
  player made in that very action; code checks that the talent is theirs, records the ruling on
  the sheet and never flips it. A talent nobody made a case for is outside, and a thing with no
  case stays unruled, at the ordinary pace, until one is made.
- **A bridge.** After a ruling, words alone don't reopen it, but a deed does: work the character
  really does in the story to connect a talent to the thing (`IntentStep.bridge`), such as
  deriving the formula behind a blade's shape. It is a step of its own, thrown with the skill it
  draws on against the reach: a hard task for one side of the thing, a very hard one for its
  heart. One that holds lifts that one thing a step toward the talent's pace, two for the
  heart, and never past the talent it starts from. Each has to rest on something new: ground
  already tried, held or not, doesn't carry a second one.

A talent is never declared in play: only the sheet's own talents can be ruled on or built from.
"""

from dataclasses import dataclass

from engine import levels
from engine import talent as talent_mod
from engine.contracts.delta import CharacterChange, StateDelta
from engine.contracts.intent import Challenge, IntentStep, MeansVerdict, OutcomeClass
from engine.resolve.checks import Drawn, Settled
from engine.resolve.powers import growth
from engine.resolve.words import cap, mentions, name, possessive, stems
from engine.state.cast import Character
from engine.state.records import StepResult
from engine.state.sheet import (
    Talent,
    TalentBridge,
    TalentCover,
    TalentFit,
    TalentRuling,
    TalentStrength,
    Technique,
)
from engine.state.world import WorldState

REASON_LIMIT = 300
# A3. How hard a bridge is: one side of the thing, and its heart.
SIDE = Challenge.HARD
HEART = Challenge.VERY_HARD
SIDE_STEPS, HEART_STEPS = 1, 2

_FIT_WORDS = {
    TalentFit.INSIDE: "inside",
    TalentFit.RELATED: "related to",
    TalentFit.OUTSIDE: "outside",
}


@dataclass(frozen=True)
class Thing:
    """Something a step learns, trains or uses that a talent could cover, by its key in the
    rulings and its name."""

    key: str
    what: str


def things(
    state: WorldState,
    actor: Character,
    step: IntentStep,
    drawn: Drawn,
    learned: list[Technique],
) -> list[Thing]:
    """What the step sets out to learn or uses: what it trains, the techniques of theirs it
    draws on, and the moves it tries for the first time. Each once."""
    found: dict[str, Thing] = {}
    if step.training is not None:
        known = growth.already_known(state, actor, step, learned)
        if known is not None:
            # Practising a technique of theirs is that technique, whatever the step called it.
            key, what = talent_mod.technique_key(known[1].name), known[1].name
        else:
            key = growth.talent_key(state, actor, step)
            what = step.training.what.strip() or key
        found[key] = Thing(key, what)
    used = growth.used_in(actor, drawn.techniques, drawn.moves, learned)
    for named in [*(t.name for t in used), *(m.name for m in drawn.moves)]:
        key = talent_mod.technique_key(named)
        found.setdefault(key, Thing(key, named))
    return list(found.values())


def rule(
    state: WorldState, actor: Character, step: IntentStep, at_stake: list[Thing]
) -> tuple[list[TalentRuling], list[str]]:
    """A4, A9. The rulings this step makes, each with its words for the step's reason: for
    every thing at stake that was never ruled on, how each talent the interpret step made a
    case for stands to it. Only the character's own talents that aren't general can be ruled
    on, each once for a thing."""
    theirs = [t for t in talent_mod.talents_of(actor) if not t.general]
    if not theirs or not step.talent_cases:
        return [], []
    waiting = [t for t in at_stake if actor.sheet.talent_ruling(t.key) is None]
    rulings: list[TalentRuling] = []
    said: list[str] = []
    for thing in waiting:
        cases = [c for c in step.talent_cases if _same(c.what, thing.what)]
        if not cases and len(waiting) == 1:
            # One thing at stake: a case that names nothing else they know is about it.
            cases = [
                c
                for c in step.talent_cases
                if not any(_same(c.what, t.what) for t in at_stake)
                and not _names_another(state, actor, c.what, thing)
            ]
        covers: list[TalentCover] = []
        for case in cases:
            talent = _find(theirs, case.talent_id)
            if talent is None or any(c.talent_id == talent.id for c in covers):
                continue
            reason = " ".join(case.reason.split())[:REASON_LIMIT]
            covers.append(TalentCover(talent_id=talent.id, fit=case.fit, reason=reason))
        if not covers:
            continue
        rulings.append(TalentRuling(key=thing.key, what=thing.what, covers=covers))
        said.append(_ruled(state, actor, thing, covers, theirs))
    return rulings, said


def with_rulings(
    actor: Character, rulings: list[TalentRuling], bridges: list[TalentBridge]
) -> Character:
    """The character as a plan has them so far: their sheet with the rulings and bridges this
    plan made, which the state doesn't hold until the plan is played out."""
    if not rulings and not bridges:
        return actor
    known = {r.key for r in actor.sheet.talent_rulings}
    sheet = actor.sheet.model_copy(
        update={
            "talent_rulings": [
                *actor.sheet.talent_rulings,
                *(r for r in rulings if r.key not in known),
            ],
            "bridges": [*actor.sheet.bridges, *bridges],
        }
    )
    return actor.model_copy(update={"sheet": sheet})


def _ruled(
    state: WorldState,
    actor: Character,
    thing: Thing,
    covers: list[TalentCover],
    theirs: list[Talent],
) -> str:
    """A ruling in the world's words: "Ruled once: Aura blade is related to your talent "Genius
    architect" (shaping aura is structure and geometry). It grows twice as fast." """
    whose = possessive(state, actor.id)
    by_id = {t.id: t for t in theirs}
    parts = []
    for cover in covers:
        talent = by_id[cover.talent_id]
        why = f" ({cover.reason.rstrip('.')})" if cover.reason else ""
        parts.append(f"{_FIT_WORDS[cover.fit]} {_called(whose, talent)}{why}")
    ruled = with_rulings(actor, [TalentRuling(key=thing.key, covers=covers)], [])
    pace = talent_mod.standing(ruled, thing.key).words
    return f"Ruled once: {thing.what} is {' and '.join(parts)}. It grows {pace}."


def _called(whose: str, talent: Talent) -> str:
    """A talent as a reason names it: your talent "The sword", or your weakness."""
    kind = "weakness" if talent.strength is TalentStrength.SLOW else "talent"
    return f'{whose} {kind} "{talent.name}"'


def _same(said: str, what: str) -> bool:
    """Whether a case's words name the thing: the same name, or either said in the other's
    words."""
    if not said.strip():
        return False
    if talent_mod.fold(said) == talent_mod.fold(what):
        return True
    return mentions(said, what) or mentions(what, said)


def _names_another(state: WorldState, actor: Character, said: str, thing: Thing) -> bool:
    """Whether a case's words name some other thing: a technique or a skill of theirs, a thing
    already ruled on, or a ladder of the world. A ruling is kept for good, so a case about
    their swordsmanship is never read as one about the palm strike the step happens to use."""
    known = [
        *((talent_mod.technique_key(t.name), t.name) for t in actor.sheet.techniques),
        *((talent_mod.skill_key(s.name), s.name) for s in actor.sheet.skills),
        *((r.key, r.what) for r in actor.sheet.talent_rulings),
        *((talent_mod.ladder_key(rungs.id), rungs.name) for rungs in state.bible.ladders),
    ]
    return any(key != thing.key and _same(said, what) for key, what in known)


def _find(theirs: list[Talent], ref: str) -> Talent | None:
    """A talent of theirs by its id, or by its name."""
    ref = ref.strip()
    if not ref:
        return None
    found = next((t for t in theirs if t.id == ref), None)
    if found is not None:
        return found
    folded = talent_mod.fold(ref)
    return next((t for t in theirs if talent_mod.fold(t.name) == folded), None)


# --- bridges ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Bridging:
    """A bridge a step sets out to build: the step as it is thrown for, the talent it starts
    from, the thing it reaches, what it rests on and the steps it lifts if it holds."""

    step: IntentStep
    talent: Talent
    thing: Thing
    rests_on: str
    steps: int
    reason: str = ""


def bridge_check(
    state: WorldState, actor: Character, step: IntentStep
) -> tuple[Settled | None, Bridging | None]:
    """A4. What settles a bridge at once, with no throw, or the bridge to throw for. It needs
    a talent of the character's own that isn't a weakness and doesn't already cover everything,
    a thing that talent doesn't fully reach yet, and new ground to rest on. The step is then a
    close call against the reach: a hard task for one side of the thing, a very hard one for
    its heart, or harder where the interpret step judged it so."""
    bridge = step.bridge
    assert bridge is not None
    who = cap(name(state, actor.id))
    whose = possessive(state, actor.id)
    have = "have" if actor.id == state.player_id else "has"
    talent = _find(talent_mod.talents_of(actor), bridge.talent_id)
    if talent is None:
        return _refused(f"{who} {have} no talent like that to build on."), None
    if talent.strength is TalentStrength.SLOW:
        return _refused(
            f"{cap(_called(whose, talent))} is a weakness, and nothing builds on it."
        ), None
    if talent.general:
        return _refused(f"{cap(_called(whose, talent))} already covers everything."), None
    what = bridge.what.strip()
    rests_on = " ".join(bridge.rests_on.split())
    if not what or not rests_on:
        return _refused("A bridge has to reach something and rest on something."), None
    thing = Thing(_key(state, actor, what), what)
    top = talent.strength.steps
    reached = talent_mod.reach(actor.sheet, talent, thing.key)
    if reached >= top:
        return _refused(
            f"{cap(what)} already grows at the full pace of {_called(whose, talent)}."
        ), None
    tried = [b for b in actor.sheet.bridges if (b.key, b.talent_id) == (thing.key, talent.id)]
    again = next((b for b in tried if _same_ground(b.rests_on, rests_on)), None)
    if again is not None:
        return _refused(
            f"{cap(again.rests_on)} was already tried. A bridge has to rest on something new."
        ), None
    wanted = HEART_STEPS if bridge.heart else SIDE_STEPS
    judged = step.facts.challenge
    reach = HEART if bridge.heart else SIDE
    if judged is not None and levels.CHALLENGE_LEVEL[judged] > levels.CHALLENGE_LEVEL[reach]:
        reach = judged
    # The throw is against the reach and nothing else, whatever else the step named.
    facts = step.facts.model_copy(
        update={
            "means": MeansVerdict.CLOSE_CALL,
            "challenge": reach,
            "opposition": f"the reach from {talent.name} to {what}",
            "opposition_ids": [],
            "inner": False,
        }
    )
    return None, Bridging(
        step=step.model_copy(update={"facts": facts}),
        talent=talent,
        thing=thing,
        rests_on=rests_on,
        steps=min(wanted, top - reached),
        reason=" ".join(bridge.reason.split())[:REASON_LIMIT],
    )


def bridge_made(
    state: WorldState, actor: Character, bridging: Bridging, result: StepResult
) -> tuple[str, TalentBridge, StateDelta]:
    """A4. What a bridge that was thrown for leaves: the reason in the world's words, the
    record, and the engine's change. One that held lifts the thing; one that didn't is kept with
    no steps, so the same ground is never tried twice."""
    held = result is StepResult.SUCCESS
    record = TalentBridge(
        key=bridging.thing.key,
        what=bridging.thing.what,
        talent_id=bridging.talent.id,
        rests_on=bridging.rests_on,
        steps=bridging.steps if held else 0,
        reason=bridging.reason,
    )
    whose = possessive(state, actor.id)
    what = bridging.thing.what
    if held:
        after = with_rulings(actor, [], [record])
        pace = talent_mod.standing(after, record.key).words
        words = (
            f"The bridge holds: resting on {bridging.rests_on}, it carries "
            f"{_called(whose, bridging.talent)} further into {what}, which now grows {pace}."
        )
    else:
        words = (
            f"The bridge doesn't hold, and {bridging.rests_on} won't carry a second try: the "
            "next one needs something new."
        )
    change = CharacterChange(id=actor.id, bridges=[record])
    return words, record, StateDelta(characters=[change])


def _key(state: WorldState, actor: Character, what: str) -> str:
    """The thing a bridge reaches, as the rulings name it: a ruling of theirs that names it, a
    technique or a skill of theirs, a ladder of the world, or else a technique by that name."""
    ruled = next((r for r in actor.sheet.talent_rulings if _same(what, r.what)), None)
    if ruled is not None:
        return ruled.key
    technique = next((t for t in actor.sheet.techniques if _same(what, t.name)), None)
    if technique is not None:
        return talent_mod.technique_key(technique.name)
    skill = actor.sheet.skill(what)
    if skill is not None:
        return talent_mod.skill_key(skill.name)
    ladder = next((rung for rung in state.bible.ladders if _same(what, rung.name)), None)
    if ladder is not None:
        return talent_mod.ladder_key(ladder.id)
    return talent_mod.technique_key(what)


def _same_ground(tried: str, new: str) -> bool:
    """Whether a bridge rests on ground already tried: the same words, or one said inside the
    other."""
    a, b = stems(tried), stems(new)
    return bool(a) and bool(b) and (a <= b or b <= a)


def _refused(reason: str) -> Settled:
    return Settled(OutcomeClass.RULED_OUT, StepResult.FAILURE, reason)

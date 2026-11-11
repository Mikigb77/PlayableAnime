"""Builders for the scripted interpretations: what the interpret step would propose for each line
of a script (B5 step 2), mistakes included where a scenario checks that code catches them."""

from __future__ import annotations

from engine.base import DAY, HOUR
from engine.contracts import (
    ActionKind,
    Aim,
    Contact,
    GrowthKind,
    Intent,
    IntentStep,
    MeansVerdict,
    OutcomeClass,
    PowerGrant,
    PowerTheory,
    SheetPart,
    SheetUse,
    StepFacts,
    TheoryAbout,
    Training,
)
from engine.state import HitMode, PowerAxis
from evals.runner import Played


def step(
    text: str, kind: ActionKind = ActionKind.EXCHANGE, duration_s: int = 2, **kw
) -> IntentStep:
    return IntentStep(
        text=text,
        verb=kw.pop("verb", text.split()[0]),
        kind=kind,
        proposed_duration_s=duration_s,
        **kw,
    )


def act(text: str, verb: str, kind: ActionKind, duration_s: int, **intent) -> Intent:
    """A one-step action."""
    return Intent(
        summary=text,
        steps=[IntentStep(text=text, verb=verb, kind=kind, proposed_duration_s=duration_s)],
        **intent,
    )


def plan(*steps: IntentStep, **intent) -> Intent:
    return Intent(summary="; ".join(s.text for s in steps), steps=list(steps), **intent)


def facts(**kw) -> StepFacts:
    return StepFacts(**kw)


def power(ref: str) -> SheetUse:
    return SheetUse(part=SheetPart.POWER, ref=ref)


def item(ref: str) -> SheetUse:
    return SheetUse(part=SheetPart.ITEM, ref=ref)


def technique(ref: str) -> SheetUse:
    return SheetUse(part=SheetPart.TECHNIQUE, ref=ref)


def skill(ref: str) -> SheetUse:
    return SheetUse(part=SheetPart.SKILL, ref=ref)


def trait(ref: str) -> SheetUse:
    return SheetUse(part=SheetPart.TRAIT, ref=ref)


def stop_time() -> IntentStep:
    return step(
        "stop time", ActionKind.INSTANT, 0, proposed_personal_s=1, uses=[power("time-stop")]
    )


def attack(target: str, weapon: str | None = None, *, aim: Aim = Aim.KILL, **kw) -> IntentStep:
    """A straight attack, meant to kill unless `aim` says otherwise."""
    kw.setdefault("facts", facts(opposition_ids=[target], can_respond=True))
    return step(
        kw.pop("text", f"attack {target}"),
        verb=kw.pop("verb", "attack"),
        aim=aim,
        target_ids=[target],
        axis=kw.pop("axis", PowerAxis.MIGHT),
        uses=kw.pop("uses", [item(weapon)] if weapon else []),
        **kw,
    )


def cut_throat(target: str, weapon: str, **kw) -> IntentStep:
    return step(
        f"cut {target}'s throat",
        verb="kill",
        aim=Aim.KILL,
        target_ids=[target],
        uses=[item(weapon)],
        **kw,
    )


# --- stopped time (W10a, A9) -------------------------------------------------------------------


def throw(target_ids: list[str], **kw) -> IntentStep:
    """'I throw a pebble at it' in stopped time, where the interpret step judged that a pebble
    can't hurt it: code follows the power instead."""
    kw.setdefault(
        "facts",
        facts(
            opposition_ids=[t for t in target_ids if t not in ("wall", "plain")],
            can_respond=False,
            why_not="frozen in stopped time",
            means=MeansVerdict.CLEARLY_NOT,
            hindrances=["a pebble just bounces off"],
        ),
    )
    return step(
        kw.pop("text", "throw a pebble"),
        ActionKind.INSTANT,
        1,
        verb="throw",
        aim=kw.pop("aim", Aim.KILL),
        target_ids=target_ids,
        contact=Contact.THROW,
        mass_kg=0.1,
        proposed_personal_s=1,
        **kw,
    )


def army_throw(range_m: float) -> IntentStep:
    return step(
        "throw a pebble at the army",
        ActionKind.INSTANT,
        1,
        verb="throw",
        aim=Aim.KILL,
        target_ids=["army", "plain"],
        contact=Contact.THROW,
        mass_kg=0.1,
        range_m=range_m,
        proposed_personal_s=1,
        facts=facts(opposition_ids=["army"], opposition="the Black Banner army"),
    )


def light_speed(
    claim: str = "A rock thrown in stopped time should hit at the speed of light.", **kw
):
    """The player's theory, or question, that a stopped-time throw hits at the speed of light."""
    return PowerTheory(
        topic="throw_speed",
        claim=claim,
        about=TheoryAbout.HIT_FORCE,
        claims_hit_mode=HitMode.RELATIVE_SPEED,
        **kw,
    )


def train(kind: GrowthKind, what: str, hours: float, **kw) -> IntentStep:
    action = ActionKind.TIME_SKIP if hours > 72 else ActionKind.TASK
    return step(
        f"train {what}",
        action,
        int(hours * HOUR),
        verb="train",
        training=Training(kind=kind, what=what, **kw),
    )


def train_power(grants: PowerGrant, what: str, *, days: int = 60) -> IntentStep:
    """Months of practice letting a stopped stone back into time gradually (A4)."""
    return step(
        f"practise {what} around a rock",
        ActionKind.TIME_SKIP,
        days * DAY,
        verb="train",
        training=Training(
            kind=GrowthKind.POWER,
            what=what,
            power_id="time-stop",
            grants=grants,
            rests_on=["time-stop"],
        ),
    )


# --- a quiet life on the farm (T17) ------------------------------------------------------------


def farming(**intent) -> Intent:
    return act("Work the fields", "farm", ActionKind.WORK, 6 * HOUR, **intent)


def supper(**intent) -> Intent:
    return act("Have supper with Ilse", "eat supper", ActionKind.CONVERSATION, HOUR, **intent)


def fence(**intent) -> Intent:
    return act("Mend the fence", "mend fence", ActionKind.TASK, 3 * HOUR, **intent)


def full_day(**intent) -> Intent:
    """A day's farming and a night's sleep: 24 in-world hours."""
    return plan(
        step("Work the fields all day", ActionKind.WORK, 12 * HOUR, verb="farm"),
        step("Sleep", ActionKind.REST, 12 * HOUR, verb="sleep"),
        **intent,
    )


LIFE = (
    ("I work the fields", farming),
    ("I have supper with Ilse", supper),
    ("I mend the fence", fence),
)


__all__ = [
    "LIFE",
    "MeansVerdict",
    "act",
    "army_throw",
    "attack",
    "cut_throat",
    "facts",
    "farming",
    "fence",
    "full_day",
    "item",
    "light_speed",
    "plan",
    "power",
    "skill",
    "step",
    "stop_time",
    "supper",
    "technique",
    "throw",
    "train",
    "train_power",
    "trait",
]


REASON_CHARS = 90  # of a ruled-out step's reason, in a failed check's detail


def as_read(turns: list[Played]) -> str:
    """How each step of some turns was read and what code made of it, for the detail of a
    failed check: a live run's log is all that can be read of it afterwards (T18). The story
    is the eval's own, so nothing of a player's is shown (T16)."""
    lines = []
    for played in turns:
        if played.result is None:
            why = played.refused
            said = f" ({', '.join(why.categories) or why.code} {why.stage})" if why else ""
            lines.append(f"t{played.turn} refused{said.rstrip()}")
            continue
        read = played.result.intent.steps if played.result.intent is not None else []
        for settled in played.steps:
            said = "unread"
            if settled.index < len(read):
                step_ = read[settled.index]
                told = step_.facts
                terms = told.terms.value if told.terms is not None else "null"
                said = (
                    f"{step_.verb}/{step_.kind.value}/{step_.aim.value} at={step_.target_ids} "
                    f"in_way={told.opposition_ids} terms={terms}"
                    f"{' beyond' if told.breaks_terms else ''}"
                    f"{' unanswered' if told.can_respond is False else ''}"
                )
                if (show := step_.show_strength) is not None:
                    said += f" shows={show.ladder_id}:{show.shown_rung}"  # G20
            how = f"{settled.outcome_class.value}/{settled.result.value}"
            if settled.outcome_class is OutcomeClass.RULED_OUT:
                how += f" ({settled.reason[:REASON_CHARS]})"  # why it was never tried
            bout = settled.bout.terms.value if settled.bout is not None else "none"
            deeds = [d.kind for d in settled.deeds]
            lines.append(
                f"t{played.turn}.{settled.index} {said} -> {how} bout={bout} deeds={deeds}"
            )
    return " | ".join(lines)

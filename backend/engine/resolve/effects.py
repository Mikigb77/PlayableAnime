"""What a settled step does to the world, recorded by the engine before narration (F4): the aim's
outcome on its targets, the deed it proposes (W1) and the costs of the powers it used (A1).

Only the step's aim changes state here, and only for living characters it targeted, so nothing a
player writes can raise the dead or rewrite someone (A6, A7). Severity is a first guess that
`record_consequences` weighs by the world's norms (W12), and witnesses are worked out there too.
"""

from engine.contracts.delta import CharacterChange, ConditionChange, StateDelta
from engine.contracts.intent import Aim, IntentStep, OutcomeClass
from engine.contracts.resolution import Cost, ProposedDeed
from engine.resolve.power import SUBDUED_STATE
from engine.state.cast import Character, CharacterStatus, DeathCertainty
from engine.state.records import StepResult
from engine.state.sheet import Health, Power

_HEALTH_ORDER = list(Health)

# What each aim does to a target on a success and on a partial success.
_ON_SUCCESS = {Aim.KILL: None, Aim.WOUND: Health.WOUNDED, Aim.SUBDUE: None}
_ON_PARTIAL = {Aim.KILL: Health.BADLY_WOUNDED, Aim.WOUND: Health.HURT, Aim.SUBDUE: Health.HURT}

# A first guess at severity (W1), by aim and result; `record_consequences` weighs it (W12).
_SEVERITY = {
    Aim.KILL: {StepResult.SUCCESS: 4, StepResult.PARTIAL: 3, StepResult.FAILURE: 3},
    Aim.WOUND: {StepResult.SUCCESS: 3, StepResult.PARTIAL: 2, StepResult.FAILURE: 2},
    Aim.SUBDUE: {StepResult.SUCCESS: 2, StepResult.PARTIAL: 2, StepResult.FAILURE: 1},
    Aim.NONE: {StepResult.SUCCESS: 1, StepResult.PARTIAL: 1, StepResult.FAILURE: 1},
}


def aim_effects(step: IntentStep, result: StepResult, targets: list[Character]) -> StateDelta:
    """The engine's own changes for the aim's outcome on each living target."""
    if not step.aim.harmful or result is StepResult.FAILURE:
        return StateDelta()
    changes: list[CharacterChange] = []
    for target in targets:
        if not target.alive:
            continue
        if result is StepResult.SUCCESS and step.aim is Aim.KILL:
            changes.append(
                CharacterChange(
                    id=target.id,
                    status=CharacterStatus.DEAD,
                    death_certainty=DeathCertainty.CONFIRMED,
                )
            )
            continue
        if result is StepResult.SUCCESS and step.aim is Aim.SUBDUE:
            changes.append(
                CharacterChange(id=target.id, condition=ConditionChange(states=[SUBDUED_STATE]))
            )
            continue
        table = _ON_SUCCESS if result is StepResult.SUCCESS else _ON_PARTIAL
        health = table[step.aim]
        current = target.sheet.condition.health
        if health is None or _HEALTH_ORDER.index(health) <= _HEALTH_ORDER.index(current):
            continue
        changes.append(
            CharacterChange(
                id=target.id, condition=ConditionChange(health=health, wounds=[step.text])
            )
        )
    return StateDelta(characters=changes)


def proposed_deed(
    step: IntentStep,
    outcome_class: OutcomeClass,
    result: StepResult,
    actor_id: str | None,
    targets: list[Character],
    *,
    in_stopped_time: bool,
) -> ProposedDeed | None:
    """W1, A8. An attempt on someone is a deed even when it fails: the god notices the swing.
    Steps with no one on the other side aren't deeds here."""
    if not targets:
        return None
    harmed = (
        step.aim.harmful
        and result is not StepResult.FAILURE
        and outcome_class is not OutcomeClass.RULED_OUT
    )
    ids = [t.id for t in targets]
    outcome = {
        StepResult.SUCCESS: "it worked",
        StepResult.PARTIAL: "it partly worked",
        StepResult.FAILURE: "it failed",
    }[result]
    return ProposedDeed(
        kind=step.verb or step.aim.value,
        text=f"{step.text} ({outcome})",
        actor_id=actor_id,
        victim_ids=ids if harmed else [],
        target_ids=[] if harmed else ids,
        severity=_SEVERITY[step.aim][result],
        in_stopped_time=in_stopped_time,
    )


def power_costs(powers: list[Power]) -> list[Cost]:
    """A1, G22. Each power used pays its costs."""
    return [Cost(kind=c.kind, text=c.text, ref=p.id) for p in powers for c in p.costs]

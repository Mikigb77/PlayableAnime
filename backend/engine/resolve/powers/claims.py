"""Backstory claims (N4): what the player says about their own character's past or inner life.

A claim is recorded when it changes nothing the world already holds: a memory, a feeling, a
habit, an old wound. It is refused, and plays as something the character says or believes, when
it would give the sheet something it doesn't hold (a power, an item, a rank, an ally), when it says
how other people feel or react (A6, A7), when it contradicts a fact or a person the world already
has, or when it breaks a rule of the world that never changes (G7). A refused claim the character
believes is kept as their belief, not the truth.
"""

from engine.contracts.delta import CharacterChange, NewFact, StateDelta
from engine.contracts.intent import PastClaim
from engine.contracts.resolution import ClaimVerdict
from engine.state.cast import Character
from engine.state.records import FactKind
from engine.state.world import WorldState

RECORDED = "Recorded: it changes nothing the world already holds."
GRANTS = "It would give the sheet something it doesn't hold; that is earned in play (A4)."
OTHERS = "Other people's feelings and reactions are theirs, so it plays as a hope (A6)."
CONTRADICTS = "It contradicts what the world already holds."
RULE = "The world doesn't allow it ({rule}), so it plays as something believed, not the truth."


def judge_claims(
    state: WorldState, actor: Character, claims: list[PastClaim]
) -> tuple[list[ClaimVerdict], StateDelta]:
    """N4. A verdict on each claim, and the engine's changes: accepted claims on the sheet's
    backstory, and refused ones the character holds as beliefs."""
    verdicts: list[ClaimVerdict] = []
    accepted: list[str] = []
    beliefs: list[NewFact] = []
    for claim in claims:
        text = claim.text.strip()
        if not text:
            continue
        reason = _refusal(state, claim)
        if reason is None:
            verdicts.append(ClaimVerdict(text=text, accepted=True, reason=RECORDED))
            accepted.append(text)
            continue
        verdicts.append(ClaimVerdict(text=text, accepted=False, reason=reason))
        if reason.startswith("The world doesn't allow it"):
            beliefs.append(
                NewFact(
                    text=f"{actor.name} believes: {text}",
                    kind=FactKind.BELIEF,
                    is_true=False,
                    subject_ids=[actor.id],
                    known_by=[actor.id],
                    known_to_player=True,
                )
            )
    characters = [CharacterChange(id=actor.id, backstory=accepted)] if accepted else []
    return verdicts, StateDelta(characters=characters, facts=beliefs)


def _refusal(state: WorldState, claim: PastClaim) -> str | None:
    fixed = [r for r in (state.bible.rule(i) for i in claim.against_rule_ids) if r and r.fixed]
    if fixed:
        return RULE.format(rule=fixed[0].text.strip().rstrip("."))
    if claim.grants_power:
        return GRANTS
    if claim.about_others:
        return OTHERS
    for ref in claim.contradicts_ids:
        fact = state.facts.get(ref)
        if fact is not None and fact.is_true:
            return CONTRADICTS
        if ref in state.characters:
            return CONTRADICTS
    return None

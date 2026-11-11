"""W1, W4, N6: a bout both sides agreed to is not an attack.

People spar, test each other, fight matches and duel. Such a fight has terms, the worst both sides
accepted (`Terms`), and consent covers the bout, not the wound (Miki's long story, 2026-11: every
blow of a lesson with a mentor was recorded as an attack on him, and left him afraid, bearing
grudges and due to come for revenge):

- **Inside the terms** a blow is no attack. It leaves no grudge, starts no rumor of one, is no
  crime and brings nobody for revenge, however many blows the bout has. The bout is one deed,
  which those who fought it think a little better of each other for (`engine.world`).
- **The terms hold the blows.** A blow of the bout is any step that fights those in it
  (`is_blow`), whether they are its targets or only stand in its way, and whatever it aims to
  do: in the first live lesson (2026-11-11) a practice blow that aimed no harm and named no
  target was filed as an attack. A blow does at most what the terms accept, whatever aim was
  proposed for it. Under `no_harm` a touch, a throw or a pin decides it: nobody is wounded or
  left helpless, and a bruise is the worst it leaves. So a sparring blow read carelessly can't
  turn into a wounding. A friendly partner strikes only in the bout's exchanges, and waits
  while the player character talks or looks on.
- **Beyond the terms** a blow is an attack that came under cover of a friendly fight, and costs
  more trust than an open one. The actor goes beyond them only when the interpret step says they
  mean to (`StepFacts.breaks_terms`). Someone fighting the player character does only when they
  bear them ill will: a mentor fond of their student never tries to wound them in a lesson,
  whatever was proposed, and a rival with a grudge may, so a "friendly" bout can be a lure.
  Either way the bout is over, and what is left is an open fight.
- **Who can agree.** A person who is there and able to answer: alive, not helpless, no beast. A
  fight in earnest, in which someone was harmed outside any terms or whose terms were broken,
  can't become a bout afterwards, so an attack is never relabelled as one. A first blow that
  hurt nobody doesn't close that door: terms the interpret step left out once can still be
  agreed. While a bout is on its terms stay as agreed or get milder, never harsher, and someone
  new comes into it by agreeing to them, unless they are already fighting the player character
  openly.

The interpret step proposes the terms (`StepFacts.terms`). Code decides whether they hold and
keeps them on the encounter (`Encounter.bout`, `engine.encounters`), so a bout stays one when a
later step leaves them out. Plain Python (B4); nothing here assumes a genre (G5).
"""

from engine.contracts.intent import ActionKind, Aim, IntentStep
from engine.resolve.power import helpless_state, in_the_fray
from engine.state.cast import Character
from engine.state.scene import Bout, EncounterKind, Terms
from engine.state.world import WorldState
from engine.world.norms import DISPLAY_KINDS, HARM_FLOORS, HELP_KINDS, canonical, is_beast

# The worst a blow may be out to do under each terms, and the aims from mildest to worst.
WORST = {Terms.NO_HARM: Aim.SUBDUE, Terms.WOUNDS: Aim.WOUND, Terms.DEATH: Aim.KILL}
_AIMS = [Aim.NONE, Aim.SUBDUE, Aim.WOUND, Aim.KILL]
_TERMS = [Terms.NO_HARM, Terms.WOUNDS, Terms.DEATH]
# How little someone has to like the player character, on affinity (W4), to go beyond the terms
# of a bout with them. Anyone who holds a grudge against them may as well.
ILL_WILL = -20
# The kinds of deed that are blows, in the world's norms (`engine.world.norms`): what an attack,
# a strike or a stab is recorded as.
_STRIKES = frozenset({"assault", "wound", "kill"})
_VERB_MEANS = {"wound": Aim.WOUND, "kill": Aim.KILL}


def is_blow(step: IntentStep) -> bool:
    """Whether a step fights: it aims harm at someone, is told as a strike, or is an exchange
    of a fight. A practice blow often aims no harm at all and names nobody as its target, with
    the partner as what stands in its way, and it is still a blow of the bout. A step that is
    some other deed, such as an insult, a theft or a healing, is that deed whatever goes on
    around it."""
    if step.aim.harmful:
        return True
    word = canonical(step.verb or "")
    if word in _STRIKES:
        return True
    if word in HARM_FLOORS or word in HELP_KINDS or word in DISPLAY_KINDS:
        return False
    return step.encounter is EncounterKind.FIGHT or step.kind is ActionKind.EXCHANGE


def against(state: WorldState, actor_id: str, step: IntentStep) -> list[str]:
    """The characters a step is a blow at: those it names as its targets, or when it names
    none, those who stand in its way."""
    for faced in (step.target_ids, step.facts.opposition_ids):
        found = [i for i in dict.fromkeys(faced) if i != actor_id and i in state.characters]
        if found:
            return found
    return []


def meant(step: IntentStep) -> Aim:
    """What a blow is out to do: its aim, or when it has none, what its verb says of it (a
    stab wounds). Whether a blow goes beyond the terms is judged by this, so one the interpret
    step says is meant to maim is an attack even when it gave it no aim."""
    if step.aim.harmful:
        return step.aim
    return _VERB_MEANS.get(canonical(step.verb or ""), Aim.NONE)


def allows(terms: Terms, aim: Aim) -> bool:
    """Whether a blow out to do `aim` stays inside the terms."""
    return _AIMS.index(aim) <= _AIMS.index(WORST[terms])


def held(terms: Terms, aim: Aim) -> Aim:
    """The aim as the terms hold it: itself when they allow it, else the worst they accept."""
    return aim if allows(terms, aim) else WORST[terms]


def milder(first: Terms, second: Terms | None) -> Terms:
    """The milder of two terms: a bout's terms never get harsher while it is on."""
    if second is None:
        return first
    return min(first, second, key=_TERMS.index)


def can_agree(state: WorldState, character: Character) -> bool:
    """Whether someone can be one side of a bout: a person who is there and able to answer."""
    if not character.alive or helpless_state(character) is not None:
        return False
    if is_beast(state, character.id):
        return False
    return character.id == state.player_id or in_the_fray(state, character)


def sides(state: WorldState, bout: Bout) -> set[str]:
    """Everyone the bout's terms cover: the player character and those they agreed them with."""
    return {state.player_id, *bout.with_ids}


def covers(state: WorldState, bout: Bout | None, actor_id: str, target_ids: list[str]) -> bool:
    """Whether a blow of `actor_id` at `target_ids` is one of the bout's: both ends are sides of
    it. A blow that also falls on someone outside it is none of its own."""
    if bout is None or not target_ids:
        return False
    within = sides(state, bout)
    return actor_id in within and all(t in within for t in target_ids)


def bears_ill_will(character: Character, toward_id: str) -> bool:
    """W4. Whether someone dislikes another enough, by their true feelings (C6), or holds a
    grudge against them, to go beyond the terms of a bout with them."""
    attitude = character.sheet.disposition.attitudes.get(toward_id)
    if attitude is None:
        return False
    return attitude.affinity <= ILL_WILL or bool(attitude.grudges)

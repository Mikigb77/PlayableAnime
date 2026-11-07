"""Hurt bodies come only from the record (A8, N6, G13).

A wound, an injury, pain or an illness exists in a story only where the state holds it: a
character's health and wounds, a flaw trait such as a bad knee, or a passing state such as
poisoned. The player character starts every story unhurt, and everything that hurts them after
that is the engine's to settle (N6): a foe's blow or a danger that struck them, a breakthrough gone
wrong, a blast. So no model gives the player character an injury the engine didn't settle, and no
model leans on an injury the record doesn't hold (Miki, 2026-11-07, after a fight "reopened an old
wound" the character never had):

- **The narrator's update** never harms the player character: no worse health, no new wound and
  no passing state that names an injury (`engine.apply`). Healing stays the narrator's to show.
- **The interpret step's edges and hindrances** that speak of an injury stand only where the
  record holds it (`unrecorded_harm`). The character's own wounds and health are code's to weigh
  (`engine.resolve.capability`, A8), so a hindrance stands only when it names one of their flaw
  traits or passing states, or they carry a wound that lasts, and an edge only when someone the
  step faces is hurt on the record.
- **A body back to unhurt** keeps only the wounds that last, such as a lost eye
  (`Condition.set_health`), so a healed wound never lingers in the record to be "reopened".

Spotting an injury in a model's words is a word list in each story language (S10), deliberately
narrow: a word that only means harm next to a body part ("broken", "twisted") counts only there,
so a broken lock or a swollen river is never an injury.
"""

import re
import unicodedata
from collections.abc import Iterable

from engine.contracts.intent import IntentStep, StepFacts
from engine.state.cast import Character
from engine.state.sheet import Health, TraitKind
from engine.state.world import WorldState
from engine.text import mentions

# Words that always mean harm to a body, in English, Spanish and Catalan, without accents.
# A trailing "*" matches any ending.
_HARM = """
    wound* injur* hurt hurts hurting bruis* fractur* sprain* bleed* bled concuss* lacerat* gash*
    dislocat* pain pains painful pained ache aches aching headache* sore soreness limp limps
    limping sick sickness sickly illness ailing ailment* fever* maimed crippled
    herid* malherid* lesion* lesionad* magullad* moraton* contusion* esguince* sangrando
    sangrante* sangra hemorrag* cojea* cojera dolor dolores dolorid* dolorosa* doloroso*
    enfermo enferma enfermos enfermas enfermedad* fiebre* lastimad* duele duelen
    ferida ferides ferit ferits malferit* lesio lesions lesionat* contusio* esquinc* sagna
    sagnant* sagnar coixeja* coixesa dolors adolorit* malalt* febre* masegad* masegat*
"""
# Words that mean harm only next to a body part: "broken ribs", "una pierna rota", "cama
# trencada". A broken lock, a swollen river or a treasure chest is never an injury.
_DAMAGED = """
    broken broke cracked twisted torn shattered crushed burnt burned swollen stiff numb
    rot* quebrad* partid* torcid* hinchad* quemad* aplastad*
    trencat trencada trencats trencades esquerdat esquerdada torcat torcada inflat inflada
    inflats inflades cremat cremada cremats cremades
"""
_BODY = """
    rib ribs arm arms leg legs ankle ankles wrist wrists knee knees shoulder shoulders hand hands
    skull nose jaw hip hips finger fingers collarbone spine neck eye eyes
    costilla* brazo* pierna* tobillo* muneca* rodilla* hombro* mano manos nariz mandibula cadera*
    dedo* clavicula cuello pecho ojo ojos
    costella costelles brac bracos cama cames turmell* canell* genoll* espatlla* mans nas maluc*
    peu peus dit dits coll ull ulls
"""


def _patterns(words: str) -> re.Pattern[str]:
    parts = [re.escape(w[:-1]) + r"\w*" if w.endswith("*") else re.escape(w) for w in words.split()]
    return re.compile(r"\b(?:" + "|".join(parts) + r")\b")


_HARM_WORDS = _patterns(_HARM)
_DAMAGED_WORDS = _patterns(_DAMAGED)
_BODY_WORDS = _patterns(_BODY)


def _plain(text: str) -> str:
    """Lower case without accents, so "lesión" and "lesion", "braç" and "brac" match alike."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def names_injury(text: str) -> bool:
    """Whether the words speak of harm to a body: a wound, an injury, pain or an illness."""
    plain = _plain(text)
    if _HARM_WORDS.search(plain):
        return True
    return bool(_DAMAGED_WORDS.search(plain) and _BODY_WORDS.search(plain))


def is_hurt(character: Character) -> bool:
    """Whether the record holds harm to this character's body: worse than unhurt, or a wound."""
    condition = character.sheet.condition
    return condition.health is not Health.UNHURT or bool(condition.wounds)


def _held(character: Character) -> list[str]:
    """What the record holds of a character's body by name: flaw traits and passing states."""
    flaws = [t.name for t in character.sheet.traits if t.kind is TraitKind.FLAW]
    return [*flaws, *(s.name for s in character.sheet.condition.states)]


def _on_record(text: str, characters: Iterable[Character]) -> bool:
    return any(mentions(text, held) for c in characters for held in _held(c))


def unrecorded_harm(state: WorldState, actor: Character, step: IntentStep) -> tuple[StepFacts, int]:
    """The step's facts with every edge and hindrance that speaks of an injury the record doesn't
    hold left out, and how many were.

    A hindrance is the actor's own. Their health and passing wounds are code's to weigh (A8), so
    one that speaks of an injury stands only when it names a flaw trait or a passing state of
    theirs, or when they carry a wound that lasts, such as a lost eye, which no odds weigh. An
    edge is about whoever the step faces: it stands only when one of them is hurt on the record,
    or holds what it names."""
    facts = step.facts
    faced = [
        state.characters[i]
        for i in dict.fromkeys([*step.target_ids, *facts.opposition_ids])
        if i in state.characters and i != actor.id
    ]
    lasting = any(w.lasting for w in actor.sheet.condition.wounds)
    hindrances = [
        h for h in facts.hindrances if not names_injury(h) or lasting or _on_record(h, [actor])
    ]
    edges = [
        e
        for e in facts.edges
        if not names_injury(e) or any(is_hurt(c) for c in faced) or _on_record(e, faced)
    ]
    dropped = len(facts.hindrances) - len(hindrances) + len(facts.edges) - len(edges)
    if not dropped:
        return facts, 0
    return facts.model_copy(update={"hindrances": hindrances, "edges": edges}), dropped

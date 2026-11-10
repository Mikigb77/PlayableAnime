"""Hurt bodies come only from the record (A8, N6, G13).

A wound, an injury, pain or an illness exists in a story only where the state holds it: a
character's health and wounds, a flaw trait such as a bad knee, or a passing state such as
poisoned. The player character starts every story unhurt, and everything that hurts them after
that is the engine's to settle (N6): a foe's blow or a danger that struck them, a breakthrough gone
wrong, a blast. So no model gives the player character an injury nothing recorded, and no model
leans on an injury the record doesn't hold (Miki, 2026-11-07, after a fight "reopened an old
wound" the character never had):

- **The narrator's update** never harms the player character: no worse health, no new wound and
  no passing state that names an injury (`engine.apply`), except where something recorded this
  turn is the cause (`may_hurt_player`): a power's toll in health or blood that OUTCOME lists
  (`pays_in_body`), or the first opening's premise. Healing stays the narrator's to show.
- **The interpret step's edges and hindrances** that speak of an injury stand only where the
  record holds it (`unrecorded_harm`). One about the actor's own body stands only when it names a
  flaw or passing state of theirs or a wound that lasts, since their health and passing wounds are
  code's to weigh (`engine.resolve.capability`, A8). One about someone else stands only when that
  person is hurt on the record, and never names a part of them the record says is whole.
- **A body back to unhurt** keeps only the wounds that last, such as a lost eye
  (`Condition.set_health`), so a healed wound never lingers in the record to be "reopened".

Spotting an injury in a model's words is a word list in each story language (S10), deliberately
narrow: a word that only means harm beside a body part ("broken", "twisted", "sore") counts only
within a word of one, so a broken lock in someone's hand or a swollen river is never an injury.
"""

import re
import unicodedata
from collections.abc import Iterable

from engine.contracts.intent import IntentStep, StepFacts
from engine.contracts.resolution import Resolution
from engine.state.cast import Character
from engine.state.sheet import CostKind, Health, TraitKind
from engine.state.world import WorldState
from engine.text import mentions

# Words that always mean harm to a body, in English, Spanish and Catalan, without accents. A
# trailing "*" matches any ending. Words with an everyday sense besides harm ("limp", "sick",
# "cama", "dit") are left out or need a body part beside them.
_HARM = """
    wound wounds wounded wounding injur* hurts hurting bruis* fractur* sprain* bleed* bled
    concuss* lacerat* gash gashes gashed dislocat* pain pains painful pained ache aches aching
    headache* soreness limping sickness illness ailing ailment* fever* maimed crippled
    herid* malherid* lesion* lesionad* magullad* moraton* contusion* esguince* sangrando
    sangrante* sangra hemorrag* cojea* cojera dolor dolores dolorid* dolorosa* doloroso*
    enfermo enferma enfermos enfermas enfermedad* fiebre* lastimad* duele duelen
    ferida ferides ferit ferits malferit* lesio lesions lesionat* contusio* esquinc* sagna
    sagnant* sagnar coixeja* coixesa dolors adolorit* malalt* febre* masegad* masegat*
"""
# "hurt" is harm, except hurt pride or hurt feelings.
_HARM_RAW = (r"hurt(?!\s+(?:pride|feelings|ego)\b)",)
# Words that mean harm only beside a body part: "broken ribs", "una pierna rota", "el turmell
# inflat".
_DAMAGED = """
    broken broke cracked twisted torn shattered crushed burnt burned swollen stiff numb sore
    rota roto rotas rotos quebrad* torcid* hinchad* quemad* aplastad*
    trencat trencada trencats trencades esquerdat esquerdada torcat torcada inflat inflada
    inflats inflades cremat cremada cremats cremades
"""
_BODY = """
    rib ribs arm arms leg legs ankle ankles wrist wrists knee knees shoulder shoulders hand hands
    skull nose jaw hip hips finger fingers collarbone spine neck eye eyes
    costilla* brazo* pierna* tobillo* muneca* rodilla* hombro* mano manos nariz mandibula cadera*
    dedo* clavicula cuello pecho ojo ojos
    costella costelles brac bracos turmell* canell* genoll* espatlla* mans nas maluc* peu peus
    coll ull ulls
"""
# How far apart, in words, a damaged word and a body part may stand: "broken left arm".
_BESIDE = 2
# A power's toll paid in the body (A1, G13), which the narrator records in proportion.
TOLLS = (CostKind.HEALTH, CostKind.BLOOD)


def _pattern(words: str, raw: Iterable[str] = ()) -> re.Pattern[str]:
    parts = [re.escape(w[:-1]) + r"\w*" if w.endswith("*") else re.escape(w) for w in words.split()]
    return re.compile(r"\b(?:" + "|".join([*raw, *parts]) + r")\b")


_HARM_WORDS = _pattern(_HARM, _HARM_RAW)
_DAMAGED_WORDS = _pattern(_DAMAGED)
_BODY_WORDS = _pattern(_BODY)


def _plain(text: str) -> str:
    """Lower case without accents, so "lesión" and "lesion", "braç" and "brac" match alike."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _words(text: str) -> list[str]:
    return re.findall(r"\w+", _plain(text))


def _body(text: str) -> set[str]:
    """The body parts the words name, as written."""
    return {w for w in _words(text) if _BODY_WORDS.fullmatch(w)}


def names_injury(text: str) -> bool:
    """Whether the words speak of harm to a body: a wound, an injury, pain or an illness."""
    if _HARM_WORDS.search(_plain(text)):
        return True
    words = _words(text)
    damaged = [i for i, w in enumerate(words) if _DAMAGED_WORDS.fullmatch(w)]
    body = [i for i, w in enumerate(words) if _BODY_WORDS.fullmatch(w)]
    return any(abs(d - b) <= _BESIDE for d in damaged for b in body)


def is_hurt(character: Character) -> bool:
    """Whether the record holds harm to this character's body: worse than unhurt, or a wound."""
    condition = character.sheet.condition
    return condition.health is not Health.UNHURT or bool(condition.wounds)


def pays_in_body(resolution: Resolution) -> bool:
    """Whether a step that played paid a power's toll in health or blood this turn (A1)."""
    return any(c.kind in TOLLS for s in resolution.steps if not s.interrupted for c in s.costs)


def _flaws_and_states(character: Character) -> list[str]:
    flaws = [t.name for t in character.sheet.traits if t.kind is TraitKind.FLAW]
    return [*flaws, *(s.name for s in character.sheet.condition.states)]


def _matches(text: str, record: list[str]) -> bool:
    """Whether the words name something the record holds: all of its words, or a body part it
    names too."""
    if any(mentions(text, held) for held in record if held.strip()):
        return True
    named = _body(text)
    return bool(named & {part for held in record for part in _body(held)})


def _own(actor: Character, text: str) -> bool:
    """An injury the actor's record holds beyond what the odds already weigh: a flaw, a passing
    state, or a wound that lasts (with the look it left, M5) naming the same part."""
    lasting = [w.text for w in actor.sheet.condition.wounds if w.lasting]
    record = [*_flaws_and_states(actor), *lasting]
    if lasting:
        record.append(actor.appearance)
    return _matches(text, record)


def _theirs(character: Character, text: str) -> bool:
    """An injury someone else's record holds: a flaw or passing state it names, or harm on the
    record that the words don't contradict, part for part."""
    if _matches(text, _flaws_and_states(character)):
        return True
    if not is_hurt(character):
        return False
    named = _body(text)
    on_record = {part for w in character.sheet.condition.wounds for part in _body(w.text)}
    return not named or not on_record or bool(named & on_record)


def _named(text: str, character: Character) -> bool:
    """Whether the words name this character: by name, an alias or the first word of the name."""
    first = character.name.split()[0] if character.name.split() else ""
    names = [character.name, *character.aliases, *([first] if len(first) >= 3 else [])]
    return any(mentions(text, n) for n in names if n.strip())


def unrecorded_harm(state: WorldState, actor: Character, step: IntentStep) -> tuple[StepFacts, int]:
    """The step's facts with every edge and hindrance that speaks of an injury the record doesn't
    hold left out, and how many were.

    Words that name someone in the scene or someone the step faces are about them, and stand only
    when their record holds the injury. Otherwise a hindrance is about the actor, and stands only
    when it names a flaw, a passing state or a wound that lasts of theirs: their health and
    passing wounds are code's to weigh (A8). An edge that names nobody stands when someone the
    step faces holds the injury."""
    facts = step.facts
    faced_ids = [*step.target_ids, *facts.opposition_ids]
    faced = [
        state.characters[i]
        for i in dict.fromkeys(faced_ids)
        if i in state.characters and i != actor.id
    ]
    around = [
        state.characters[i]
        for i in dict.fromkeys([*faced_ids, *state.scene.present_ids])
        if i in state.characters and i != actor.id
    ]

    def stands(text: str, *, edge: bool) -> bool:
        if not names_injury(text):
            return True
        named = [c for c in around if _named(text, c)]
        if named:
            return any(_theirs(c, text) for c in named)
        if edge:
            return any(_theirs(c, text) for c in faced)
        return _own(actor, text)

    hindrances = [h for h in facts.hindrances if stands(h, edge=False)]
    edges = [e for e in facts.edges if stands(f"{e.text} {e.ref}".strip(), edge=True)]
    dropped = len(facts.hindrances) - len(hindrances) + len(facts.edges) - len(edges)
    if not dropped:
        return facts, 0
    return facts.model_copy(update={"hindrances": hindrances, "edges": edges}), dropped

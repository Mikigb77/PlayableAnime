"""S4: a scene's ending is shown, never told.

The narrator is asked to end on where things stand and stop (`NarratorOutput.narration`), and
on the real models it still closed scenes on the player's move: "You must decide whether to
slip your sleeping powder into his wine, or keep him charmed here", "The time has come to slip
away and secure the schedules", "It is time to rest, or perhaps to share what you have done"
(the plays of 2026-11-14: four scenes of fifty, one of them after the form said so). So
code holds the line. The closing
sentences of a scene that tell the player what to do are left out of it (`shown`), and the
scene ends on what it showed before them. While the scene streams, a sentence that may yet
turn out to be one of those waits (`showable`), so the player never reads a line the saved
scene won't have.

Only the narrator's own closing words are read. What someone in the scene says is theirs to
say ("Will you answer the call, or must I draft every youth of the village?"), so a sentence
with a quotation mark in it, or inside a speech still open, always stays. So does the last
sentence a scene has left: nothing here ever leaves a scene blank.

The wordings are the ones narrators reach for, in the three languages the app speaks (S10):
what the player must decide, choose or do, that it is time to do something, which ways are
open, that the choice is theirs, and a question put to the player. A sentence is read from its
first words, so one that only mentions a decision further on ("Aldous waits to hear what you
decide") is showing, and stays. Words that also plainly tell a game or a thing in hand ("Your
move", "Está en tus manos") are left alone: a scene that loses a good last line is worse off
than one that keeps a soft one.
"""

import re
from collections.abc import Iterator

# The issue code for a scene whose closing words code left out: only that it happened is
# logged, never the words (T5, T6).
ENDING_TOLD = "ending_told"
# How far into a sentence the words that make it one of these can run. A sentence still being
# told is held until it has this many characters, since nothing yet says what it will be.
OPENING_CHARS = 72

# Where one sentence stops and the next starts: the marks that close it, then the space
# between them. Not before a small letter, where the stop was a pause ("And then... you").
_BREAK = re.compile(r"(?<=[.!?…])([\"'”’»)*_]*)(\s+)(?![a-zà-öø-ÿ])")
# A quotation mark: any double one, and a single one that isn't an apostrophe inside a word.
_QUOTE = re.compile(r"[\"“”„«»]|(?<![^\W\d_])['‘’]|['‘’](?![^\W\d_])")

_AND = r"(?:(?:and|but|so|then|y|pero|así que|entonces|i|però|així que|llavors)[,;:]? )?"
_NOW = r"(?:(?:now|for now|ahora|por ahora|ara|per ara)[,;:]? )?"
_ASKED = r"\?$"

# Each wording as how the sentence opens, and what the rest of it must hold for it to count:
# nothing more, or the question mark of a question put to the player.
_WORDINGS: tuple[tuple[str, str | None], ...] = (
    # What the player must decide, choose or do.
    (
        r"you (?:now |soon |alone |still )?"
        r"(?:must|should|need to|have to|will have to|will need to|['’]ll have to|had better) "
        r"(?:now |soon |quickly |first )?"
        r"(?:decide|choose|pick|act|make (?:a|your|the) (?:choice|decision|move))\b",
        None,
    ),
    (
        r"(?:debes|tienes que|has de|deberás|tendrás que|te toca|necesitas|deberías) "
        r"(?:ahora |pronto |ya )?"
        r"(?:decidir|elegir|escoger|actuar|tomar (?:una|la|tu) decisión)\b",
        None,
    ),
    (
        r"(?:has de|hauràs de|et cal|et caldrà|et toca|hauries de|necessites) "
        r"(?:ara |aviat |ja )?"
        r"(?:decidir|triar|escollir|actuar|prendre (?:una|la) decisió)\b",
        None,
    ),
    (r"cal que (?:ara )?(?:decideixis|triïs|escullis|actuïs)\b", None),
    (r"(?:decide|choose)(?: (?:now|quickly|wisely|carefully|well|fast|soon))?[.!,:]", None),
    (r"whatever you (?:choose|decide)\b", None),
    # That it is time to do something.
    (r"it(?: is|['’]s) (?:now |finally |high |about )?time (?:for you )?to\b", None),
    (r"the (?:time|moment|hour) has (?:now |finally )?come (?:for you )?to\b", None),
    (r"now is the (?:time|moment) to\b", None),
    (r"(?:ya )?(?:ha llegado|llegó|llega|es) (?:el momento|la hora|hora|momento) de\b", None),
    (r"(?:ja )?(?:ha arribat|arriba|és) (?:el moment|l['’]hora|hora|moment) d(?:e\b|['’])", None),
    # Which ways are open.
    (r"you (?:can|could|may|might) (?:either|choose (?:to|between|whether))\b", None),
    (
        r"you (?:now )?have (?:only |but |just )?(?:two|three|a few|several) "
        r"(?:choices|options|paths|ways|courses)\b",
        None,
    ),
    (r"your (?:options|choices) are\b", None),
    (r"puedes (?:elegir|escoger|optar)\b", None),
    (
        r"tienes (?:solo |sólo |tan solo )?(?:dos|tres|varias|varios|unas pocas) "
        r"(?:opciones|salidas|alternativas|caminos)\b",
        None,
    ),
    (r"tus opciones son\b", None),
    (r"pots (?:triar|escollir|optar)\b", None),
    (
        r"tens (?:només |tan sols )?(?:dues|dos|tres|diverses|diversos|unes poques) "
        r"(?:opcions|sortides|alternatives|camins)\b",
        None,
    ),
    (r"les teves opcions són\b", None),
    # That the choice is theirs.
    (
        r"the (?:choice|decision|next move|next step) (?:is|lies|rests) "
        r"(?:now |entirely |all |solely )?(?:yours|up to you|in your hands|with you)\b",
        None,
    ),
    (
        r"it(?: is|['’]s) (?:now |all |entirely )?(?:up to you|your (?:call|choice|decision))\b",
        None,
    ),
    (
        r"what (?:(?:happens|comes) next|you do (?:next|now)) is "
        r"(?:up to you|yours to decide|in your hands|your (?:choice|call|decision))\b",
        None,
    ),
    (
        r"la (?:decisión|elección) (?:es|está) (?:solo |sólo |únicamente |ahora )?"
        r"(?:tuya|en tus manos)\b",
        None,
    ),
    (r"tú decides(?:$|[.!…]| (?:qué|cómo|si|cuándo|ahora)\b)", None),
    (r"(?:todo )?depende de ti\b", None),
    (r"todo está en tus manos\b", None),
    (
        r"la (?:decisió|tria|elecció) (?:és|està) (?:només |tota |ara )?"
        r"(?:teva|(?:a|en) les teves mans)\b",
        None,
    ),
    (r"tu decideixes(?:$|[.!…]| (?:què|com|si|quan|ara)\b)", None),
    (r"(?:tot )?depèn de tu\b", None),
    (r"tot (?:és|està) (?:a|en) les teves mans\b", None),
    # A question put to the player.
    (
        r"what (?:will|do|would|should|can|could) you (?:do|say|choose|decide|answer|try)\b",
        _ASKED,
    ),
    (r"what are you going to (?:do|say|choose)\b", _ASKED),
    (r"what would you like to do\b", _ASKED),
    (
        r"how (?:will|do|would|should) you "
        r"(?:respond|answer|react|proceed|reply|handle|act|play)\b",
        _ASKED,
    ),
    (
        r"what(?:['’]s| is| will be) your (?:next )?"
        r"(?:move|choice|decision|answer|plan|response|play)\b",
        _ASKED,
    ),
    (r"what (?:now|next)\b", _ASKED),
    (r"which (?:\w{1,12} )?(?:will|do|would|should) you (?:choose|take|pick|follow)\b", _ASKED),
    # One that sets ways side by side: "Will you wake him, or fetch the bailiff?"
    (r"(?:will|do|would|should|can|could) you\b", r"\bor\b[^?]*\?$"),
    (
        r"qué (?:harás|haces|vas a hacer|decides|decidirás|eliges|elegirás|dices|dirás"
        r"|respondes|responderás)\b",
        _ASKED,
    ),
    (
        r"cómo (?:respondes|responderás|reaccionas|reaccionarás|actúas|actuarás|procedes"
        r"|procederás)\b",
        _ASKED,
    ),
    (
        r"cuál (?:será|es) tu (?:próximo |siguiente |próxima )?"
        r"(?:movimiento|paso|decisión|respuesta|elección|jugada)\b",
        _ASKED,
    ),
    (r"(?:ahora qué|qué ahora)\b", _ASKED),
    (
        r"què (?:faràs|fas|decideixes|decidiràs|tries|triaràs|dius|diràs|respons"
        r"|respondràs)\b",
        _ASKED,
    ),
    (r"com (?:respons|respondràs|reacciones|reaccionaràs|actues|actuaràs)\b", _ASKED),
    (
        r"quina? (?:serà|és) (?:el teu|la teva) (?:proper |propera |següent )?"
        r"(?:moviment|pas|decisió|resposta|tria|jugada)\b",
        _ASKED,
    ),
    (r"(?:ara què|què ara)\b", _ASKED),
)
_READ = tuple(
    (re.compile(_AND + _NOW + opening, re.IGNORECASE), rest and re.compile(rest, re.IGNORECASE))
    for opening, rest in _WORDINGS
)


def _words(sentence: str) -> str:
    """A sentence as its words alone: one space between them, and none of the marks a sentence
    can stand in (an emphasis, a dash, Spanish's opening question mark)."""
    return " ".join(sentence.split()).strip("*_ ").lstrip("¿¡—–-… ")


def tells(sentence: str) -> bool:
    """Whether a sentence of the narrator's own tells the player what to do: what they must
    decide, that it is time, which ways are open, that the choice is theirs, or a question put
    to them."""
    words = _words(sentence)
    for opening, rest in _READ:
        found = opening.match(words)
        if found and (rest is None or rest.search(words, found.end())):
            return True
    return False


def _may_tell(sentence: str) -> bool:
    """Whether a sentence still being told may yet be one that tells: it opens as one, or it is
    too short to say."""
    words = _words(sentence)
    return len(words) < OPENING_CHARS or any(opening.match(words) for opening, _ in _READ)


def _sentences(text: str) -> Iterator[tuple[int, int]]:
    """Where each sentence of a text starts and ends, last first."""
    end = len(text.rstrip())
    for found in reversed(list(_BREAK.finditer(text, 0, end))):
        yield found.end(2), end
        end = found.end(1)
    start = len(text) - len(text.lstrip())
    if start < end:
        yield start, end


def _spoken(text: str, start: int, end: int) -> bool:
    """Whether the sentence at `start` is, or may be, someone's speech: it has a quotation mark
    in it, or a speech opened before it is still open."""
    if _QUOTE.search(text, start, end):
        return True
    before = text[:start]
    return (
        before.count('"') % 2 == 1
        or before.count("“") > before.count("”")
        or before.count("«") > before.count("»")
    )


def shown(narration: str, *, after: str = "") -> str:
    """S4: a scene's narration without the closing sentences that tell the player what to do,
    given back as it came when it has none. `after` is what the scene told before it (its
    action, R1), where a speech may have opened. The narration's last sentence left is never
    taken, so no scene is left blank."""
    text = f"{after}\n\n{narration}" if after.strip() else narration
    offset = len(text) - len(narration)
    spans = [(start, end) for start, end in _sentences(text) if start >= offset]
    keep = None
    for (start, end), following in zip(spans, spans[1:], strict=False):
        if _spoken(text, start, end) or not tells(text[start:end]):
            break
        keep = following[1]
    return narration if keep is None else text[offset:keep]


def showable(telling: str) -> int:
    """S4: how much of a scene still being told can go out to the player: all of it but its
    closing sentences that tell the player what to do, or may yet turn out to. Whatever
    follows them later lets them go, and a scene that ends on them never showed them. It never
    holds more than `shown` can take, so nothing a scene keeps waits past its end."""
    spans = list(_sentences(telling))
    held = None
    # Never the scene's first sentence, which it keeps whatever it says: it goes out as it is
    # written, so the first words reach the player as soon as before (S3).
    for at, (start, end) in enumerate(spans[:-1]):
        sentence = telling[start:end]
        # The last may still be growing; the ones before it are whole.
        told = _may_tell(sentence) if at == 0 else tells(sentence)
        if not told or _spoken(telling, start, end):
            break
        held = start
    if held is None:
        return len(telling)
    # Not the space before them either: what went out reads as the scene would without them.
    return len(telling[:held].rstrip())

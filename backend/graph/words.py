"""The words of a text, read by code in the story's languages (S10): which ones say something,
and when two are the same word.

Plain Python, shared by what reads a scene's wording (`graph.turn.worn`, R9) and what reads the
player's own words for a draft (`graph.drafting.named`, G1). Nothing here knows a genre, and
nothing is logged.
"""

import re

from engine.context import Language

# The small words that say nothing by themselves, by language: articles, pronouns,
# prepositions, conjunctions, the commonest helper verbs and adverbs.
_FILLER = {
    Language.EN: """a an the and or but nor so yet for of in on at to from by with without into
        onto over under above below between among through across against about around before
        after behind beside near off up down out as than then that this these those there here
        it its is are was were be been being am do does did have has had having will would
        shall should can could may might must not no you your yours yourself he him his she her
        hers they them their theirs we us our i me my mine who whom whose which what when where
        why how if while though although because until unless since once still just only even
        also too very more most much many some any each every all both either neither one two
        own same such again ever never now already almost enough rather quite you're you've
        you'll you'd it's he's she's they're don't doesn't didn't can't won't isn't aren't
        wasn't weren't there's that's i'm i've""",
    Language.ES: """el la los las un una unos unas lo al del de en a por para con sin sobre bajo
        entre hacia hasta desde contra tras ante durante según y e o u ni pero sino que como
        cuando donde mientras aunque porque pues si no sí ya aún todavía también tampoco muy más
        menos mucho mucha muchos muchas poco poca pocos pocas tan tanto todo toda todos todas
        cada otro otra otros otras mismo misma este esta estos estas ese esa esos esas aquel
        aquella aquellos aquellas esto eso aquello tu tus tú te ti tuyo tuya su sus se le les me
        mi mis nos nuestro nuestra él ella ellos ellas yo es son era eran fue fueron ser estar
        está están estaba estaban ha han había habían hay he has soy eres somos qué quién cuál
        cómo dónde cuándo algo nada alguien nadie uno dos sólo solo apenas casi así entonces
        ahora luego después antes aquí allí ahí""",
    Language.CA: """el la els les un una uns unes lo de del dels al als a en amb sense per pel
        pels sobre sota entre cap fins des contra durant segons i o ni però sinó que com quan on
        mentre encara perquè doncs si no sí ja també tampoc molt molta molts moltes més menys
        poc poca pocs poques tan tant tot tota tots totes cada altre altra altres mateix mateixa
        aquest aquesta aquests aquestes aquell aquella aquells aquelles això allò tu et te ti
        teu teva teus teves seu seva seus seves se es li hi ho em me meu meva ens nostre nostra
        ell ella ells elles jo és són era eren va van ser estar està estan estava estaven ha han
        havia havien he has sóc ets som què qui quin quina res algú ningú dos només gairebé
        així llavors ara després abans aquí allà""",
}
FILLER = {language: frozenset(words.split()) for language, words in _FILLER.items()}

WORD = re.compile(r"[^\W\d_]+(?:['’-][^\W\d_]+)*")
# "l'espasa" is "espasa", and "Zhao's" is "Zhao".
_ELIDED = re.compile(r"^[ldsnmt]'|'s$")
# How much of the shorter word two words must share from their start to be one word in two
# forms, and never fewer letters than this: "killed" and "killing", "torneo" and "torneos".
ALIKE_SHARE = 0.6
ALIKE_MIN = 4


def core(word: str) -> str:
    """A word as it is compared: in lower case, without an elided article or a possessive."""
    return _ELIDED.sub("", word.replace("’", "'").casefold())


def content(text: str, language: Language) -> list[str]:
    """The words of `text` that say something, in order: no small words, and none under three
    letters."""
    filler = FILLER[language]
    found = (core(word) for word in WORD.findall(text))
    return [word for word in found if len(word) >= 3 and word not in filler]


def alike(one: str, other: str) -> bool:
    """Whether two words are the same word, in the same form or another: they are equal, or
    they start alike for most of the shorter one."""
    if one == other:
        return True
    shared = 0
    for a, b in zip(one, other, strict=False):
        if a != b:
            break
        shared += 1
    return shared >= ALIKE_MIN and shared >= ALIKE_SHARE * min(len(one), len(other))

"""Matching what a model wrote against what the state holds, in plain words.

The interpret step and the narrator name things in words ("a stone the size of an egg",
"teleport", "12 copper coins"), and the state names them in words too (a scene prop, a power's
description, an item). Matching is on word stems and goes one way only: every meaningful word the
model wrote must be in what the state holds. So "my pistol" finds the "Beretta pistol" and
"teleport" finds "Void Step: teleports her a mile", while "a shotgun under the bar" doesn't find
the bar, and a trait called "Fire" doesn't answer "put out the fire". A word the state doesn't hold
is never a match, so models give ids where they can and words are the fallback. It is deliberately
simple and genre-free (G5), and depends on nothing else in the engine, so any part of it can use
it (`engine.resolve.words`, `engine.possessions`).

A story's sheet and the models' words are in its language (S10), so Spanish and Catalan articles
and prepositions count for nothing either, and accented letters stay part of their word: "la
cuchilla de aura" finds "Cuchilla del Aura", and "técnica" is one word, not "t" and "cnica".
"""

import re

_STOPWORDS = frozenset(
    """a an the of to and or in on at by for from with without into onto out up down off over
    under through her his its their your my our me them him she he they it this that these those
    is are be was were been has have had can could would should will shall do does did not no
    any some all just very one own so as if then than there here who whom which what when""".split()
)
# S10. The same small words in Spanish and Catalan: articles, prepositions and possessives. Only
# words that are no English word a story would match on, so "sin", "son" and "al" stay.
_STOPWORDS_ES_CA = frozenset(
    """el la los las lo un una unos unas de del en con por para su sus tu tus mi mis se le les
    que es y o els uns unes dels amb per seu seva seus seves teu teva teus teves meu meva meus
    meves""".split()
)
_STOPWORDS = _STOPWORDS | _STOPWORDS_ES_CA
_SUFFIXES = ("ation", "ing", "ed", "es", "s")
_VOWELS_AND_DOUBLES = set("aeioulsz")


def _stem(word: str) -> str:
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            word = word[: -len(suffix)]
            # "stopped" -> "stopp" -> "stop", but "asleep" and "spell" keep their letters.
            if len(word) >= 3 and word[-1] == word[-2] and word[-1] not in _VOWELS_AND_DOUBLES:
                word = word[:-1]
            break
    if len(word) > 3 and word.endswith("e"):
        word = word[:-1]  # "breathe" and "breath", "fire" and "fires"
    return word


def stems(text: str) -> frozenset[str]:
    """The meaningful word stems of a text."""
    words = re.findall(r"[^\W_]+", text.casefold())
    return frozenset(_stem(w) for w in words if w not in _STOPWORDS and len(w) > 1)


def mentions(haystack: str, needle: str) -> bool:
    """Whether the needle names something the haystack holds: every meaningful word of the needle
    appears in the haystack. One way only, so extra words in the needle never match by accident."""
    hay, wanted = stems(haystack), stems(needle)
    return bool(wanted) and wanted <= hay


def any_mentions(haystacks: list[str], needle: str) -> str | None:
    """The first haystack that mentions the needle."""
    return next((h for h in haystacks if mentions(h, needle)), None)

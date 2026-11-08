"""The studio voices a player can pick for reading aloud (V9), and the accent each story is read in.

Gemini's TTS models have 30 prebuilt voices, each of which reads any language. These four suit a
storyteller: two lower, two higher, from warm to grave. The app names them by how they sound and
sends the name; the default is the one a new player hears.

Left to itself, the voice model guesses the language from the words, and can read Spanish with a
Latin American accent, or with an English voice's pronunciation (Miki, 2026-11-08). So each part
is read with the story's language and accent named (`READING_LOCALES`): Spanish from Spain, as the
narrator writes it (S10), never Latin American; American English, as dictation hears it (V4); and
Catalan.
"""

from engine.context import Language

DEFAULT_VOICE = "Sulafat"
# Name: how it sounds, as Google describes it.
VOICES = {
    "Sulafat": "warm",
    "Gacrux": "mature",
    "Charon": "informative, deep",
    "Algieba": "smooth",
}

# The BCP-47 code each story language is read in, which sets the voice's accent.
READING_LOCALES = {
    Language.EN: "en-US",
    Language.ES: "es-ES",
    Language.CA: "ca-ES",
}


def reading_locale(language: Language) -> str:
    """The language and accent a story in `language` is read aloud in, such as `es-ES`."""
    return READING_LOCALES[language]

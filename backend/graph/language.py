"""The language a story is written in (S10), for the prompts of the models that write what the
player reads: the drafter, the narrator, the summarizer and the interpret step's notes.

A story has one language at a time (`StorySettings.language`), and the player can switch it, so
the story carries on in the new language from the next scene. What was already written stays as
it was: the prompts say to write in the story's language even when earlier scenes, the world or
the player's words are in another. Names keep the spelling they were given.
"""

from engine.context import Language

_WRITTEN_IN = {
    Language.EN: "English",
    Language.ES: "Spanish from Spain, speaking to the player as tú",
}


def written_in(language: Language) -> str:
    """The language as a prompt names it, such as "English"."""
    return _WRITTEN_IN[language]


def language_line(language: Language, what: str) -> str:
    """One prompt line: write `what` in the story's language, keeping names and ids as they
    are."""
    return (
        f"Language: write {what} in {written_in(language)}, even where the input is in another "
        "language. Keep every name as it is spelled, and ids as short lowercase words."
    )

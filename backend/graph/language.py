"""The language a story is written in (S10), for the prompts of the models that write what the
player reads: the drafter, the narrator, the summarizer and the interpret step's notes.

A story is written in the language it was started in (`StorySettings.language`): English, Spanish
or Catalan, from the app's language when the player set it up. The prompts say to write in it
even when the world, the player's words or, in a story switched before stories kept their
language, earlier scenes are in another. Names keep the spelling they were given.
"""

from engine.context import Language

_WRITTEN_IN = {
    Language.EN: "English",
    Language.ES: "Spanish from Spain, speaking to the player as tú",
    Language.CA: "Catalan, speaking to the player as tu",
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

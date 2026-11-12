"""Gemini safety settings per rating (F5), in one table so WS16 and the T15 evals can tune it.

F5 asks for the most permissive level the policy allows. Gemini on Vertex AI offers, from least
to most strict: `off` (no filter, no safety metadata), `block_none` (scores only, and restricted
to approved projects, so we don't use it), `block_only_high`, `block_medium_and_above` and
`block_low_and_above`. Gemini has no category for fictional violence, so gore is governed by the
prompt and the ratings table, never by a filter. The non-configurable filters (child safety and
personal data) stay on whatever we set; they show up as `prohibited_content` or `spii` blocks.

Why each line is where it is:

- **Harassment** is off in Mature, where villains threaten and insult, and filters only the
  worst in Teen.
- **Hate speech** filters only the worst in both, because hate aimed at real groups is out in
  every rating (G12) while fictional race feuds (G23) are in.
- **Sexually explicit** filters only the worst in Mature, as a backstop for the fade-out rule
  (F2, Google's prohibited use policy), and from medium in Teen, where romance stops at a kiss.
- **Dangerous content** filters only the worst in both by default, as a backstop for F3's ban on
  real-world harm instructions. It is off where it would stop the story rather than an
  instruction (below), because Gemini files a character's self-harm under it: on 2026-11-05 it
  blocked "I stab myself", "I jump off the castle" and a knife to a stranger.
- **Pictures** stay mild in every rating (M6), so they filter from medium, and sexual content
  from low.
- **The interpret step** runs with dangerous content off in both ratings, and in Mature with
  harassment, hate speech and sexual content off too. It only reads the player's own words, and
  the scene they answer (R2), which the narrator's own filters already let through, into an
  intent and writes no story text, yet a block there is the one the player sees: the action
  can't be read, so the deed never happens (F4). That is likeliest exactly where the ratings
  table allows the deed and only its telling is bounded, such as a character taking their own
  life or sexual violence off the page. The narrator's filters and the code's hard limits
  (`engine.limits`, F3) still bound what is told. Teen keeps the narrator's other settings, and
  a sexual step never plays there anyway (F2). A second reading of the same words by the larger
  model (B8) runs with the same settings, and so does the wording of the engine's own lines in
  the story's language (S10): it only says again, line by line, what code already decided ("It
  kills you."), and code keeps each line only when its numbers and names are the engine's.
- **The narrator in Mature** runs with dangerous content off, so a death the player chose is
  told, not cut away (F1, Miki 2026-11-05). F3's line on real-world instructions is held there by
  code instead: a narration that reads as a working procedure is retold as a cut-away
  (`engine.limits.harm_instructions`). Teen keeps the filter, so such a death happens off the
  page there.
- **Chapter summaries** (C3) run with dangerous content off in both ratings. They only retell
  scenes already told, and a blocked one is asked for again on every turn, so a Teen story with
  a death in it would never get its chapter. A summary that reads as working instructions is
  dropped by the same code check before it is kept.

Checked against google-genai 2.34 for WS16 (2026-11-03). `civic_integrity` is deprecated and
`jailbreak` ("prompts designed to bypass safety filters") stays at Gemini's default. The image
categories (`image_hate`, `image_dangerous_content`, `image_harassment`,
`image_sexually_explicit`) exist only on Vertex AI and are refused by the Gemini API that a
player's own key uses, and an `IMAGE_SAFETY` block can't be turned down, so pictures rely on the
text categories above and the mild-picture prompt (M6) until T18's live picture evals show what
the image categories add.
"""

from __future__ import annotations

from collections.abc import Mapping

from graph.llm.types import Node, Rating

HARM_CATEGORIES = ("harassment", "hate_speech", "sexually_explicit", "dangerous_content")
THRESHOLDS = ("off", "block_only_high", "block_medium_and_above", "block_low_and_above")

_TEXT: Mapping[Rating, Mapping[str, str]] = {
    "mature": {
        "harassment": "off",
        "hate_speech": "block_only_high",
        "sexually_explicit": "block_only_high",
        "dangerous_content": "block_only_high",
    },
    "teen": {
        "harassment": "block_only_high",
        "hate_speech": "block_only_high",
        "sexually_explicit": "block_medium_and_above",
        "dangerous_content": "block_only_high",
    },
}

_INTERPRET: Mapping[Rating, Mapping[str, str]] = {
    "mature": {
        "harassment": "off",
        "hate_speech": "off",
        "sexually_explicit": "off",
        "dangerous_content": "off",
    },
    "teen": {**_TEXT["teen"], "dangerous_content": "off"},
}

# Mature: the narrator, where code holds F3's line on instructions as it streams.
_TELLS_STORY = (Node.NARRATOR,)

_PICTURES: Mapping[str, str] = {
    "harassment": "block_medium_and_above",
    "hate_speech": "block_medium_and_above",
    "sexually_explicit": "block_low_and_above",
    "dangerous_content": "block_medium_and_above",
}


def safety_settings(
    rating: Rating, *, picture: bool = False, node: Node | str | None = None
) -> Mapping[str, str]:
    """The threshold per harm category for a call, in our lowercase names."""
    if rating not in _TEXT:
        raise ValueError(f"Unknown rating {rating!r}")
    if picture:
        return dict(_PICTURES)
    if node in (Node.INTERPRET, Node.SECOND_READING, Node.WORDING):
        return dict(_INTERPRET[rating])
    if node in (Node.SUMMARIZER, Node.PICTURE_NOTE):
        # C3: a chapter only retells what was already told, and a block would ask for it again
        # every turn; code checks it for instructions before it is kept (F3). M5: a picture's
        # description only retells, mildly, a scene the player has read, and the picture's own
        # settings and rules (M6) stand behind it.
        return {**_TEXT[rating], "dangerous_content": "off"}
    if rating == "mature" and node in _TELLS_STORY:
        return {**_TEXT[rating], "dangerous_content": "off"}
    return dict(_TEXT[rating])

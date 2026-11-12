"""T15's content-line cases as data, for the eval runner (WS17) to play deterministically in CI
and live against Gemini later. The cases are in `content_lines.json`; this module loads them and
builds each case's starting world. Plain Python with no Django, so the runner can use it alone.

    for case in load_cases():
        world = build_world(case)  # None for a case drafted from its premise
        ...                        # play case.script, then check case.expect

- A **deterministic** case (`case.deterministic`) has an `interpretation` per script line, fed
  to the turn graph in place of the interpret model, and expects the engine to refuse the step
  with `expect.limit`, one of `engine.limits.LimitCategory` (F3, G12, F2). No model is needed.
  A case with a `language` plays in a story in it (S10): the engine reads the limits in that
  language's words too, and a live run has the real model read an action written in it.
- A **live** case runs the real models. `expect.narration_mode` lists the acceptable
  `TurnResult.narration_mode` values: `template` is never one, because it means Gemini's filters
  blocked a scene the ratings table allows twice over (F4, F5). The judge scores the narration
  against `must` and `must_not` with `JUDGE["instructions"]`, and a case with `picture` draws the
  scene's picture and judges it with `JUDGE["picture_instructions"]` (M6, T18).
"""

import json
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any, Literal

from engine import samples
from engine.context import ContentPrefs, Language, Rating
from engine.contracts import Intent
from engine.limits import LimitCategory
from engine.state.cast import Character
from engine.state.world import WorldState

CASES_FILE = Path(__file__).with_name("content_lines.json")

Theme = Literal[
    "violence_and_gore", "romance_and_sex", "sexual_violence", "cruelty_and_crime", "hard_limits"
]
# The ratings table's rows (docs/REQUIREMENTS.md, under F2).
TABLE_THEMES: tuple[Theme, ...] = (
    "violence_and_gore",
    "romance_and_sex",
    "sexual_violence",
    "cruelty_and_crime",
)
WORLDS = {"grounded": samples.grounded_world, "cultivation": samples.cultivation_world}
NarrationMode = Literal["full", "cutaway"]


@dataclass(frozen=True)
class Expect:
    limit: LimitCategory | None = None
    narration_mode: tuple[NarrationMode, ...] = ()
    must: tuple[str, ...] = ()
    must_not: tuple[str, ...] = ()
    picture: Literal["scene"] | None = None
    deed_recorded: bool = False
    no_real_entities_in_state: bool = False


@dataclass(frozen=True)
class ContentLineCase:
    id: str
    title: str
    theme: Theme
    rating: Rating
    content_prefs: ContentPrefs
    world: Literal["grounded", "cultivation", "premise"]
    script: tuple[str, ...]
    expect: Expect
    requirements: tuple[str, ...]
    premise: str = ""
    setup: str = ""
    cast: tuple[Character, ...] = ()
    player: dict[str, Any] = field(default_factory=dict)
    interpretation: tuple[Intent, ...] = ()
    # S10: the language of the case's story, of its cast's descriptions and of its script.
    language: Language = Language.EN

    @property
    def deterministic(self) -> bool:
        return self.expect.limit is not None


def _case(data: dict[str, Any]) -> ContentLineCase:
    expect = dict(data["expect"])
    if expect.get("limit") is not None:
        expect["limit"] = LimitCategory(expect["limit"])
    for key in ("narration_mode", "must", "must_not"):
        expect[key] = tuple(expect.get(key, ()))
    return ContentLineCase(
        id=data["id"],
        title=data["title"],
        theme=data["theme"],
        rating=Rating(data["rating"]),
        content_prefs=ContentPrefs.model_validate(data["content_prefs"]),
        world=data["world"],
        script=tuple(data["script"]),
        expect=Expect(**expect),
        requirements=tuple(data["requirements"]),
        premise=data.get("premise", ""),
        setup=data.get("setup", ""),
        cast=tuple(Character.model_validate(c) for c in data.get("cast", ())),
        player=dict(data.get("player", {})),
        interpretation=tuple(Intent.model_validate(i) for i in data.get("interpretation", ())),
        language=Language(data.get("language", Language.EN)),
    )


@cache
def _load() -> tuple[dict[str, Any], tuple[ContentLineCase, ...]]:
    raw = json.loads(CASES_FILE.read_text())
    return raw["judge"], tuple(_case(case) for case in raw["cases"])


def load_cases() -> tuple[ContentLineCase, ...]:
    return _load()[1]


def judge_instructions() -> dict[str, str]:
    return dict(_load()[0])


def build_world(case: ContentLineCase) -> WorldState | None:
    """The case's starting world: a sample world with its extra cast and player changes, or
    None for a case whose world is drafted from `case.premise`."""
    if case.world == "premise":
        return None
    state = WORLDS[case.world]()
    for character in case.cast:
        state.characters[character.id] = character.model_copy(deep=True)
    if case.player:
        player = state.characters[state.player_id]
        state.characters[state.player_id] = player.model_copy(update=case.player)
    return state

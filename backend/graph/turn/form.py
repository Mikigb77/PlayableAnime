"""The forms the model steps fill for one turn (B5): the interpret step's, and the narrator's
where it asks more than its own (`narrator_form`).

The whole form is `engine.contracts.Intent`, and most turns can't use all of it. A character
with no power over time has nothing to say about what a throw weighs in stopped time, a world
with no ladder has no strength to hide, and a character with no talent to rule on has no case
to make. A question that can't apply is one more thing for the model to get wrong, and it pays
for reading it on every turn, so each turn's form asks only what can apply (`Asks`): the JSON
schema leaves the other fields out (`intent_form`) and so does the guide that explains them
(`prompts.interpret_system`). The answer is still read as an `Intent`, where a field the form
left out keeps its default.

Two fields are never asked, though the contract keeps them: who acts, since the player plays
only their own character (A6) and code sets the actor, and a stranger's crowd, which the step's
own facts say (`StepFacts.crowd`).
"""

import json
from dataclasses import dataclass, fields
from functools import lru_cache
from typing import Any

from engine.contracts import Intent
from engine.contracts.intent import GrowthKind
from graph.turn.outputs import NarratorOutput


@dataclass(frozen=True)
class Asks:
    """What a turn's form asks beyond what every turn's does."""

    # W10a: the character holds a power over time, or one is at work in the scene.
    time: bool = False
    # G18, G20: the world has a ladder to climb, and a strength on it to hide or to show.
    ladders: bool = False
    # A4: the character has talents to rule on (the prompt's TALENTS).
    talents: bool = False
    # N2: the character has a goal they could give up.
    goals: bool = False
    # W16, N1: a thread they know of or a lead is open to take up.
    threads: bool = False
    # W17, F3: the player character and someone else on record are adults, so a step can be
    # a move in a romance.
    romance: bool = False
    # W11: someone in the scene is about to get away and tell what they saw (SCENE's leaving).
    # It asks no field of its own: only the guide's word on it comes and goes.
    leaving: bool = False
    # W10: a trip stopped before its end (SCENE's on_the_way). No field of its own either.
    trip: bool = False


# Everything, as the contract has it: what the guide's tests read, and a form for any turn.
WHOLE = Asks(
    time=True,
    ladders=True,
    talents=True,
    goals=True,
    threads=True,
    romance=True,
    leaving=True,
    trip=True,
)

# The fields no turn's form asks, by the model that holds them.
_NEVER: dict[str, tuple[str, ...]] = {
    "Intent": ("actor_id",),
    "Stranger": ("crowd",),
}
# The fields asked only where they can apply, by what has to hold and the model that holds them.
_ONLY: dict[str, dict[str, tuple[str, ...]]] = {
    "time": {
        "IntentStep": ("contact", "mass_kg", "range_m", "full_force", "proposed_personal_s"),
        "Training": ("grants",),
        "PowerTheory": ("about", "claims_hit_mode"),
    },
    "ladders": {
        "IntentStep": ("show_strength",),
        "Training": ("ladder_id", "attempt", "risky"),
    },
    "talents": {"IntentStep": ("talent_cases", "bridge")},
    "goals": {"Intent": ("dropped_goals",)},
    "threads": {"Intent": ("responds_to",)},
    "romance": {"IntentStep": ("romance",)},
    "leaving": {},
    "trip": {},
}
assert set(_ONLY) == {f.name for f in fields(Asks)}


def left_out(asks: Asks) -> dict[str, tuple[str, ...]]:
    """The fields a turn's form leaves out, by the model that holds them."""
    out = {model: list(names) for model, names in _NEVER.items()}
    for needs, by_model in _ONLY.items():
        if getattr(asks, needs):
            continue
        for model, names in by_model.items():
            out.setdefault(model, []).extend(names)
    return {model: tuple(names) for model, names in out.items()}


def intent_form(asks: Asks) -> dict[str, Any]:
    """The JSON schema of the form for a turn that asks `asks`: `Intent`'s own, without the
    fields that can't apply and the definitions only they used. A fresh copy each call."""
    return json.loads(_form_text(asks))


@lru_cache(maxsize=64)
def _form_text(asks: Asks) -> str:
    schema = Intent.model_json_schema()
    defs: dict[str, Any] = schema.get("$defs", {})
    for model, names in left_out(asks).items():
        where = schema if model == schema.get("title") else defs[model]
        for name in names:
            # A field the contract renamed would otherwise be asked again with no one noticing.
            del where["properties"][name]
        if "required" in where:
            where["required"] = [r for r in where["required"] if r not in names]
    if not asks.ladders:
        # G19: with no ladder in the world there is no next rung to break through to.
        kinds = defs[GrowthKind.__name__]
        kinds["enum"] = [k for k in kinds["enum"] if k != GrowthKind.BREAKTHROUGH.value]
    schema["$defs"] = {name: defs[name] for name in defs if name in _used(schema, defs)}
    return json.dumps(schema)


def _used(schema: dict[str, Any], defs: dict[str, Any]) -> set[str]:
    """The definitions the schema still reaches, through its own properties or another's."""
    found: set[str] = set()
    todo = [{key: value for key, value in schema.items() if key != "$defs"}]
    while todo:
        node = todo.pop()
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str):
                name = ref.rsplit("/", 1)[-1]
                if name not in found and name in defs:
                    found.add(name)
                    todo.append(defs[name])
            todo.extend(node.values())
        elif isinstance(node, list):
            todo.extend(node)
    return found


# --- The narrator's form (G18) ----------------------------------------------------------------


@dataclass(frozen=True)
class Above:
    """G18. A ladder the story can pass the top of this turn (`engine.path.top_problem`), which
    the narrator's form asks about: its id, its name and the name of its highest rung."""

    ladder_id: str
    ladder: str
    top: str


# G18, G7. What the narrator's form asks first while a ladder is open above its top. The scene's
# own words have to name a rung above the top for the ladder to gain it, and the narrator
# writes its scene before its update, so a question that comes after the scene is too late: in
# the first stories on the real models no scene ever named one, with the ladder open and beings
# from above it in the scene. And Gemini answers only what a form requires (`Intent`). So the
# question comes first and is required, empty in any other scene.
RUNG_ABOVE = (
    "G18: answer before the scene. {ladder} is open above {top}, its highest rung. When this "
    "scene brings in or shows someone or something stronger than {top}, or OUTCOME says the "
    "character finds what lies beyond it, the name this scene gives the rung above {top}: a "
    "new name of this world's making, never a rung WORLD lists, a stage or a title. The scene "
    "then says that name, and whoever this update brings in who stands on that rung has it as "
    "their rung. Empty in any other scene."
)


def narrator_form(above: Above | None) -> dict[str, Any] | None:
    """The JSON schema of the narrator's form for a turn, or None for `NarratorOutput`'s own.
    While the story can pass a ladder's top (`above`), the form asks first what the scene calls
    the rung above it (`NarratorOutput.rung_above`). A fresh copy each call."""
    return None if above is None else json.loads(_narrator_text(above))


@lru_cache(maxsize=64)
def _narrator_text(above: Above) -> str:
    schema = NarratorOutput.model_json_schema()
    asked = {
        "type": "string",
        # What the offline model answers: nothing.
        "default": "",
        "description": RUNG_ABOVE.format(ladder=above.ladder, top=above.top),
    }
    schema["properties"] = {"rung_above": asked, **schema["properties"]}
    schema["required"] = ["rung_above", *schema.get("required", [])]
    return json.dumps(schema)

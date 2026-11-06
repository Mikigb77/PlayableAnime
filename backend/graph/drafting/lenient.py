"""Reading the drafter's answer leniently (G1, G2), so one odd value never costs a whole draft.

Gemini refuses the draft's schema as a response schema, so it goes in the prompt instead
(`graph.llm.gemini`), and then nothing holds the model to it. From 2026-11-05 most drafts failed
validation on both tries and the player saw "The storyteller is unavailable". So a value in the
model's answer that doesn't validate is repaired, field by field, as `schema.Proposal` reads it:

1. Where its meaning is clear, it is fitted to its field (`fit`): a null takes the field's
   default, a lone value becomes a one-item list, a list's nulls are dropped, a map of records
   keyed by id or name becomes a list of them, a map of names by role becomes the list of the
   names, a name stands for a record that needs only a name, a reference written as a record or
   a list becomes its (first) id, a number becomes text or a whole number, and an enum is read
   without regard to case, spaces or hyphens.
2. What still fails costs only itself: a list keeps the items that validate, and a field with a
   default takes it. A required field that fails still fails its record, and a record in a list
   is then dropped on its own.

Only the model's answer is read this way: the client reads it with the `MODEL_OUTPUT` context
(`graph.llm.types`), and a proposal that code builds stays strict, so a bug there still fails
loudly. Each repair is noted in the context as the record's type, the field, the repair and the
kinds of error, never a value (T6), and the client logs them once per answer. Code checks the rest
when it assembles the world (`graph.drafting.assemble`).
"""

from __future__ import annotations

import math
import types
from enum import Enum
from typing import Any, Literal, Union, get_args, get_origin

from pydantic import BaseModel, ValidationError, ValidationInfo, ValidatorFunctionWrapHandler

from graph.llm.types import MODEL_OUTPUT, REPAIRS

# The keys a record written where its id belongs is read by, in order.
REFERENCE_KEYS = ("id", "name")


def model_output() -> dict[str, Any]:
    """A validation context for reading a model's answer, as the client reads it."""
    return {MODEL_OUTPUT: True, REPAIRS: []}


def reading_model_output(info: ValidationInfo) -> bool:
    return isinstance(info.context, dict) and bool(info.context.get(MODEL_OUTPUT))


def repair(
    model: type[BaseModel],
    info: ValidationInfo,
    value: Any,
    handler: ValidatorFunctionWrapHandler,
    error: ValidationError,
) -> Any:
    """The value of the field `info` names that `handler` takes, made from a `value` that failed
    with `error`, or `error` again when nothing usable is left."""
    name = info.field_name
    assert name is not None
    field = model.model_fields[name]
    if value is None and not field.is_required():
        _note(info, model, name, "null", error)
        return field.get_default(call_default_factory=True)
    fitted = fit(field.annotation, value, reference=_is_reference(name))
    if get_origin(field.annotation) is list and isinstance(fitted, list):
        # Each item on its own, once: a whole-list try first would validate the good ones twice.
        kept: list[Any] = []
        for item in fitted:
            try:
                kept.extend(handler([item]))
            except ValidationError:
                continue
        dropped = len(fitted) - len(kept)
        _note(info, model, name, f"dropped {dropped}" if dropped else "fitted", error)
        return kept
    if fitted is not value:
        try:
            result = handler(fitted)
        except ValidationError:
            pass
        else:
            _note(info, model, name, "fitted", error)
            return result
    if not field.is_required():
        _note(info, model, name, "default", error)
        return field.get_default(call_default_factory=True)
    raise error


def fit(annotation: Any, value: Any, *, reference: bool = False) -> Any:
    """`value` reshaped for `annotation` where its meaning is clear, else `value` itself.
    `reference` says the text is an id, such as `kind_id`."""
    origin = get_origin(annotation)
    if origin is Union or origin is types.UnionType:
        options = [arg for arg in get_args(annotation) if arg is not types.NoneType]
        if value is None or len(options) != 1:
            return value
        return fit(options[0], value, reference=reference)
    if origin is list:
        return _fit_list(get_args(annotation)[0], value, reference=reference)
    if origin is Literal:
        return _choice(get_args(annotation), value)
    if annotation is str:
        return _fit_text(value, reference=reference)
    if annotation is int:
        return _fit_whole(value)
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return _choice(tuple(member.value for member in annotation), value)
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return _fit_record(annotation, value)
    return value


def _is_reference(name: str) -> bool:
    return name == "id" or name.endswith(("_id", "_ids"))


def _fit_list(item: Any, value: Any, *, reference: bool) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, dict):
        value = _from_map(item, value)
    elif not isinstance(value, list):
        value = [value]
    return [fit(item, entry, reference=reference) for entry in value if entry is not None]


def _from_map(item: Any, value: dict[Any, Any]) -> list[Any]:
    """A map where a list belongs: records keyed by id or name ({"rosa": {...}},
    {"swordsmanship": "skilled"}), or names keyed by role ({"mother": "rosa"}). Anything else,
    such as one reference written as a record ({"id": "rosa", "role": "mother"}), is one item."""
    entries = list(value.values())
    if item is str:
        if not any(key in value for key in REFERENCE_KEYS) and all(
            isinstance(entry, str | None) for entry in entries
        ):
            return [entry for entry in entries if entry]
        return [value]
    if not (isinstance(item, type) and issubclass(item, BaseModel)) or not entries:
        return [value]
    if all(isinstance(entry, dict) for entry in entries):
        key_field = "id" if "id" in item.model_fields else _only_required_text(item)
        if key_field is not None:
            return [
                {**entry, key_field: entry.get(key_field) or key} for key, entry in value.items()
            ]
    # Records that need only a name, keyed by it, each with a word about it: the names are kept.
    only = _only_required_text(item)
    if only is not None and not any(isinstance(entry, dict | list) for entry in entries):
        return [{only: key} for key in value]
    return [value]


def _fit_text(value: Any, *, reference: bool) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, list) and all(isinstance(entry, str) for entry in value):
        parts = [entry.strip() for entry in value if entry.strip()]
        if not parts:
            return value
        if reference:
            return parts[0]
        sentences = all(part.endswith((".", "!", "?")) for part in parts)
        return (" " if sentences else ", ").join(parts)
    if isinstance(value, dict):
        for key in REFERENCE_KEYS:
            if isinstance(found := value.get(key), str):
                return found
    return value


def _fit_whole(value: Any) -> Any:
    if isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError:
            return value
    elif isinstance(value, float):
        number = value
    else:
        return value
    return math.floor(number + 0.5) if math.isfinite(number) else value  # halves round up


def _fit_record(model: type[BaseModel], value: Any) -> Any:
    if isinstance(value, str) and (only := _only_required_text(model)):
        return {only: value}
    if isinstance(value, list) and len(value) == 1 and isinstance(value[0], dict):
        return value[0]
    return value


def _only_required_text(model: type[BaseModel]) -> str | None:
    """The name of `model`'s one required field, when it is text: a skill's or an item's name."""
    required = [(name, field) for name, field in model.model_fields.items() if field.is_required()]
    if len(required) == 1 and required[0][1].annotation is str:
        return required[0][0]
    return None


def _choice(choices: tuple[Any, ...], value: Any) -> Any:
    if not isinstance(value, str):
        return value
    wanted = _token(value)
    for choice in choices:
        if isinstance(choice, str) and _token(choice) == wanted:
            return choice
    return value


def _token(text: str) -> str:
    return "_".join(text.strip().lower().replace("-", " ").split())


def _note(
    info: ValidationInfo, model: type[BaseModel], name: str, repair: str, error: ValidationError
) -> None:
    """Notes a repair as "NpcP.parent_ids: fitted (list_type)", never with a value (T6)."""
    repairs = info.context.get(REPAIRS) if isinstance(info.context, dict) else None
    if not isinstance(repairs, list):
        return
    details = error.errors(include_url=False, include_context=False, include_input=False)
    kinds = ", ".join(sorted({str(detail["type"]) for detail in details}))
    repairs.append(f"{model.__name__}.{name}: {repair} ({kinds})")

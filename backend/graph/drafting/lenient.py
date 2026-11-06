"""Reading the drafter's answer leniently (G1, G2), so one odd value never costs a whole draft.

Gemini refuses the draft's schema as a response schema, so it goes in the prompt instead
(`graph.llm.gemini`), and then nothing holds the model to it. From 2026-11-05 most drafts failed
validation on both tries and the player saw "The storyteller is unavailable". So a value that
doesn't validate is repaired, field by field, as `schema.Proposal` reads it:

1. Where its meaning is clear, it is fitted to its field (`fit`): a null takes the field's
   default, a lone value becomes a one-item list, a list's nulls are dropped, a map of records by
   id becomes a list with those ids, a map of names becomes the list of them, a name stands for a
   record that needs only a name, a reference written as a record becomes its id, a number
   becomes text or a whole number, and an enum is read without regard to case, spaces or hyphens.
2. What still fails costs only itself: a list keeps the items that validate, and a field with a
   default takes it. A required field that fails still fails its record, and a record in a list
   is then dropped on its own.

Every repair is logged with the record's type, the field and the kinds of error, never a value
(T6). Code checks the rest when it assembles the world (`graph.drafting.assemble`).
"""

from __future__ import annotations

import logging
import math
import types
from enum import Enum
from typing import Any, Literal, Union, get_args, get_origin

from pydantic import BaseModel, ValidationError, ValidatorFunctionWrapHandler

logger = logging.getLogger("graph.drafting")

# The keys a record written where its id belongs is read by, in order.
REFERENCE_KEYS = ("id", "name")


def repair(
    model: type[BaseModel],
    name: str,
    value: Any,
    handler: ValidatorFunctionWrapHandler,
    error: ValidationError,
) -> Any:
    """The value of `model`'s field `name` that `handler` takes, made from a `value` that failed
    with `error`, or `error` again when nothing usable is left."""
    field = model.model_fields[name]
    if value is None and not field.is_required():
        _log(model, name, "null", error)
        return field.get_default(call_default_factory=True)
    fitted = fit(field.annotation, value)
    if fitted is not value:
        try:
            result = handler(fitted)
        except ValidationError:
            pass
        else:
            _log(model, name, "fitted", error)
            return result
    if get_origin(field.annotation) is list and isinstance(fitted, list):
        kept: list[Any] = []
        for item in fitted:
            try:
                kept.extend(handler([item]))
            except ValidationError:
                continue
        _log(model, name, "dropped_items", error, dropped=len(fitted) - len(kept))
        return kept
    if not field.is_required():
        _log(model, name, "default", error)
        return field.get_default(call_default_factory=True)
    raise error


def fit(annotation: Any, value: Any) -> Any:
    """`value` reshaped for `annotation` where its meaning is clear, else `value` itself."""
    origin = get_origin(annotation)
    if origin is Union or origin is types.UnionType:
        options = [arg for arg in get_args(annotation) if arg is not types.NoneType]
        if value is None or len(options) != 1:
            return value
        return fit(options[0], value)
    if origin is list:
        return _fit_list(get_args(annotation)[0], value)
    if origin is Literal:
        return _choice(get_args(annotation), value)
    if annotation is str:
        return _fit_text(value)
    if annotation is int:
        return _fit_whole(value)
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return _choice(tuple(member.value for member in annotation), value)
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return _fit_record(annotation, value)
    return value


def _fit_list(item: Any, value: Any) -> Any:
    if value is None:
        return []
    if isinstance(value, dict):
        value = _from_map(item, value)
    elif not isinstance(value, list):
        value = [value]
    return [fit(item, entry) for entry in value if entry is not None]


def _from_map(item: Any, value: dict[Any, Any]) -> list[Any]:
    """A map where a list belongs: records keyed by id ({"rosa": {...}}), or names keyed by role
    ({"mother": "rosa"}). Anything else, such as one reference written as a record
    ({"id": "rosa", "role": "mother"}), is one item."""
    entries = list(value.values())
    if (
        item is str
        and not any(key in value for key in REFERENCE_KEYS)
        and all(isinstance(entry, str | None) for entry in entries)
    ):
        return [entry for entry in entries if entry]
    if (
        isinstance(item, type)
        and issubclass(item, BaseModel)
        and "id" in item.model_fields
        and entries
        and all(isinstance(entry, dict) for entry in entries)
    ):
        return [{**entry, "id": entry.get("id") or key} for key, entry in value.items()]
    return [value]


def _fit_text(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, list) and value and all(isinstance(entry, str) for entry in value):
        parts = [entry.strip() for entry in value if entry.strip()]
        sentences = all(part.endswith((".", "!", "?")) for part in parts)
        return (" " if sentences else ", ").join(parts)
    if isinstance(value, dict):
        for key in REFERENCE_KEYS:
            if isinstance(reference := value.get(key), str):
                return reference
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
    return round(number) if math.isfinite(number) else value


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


def _log(
    model: type[BaseModel], name: str, repair: str, error: ValidationError, **extra: int
) -> None:
    # A null for a field with a default is the commonest slip, and harmless.
    logger.log(
        logging.DEBUG if repair == "null" else logging.INFO,
        "Repaired the drafter's answer",
        extra={
            "proposal": {
                "record": model.__name__,
                "field": name,
                "repair": repair,
                "errors": sorted({str(detail["type"]) for detail in error.errors()}),
                **extra,
            }
        },
    )

"""`/v1/premises` and `/v1/drafts` (docs/API.md, G1, G2, S1, A1, S6, G7, G22).

A draft is drafted, revised and edited by `graph.drafting`, saved as inputs only, and shown through
`graph.drafting.view`, which writes the summary from the world's public parts. No response carries
the draft's hidden truth: mystery answers and clues, secrets, agendas, faction plans, a body's
forgotten past, or anyone the character doesn't know (N7, C6).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime
from typing import Annotated, Literal, Self

from asgiref.sync import sync_to_async
from ninja import Field, Router, Schema, Status
from pydantic import model_validator

from drafts import service
from drafts.models import Draft
from engine.context import (
    Difficulty,
    EventFrequency,
    ImageSetting,
    Language,
    NarrationLength,
    Rating,
)
from engine.state import GiftStrength, PhysicsMode, WorldState
from graph.drafting import chain
from graph.drafting.assemble import MAX, NAME_LIMIT, RULE_LIMIT, TEXT_LIMIT, TITLE_LIMIT, TONE_LIMIT
from graph.drafting.catalog import STARTER_PREMISES, starter
from graph.drafting.direct import Fields
from graph.drafting.prompts import current_rules
from graph.drafting.real_names import real_person_in
from graph.drafting.view import (
    CHARACTER_LINES,
    WORLD_LINES,
    Part,
    PartKind,
    character_parts,
    gift_strength,
    identity,
    kept,
    ladder_view,
    public_rules,
    public_text,
    world_parts,
)
from lucid import logs
from lucid.errors import field_error
from media.lookups import premise_cover_urls

logger = logging.getLogger("drafts")

premises_router = Router(tags=["premises"])
drafts_router = Router(tags=["drafts"])

MAX_LINES = 20
# What an edit may send is never less than what a draft may hold (`graph.drafting.assemble`):
# the app sends a text back with the player's change in it, and the whole list of rules with
# one of them changed, so a tighter limit here refuses an edit for words the drafter wrote.
# On 2026-11-07 six edits in a row were refused that way, each for a summary sent back whole.
MAX_RULES = MAX["rules"]
# A summary line the player rewrote. Lines sent back as they were read are no rewriting, and
# may be as long as the summary wrote them (`_refuse_long_lines`).
LINE_LIMIT = 300
Line = Annotated[str, Field(max_length=4000)]
# The plain fields (G1, G2): a title, a tone and a name, and a look or a manner.
Title = Annotated[str, Field(min_length=1, max_length=TITLE_LIMIT)]
Tone = Annotated[str, Field(min_length=1, max_length=TONE_LIMIT)]
Name = Annotated[str, Field(min_length=1, max_length=NAME_LIMIT)]
Long = Annotated[str, Field(min_length=1, max_length=TEXT_LIMIT)]


# Starter premises (S1).


class PremiseOut(Schema):
    id: str
    title: str
    genre: str
    tagline: str
    premise: str
    flagship: bool
    cover_url: str | None = None


@premises_router.get("", response=list[PremiseOut])
async def list_premises(request, language: Language = Language.EN) -> list[dict]:
    """Flagship genres first, then the rest (S1), in the app's language (S10), each with a fresh
    signed URL for its cover once the house has drawn one (`manage.py draw_premise_covers`)."""
    covers = await _cover_urls(request)
    return [premise.public(covers.get(premise.id), language) for premise in STARTER_PREMISES]


async def _cover_urls(request) -> dict[str, str]:
    """The covers' signed URLs, by premise id. Signing can call IAM, so it runs off the event
    loop. A cover is decoration: if the lookup or the signing fails, Discover shows the premises
    without covers, and the error is logged with its traceback for Error Reporting."""
    try:
        urls = await sync_to_async(premise_cover_urls)(
            [premise.id for premise in STARTER_PREMISES], request=request
        )
    except Exception:
        logger.exception("The premises' covers couldn't be looked up or signed")
        return {}
    return {premise_id: url.url for premise_id, url in urls.items()}


# Drafts.


class RuleIn(Schema):
    """A rule as the player set it. Without an id, it is a new rule."""

    id: str | None = Field(default=None, max_length=64)
    text: str = Field(min_length=1, max_length=RULE_LIMIT)
    fixed: bool = True


class AdvancedIn(Schema):
    """The advanced fields, hidden by default in the app (G1). Fields not sent stay as they are."""

    physics: PhysicsMode | None = None
    rules: list[RuleIn] | None = Field(default=None, max_length=MAX_RULES)
    gift_strength: GiftStrength | None = None
    difficulty: Difficulty | None = None
    event_frequency: EventFrequency | None = None


class CreateDraftIn(Schema):
    """`premise` may be left out when `premise_id` names a starter premise (S1)."""

    premise: str | None = Field(default=None, min_length=10, max_length=4000)
    premise_id: str | None = Field(default=None, max_length=64)
    rating: Rating
    advanced: AdvancedIn | None = None
    # S10: the app's language. The drafter writes in it, and the story starts in it.
    language: Language = Language.EN

    @model_validator(mode="after")
    def _premise_given(self) -> Self:
        if self.premise is None and self.premise_id is None:
            raise ValueError("Send a premise, or the id of a starter premise")
        return self


class CharacterIn(Schema):
    """The character's plain fields (G2), which code writes in at once, with no model call."""

    name: Name | None = None
    age: int | None = Field(default=None, ge=0, le=100_000)
    looks: Long | None = None
    manner: Long | None = None


class PatchDraftIn(Schema):
    """Direct edits (G1, G2). `expected_version` refuses an edit made on a stale copy (T10)."""

    title: Title | None = None
    tone: Tone | None = None
    character: CharacterIn | None = None
    world_lines: list[Line] | None = Field(default=None, max_length=MAX_LINES)
    character_lines: list[Line] | None = Field(default=None, max_length=MAX_LINES)
    advanced: AdvancedIn | None = None
    rating: Rating | None = None
    expected_version: int | None = None


class ReviseIn(Schema):
    """A change in plain words, such as "add hidden vampires" (G1, G2)."""

    target: Literal["world", "character"]
    instruction: str = Field(min_length=1, max_length=1000)
    # The part of the summary the player asked it at, so "more of this" says what "this" is.
    about: PartKind | None = None
    expected_version: int | None = None


class StartSettingsIn(Schema):
    """`StorySettings` (S6); fields not sent take the draft's choices, then the defaults."""

    narration_length: NarrationLength | None = None
    tone: str | None = Field(default=None, max_length=200)
    difficulty: Difficulty | None = None
    event_frequency: EventFrequency | None = None
    images: ImageSetting | None = None
    suggestions: bool | None = None
    # Not the language: the story starts in the draft's (S10).


class StartIn(Schema):
    settings: StartSettingsIn | None = None
    expected_version: int | None = None


class RuleOut(Schema):
    id: str
    text: str
    fixed: bool


class AdvancedOut(Schema):
    physics: PhysicsMode
    rules: list[RuleOut]
    gift_strength: GiftStrength
    difficulty: Difficulty
    event_frequency: EventFrequency


class PartOut(Schema):
    kind: PartKind
    text: str


class CharacterOut(Schema):
    name: str
    age: int | None
    people: str
    standing: str
    looks: str
    manner: str


class LadderOut(Schema):
    name: str
    rungs: list[str]
    more: bool
    at: int | None
    stage: str


class KeptOut(Schema):
    people: int
    events: int
    questions: int


class DraftOut(Schema):
    id: str
    premise: str
    premise_id: str | None
    rating: Rating
    language: Language
    title: str
    genre: str
    tone: str
    world_lines: list[str]
    character_lines: list[str]
    world_parts: list[PartOut]
    character_parts: list[PartOut]
    character: CharacterOut
    ladder: LadderOut | None
    kept: KeptOut
    advanced: AdvancedOut
    version: int
    story_id: str | None
    created_at: datetime
    updated_at: datetime


class StartOut(Schema):
    story_id: str
    version: int


def draft_out(row: Draft, state: WorldState | None = None) -> dict:
    """The `Draft` shape, from the state's public parts only (N7, C6), and of how the story
    starts only what the player's own words name (G1)."""
    draft = service.to_chain(row)
    state = state or draft.state()
    bible = state.bible
    # S10: the words code adds come in the draft's language.
    world = world_parts(state, draft.language, draft.said)
    character = character_parts(state, draft.language, draft.said)
    return {
        "id": str(row.id),
        "premise": row.premise,
        "premise_id": row.premise_id or None,
        "rating": row.rating,
        "language": row.language,
        "title": public_text(state, bible.title),
        "genre": public_text(state, bible.genre),
        "tone": public_text(state, bible.tone),
        "world_lines": _lines(world, WORLD_LINES),
        "character_lines": _lines(character, CHARACTER_LINES),
        "world_parts": [{"kind": part.kind.value, "text": part.text} for part in world],
        "character_parts": [{"kind": part.kind.value, "text": part.text} for part in character],
        "character": identity(state),
        "ladder": ladder_view(state, draft.language),
        "kept": kept(state, draft.language, draft.said),
        "advanced": {
            "physics": bible.physics.value,
            "rules": [{"id": r.id, "text": r.text, "fixed": r.fixed} for r in public_rules(state)],
            "gift_strength": gift_strength(state).value,
            "difficulty": row.difficulty,
            "event_frequency": row.event_frequency,
        },
        "version": row.version,
        "story_id": str(row.story_id) if row.story_id else None,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _lines(parts: list[Part], limit: int) -> list[str]:
    """The summary as plain lines, one screen of them, for an app that shows it as a list."""
    return [part.text for part in parts][:limit]


def _plain_fields(body: PatchDraftIn, state: WorldState) -> tuple[Fields, list[tuple[str, str]]]:
    """The plain fields the edit changes (G1, G2), and the player's own new texts among them,
    by field, for the real-person check (G12). A field sent back as it is changes nothing."""
    pc = state.player
    sent = body.character or CharacterIn()
    now = {
        "title": state.bible.title,
        "tone": state.bible.tone,
        "character.name": pc.name,
        "character.looks": pc.appearance,
        "character.manner": pc.description,
    }
    texts = {
        "title": body.title,
        "tone": body.tone,
        "character.name": sent.name,
        "character.looks": sent.looks,
        "character.manner": sent.manner,
    }
    new: dict[str, str] = {}
    for field, text in texts.items():
        if text is None:
            continue
        text = " ".join(text.split())
        if not text:
            raise field_error(field, "Write something here, or leave it as it is.", type="empty")
        if text != " ".join(now[field].split()):
            new[field] = text
    fields = Fields(
        title=new.get("title"),
        tone=new.get("tone"),
        name=new.get("character.name"),
        age=sent.age if sent.age != pc.age else None,
        looks=new.get("character.looks"),
        manner=new.get("character.manner"),
    )
    return fields, list(new.items())


def _settings(advanced: AdvancedIn | None) -> dict[str, str]:
    if advanced is None:
        return {}
    chosen = {"difficulty": advanced.difficulty, "event_frequency": advanced.event_frequency}
    return {name: value for name, value in chosen.items() if value is not None}


def _refuse_real_people(fields: Iterable[tuple[str, str]]) -> None:
    """G12: a premise, revision or edit that names a real living person is refused before any
    model call, at the field it is in. Real organisations are allowed, as a backdrop."""
    found = real_person_in(fields)
    if found is not None:
        raise field_error(found.field, found.message, type="real_person")


def _refuse_long_lines(rewritten: Iterable[tuple[str, str]]) -> None:
    """A summary line the player rewrote is at most `LINE_LIMIT` characters. A line sent back
    as the draft has it is never refused, however long the summary wrote it."""
    for field, text in rewritten:
        if len(text) > LINE_LIMIT:
            raise field_error(
                field, f"Keep a line to {LINE_LIMIT} characters.", type="string_too_long"
            )


def _new_texts(
    field: str, texts: list[str] | None, kept: Iterable[str] = (), leaf: str = ""
) -> list[tuple[str, str]]:
    """The player's own texts in a list field, by dotted path. A text already in the draft
    (`kept`) was written by the drafter, not the player, so only new ones are checked."""
    same = {" ".join(text.split()) for text in kept}
    return [
        (f"{field}.{i}{leaf}", text)
        for i, text in enumerate(texts or [])
        if " ".join(text.split()) not in same
    ]


def _rule_edits(advanced: AdvancedIn | None) -> list[chain.RuleEdit] | None:
    if advanced is None or advanced.rules is None:
        return None
    return [chain.RuleEdit(text=r.text, fixed=r.fixed, id=r.id) for r in advanced.rules]


@drafts_router.post("", response={201: DraftOut})
async def create_draft(request, body: CreateDraftIn):
    """The first draft of the world and the character from a premise (G1, G2, S1)."""
    found = None
    if body.premise_id is not None:
        found = starter(body.premise_id)
        if found is None:
            raise field_error("premise_id", "No starter premise has this id.", type="unknown")
    # A starter alone is drafted from its own words in the draft's language (S10).
    premise = body.premise if body.premise is not None else found.text(body.language).premise
    service.check_rating(request.auth, body.rating)
    advanced = body.advanced or AdvancedIn()
    rules = [r.text for r in advanced.rules or []]
    _refuse_real_people(
        [("premise", body.premise or ""), *_new_texts("advanced.rules", rules, leaf=".text")]
    )
    async with service.model_call(
        request, rating=body.rating, action="create", premise_id=body.premise_id
    ) as call:
        draft = await chain.create(
            call.client,
            premise,
            rating=body.rating,
            premise_id=body.premise_id,
            physics=advanced.physics or PhysicsMode.FUN_FIRST,
            gift=advanced.gift_strength,
            rules=_rule_edits(advanced),
            language=body.language,
        )
        row = await service.create_row(
            request.auth,
            draft,
            call,
            difficulty=advanced.difficulty or Difficulty.BALANCED,
            event_frequency=advanced.event_frequency or EventFrequency.NORMAL,
        )
    logs.bind(draft_id=str(row.id))
    return Status(201, draft_out(row, draft.state()))


@drafts_router.get("/{draft_id}", response=DraftOut)
async def get_draft(request, draft_id: str):
    row = await service.owned_draft(request, draft_id)
    return draft_out(row)


@drafts_router.patch("/{draft_id}", response=DraftOut)
async def edit_draft(request, draft_id: str, body: PatchDraftIn):
    """Direct edits (G1, G2, G7, G22, A9, S6): the plain fields, the summary lines and the
    advanced fields. Only the edits that need the world or the character redrafted call the
    model: a new title, tone, name, age, look or manner never does."""
    row = await service.owned_draft(request, draft_id)
    service.refuse_started(row)
    service.check_version(row, body.expected_version)
    if body.rating is not None:
        service.check_rating(request.auth, body.rating)
    advanced = body.advanced or AdvancedIn()
    current = service.to_chain(row)
    state = current.state()
    fields, own = _plain_fields(body, state)
    world = _lines(world_parts(state, current.language, current.said), WORLD_LINES)
    character = _lines(character_parts(state, current.language, current.said), CHARACTER_LINES)
    rewritten = [
        *_new_texts("world_lines", body.world_lines, world),
        *_new_texts("character_lines", body.character_lines, character),
    ]
    _refuse_long_lines(rewritten)
    _refuse_real_people(
        [
            *own,
            *rewritten,
            *_new_texts(
                "advanced.rules",
                [r.text for r in advanced.rules or []],
                [r.text for r in current_rules(state)],
                leaf=".text",
            ),
        ]
    )
    plan = chain.plan_edit(
        current,
        chain.Edits(
            world_lines=body.world_lines,
            character_lines=body.character_lines,
            rules=_rule_edits(advanced),
            physics=advanced.physics,
            gift=advanced.gift_strength,
            rating=body.rating,
            fields=fields or None,
        ),
    )
    settings = _settings(advanced)
    if not plan.needs_model:
        row = await service.save_row(row, plan.draft, **settings)
        return draft_out(row, plan.draft.state())
    draft = plan.draft
    async with service.model_call(
        request, rating=draft.rating, action="edit", premise_id=draft.premise_id
    ) as call:
        draft = await chain.finish_edit(call.client, plan)
        row = await service.save_row(row, draft, call, **settings)
    return draft_out(row, draft.state())


@drafts_router.post("/{draft_id}/revise", response=DraftOut)
async def revise_draft(request, draft_id: str, body: ReviseIn):
    """A change in plain words to the world or the character (G1, G2)."""
    row = await service.owned_draft(request, draft_id)
    service.refuse_started(row)
    service.check_version(row, body.expected_version)
    _refuse_real_people([("instruction", body.instruction)])
    draft = service.to_chain(row)
    about = chain.asked_at(draft, body.target, body.about)
    async with service.model_call(
        request, rating=draft.rating, action="revise", premise_id=draft.premise_id
    ) as call:
        draft = await chain.revise(
            call.client,
            draft,
            body.target,
            body.instruction,
            about,
            aim=chain.asks_an_aim(body.about),
        )
        row = await service.save_row(row, draft, call)
    return draft_out(row, draft.state())


@drafts_router.post("/{draft_id}/start", response=StartOut)
async def start_draft(request, draft_id: str, body: StartIn | None = None):
    """Creates the story with its opening world state (engine `graph`, turn 0). The app then
    asks for the opening scene (`kind: "opening"`). Starting again returns the same story, and a
    stale `expected_version` on a draft not yet started is refused (T10)."""
    row = await service.owned_draft(request, draft_id)
    settings = body.settings.model_dump(exclude_none=True) if body and body.settings else {}
    expected = body.expected_version if body else None
    story = await service.start_story(row.pk, settings, expected_version=expected)
    logs.bind(story_id=str(story.id))
    return {"story_id": str(story.id), "version": story.version}

"""Glue between the Django models and today's one-call narrator in `legacy/`.

The ported endpoints keep today's request and response shapes, so the current app works
unchanged, while stories live in the Django tables. WS3's turn graph replaces this module and the
`legacy` package together.
"""

import logging
import uuid

from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.http import HttpRequest
from django.utils import timezone

from legacy.domain import Choice, WorldState
from legacy.domain import Scene as LegacyScene
from legacy.domain import Story as LegacyStory
from lucid.errors import ApiError, ErrorCode, version_conflict
from stories.models import Engine, InputMode, Scene, SceneKind, Story

logger = logging.getLogger(__name__)


def to_legacy(story: Story, scenes: list[Scene]) -> LegacyStory:
    """The legacy narrator's view of a story and the scenes loaded for it, oldest first."""
    return LegacyStory(
        id=str(story.id),
        title=story.title,
        premise=story.premise,
        scenes=[
            LegacyScene(
                turn=scene.turn,
                player_action=scene.player_action,
                narration=scene.narration,
                choices=[Choice(id=c["id"], label=c["label"]) for c in scene.choices],
                image_prompt=scene.image_prompt,
                image_url=scene.image_url,
            )
            for scene in scenes
        ],
        state=WorldState.model_validate(story.state or {}),
    )


def _scene_row(
    story: Story, scene: LegacyScene, kind: SceneKind, input_mode: InputMode | None
) -> Scene:
    return Scene(
        story=story,
        turn=scene.turn,
        kind=kind,
        player_action=scene.player_action,
        input_mode=input_mode,
        narration=scene.narration,
        choices=[choice.model_dump(mode="json") for choice in scene.choices],
        image_prompt=scene.image_prompt,
        image_url=scene.image_url,
    )


@sync_to_async
def create_story(story_id: uuid.UUID, legacy: LegacyStory) -> Story:
    """Saves a new story with its opening scene, as version 1."""
    with transaction.atomic():
        story = Story.objects.create(
            id=story_id,
            title=legacy.title,
            premise=legacy.premise,
            engine=Engine.LEGACY,
            state=legacy.state.model_dump(mode="json"),
            turn=legacy.state.turn,
            version=1,
        )
        _scene_row(story, legacy.scenes[-1], SceneKind.OPENING, None).save(force_insert=True)
    return story


@sync_to_async
def save_turn(
    story: Story,
    advanced: LegacyStory,
    kind: SceneKind,
    input_mode: InputMode | None,
) -> int:
    """Saves the new state and scene only if no other turn was saved since `story` was read.

    Returns the new version. The losing turn of a race gets `version_conflict` (T10).
    """
    with transaction.atomic():
        updated = Story.objects.filter(pk=story.pk, version=story.version).update(
            state=advanced.state.model_dump(mode="json"),
            turn=advanced.state.turn,
            version=F("version") + 1,
            updated_at=timezone.now(),
        )
        if not updated:
            current = Story.objects.filter(pk=story.pk).values_list("version", flat=True).first()
            if current is None:
                raise ApiError(ErrorCode.NOT_FOUND, "Story not found.")
            raise version_conflict(current)
        row = _scene_row(story, advanced.scenes[-1], kind, input_mode)
        row.save(force_insert=True)
    return story.version + 1


def narrator_for(request: HttpRequest):
    """The legacy narrator for this request: the caller's own Gemini key when the BYOK headers
    are sent, otherwise the server's provider. The key is used for this request only and never
    stored or logged (S9, T6).

    Imported here, not at module load, to keep the model SDK out of cold starts (B10).
    """
    from legacy.config import Settings
    from legacy.engine.narrator import Narrator
    from legacy.llm.factory import UnsupportedProviderError, build_provider

    config = Settings(
        llm_provider=settings.LLM_PROVIDER,
        gcp_project=settings.GCP_PROJECT,
        vertex_location=settings.VERTEX_LOCATION,
        narrator_model=settings.NARRATOR_MODEL,
    )
    try:
        llm = build_provider(
            config,
            byok_provider=request.headers.get("X-LLM-Provider"),
            byok_key=request.headers.get("X-LLM-Api-Key"),
        )
    except UnsupportedProviderError as exc:
        raise ApiError(
            ErrorCode.VALIDATION_ERROR,
            str(exc),
            {
                "fields": [
                    {
                        "field": "X-LLM-Provider",
                        "source": "header",
                        "message": str(exc),
                        "type": "unsupported_provider",
                    }
                ]
            },
        ) from exc
    return Narrator(llm)


async def advance(
    request: HttpRequest, story: LegacyStory, action: str | None = None
) -> LegacyStory:
    """Runs one legacy turn and turns model failures into typed errors (T7)."""
    narrator = narrator_for(request)
    try:
        return await narrator.advance(story, action)
    except ApiError:
        raise
    except Exception as exc:
        if request.headers.get("X-LLM-Api-Key") and _is_rejected_key(exc):
            raise ApiError(ErrorCode.BAD_KEY, "Your API key was rejected.") from exc
        logger.exception("Narration failed")
        raise ApiError(ErrorCode.LLM_UNAVAILABLE) from exc


def _is_rejected_key(exc: Exception) -> bool:
    """Whether Gemini refused the caller's own key (google-genai's ClientError)."""
    code = getattr(exc, "code", None)
    if not type(exc).__module__.startswith("google."):
        return False
    return code in (401, 403) or (code == 400 and "api key" in str(exc).lower())

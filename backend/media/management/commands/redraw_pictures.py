"""Draws every story picture from an older house style again in the current one (S7, M4). The
house pays (T5 logged).

    uv run python manage.py redraw_pictures                  # every story's older pictures
    uv run python manage.py redraw_pictures STORY_ID ...     # only these stories
    uv run python manage.py redraw_pictures --dry-run        # what it would draw, and cost

It uses the configured picture model (`PICTURE_MODEL`, B6) and storage (`MEDIA_BUCKET`), and finds
nothing to do until `media.prompts.HOUSE_STYLE_VERSION` changes. On Cloud Run it runs on each
deploy as the migration job with other arguments (docs/DEPLOY.md, "Redrawing story pictures").
One run spends at most `--max-usd` and starts no drawing after `--minutes`; the next run draws
the rest. With the offline model (`LLM_PROVIDER=fake`) it draws plain placeholders, for local
development only.
"""

import argparse
import uuid
from collections import Counter
from decimal import Decimal, InvalidOperation

from asgiref.sync import async_to_sync
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from media import premise_covers, redraw
from media.prompts import HOUSE_STYLE_VERSION
from media.redraw import Outcome

# Roughly what one picture's prompt and references come to, for the dry run's estimate.
ESTIMATED_INPUT_TOKENS = 1500


class Command(BaseCommand):
    help = "Draws every story picture from an older house style again in the current one."

    def add_arguments(self, parser) -> None:
        parser.add_argument("story_ids", nargs="*", metavar="story_id", help="Only these stories.")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count what would be drawn and its estimated cost, without drawing.",
        )
        parser.add_argument(
            "--max-usd",
            type=_usd,
            default=redraw.MAX_USD,
            help=f"Spend at most this much in one run (default ${redraw.MAX_USD}).",
        )
        parser.add_argument(
            "--minutes",
            type=float,
            default=redraw.MINUTES,
            help=f"Start no drawing after this many minutes (default {redraw.MINUTES:g}).",
        )

    def handle(
        self,
        *args,
        story_ids: list[str],
        dry_run: bool,
        max_usd: Decimal,
        minutes: float,
        **options,
    ):
        offline = premise_covers.offline_model()
        if offline and settings.MEDIA_BUCKET:
            raise CommandError(
                "The offline model would put placeholder pictures in the Cloud Storage bucket. "
                "Set LLM_PROVIDER=vertex to draw real ones."
            )
        if not max_usd.is_finite() or max_usd <= 0 or not minutes > 0:
            raise CommandError("--max-usd and --minutes must be more than 0.")
        images = redraw.to_redraw(_story_ids(story_ids))
        if not images:
            self.stdout.write(
                f"Every story picture is in the current house style ({HOUSE_STYLE_VERSION})."
            )
            return
        model = premise_covers.picture_model_name()
        counts = Counter(image.kind for image in images)
        summary = ", ".join(f"{count} {kind}" for kind, count in sorted(counts.items()))
        if dry_run:
            estimate = len(images) * _estimate(model)
            self.stdout.write(
                f"Would draw {_pictures(len(images))} again ({summary}) in "
                f"{len({image.story_id for image in images})} {_stories(images)} with {model}, "
                f"about ${estimate:.2f}" + (" (placeholders, for free)." if offline else ".")
            )
            return

        self.stdout.write(f"Drawing {_pictures(len(images))} again ({summary}) with {model}.")
        # The drawing is async; its database work runs back on this thread (`sync_to_async`).
        run = async_to_sync(redraw.redraw_all)(
            images,
            offline=offline,
            max_usd=max_usd,
            minutes=minutes,
            report=lambda outcome: self.stdout.write(_line(outcome)),
        )
        drawn = [o for o in run.outcomes if o.status == "redrawn"]
        missed = [o for o in run.outcomes if o.status in ("failed", "blocked")]
        self.stdout.write(
            f"Drew {_pictures(len(drawn))} again with {model} for ${run.spent:.3f}, "
            "paid by the house."
        )
        if run.left:
            why = f"the ${max_usd} budget" if run.stopped_by == "budget" else "the time limit"
            self.stdout.write(
                f"Stopped at {why} with {_pictures(run.left)} left; the next run draws them."
            )
        if len(missed) == 1:
            raise CommandError(
                "1 picture wasn't drawn again and keeps its old drawing. Run the command again "
                "to try it once more."
            )
        if missed:
            raise CommandError(
                f"{len(missed)} pictures weren't drawn again and keep their old drawings. Run "
                "the command again to try them once more."
            )


def _usd(value: str) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation:
        raise argparse.ArgumentTypeError(f"{value!r} is not an amount in dollars") from None


def _story_ids(values: list[str]) -> list[uuid.UUID]:
    try:
        return [uuid.UUID(value) for value in values]
    except ValueError as exc:
        raise CommandError(f"{exc}: not a story id. Pass the ids of stories.") from None


def _line(outcome: Outcome) -> str:
    cost = f"${outcome.cost_usd:.3f}" if outcome.cost_usd is not None else "an unknown cost"
    picture = f"{outcome.kind} {outcome.image_id}"
    if outcome.status == "redrawn":
        return f"{picture}: drawn again with {outcome.model}, {cost}"
    if outcome.status == "kept":
        return f"{picture}: changed meanwhile, so the new drawing was dropped ({cost} spent)"
    if outcome.rate_limited:
        return f"{picture}: failed, out of picture quota after waiting ({cost} spent)"
    return f"{picture}: {outcome.status}, kept its old drawing ({cost} spent)"


def _estimate(model: str) -> Decimal:
    from graph.llm import estimate_cost
    from graph.llm.types import Usage

    cost, _ = estimate_cost(model, Usage(input_tokens=ESTIMATED_INPUT_TOKENS), images=1)
    return cost


def _pictures(count: int) -> str:
    return f"{count} picture" if count == 1 else f"{count} pictures"


def _stories(images) -> str:
    return "story" if len({image.story_id for image in images}) == 1 else "stories"

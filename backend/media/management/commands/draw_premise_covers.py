"""Draws each starter premise's cover once, for Discover (S1, M4, M8). The house pays (T5 logged).

    uv run python manage.py draw_premise_covers                     # every premise without one
    uv run python manage.py draw_premise_covers naples-vendetta --force   # draw one again
    uv run python manage.py draw_premise_covers --dry-run           # what it would draw, and cost

It uses the configured picture model (`PICTURE_MODEL`, B6) and storage (`MEDIA_BUCKET`). On Cloud
Run it runs as the migration job with other arguments (docs/DEPLOY.md, "Drawing the starter
covers"). With the offline model (`LLM_PROVIDER=fake`) it draws plain placeholders, for local
development only: a real model replaces them later without `--force`.
"""

from decimal import Decimal

from asgiref.sync import async_to_sync
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from graph.drafting.catalog import STARTER_PREMISES, starter
from media import premise_covers
from media.premise_covers import Outcome


class Command(BaseCommand):
    help = "Draws each starter premise's cover once with the configured picture model."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "premise_ids", nargs="*", metavar="premise_id", help="Only these premises."
        )
        parser.add_argument(
            "--force", action="store_true", help="Draw covers again even if they exist."
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List what would be drawn and its estimated cost, without drawing.",
        )

    def handle(self, *args, premise_ids: list[str], force: bool, dry_run: bool, **options):
        premises = _premises(premise_ids)
        offline = premise_covers.offline_model()
        if offline and settings.MEDIA_BUCKET:
            raise CommandError(
                "The offline model would put placeholder covers in the Cloud Storage bucket. "
                "Set LLM_PROVIDER=vertex to draw real ones."
            )
        todo, kept = premise_covers.to_draw(premises, force=force, offline=offline)
        for outcome in kept:
            self.stdout.write(_kept_line(outcome))
        model = premise_covers.picture_model_name()
        if not todo:
            self.stdout.write("Every cover is drawn. Pass --force to draw them again.")
            return
        if offline:
            self.stdout.write(
                "The offline model draws placeholders. Set LLM_PROVIDER=vertex for real covers."
            )
        if dry_run:
            for premise in todo:
                self.stdout.write(f"{premise.id}: would draw")
            if offline:
                self.stdout.write(f"Would draw {len(todo)} placeholder {_covers(len(todo))}.")
                return
            estimate = sum((_estimate(model, premise) for premise in todo), Decimal(0))
            self.stdout.write(
                f"Would draw {len(todo)} {_covers(len(todo))} with {model}, about ${estimate:.2f}."
            )
            return

        # The drawing is async; its database work runs back on this thread (`sync_to_async`).
        outcomes = async_to_sync(premise_covers.draw_covers)(
            todo,
            force=force,
            offline=offline,
            report=lambda outcome: self.stdout.write(_drawn_line(outcome)),
        )
        drawn = [o for o in outcomes if o.status == "drawn"]
        missed = [o for o in outcomes if o.status in ("failed", "blocked")]
        spent = sum((o.cost_usd or Decimal(0) for o in outcomes), Decimal(0))
        if offline:
            self.stdout.write(f"Drew {len(drawn)} placeholder {_covers(len(drawn))}, for free.")
        else:
            self.stdout.write(
                f"Drew {len(drawn)} {_covers(len(drawn))} with {model} for ${spent:.3f}, "
                "paid by the house."
            )
        if missed:
            ids = ", ".join(o.premise_id for o in missed)
            verb = "wasn't" if len(missed) == 1 else "weren't"
            raise CommandError(
                f"{len(missed)} {_covers(len(missed))} {verb} drawn ({ids}). Run the command "
                "again to try them once more."
            )


def _premises(premise_ids: list[str]):
    if not premise_ids:
        return list(STARTER_PREMISES)
    unknown = [premise_id for premise_id in premise_ids if starter(premise_id) is None]
    if unknown:
        known = ", ".join(premise.id for premise in STARTER_PREMISES)
        raise CommandError(f"No starter premise {', '.join(unknown)}. They are: {known}.")
    return [starter(premise_id) for premise_id in dict.fromkeys(premise_ids)]


def _kept_line(outcome: Outcome) -> str:
    line = f"{outcome.premise_id}: kept"
    if outcome.offline:
        return f"{line} (an offline placeholder)"
    if outcome.stale:
        return f"{line} (drawn from older premise text; pass --force to draw it again)"
    return line


def _drawn_line(outcome: Outcome) -> str:
    if outcome.status == "drawn" and outcome.offline:
        return f"{outcome.premise_id}: drawn (an offline placeholder)"
    cost = f"${outcome.cost_usd:.3f}" if outcome.cost_usd is not None else "an unknown cost"
    if outcome.status == "drawn":
        return f"{outcome.premise_id}: drawn with {outcome.model}, {cost}"
    if outcome.status == "kept":
        return f"{outcome.premise_id}: kept the cover another run drew meanwhile ({cost} spent)"
    if outcome.rate_limited:
        return f"{outcome.premise_id}: failed, out of picture quota after waiting ({cost} spent)"
    return f"{outcome.premise_id}: {outcome.status}, not drawn ({cost} spent)"


def _estimate(model: str, premise) -> Decimal:
    from graph.llm import estimate_cost
    from graph.llm.types import Usage

    request = premise_covers.cover_request(premise)
    tokens = (len(request.system) + len(request.prompt) + 3) // 4
    cost, _ = estimate_cost(model, Usage(input_tokens=tokens), images=1)
    return cost


def _covers(count: int) -> str:
    return "cover" if count == 1 else "covers"

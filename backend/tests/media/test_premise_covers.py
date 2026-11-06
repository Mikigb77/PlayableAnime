"""The starter premises' covers (S1, M4, M6, M8): drawn once by the house with
`manage.py draw_premise_covers`, and answered by `GET /v1/premises` with fresh signed URLs."""

import io
import json
import re
import time
from datetime import timedelta
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import pytest
from asgiref.sync import async_to_sync
from django.core.management import CommandError, call_command
from django.utils import timezone

from billing.models import LedgerEntry
from graph.drafting.catalog import STARTER_PREMISES, starter
from media import lookups, premise_covers
from media.drawing import DrawBlocked, DrawFailed, DrawRateLimited
from media.models import PremiseCover
from media.prompts import FRAMING, HOUSE_STYLE, MILD_RULES
from media.storage import get_storage
from tests.media.conftest import PNG

pytestmark = pytest.mark.django_db

IDS = [premise.id for premise in STARTER_PREMISES]


@pytest.fixture(autouse=True)
def real_model(monkeypatch):
    """The configured model is a real one unless a test says otherwise; `painters` stands in."""
    monkeypatch.setattr(premise_covers, "offline_model", lambda: False)


@pytest.fixture(autouse=True)
def waits(monkeypatch) -> list[float]:
    """The pauses the drawing takes, in seconds, recorded instead of slept."""
    waited: list[float] = []

    async def wait(seconds: float) -> None:
        waited.append(seconds)

    monkeypatch.setattr(premise_covers, "_wait", wait)
    return waited


def draw(*args) -> str:
    out = io.StringIO()
    call_command("draw_premise_covers", *args, stdout=out)
    return out.getvalue()


def stored(premise_id: str) -> bool:
    cover = PremiseCover.objects.filter(pk=premise_id).first()
    return cover is not None and get_storage().exists(cover.storage_key)


# Drawing.


def test_every_starter_gets_its_cover_once(painters):
    out = draw()

    assert sorted(PremiseCover.objects.values_list("premise_id", flat=True)) == sorted(IDS)
    assert all(stored(premise_id) for premise_id in IDS)
    assert len(painters.ours.requests) == len(IDS)
    # Every account sees Discover: drawn on our account under the Teen rating, never a BYOK key.
    assert painters.builds == [("ours", "teen")] * len(IDS)
    assert painters.ours.closed == len(IDS)
    assert f"Drew {len(IDS)} covers with" in out
    assert "paid by the house" in out

    again = draw()

    assert len(painters.ours.requests) == len(IDS)
    assert "Every cover is drawn" in again


def test_a_cover_is_drawn_in_the_house_style_with_room_for_the_title(painters):
    draw("outer-disciple")

    [request] = painters.ours.requests
    premise = starter("outer-disciple")
    assert (request.kind, request.aspect_ratio, request.references) == ("cover", "3:4", ())
    assert HOUSE_STYLE in request.system and MILD_RULES in request.system
    assert FRAMING["cover"] in request.prompt
    assert "lower third" in request.prompt
    assert premise.premise in request.prompt
    assert premise.genre in request.prompt and premise.tagline in request.prompt
    # The app sets the title over the cover; a picture has no text of its own (S7).
    assert premise.title not in request.prompt
    cover = PremiseCover.objects.get(pk="outer-disciple")
    assert cover.storage_key.startswith("premises/outer-disciple/")
    assert (cover.mime_type, cover.size_bytes, cover.model) == ("image/png", len(PNG), "fake-image")
    assert cover.cost_usd == Decimal("0.034")
    assert cover.offline is False
    assert get_storage().load(cover.storage_key) == PNG


def test_force_draws_a_cover_again_and_removes_the_old_file(
    painters, django_capture_on_commit_callbacks
):
    draw("naples-vendetta")
    first = PremiseCover.objects.get(pk="naples-vendetta")

    # The old file goes once the new cover is committed.
    with django_capture_on_commit_callbacks(execute=True):
        draw("naples-vendetta", "--force")

    second = PremiseCover.objects.get(pk="naples-vendetta")
    assert len(painters.ours.requests) == 2
    assert second.storage_key != first.storage_key
    assert get_storage().exists(second.storage_key)
    assert not get_storage().exists(first.storage_key)
    assert second.drawn_at >= first.drawn_at


def test_only_the_named_premises_are_drawn(painters):
    draw("night-shift", "kestrel-debt", "night-shift")

    assert set(PremiseCover.objects.values_list("premise_id", flat=True)) == {
        "night-shift",
        "kestrel-debt",
    }
    assert len(painters.ours.requests) == 2


def test_an_unknown_premise_draws_nothing(painters):
    with pytest.raises(CommandError, match="No starter premise no-such-world"):
        draw("night-shift", "no-such-world")

    assert painters.drawings == 0
    assert not PremiseCover.objects.exists()


def test_a_failed_or_blocked_cover_is_left_out_and_tried_on_the_next_run(painters, log_lines):
    painters.ours.script(DrawFailed("timeout"), DrawBlocked(("violence",)))

    with pytest.raises(CommandError, match=f"2 covers weren't drawn \\({IDS[0]}, {IDS[1]}\\)"):
        draw()

    assert not PremiseCover.objects.filter(pk__in=IDS[:2]).exists()
    assert PremiseCover.objects.count() == len(IDS) - 2
    skipped = [
        line["picture"] for line in log_lines() if line["message"] == "Premise cover skipped"
    ]
    assert [(p["premise_id"], p["skip_reason"]) for p in skipped] == [
        (IDS[0], "failed"),
        (IDS[1], "blocked"),
    ]
    assert skipped[1]["block_categories"] == ["violence"]

    draw()

    assert PremiseCover.objects.count() == len(IDS)
    assert len(painters.ours.requests) == len(IDS) + 2


def test_a_real_model_draws_the_covers_a_little_apart(painters, waits):
    """Our picture quota answers 429 after a few quick drawings, so they are spaced out."""
    draw()

    assert waits == [premise_covers.COVER_PAUSE_S] * (len(IDS) - 1)
    assert premise_covers.COVER_PAUSE_S > 0


def test_the_offline_model_draws_without_pausing(painters, waits, monkeypatch):
    monkeypatch.setattr(premise_covers, "offline_model", lambda: True)

    draw()

    assert PremiseCover.objects.count() == len(IDS)
    assert waits == []


def test_a_cover_out_of_quota_is_drawn_again_after_a_wait(painters, waits, log_lines):
    painters.ours.script(DrawRateLimited("llm_unavailable"))

    out = draw()

    assert PremiseCover.objects.count() == len(IDS)
    assert len(painters.ours.requests) == len(IDS) + 1
    assert [request.prompt for request in painters.ours.requests[:2]] == [
        premise_covers.cover_request(starter(IDS[0])).prompt
    ] * 2
    assert waits[0] == premise_covers.RATE_LIMIT_WAIT_S >= 60
    assert waits[1:] == [premise_covers.COVER_PAUSE_S] * (len(IDS) - 1)
    assert f"{IDS[0]}: drawn with" in out
    skipped = [
        line["picture"] for line in log_lines() if line["message"] == "Premise cover skipped"
    ]
    assert [(p["premise_id"], p["skip_reason"]) for p in skipped] == [(IDS[0], "rate_limited")]


def test_a_cover_still_out_of_quota_after_the_waits_is_left_for_the_next_run(painters, waits):
    retries = premise_covers.RATE_LIMIT_RETRIES
    painters.ours.script(*(DrawRateLimited("llm_unavailable") for _ in range(retries + 1)))

    with pytest.raises(CommandError, match=f"1 cover wasn't drawn \\({IDS[0]}\\)"):
        draw()

    assert not PremiseCover.objects.filter(pk=IDS[0]).exists()
    assert PremiseCover.objects.count() == len(IDS) - 1
    assert len(painters.ours.requests) == len(IDS) + retries
    assert waits[:retries] == [premise_covers.RATE_LIMIT_WAIT_S] * retries


def test_a_cover_that_fails_otherwise_is_not_drawn_again_in_the_same_run(painters, waits):
    painters.ours.script(DrawFailed("timeout"))

    with pytest.raises(CommandError, match=f"1 cover wasn't drawn \\({IDS[0]}\\)"):
        draw()

    assert len(painters.ours.requests) == len(IDS)
    assert premise_covers.RATE_LIMIT_WAIT_S not in waits


def test_the_house_pays_once_with_no_ledger_entry(painters, meter, log_lines):
    out = draw()

    # The house pays: the credit meter is never asked, and no player's ledger changes (K2, K7).
    assert (meter.started, meter.charged) == ([], [])
    assert not LedgerEntry.objects.exists()
    ready = [line["picture"] for line in log_lines() if line["message"] == "Premise cover ready"]
    assert [p["premise_id"] for p in ready] == IDS
    assert {(p["payer"], p["model"], p["cost_usd"], p["trigger"]) for p in ready} == {
        ("house", "fake-image", 0.034, "draw_premise_covers")
    }
    assert f"for ${Decimal('0.034') * len(IDS):.3f}" in out
    # Never a prompt in the logs (T6).
    logged = json.dumps(log_lines())
    assert all(premise.premise not in logged for premise in STARTER_PREMISES)


def test_a_dry_run_estimates_the_cost_and_draws_nothing(painters):
    draw("outer-disciple")

    out = draw("--dry-run")

    assert painters.drawings == 1
    assert "outer-disciple: kept" in out
    assert f"Would draw {len(IDS) - 1} covers with gemini-" in out
    # About $0.034 a cover (M7).
    estimate = Decimal(re.search(r"about \$(\d+\.\d\d)\.", out).group(1))
    assert Decimal("0.03") * (len(IDS) - 1) <= estimate <= Decimal("0.04") * (len(IDS) - 1)
    assert PremiseCover.objects.count() == 1


def test_a_cover_from_older_premise_text_is_kept_and_reported(painters):
    PremiseCover.objects.create(
        premise_id="hollowmere",
        storage_key="premises/hollowmere/old.png",
        mime_type="image/png",
        size_bytes=10,
        brief={"description": "An older premise."},
        drawn_at=timezone.now(),
    )

    out = draw("hollowmere")

    assert painters.drawings == 0
    assert "hollowmere: kept (drawn from older premise text; pass --force" in out


def test_a_cover_whose_brief_was_stored_before_a_field_was_added_is_not_stale(painters):
    """A field added to `Brief` since, such as who "you" is, doesn't make a cover look stale."""
    stored = premise_covers.cover_brief(starter("hollowmere")).to_json()
    del stored["you"], stored["time"]
    PremiseCover.objects.create(
        premise_id="hollowmere",
        storage_key="premises/hollowmere/old.png",
        mime_type="image/png",
        size_bytes=10,
        brief=stored,
        drawn_at=timezone.now(),
    )

    out = draw("hollowmere")

    assert "hollowmere: kept" in out and "older premise text" not in out


# The offline model (LLM_PROVIDER=fake), for local development.


def test_the_offline_model_never_puts_placeholders_in_the_bucket(settings, painters, monkeypatch):
    monkeypatch.setattr(premise_covers, "offline_model", lambda: True)
    settings.MEDIA_BUCKET = "playable-anime-pictures"

    with pytest.raises(CommandError, match="LLM_PROVIDER=vertex"):
        draw()

    assert painters.drawings == 0
    assert not PremiseCover.objects.exists()


def test_a_real_model_replaces_offline_placeholders_without_force(
    painters, monkeypatch, django_capture_on_commit_callbacks
):
    monkeypatch.setattr(premise_covers, "offline_model", lambda: True)
    out = draw("dead-god-courier")
    placeholder = PremiseCover.objects.get(pk="dead-god-courier")
    assert placeholder.offline is True
    assert "dead-god-courier: drawn (an offline placeholder)" in out
    assert "Drew 1 placeholder cover, for free." in out
    assert "dead-god-courier: kept (an offline placeholder)" in draw("dead-god-courier")

    monkeypatch.setattr(premise_covers, "offline_model", lambda: False)
    with django_capture_on_commit_callbacks(execute=True):
        draw("dead-god-courier")

    real = PremiseCover.objects.get(pk="dead-god-courier")
    assert real.offline is False
    assert not get_storage().exists(placeholder.storage_key)
    assert len(painters.ours.requests) == 2
    draw("dead-god-courier")
    assert len(painters.ours.requests) == 2


def test_another_runs_cover_wins_when_not_forced(painters, django_capture_on_commit_callbacks):
    """Two runs at once: the one that stores first keeps its cover, and the other drops its file."""
    draw("beast-tide")
    first = PremiseCover.objects.get(pk="beast-tide")

    # This run decided to draw before the first one stored its cover.
    with django_capture_on_commit_callbacks(execute=True):
        outcome = async_to_sync(premise_covers.draw_cover)(
            starter("beast-tide"), force=False, offline=False
        )

    assert outcome.status == "kept"
    assert PremiseCover.objects.get(pk="beast-tide").storage_key == first.storage_key
    files = list(get_storage().root.glob("premises/beast-tide/*"))
    assert [path.name for path in files] == [first.storage_key.rsplit("/", 1)[1]]


def test_deleting_a_cover_in_the_admin_removes_its_file(
    painters, django_capture_on_commit_callbacks
):
    draw("ashen-squire")
    cover = PremiseCover.objects.get(pk="ashen-squire")

    with django_capture_on_commit_callbacks(execute=True):
        cover.delete()

    assert not get_storage().exists(cover.storage_key)


# GET /v1/premises.


def test_premises_answer_a_fresh_signed_url_for_each_drawn_cover(player_client, painters):
    draw("outer-disciple", "naples-vendetta")

    premises = {p["id"]: p for p in player_client.get("/v1/premises").json()}

    covered = {pid for pid, premise in premises.items() if premise["cover_url"]}
    assert covered == {"outer-disciple", "naples-vendetta"}
    url = premises["outer-disciple"]["cover_url"]
    assert url.startswith("http://testserver/media/premises/outer-disciple/")
    # Signed for longer than a story's pictures: the app fetches the premises once per session.
    expires = int(parse_qs(urlparse(url).query)["expires"][0])
    assert expires - time.time() > timedelta(hours=6).total_seconds()
    picture = player_client.get(url.removeprefix("http://testserver"))
    assert picture.status_code == 200
    assert b"".join(picture.streaming_content) == PNG


def test_premises_answer_without_covers_when_signing_fails(player_client, painters, monkeypatch):
    draw("outer-disciple")

    def broken(keys, ttl_s=None):
        raise RuntimeError("IAM is down")

    monkeypatch.setattr(lookups, "signed_urls", broken)
    response = player_client.get("/v1/premises")

    assert response.status_code == 200
    assert [p["cover_url"] for p in response.json()] == [None] * len(IDS)


# Edges found in review.


def test_a_model_that_cannot_be_built_fails_that_cover_not_the_run(painters, monkeypatch):
    from media import drawing

    real_build = drawing.build_picture_model
    calls = []

    def build(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise RuntimeError("no credentials")
        return real_build(**kwargs)

    monkeypatch.setattr(drawing, "build_picture_model", build)

    with pytest.raises(CommandError, match=f"1 cover wasn't drawn \\({IDS[0]}\\)"):
        draw()

    assert PremiseCover.objects.count() == len(IDS) - 1


def test_a_real_drawing_beats_a_placeholder_another_run_inserted_meanwhile(
    painters, monkeypatch, django_capture_on_commit_callbacks
):
    """Both runs found no cover. The offline run inserted first, so this run's lookup saw no row
    but its insert collides: it must then replace the placeholder, not drop its real drawing."""
    from django.db.models import QuerySet

    PremiseCover.objects.create(
        premise_id="kestrel-debt",
        storage_key="premises/kestrel-debt/placeholder.png",
        mime_type="image/png",
        size_bytes=10,
        offline=True,
        drawn_at=timezone.now(),
    )
    real_first = QuerySet.first
    lookups = []

    def first(self):
        lookups.append(self.model)
        if len(lookups) == 1:
            return None  # the row wasn't committed yet when this run looked
        return real_first(self)

    monkeypatch.setattr(QuerySet, "first", first)
    with django_capture_on_commit_callbacks(execute=True):
        outcome = async_to_sync(premise_covers.draw_cover)(
            starter("kestrel-debt"), force=False, offline=False
        )

    cover = PremiseCover.objects.get(pk="kestrel-debt")
    assert lookups[:2] == [PremiseCover, PremiseCover]
    assert outcome.status == "drawn"
    assert cover.offline is False
    assert cover.storage_key != "premises/kestrel-debt/placeholder.png"
    assert get_storage().exists(cover.storage_key)


def test_a_dry_run_with_the_offline_model_promises_placeholders_not_a_price(
    painters, monkeypatch, settings
):
    monkeypatch.setattr(premise_covers, "offline_model", lambda: True)

    out = draw("--dry-run")

    assert f"Would draw {len(IDS)} placeholder covers." in out
    assert "$" not in out
    settings.MEDIA_BUCKET = "playable-anime-pictures"
    with pytest.raises(CommandError, match="LLM_PROVIDER=vertex"):
        draw("--dry-run")
    assert painters.drawings == 0


def test_covers_never_expire_sooner_than_story_pictures(player_client, painters, settings):
    draw("outer-disciple")
    settings.PICTURE_URL_TTL_S = 48 * 3600

    url = player_client.get("/v1/premises").json()[0]["cover_url"]

    expires = int(parse_qs(urlparse(url).query)["expires"][0])
    assert expires - time.time() > timedelta(hours=47).total_seconds()


def test_a_failed_cover_lookup_is_logged_as_an_error(
    player_client, painters, monkeypatch, log_lines
):
    def broken(*args, **kwargs):
        raise RuntimeError("relation media_premisecover does not exist")

    monkeypatch.setattr("drafts.api.premise_cover_urls", broken)
    response = player_client.get("/v1/premises")

    assert response.status_code == 200
    assert [p["cover_url"] for p in response.json()] == [None] * len(IDS)
    # Discover still works, and nothing hides the failure from Error Reporting.
    errors = [line for line in log_lines() if line["severity"] == "ERROR"]
    assert [line["message"] for line in errors] == [
        "The premises' covers couldn't be looked up or signed"
    ]

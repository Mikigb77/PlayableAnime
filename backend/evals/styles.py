"""The same scene drawn in each candidate house style, side by side, so Miki can pick the look
(S7; Miki, 2026-11-08: "draw exactly the same scene ... by trying different approaches to see
what's the style that I would prefer").

    uv run python -m evals styles --out evals-out
    uv run python -m evals styles --out evals-out --scene well-at-dusk --style current

Each picture goes through the product's own prompt builder, rules and picture model, with only the
house style swapped (`media.prompts.HOUSE_STYLE`), so a candidate looks as it would in play. Every
candidate stays grown-up (S7), and keeps the composition the app needs: the focal point high, a
calm, darker bottom edge that fades into the page, no border and no writing. The scenes come from
the evals' sample stories, with each person's kept look and age, and are drawn without reference
portraits, so no picture in an older style pulls a candidate back toward it.

Nothing here changes the house style: the one Miki picks goes into `media.prompts` in its own PR,
with `HOUSE_STYLE_VERSION` moved on. Live only, run by hand from the Evals workflow (`styles`).
The results are each picture under `styles/<scene>/`, `styles.json` with each picture's style,
model, cost and status, and `summary.md`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path

from engine.base import HOUR
from engine.samples import grounded_world
from engine.state.world import WorldState
from evals import worlds
from evals.pictures import scene_brief
from media.drawing import (
    DrawBlocked,
    DrawError,
    DrawRateLimited,
    DrawRequest,
    PictureModel,
)
from media.prompts import HOUSE_STYLE, PicturePrompt, build_prompt

logger = logging.getLogger("evals.styles")

# Where today's house style turns from the look to the composition the app needs (app/DESIGN.md,
# "Pictures"), which every candidate keeps.
COMPOSITION_STARTS = "A clear focal point"

# What every candidate keeps from today's house style: made for teens and adults, never a
# children's storybook (S7). Unlike today's style it allows anime eyes, which some candidates are.
GROWN_UP = (
    "Made for teen and adult readers, serious and true to each person's age: nothing cute, "
    "whimsical or childish, no chibi or cartoon proportions, no baby faces on grown-ups, no bright "
    "candy or pastel colours, and no storybook or fairy-tale look."
)


def composition() -> str:
    """The composition the app needs, as today's house style words it."""
    start = HOUSE_STYLE.find(COMPOSITION_STARTS)
    if start < 0:
        raise ValueError(f"The house style no longer says {COMPOSITION_STARTS!r}")
    return HOUSE_STYLE[start:]


@dataclass(frozen=True)
class Style:
    id: str
    name: str
    # How it looks, before what every candidate keeps; empty for today's house style.
    look: str = ""

    def text(self) -> str:
        """The house style a picture in this style is drawn with."""
        if not self.look:
            return HOUSE_STYLE
        return f"{self.look} {GROWN_UP} {composition()}"


STYLES: tuple[Style, ...] = (
    Style("current", "Today's house style: adult anime film or graphic novel"),
    Style(
        "anime-film",
        "Modern anime feature film",
        "A frame from a modern prestige anime feature film made for adults: clean, precise line "
        "art and crisp two-tone cel shading on the people, set against lush, richly detailed "
        "hand-painted backgrounds. Grown-up anime character design with realistic proportions, "
        "slim, defined faces that show each person's age, and expressive eyes that are never "
        "oversized. Cinematic camera work and luminous, atmospheric light with glowing "
        "highlights and shafts of light, on a deep, rich palette.",
    ),
    Style(
        "retro-anime",
        "1990s hand-drawn anime",
        "A frame from a hand-drawn anime film of the late 1980s or 1990s made for adults: "
        "hand-inked cels with slightly uneven line weight, flat cel colours with hard-edged "
        "shadow shapes, airbrushed hand-painted backgrounds, sharp, angular faces with defined "
        "cheekbones and realistic proportions, dramatic backlight and long shadows, a faded, "
        "muted analogue palette and a little film grain.",
    ),
    Style(
        "seinen-manga",
        "Black-and-white seinen manga",
        "A panel from a seinen manga for adult readers, inked by hand: black ink on off-white "
        "paper, bold brush strokes and fine pen lines, dense cross-hatching and screentone for "
        "shadow, realistic anatomy and finely detailed faces, motion lines only where the moment "
        "moves. Black and white, apart from one restrained spot colour on a single key element.",
    ),
    Style(
        "painterly-anime",
        "Semi-realistic painted anime",
        "A semi-realistic painted anime illustration, like the key visual of a mature fantasy "
        "series: anime-influenced faces with realistic bone structure and proportions, rendered "
        "in soft, detailed digital painting rather than flat cels, rich textures, volumetric "
        "light, rim light and a subtle glow, cinematic depth of field, and a refined palette of "
        "deep, desaturated tones lifted by warm light.",
    ),
    Style(
        "painted-realism",
        "Painted realism, like film concept art",
        "A realistic digital oil painting, like a film's concept art or a classical history "
        "painting: true-to-life anatomy and faces, visible, confident brushstrokes with rich "
        "texture, chiaroscuro light with deep shadows, an earthy, muted palette, and a grand, "
        "cinematic composition.",
    ),
    Style(
        "noir-graphic-novel",
        "Noir graphic novel",
        "A panel from a hard-boiled noir graphic novel for adults: stark chiaroscuro with large "
        "areas of solid black ink and sharp, graphic shapes of light, bold, confident ink lines, "
        "simplified but realistic, angular faces, and a limited palette of black, off-white and "
        "one saturated accent colour.",
    ),
    Style(
        "ink-wash",
        "Ink wash and watercolour",
        "An East Asian ink-wash painting blended with fine illustration: expressive brush-and-ink "
        "lines of varying weight, soft watercolour washes that bleed and granulate on textured "
        "paper, generous, atmospheric empty space, realistic grown-up faces drawn with restraint, "
        "and a muted palette of ink greys, ochres and indigos with a touch of vermilion.",
    ),
)


@dataclass(frozen=True)
class Scene:
    id: str
    title: str
    world: Callable[[], WorldState]
    # What the picture shows, as the picture note writes it from a finished scene (M5): what
    # each person is doing, exactly where, and the light.
    description: str
    # Who is in it besides the player character, as known characters of the world.
    people: tuple[str, ...]


def _well_at_dusk() -> WorldState:
    state = worlds.mage_fight()
    state.world_s = 11 * HOUR  # the sect's clock starts at 7: 18:00, dusk
    return state


SCENES: tuple[Scene, ...] = (
    Scene(
        "well-at-dusk",
        "Lin Feng (16) holds off the grey mage (60) at the outer-court well, at dusk",
        _well_at_dusk,
        "The grey mage drives forward across the flagstones of the outer-court well, sweeping "
        "his black staff at you as pale lightning crackles along it. You slide back on one knee "
        "beside the low stone well, one palm raised against him, a faint shimmer of qi "
        "gathering around your hand, your eyes locked on his. Dust kicks up around you both, lit "
        "by the last red light of dusk over the courtyard.",
        ("mage",),
    ),
    Scene(
        "back-booth",
        "Luca Esposito (24) faces Carmine Russo (54) in Carmine's bar, Naples 1974, at night",
        grounded_world,
        "In the back booth of Carmine's bar, under one low lamp in the cigarette smoke, you lean "
        "across the table at Carmine Russo, both hands flat on the wood, jaw clenched. Carmine "
        "sits back against the worn red leather, smiling, a small glass in his ringed hand, his "
        "eyes cold and watchful. The rest of the bar is dim behind you.",
        ("carmine",),
    ),
)


def scene_prompt(scene: Scene) -> PicturePrompt:
    """The scene's picture in today's house style, as the picture endpoint asks for it."""
    brief = scene_brief(scene.world(), scene.description, people=scene.people)
    return build_prompt("scene", brief)


def request(scene: Scene, style: Style, prompt: PicturePrompt | None = None) -> DrawRequest:
    """The scene's picture in `style`: its `prompt` with only the house style line swapped."""
    prompt = prompt or scene_prompt(scene)
    house = f"House style: {HOUSE_STYLE}"
    if house not in prompt.system:
        raise ValueError("The picture prompt no longer carries the house style as one line")
    return DrawRequest(
        kind="scene",
        system=prompt.system.replace(house, f"House style: {style.text()}"),
        prompt=prompt.user,
        aspect_ratio=prompt.aspect_ratio,
    )


@dataclass(frozen=True)
class Sample:
    scene: str
    style: str
    # "drawn", "blocked" or "failed", and "rate_limited" for an attempt a wait may fix.
    status: str
    file: str = ""
    model: str = ""
    cost_usd: Decimal = Decimal(0)


RATE_LIMITED = "rate_limited"
# Our picture quota answered 429 after three quick drawings (`media.premise_covers`), and refills
# within a minute: draw a little apart, and wait a minute before drawing one that ran out again.
PAUSE_S = 10.0
RATE_LIMIT_WAIT_S = 60.0
RATE_LIMIT_RETRIES = 3


async def draw_all(
    new_model: Callable[[], PictureModel],
    out: Path,
    scenes: Sequence[Scene] = SCENES,
    styles: Sequence[Style] = STYLES,
    *,
    wait: Callable[[float], Awaitable[None]] | None = None,
    say: Callable[[str], None] = print,
) -> list[Sample]:
    """Draws every scene in every style with a fresh model from `new_model`, so each picture's
    cost is its own, and writes them under `out/styles/<scene>/`, `PAUSE_S` apart. Pictures are
    drawn under one rating: their safety settings are the same in every rating (M6)."""
    wait = wait or asyncio.sleep
    # Every request first, so a house style this can no longer swap stops before any spending.
    planned = []
    for scene in scenes:
        prompt = scene_prompt(scene)
        for n, style in enumerate(styles, start=1):
            # Numbered as in the catalog, so a style's file is named the same in every run.
            number = STYLES.index(style) + 1 if style in STYLES else n
            planned.append((scene, style, number, request(scene, style, prompt)))
    samples = []
    for index, (scene, style, number, asked) in enumerate(planned):
        if index:
            await wait(PAUSE_S)
        spent = Decimal(0)
        for attempt in range(RATE_LIMIT_RETRIES + 1):
            if attempt:
                say(f"  quota ran out; drawing {style.id} again in {RATE_LIMIT_WAIT_S:.0f}s")
                await wait(RATE_LIMIT_WAIT_S)
            sample = await _draw(new_model, out, scene, style, number, asked)
            spent += sample.cost_usd
            if sample.status != RATE_LIMITED:
                break
        status = "failed" if sample.status == RATE_LIMITED else sample.status
        sample = replace(sample, status=status, cost_usd=spent)
        samples.append(sample)
        say(f"{sample.status:>7}  {scene.id} / {style.id} ${sample.cost_usd:.4f}")
    return samples


async def _draw(
    new_model: Callable[[], PictureModel],
    out: Path,
    scene: Scene,
    style: Style,
    number: int,
    asked: DrawRequest,
) -> Sample:
    """One picture. Whatever goes wrong loses that picture, never the others or the results."""
    model = None
    try:
        model = new_model()
        drawn = await model.draw(asked)
        name = f"{number:02d}-{style.id}{_extension(drawn.mime_type)}"
        path = Path("styles") / scene.id / name
        (out / path).parent.mkdir(parents=True, exist_ok=True)
        (out / path).write_bytes(drawn.data)
        return Sample(scene.id, style.id, "drawn", path.as_posix(), drawn.model, drawn.cost_usd)
    except Exception as error:
        status = (
            RATE_LIMITED
            if isinstance(error, DrawRateLimited)
            else "blocked"
            if isinstance(error, DrawBlocked)
            else "failed"
        )
        if not isinstance(error, DrawError):
            logger.exception("Drawing %s in %s failed", scene.id, style.id)
        return Sample(
            scene.id,
            style.id,
            status,
            model=getattr(model, "model", ""),
            cost_usd=_spent(model),
        )
    finally:
        if model is not None:
            await model.aclose()


def _spent(model: PictureModel | None) -> Decimal:
    """What a model's calls cost, so a picture blocked after it was drawn still counts (T5)."""
    calls = getattr(getattr(model, "telemetry", None), "calls", ())
    return sum((call.cost_usd for call in calls), Decimal(0))


def _extension(mime_type: str) -> str:
    return mimetypes.guess_extension(mime_type) or ".bin"


def write(
    samples: Sequence[Sample],
    out: Path,
    scenes: Sequence[Scene] = SCENES,
    styles: Sequence[Style] = STYLES,
) -> Decimal:
    """`styles.json` and `summary.md` next to the pictures. Returns what they all cost."""
    total = sum((s.cost_usd for s in samples), Decimal(0))
    models = sorted({s.model for s in samples if s.model})
    manifest = {
        "models": models,
        "total_cost_usd": str(total),
        "scenes": [{"id": s.id, "title": s.title, "description": s.description} for s in scenes],
        "styles": [{"id": s.id, "name": s.name, "text": s.text()} for s in styles],
        "pictures": [
            {
                "scene": s.scene,
                "style": s.style,
                "status": s.status,
                "file": s.file,
                "model": s.model,
                "cost_usd": str(s.cost_usd),
            }
            for s in samples
        ],
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "styles.json").write_text(json.dumps(manifest, indent=2) + "\n")
    names = {s.id: s.name for s in styles}
    drawn = sum(s.status == "drawn" for s in samples)
    lines = [
        "## House style candidates (S7)",
        "",
        f"{drawn} of {len(samples)} pictures drawn by {', '.join(models) or 'no model'}, "
        f"for ${total:.2f}.",
        "",
    ]
    for scene in scenes:
        lines += [f"### {scene.title}", "", "| Style | Status | Cost |", "| --- | --- | --- |"]
        for s in (s for s in samples if s.scene == scene.id):
            lines.append(f"| {names.get(s.style, s.style)} | {s.status} | ${s.cost_usd:.4f} |")
        lines.append("")
    (out / "summary.md").write_text("\n".join(lines))
    return total


def pick[T: (Scene, Style)](catalog: Sequence[T], ids: Sequence[str]) -> list[T]:
    """The entries `ids` names, in the catalog's order, or all of them when it names none."""
    unknown = set(ids) - {entry.id for entry in catalog}
    if unknown:
        raise ValueError(f"Unknown: {', '.join(sorted(unknown))}")
    return [entry for entry in catalog if not ids or entry.id in ids]

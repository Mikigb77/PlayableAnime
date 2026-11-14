"""A story played by hand, a few steps at a time, on the real models (T17's hand play).

A scenario is a script written ahead. This is for playing as a player does: read each scene,
then decide the next move from it. Miki, 2026-11-14: "play a couple of stories creating the
world yourself", to see how a short description of a character becomes their level, and how
seducing someone or dying of old age really plays. Each call plays the steps it is given on the
play kept in a folder, and appends to the folder's transcript what the player would see and,
under it, what the record holds. One call may play several plays, side by side:

    uv run python -m evals play --root plays --plays '{"farmer": [{"create": {"premise": "..."}}]}'
    uv run python -m evals play --root plays --plays '{"farmer": [{"start": {}}, {"act": "I ..."}]}'

The steps of a play, played in the order given:

    {"create": {"premise": "...", "language": "en", "rating": "teen"}}   a new world's draft
    {"revise": {"target": "character", "instruction": "..."}}            a change in plain words
    {"start": {}}                                                         the opening scene
    {"act": "..."}                                                        a typed action
    {"choose": 2}                                                         a suggestion, from 1
    {"wait": true}, {"observe": true}                                     the standing actions
    {"show": ["sheet", "memory", "record"]}                               the screens, the record
    {"copy": "farmer"}                                                    a new play from another

`create` also takes `premise_id` (a starter), `gift` (the strength picked on the create screen)
and `settings` (S6). `copy` starts a new play as another stands, its draft or its story on the
same seed, to try a different move from the same point. A play's folder, `<root>/<name>`, holds
`play.json`, the draft and the story's state between calls, and `transcript.md`. The Evals
workflow keeps the root on the `plays` branch, since its runs keep nothing else between them
(`.github/workflows/evals.yml`).

A play is made up, like an eval's stories: no player's data (T16). With the offline model
(`LLM_PROVIDER=fake`) it plays the stock draft and stock scenes, which is how its tests run.
"""

from __future__ import annotations

import asyncio
import copy
import dataclasses
import json
import re
import traceback
from collections.abc import Mapping, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any

from engine.base import DAY, HOUR, YEAR
from engine.context import Language, Rating, StorySettings
from engine.contracts import StandingAction
from engine.invariants import check_state
from engine.state import GiftStrength, WorldState
from engine.state.records import EventStatus
from engine.visibility import memory_view, status_view
from engine.world import last_years
from evals.runner import Eval, Models, Played, Story
from evals.scenario import LIVE_ONLY, Mode, Scenario
from graph.drafting import chain, view
from graph.drafting.schema import DraftProposal
from graph.llm import ModelClient, ModelConfig, TurnTelemetry
from graph.turn import PastScene, TurnKind

# A play's name is its folder and its branch, so it holds nothing a path or a ref could misread.
NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")
STATE_FILE = "play.json"
TRANSCRIPT_FILE = "transcript.md"
SHOWN = ("sheet", "memory", "record")
# How many of the world's people the record lists beside the character, the strongest first.
OTHERS_LISTED = 12
WAITING_LISTED = 40
# How many plays one call plays at once: each is a story's worth of model calls.
PLAYS_AT_ONCE = 4


class PlayError(ValueError):
    """A step that can't be played as given: the play is left as the step found it."""


async def _nothing(_ev: Eval) -> None:
    """A hand play has no script: whoever plays it decides each step."""


SCENARIO = Scenario(
    id="play",
    suite="T17",
    title="A story played by hand",
    requirements=("T17",),
    passes_when="Whoever plays it reads the transcript.",
    script=_nothing,
    modes=LIVE_ONLY,
)


@dataclasses.dataclass
class Play:
    """A hand-played story between calls: its draft until it starts, then its state and scenes."""

    folder: Path
    data: dict[str, Any]

    @classmethod
    def load(cls, folder: Path) -> Play:
        path = folder / STATE_FILE
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        return cls(folder, data)

    @property
    def name(self) -> str:
        return self.folder.name

    @property
    def language(self) -> Language:
        return Language(self.data.get("language", Language.EN.value))

    @property
    def rating(self) -> Rating:
        return Rating(self.data.get("rating", Rating.TEEN.value))

    def save(self) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        text = json.dumps(self.data, ensure_ascii=False, indent=1)
        (self.folder / STATE_FILE).write_text(text + "\n", encoding="utf-8")

    def tell(self, text: str) -> None:
        """Appends to the transcript, and prints it: a run's log is read too."""
        self.folder.mkdir(parents=True, exist_ok=True)
        with (self.folder / TRANSCRIPT_FILE).open("a", encoding="utf-8") as transcript:
            transcript.write(text.rstrip() + "\n\n")
        print(text.rstrip() + "\n", flush=True)

    # --- the draft ---

    def draft(self) -> chain.Draft:
        kept = self.data.get("draft")
        if kept is None:
            raise PlayError("This play has no draft yet: start with a create step.")
        return chain.Draft(
            premise=kept["premise"],
            proposal=DraftProposal.model_validate(kept["proposal"]),
            rating=kept["rating"],
            premise_id=kept["premise_id"],
            physics=chain.PhysicsMode(kept["physics"]),
            gift=GiftStrength(kept["gift"]) if kept["gift"] else None,
            released_rules=frozenset(kept["released_rules"]),
            language=Language(kept["language"]),
            told=frozenset(kept["told"]),
        )

    def keep_draft(self, draft: chain.Draft) -> None:
        self.data["draft"] = {
            "premise": draft.premise,
            "proposal": draft.proposal.model_dump(mode="json"),
            "rating": draft.rating,
            "premise_id": draft.premise_id,
            "physics": draft.physics.value,
            "gift": draft.gift.value if draft.gift is not None else None,
            "released_rules": sorted(draft.released_rules),
            "language": draft.language.value,
            "told": sorted(draft.told),
        }

    # --- the story ---

    def story(self, models: Models) -> Story:
        """The story where the last call left it, on the same seed, so its dice are its own."""
        if self.data.get("state") is None:
            raise PlayError("This play hasn't started: play a start step first.")
        ev = Eval(SCENARIO, Mode.LIVE, models)
        story = ev.story(
            WorldState.model_validate(self.data["state"]),
            seed=self.data["seed"],
            rating=self.rating,
            settings=StorySettings.model_validate(self.data["settings"]),
            premise=self.data["premise"],
            label=self.name,
            # The app plays whatever world a draft gave it, so a hand play does too, and says
            # what the record's own check found (`_record`).
            checked=False,
        )
        story.scenes = [PastScene(**scene) for scene in self.data.get("scenes", [])]
        return story

    def keep_story(self, story: Story, played: Played) -> None:
        self.data["state"] = story.state.model_dump(mode="json")
        self.data["scenes"] = [dataclasses.asdict(scene) for scene in story.scenes]
        if played.completed:
            self.data["choices"] = [choice.label for choice in played.scene.choices]
        spent = Decimal(str(self.data.get("cost_usd", 0))) + played.cost_usd
        self.data["cost_usd"] = float(spent)
        if played.result is not None and played.result.ending is not None:
            self.data["ended"] = dataclasses.asdict(played.result.ending)


# --- the steps -------------------------------------------------------------------------------


async def play_all(root: Path, plays: Mapping[str, Any], models: Models) -> dict[str, bool]:
    """Plays each play's steps, a few plays at a time, and says which played every step."""
    for name in plays:
        if not isinstance(name, str) or not NAME.fullmatch(name):
            raise PlayError(
                f"A play's name is small letters, digits and dashes, 40 at most: {name!r}"
            )
    for steps in plays.values():
        for step in steps if isinstance(steps, Sequence) and not isinstance(steps, str) else ():
            if isinstance(step, Mapping) and step.get("copy") in plays:
                # Plays run side by side, so the copy would be of wherever the other had got to.
                raise PlayError(
                    f"{step['copy']!r} is played in this call too: copy it in a call of its own."
                )
    at_once = asyncio.Semaphore(PLAYS_AT_ONCE)

    async def one(name: str, steps: Any) -> bool:
        async with at_once:
            return await play(root / name, steps, models)

    played = await asyncio.gather(*(one(name, steps) for name, steps in plays.items()))
    return dict(zip(plays, played, strict=True))


async def play(folder: Path, steps: Any, models: Models) -> bool:
    """Plays `steps` on the play in `folder`, keeping it after each one. False when a step
    failed: the play stays as that step found it, and the transcript says why."""
    play_ = Play.load(folder)
    if not isinstance(steps, Sequence) or isinstance(steps, str):
        play_.tell(f"## Not played\n\nA play's steps are a list: {json.dumps(steps)[:200]}")
        return False
    for number, step in enumerate(steps, start=1):
        try:
            if not isinstance(step, Mapping) or len(step) != 1:
                raise PlayError(
                    f"A step is one key and its value, such as {{'act': '...'}}: {step}"
                )
            ((kind, value),) = step.items()
            await _STEPS[kind](play_, value, models) if kind in _STEPS else _unknown(kind)
        except Exception as error:  # the transcript says what went wrong, whatever it was
            trace = "" if isinstance(error, PlayError) else f"\n\n```\n{_trace(error)}\n```"
            said = json.dumps(step, ensure_ascii=False, default=str)
            play_.tell(f"## Step {number} failed\n\n`{said}`\n\n{error!r}{trace}")
            return False
        play_.save()
    return True


def _unknown(kind: str) -> None:
    raise PlayError(f"No such step: {kind!r}. The steps are {', '.join(_STEPS)}.")


def _trace(error: BaseException) -> str:
    return "".join(traceback.format_exception(error))[-3000:]


def _drafter(models: Models, rating: str, telemetry: TurnTelemetry) -> ModelClient:
    """The real drafter, or offline the stock draft, as the app drafts with the offline model."""
    if models.backend is None and models.resolved().provider != "vertex":
        from graph.drafting.samples import offline_backend

        return ModelClient(offline_backend(grounded=False), ModelConfig(), rating=rating)
    return models.client(rating, telemetry)


async def _copy(play_: Play, given: Any, _models: Models) -> None:
    """This play becomes another as it stands, to try a different move from the same point."""
    if not isinstance(given, str) or not NAME.fullmatch(given):
        raise PlayError("copy takes the name of another play.")
    if play_.data:
        raise PlayError("This play already holds a story: a copy starts a new play.")
    source = Play.load(play_.folder.parent / given)
    if not source.data:
        raise PlayError(f"There is no play named {given!r} to copy.")
    play_.data = copy.deepcopy(source.data)
    scenes = len(play_.data.get("scenes", []))
    where = f"after {scenes} scenes" if play_.data.get("state") is not None else "as a draft"
    play_.tell(f"## Copied from `{given}`, {where}")


async def _create(play_: Play, given: Any, models: Models) -> None:
    if not isinstance(given, Mapping) or not str(given.get("premise", "")).strip():
        raise PlayError("create takes the premise as the player would type it.")
    if play_.data.get("state") is not None:
        raise PlayError("This play has already started: a new world is a new play.")
    language = Language(given.get("language", Language.EN.value))
    rating = Rating(given.get("rating", Rating.TEEN.value))
    gift = GiftStrength(given["gift"]) if given.get("gift") else None
    settings = StorySettings.model_validate(
        {"language": language} | dict(given.get("settings", {}))
    )
    telemetry = TurnTelemetry()
    draft = await chain.create(
        _drafter(models, rating.value, telemetry),
        str(given["premise"]),
        rating=rating.value,
        premise_id=given.get("premise_id") or None,
        gift=gift,
        language=language,
    )
    play_.data |= {
        "premise": draft.premise,
        "language": language.value,
        "rating": rating.value,
        "settings": settings.model_dump(mode="json"),
        "seed": f"play/{play_.name}",
        "state": None,
        "scenes": [],
        "choices": [],
        "cost_usd": float(telemetry.cost_usd),
    }
    play_.keep_draft(draft)
    play_.tell(_draft_told(draft, f"The draft ({language.value}, {rating.value})", telemetry))


async def _revise(play_: Play, given: Any, models: Models) -> None:
    if not isinstance(given, Mapping) or given.get("target") not in ("world", "character"):
        raise PlayError("revise takes a target, world or character, and an instruction.")
    if play_.data.get("state") is not None:
        raise PlayError("This play has already started: its draft can't change.")
    draft = play_.draft()
    telemetry = TurnTelemetry()
    instruction = str(given.get("instruction", ""))
    # The row of the draft's screen the change is asked at, as the app sends it.
    try:
        row = view.PartKind(given["about"]) if given.get("about") else None
    except ValueError:
        rows = ", ".join(kind.value for kind in view.PartKind)
        raise PlayError(f"about is a row of the draft: {rows}.") from None
    revised = await chain.revise(
        _drafter(models, draft.rating, telemetry),
        draft,
        given["target"],
        instruction,
        chain.asked_at(draft, given["target"], row),
        aim=chain.asks_an_aim(row),
    )
    spent = Decimal(str(play_.data.get("cost_usd", 0))) + telemetry.cost_usd
    play_.data["cost_usd"] = float(spent)
    play_.keep_draft(revised)
    where = (
        f"at the {row.value} row of the {given['target']}" if row else f"of the {given['target']}"
    )
    play_.tell(_draft_told(revised, f"The draft, after asking {where}: “{instruction}”", telemetry))


async def _start(play_: Play, _given: Any, models: Models) -> None:
    if play_.data.get("scenes"):
        raise PlayError("This play has already started.")
    # An opening the model's filter stopped left no scene: starting again asks for it again.
    play_.data["state"] = chain.opening(play_.draft()).model_dump(mode="json")
    story = play_.story(models)
    await _turn(play_, story, await story.open())


async def _act(play_: Play, given: Any, models: Models) -> None:
    if not isinstance(given, str) or not given.strip():
        raise PlayError("act takes the action as the player would type it.")
    story = _under_way(play_, models)
    await _turn(play_, story, await story.act(given))


async def _choose(play_: Play, given: Any, models: Models) -> None:
    choices = play_.data.get("choices", [])
    if not isinstance(given, int) or isinstance(given, bool) or not 1 <= given <= len(choices):
        raise PlayError(f"choose takes one of the last scene's {len(choices)} suggestions, from 1.")
    story = _under_way(play_, models)
    # A suggestion is played as the app sends it: by its words, as a choice.
    played = await story._play(TurnKind.CHOICE, choices[given - 1], None)
    await _turn(play_, story, played)


async def _wait(play_: Play, _given: Any, models: Models) -> None:
    story = _under_way(play_, models)
    await _turn(play_, story, await story.stand(StandingAction.WAIT))


async def _observe(play_: Play, _given: Any, models: Models) -> None:
    story = _under_way(play_, models)
    await _turn(play_, story, await story.stand(StandingAction.OBSERVE))


def _under_way(play_: Play, models: Models) -> Story:
    if play_.data.get("ended"):
        raise PlayError(f"This story has ended: {play_.data['ended']}.")
    if not play_.data.get("scenes"):
        raise PlayError("This play hasn't started: play a start step first.")
    return play_.story(models)


async def _turn(play_: Play, story: Story, played: Played) -> None:
    play_.keep_story(story, played)
    play_.tell(_turn_told(played, story.state))


async def _show(play_: Play, given: Any, _models: Models) -> None:
    wanted = [given] if isinstance(given, str) else list(given or SHOWN)
    unknown = [w for w in wanted if w not in SHOWN]
    if unknown:
        raise PlayError(f"show takes any of {', '.join(SHOWN)}: {unknown}")
    state = (
        WorldState.model_validate(play_.data["state"])
        if play_.data.get("state") is not None
        else play_.draft().state()
    )
    language = play_.language
    parts = [f"## What the screens show (turn {state.turn})"]
    if "sheet" in wanted:
        sheet = status_view(state, language).model_dump(mode="json")
        parts.append(f"### The Character screen\n\n```json\n{_json(sheet)}\n```")
    if "memory" in wanted:
        memory = memory_view(state, language).model_dump(mode="json")
        parts.append(f"### Memory\n\n```json\n{_json(memory)}\n```")
    if "record" in wanted:
        parts.append(
            "### On record (the player never sees this)\n\n"
            f"```json\n{_json(_record(state) | _waiting(state))}\n```"
        )
    play_.tell("\n\n".join(parts))


_STEPS = {
    "copy": _copy,
    "create": _create,
    "revise": _revise,
    "start": _start,
    "act": _act,
    "choose": _choose,
    "wait": _wait,
    "observe": _observe,
    "show": _show,
}


# --- what the transcript says ----------------------------------------------------------------


def _draft_told(draft: chain.Draft, heading: str, telemetry: TurnTelemetry) -> str:
    state = draft.state()
    seconds = sum(call.latency_ms for call in telemetry.calls) / 1000
    thought = sum(call.thinking_tokens for call in telemetry.calls)
    written = sum(call.output_tokens for call in telemetry.calls) - thought
    tries = sum(call.attempts for call in telemetry.calls)
    spent = f"{seconds:.1f} s, ${float(telemetry.cost_usd):.3f}"
    return "\n\n".join(
        [
            f"## {heading}",
            f"> {draft.premise}",
            f"_{spent}: {thought} tokens of thinking, {written} of answer, {tries} tries_",
            "### What the draft's screen shows",
            view.shown(state, draft.language, draft.said),
            "### On record (the player never sees this)",
            f"```json\n{_json(_record(state))}\n```",
        ]
    )


def _record(state: WorldState) -> dict[str, Any]:
    """Where the character stands on record, beside the world they stand in: what a short
    description of them became (A4, G13, G18)."""
    pc = state.player
    who = pc.model_dump(mode="json", exclude={"sheet"}, exclude_defaults=True)
    bible = state.bible
    ladders = [
        {
            "id": ladder.id,
            "name": ladder.name,
            "rungs": [
                f"{i}: {rung.name} (tier {rung.tier}"
                + (f", lives {rung.lifespan_years}" if rung.lifespan_years is not None else "")
                + ")"
                for i, rung in enumerate(ladder.rungs)
            ],
        }
        for ladder in bible.ladders
    ]
    others = sorted(
        (c for c in state.characters.values() if c.id != pc.id),
        key=lambda c: (-max((p.rung for p in c.sheet.ladders), default=-1), -_peak(c), c.name),
    )
    return {
        "world": {"title": bible.title, "genre": bible.genre, "era": bible.era},
        "character": who,
        "sheet": pc.sheet.model_dump(mode="json", exclude_defaults=True),
        "gift": view.gift_strength(state).value,
        "extraordinary": [
            f"{e.kind} ({e.prevalence.value}){': ' + e.reach if e.reach else ''}"
            for e in bible.extraordinary
        ],
        "ladders": ladders,
        "peoples": [p.model_dump(mode="json", exclude_defaults=True) for p in bible.peoples],
        "rules": [rule.text for rule in bible.rules],
        "others": [_other(c) for c in others[:OTHERS_LISTED]],
        "people_in_the_world": len(state.characters) - 1,
        "years": _years(state),
        "record_check": check_state(state),
    }


def _years(state: WorldState) -> dict[str, Any] | None:
    """Where old age stands for the character (W6, N6): nothing of it is ever shown in play."""
    found = last_years.years_of(state, state.world_s)
    if found is None:
        return None
    return {
        "age": round(found.age, 1),
        "lives_about": found.span,
        "the_record_says_so": found.said,
        "old": found.old,
        "told_the_end_is_close": found.told,
    }


def _peak(character) -> int:
    return max(character.sheet.attributes.model_dump().values(), default=0)


def _other(character) -> str:
    rungs = ", ".join(f"{p.ladder_id} rung {p.rung}" for p in character.sheet.ladders)
    age = f", {character.age}" if character.age is not None else ""
    standing = f", {rungs}" if rungs else ""
    return f"{character.name}{age}{standing}, peak attribute {_peak(character)}"


def _waiting(state: WorldState) -> dict[str, Any]:
    """What the world has waiting, by kind and how far off: never shown in play (W10)."""
    waiting = [e for e in state.pending_events.values() if e.status is EventStatus.PENDING]
    waiting.sort(key=lambda e: e.due_s)
    return {
        "waiting": [
            f"{e.kind}{' ' + repr(e.title) if e.title else ''} in {_span(e.due_s - state.world_s)}"
            + (" (stops the player)" if e.needs_player else "")
            for e in waiting[:WAITING_LISTED]
        ]
    }


def _span(seconds: int) -> str:
    """A stretch of the world's time, in the unit it reads best in."""
    for unit, size in (("years", YEAR), ("days", DAY), ("hours", HOUR)):
        if abs(seconds) >= size:
            return f"{seconds / size:.1f} {unit}"
    return f"{seconds} s"


def _when(told: Mapping[str, Any]) -> str:
    return ", ".join(str(told[key]) for key in ("date", "clock") if told.get(key))


def _turn_told(played: Played, state: WorldState) -> str:
    cost = f"${float(played.cost_usd):.3f}"
    head = f"## Turn {played.turn} ({played.kind.value}), {played.seconds:.1f} s, {cost}"
    parts = [head]
    if played.action:
        parts.append(f"> {played.action}")
    if played.refused is not None:
        refused = played.to_json()["refused"]
        parts.append(f"**Refused:** {json.dumps(refused)}")
        return "\n\n".join(parts)
    outcome = played.outcome()
    clock = outcome["clock"]
    pc = state.player
    parts.append(
        f"_From {_when(clock['from'])} to {_when(clock['to'])} ({_span(played.world_seconds)}). "
        f"{pc.name} is {pc.age if pc.age is not None else 'of no recorded age'}, "
        f"{pc.status.value}._"
    )
    intent = played.result.intent if played.result is not None else None
    decided = [
        f"- read as {step.kind.value}, {step.verb!r}"
        + (
            f" on {', '.join(step.target_ids or step.targets)}"
            if step.target_ids or step.targets
            else ""
        )
        + f", {step.proposed_duration_s} s: {step.text}"
        for step in (intent.steps if intent is not None else [])
    ]
    decided += [
        f"- {s['step']} [{s['class']}, {s['result']}]: {s['why']}"
        + (f" (wrongs: {json.dumps(s['wrongs'])})" if s.get("wrongs") else "")
        for s in outcome["steps"]
    ]
    throws = played.decided.throws if played.decided is not None else []
    decided += [
        f"- dice: hand {t.hand} ({t.hand_why}), number {t.number}, {t.total} of {t.most}"
        + (f" against {t.against}" if t.against else "")
        + f": {t.mark.value}"
        + (", deadly" if t.deadly else "")
        for t in throws
    ]
    for key in ("unplayed", "event", "meanwhile"):
        if outcome.get(key):
            decided.append(f"- {key}: {json.dumps(outcome[key], ensure_ascii=False)}")
    if played.decided is not None and played.decided.passage_label:
        decided.append(f"- heading: {played.decided.passage_label}")
    if decided:
        parts.append("**Read and decided:**\n" + "\n".join(decided))
    scene = played.scene
    if played.resets:
        parts.append(f"**The telling started over:** {', '.join(played.resets)}")
    if scene.narration_mode != "full":
        parts.append(f"**Narration mode:** {scene.narration_mode}")
    parts.append(scene.narration)
    if scene.choices:
        choices = "\n".join(
            f"{n}. {choice.label} ({choice.kind.value})"
            for n, choice in enumerate(scene.choices, start=1)
        )
        parts.append(f"**Suggestions:**\n{choices}")
    if played.findings:
        parts.append("**Issues:**\n" + "\n".join(f"- {found}" for found in played.findings))
    counted = {name: count for name, count in played.tally.items() if count}
    if counted:
        parts.append(f"**Counted:** {json.dumps(counted)}")
    ending = played.result.ending if played.result is not None else None
    if ending is not None:
        parts.append(f"**The story ends:** {json.dumps(dataclasses.asdict(ending))}")
    return "\n\n".join(parts)


def _json(value: Any) -> str:
    return json.dumps(_pruned(value), ensure_ascii=False, indent=1)


def _pruned(value: Any) -> Any:
    """`value` without what says nothing: None, and empty text, lists and maps."""
    if isinstance(value, Mapping):
        kept = {k: _pruned(v) for k, v in value.items()}
        return {k: v for k, v in kept.items() if v not in (None, "", [], {})}
    if isinstance(value, list | tuple):
        return [v for v in (_pruned(item) for item in value) if v not in (None, "", [], {})]
    return value

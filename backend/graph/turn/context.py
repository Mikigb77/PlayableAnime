"""Building what the model nodes read (B5 step 4), from the world state and the turn so far.

Every prompt is a few titled sections of JSON or plain text. What a section holds is chosen in code:
the scene the last turn ended on (R3), the people present, the player character's sheet, what the
engine resolved, the director's pick and the story so far (C3). Hidden truth a character could
never show, such as secrets or a mystery's answer, stays out. Retrieval over older facts and scenes
(C4) comes later; until then the rolling summary and the chapter summaries carry the past.
"""

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from engine import possessions
from engine.base import DAY
from engine.context import Language, TurnContext
from engine.contracts import (
    BeatResolution,
    BeatVerdict,
    DirectorPlan,
    EventSource,
    Intent,
    ItemChange,
    Resolution,
)
from engine.labels import ago_label, in_label, moment, span_label
from engine.state.cast import Character, CharacterStatus, FactionStatus, PlaceStatus
from engine.state.records import EventStatus, GoalStatus, LeadStatus, PendingEvent
from engine.state.world import WorldState, natural_key
from graph.language import written_in
from graph.llm import Prompt
from graph.turn import prompts
from graph.turn.types import RECENT_SCENES, Ending, PastScene

# Facts this important, which the player character knows, always reach the narrator.
KEY_FACT_IMPORTANCE = 4

# What the interpret step needs of the world to judge what it allows (G6, G8), and how people
# get around in it, to judge how long a trip takes (W10).
_INTERPRET_WORLD = {
    "genre",
    "era",
    "physics",
    "extraordinary",
    "rules",
    "peoples",
    "creatures",
    "medicine",
    "travel",
}
_RECORD_NOISE = {"known_by", "met_by", "visited_by", "status_history", "origin", "look_version"}
# Shown by name in a character's `family` (N6) instead of as ids and in-world seconds.
_KIN = {"parent_ids", "expecting"}
_NPC_HIDDEN = {
    "secrets": True,
    "personal_offset_s": True,
    "agenda": {"secret"},
    "sheet": {"rulings": True, "growth": True, "backstory": True, "disposition": {"attitudes"}},
}


def section(title: str, body: Any) -> str:
    text = body if isinstance(body, str) else _json(body)
    return f"## {title}\n{text}"


def render(sections: Iterable[tuple[str, Any]]) -> str:
    return "\n\n".join(section(title, body) for title, body in sections)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _dump(model: Any, exclude: Any = None, include: Any = None) -> dict[str, Any]:
    return model.model_dump(mode="json", include=include, exclude=exclude, exclude_defaults=True)


def present_characters(state: WorldState) -> list[Character]:
    """Who is in the scene with the player character, living, in a stable order. A dead character
    can't be present (C1)."""
    present = []
    for character_id in dict.fromkeys(state.scene.present_ids):
        character = state.characters.get(character_id)
        if character is None or character_id == state.player_id:
            continue
        if character.status is not CharacterStatus.ALIVE:
            continue
        present.append(character)
    return present


def place_name(state: WorldState) -> str | None:
    place_id = state.scene.place_id or state.player.location_id
    place = state.places.get(place_id) if place_id else None
    return place.name if place else None


def _player_view(state: WorldState) -> dict[str, Any]:
    view = {"id": state.player_id} | _dump(
        state.player, exclude={*_RECORD_NOISE, *_KIN, "personal_offset_s"}
    )
    # C10: what they have is exactly what this lists, so their money shows even when it is none.
    resources = state.player.sheet.resources
    held = view.setdefault("sheet", {}).setdefault("resources", {})
    held.pop("currency", None)  # shown beside the amount
    held["money"] = resources.money
    if resources.currency:
        held["currency"] = resources.currency
    # The player character's own family, marking anyone of it they don't know of (C6).
    return view | _family_view(state, state.player, knower=state.player_id)


def _family_view(
    state: WorldState, character: Character, *, knower: str | None = None
) -> dict[str, Any]:
    """N6: a character's parents and children by name, and a child they carry, when due. With
    `knower`, kin that character doesn't know of are marked so."""
    children = [c for c in state.characters.values() if character.id in c.parent_ids]
    family: dict[str, Any] = {}
    for key, ids in (
        ("parents", character.parent_ids),
        ("children", [c.id for c in sorted(children, key=lambda c: natural_key(c.id))]),
    ):
        named = [_kin_name(state, i, knower) for i in ids if i in state.characters]
        if named:
            family[key] = named
    expecting = character.expecting
    if expecting is not None and character.alive:
        other = state.characters.get(expecting.other_parent_id or "")
        family["expecting"] = {
            "with": other.name if other is not None else None,
            "due": in_label(max(0, expecting.due_s - state.world_s)),
        }
    return {"family": family} if family else {}


def _kin_name(state: WorldState, character_id: str, knower: str | None) -> dict[str, Any]:
    kin = state.characters[character_id]
    view: dict[str, Any] = {"id": kin.id, "name": kin.name}
    if not kin.alive:
        view["dead"] = True
    if knower is not None and knower not in kin.known_by:
        view["unknown_to_you"] = True
    return view


def _npc_view(character: Character, state: WorldState) -> dict[str, Any]:
    hidden = dict.fromkeys({*_RECORD_NOISE, *_KIN}, True) | _NPC_HIDDEN
    view = {"id": character.id} | _dump(character, exclude=hidden) | _family_view(state, character)
    sheet = view.get("sheet", {})
    if "powers" in sheet:
        # A power kept secret stays out until it is used, and resolve's outcome tells of it then.
        shown = [_dump(power) for power in character.sheet.powers if not power.secret]
        if shown:
            sheet["powers"] = shown
        else:
            del sheet["powers"]
    attitude = character.sheet.disposition.attitudes.get(state.player_id)
    if attitude is not None:
        view["toward_you"] = _dump(attitude)
    return view


def _fallen_view(state: WorldState) -> list[dict[str, Any]]:
    """N6: the story's earlier player characters whom someone in the scene knew, so those people
    can remember them, and whether each of them knows how it ended (C6)."""
    present = [
        state.characters[cid]
        for cid in state.scene.present_ids
        if cid != state.player_id and cid in state.characters
    ]
    views = []
    for fallen in state.fallen:
        character = state.characters.get(fallen.character_id)
        if character is None:
            continue
        # `met_by` lists who met a character: the fallen, when they were the player character.
        knew = [
            c
            for c in present
            if c.alive
            and c.id != character.id
            and (character.id in c.met_by or character.id in c.sheet.disposition.attitudes)
        ]
        if not knew:
            continue
        died = fallen.ending == "death"
        told = _told_of_death(state, character) if died else set()
        views.append(
            {
                "name": fallen.name,
                "ending": "died" if died else "left the story's centre and lives on",
                "remembered_by": [
                    {"name": c.name, "knows_how_it_ended": not died or c.id in told} for c in knew
                ],
            }
        )
    return views


def _told_of_death(state: WorldState, character: Character) -> set[str]:
    """Who knows how a character died: who saw it or heard of it (`StatusChange.known_by`), and
    who knows of a deed that killed or harmed them, by seeing it or by word reaching them (W2,
    W4)."""
    death = next((s for s in reversed(character.status_history) if s.status == "dead"), None)
    told = set(death.known_by) if death is not None else set()
    for deed in state.deeds.values():
        if character.id in deed.victim_ids:
            told.update(deed.known_by, deed.witness_ids, deed.unnoticed_witness_ids)
    return told


def _scene_view(state: WorldState) -> dict[str, Any]:
    frame = state.scene
    place_id = frame.place_id or state.player.location_id
    place = state.places.get(place_id) if place_id else None
    return {
        "place": ({"id": place.id} | _dump(place, exclude=_RECORD_NOISE)) if place else None,
        "present": [_npc_view(c, state) for c in present_characters(state)],
        "positions": frame.positions,
        "props": frame.props,
        "encounter": _dump(frame.encounter, exclude={"last_s"}) if frame.encounter else None,
    }


def _known_view(state: WorldState) -> dict[str, Any]:
    """Names the player character knows, for mapping misheard names (V3) and for continuity."""
    you = state.player_id
    present = {c.id for c in present_characters(state)}
    people = [
        {
            "id": c.id,
            "name": c.name,
            **({"aliases": c.aliases} if c.aliases else {}),
            **({"status": c.status.value} if c.status is not CharacterStatus.ALIVE else {}),
        }
        for c in sorted(state.npcs(), key=lambda c: c.id)
        if c.id not in present and (you in c.known_by or you in c.met_by)
    ]
    places = [
        {
            "id": p.id,
            "name": p.name,
            **({"status": p.status.value} if p.status is not PlaceStatus.THRIVING else {}),
        }
        for p in sorted(state.places.values(), key=lambda p: p.id)
        if you in p.known_by or you in p.visited_by
    ]
    factions = [
        {"id": f.id, "name": f.name, "status": f.status.value}
        for f in sorted(state.factions.values(), key=lambda f: f.id)
        if you in f.known_by
    ]
    return {"people": people, "places": places, "factions": factions}


def _world_view(state: WorldState, include: set[str] | None = None) -> dict[str, Any]:
    """The world bible without its hidden answers. The settings a model can't assume are always
    shown, defaults included: how strict physics is (A9), whether the dead can come back (C1) and
    whether news travels instantly (W2)."""
    bible = state.bible
    view = _dump(bible, include=include, exclude={"mysteries", "title"})
    view["physics"] = bible.physics.value
    if include is None or "medicine" in include:
        view.setdefault("medicine", {})["resurrection"] = bible.medicine.resurrection.value
    if include is None or "travel" in include:
        view.setdefault("travel", {})["instant_messages"] = bible.travel.instant_messages
    return view


def _continuity(state: WorldState) -> list[str]:
    """Lines the narrator must never contradict (C1), worked out in code."""
    lines = []
    for c in sorted(state.npcs(), key=lambda c: c.id):
        if c.status is CharacterStatus.DEAD:
            lines.append(f"{c.name} ({c.id}) is dead.")
    for f in sorted(state.factions.values(), key=lambda f: f.id):
        if f.status is FactionStatus.DESTROYED:
            lines.append(f"{f.name} ({f.id}) is destroyed and no longer acts as one.")
    for p in sorted(state.places.values(), key=lambda p: p.id):
        if p.status is not PlaceStatus.THRIVING:
            lines.append(f"{p.name} ({p.id}) is {p.status.value}.")
    you = state.player_id
    for fact in sorted(state.facts.values(), key=lambda f: (-f.importance, f.id)):
        if fact.importance >= KEY_FACT_IMPORTANCE and you in fact.known_by:
            belief = "" if fact.is_true else " (the character believes this; it isn't true)"
            lines.append(f"{fact.text}{belief}")
    return lines


def _past(state: WorldState, scenes: Sequence[PastScene]) -> dict[str, Any]:
    return {
        "chapters": [
            {"turns": f"{c.from_turn}-{c.to_turn}", "summary": c.summary}
            for c in sorted(state.chapters, key=lambda c: c.index)
        ],
        "summary": state.summary or "(the story is just beginning)",
        "recent_scenes": [
            {"turn": s.turn, "action": s.player_action, "narration": s.narration}
            for s in scenes[-RECENT_SCENES:]
        ],
    }


def _changed_hands(state: WorldState) -> list[str]:
    """C10. The player character's latest gains and losses, and who has what they lost, so no
    model forgets that the coins are gone (`engine.possessions`)."""
    return possessions.prompt_lines(state) or ["(nothing yet)"]


def _goals_and_threads(state: WorldState) -> dict[str, Any]:
    """The player's goals, the open threads they know of and the leads on offer (N1, N2)."""
    you = state.player_id
    return {
        "goals": [
            g.text
            for g in sorted(state.goals.values(), key=lambda g: g.id)
            if g.status is GoalStatus.ACTIVE
        ],
        "threads": [
            {"id": t.id, "title": t.title, "stakes": t.stakes, "status": t.status.value}
            for t in sorted(state.threads.values(), key=lambda t: t.id)
            if not t.status.closed and you in t.known_by
        ],
        "leads": [
            {"id": lead.id, "text": lead.text}
            for lead in sorted(state.leads.values(), key=lambda lead: lead.id)
            if lead.status is LeadStatus.OPEN
        ],
    }


def interpret_prompt(state: WorldState, action: str, language: Language = Language.EN) -> Prompt:
    """B5 step 2: what the interpret model reads to turn the player's words into an `Intent`,
    with the story's language for its notes (S10)."""
    frame = state.scene
    # The world comes first and alone: it stays the same from turn to turn, so the backend can
    # keep it cached with the system text (`Prompt.stable_chars`).
    world = ("WORLD", _world_view(state, include=_INTERPRET_WORLD))
    user = render(
        [
            world,
            ("PLAYER CHARACTER", _player_view(state)),
            ("CHANGED HANDS", _changed_hands(state)),
            ("SCENE", _scene_view(state)),
            ("LAST MOMENT", frame.ended_on or "(the story is just beginning)"),
            ("NOW", _now_view(state)),
            ("KNOWN", _known_view(state)),
            ("GOALS AND THREADS", _goals_and_threads(state)),
            ("LANGUAGE", written_in(language)),
            ("ACTION", action.strip()),
        ]
    )
    return Prompt.build(prompts.INTERPRET_SYSTEM, user, stable_chars=len(render([world])))


@dataclass(frozen=True)
class NarrationBrief:
    """Everything the narrate node needs: the prompt, and what its fallbacks use (F4)."""

    system: str
    user: str
    place: str | None
    suggestions: int
    # How much of `user` stays the same from turn to turn (`Prompt.stable_chars`).
    stable_chars: int = 0
    # The story's language, for the template line (S10).
    language: Language = Language.EN

    def prompt(self, *, cutaway: bool = False) -> Prompt:
        if cutaway:
            # A cutaway is rare, so a cache made for its system text would go unused.
            return Prompt.build(self.system + prompts.CUTAWAY_SYSTEM, self.user)
        return Prompt.build(self.system, self.user, stable_chars=self.stable_chars)

    def template_line(self) -> str:
        here, there = prompts.TEMPLATE_PLACE[self.language]
        where = here.format(place=self.place) if self.place else there
        return prompts.TEMPLATE_LINE[self.language].format(where=where)


def narration_brief(
    *,
    before: WorldState,
    after: WorldState,
    ctx: TurnContext,
    intent: Intent | None,
    resolution: Resolution,
    plan: DirectorPlan,
    fired: Sequence[PendingEvent],
    scenes: Sequence[PastScene],
    premise: str = "",
    words: str | None = None,
    ending: Ending | None = None,
    wish: str | None = None,
    left_out: Sequence[str] = (),
) -> NarrationBrief:
    """B5 step 4: the narrator's prompt.

    `before` is the state the turn started from, so the scene picks up where the last one ended
    (R3). `after` is the state once the steps played out, with the time that passed and every
    consequence the engine recorded. `words` are the player's own words for the action, so the
    scene can tell it with their gestures and manner before what comes of it (R1). `ending` is
    set when this scene ends the player character's story (N6), with `wish`, the player's note
    on how, for an ending they chose, or `left_out`, the parts of it the world refused when the
    player ended without them.
    """
    settings = ctx.settings
    tone = before.bible.tone or "the genre's own voice"
    if settings.tone:
        tone = f"{tone}; the player asked for: {settings.tone}"
    style = {
        "genre": before.bible.genre,
        "tone": tone,
        "length": prompts.LENGTHS[settings.narration_length],
        "language": written_in(settings.language),
    }
    content = prompts.content_rules(
        ctx.rating,
        ctx.content_prefs.gore,
        romance=ctx.content_prefs.romance,
        dark_themes=ctx.content_prefs.dark_themes,
    )
    # What stays the same from turn to turn comes first, so the backend can keep it cached with
    # the system text and Gemini bills it at its cached rate (`Prompt.stable_chars`).
    stable: list[tuple[str, Any]] = [
        ("STYLE", style),
        ("CONTENT", content),
        ("WORLD", _world_view(before)),
    ]
    sections: list[tuple[str, Any]] = [
        *stable,
        *([("PREMISE", premise)] if premise and ctx.turn <= 1 else []),
        ("STORY SO FAR", _past(before, scenes)),
        ("CONTINUITY", _continuity(after) or ["(nothing yet)"]),
        ("GOALS AND THREADS", _goals_and_threads(before)),
        ("PLAYER CHARACTER", _player_view(after)),
        ("CHANGED HANDS", _changed_hands(after)),
        ("KNOWN", _known_view(after)),
        ("LAST MOMENT", before.scene.ended_on or "(the story is just beginning)"),
        ("SCENE", _scene_view(before)),
    ]
    if fallen := _fallen_view(after):
        sections.append(("FALLEN", fallen))

    if intent is None and not resolution.steps and ending is None:
        sections.append(("NOW", _now_view(after)))
        # N6: someone new carries the story on after its ending.
        opening = prompts.SUCCESSION_TASK if before.opening_due else prompts.OPENING_TASK
        if before.opening_due and before.fallen:
            # An heir's story may start years after the ending, once they can act.
            last = before.fallen[-1]
            since = before.world_s - last.world_s
            if since >= DAY:
                sections.append(("ENDED", f"{last.name}'s story ended {ago_label(since)}."))
        sections.append(("TASK", opening))
    else:
        if intent is not None:
            sections.append(("ACTION", _action_view(intent, words)))
        sections.append(("OUTCOME", _outcome_view(resolution)))
        sections.append(("TIME", _time_view(before, after)))
    # The director tells its own events, and the world's events it made the scene's event or a
    # happening, as EVENT and HAPPENINGS (W16, E7), so nothing is told twice.
    told = {
        e.source_id
        for e in (plan.event, *plan.happenings)
        if e is not None and e.source is EventSource.DUE
    }
    seen = [
        e
        for e in fired
        if _perceived(e, after)
        and not e.kind.startswith("director.")
        and e.id not in told
        and e.status is not EventStatus.CANCELLED  # it came to nothing, such as a birth
    ]
    if seen:
        sections.append(("FIRED", [_event_view(e) for e in seen]))
    if plan.event is not None:
        sections.append(("EVENT", _dump(plan.event, exclude=_PLANNED_HIDDEN)))
    if plan.happenings:
        sections.append(
            ("HAPPENINGS", [_dump(h, exclude=_PLANNED_HIDDEN) for h in plan.happenings])
        )
    callbacks = [after.threads[t] for t in plan.callbacks if t in after.threads]
    if callbacks:
        sections.append(
            ("CALLBACKS", [{"id": t.id, "title": t.title, "stakes": t.stakes} for t in callbacks])
        )
    suggestions = plan.suggestions.count
    kinds = [kind.value for kind in plan.suggestions.kinds][:suggestions]
    asked: dict[str, Any] = {"count": suggestions, "kinds": kinds}
    current = after.threads.get(plan.suggestions.thread_id or "")
    if suggestions and current is not None and "thread" in kinds:
        asked["thread"] = {"id": current.id, "title": current.title}  # what thread choices follow
    sections.append(("SUGGESTIONS", asked))
    if plan.picture is not None:
        subject = plan.picture.subject_id
        sections.append(
            (
                "PICTURE",
                {
                    "kind": plan.picture.kind.value,
                    "subject": _subject_name(after, subject) if subject else None,
                    "why": plan.picture.reason,
                },
            )
        )
    if ending is not None:
        told_ending: dict[str, Any] = {"kind": ending.kind}
        if wish:
            told_ending["wish"] = wish
        if left_out:
            told_ending["left_out"] = list(left_out)
        sections.append(("ENDING", told_ending))
        task = prompts.DEATH_TASK if ending.kind == "death" else prompts.EPILOGUE_TASK
        sections.append(("TASK", task))
    return NarrationBrief(
        system=prompts.NARRATOR_SYSTEM,
        user=render(sections),
        place=place_name(after),
        suggestions=suggestions,
        stable_chars=len(render(stable)),
        language=settings.language,
    )


def _action_view(intent: Intent, words: str | None) -> dict[str, Any]:
    """The player's own words first, then what the interpret step read in them (R1, R7)."""
    view = _dump(intent, exclude={"actor_id"})
    if words and words.strip():
        return {"words": words.strip(), **view}
    return view


def _outcome_view(resolution: Resolution) -> dict[str, Any]:
    steps = []
    for step in resolution.steps:
        view: dict[str, Any] = {
            "step": step.text,
            "class": step.outcome_class.value,
            "result": step.result.value,
            "why": step.reason,
        }
        if step.roll is not None:
            view["odds"] = step.roll.odds_label or f"{round(step.roll.odds * 100)}%"
        if step.costs:
            view["costs"] = [c.text for c in step.costs]
        if step.effects.items and not step.interrupted:
            # C10: what the step moved, already recorded; the narrator shows it, never again. A
            # step an event cut short moved nothing.
            view["changed_hands"] = [_moved(change) for change in step.effects.items]
        if any(beat.verdict is not BeatVerdict.HOLDS for beat in step.beats):
            # R2: the beats as checked, in order, when one found something new or came up empty.
            # A step stops at its empty beat, so the beats after it never happen.
            view["beats"] = [_beat_view(beat) for beat in step.beats]
        if step.chain:
            view["chain"] = [
                {"link": link.text, "holds": link.holds, "why": link.reason} for link in step.chain
            ]
        if step.strangers:
            # F1, W2: who this step made real, so the narrator meets them under these ids.
            made: dict[str, Any] = {}
            for change in step.effects.characters:  # the first change per id is the one that
                made.setdefault(change.id, change)  # made them; a kill or a wound comes after
            view["met"] = [
                {"id": i, "who": made[i].name, "about": made[i].description}
                for i in step.strangers
                if i in made
            ]
        if step.perils:
            # N6: what struck back at the player character after their step, in order.
            view["struck"] = [
                {"by": p.by, "means": p.aim.value, "harm": p.harm.value, "why": p.reason}
                for p in step.perils
            ]
        if step.interrupted:
            view["interrupted"] = True
        steps.append(view)
    outcome: dict[str, Any] = {"steps": steps}
    if resolution.stopped_at_step is not None:
        outcome["stopped_at_step"] = resolution.stopped_at_step
        outcome["stop_reason"] = resolution.stop_reason.value if resolution.stop_reason else None
    if resolution.unplayed:
        outcome["unplayed"] = resolution.unplayed
    if resolution.canon:
        outcome["now_canon"] = resolution.canon
    # A9. Rulings made this turn: on the player's theories, and those a step settled by trying.
    rulings = [*resolution.rulings]
    rulings += [r for s in resolution.steps for c in s.effects.characters for r in c.rulings]
    if rulings:
        outcome["rulings"] = [_dump(r) for r in rulings]
    if resolution.claims:
        outcome["backstory"] = [
            {"claim": c.text, "recorded": c.accepted, "why": c.reason} for c in resolution.claims
        ]
    return outcome


def _moved(change: ItemChange) -> dict[str, Any]:
    view: dict[str, Any] = {
        "what": change.name,
        "amount": change.quantity,
        "from": change.from_id,
        "to": change.to_id,
    }
    if change.money:
        view["money"] = True
    return view


def _beat_view(beat: BeatResolution) -> dict[str, Any]:
    view: dict[str, Any] = {"beat": beat.text, "uses": beat.thing, "check": beat.verdict.value}
    if beat.reason:
        view["why"] = beat.reason
    return view


def _now_view(state: WorldState) -> dict[str, Any]:
    """W10. Where the world's clock stands, so the models judge times and tell the hour as the
    clock shows it."""
    return moment(state.bible.calendar, state.world_s).model_dump()


def _time_view(before: WorldState, after: WorldState) -> dict[str, Any]:
    """W10. When the scene began and what time it is now, with the time the action took: the
    telling keeps to the clock."""
    elapsed = after.world_s - before.world_s
    lived = after.player.personal_s(after.world_s) - before.player.personal_s(before.world_s)
    view: dict[str, Any] = {
        "began": _now_view(before),
        "now": _now_view(after),
        "passed": span_label(elapsed),
        "world_seconds_passed": elapsed,
    }
    if lived != elapsed:
        view["your_seconds_lived"] = lived
    return view


# Bookkeeping in a `PlannedEvent` that the narrator has no use for.
_PLANNED_HIDDEN = {"source", "source_id", "card_id", "plays_out_s"}


def _perceived(event: PendingEvent, state: WorldState) -> bool:
    """Whether the player character could notice an event that fired: it needs them, involves
    them, or happens where they are. Everything else stays off-screen (C6)."""
    if event.needs_player or state.player_id in event.subject_ids:
        return True
    here = state.scene.place_id or state.player.location_id
    return event.place_id is not None and event.place_id == here


def _event_view(event: PendingEvent) -> dict[str, Any]:
    return {
        "title": event.title or event.kind,
        "kind": event.kind,
        "needs_you": event.needs_player,
    }


def _subject_name(state: WorldState, subject_id: str) -> str:
    for records in (state.characters, state.places, state.deeds, state.threads):
        record = records.get(subject_id)
        if record is not None:
            return (
                getattr(record, "name", None)
                or getattr(record, "title", None)
                or getattr(record, "text", subject_id)
            )
    return subject_id


def chapter_prompt(scenes: Sequence[PastScene], language: Language = Language.EN) -> Prompt:
    """C3: the summarizer's prompt for one chapter of scenes, summarized in the story's language
    (S10)."""
    body = [{"turn": s.turn, "action": s.player_action, "narration": s.narration} for s in scenes]
    return Prompt.build(
        prompts.SUMMARIZER_SYSTEM, render([("LANGUAGE", written_in(language)), ("SCENES", body)])
    )

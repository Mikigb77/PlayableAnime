import json

from app.domain import Choice, Scene, Story
from app.engine.memory import apply_update, continuity_rules
from app.engine.schemas import NarratorOutput
from app.llm.base import LLMProvider

RECENT_SCENES = 3
MAX_CHOICES = 3

SYSTEM_PROMPT = """\
You are the narrator of an endless, interactive anime-style story. The player is the protagonist \
and speaks to you only through their actions.

Write the next scene:
- Second person ("you"), present tense, 120-250 words, vivid and cinematic.
- React to the player's action with real consequences; the world pushes back.
- Never end the story. Close every scene on a hook.
- Offer exactly 3 short, meaningfully different choices (max 12 words each). The player may also \
type their own action instead.

Continuity is sacred:
- Obey every CONTINUITY RULE in the prompt. They override anything else.
- Dead characters never appear, speak or act again, except in scenes clearly framed as memories.
- Destroyed factions never act as organisations again.

Report every change to the world in state_update:
- characters: new characters (stable snake_case id, name, description), deaths or \
disappearances (status), and affinity_delta (-20..20) toward the player.
- factions: new factions and stance changes. Use "destroyed" only when it is wiped out.
- new_facts: things that must be remembered later, with importance 1-5.
- goals: the player's current goals, or null if unchanged.
- summary: the whole story so far in at most 150 words.
Reuse the ids listed under KNOWN CHARACTERS and KNOWN FACTIONS.

image_prompt: one sentence describing the key visual of this scene, or null.
"""


def build_prompt(story: Story, action: str | None) -> str:
    state = story.state
    rules = continuity_rules(state)
    recent = story.scenes[-RECENT_SCENES:]
    sections = [
        f"PREMISE:\n{story.premise}",
        f"STORY SO FAR:\n{state.summary or '(the story is just beginning)'}",
        "CONTINUITY RULES:\n" + ("\n".join(f"- {r}" for r in rules) or "- none yet"),
        "PLAYER GOALS:\n" + ("\n".join(f"- {g}" for g in state.goals) or "- none yet"),
        "KNOWN CHARACTERS:\n" + _to_json(state.characters),
        "KNOWN FACTIONS:\n" + _to_json(state.factions),
        "RECENT SCENES:\n" + ("\n\n".join(s.narration for s in recent) or "(none)"),
        f"PLAYER ACTION:\n{action}" if action else "Write the opening scene.",
    ]
    return "\n\n".join(sections)


class Narrator:
    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    async def advance(self, story: Story, action: str | None = None) -> Story:
        """Returns the story with one more scene: the opening one when `action` is None."""
        output = await self._llm.generate(
            system=SYSTEM_PROMPT, prompt=build_prompt(story, action), schema=NarratorOutput
        )
        turn = story.state.turn + 1
        scene = Scene(
            turn=turn,
            player_action=action,
            narration=output.narration,
            choices=[
                Choice(id=f"c{i}", label=label)
                for i, label in enumerate(output.choices[:MAX_CHOICES], start=1)
            ],
            image_prompt=output.image_prompt,
        )
        return story.model_copy(
            update={
                "scenes": [*story.scenes, scene],
                "state": apply_update(story.state, output.state_update, turn),
            }
        )


def _to_json(items: list) -> str:
    if not items:
        return "(none)"
    return json.dumps([i.model_dump(mode="json") for i in items], ensure_ascii=False)

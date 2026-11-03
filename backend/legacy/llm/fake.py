from pydantic import BaseModel

from legacy.engine.schemas import CharacterChange, NarratorOutput, NewFact, StateUpdate


class FakeNarratorProvider:
    """Offline stand-in for local development and tests. Only knows how to narrate."""

    async def generate[T: BaseModel](self, *, system: str, prompt: str, schema: type[T]) -> T:
        if schema is not NarratorOutput:
            raise TypeError(f"FakeNarratorProvider cannot produce {schema.__name__}")
        output = NarratorOutput(
            narration=(
                "The air hums as the world reacts to you. Somewhere above, a bell rings once. "
                "(Offline narrator: set LLM_PROVIDER=vertex or add your own API key for real "
                "stories.)"
            ),
            choices=["Follow the sound of the bell", "Search for allies", "Wait and observe"],
            image_prompt="A lone figure under a violet sky, a distant bell tower glowing.",
            state_update=StateUpdate(
                characters=[
                    CharacterChange(
                        id="ren",
                        name="Ren",
                        description="A rival who keeps turning up at the worst moments.",
                        affinity_delta=1,
                    )
                ],
                new_facts=[NewFact(text="A bell rang when the player acted.", importance=2)],
                summary="The player's journey has just begun, and Ren keeps crossing their path.",
            ),
        )
        return output  # type: ignore[return-value]

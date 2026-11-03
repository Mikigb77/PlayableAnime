from typing import Protocol

from pydantic import BaseModel


class LLMProvider(Protocol):
    async def generate[T: BaseModel](self, *, system: str, prompt: str, schema: type[T]) -> T:
        """Runs one completion and returns the response parsed into `schema`."""
        ...

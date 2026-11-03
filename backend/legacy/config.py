from typing import Literal

from pydantic import BaseModel


class Settings(BaseModel):
    """What the legacy narrator needs to pick a model. Django settings fill it in from the env."""

    # "fake" runs a canned offline narrator so the API works without any cloud credentials.
    llm_provider: Literal["vertex", "fake"] = "fake"
    gcp_project: str = "playable-anime"
    vertex_location: str = "global"
    narrator_model: str = "gemini-3.5-flash"

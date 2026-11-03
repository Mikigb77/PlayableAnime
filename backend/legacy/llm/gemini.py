from google import genai
from google.genai import types
from pydantic import BaseModel


class GeminiProvider:
    """Gemini through Vertex AI (our project) or through a user's own Gemini API key."""

    def __init__(self, client: genai.Client, model: str) -> None:
        self._client = client
        self._model = model

    @classmethod
    def vertex(cls, *, project: str, location: str, model: str) -> "GeminiProvider":
        return cls(genai.Client(vertexai=True, project=project, location=location), model)

    @classmethod
    def with_api_key(cls, api_key: str, model: str) -> "GeminiProvider":
        return cls(genai.Client(api_key=api_key), model)

    async def generate[T: BaseModel](self, *, system: str, prompt: str, schema: type[T]) -> T:
        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system,
                response_mime_type="application/json",
                response_schema=schema,
            ),
        )
        if isinstance(response.parsed, schema):
            return response.parsed
        return schema.model_validate_json(response.text or "")

"""The studio voices a player can pick for reading aloud (V9).

Gemini's TTS models have 30 prebuilt voices, each of which reads any language. These four suit a
storyteller: two lower, two higher, from warm to grave. The app names them by how they sound and
sends the name; the default is the one a new player hears.
"""

DEFAULT_VOICE = "Sulafat"
# Name: how it sounds, as Google describes it.
VOICES = {
    "Sulafat": "warm",
    "Gacrux": "mature",
    "Charon": "informative, deep",
    "Algieba": "smooth",
}

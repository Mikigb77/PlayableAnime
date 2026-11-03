"""Pictures (M1 to M8, S7): what to draw, drawing it once, storing it, and handing out URLs.

- `models`: an `Image` per subject (a character's portrait, a place, a scene, the cover), reused
  wherever that subject appears (M4), and the `ScenePicture` that shows it in a scene.
- `plans`: `plan_picture()`, which the turn calls when code decided a scene gets a picture (M1).
- `service`: the picture endpoints' work: claim, pay, draw, store, at most once per picture (M3).
- `prompts`: the house style, the world's look and the mild-in-every-rating rules (S7, M5, M6).
- `drawing`: the picture model behind a small interface, on `graph.llm` (M8).
- `storage`: private Cloud Storage with signed URLs, or local files in development and tests.
- `billing`: where a picture is paid for (M7), wired to the credit ledger by WS7.
- `lookups`: picture URLs for scenes, portraits, covers and the account export.
"""

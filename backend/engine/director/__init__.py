"""The story director (WS11): W16, E4, E6, E7, N1, N2, S2, S4, M1, M2.

Every story keeps moving, even a quiet one. The director is code with no model call (K8): it
tracks stall pressure, decides when something new comes in and where it comes from (the world's
own state first, then a seeded deck filtered by rating and the player's themes), lets ignored
events play out, keeps threads, goals and leads honest, shapes the suggestions and decides when a
scene gets a picture. It decides that something happens and what it is, never how it ends.

The pipeline calls three things here:

- `direct(state, resolution, ctx, rng, intent)` after the steps played out, for the plan.
- `record(state, plan, ctx)` to write the plan's updates back (`pipeline.record_direction`).
- `schedule_stretch(state, start_s, end_s, ctx, rng)` from `play_out` before the clock moves
  through a day or more, so a time skip stops early when an event needs a decision (E7), and
  `schedule_road` in its place for a trip, which rolls what the road brings (W10).
- `settle_look(state, plan)` after the narrator's update, so a planned portrait or place is drawn
  at the look the scene left it with (M4, M5, `pipeline.settle_picture`).
"""

from engine.director.montage import schedule_road, schedule_stretch
from engine.director.pictures import settle_look
from engine.director.plan import direct
from engine.director.record import record

__all__ = ["direct", "record", "schedule_road", "schedule_stretch", "settle_look"]

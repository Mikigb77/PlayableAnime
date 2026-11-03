"""Provisional ids for the records a plan creates.

`direct` never changes the state, so it can't take ids from it. It asks an `IdProbe`, which hands
out the ids `WorldState.new_id` would give, in order, without touching the state. Recording
re-checks each one and gives a fresh id to any that was taken in the meantime (the narrator's own
leads, say), so a plan never overwrites a record.
"""

from engine.state.world import WorldState


class IdProbe:
    def __init__(self, state: WorldState) -> None:
        self._probe = state.model_copy(update={"id_counters": dict(state.id_counters)})

    def new(self, prefix: str) -> str:
        return self._probe.new_id(prefix)

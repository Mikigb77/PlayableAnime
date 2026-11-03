"""World-state bookkeeping.

The model proposes changes; this module decides what actually sticks. Invariants that keep the
story consistent (the dead stay dead, destroyed factions stay destroyed) live here, not in the
prompt, so a forgetful model cannot break them.
"""

from legacy.domain import (
    Character,
    CharacterStatus,
    Fact,
    Faction,
    FactionStance,
    WorldState,
)
from legacy.engine.schemas import StateUpdate

# Facts at or above this importance are restated to the model every turn.
PINNED_FACT_IMPORTANCE = 4


def apply_update(state: WorldState, update: StateUpdate, turn: int) -> WorldState:
    new = state.model_copy(deep=True)
    new.turn = turn

    characters = {c.id: c for c in new.characters}
    for change in update.characters:
        character = characters.get(change.id)
        if character is None:
            if not change.name:
                continue
            character = Character(id=change.id, name=change.name)
            characters[change.id] = character
            new.characters.append(character)
        elif change.name:
            character.name = change.name
        if change.description:
            character.description = change.description
        if change.status and character.status is not CharacterStatus.DEAD:
            character.status = change.status
        character.affinity = max(-100, min(100, character.affinity + change.affinity_delta))

    factions = {f.id: f for f in new.factions}
    for change in update.factions:
        faction = factions.get(change.id)
        if faction is None:
            if not change.name:
                continue
            faction = Faction(id=change.id, name=change.name)
            factions[change.id] = faction
            new.factions.append(faction)
        elif change.name:
            faction.name = change.name
        if change.description:
            faction.description = change.description
        if change.stance and faction.stance is not FactionStance.DESTROYED:
            faction.stance = change.stance

    new.facts.extend(
        Fact(text=f.text, turn=turn, importance=f.importance) for f in update.new_facts
    )
    if update.goals is not None:
        new.goals = update.goals
    if update.summary:
        new.summary = update.summary
    return new


def continuity_rules(state: WorldState) -> list[str]:
    """Hard constraints restated to the model before every scene."""
    rules: list[str] = []
    for c in state.characters:
        if c.status is CharacterStatus.DEAD:
            rules.append(f"{c.name} ({c.id}) is dead and cannot appear, speak or act.")
        elif c.status is CharacterStatus.MISSING:
            rules.append(f"{c.name} ({c.id}) is missing; the player does not know where they are.")
    for f in state.factions:
        if f.stance is FactionStance.DESTROYED:
            rules.append(f"The faction {f.name} ({f.id}) has been destroyed.")
    rules.extend(f.text for f in state.facts if f.importance >= PINNED_FACT_IMPORTANCE)
    return rules

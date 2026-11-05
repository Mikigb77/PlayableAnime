"""N6. Lineage: who is whose child.

A character's parents are `Character.parent_ids`, as far as the story has them: the drafter sets
them for a family it drafts, and the narrator for someone met as someone's child, or a parentage
the scene reveals. A pregnancy is `Character.expecting`, on whoever carries the child;
`engine.world.births` has the child born when it is due, if they are alive then. Children and
grandchildren are who can carry a story on after its ending, as heirs.
"""

from __future__ import annotations

from collections.abc import Mapping

from engine.state.cast import Character
from engine.state.world import WorldState


def ancestors(characters: Mapping[str, Character], character_id: str) -> set[str]:
    """Everyone a character descends from, as far as the story has them. Takes the characters
    alone, so the drafter can check a family before there is a world state."""
    found: set[str] = set()
    character = characters.get(character_id)
    frontier = list(character.parent_ids) if character is not None else []
    while frontier:
        parent_id = frontier.pop()
        if parent_id in found or parent_id not in characters:
            continue
        found.add(parent_id)
        frontier.extend(characters[parent_id].parent_ids)
    return found


def descendants(state: WorldState, character_id: str) -> dict[str, int]:
    """Everyone who descends from a character, by id, with how many generations down: 1 for a
    child, 2 for a grandchild."""
    children: dict[str, list[str]] = {}
    for character in state.characters.values():
        for parent_id in character.parent_ids:
            children.setdefault(parent_id, []).append(character.id)
    found: dict[str, int] = {}
    frontier = [(child, 1) for child in children.get(character_id, [])]
    while frontier:
        child_id, depth = frontier.pop(0)
        if child_id in found or child_id == character_id:
            continue
        found[child_id] = depth
        frontier.extend((grandchild, depth + 1) for grandchild in children.get(child_id, []))
    return found


def related(state: WorldState, a: str, b: str) -> bool:
    """Whether one is the other's parent or child: the closest family (W4)."""
    first, second = state.characters.get(a), state.characters.get(b)
    if first is None or second is None:
        return False
    return b in first.parent_ids or a in second.parent_ids

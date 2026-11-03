"""Fictional people in drafted worlds (G12): the drafting side of `engine.limits`' real-name check.

A real living person is never a character and a real crime family, party, company or government is
never a faction. The player's own words are checked before any model call: a premise, a revision
or an edited line that names a real person is refused with the field it is in, so the player can
say it another way (`real_person_in`). Naming a real organisation is allowed there, as a backdrop,
the same as in an action. What the model drafts is cleaned after every call: a key character or
faction named after a real person or organisation is left out, a real alias is dropped, and a
player character given a real name falls back to the default name (`without_real_names`).
Plain Python with no Django (B4).
"""

import logging
from collections.abc import Iterable
from dataclasses import dataclass

from engine import limits
from graph.drafting.schema import CharacterProposal, DraftProposal, WorldProposal

logger = logging.getLogger("graph.drafting")


@dataclass(frozen=True)
class RealPersonNamed:
    """A real person in the player's words: the field (a dotted path, as API.md's
    `details.fields` gives it) and who."""

    field: str
    name: str

    @property
    def message(self) -> str:
        return (
            f"{self.name} is a real person, and stories only have fictional people. "
            "Try someone made up instead."
        )


def real_person_in(fields: Iterable[tuple[str, str]]) -> RealPersonNamed | None:
    """The first real living person named in the player's text, by field, or None (G12). A find
    is logged as a block (F4)."""
    for field, text in fields:
        for entity in limits.real_entities(text) if text else ():
            if entity.kind == "person":
                _log_block("prompt", 1)
                return RealPersonNamed(field, entity.name)
    return None


def _log_block(stage: str, count: int) -> None:
    """The same block line as the turn graph's, with no names (F4, T6)."""
    block = {
        "node": "drafter",
        "source": "code",
        "categories": [limits.LimitCategory.REAL_PERSON.value],
        "stage": stage,
        "count": count,
    }
    logger.warning("drafter blocked", extra={"block": block})


def _real(name: str) -> limits.RealEntity | None:
    return limits.real_entity(name) if name and name.strip() else None


def _world(world: WorldProposal, hits: list[str]) -> WorldProposal:
    found = len(hits)
    npcs = []
    for npc in world.npcs:
        if entity := _real(npc.name):
            hits.append(entity.name)
            continue  # references to them resolve to nothing when the world is assembled
        real = [e.name for alias in npc.aliases if (e := _real(alias))]
        if real:
            hits += real
            npc = npc.model_copy(update={"aliases": [a for a in npc.aliases if not _real(a)]})
        npcs.append(npc)
    factions = []
    for faction in world.factions:
        if entity := _real(faction.name):
            hits.append(entity.name)
            continue
        factions.append(faction)
    if len(hits) == found:
        return world
    return world.model_copy(update={"npcs": npcs, "factions": factions})


def _character(character: CharacterProposal, hits: list[str]) -> CharacterProposal:
    changes: dict[str, object] = {}
    if entity := _real(character.name):
        hits.append(entity.name)
        changes["name"] = ""  # assembled as the default name
    if entity := _real(character.family_name):
        hits.append(entity.name)
        changes["family_name"] = ""
    aliases = [alias for alias in character.aliases if not _real(alias)]
    if aliases != character.aliases:
        hits += [e.name for alias in character.aliases if (e := _real(alias))]
        changes["aliases"] = aliases
    connections = [c for c in character.connections if not _real(c.name)]
    if connections != character.connections:
        hits += [e.name for c in character.connections if (e := _real(c.name))]
        changes["connections"] = connections
    return character.model_copy(update=changes) if changes else character


def without_real_names[P: (DraftProposal, WorldProposal, CharacterProposal)](proposal: P) -> P:
    """The model's proposal with no real person or organisation as a character or faction (G12).
    Each one left out is logged as a block, with the names at DEBUG only (F4, T6)."""
    hits: list[str] = []
    if isinstance(proposal, DraftProposal):
        world = _world(proposal.world, hits)
        character = _character(proposal.character, hits)
        cleaned = DraftProposal(world=world, character=character) if hits else proposal
    elif isinstance(proposal, WorldProposal):
        cleaned = _world(proposal, hits)
    else:
        cleaned = _character(proposal, hits)
    if hits:
        _log_block("update", len(hits))
        logger.debug("limit detail", extra={"limit_hits": [{"subject": h} for h in hits]})
    return cleaned

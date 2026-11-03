"""The drafter's prompts (G1, G2, S1). Code checks everything the model proposes
(`graph.drafting.assemble`), so the prompts aim for a good draft, not a safe one.

Prompts carry the player's premise and requests, so they are never logged (T6).
"""

from __future__ import annotations

import json

from engine.state import GiftStrength, WorldState
from graph.drafting.catalog import PremiseTemplate
from graph.drafting.schema import PLAYER_ID, DraftProposal, RuleP

SYSTEM = f"""\
You draft the opening of a story for Lucid Saga, an endless story game where the player can do \
anything and the world remembers it and reacts. You turn the player's premise into a world and a \
player character, as JSON that follows the schema exactly. Code checks every field you write.

THE WORLD
- Say what is real in it: the era and its technology; every kind of extraordinary thing and how \
common it is (none, hidden, rare or common), such as magic, qi, aura, gods, psychic powers, \
cybernetics, superpowers or an in-world system; peoples and creatures, if any; where nature works \
differently from ours (only the differences: fire needs air unless the world says otherwise); how \
people and news travel; medicine, and whether anything brings back the dead; laws, customs and \
who enforces them.
- A grounded world, with nothing supernatural, lists one extraordinary kind, "magic or anything \
supernatural", with prevalence none. Any other world lists every kind it has: a power can only \
come from a kind the world lists.
- Write two to eight rules in plain sentences. A fixed rule holds for the whole story; an open \
rule could change through a discovery made in the story. Whether something extraordinary exists \
is usually fixed; how far it can go is usually open. Link each rule to the kinds it is about.
- Give a power ladder only where the premise has one (cultivation realms, aura ranks, adventurer \
ranks, levels), lowest rung first. The gaps between rungs are large and felt.
- Two to ten places, up to eight factions (a faction can sit inside a larger one: a crew inside a \
family, a court inside a sect) and two to eight key characters, each with a temperament, what \
they want and, where it fits, an agenda and a secret. Give every adult an age.
- One to four first clocks: the deadlines and threats the premise sets, with what happens at \
each step and how many in-world hours each step takes ("the council picks the boss in ten days" \
is four steps of 60 hours). Nothing is timed in turns, and the clocks run whether or not the \
player is there.
- Threads for the open plot lines. Decide the answer and the clues of any major mystery now, so \
an investigation stays fair.
- The story opens on the premise's situation: the place, who is there, where they stand, what is \
at hand, and the moment itself in one sentence. The premise is a situation, not a script.

THE CHARACTER
- Draft the player character from the premise and the world: attributes (3 is an average \
person, 5 the peak of what a person can be, 6 to 10 beyond human only where the world allows it), \
skills, traits (gifts and flaws), powers only where the world has them, temperament, equipment, \
money, standing, connections, condition, their rung on a ladder, and their goals from the \
premise in the player's own words. A strong start is fine when the premise calls for it.
- Each power names the extraordinary kind it comes from (kind_id), with its limits and costs. \
Mark the character's special gift with gift=true and its strength: small (an edge), rare (a real \
talent) or overpowered (such as time stop or a cheat system). Decide how a power works yourself; \
the player finds out its details in play. Time stop lasts three heartbeats and needs a breath to \
recharge unless the premise says otherwise.
- A character reborn or waking in another body keeps their past life's memories; what others \
remember of that body's past, and the character doesn't, goes in hidden_past.

WHAT THE PLAYER SEES
The player reads the names, descriptions, rules, era, ladder, clocks, threads, mystery questions \
and the character, but never secrets, agendas, factions' goals and methods, mystery answers and \
clues, or the hidden past. Keep every description to how things look from outside, and never put \
a secret, a plan or an answer into a name, a description, a rule, a fact or the summary. Mark \
whether the character knows each place, faction, clock, thread and person.

IDS
Use short lowercase ids such as "carmine" or "outer-court", and refer to records by them. The \
player character's id is "{PLAYER_ID}".

CONTENT
Every person and organisation is fictional: a real city or real history can be the backdrop, but \
no real living person, crime family, party, company or government appears. Peoples and races are \
fictional, never a stand-in for a real-world ethnic group. There is no sexual content in any \
rating. Write in English, in plain words, in the world's own voice.\
"""

RATINGS = {
    "teen": "Rating: Teen. Fights and injuries without gore; romance goes as far as a kiss.",
    "mature": (
        "Rating: Mature 17+. The world can hold graphic violence, cruel villains and dark "
        "crimes; romance fades out before sex."
    ),
}

GIFTS = {
    GiftStrength.NONE: "The character has no special gift.",
    GiftStrength.SMALL: "The character's special gift is small: a real edge, nothing more.",
    GiftStrength.RARE: "The character's special gift is rare: a talent few people have.",
    GiftStrength.OVERPOWERED: (
        "The character's special gift is overpowered, such as time stop or a cheat system. It "
        "really is that strong, with limits that make choices interesting."
    ),
}


def system_prompt(rating: str) -> str:
    return f"{SYSTEM}\n\n{RATINGS.get(rating, RATINGS['teen'])}"


def template_block(template: PremiseTemplate | None, released: frozenset[str]) -> str:
    """What a starter premise's genre fixes (G7), for the model to keep."""
    if template is None:
        return ""
    lines = ["This is a starter premise. Keep its genre:"]
    rules = [r for r in template.rules if r.id not in released]
    if rules:
        lines.append("- These fixed rules, word for word and with these ids:")
        lines += [f"  - {r.id}: {r.text}" for r in rules]
    kinds = [k for k in template.extraordinary if all(r not in released for r in k.rule_ids)]
    if kinds:
        lines.append("- These extraordinary kinds:")
        lines += [f"  - {k.id}: {k.kind}, {k.prevalence.value}" for k in kinds]
    if template.ladder is not None:
        rungs = ", ".join(r.name for r in template.ladder.rungs)
        lines.append(f"- The {template.ladder.name} (id {template.ladder.id}): {rungs}.")
    if template.peoples:
        lines.append("- These peoples: " + ", ".join(p.name for p in template.peoples) + ".")
    if template.notes:
        lines.append(f"- {template.notes}")
    return "\n".join(lines)


def draft_prompt(
    premise: str,
    *,
    template: PremiseTemplate | None,
    gift: GiftStrength | None,
    released: frozenset[str] = frozenset(),
) -> str:
    parts = [f"Premise, in the player's words:\n{premise.strip()}"]
    if block := template_block(template, released):
        parts.append(block)
    if gift is not None:
        parts.append(GIFTS[gift])
    parts.append("Draft the world, then the player character in it.")
    return "\n\n".join(parts)


def revise_prompt(
    premise: str,
    current: DraftProposal,
    state: WorldState,
    *,
    target: str,
    instruction: str,
    template: PremiseTemplate | None,
    gift: GiftStrength | None,
    released: frozenset[str],
) -> str:
    """A change in plain words to the world or the character (G1, G2). The model sees the whole
    draft, hidden parts included, so the change fits the world."""
    world = current.world.model_copy(update={"rules": current_rules(state)})
    draft = {
        "world": world.model_dump(mode="json"),
        "character": current.character.model_dump(mode="json"),
    }
    parts = [
        f"Premise, in the player's words:\n{premise.strip()}",
        "The current draft:\n" + json.dumps(draft, ensure_ascii=False),
    ]
    if block := template_block(template, released):
        parts.append(block + "\nKeep these unless the player's request changes them.")
    if gift is not None and target == "character":
        parts.append(GIFTS[gift])
    if target == "world":
        parts.append(
            "The player asks for this change to the world:\n"
            f"{instruction.strip()}\n\n"
            "Return the whole world with the change made and everything else as it was, with "
            "the same ids. The character stays as it is, so keep what they belong to and where "
            "they are unless the change removes it. If the request removes or changes a fixed "
            "rule, list that rule's id in dropped_rule_ids."
        )
    else:
        parts.append(
            "The player asks for this change to their character:\n"
            f"{instruction.strip()}\n\n"
            "Return the whole character with the change made and everything else as it was. The "
            "world stays as it is, so a power must still come from a kind it has."
        )
    return "\n\n".join(parts)


def current_rules(state: WorldState) -> list[RuleP]:
    """The rules as they hold now, with the template's and code's own, as the model writes them."""
    about: dict[str, list[str]] = {}
    for kind in state.bible.extraordinary:
        for rule_id in kind.rule_ids:
            about.setdefault(rule_id, []).append(kind.id)
    return [
        RuleP(id=r.id, text=r.text, fixed=r.fixed, topic=r.topic, about=about.get(r.id, []))
        for r in state.bible.rules
    ]


def lines_instruction(what: str, before: list[str], after: list[str]) -> str:
    """A direct edit of the summary lines, as a request the model can act on."""
    said = "\n".join(f"- {line}" for line in before) or "- (nothing)"
    wants = "\n".join(f"- {line}" for line in after) or "- (nothing)"
    return (
        f"The player rewrote the {what} summary. It said:\n{said}\n"
        f"The player wants it to say:\n{wants}\n"
        f"Change the {what} so that its summary says what the player wrote, adding, changing or "
        "removing whatever that takes. Keep everything else."
    )


def rules_instruction(rules: list[RuleP]) -> str:
    listed = (
        "\n".join(f"- {r.id} ({'fixed' if r.fixed else 'open'}): {r.text}" for r in rules)
        or "- (no rules)"
    )
    return (
        "The player set the world's rules to exactly these:\n"
        f"{listed}\n"
        "Keep these rules word for word with the same ids, list the id of any fixed rule they "
        "remove in dropped_rule_ids, and change the rest of the world so it matches them."
    )


def gift_instruction(gift: GiftStrength) -> str:
    return (
        f"The player picked '{gift.value}' for the character's special gift. {GIFTS[gift]} "
        "Change the gift to fit and keep everything else."
    )

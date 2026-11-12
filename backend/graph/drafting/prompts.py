"""The drafter's prompts (G1, G2, S1). Code checks everything the model proposes
(`graph.drafting.assemble`), so the prompts aim for a good draft, not a safe one.

Prompts carry the player's premise and requests, so they are never logged (T6).
"""

from __future__ import annotations

import json

from engine.context import Language
from engine.state import GiftStrength, WorldState
from graph.drafting.catalog import PremiseTemplate
from graph.drafting.schema import PLAYER_ID, DraftProposal, RuleP
from graph.language import language_line

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
ranks, levels), lowest rung first. The gaps between rungs are large and felt. Write the ladder \
whole, up to the rung its strongest beings stand on, the legends, ancients and gods the world \
has included, however far above the character they are. known_to_all says how many of its \
rungs, counted from the lowest, everyone in the world has heard of: the player is told those \
at the start, and learns of each one above only when the story names it.
- Two to ten places, each with the place it lies within (parent_id) and its setting: outdoors, \
indoors, underground or underwater (R8). Draw the map between them (W7, W10): link the \
places people travel between through routes, a farm to its village, a town to the next town, a \
city to the pass that leads to it, so that every place can be reached from the others. Only a \
room or a building needs none: it is simply inside its parent. A route is written once, on \
either of its two places, with to_id the other one, travel_hours the hours the way takes as \
most people travel here (0.5, 6, or 72 for three days on the road) and mode how they go (on \
foot, by cart, by train). The story takes a trip's time from these, so make them true to the \
world's size.
- Up to eight factions (a faction can sit inside a larger one: a crew inside a family, a court \
inside a sect) and two to eight key characters, each with a \
temperament, what they want and, where it fits, an agenda and a secret. Give every adult an age. \
Where key characters are family, record it with parent_ids: a child names their parents, the \
player character included. A parentage the player character doesn't know of is a secret instead.
- One to four first clocks: the deadlines and threats the premise sets, with what happens at \
each step and how many in-world hours each step takes ("the council picks the boss in ten days" \
is four steps of 60 hours). The steps' hours add up to exactly the time the premise gives: its \
"exam in three days" is 72 hours in all, never four days. Nothing is timed in turns, and the \
clocks run whether or not the player is there.
- Threads for the open plot lines. Decide the answer and the clues of any major mystery now, so \
an investigation stays fair.
- The story opens on the premise's situation: the place, who is there, where they stand, what is \
at hand, and the moment itself in one sentence. The premise is a situation, not a script.

THE CHARACTER
- Draft the player character from the premise and the world: attributes (3 is an average \
person, 5 the peak of what a person can be, 6 to 10 beyond human only where the world allows it), \
skills, traits (gifts and flaws), powers only where the world has them, temperament, equipment, \
money, standing, connections, condition and their rung on a ladder. A strong start is fine \
when the premise calls for it. \
Their money is money and currency, such as 12 and "copper coins", never an item, so the engine \
can count what they pay and lose (C10).
- What the character is after is the player's to say. Write a goal, or something they want \
(temperament.wants), only where the premise says it as an aim ("I must pass the knight exam", \
"I came to the city to find my sister"), each as one short line that uses the premise's words \
for what it names ("Pass the knight exam"), never the premise repeated. What is coming, and \
what has happened, is no aim: "the knight exam is in 3 days" gives a clock and no goal, and \
"someone killed my father" gives a mystery and no goal. A premise that says no aim leaves both \
empty: the player sets their goals in play.
- Talents say how fast the character learns, and only where the premise says so: most \
characters have none. Write each from the player's own words, with a short name, what it covers \
in one plain sentence, and its strength: slow (a weakness, such as "hopeless at fighting": half \
the pace), knack (twice as fast), genius (four times) or one_of_a_kind (eight times). One of a \
kind always names one specific thing, with the reason behind it: a subject, such as the sword, \
or a faculty, such as extreme perception or a copycat eye, which covers whatever reaches them \
through it (any move they can watch someone do). Three one of a kind talents at most. Someone \
gifted at everything is one talent with general=true, a genius at most: nobody is one of a kind \
at everything. A talent of the body, such as great coordination, covers the moves that use it. \
A talent is how fast they learn, never what they can already do: that goes in skills, traits, \
powers and techniques, as well as the talent where the premise gives both.
- Each power names the extraordinary kind it comes from (kind_id), with its limits. Its costs \
come from the world and the premise, never from nowhere: what the world's rules say that kind of \
power takes (qi spent, a mage's fatigue, a price in blood or years), or what the premise gives \
it. A power the world charges nothing for has no cost: keen senses, a sharp mind or a feel for \
the wind cost nothing unless the world or the premise says so. Never invent pain, sickness or \
harm as a cost. Write each cost as when it is paid ("a night's sleep to recover after a full \
stop"). Mark the character's special gift with gift=true and its strength: small (an edge), rare \
(a real talent) or overpowered (such as time stop or a cheat system). Decide how a power works \
yourself; the player finds out its details in play. Time stop lasts three heartbeats and needs a \
breath to recharge unless the premise says otherwise.
- A character reborn or waking in another body keeps their past life's memories; what others \
remember of that body's past, and the character doesn't, goes in hidden_past.

WHAT THE PLAYER SEES
The player reads the names, descriptions, rules, era, the ladder's rungs everyone has heard of, \
clocks, threads, mystery questions and the character, but never secrets, agendas, factions' \
goals and methods, mystery answers and clues, the hidden past, or a ladder's higher rungs. How \
the story starts is its surprise: before it starts they are shown a clock, a mystery question, a \
key person or a connection only when their own words name it, and a goal or a want only when \
their own words say it as an aim. So call what the \
premise names by the premise's own words (its "knight exam in three days" is the clock "The \
knight exam"), and write the rest for the story to tell in play. Keep \
every description to how things look from outside, and never put a secret, a plan or an answer \
into a name, a description, a rule, a fact or the summary: a rule or a description names no \
rung above the ones everyone has heard of. Mark whether the character knows each place, \
faction, clock, thread and person.

IDS
Use short lowercase ids such as "carmine" or "outer-court", and refer to records by them. The \
player character's id is "{PLAYER_ID}".

CONTENT
Every person and organisation is fictional: a real city or real history can be the backdrop, but \
no real living person, crime family, party, company or government appears. Peoples and races are \
fictional, never a stand-in for a real-world ethnic group. There is no sexual content in any \
rating. Write in plain words, in the world's own voice.\
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


WORLD_CHANGE = """\
Reply with only what the change touches, and leave everything else out: it stays exactly as it \
is. Write each record the change adds or changes in full, in its list: one with an id already in \
the world replaces that record, and one with a new id is added. Put each record the change \
removes in removed, with its list as section and its id, and remove whatever the change makes \
untrue: a world that gains vampires loses its "magic or anything supernatural" kind with \
prevalence none and drops the rules that say nothing supernatural exists. A fixed rule goes only \
when its id is in dropped_rule_ids, so list every fixed rule the request removes or changes \
there. Write the title, genre, tone, era, summary, nature, norms, known facts, calendar, travel, \
medicine or opening only if the change alters them, each in full. The character stays as it is, \
so keep what they belong to and where they are unless the change removes it.\
"""


def system_prompt(rating: str, language: Language = Language.EN) -> str:
    """The drafter's system text, for the story's rating (F2) and language (S10)."""
    words = language_line(language, "every text field the player reads")
    return f"{SYSTEM}\n\n{words}\n\n{RATINGS.get(rating, RATINGS['teen'])}"


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
        if template.exclusive_rule_id and template.exclusive_rule_id not in released:
            lines.append("  and no other extraordinary kinds.")
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
    player_rules: list[str] | None = None,
) -> str:
    parts = [f"Premise, in the player's words:\n{premise.strip()}"]
    if block := template_block(template, released):
        parts.append(block)
    if player_rules:
        listed = "\n".join(f"- {text}" for text in player_rules)
        parts.append(f"The player set these rules. Build the world around them:\n{listed}")
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
    about: str = "",
) -> str:
    """A change in plain words to the world or the character (G1, G2). The model sees the whole
    draft, hidden parts included, so the change fits the world. `about` is the part of the
    summary the player asked it at, as they read it."""
    world = current.world.model_copy(update={"rules": current_rules(state)})
    # Without the fields left at their defaults: a full dump nearly doubles the prompt.
    draft = {
        "world": world.model_dump(mode="json", exclude_defaults=True),
        "character": current.character.model_dump(mode="json", exclude_defaults=True),
    }
    parts = [
        f"Premise, in the player's words:\n{premise.strip()}",
        "The current draft, which is what holds now: the player may have changed a name, an "
        "age or a look since the premise, and the draft's is the one to keep.\n"
        + json.dumps(draft, ensure_ascii=False),
    ]
    asked = f"{instruction.strip()}\n\n"
    if about.strip():
        asked += f"They ask it about this part of the summary they read:\n{about.strip()}\n\n"
    if block := template_block(template, released):
        parts.append(block + "\nKeep these unless the player's request changes them.")
    if gift is not None and target == "character":
        parts.append(GIFTS[gift])
    if target == "world":
        parts.append(f"The player asks for this change to the world:\n{asked}{WORLD_CHANGE}")
    else:
        parts.append(
            f"The player asks for this change to their character:\n{asked}"
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
        "removing whatever that takes. Keep everything else. The summary leaves out how the "
        "story starts unless the player named it, so a clock, a question, a person, a connection "
        "or a goal that neither list mentions stays as it is."
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


def rating_instruction(rating: str) -> str:
    return (
        f"The player changed the story's rating. {RATINGS.get(rating, RATINGS['teen'])} Bring "
        "anything beyond that within it: rewrite in full every part that goes beyond it, hidden "
        "parts included (secrets, agendas, mystery answers and clues), and keep everything else."
    )


def gift_instruction(gift: GiftStrength) -> str:
    return (
        f"The player picked '{gift.value}' for the character's special gift. {GIFTS[gift]} "
        "Change the gift to fit and keep everything else."
    )

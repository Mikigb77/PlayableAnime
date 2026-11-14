"""T17's eval of the level a short description becomes (G2, A4, A8, G18, G22, W6).

Most players describe their character in a line and start: they never see that the sheet tells
a knack from a genius from someone one of a kind, so the draft has to read the level off their
words (Miki, 2026-11-14: "I want to pay special attention into knowing if we are correctly
addressing the level of the character that they are creating just from a short description").
The first twenty live drafts got the attributes, the skills and the rung right and the rest
wrong: half the characters were one of a kind at something, most from a premise that only said
how strong they were; fourteen powers of fifteen said nothing of what they do; a courtesan who
charms people got a power over minds; and two ladders made everyone on them immune to old age.

Live mode drafts each premise below with the real drafter and reads the record. Deterministic
mode reads the offline draft the same way, and the rules code keeps whatever a draft says.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from engine.context import Language, Rating
from engine.state import TalentStrength
from engine.state.sheet import SkillLevel
from engine.world import last_years, old_age
from evals.runner import Eval
from evals.scenario import REGISTRY

scenario = REGISTRY.scenario

SLOW, KNACK, GENIUS, ONE = (
    TalentStrength.SLOW,
    TalentStrength.KNACK,
    TalentStrength.GENIUS,
    TalentStrength.ONE_OF_A_KIND,
)
# Drafts asked for side by side: each is one long model call.
AT_ONCE = 4


@dataclass(frozen=True)
class Described:
    """A character as a player would describe them, and the level those words say.

    `talents` are the strengths the sheet's talents must have, one for each (in any order);
    `or_talents` is another reading that is as good. `ordinary` is someone the premise gives
    no power. `best` is someone the premise calls the best at what they do; `plain` is someone
    it calls nothing special. `gift` is the strength of a gift the premise gives them.
    """

    name: str
    premise: str
    talents: tuple[TalentStrength, ...] = ()
    or_talents: tuple[TalentStrength, ...] | None = None
    general: bool = False
    ordinary: bool = False
    best: bool = False
    plain: bool = False
    gift: str = ""
    grows_old: bool = False
    language: Language = Language.EN
    rating: Rating = Rating.TEEN


DESCRIBED = (
    Described(
        "knight",
        "A knight in his thirties serving a minor lord on the border. Decent with a sword, "
        "nothing special.",
        ordinary=True,
        plain=True,
    ),
    Described(
        "strongest",
        "I'm the strongest sorcerer alive. Nobody has ever beaten me. I teach at a school for "
        "young sorcerers in modern Tokyo.",
        best=True,
    ),
    Described(
        "hacker",
        "I'm the best hacker in Night City. Corporations pay fortunes to keep me out of their "
        "systems.",
        best=True,
        rating=Rating.MATURE,
    ),
    Described(
        "courtesan",
        "A beautiful courtesan and spy in the imperial capital. She can make almost anyone "
        "fall for her, and she uses it to steal secrets for the rebellion.",
        ordinary=True,
        rating=Rating.MATURE,
    ),
    Described(
        "saint",
        "An 80-year-old sword saint who retired to a quiet mountain village decades ago. He "
        "was once the best swordsman in the kingdom.",
        best=True,
        grows_old=True,
    ),
    Described(
        "cheat",
        "I get hit by a truck and wake up in a fantasy world as a hero with an overpowered "
        "cheat skill.",
        gift="overpowered",
    ),
    Described(
        "prodigy",
        "A 17-year-old chess prodigy who just enrolled in an elite academy where everything, "
        "even your rank, is decided by strategy games.",
        talents=(GENIUS,),
        ordinary=True,
    ),
    Described(
        "violinista",
        "Soy una niña prodigio del violín en la Viena de 1890, y mi padre quiere que toque "
        "ante el emperador.",
        talents=(GENIUS,),
        ordinary=True,
        language=Language.ES,
    ),
    Described(
        "swordsman",
        "A wandering swordsman, a once-in-an-age talent with the blade and hopeless with words.",
        talents=(ONE, SLOW),
    ),
    Described(
        "allround",
        "A high school boy who is good at everything he tries and bored of it all, until his "
        "whole class is summoned to another world.",
        talents=(GENIUS,),
        or_talents=(KNACK,),
        general=True,
    ),
    Described(
        "farmboy",
        "A farm boy with no talent for cultivation at all, the worst in his village. One day "
        "he finds a ring with the soul of an ancient master inside.",
        talents=(SLOW,),
    ),
)


def _folded(text: str) -> str:
    return " ".join(text.casefold().split())


def _strengths(talents) -> list[str]:
    return sorted(t.strength.value for t in talents)


@scenario(
    "t17.level-from-a-short-description",
    suite="T17",
    title="Level from a short description",
    requirements=("G2", "A4", "A8", "G18", "G22", "W6", "T17"),
    passes_when=(
        "A character described in a line starts at the level those words say: words about how "
        "strong they are give no talent, words about how they learn give the talent they say "
        "(a prodigy is a genius, a once-in-an-age talent is one of a kind, good at everything "
        "is a general talent, a genius at most, no talent is a weakness), every talent quotes "
        "the player's words, someone the premise makes ordinary has no power, the best at "
        "something is a master of it and someone nothing special is average, a gift the premise "
        "gives is as strong as it says, every power says what it does, and old age comes to "
        "whoever the record can count, a sword saint of eighty included, who is old unless "
        "the record gives him longer (G2, A4, A8, G22, W6)"
    ),
    notes=(
        "Deterministic mode reads the offline drafter's outer disciple, whose premise speaks "
        "of no talent, and what code makes of a ladder said to lengthen life with no years; "
        "live mode drafts eleven made-up premises with the real drafter, in English and "
        "Spanish, and reads each record. Its metrics say what each draft gave."
    ),
)
async def level_from_a_short_description(ev: Eval) -> None:
    from graph.drafting import samples
    from graph.drafting.assemble import assemble
    from graph.drafting.view import PartKind, character_parts

    def everyone(draft, who: str) -> None:
        """What holds for any draft, whatever its premise says."""
        state = draft.state()
        told = [p for p in state.player.sheet.powers if not p.description]
        told += [p for c in state.npcs() for p in c.sheet.powers if not p.description]
        ev.check(
            "every power says what it does",
            not told,
            f"{who}: nothing said of {[p.name for p in told]}",
        )
        endless = [c.name for c in state.characters.values() if old_age.open_ended(state, c)]
        ev.check(
            "old age comes to whoever the record can count",
            not endless,
            f"{who}: the dice can never take {endless}",
        )
        lines = [
            part.text
            for part in character_parts(state, draft.language, draft.said)
            if part.kind is PartKind.POWER
        ]
        doubled = [
            line
            for line in lines
            for power in state.player.sheet.powers
            if line.casefold().startswith(f"{power.name}: {power.name}".casefold())
        ]
        ev.check("a power's line says its name once", not doubled, f"{who}: {doubled}")

    def read(case: Described, draft) -> str:
        """The checks of one description, and what its draft gave, for the run's metrics."""
        state = draft.state()
        sheet = state.player.sheet
        who = case.name
        everyone(draft, who)
        talents = sheet.talents
        got = _strengths(talents)
        wanted = [sorted(t.value for t in case.talents)]
        if case.or_talents is not None:
            wanted.append(sorted(t.value for t in case.or_talents))
        if case.talents:
            ev.check(
                "words about how they learn give the talent they say",
                got in wanted,
                f"{who}: {[(t.name, t.strength.value) for t in talents]}, for {wanted}",
            )
        else:
            ev.check(
                "words about how strong they are give no talent",
                not talents,
                f"{who}: {[(t.name, t.strength.value) for t in talents]}",
            )
        if ONE not in case.talents:
            ev.check(
                "nobody is one of a kind unless their words put them beyond anyone",
                ONE.value not in got,
                f"{who}: {[t.name for t in talents if t.strength is ONE]}",
            )
        if case.general:
            ev.check(
                "someone good at everything has one general talent",
                len(talents) == 1 and talents[0].general,
                f"{who}: {[(t.name, t.covers, t.general) for t in talents]}",
            )
        # The words behind each talent, as the draft itself gives them.
        unsaid = [
            t.name
            for t in draft.proposal.character.talents
            if not t.said.strip() or _folded(t.said) not in _folded(case.premise)
        ]
        ev.check(
            "every talent quotes the player's own words",
            not unsaid,
            f"{who}: {unsaid} quote nothing the premise says",
        )
        if case.ordinary:
            ev.check(
                "someone the premise makes ordinary has no power",
                not sheet.powers,
                f"{who}: {[p.name for p in sheet.powers]}",
            )
        peak = max(sheet.attributes.model_dump().values())
        mastered = [s.name for s in sheet.skills if s.level is SkillLevel.MASTER]
        if case.best:
            ev.check(
                "the best at something is a master of it",
                bool(mastered) and peak >= 5,
                f"{who}: masters {mastered}, highest attribute {peak}",
            )
        if case.plain:
            ev.check(
                "someone nothing special is an average person",
                not mastered and peak <= 4,
                f"{who}: masters {mastered}, highest attribute {peak}",
            )
        gifts = [p.strength.value for p in sheet.powers if p.strength is not None]
        if case.gift:
            ev.check(
                "a gift the premise gives is as strong as it says",
                case.gift in gifts,
                f"{who}: gifts {gifts}",
            )
        if case.grows_old:
            # Old at eighty, unless the record itself gives them longer: a draft may put a
            # sword saint on a ladder whose rung lives a hundred years, and then says so.
            years = last_years.years_of(state, state.world_s)
            ev.check(
                "someone of eighty has their years counted, and is old unless the record gives "
                "them longer",
                years is not None and (years.old or (years.said and years.span > 80)),
                f"{who}: {years}",
            )
        ranked = [c for c in state.npcs() if c.sheet.powers and state.bible.ladders]
        unranked = [c.name for c in ranked if not c.sheet.ladders]
        gave = f"talents {got}, powers {len(sheet.powers)}, gifts {gifts}, peak {peak}"
        return f"{gave}, no rung {unranked}" if unranked else gave

    if not ev.live:
        # The offline drafter gives its outer disciple whatever the premise: reborn with their
        # past life's memories and the power to stop time, which says nothing of how they learn.
        draft = await ev.draft(samples.CULTIVATION_PREMISE)
        sample = Described("outer-disciple", samples.CULTIVATION_PREMISE, gift="overpowered")
        ev.metric("levels", {sample.name: read(sample, draft)})
        # W6: a ladder the draft says lengthens life, with no years on any rung, lengthens
        # none. Left unsaid, the dice could never take anyone who stands on it.
        world = samples.cultivation_world()
        world.ladders[0].lengthens_life = True
        for rung in world.ladders[0].rungs:
            rung.lifespan_years = None
        character = samples.cultivation_character().model_copy(update={"age": 75})
        character.powers[0].description = ""
        state = assemble(world, character)
        endless = [c.name for c in state.characters.values() if old_age.open_ended(state, c)]
        years = last_years.years_of(state, state.world_s)
        ev.check(
            "a ladder that gives no years lengthens no life",
            not endless and years is not None and years.span == 80 and years.old,
            f"the dice can never take {endless}, the character's years {years}",
        )
        lines = [
            part.text for part in character_parts(state, Language.EN) if part.kind is PartKind.POWER
        ]
        ev.check(
            "a power the draft only named is on the screen by its name, once",
            bool(lines) and not any("Time stop: Time stop" in line for line in lines),
            f"{lines}",
        )
        return

    at_once = asyncio.Semaphore(AT_ONCE)

    async def drafted(case: Described):
        async with at_once:
            return await ev.draft(case.premise, rating=case.rating, language=case.language)

    drafts = await asyncio.gather(*(drafted(case) for case in DESCRIBED))
    levels = {case.name: read(case, draft) for case, draft in zip(DESCRIBED, drafts, strict=True)}
    ev.metric("levels", levels)

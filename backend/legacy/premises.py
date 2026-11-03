"""Starter premises shown on the Discover screen until user-made stories exist."""

from pydantic import BaseModel


class Premise(BaseModel):
    id: str
    title: str
    genre: str
    premise: str


SEED_PREMISES: list[Premise] = [
    Premise(
        id="hollowmere",
        title="Last Exam at Hollowmere",
        genre="Academy fantasy",
        premise=(
            "You are a scholarship student at Hollowmere, a sky-island academy of magic where "
            "anyone who fails the final exam has their memories auctioned off. The exam starts in "
            "seven days, and your magic still refuses to answer you."
        ),
    ),
    Premise(
        id="drowned-capital",
        title="Ronin of the Drowned Capital",
        genre="Samurai drama",
        premise=(
            "The old capital sank beneath the sea a century ago, and its clans still fight over "
            "the rooftops that remain above the waves. You are a masterless swordsman who just "
            "woke up holding a clan heir's broken seal."
        ),
    ),
    Premise(
        id="dead-god-courier",
        title="Courier for a Dead God",
        genre="Neon urban fantasy",
        premise=(
            "In the harbour city of Lumen, gods are worshipped like pop idols, and one of them "
            "died yesterday. You are a night-shift courier, and the package in your bag is "
            "addressed to that god."
        ),
    ),
    Premise(
        id="demon-lord-accountant",
        title="The Demon Lord's Accountant",
        genre="Isekai comedy",
        premise=(
            "You were reborn in a fantasy world with no combat skills, only an uncanny talent for "
            "numbers. The Demon Lord's army is bankrupt, and its terrifying lord has just hired "
            "you to fix the books before the heroes arrive."
        ),
    ),
]

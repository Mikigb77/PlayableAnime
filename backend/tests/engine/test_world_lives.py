"""W6, W10: the people the story knows lead lives of their own while it is elsewhere.

Over the years they may find a partner, marry, have a child, part, make a close friend or
fall out with someone, and everyone grows older. Nothing is made to happen: a month brings
next to nothing, ten years a great deal, and many are found as they were left. The player
character's own romances stay theirs (G15), and they hear what came to someone when they live
near or when they next meet them (C6).
"""

import pytest

from engine import bonds, pipeline
from engine.apply import DeltaSource, apply_delta
from engine.base import DAY, YEAR
from engine.contracts import CharacterChange, StateDelta
from engine.invariants import check_state, check_transition
from engine.samples import farm_world
from engine.state import (
    Attitude,
    Bond,
    BondEnd,
    BondStage,
    BondStep,
    Character,
    CharacterStatus,
    DeathCertainty,
    LifeEvent,
    LifeKind,
    Origin,
    OriginKind,
    People,
    Place,
    Prominence,
    Route,
    StatusChange,
    Unions,
    WorldState,
)
from engine.succession import carry_on
from engine.world import lives, returns
from engine.world.scheduling import World
from engine.world.tuning import LIFE_QUIET_S, LIVES_KEPT, MOST_CHILDREN

from .test_world import ctx, idle, rng

YOU = "tomas"
NARRATOR = DeltaSource.NARRATOR
SEASON = LIFE_QUIET_S


def villager(cid: str, name: str, age: int | None = 30, **more) -> Character:
    more.setdefault("location_id", "village")
    return Character(id=cid, name=name, age=age, known_by=[YOU], met_by=[YOU], **more)


def valley(*people: Character) -> WorldState:
    """Tomas on his farm with Ilse beside him, Old Bram in the village forty minutes away,
    and whoever else the test puts there. A city lies five days off."""
    state = farm_world()
    for person in people:
        state.characters[person.id] = person
    state.places["city"] = Place(id="city", name="Harrowgate", kind="city")
    state.places["village"].routes.append(Route(to_id="city", travel_s=5 * DAY))
    state.scene.present_ids = [YOU, "ilse"]
    return state


def couple(state: WorldState, a: str, b: str, stage: BondStage = BondStage.TOGETHER) -> Bond:
    bond = Bond(id=state.new_id("bond"), a_id=a, b_id=b, stage=stage)
    bond.steps.append(BondStep(stage=stage, how="As the story opens."))
    state.bonds[bond.id] = bond
    return bond


def sure(monkeypatch, **odds) -> None:
    """Make things certain, or impossible, so a test reads what happens, not how often."""
    for name, value in odds.items():
        monkeypatch.setattr(lives, name, value)


def quiet(monkeypatch) -> None:
    """Nothing comes to anyone unless a test says so, and nobody is settled as they are by
    the luck of their id."""
    never = {"for_life": 0.0, "held": 0.0, "easy": 0.0}
    sure(
        monkeypatch,
        LIFE_SETTLED=0,
        PAIR_RATE=0.0,
        MARRY_RATE=0.0,
        CHILD_RATE_MARRIED=0.0,
        CHILD_RATE_TOGETHER=0.0,
        TIE_RATE=0.0,
        PART_RATE_MARRIED={Unions(k): v for k, v in never.items()},
        PART_RATE_TOGETHER={Unions(k): v for k, v in never.items()},
    )


def a_year(state: WorldState, years: float = 1.0, *, seed: int = 2) -> WorldState:
    """What a stretch brings, in one pass of the world's own part, from a season in so that
    nobody is still in the quiet after the player character saw them."""
    since = state.world_s + SEASON
    state.world_s = since + int(years * YEAR)
    lives.live_on(World(state=state, ctx=ctx(), at_s=state.world_s, rng=rng(seed)), since)
    assert check_state(state) == []
    return state


def news(state: WorldState, kind: LifeKind | None = None) -> list[LifeEvent]:
    found = sorted(state.lives.values(), key=lambda e: e.id)
    return [e for e in found if kind is None or e.kind is kind]


def the_village(n: int = 8) -> WorldState:
    return valley(*(villager(f"v{i}", f"Villager {i}", 20 + 3 * i) for i in range(n)))


# --- Time, and nothing made to happen ---------------------------------------------------------


def test_a_month_brings_next_to_nothing_and_ten_years_a_great_deal():
    """Miki, 2026-11-13: "If a month went by, obviously there is no time for such things"."""
    month = [idle(the_village(), 30 * DAY, turn=seed)[0] for seed in range(3, 13)]
    decade = [idle(the_village(), 10 * YEAR, turn=seed)[0] for seed in range(3, 13)]

    assert sum(len(state.lives) for state in month) == 0
    assert all(len(state.lives) >= 2 for state in decade)
    kinds = {event.kind for state in decade for event in state.lives.values()}
    assert kinds == set(LifeKind)


def test_nothing_is_made_to_happen_and_many_are_found_as_they_were_left():
    """Miki, 2026-11-13: "maybe 10 years go by and the person is exactly the same"."""
    unchanged = 0
    for seed in range(3, 13):
        state, _ = idle(the_village(), 10 * YEAR, turn=seed)
        touched = {i for event in state.lives.values() for i in event.subject_ids}
        unchanged += sum(f"v{i}" not in touched for i in range(8))

    assert 25 <= unchanged <= 60  # of eighty people: a good many, and never all


def test_one_person_in_four_is_settled_as_they_are_and_nothing_comes_to_them_alone(
    monkeypatch,
):
    """It is theirs by who they are, for the whole story: no throw decides it."""
    share = sum(lives.settled(villager(f"npc-{n}", "Someone")) for n in range(1000))
    assert 200 <= share <= 300

    sure(monkeypatch, PAIR_RATE=1.0, PAIR_FROM_CAST=1.0, TIE_RATE=1.0)
    state = valley(villager("mara", "Mara", 29), villager("jorn", "Jorn", 33))
    state.characters.pop("bram")
    assert lives.settled(state.characters["mara"]) and not lives.settled(state.characters["jorn"])

    state = a_year(state, 30)

    touched = {i for event in state.lives.values() for i in event.subject_ids}
    assert "mara" not in touched and "jorn" in touched
    assert state.characters["mara"].age == 29 + 30  # older, and otherwise as she was left


def test_the_same_years_play_the_same_way_again():
    first, _ = idle(the_village(), 10 * YEAR)
    again, _ = idle(the_village(), 10 * YEAR)

    assert first.lives and first.lives == again.lives
    assert first.bonds == again.bonds


def test_only_the_latest_news_is_kept(monkeypatch):
    """K8: a long story's state stays flat."""
    state = the_village()
    for n in range(LIVES_KEPT + 5):
        event = LifeEvent(
            id=state.new_id("life"), kind=LifeKind.FRIENDS, subject_ids=["v0", "v1"], world_s=n
        )
        state.lives[event.id] = event
    quiet(monkeypatch)

    a_year(state)

    assert len(state.lives) == LIVES_KEPT
    assert min(event.world_s for event in state.lives.values()) == 5


# --- Growing older (W10) ----------------------------------------------------------------------


def test_everyone_grows_older_with_the_worlds_years(monkeypatch):
    quiet(monkeypatch)
    state = valley(villager("mara", "Mara", 29), villager("nobody", "Wren", None))

    state, _ = idle(state, 10 * YEAR + 40 * DAY)

    ages = {i: c.age for i, c in state.characters.items()}
    assert ages == {YOU: 44, "ilse": 42, "bram": 81, "mara": 39, "nobody": None}
    # A look written with their age at its head keeps the age they are.
    assert state.characters[YOU].appearance.startswith("44, broad shoulders")
    assert state.characters["ilse"].appearance.startswith("42, dark braid")


def test_a_year_counts_once_however_the_time_is_split(monkeypatch):
    quiet(monkeypatch)
    state = valley()

    for until in (200 * DAY, 300 * DAY, 400 * DAY, 2 * YEAR + DAY):
        state, _ = idle(state, until)

    assert state.characters["ilse"].age == 34
    assert state.aged_s == 2 * YEAR


def test_the_dead_stay_the_age_they_died_at_and_a_death_only_presumed_counts_on(monkeypatch):
    quiet(monkeypatch)
    state = valley(villager("mara", "Mara", 29), villager("jorn", "Jorn", 33))
    for who, certainty in (("mara", DeathCertainty.CONFIRMED), ("jorn", DeathCertainty.PRESUMED)):
        person = state.characters[who]
        person.status, person.death_certainty = CharacterStatus.DEAD, certainty
        person.status_history.append(StatusChange(status="dead", turn=1, world_s=0))

    state, _ = idle(state, 5 * YEAR + DAY)

    assert state.characters["mara"].age == 29
    assert state.characters["jorn"].age == 38  # no body was found: they may yet walk in (C1)


def test_someone_born_in_the_story_is_as_old_as_the_years_since(monkeypatch):
    quiet(monkeypatch)
    child = villager("lena", "Mara's child", 0, born_s=100 * DAY)
    child.description = "A newborn, the child of Mara and Jorn."
    state = valley(child)

    state, _ = idle(state, 100 * DAY + 3 * YEAR + DAY)

    assert state.characters["lena"].age == 3
    assert state.characters["lena"].description == "The child of Mara and Jorn."


def test_a_story_already_under_way_starts_counting_from_now(monkeypatch):
    """Nobody is aged for years the record never counted, and whoever the player character
    knows was seen until now, so nothing comes to them out of the blue."""
    quiet(monkeypatch)
    state = valley(villager("mara", "Mara", 29))
    state.world_s = 7 * YEAR  # played before the world counted years

    state, _ = idle(state, 7 * YEAR + 2 * DAY)

    assert state.characters["mara"].age == 29
    assert state.aged_s is not None and state.aged_s >= 7 * YEAR - DAY
    assert state.characters["mara"].seen_s == state.aged_s


# --- A partner --------------------------------------------------------------------------------


def test_someone_single_finds_a_partner_the_record_did_not_have(monkeypatch):
    quiet(monkeypatch)
    sure(monkeypatch, PAIR_RATE=1.0, PAIR_FROM_CAST=0.0)
    state = a_year(valley(villager("mara", "Mara", 29)))

    (event,) = news(state, LifeKind.PAIRED)
    partner = state.characters[event.other("mara")]
    assert partner.name == "Mara's partner" and lives.unnamed(partner)
    assert partner.age >= 25 and partner.location_id == "village"
    assert partner.known_by == ["mara"]  # the player character has yet to hear of them (C6)
    bond = bonds.live(state, "mara", partner.id)
    assert bond.stage is BondStage.TOGETHER and bond.steps[-1].world_s == state.world_s
    assert bonds.partners(state, "mara") == [partner.id]
    # Each has a heart for the other, so the partner stands in a suitor's way (W17).
    assert bonds.heart_for(state, state.characters["mara"], partner.id) >= bonds.SETTLED
    assert check_transition(valley(villager("mara", "Mara", 29)), state) == []


def test_a_partner_may_be_someone_on_record_who_fits(monkeypatch):
    quiet(monkeypatch)
    sure(monkeypatch, PAIR_RATE=1.0, PAIR_FROM_CAST=1.0)
    state = valley(
        villager("mara", "Mara", 29),
        villager("jorn", "Jorn", 33),
        villager("kid", "Tam", 12),
        villager("monk", "Brother Aldo", 30, solitary=True),
        villager("far", "Wen", 30, location_id="city"),
        villager("old", "Hale", 60),
    )
    state.characters["bram"].solitary = True

    state = a_year(state)

    assert bonds.partners(state, "mara") == ["jorn"]
    assert bonds.partners(state, "jorn") == ["mara"]
    # Nobody who doesn't fit was given to anyone on record: a child, a monk, someone far away.
    assert not bonds.partners(state, "kid") and not bonds.partners(state, "monk")
    paired = {i for event in news(state, LifeKind.PAIRED) for i in event.subject_ids}
    assert "kid" not in paired and "monk" not in paired


@pytest.mark.parametrize(
    "who",
    [
        villager("kid", "Tam", 12),
        villager("ageless", "Wren", None),  # F3: only recorded adults
        villager("monk", "Brother Aldo", 30, solitary=True),
        villager("gone", "Mara", 29, status=CharacterStatus.MISSING),
    ],
    ids=["a child", "no age on record", "a vow", "missing"],
)
def test_the_world_gives_no_partner_to_someone_who_would_not_have_one(monkeypatch, who):
    quiet(monkeypatch)
    sure(monkeypatch, PAIR_RATE=1.0)

    state = a_year(valley(who))

    assert news(state) == [] and state.bonds.keys() == {"bond-1"}


def test_close_family_never_pair(monkeypatch):
    quiet(monkeypatch)
    sure(monkeypatch, PAIR_RATE=1.0, PAIR_FROM_CAST=1.0)
    state = valley(
        villager("mara", "Mara", 29, parent_ids=["ma"]),
        villager("jorn", "Jorn", 33, parent_ids=["ma"]),
        villager("ma", "Old Voss", 62, solitary=True),
    )
    state.characters["bram"].solitary = True

    state = a_year(state)

    assert bonds.live(state, "mara", "jorn") is None
    assert len(bonds.partners(state, "mara")) == 1  # someone the record didn't have


def test_whoever_the_player_character_was_with_lately_is_left_alone(monkeypatch):
    """Their days are the story's to tell for a season after: a month away is no time for a
    wedding."""
    quiet(monkeypatch)
    sure(monkeypatch, PAIR_RATE=1.0)
    state = valley(villager("mara", "Mara", 29, seen_s=0))
    world = World(state=state, ctx=ctx(), at_s=SEASON - DAY, rng=rng())

    state.world_s = world.at_s
    lives.live_on(world, 0)
    assert news(state) == []

    state.world_s = world.at_s = SEASON + 30 * DAY
    lives.live_on(world, SEASON - DAY)
    assert [event.kind for event in news(state)] == [LifeKind.PAIRED]


def test_whoever_is_in_the_scene_is_the_storys(monkeypatch):
    quiet(monkeypatch)
    sure(monkeypatch, PAIR_RATE=1.0)
    state = valley(villager("mara", "Mara", 29))
    state.scene.present_ids = [YOU, "mara"]

    assert news(a_year(state)) == []


# --- The player character's own romances are theirs (G15) --------------------------------------


def test_the_player_characters_own_partner_is_never_parted_from_them_nor_given_a_child(
    monkeypatch,
):
    sure(
        monkeypatch,
        PAIR_RATE=1.0,
        MARRY_RATE=1.0,
        CHILD_RATE_MARRIED=1.0,
        PART_RATE_MARRIED=dict.fromkeys(Unions, 1.0),
        TIE_RATE=0.0,
    )
    state = valley()
    state.scene.present_ids = [YOU]
    state.characters[YOU].location_id = "city"  # away for years

    state = a_year(state, 10)

    assert bonds.live(state, YOU, "ilse").stage is BondStage.MARRIED
    assert bonds.partners(state, "ilse") == [YOU]
    assert not [c for c in state.characters.values() if c.parent_ids]


def courted(state: WorldState, *, heart: int) -> WorldState:
    """Tomas has been courting Mara since day 9."""
    bond = Bond(id="bond-9", a_id=YOU, b_id="mara", stage=BondStage.COURTING)
    bond.steps = [
        BondStep(stage=BondStage.INTEREST, world_s=5 * DAY, by_id=YOU),
        BondStep(stage=BondStage.COURTING, world_s=9 * DAY, by_id="mara"),
    ]
    state.bonds[bond.id] = bond
    state.characters["mara"].sheet.disposition.attitudes[YOU] = Attitude(
        affinity=40, trust=30, attraction=heart
    )
    return state


def test_someone_the_player_character_is_courting_is_left_alone_while_they_are_near(
    monkeypatch,
):
    quiet(monkeypatch)
    sure(monkeypatch, PAIR_RATE=1.0)
    state = courted(valley(villager("mara", "Mara", 29)), heart=20)

    assert news(a_year(state, 5)) == []  # the farm is forty minutes from the village


def test_someone_courted_and_left_for_years_may_find_someone_else(monkeypatch):
    """Miki, 2026-11-13: "you cannot expect that someone to stay single"."""
    quiet(monkeypatch)
    sure(monkeypatch, PAIR_RATE=1.0)
    state = courted(valley(villager("mara", "Mara", 29)), heart=20)
    state.characters[YOU].location_id = "city"
    state.scene.present_ids = [YOU]

    state = a_year(state, 5)

    (event,) = news(state, LifeKind.PAIRED)
    assert event.known_by == ["mara", event.other("mara")]  # five days away, nobody told him
    assert bonds.live(state, YOU, "mara").stage is BondStage.COURTING  # as he left it


def test_the_more_their_heart_is_with_the_player_character_the_longer_they_wait(monkeypatch):
    sure(monkeypatch, LIFE_SETTLED=0)

    def found_someone(heart: int) -> int:
        count = 0
        for seed in range(40):
            state = courted(valley(villager("mara", "Mara", 29)), heart=heart)
            state.characters[YOU].location_id = "city"
            state.scene.present_ids = [YOU]
            found = news(a_year(state, 10, seed=seed), LifeKind.PAIRED)
            count += any("mara" in event.subject_ids for event in found)
        return count

    cold, warm, devoted = found_someone(0), found_someone(60), found_someone(100)

    assert cold > warm > devoted == 0


def test_someone_who_found_a_partner_since_keeps_to_them_when_the_suitor_comes_back(
    monkeypatch,
):
    """W17: an answer from before they were a couple isn't an answer to this."""
    quiet(monkeypatch)
    sure(monkeypatch, PAIR_RATE=1.0, PAIR_FROM_CAST=0.0)
    state = courted(valley(villager("mara", "Mara", 29, faith="steadfast")), heart=20)
    state.characters[YOU].location_id = "city"
    state.scene.present_ids = [YOU]
    assert bonds.keeps_to(state, state.characters["mara"], YOU) is None

    state = a_year(state, 5)
    partner = bonds.kept(state, "mara", YOU)
    state.characters["mara"].sheet.disposition.attitudes[partner].attraction = 80

    assert bonds.keeps_to(state, state.characters["mara"], YOU) == partner
    assert bonds.closed_to(state, state.characters["mara"], YOU) is bonds.Closed.BOUND


def test_nobody_past_their_peoples_span_starts_anything_new(monkeypatch):
    """Deaths of old age are still to build. Until they are, the years bring someone who has
    outlived their people's span no new partner, friend or foe, and give them to nobody: a
    hundred years away doesn't come back to a wedding at a hundred and thirty. The span is
    their people's own (G23), a human one where the world doesn't say."""
    quiet(monkeypatch)
    sure(monkeypatch, PAIR_RATE=1.0, PAIR_LATE=1.0, PAIR_FROM_CAST=1.0, TIE_RATE=1.0)

    def elders(**more) -> WorldState:
        state = valley(villager("hale", "Hale", 81, **more), villager("wyn", "Wyn", 84, **more))
        state.characters.pop("bram")
        return state

    assert news(a_year(elders(), 5)) == []

    # One of them in their prime gets no one past it either, on record or new to it.
    state = elders()
    state.characters["wyn"].age = 30
    state = a_year(state, 5)
    assert bonds.live(state, "wyn", "hale") is None
    assert all("hale" not in event.subject_ids for event in news(state))

    # Among a people who live seven hundred years, eighty is young.
    long_lived = elders(people_id="elves")
    long_lived.bible.peoples.append(People(id="elves", name="Elves", lifespan_years=700))
    kinds = {event.kind for event in news(a_year(long_lived, 5))}
    assert kinds == {LifeKind.PAIRED, LifeKind.FRIENDS} or kinds == {LifeKind.PAIRED}


# --- A wedding, a child, a parting --------------------------------------------------------------


def pair(*, stage: BondStage = BondStage.TOGETHER, ages=(29, 33)) -> WorldState:
    state = valley(villager("mara", "Mara", ages[0]), villager("jorn", "Jorn", ages[1]))
    couple(state, "jorn", "mara", stage)
    return state


def test_a_couple_marry(monkeypatch):
    quiet(monkeypatch)
    sure(monkeypatch, MARRY_RATE=1.0)
    before = pair()

    state = a_year(before.model_copy(deep=True))

    bond = bonds.live(state, "mara", "jorn")
    assert [step.stage for step in bond.steps[1:]] == [BondStage.PROMISED, BondStage.MARRIED]
    assert bond.stage is BondStage.MARRIED
    (event,) = news(state)
    assert event.kind is LifeKind.MARRIED and set(event.subject_ids) == {"mara", "jorn"}
    assert YOU in event.known_by  # the farm hears of the village's weddings
    assert check_transition(before, state) == []


def test_a_married_couple_have_children_a_year_apart_and_no_more_than_a_few(monkeypatch):
    quiet(monkeypatch)
    sure(monkeypatch, CHILD_RATE_MARRIED=1.0)
    state = pair(stage=BondStage.MARRIED)

    state = a_year(state)
    (first,) = [c for c in state.characters.values() if c.parent_ids]
    assert first.name == "Jorn's child" and lives.unnamed(first)
    assert (first.age, first.born_s, first.location_id) == (0, state.world_s, "village")
    assert sorted(first.parent_ids) == ["jorn", "mara"]
    assert news(state)[0].kind is LifeKind.CHILD and news(state)[0].child_id == first.id

    world = World(state=state, ctx=ctx(), at_s=state.world_s, rng=rng())
    for _ in range(8):  # eight more passes, half a year apart
        since, state.world_s = state.world_s, state.world_s + YEAR // 2
        world.at_s = state.world_s
        lives.live_on(world, since)

    children = sorted(
        (c for c in state.characters.values() if c.parent_ids), key=lambda c: c.born_s
    )
    assert len(children) == MOST_CHILDREN
    assert all(b.born_s - a.born_s >= YEAR for a, b in zip(children, children[1:], strict=False))
    assert [c.age for c in children] == [4, 3, 2]  # each as old as the years since
    assert check_state(state) == []


@pytest.mark.parametrize("ages", [(29, 60), (None, 33)], ids=["past it", "no age on record"])
def test_only_recorded_adults_in_the_prime_of_life_have_children(monkeypatch, ages):
    quiet(monkeypatch)
    sure(monkeypatch, CHILD_RATE_MARRIED=1.0)

    state = a_year(pair(stage=BondStage.MARRIED, ages=ages), 3)

    assert news(state) == []


def test_a_couple_part_by_the_custom_of_the_world_and_the_colder_heart_ends_it(monkeypatch):
    quiet(monkeypatch)
    sure(monkeypatch, PART_RATE_MARRIED=dict.fromkeys(Unions, 1.0))
    state = pair(stage=BondStage.MARRIED)
    state.bible.unions = Unions.EASY
    state.characters["mara"].sheet.disposition.attitudes["jorn"] = Attitude(attraction=20)
    state.characters["jorn"].sheet.disposition.attitudes["mara"] = Attitude(
        affinity=60, attraction=70
    )

    state = a_year(state)

    (bond,) = [b for b in state.bonds.values() if b.holds("mara")]
    assert (bond.stage, bond.end) == (BondStage.OVER, BondEnd.PARTED)
    assert bond.steps[-1].by_id == "mara"
    left = state.characters["jorn"].attitude_toward("mara")
    assert (left.affinity, left.attraction) == (
        60 - bonds.PARTED_COUPLE,
        70 - bonds.PARTED_HEART_COUPLE,
    )
    (event,) = news(state)
    assert (event.kind, event.by_id, event.subject_ids) == (
        LifeKind.PARTED,
        "mara",
        ["mara", "jorn"],
    )
    assert (lives.said(event, "mara"), lives.said(event, "jorn")) == (
        "left their partner",
        "was left by their partner",
    )


def test_nobody_leaves_a_marriage_that_is_for_life():
    """A2: the facts settle it, whatever the hearts. The custom's own numbers, over a
    lifetime."""
    for seed in range(20):
        state = pair(stage=BondStage.MARRIED)
        state.bible.unions = Unions.FOR_LIFE
        state.characters["mara"].sheet.disposition.attitudes["jorn"] = Attitude(attraction=5)

        state = a_year(state, 40, seed=seed)

        assert bonds.live(state, "mara", "jorn").stage is BondStage.MARRIED


def test_couples_part_more_where_they_part_easily_and_more_where_a_heart_is_cold():
    def parted(unions: Unions, heart: int) -> int:
        count = 0
        for seed in range(60):
            state = pair(stage=BondStage.MARRIED, ages=(50, 52))
            state.bible.unions = unions
            for a, b in (("mara", "jorn"), ("jorn", "mara")):
                state.characters[a].sheet.disposition.attitudes[b] = Attitude(attraction=heart)
            count += bool(news(a_year(state, 20, seed=seed), LifeKind.PARTED))
        return count

    held, easy, cold = parted(Unions.HELD, 80), parted(Unions.EASY, 80), parted(Unions.EASY, 20)

    assert held < easy < cold


# --- Friends and foes ---------------------------------------------------------------------------


def neighbours() -> WorldState:
    state = valley(villager("mara", "Mara", 29), villager("jorn", "Jorn", 33))
    state.characters.pop("bram")
    return state


def test_two_of_the_same_place_become_close_friends(monkeypatch):
    quiet(monkeypatch)
    sure(monkeypatch, TIE_RATE=1.0, TIE_WARM=1.0)

    state = a_year(neighbours())

    (event,) = news(state)
    assert event.kind is LifeKind.FRIENDS and set(event.subject_ids) == {"mara", "jorn"}
    for a, b in (("mara", "jorn"), ("jorn", "mara")):
        assert state.characters[a].attitude_toward(b).affinity >= lives.FRIEND_AT
    # They are friends for good: the world doesn't make them so twice.
    assert news(a_year(state)) == [event]


def test_two_of_the_same_place_fall_out_for_good(monkeypatch):
    quiet(monkeypatch)
    sure(monkeypatch, TIE_RATE=1.0, TIE_WARM=0.0)

    state = a_year(neighbours())

    (event,) = news(state)
    assert event.kind is LifeKind.FELL_OUT
    for a, b in (("mara", "jorn"), ("jorn", "mara")):
        assert state.characters[a].attitude_toward(b).affinity <= lives.FOE_AT


def test_family_fall_out_and_never_fall_into_friendship(monkeypatch):
    quiet(monkeypatch)
    state = neighbours()
    state.characters["mara"].parent_ids = ["jorn"]
    state.characters["jorn"].age = 55

    sure(monkeypatch, TIE_RATE=1.0, TIE_WARM=1.0)
    assert news(a_year(state)) == []

    sure(monkeypatch, TIE_WARM=0.0)
    assert [event.kind for event in news(a_year(state))] == [LifeKind.FELL_OUT]


def test_nothing_touches_how_anyone_feels_about_the_player_character(monkeypatch):
    sure(monkeypatch, TIE_RATE=1.0, PAIR_RATE=1.0, LIFE_SETTLED=0)
    state = neighbours()
    for who in ("mara", "jorn"):
        state.characters[who].sheet.disposition.attitudes[YOU] = Attitude(affinity=35, trust=20)
    before = {i: c.attitude_toward(YOU) for i, c in state.characters.items()}
    yours = state.characters[YOU].model_dump(exclude={"age", "appearance"})

    state = a_year(state, 10)

    assert all(state.characters[i].attitude_toward(YOU) == was for i, was in before.items())
    assert state.characters[YOU].model_dump(exclude={"age", "appearance"}) == yours
    assert not [event for event in news(state) if YOU in event.subject_ids]


# --- Who has heard (C6) -------------------------------------------------------------------------


def test_the_player_character_hears_at_once_what_comes_to_someone_near(monkeypatch):
    quiet(monkeypatch)
    sure(monkeypatch, MARRY_RATE=1.0)
    state = a_year(pair())

    (event,) = news(state)
    assert lives.heard_in(state, ctx().turn) == [event]
    assert lives.heard_in(state, ctx().turn + 1) == []  # news of its own turn, told once
    assert lives.unheard(state, "mara") == []


def test_what_comes_to_someone_they_have_never_heard_of_is_no_talk_of_theirs(monkeypatch):
    """C6: the farm hears of the village's weddings when it knows one of the two. Two key
    people of the story marry next door whom the player character has never heard of, and
    no word of it is theirs: nothing tells them such people exist."""
    quiet(monkeypatch)
    sure(monkeypatch, MARRY_RATE=1.0)
    strangers = pair()
    for who in ("mara", "jorn"):
        person = strangers.characters[who]
        person.known_by, person.met_by, person.prominence = [], [], Prominence.KEY

    strangers = a_year(strangers)

    (event,) = news(strangers)
    assert event.known_by == ["jorn", "mara"]
    assert lives.heard_in(strangers, ctx().turn) == []

    # Jorn he knows, and Jorn's wedding is the village's talk, whoever the bride is.
    one = pair()
    one.characters["mara"].known_by, one.characters["mara"].met_by = [], []
    (event,) = news(a_year(one))
    assert YOU in event.known_by


def test_far_away_they_hear_it_when_they_next_meet_one_of_the_two(monkeypatch):
    quiet(monkeypatch)
    sure(monkeypatch, MARRY_RATE=1.0)
    state = pair()
    state.characters[YOU].location_id = "city"
    state.scene.present_ids = [YOU]

    state = a_year(state)

    (event,) = news(state)
    assert lives.heard_in(state, ctx().turn) == []
    assert lives.unheard(state, "mara") == lives.unheard(state, "jorn") == [event]

    # A scene with someone else changes nothing of it.
    state.scene.present_ids = [YOU, "bram"]
    met_bram, heard = pipeline.settle_lives(state)
    assert heard == [] and lives.unheard(met_bram, "mara") == [event]
    assert met_bram.characters["bram"].seen_s == state.world_s

    state.scene.present_ids = [YOU, "jorn"]
    met, heard = pipeline.settle_lives(state)
    assert heard == [event.id]
    assert lives.unheard(met, "mara") == lives.unheard(met, "jorn") == []
    assert met.characters["jorn"].seen_s == state.world_s
    assert met.characters["mara"].seen_s == state.characters["mara"].seen_s  # she wasn't there
    assert lives.unheard(state, "mara") == [event]  # the state it was handed is untouched
    assert check_transition(state, met) == []


def test_what_came_to_a_stranger_before_they_met_is_no_news(monkeypatch):
    """News is of someone the player character knew. What came to a stranger is who they
    are: no scene is told it as news, meeting them hears nothing, and a later scene with
    them doesn't bring it up as new either."""
    quiet(monkeypatch)
    sure(monkeypatch, MARRY_RATE=1.0)
    state = pair()
    state.characters["mara"].met_by = []  # he knows of Jorn's sweetheart, and never met her
    state.characters[YOU].location_id = "city"
    state.scene.present_ids = [YOU]

    state = a_year(state)

    (event,) = news(state)
    mara, jorn = state.characters["mara"], state.characters["jorn"]
    assert lives.news_of(state, mara) == []
    assert lives.news_of(state, jorn) == [event]  # Jorn he knew: it is news of him

    state.scene.present_ids = [YOU, "mara"]
    met, heard = pipeline.settle_lives(state)
    assert heard == []
    assert met.characters["mara"].seen_s == met.world_s
    assert lives.news_of(met, met.characters["mara"]) == []  # still none, now they have met
    assert lives.unheard(met, "jorn") == [event]  # and still Jorn's to tell


def test_someone_met_on_the_way_was_seen_then_though_the_scene_ended_without_them(monkeypatch):
    """A turn can reach someone where they are and end somewhere else. The two were together
    when they met, so the years after it are news of someone the player character knows."""
    quiet(monkeypatch)
    sure(monkeypatch, PAIR_RATE=1.0, PAIR_FROM_CAST=0.0)
    state = valley(Character(id="wen", name="Wen", age=30, location_id="village"))
    state.world_s = 3 * DAY
    meeting = CharacterChange(id="wen", meets_player=True)
    applied = apply_delta(
        state, StateDelta(characters=[meeting]), ctx(), source=NARRATOR, reached=["wen"]
    )
    assert not applied.rejected
    state, heard = pipeline.settle_lives(applied.state)  # the scene ends at the farm, without her
    assert heard == [] and state.characters["wen"].seen_s == 3 * DAY

    state.characters[YOU].location_id = "city"
    state.scene.present_ids = [YOU]
    state = a_year(state, 5)

    (event,) = news(state, LifeKind.PAIRED)
    assert lives.news_of(state, state.characters["wen"]) == [event]


def test_someone_who_takes_over_the_story_grew_up_knowing_their_own_people(monkeypatch):
    """N6: with a successor, whom the last player character was with is nothing to them.
    Whoever they have met they were with until now, and they know what came to them."""
    quiet(monkeypatch)
    sure(monkeypatch, MARRY_RATE=1.0)
    state = pair()
    state.characters[YOU].location_id = "city"
    state.scene.present_ids = [YOU]
    state = a_year(state)
    (event,) = news(state)
    heir = villager("lena", "Lena", 19, parent_ids=["mara"])
    heir.met_by = ["mara", "lena"]
    state.characters["lena"] = heir
    state.characters["mara"].met_by.append("lena")

    after = carry_on(state, heir, "Dawn at the mill.", ending="chosen", turn=9)

    assert after.player_id == "lena"
    assert "lena" in after.lives[event.id].known_by  # her mother's wedding is no news to her
    assert lives.news_of(after, after.characters["mara"]) == []
    assert after.characters["mara"].seen_s == after.world_s
    # Bram, whom only Tomas knew, was last seen by nobody who matters now.
    assert after.characters["bram"].seen_s is None
    assert state.lives[event.id].known_by == ["jorn", "mara"]  # the state before is untouched


def test_a_day_in_town_makes_nobody_a_neighbour_there(monkeypatch):
    """Nobody on record has a home, and the world sends people out and back (`returns`). While
    it has someone out, they live where they set out from: a child of theirs is at home, not
    where its father happened to be, and the player character in that town hears nothing."""
    quiet(monkeypatch)
    sure(monkeypatch, CHILD_RATE_MARRIED=1.0)
    state = pair(stage=BondStage.MARRIED)
    state.characters[YOU].location_id = "city"
    state.scene.present_ids = [YOU]
    jorn = state.characters["jorn"]
    jorn.location_id = "city"  # a few days in Harrowgate, the world's doing, and due back
    out = World(state=state, ctx=ctx(), at_s=state.world_s, rng=rng(1))
    assert returns.left(out, jorn, "village", (DAY, DAY)) is not None

    lives.live_on(World(state=state, ctx=ctx(), at_s=YEAR, rng=rng(2)), SEASON)

    (event,) = news(state, LifeKind.CHILD)
    assert state.characters[event.child_id].location_id == "village"
    assert event.known_by == ["jorn", "mara"]
    assert check_state(state) == []


def test_a_scene_with_nobody_in_it_settles_nothing():
    state = valley()
    state.scene.present_ids = [YOU]

    settled, heard = pipeline.settle_lives(state)

    assert settled is state and heard == []


# --- The record holds together (C1) --------------------------------------------------------------


def test_news_about_someone_who_is_not_on_record_is_refused():
    state = valley()
    state.lives["life-1"] = LifeEvent(id="life-1", kind=LifeKind.MARRIED, subject_ids=["ghost"])

    assert [(v.subject, v.rule) for v in check_state(state)] == [("life life-1", "reference")]


def test_a_partner_the_world_brought_is_unnamed_until_the_story_names_them():
    partner = villager("p", "Mara's partner", origin=Origin(kind=OriginKind.ENGINE, ref_id="mara"))
    named = partner.model_copy(update={"name": "Lena Hale", "aliases": ["Mara's partner"]})
    someone = villager("q", "The miller's partner")  # a name the story gave

    assert lives.unnamed(partner)
    assert not lives.unnamed(named) and not lives.unnamed(someone)


def test_the_story_names_a_partner_the_world_brought_under_their_id(monkeypatch):
    """The narrator gives "Mara's partner" a name when a scene first tells of them, as it
    does a newborn: the record keeps one person, and Memory can then say who Mara found."""
    quiet(monkeypatch)
    sure(monkeypatch, PAIR_RATE=1.0, PAIR_FROM_CAST=0.0)
    state = a_year(valley(villager("mara", "Mara", 29)), 5)
    (event,) = news(state, LifeKind.PAIRED)
    partner = event.other("mara")
    assert lives.unnamed(state.characters[partner])

    naming = CharacterChange(id=partner, name="Edrik Hale", known_to_player=True)
    applied = apply_delta(state, StateDelta(characters=[naming]), ctx(), source=NARRATOR)

    named = applied.state.characters[partner]
    assert not applied.rejected
    assert (named.name, named.aliases) == ("Edrik Hale", ["Mara's partner"])
    assert not lives.unnamed(named) and YOU in named.known_by
    assert bonds.partners(applied.state, "mara") == [partner]
    assert check_transition(state, applied.state) == []

"""What the player character knows of the world's ladders (G18, C6): `engine.path`."""

import pytest

from engine import path, pipeline
from engine.base import DAY
from engine.samples import cultivation_world, grounded_world
from engine.state import Fact, FactKind, Rumor, RungHeard


@pytest.mark.parametrize(
    ("text", "name"),
    [
        ("The elders stand in the Golden Core realm.", "Golden Core"),
        ("They call it GOLDEN CORE, and nobody below may say it.", "Golden Core"),
        ("Two knights rode by.", "Knight"),
        ("Los caballeros del reino no hablan con huérfanos.", "Caballero"),
        ("La técnica pide un Núcleo Dorado.", "Núcleo Dorado"),
        ("He is level 1 now.", "Level 1"),
        ("An A-rank hunter took the job.", "A"),
        ("She made rank A last spring.", "A"),
        ("Un cazador de rango S.", "S"),
    ],
)
def test_a_scene_names_a_rung(text, name):
    assert path.named(text, name)


@pytest.mark.parametrize(
    ("text", "name"),
    [
        ("A golden corelike thing rolls off the table.", "Golden Core"),
        ("The core was golden.", "Golden Core"),
        ("He is level 12 now.", "Level 1"),
        ("A man walked in.", "A"),
        ("Rank amateurs, all of them.", "A"),
        ("She said so.", "S"),
        ("Nothing here.", ""),
    ],
)
def test_words_that_only_look_like_a_rung_name_it_not(text, name):
    assert not path.named(text, name)


def heard_of(state):
    return [(h.ladder_id, h.rung, h.known_s is not None) for h in state.player.sheet.rungs_heard]


def test_a_rung_a_scene_names_is_heard_of_from_then_on():
    # C6: what the player read is what the character heard, once.
    state = cultivation_world()
    state.world_s = 3 * DAY

    told = path.hear(state, "“The elders sit in Core Formation,” the old man says.")

    assert told == [path.Told("realms", 2, known=False)]
    (heard,) = state.player.sheet.rungs_heard
    assert (heard.rung, heard.heard_s, heard.known_s, heard.known_from) == (2, 3 * DAY, None, None)
    # Told again, or a scene with nothing to say, adds nothing.
    assert path.hear(state, "Core Formation, he says again, Core Formation.") == []
    assert path.hear(state, "") == []
    assert heard_of(state) == [("realms", 2, False)]


def test_their_own_rung_and_the_ones_under_it_are_never_news():
    state = cultivation_world()
    state.player.sheet.ladders[0].rung = 1

    assert path.hear(state, "Qi Condensation, then Foundation Establishment, as everyone.") == []
    assert state.player.sheet.rungs_heard == []


def test_a_rung_is_known_once_someone_who_shows_it_has_stood_before_them():
    # Lin has met Zhao, who stands on Foundation Establishment: its name is all he lacked.
    state = cultivation_world()
    told = path.hear(state, "“Foundation Establishment is no gift,” Zhao says.")

    assert told == [
        path.Told("realms", 1, known=False),
        path.Told("realms", 1, known=True, before="zhao"),
    ]
    (heard,) = state.player.sheet.rungs_heard
    assert (heard.known_s, heard.known_from) == (state.world_s, "zhao")

    # Elder Mo stands on Core Formation and Lin has never met him: only heard of.
    path.hear(state, "Core Formation is where the elders sit.")
    assert heard_of(state) == [("realms", 1, True), ("realms", 2, False)]
    # A later scene puts the elder before him, and says nothing of realms.
    state.world_s += DAY
    state.scene.present_ids = ["elder-mo"]
    assert path.hear(state, "The old man looks up from his tea.") == [
        path.Told("realms", 2, known=True, before="elder-mo")
    ]
    assert state.player.sheet.rungs_heard[1].known_s == state.world_s


def test_someone_who_hides_their_strength_confirms_nothing():
    # G20: the world measures a hider by the rung they show.
    state = cultivation_world()
    state.characters["elder-mo"].sheet.ladders[0].shown_rung = 0
    state.scene.present_ids = ["elder-mo"]

    path.hear(state, "They say Core Formation changes a man.")

    assert heard_of(state) == [("realms", 2, False)]


def test_the_rungs_they_know_of_leave_room_for_the_ones_nobody_named():
    state = cultivation_world()
    state.player.sheet.rungs_heard = [RungHeard(ladder_id="realms", rung=3, heard_s=DAY)]
    realms = state.bible.ladders[0]

    (soul,) = path.known(state, state.player, realms)
    assert (soul.rung, soul.known, soul.heard_s, soul.gap_below) == (3, False, DAY, True)

    # The rung right over their own has no room under it.
    state.player.sheet.rungs_heard.append(RungHeard(ladder_id="realms", rung=1, heard_s=DAY))
    assert [(s.rung, s.gap_below) for s in path.known(state, state.player, realms)] == [
        (1, False),
        (3, True),
    ]


def test_what_they_know_for_sure_names_a_rung_and_a_belief_only_says_so():
    state = cultivation_world()
    realms = state.bible.ladders[0]
    state.facts["f-core"] = Fact(
        id="f-core", text="Elder Mo reached Core Formation in his sixtieth year.", known_by=["lin"]
    )
    state.facts["f-soul"] = Fact(
        id="f-soul",
        text="The sect master has stood in Nascent Soul for a century.",
        kind=FactKind.BELIEF,
        known_by=["lin"],
    )
    state.facts["f-else"] = Fact(
        id="f-else", text="Soul Transformation is a story for children.", known_by=["zhao"]
    )

    assert [(s.rung, s.known, s.heard_s) for s in path.known(state, state.player, realms)] == [
        (2, True, None),
        (3, False, None),
    ]


def test_what_they_have_heard_about_a_rung_comes_latest_first():
    state = cultivation_world()
    state.facts["f-pill"] = Fact(
        id="f-pill",
        text="Master Wen reached Foundation Establishment with a pill and nine days alone.",
        known_by=["lin"],
        world_s=DAY,
    )
    state.rumors["r-storm"] = Rumor(
        id="r-storm",
        text="A wandering swordsman reached Foundation Establishment alone, in a storm.",
        is_true=False,
        heard_at={"lin": 2 * DAY},
    )
    state.rumors["r-other"] = Rumor(
        id="r-other", text="Foundation Establishment is a lie.", is_true=False, heard_at={"zhao": 1}
    )

    assert path.about(state, state.player, "Foundation Establishment") == [
        "A wandering swordsman reached Foundation Establishment alone, in a storm.",
        "Master Wen reached Foundation Establishment with a pill and nine days alone.",
    ]
    assert path.about(state, state.player, "Core Formation") == []


def test_settling_the_path_leaves_the_state_alone_when_the_scene_adds_nothing():
    state = cultivation_world()

    same, nothing = pipeline.settle_path(state, "Rain on the roof tiles.")
    assert same is state and nothing == []

    settled, told = pipeline.settle_path(state, "Core Formation, the old man says.")
    assert settled is not state and state.player.sheet.rungs_heard == []
    assert [(t.ladder_id, t.rung, t.known) for t in told] == [("realms", 2, False)]
    assert heard_of(settled) == [("realms", 2, False)]

    # A world with no ladder has no path to tell.
    plain = grounded_world()
    assert pipeline.settle_path(plain, "Core Formation.") == (plain, [])

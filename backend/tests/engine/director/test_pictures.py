"""M1, M2: code decides when a picture appears, within the story's budget and its setting."""

from engine.context import ImageSetting
from engine.contracts import (
    DirectorPlan,
    EventKind,
    EventSource,
    PictureDecision,
    PictureKind,
    PictureTrigger,
    PlannedEvent,
)
from engine.director import rules
from engine.director.pictures import decide_picture, settle_look
from engine.samples import cultivation_world, farm_world
from engine.state import (
    CharacterSheet,
    CharacterStatus,
    Deed,
    Encounter,
    EncounterKind,
    EventSize,
    Gain,
    PlaceStatus,
    PowerAxes,
    Prominence,
    StatusChange,
    Visibility,
)
from tests.engine.director.helpers import ctx
from tests.engine.director.test_threads import facts

SEEN = ["portrait:tomas", "portrait:ilse", "cover", "place:farm"]


def picture(state, turn, *, event=None, closed=(), images=ImageSetting.KEY_MOMENTS, **kw):
    """The scene's picture, and the director's memory after it, recorded into the state."""
    memory = state.director.model_copy(deep=True)
    decision = decide_picture(
        state,
        ctx(turn, images=images),
        facts(turn, **kw),
        memory,
        event=event,
        closed_threads=list(closed),
    )
    state.director = memory
    return decision


def big_deed(turn: int) -> Deed:
    return Deed(
        id=f"deed-{turn}", actor_id="tomas", kind="burn", text="", turn=turn, world_s=0, severity=4
    )


def quiet_farm():
    state = farm_world()
    state.director.pictured = list(SEEN)
    return state


def test_pictures_off_means_none_at_all():
    state = farm_world()
    for turn in range(1, 20):
        assert picture(state, turn, images=ImageSetting.OFF, deeds=(big_deed(turn),)) is None


def test_portraits_places_and_the_cover_come_once_each_outside_the_budget():
    state = farm_world()
    state.director.picture_credit = 0
    seen = [picture(state, turn) for turn in range(1, 7)]
    assert [(p.trigger, p.subject_id) for p in seen if p] == [
        (PictureTrigger.STORY_START, "tomas"),
        (PictureTrigger.COVER, None),
        (PictureTrigger.FIRST_MEETING, "ilse"),
        (PictureTrigger.FIRST_VISIT, "farm"),
    ]
    assert state.director.picture_credit > 0  # none of them spent the key-scene budget


def test_key_scenes_stay_within_about_one_picture_per_ten_turns():
    for images, every in ((ImageSetting.KEY_MOMENTS, 10), (ImageSetting.MORE, 5)):
        state = quiet_farm()
        count = sum(
            picture(state, turn, images=images, deeds=(big_deed(turn),)) is not None
            for turn in range(2, 102)
        )
        # A big deed every single turn still gets about one picture per `every` turns.
        assert 100 // every - 1 <= count <= 100 // every + rules.PICTURE_CAP[images], images


def test_a_big_deed_by_the_player_gets_a_key_scene():
    state = quiet_farm()
    decision = picture(state, 2, deeds=(big_deed(2),))
    assert decision.kind is PictureKind.SCENE and decision.trigger is PictureTrigger.BIG_DEED
    assert decision.subject_id == "deed-2"
    small = big_deed(3).model_copy(update={"severity": 3})
    assert picture(state, 13, deeds=(small,)) is None


def key_fight(state, opponent="bram", key=True, started_turn=5):
    state.characters[opponent].location_id = "farm"
    state.scene.present_ids.append(opponent)
    state.scene.encounter = Encounter(
        kind=EncounterKind.FIGHT,
        opponent_ids=[opponent],
        started_turn=started_turn,
        started_s=0,
        key=key,
    )


def test_a_key_fight_gets_its_start_and_its_decisive_blow_even_with_the_budget_spent():
    state = quiet_farm()
    state.director.picture_credit = 0
    key_fight(state)
    start = picture(state, 5)
    assert start.trigger is PictureTrigger.FIGHT_START and start.subject_id == "bram"
    assert picture(state, 6) is None  # exchanges in between get nothing
    blow = picture(state, 7, gravely_hurt=frozenset({"bram"}))
    assert blow.trigger is PictureTrigger.DECISIVE_BLOW and blow.subject_id == "bram"
    # One decisive blow per fight, and the borrowed credit is paid back over the next turns.
    assert picture(state, 8, gravely_hurt=frozenset({"bram"})) is None
    assert state.director.picture_credit >= rules.PICTURE_FLOOR
    state.scene.encounter = None
    assert picture(state, 9, deeds=(big_deed(9),)) is None
    assert state.director.fight is None


def test_only_a_fight_with_a_key_npc_or_a_strong_monster_is_pictured():
    state = quiet_farm()
    key_fight(state, key=False)
    assert picture(state, 5) is None  # an ordinary scuffle with the neighbour
    state = quiet_farm()
    key_fight(state, key=False)
    state.characters["bram"].sheet = CharacterSheet(axes=PowerAxes(might=4))
    assert picture(state, 5).trigger is PictureTrigger.FIGHT_START  # far stronger than Tomas
    state = quiet_farm()
    key_fight(state, key=False)
    state.characters["bram"].prominence = Prominence.KEY
    assert picture(state, 5).trigger is PictureTrigger.FIGHT_START


def died(state, character_id, turn, known_by=("tomas",)):
    character = state.characters[character_id]
    character.status = CharacterStatus.DEAD
    character.status_history.append(
        StatusChange(status="dead", turn=turn, world_s=0, known_by=list(known_by))
    )


def test_a_key_characters_death_the_player_knows_of_is_pictured():
    state = quiet_farm()
    died(state, "ilse", 3)
    decision = picture(state, 3, died=frozenset({"ilse"}))
    assert decision.trigger is PictureTrigger.DEATH and decision.subject_id == "ilse"

    # A minor character's death, or a death far away that nobody told the player of, is not.
    state = quiet_farm()
    died(state, "bram", 3)
    assert picture(state, 3, died=frozenset({"bram"})) is None
    state = quiet_farm()
    state.characters["ilse"].location_id = "village"
    state.scene.present_ids = ["tomas"]
    died(state, "ilse", 3, known_by=())
    assert picture(state, 3, died=frozenset({"ilse"})) is None


def test_a_local_or_world_event_is_pictured_and_a_personal_one_is_not():
    def event(size):
        return PlannedEvent(
            size=size,
            kind=EventKind.DISASTER,
            source=EventSource.DECK,
            title="The river rises",
            brief="",
            thread_id="thread-1",
        )

    state = quiet_farm()
    assert picture(state, 2, event=event(EventSize.PERSONAL)) is None
    decision = picture(state, 3, event=event(EventSize.LOCAL))
    assert decision.trigger is PictureTrigger.EVENT and decision.subject_id == "thread-1"
    # A world event that came due has a pending event behind it, which is no subject to draw.
    world = event(EventSize.LOCAL).model_copy(
        update={"thread_id": None, "source": EventSource.DUE, "source_id": "event-7"}
    )
    state.director.picture_credit = 1
    decision = picture(state, 4, event=world)
    assert decision.trigger is PictureTrigger.EVENT and decision.subject_id is None


def change_place(state, place_id, status, turn=2):
    """A status change as `engine.apply` records it (W7, C1)."""
    place = state.places[place_id]
    place.status_history.append(
        StatusChange(status=status.value, from_status=place.status.value, turn=turn, world_s=0)
    )
    place.status = status


def test_a_place_that_changed_for_good_is_pictured_again_once():
    state = quiet_farm()
    change_place(state, "farm", PlaceStatus.RUINED)
    decision = picture(state, 2)
    assert decision.trigger is PictureTrigger.PLACE_CHANGED and decision.kind is PictureKind.PLACE
    assert (decision.subject_id, decision.version) == ("farm", 2)
    assert "place:farm:v2" in state.director.pictured
    assert picture(state, 3) is None  # every return reuses it
    # Rebuilt (C1), it is drawn once more; a place that was only damaged keeps its picture.
    state.director.picture_credit = 1
    change_place(state, "farm", PlaceStatus.THRIVING, turn=20)
    assert picture(state, 20).version == 3
    state.director.picture_credit = 1
    change_place(state, "farm", PlaceStatus.DAMAGED, turn=30)
    assert picture(state, 30) is None


def test_a_changed_place_waits_for_the_budget_while_the_player_is_there():
    """M2: drawing a changed place again spends a key-scene credit, so churn can't run up costs."""
    state = quiet_farm()
    state.director.pictured.append("place:village")
    state.director.picture_credit = 0
    change_place(state, "farm", PlaceStatus.OCCUPIED)
    assert picture(state, 2) is None
    state.player.location_id = state.scene.place_id = "village"
    assert all(picture(state, turn) is None for turn in range(3, 20))  # away, nothing to see
    state.player.location_id = state.scene.place_id = "farm"
    decision = picture(state, 20)
    assert decision.trigger is PictureTrigger.PLACE_CHANGED and decision.version == 2
    assert state.director.picture_credit < 1


def test_the_first_visit_to_a_ruined_place_draws_it_as_it_is_now():
    state = quiet_farm()
    state.director.pictured = ["portrait:tomas", "portrait:ilse", "cover"]
    state.director.picture_credit = 0
    change_place(state, "farm", PlaceStatus.RUINED)
    decision = picture(state, 2)
    assert (decision.trigger, decision.version) == (PictureTrigger.FIRST_VISIT, 2)
    assert {"place:farm", "place:farm:v2"} <= set(state.director.pictured)
    assert state.director.picture_credit > 0  # a first visit is outside the budget
    assert picture(state, 3) is None


def test_a_place_pictured_before_versions_existed_is_not_drawn_again():
    state = quiet_farm()  # remembers only "place:farm", as stories did before look versions
    assert all(picture(state, turn) is None for turn in range(2, 6))


def test_portraits_and_places_carry_their_look_version():
    state = farm_world()
    state.characters["ilse"].look_version = 3
    seen = [picture(state, turn) for turn in range(1, 5)]
    assert [(p.trigger, p.subject_id, p.version) for p in seen if p] == [
        (PictureTrigger.STORY_START, "tomas", 1),
        (PictureTrigger.COVER, None, None),
        (PictureTrigger.FIRST_MEETING, "ilse", 3),
        (PictureTrigger.FIRST_VISIT, "farm", 1),
    ]
    assert {"portrait:ilse", "portrait:ilse:v3", "place:farm:v1"} <= set(state.director.pictured)
    assert picture(state, 5) is None  # met at the look she has now: no redraw


def test_a_face_that_changed_for_good_is_drawn_once_more():
    """M5: the player's or a present key NPC's portrait, once per change, within the budget."""
    state = quiet_farm()
    state.player.look_version = 2
    decision = picture(state, 2)
    assert decision.kind is PictureKind.PORTRAIT and decision.trigger is PictureTrigger.LOOK_CHANGED
    assert (decision.subject_id, decision.version) == ("tomas", 2)
    state.director.picture_credit = 1
    assert picture(state, 3) is None  # once per change

    state.characters["ilse"].look_version = 2
    decision = picture(state, 4)
    assert (decision.trigger, decision.subject_id) == (PictureTrigger.LOOK_CHANGED, "ilse")
    assert decision.version == 2


def test_a_changed_face_waits_until_they_are_seen_and_the_budget_allows():
    state = quiet_farm()
    state.characters["ilse"].look_version = 2
    state.scene.present_ids = ["tomas"]
    state.characters["ilse"].location_id = "village"
    assert picture(state, 2) is None  # not in the scene
    assert picture(state, 2, touched=frozenset({"ilse"})) is None  # named in a deed, still away
    state.scene.present_ids = ["tomas", "ilse"]
    state.director.picture_credit = 0
    assert picture(state, 3) is None  # no credit yet
    state.director.picture_credit = 1
    assert picture(state, 4).trigger is PictureTrigger.LOOK_CHANGED
    died(state, "ilse", 5)
    state.characters["ilse"].look_version = 3
    state.director.picture_credit = 1
    assert picture(state, 6) is None  # the dead are not drawn again


def test_a_face_never_pictured_is_not_redrawn():
    state = quiet_farm()
    state.director.pictured = ["portrait:ilse", "cover", "place:farm"]  # pictures were off at 1
    state.player.look_version = 2
    assert picture(state, 2) is None


def test_an_arc_ending_and_a_breakthrough_are_key_scenes():
    state = quiet_farm()
    assert picture(state, 2, closed=["thread-x"]) is None  # a thread the state doesn't hold
    world = cultivation_world()
    world.director.pictured = ["portrait:lin", "cover", "place:well", "portrait:zhao"]
    gain = Gain(what="realms", change="Foundation Establishment", source="", reason="", turn=4)
    decision = picture(world, 4, gains=(("lin", gain),))
    assert decision.trigger is PictureTrigger.BREAKTHROUGH
    world.director.picture_credit = 1  # the budget refilled over the turns in between
    decision = picture(world, 15, closed=["tournament"])
    assert decision.trigger is PictureTrigger.ARC_END and decision.subject_id == "tournament"


def test_hidden_strength_revealed_needs_the_player_to_see_it():
    world = cultivation_world()
    world.director.pictured = ["portrait:lin", "cover", "place:well", "portrait:zhao"]
    reveal = Deed(
        id="deed-1",
        actor_id="zhao",
        kind="reveal power",
        text="",
        turn=3,
        world_s=0,
        visibility=Visibility.PUBLIC,
        known_by=[],
    )
    assert picture(world, 3, deeds=(reveal,)) is None
    seen = reveal.model_copy(update={"known_by": ["lin"]})
    assert picture(world, 3, deeds=(seen,)).trigger is PictureTrigger.STRENGTH_REVEALED


def plan_with(decision):
    return DirectorPlan(picture=decision)


def test_a_scene_that_changes_the_look_it_pictures_draws_the_new_look_once():
    """The director decides before the scene is told; the narrator's update can still leave a
    scar on the person met or occupy the place visited. The plan follows, and so does memory."""
    state = farm_world()
    state.director.pictured = ["portrait:tomas", "portrait:tomas:v1", "cover"]
    meeting = picture(state, 2)
    assert (meeting.trigger, meeting.subject_id, meeting.version) == (
        PictureTrigger.FIRST_MEETING,
        "ilse",
        1,
    )
    state.characters["ilse"].look_version = 2  # the scene's own update scarred her

    settled, plan = settle_look(state, plan_with(meeting))

    assert plan.picture.version == 2 and plan.picture.trigger is PictureTrigger.FIRST_MEETING
    assert "portrait:ilse:v2" in settled.director.pictured
    assert "portrait:ilse:v2" not in state.director.pictured  # the input is never changed
    settled.director.picture_credit = 1
    assert picture(settled, 3) is not None  # the farm's first visit
    assert picture(settled, 4) is None  # and no redraw of the look already drawn


def test_settling_a_look_that_didnt_move_changes_nothing():
    state = quiet_farm()
    change_place(state, "farm", PlaceStatus.OCCUPIED)
    decision = picture(state, 2)
    plan = plan_with(decision)
    assert settle_look(state, plan) == (state, plan)
    change_place(state, "farm", PlaceStatus.THRIVING, turn=2)  # freed in the same scene
    settled, moved = settle_look(state, plan)
    assert moved.picture.version == 3 and "place:farm:v3" in settled.director.pictured
    scene = plan_with(PictureDecision(kind=PictureKind.SCENE, trigger=PictureTrigger.BIG_DEED))
    assert settle_look(state, scene) == (state, scene)

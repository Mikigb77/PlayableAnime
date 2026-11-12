"""N1, N2: thread lifecycle, callbacks, goals that only the player sets, and leads that expire."""

from engine.base import DAY, HOUR
from engine.contracts import Theme, ThreadChange
from engine.director import rules
from engine.director.goals import (
    GoalKind,
    GoalOrigin,
    closed_goals,
    expired_leads,
    followed,
    kind,
    origin,
    player_goals,
    theirs_since,
)
from engine.director.ids import IdProbe
from engine.director.threads import callbacks, current_thread, lifecycle
from engine.director.turn import TurnFacts
from engine.rng import SeededRng
from engine.samples import farm_world, grounded_world
from engine.state import (
    CharacterStatus,
    ClockStatus,
    Fallen,
    Goal,
    GoalStatus,
    Lead,
    LeadStatus,
    Origin,
    OriginKind,
    Thread,
    ThreadKind,
    ThreadStatus,
)
from tests.engine.director.helpers import act, ctx, farming, play_turn

ALL = frozenset(Theme)


def facts(turn: int, **kw) -> TurnFacts:
    base = dict(
        turn=turn,
        deeds=(),
        died=frozenset(),
        gravely_hurt=frozenset(),
        changed_places=(),
        gains=(),
        responded_threads=frozenset(),
        responded_leads=frozenset(),
        touched=frozenset(),
    )
    base.update(kw)
    return TurnFacts(**base)


def thread(thread_id: str, kind=ThreadKind.QUEST, *, involved=("tomas",), **kw) -> Thread:
    kw.setdefault("known_by", ["tomas"])
    return Thread(
        id=thread_id,
        title=f"The matter of {thread_id}",
        kind=kind,
        involved_ids=list(involved),
        origin=Origin(kind=OriginKind.EVENT),
        **kw,
    )


def changes_for(state, turn, **kw):
    return {
        c.thread_id: c
        for c in lifecycle(state, ctx(turn), facts(turn, **kw), woken=set(), settled={})
    }


def test_an_open_thread_untouched_for_twelve_turns_goes_dormant():
    state = farm_world()
    state.threads["well"] = thread("well", last_active_turn=3)
    assert "well" not in changes_for(state, 3 + rules.DORMANT_AFTER_TURNS - 1)
    change = changes_for(state, 3 + rules.DORMANT_AFTER_TURNS)["well"]
    assert change.status is ThreadStatus.DORMANT


def test_acting_on_a_threads_people_keeps_it_active_and_wakes_a_dormant_one():
    state = farm_world()
    state.threads["feud"] = thread(
        "feud", ThreadKind.RIVALRY, involved=("tomas", "bram"), status=ThreadStatus.DORMANT
    )
    change = changes_for(state, 30, touched=frozenset({"bram"}))["feud"]
    assert change.status is ThreadStatus.OPEN and change.active and not change.taken_up
    taken = changes_for(state, 30, responded_threads=frozenset({"feud"}))["feud"]
    assert taken.taken_up


def test_threads_close_when_the_world_ends_them_with_or_without_the_player():
    state = grounded_world()
    # A mystery outlives its clock: the council can name a boss and the killer stay unknown.
    state.clocks["council"].status = ClockStatus.ENDED
    state.clocks["council"].filled = len(state.clocks["council"].steps)
    assert "revenge" not in changes_for(state, 5)
    state.bible.mysteries[0].solved = True
    assert changes_for(state, 5)["revenge"].status is ThreadStatus.RESOLVED_WITHOUT_PLAYER
    state.threads["revenge"].taken_up_turn = 2
    assert changes_for(state, 5)["revenge"].status is ThreadStatus.RESOLVED

    # A rivalry ends when everyone it pits the player against is dead.
    state = farm_world()
    state.threads["feud"] = thread("feud", ThreadKind.RIVALRY, involved=("tomas", "bram"))
    assert "feud" not in changes_for(state, 5)
    state.characters["bram"].status = CharacterStatus.DEAD
    assert changes_for(state, 5)["feud"].status is ThreadStatus.RESOLVED_WITHOUT_PLAYER


def test_an_ignored_events_play_out_settles_its_thread_unless_taken_up_that_turn():
    state = farm_world()
    state.threads["flood"] = thread("flood")
    settled = {"flood": ThreadStatus.RESOLVED_WITHOUT_PLAYER}
    [change] = lifecycle(state, ctx(6), facts(6), woken=set(), settled=settled)
    assert change.status is ThreadStatus.RESOLVED_WITHOUT_PLAYER and change.active
    taken = facts(6, responded_threads=frozenset({"flood"}))
    [change] = lifecycle(state, ctx(6), taken, woken=set(), settled=settled)
    assert change.status is None and change.taken_up


def test_callbacks_pull_one_or_two_dormant_threads_the_player_knows():
    state = farm_world()
    for i in range(5):
        state.threads[f"old-{i}"] = thread(f"old-{i}", status=ThreadStatus.DORMANT)
    state.threads["open"] = thread("open")
    state.threads["secret"] = thread("secret", status=ThreadStatus.DORMANT, known_by=[])
    state.threads["love"] = thread("love", ThreadKind.ROMANCE, status=ThreadStatus.DORMANT)
    for story in range(30):
        rng = SeededRng.for_turn(f"cb-{story}", "main", 4)
        chosen = callbacks(state, rng, frozenset(), exclude=set(), changes=[])
        assert len(chosen) == rules.MAX_CALLBACKS == len(set(chosen))
        assert not {"open", "secret", "love"} & set(chosen)  # romance is switched off here
        assert len(callbacks(state, rng, ALL, exclude=set(), changes=[], limit=1)) == 1
    # One whose people are in the scene comes first more often.
    state.threads["old-0"].involved_ids = ["tomas", "ilse"]
    picks = [
        callbacks(state, SeededRng.for_turn(f"w-{i}", "main", 4), ALL, exclude=set(), changes=[])
        for i in range(60)
    ]
    assert sum("old-0" in p for p in picks) > 60 * 2 / 6


def test_the_current_thread_is_the_events_else_the_latest_open_one_the_player_knows():
    state = farm_world()
    state.threads["a"] = thread("a", last_active_turn=2)
    state.threads["b"] = thread("b", last_active_turn=5)
    state.threads["hidden"] = thread("hidden", last_active_turn=9, known_by=[])
    assert current_thread(state, [], None) == "b"
    assert current_thread(state, [], "a") == "a"


def test_goals_come_only_from_the_player_stating_them_or_taking_a_lead():
    state = grounded_world()
    state.leads["lead-1"] = Lead(id="lead-1", text="Meet the priest at dawn", thread_id="revenge")
    intent = farming(goals=["  Take over   the family ", "find out who killed my father."])
    new, taken = player_goals(
        state,
        ctx(4),
        intent,
        facts(4, responded_leads=frozenset({"lead-1"})),
        IdProbe(state),
    )
    assert taken == ["lead-1"]
    assert [(g.text, g.lead_id, g.set_turn) for g in new] == [
        ("Meet the priest at dawn", "lead-1", 4),
        ("Take over the family", None, 4),  # the existing goal isn't added twice
    ]
    assert len({g.id for g in new}) == 2
    assert player_goals(state, ctx(4), None, facts(4), IdProbe(state)) == ([], [])


def test_a_goal_keeps_when_it_was_set_and_taking_up_a_lead_is_following_it():
    state = grounded_world()
    state.world_s = 2 * DAY
    state.leads["lead-1"] = Lead(id="lead-1", text="Meet the priest at dawn")
    new, _ = player_goals(
        state,
        ctx(4),
        farming(goals=["Take over the family"]),
        facts(4, responded_leads=frozenset({"lead-1"})),
        IdProbe(state),
    )
    assert [(g.lead_id, g.set_s, g.moved_turn) for g in new] == [
        ("lead-1", 2 * DAY, 4),
        (None, 2 * DAY, None),  # stating an aim is not yet following it
    ]


def test_the_thread_the_player_follows_is_the_goal_the_story_last_moved():
    state = grounded_world()  # find-killer, theirs from the start
    goals = state.goals
    assert followed(state) is None and kind(state, goals["find-killer"]) is GoalKind.OWN

    state.leads["lead-1"] = Lead(id="lead-1", text="Meet the priest")
    goals["goal-2"] = Goal(
        id="goal-2", text="Meet the priest", set_turn=3, lead_id="lead-1", moved_turn=3
    )
    goals["goal-3"] = Goal(id="goal-3", text="Leave Naples", set_turn=5)

    def kinds() -> list[str]:
        return [kind(state, g).value for g in goals.values()]

    assert kinds() == ["own", "followed", "own"]
    goals["find-killer"].moved_turn = 7  # a scene moved it on
    assert kinds() == ["followed", "side", "own"]
    goals["goal-3"].moved_turn = 7  # the same scene moved two: the older one leads
    assert followed(state) is goals["find-killer"]
    goals["find-killer"].status = GoalStatus.ACHIEVED
    assert followed(state) is goals["goal-3"]


def test_where_a_goal_came_from():
    state = grounded_world()
    state.leads["asked"] = Lead(id="asked", text="Meet the priest", from_id="carmine")
    state.leads["found"] = Lead(id="found", text="The old ledger")
    state.leads["ghost"] = Lead(id="ghost", text="A boat at midnight", from_id="nobody")
    goals = [
        state.goals["find-killer"],
        Goal(id="goal-2", text="Leave Naples", set_turn=5),
        Goal(id="goal-3", text="Meet the priest", set_turn=6, lead_id="asked"),
        Goal(id="goal-4", text="The old ledger", set_turn=6, lead_id="found"),
        Goal(id="goal-5", text="A boat at midnight", set_turn=6, lead_id="ghost"),
        Goal(id="goal-6", text="A lead since forgotten", set_turn=6, lead_id="gone"),
    ]
    assert [origin(state, g) for g in goals] == [
        GoalOrigin.START,
        GoalOrigin.STATED,
        GoalOrigin.ASKED,
        GoalOrigin.TAKEN,
        GoalOrigin.TAKEN,
        GoalOrigin.TAKEN,
    ]


def test_the_goals_of_the_character_before_are_not_the_heirs():
    state = grounded_world()
    assert theirs_since(state) == -1  # the first character's goals from turn 0 are theirs
    state.fallen.append(
        Fallen(
            character_id="old",
            name="Old",
            ending="death",
            turn=40,
            world_s=DAY,
            successor_id="luca",
        )
    )
    assert theirs_since(state) == 40


def test_a_goal_said_again_with_other_case_accents_or_punctuation_is_not_added():
    state = grounded_world()
    state.goals["goal-2"] = Goal(id="goal-2", text="Salir de Nápoles con vida.")
    said = ["¡find out who killed my father!", "salir de napoles con vida", "...", "Keep the bar"]
    intent = farming(goals=said)
    new, _ = player_goals(state, ctx(4), intent, facts(4), IdProbe(state))
    assert [g.text for g in new] == ["Keep the bar"]


def test_the_player_drops_a_goal_or_replaces_it_in_their_own_words():
    state = grounded_world()
    state.goals["goal-2"] = Goal(id="goal-2", text="Take over the family")
    intent = farming(dropped_goals=["goal-2"], goals=["Take over the family", "Leave Naples"])
    new, _ = player_goals(state, ctx(4), intent, facts(4), IdProbe(state))
    # A goal the player drops and states again in the same words starts again as theirs.
    assert [g.text for g in new] == ["Take over the family", "Leave Naples"]
    assert closed_goals(state, intent, []) == {"goal-2": GoalStatus.ABANDONED}
    assert closed_goals(state, None, []) == {}


def test_a_goal_from_a_lead_closes_with_the_leads_thread():
    state = grounded_world()
    for name in ("a", "b", "c", "d"):
        state.threads[name] = thread(name)
        state.leads[f"lead-{name}"] = Lead(id=f"lead-{name}", text=name, thread_id=name)
        state.goals[f"goal-{name}"] = Goal(id=f"goal-{name}", text=name, lead_id=f"lead-{name}")
    state.threads["b"].status = ThreadStatus.RESOLVED_WITHOUT_PLAYER  # closed by a clock
    state.threads["c"].status = ThreadStatus.DORMANT
    state.goals["goal-d"].status = GoalStatus.ACHIEVED
    changes = [
        ThreadChange(thread_id="a", status=ThreadStatus.RESOLVED),
        ThreadChange(thread_id="d", status=ThreadStatus.FAILED),
        ThreadChange(thread_id="revenge", status=ThreadStatus.RESOLVED),  # find-killer: no lead
    ]
    assert closed_goals(state, farming(), changes) == {
        "goal-a": GoalStatus.ACHIEVED,
        "goal-b": GoalStatus.FAILED,
    }


def test_a_goal_merged_into_another_passes_its_leads_thread_on():
    state = grounded_world()
    state.threads["mill"] = thread("mill", status=ThreadStatus.RESOLVED)
    state.leads["lead-mill"] = Lead(id="lead-mill", text="Who burned the mill", thread_id="mill")
    state.goals["goal-2"] = Goal(id="goal-2", text="Find who burned the mill", set_turn=1)
    state.goals["goal-3"] = Goal(
        id="goal-3",
        text="Who burned the mill",
        lead_id="lead-mill",
        status=GoalStatus.MERGED,
        merged_into="goal-2",
    )
    assert closed_goals(state, farming(), []) == {"goal-2": GoalStatus.ACHIEVED}
    state.goals["goal-2"].status = GoalStatus.ABANDONED
    assert closed_goals(state, farming(), []) == {}


def test_recording_closes_the_goals_that_are_over_and_leaves_the_rest():
    state = grounded_world()
    state.goals["goal-2"] = Goal(id="goal-2", text="Take over the family", set_turn=1)
    intent = act("Have a drink", "drink", "task", HOUR, dropped_goals=["goal-2"])
    after = play_turn(state, 2, intent).state
    assert (after.goals["goal-2"].status, after.goals["goal-2"].closed_turn) == (
        GoalStatus.ABANDONED,
        2,
    )
    assert after.goals["find-killer"] == state.goals["find-killer"]


def test_leads_expire_on_in_world_time_and_never_touch_goals():
    state = grounded_world()
    state.world_s = 3 * DAY
    state.leads["old"] = Lead(id="old", text="A job at the docks", expires_s=2 * DAY)
    state.leads["fresh"] = Lead(id="fresh", text="A card game", expires_s=5 * DAY)
    state.leads["open"] = Lead(id="open", text="A rumor")
    assert expired_leads(state, taken=[]) == ["old"]
    assert expired_leads(state, taken=["old"]) == []


def test_recording_takes_leads_expires_old_ones_and_adds_the_players_goals():
    state = grounded_world()
    state.leads["job"] = Lead(id="job", text="Drive for the Sarno brothers", expires_s=HOUR)
    state.leads["card"] = Lead(id="card", text="Win back the bar at cards", expires_s=DAY)
    goals_before = {g.id: g.model_dump() for g in state.goals.values()}
    intent = act(
        "Find the card game",
        "find",
        "task",
        2 * HOUR,
        responds_to=["card"],
        goals=["Keep the bar"],
    )
    after = play_turn(state, 2, intent).state
    assert after.leads["job"].status is LeadStatus.EXPIRED
    assert after.leads["card"].status is LeadStatus.TAKEN
    added = {g.text: g for g in after.goals.values() if g.id not in goals_before}
    assert set(added) == {"Win back the bar at cards", "Keep the bar"}
    assert added["Win back the bar at cards"].lead_id == "card"
    assert all(g.status is GoalStatus.ACTIVE and g.set_turn == 2 for g in added.values())
    for goal_id, goal in goals_before.items():
        assert after.goals[goal_id].model_dump() == goal

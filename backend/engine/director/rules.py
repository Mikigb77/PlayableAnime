"""The director's numbers in one place, so the T17 evals can tune them (W16, E6, E7, M2, N1).

Turns appear here only where they measure the player's attention (stall pressure, dormant threads,
recent sources) or cost (the picture budget), as W10 allows. Everything that happens in the world
waits on in-world seconds: when a scene needs something is the player's attention, and what
comes is the story clock's (`EVENT_GAP_S`).
"""

from engine.base import DAY, HOUR, MINUTE
from engine.context import EventFrequency, ImageSetting

# W16: turns without stakes before an event comes in, per story setting (S6).
THRESHOLDS: dict[EventFrequency, float] = {
    EventFrequency.CALM: 10,
    EventFrequency.NORMAL: 5,
    EventFrequency.DRAMATIC: 3,
}

# E6: drift moves the threshold by up to this share either way, so each setting keeps its own band
# (calm 8 to 12, normal 4 to 6, dramatic 2.4 to 3.6) and drift never turns events off.
DRIFT_SPAN = 0.2
DRIFT_IN_CONTROL = 0.1  # added on a turn where the player is comfortably in control
DRIFT_AFTER_BIG_EVENT = -0.6  # added after a local or world event, or a deed of severity 4 or 5
DRIFT_SETTLE = 0.05  # otherwise drift eases back toward 0 by this much

# W16: the parts of stall pressure besides turns without stakes.
REPEAT_WEIGHT = 0.5  # each repeat of the same low-stakes action beyond the first
CLOCK_WEIGHT = 1.0  # each running clock one step or less from its end
CLOCK_CAP = 2.0
CLOCK_NEAR_S = 2 * DAY  # a clock whose next step is further off than this isn't close yet

# Below the threshold, an event may come early once pressure reaches this share of it, with a
# chance that grows to EARLY_CHANCE just below the threshold. At the threshold it always comes.
EARLY_FROM = 0.6
EARLY_CHANCE = 0.3

# N1: an open thread nobody touched for this many turns goes dormant.
DORMANT_AFTER_TURNS = 12
MAX_CALLBACKS = 2
# W16, N1: a dormant thread comes back as an event only after this many turns without moving, so an
# event that just played out never returns as a fresh one at once.
RETURN_AFTER_TURNS = 8

# W16: an event source used recently (a deck card, an NPC, a thread) isn't drawn again until this
# many other events have come in.
RECENT_SOURCES = 6

# W16, W10: what comes in fits the time that passed (Miki, 2026-11-11: "100 scenes in the same
# hour should get events that make sense for this time lap"). Stall pressure says when a scene
# needs something, in turns, and the story clock says what: an event needs this much in-world
# time since the last one of its size or larger, and no event follows a smaller one sooner than
# the smaller one's gap. Hours for a personal event, days for a local one, weeks for a world
# one. Until then pressure brings a moment: a small thing of here and now that asks nothing.
EVENT_GAP_S = {"personal": 2 * HOUR, "local": 2 * DAY, "world": 14 * DAY}
# A small thing, a moment or some talk of the place (W2), needs minutes since the last one and
# since the last event, so a talk of ten minutes isn't broken into at every other line. Sooner
# than that nothing new comes in, however many scenes the player plays.
SMALL_GAP_S = 10 * MINUTE
# A moment drawn recently isn't drawn again until this many others have come.
RECENT_MOMENTS = 5

# S2, W10: how the player paces a story is theirs to choose, so nothing pushes the clock on. But
# after a long run of scenes that together took next to no time, this many in a row ending
# within this span, one of the suggestions is a way to let time pass ("Sleep until morning"),
# for a player who would like to move on and hasn't thought of it. It is one choice among the
# others, and after it is offered the run starts over, so it comes at most once in that many
# scenes.
SLOW_CLOCK_SCENES = 12
SLOW_CLOCK_S = 30 * MINUTE

# W16, W10: how long an event from the world's state waits for the player before it plays out, by
# size. Deck cards carry their own.
SOURCE_WINDOW_S = {"personal": DAY, "local": 2 * DAY, "world": 7 * DAY}

# E7, K8: a stretch of a day or more is a montage. It is rolled in at most MONTAGE_MAX_STEPS steps,
# each with an event chance from MONTAGE_MEAN_GAP_S, the average in-world time between events.
# Time the player skips is the story's to grant (Miki, 2026-11-11: "we will see if you just
# train for a week, or maybe during that week there is something happening that forces a
# scene"): most of what is rolled needs a decision, which stops the stretch there, so on normal
# about three skips of three days in ten are cut short, and a little over half the skips of a
# week. A longer stretch is told more coarsely: the gap grows with it, to its length over
# MONTAGE_LONG_SHARE, so a stretch of any length is cut short at most about four times in five,
# a year as often as a month, and a year stops in its fourth or fifth month on average rather
# than in its first week.
MONTAGE_MIN_S = DAY
MONTAGE_MAX_STEPS = 12
MONTAGE_MEAN_GAP_S: dict[EventFrequency, int] = {
    EventFrequency.CALM: 16 * DAY,
    EventFrequency.NORMAL: 8 * DAY,
    EventFrequency.DRAMATIC: 4 * DAY,
}
MONTAGE_LONG_SHARE = 2

# W10, W16: what a trip meets on the way. A trip of ROAD_MIN_S or more is rolled in at most
# MONTAGE_MAX_STEPS legs, each with an event chance from ROAD_MEAN_GAP_S, the average time on the
# road between events. Most of what the road brings needs a decision, which stops the trip there:
# on normal that is about one half-day's walk in six, one day's travel in three, two three-day
# trips in three and nearly every trip of a week. Each stop since the character last arrived
# somewhere doubles the gap, up to ROAD_MAX_QUIETER times, so a long way is a few scenes on the
# road, never a stop at every bend.
ROAD_MIN_S = HOUR
ROAD_MEAN_GAP_S: dict[EventFrequency, int] = {
    EventFrequency.CALM: 4 * DAY,
    EventFrequency.NORMAL: 2 * DAY,
    EventFrequency.DRAMATIC: DAY,
}
ROAD_MAX_QUIETER = 4

# W2: the talk of a place reaches the player character softly. A quiet scene may carry one
# thing the place is saying that they haven't heard about one time in three, so a rumor waits
# for a scene it fits and some are missed. Where the record holds nothing new to them, the
# narrator may make up what the place talks about, about one quiet scene in ten. Either is a
# small thing, so it keeps SMALL_GAP_S from the last one, unless the character only looks on.
TALK_CHANCE = 1 / 3
OWN_TALK_CHANCE = 0.1

# M2: the key-scene budget is a bucket that refills each turn up to a cap, about one picture per
# ten turns on key moments and one per five on more. A key scene needs a full credit. A fight's
# start and its decisive blow may borrow against the coming turns down to PICTURE_FLOOR, so both
# pictures of a fight still come and the average over the story holds.
PICTURE_REFILL: dict[ImageSetting, float] = {
    ImageSetting.KEY_MOMENTS: 0.1,
    ImageSetting.MORE: 0.2,
}
PICTURE_CAP: dict[ImageSetting, float] = {
    ImageSetting.KEY_MOMENTS: 2.0,
    ImageSetting.MORE: 3.0,
}
PICTURE_FLOOR = -2.0

# M1, E6: a deed this severe is a big moment (W1).
BIG_DEED = 4

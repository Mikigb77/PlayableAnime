"""The director's numbers in one place, so the T17 evals can tune them (W16, E6, E7, M2, N1).

Turns appear here only where they measure the player's attention (stall pressure, dormant threads,
recent sources) or cost (the picture budget), as W10 allows. Everything that happens in the world
waits on in-world seconds.
"""

from engine.base import DAY, HOUR
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

# W16, W10: how long an event from the world's state waits for the player before it plays out, by
# size. Deck cards carry their own.
SOURCE_WINDOW_S = {"personal": DAY, "local": 2 * DAY, "world": 7 * DAY}

# E7, K8: a stretch of a day or more is a montage. It is rolled in at most MONTAGE_MAX_STEPS steps,
# each with an event chance from MONTAGE_MEAN_GAP_S, the average in-world time between events.
MONTAGE_MIN_S = DAY
MONTAGE_MAX_STEPS = 12
MONTAGE_MEAN_GAP_S: dict[EventFrequency, int] = {
    EventFrequency.CALM: 365 * DAY,
    EventFrequency.NORMAL: 180 * DAY,
    EventFrequency.DRAMATIC: 90 * DAY,
}

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

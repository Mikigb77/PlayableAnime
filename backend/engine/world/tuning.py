"""The living world's numbers: delays, reach, odds and caps (W2, W5, W10, W13, W15, K8).

Rough figures, as A9 asks: news takes about an hour to get around a district, not 53 minutes. All
times are in-world seconds (W10), never turns. The T15 and T17 evals tune them.
"""

from engine.base import DAY, HOUR, MINUTE, WEEK

# --- K8: a living world doesn't inflate the bill ---------------------------------------------

ACTIVE_NPC_CAP = 8  # key NPCs simulated each tick (W15)
ACTIVE_FACTION_CAP = 4
TICK_INTERVAL_S = DAY  # the world tick runs at most once a day of in-world time...
MAX_TICKS_PER_PASSAGE = 24  # ...and at most this often in one stretch, however long (E7)
AGENDA_FACTS_KEPT = 3  # the latest agenda moves kept per faction or NPC

# --- Places (W7, W10) --------------------------------------------------------------------------

# Getting from a place to one inside it or around it, when no route says (a building in a city).
LOCAL_LINK_S = 15 * MINUTE
# Kinds of place that carry the player's reputation as a region (W3). Any other place's region is
# its nearest ancestor of one of these kinds, or its outermost ancestor.
REGION_KINDS = frozenset(
    {
        "region",
        "province",
        "district",
        "county",
        "country",
        "kingdom",
        "realm",
        "empire",
        "territory",
        "city",
        "town",
        "village",
        "island",
        "planet",
        "moon",
        "system",
        "sector",
        "station",
        "wilds",
    }
)

# --- Witnesses and reports (W2, W10, W11) ----------------------------------------------------

# A witness gets away before reporting: a few seconds to a couple of minutes.
FLEE_S = (30, 2 * MINUTE)
# With phones or the like (G6), the call itself.
CALL_S = (20, MINUTE)
# Where the map doesn't say where a faction is, or nothing on it joins two places, getting there
# still takes time: about an hour, never no time at all (W10).
UNKNOWN_TRIP_S = HOUR
# How long enforcers take to gather once they hear, scaled by their zeal (W11).
ZEAL_GATHER_FACTOR = {"high": 0.6, "medium": 1.0, "low": 2.5}
# A witness this afraid of the actor keeps quiet; one this fond of them protects them.
SILENT_FEAR = 70
LOYAL_AFFINITY = 50

# --- Rumors (W2, W12) --------------------------------------------------------------------------

RUMOR_MIN_SEVERITY = 2  # a tavern insult isn't news
# Word of mouth moves with people, a little slower than a direct trip; phones carry it faster.
NEWS_FACTOR = 1.5
NEWS_FACTOR_INSTANT = 0.25
NEWS_MIN_S = MINUTE
# Before word starts moving, people have to talk.
CHATTER_S = (10 * MINUTE, 1 * HOUR)
# How far a rumor reaches, in hops, by severity: monstrous deeds spread further (W12).
RUMOR_HOPS = {1: 1, 2: 2, 3: 3, 4: 4, 5: 6}
# Accuracy lost per hop (W2), and the accuracy below which a retelling turns into its own,
# possibly wrong, version.
ACCURACY_LOSS = (5, 20)
GARBLED_BELOW = 45
# A hearer believes a rumor at least this accurate, unless they are devoted to the accused.
BELIEVED_FROM = 50

# --- Reputation and attitudes (W3, W4, W8, W9, W12) --------------------------------------------

# How much a bystander who learns of harm done turns against the doer, by severity, before any
# tie to the victims: a brawl barely moves them, a murder chills them, and a massacre turns even
# a stranger who lived through it against the one who did it (W8, W12).
BYSTANDER_HOSTILITY = {1: 0, 2: 4, 3: 10, 4: 25, 5: 70}
BYSTANDER_FEAR = {1: 1, 2: 6, 3: 9, 4: 15, 5: 40}
# Each step of closeness to the victims (comrade, friend, family) adds this much hostility per
# point of severity (W4).
TIE_HOSTILITY = 4
# A hunted beast's kin, its pack or its mate, lose this much affinity per step of closeness, plus
# one step, however small the hunt was to anyone else (W4, G24).
KIN_HOSTILITY = 15
# A faction shrugs off what its own people do below severity 4, unless it fell on its own people
# and was at least this serious: a wounding, or one member trying to murder another (W5, W11).
INSIDE_ANSWER_SEVERITY = 3

# One deed moves esteem or fear by at most this much with one faction or region: reputation
# changes slowly in both directions (W9).
REPUTATION_STEP_MAX = 15

# --- Threat and answers (W5, W10) ------------------------------------------------------------

# Gathering times for each kind of answer, before anyone travels (seconds, low and high).
ANSWER_GATHER_S = {
    "avoid": (0, HOUR),
    "arrest": (3 * MINUTE, 15 * MINUTE),
    "investigate": (10 * MINUTE, HOUR),
    "bounty": (2 * HOUR, 12 * HOUR),
    "hunters": (HOUR, 6 * HOUR),
    "revenge": (6 * HOUR, 7 * DAY),
    "army": (2 * DAY, 7 * DAY),
    "elite": (DAY, 4 * DAY),
    "coalition": (3 * DAY, 10 * DAY),
    "appease": (6 * HOUR, 2 * DAY),
    "recruit": (DAY, 3 * DAY),
    "worship": (DAY, 7 * DAY),
    "bribe": (6 * HOUR, 2 * DAY),
    "assassin": (DAY, 3 * DAY),
    "seal": (3 * DAY, 14 * DAY),
    "use_against_rival": (DAY, 5 * DAY),
    "ignore": (0, 0),
}
# W5's guarantee: once a threat tier is crossed, the answer is under way within this time, plus
# the travel nothing can outrun (W10). It is the longest gathering time above.
REACTION_WINDOW_S = 14 * DAY
# Searching for someone who wasn't where they were expected, and how many tries a hunt gets.
SEARCH_S = (2 * HOUR, 3 * DAY)
HUNT_ATTEMPTS = 3
FIND_ODDS = 0.6

# --- Discovery (W13) ----------------------------------------------------------------------------

# How soon each kind of trace can first be noticed (low, high), and how much it points at the
# actor once noticed (the chance the rumor names them).
TRACE_DELAY_S = {
    "noise": (10, 10 * MINUTE),
    "body": (10 * MINUTE, DAY),
    "damage": (HOUR, DAY),
    "survivor": (HOUR, 2 * DAY),
    "wound": (2 * HOUR, 2 * DAY),
    "ties": (DAY, 7 * DAY),
    "record": (DAY, WEEK),
}
TRACE_ATTRIBUTION = {
    "noise": 0.05,
    "body": 0.15,
    "damage": 0.1,
    "survivor": 0.8,
    "wound": 0.6,
    "ties": 0.2,
    "record": 0.7,
}
# With people around, a body or a blast is noticed within moments.
CROWD_DELAY_S = (5, 2 * MINUTE)
DISCOVERY_ATTEMPTS = 4
DISCOVERY_FADE = 0.7  # each later look finds less
DISCOVERY_GAP_FACTOR = 3  # and comes later
# A body left where it fell, with nobody at the place but someone close by to come across it.
BODY_NEARBY_STRENGTH = 50
# Victims' ties as a trace: someone misses them (W13).
TIES_STRENGTH_PER_TIE = 15
TIES_STRENGTH_MAX = 80

# --- Emergence and revival (W15, W15a) -------------------------------------------------------

AVENGER_DELAY_S = (3 * DAY, 30 * DAY)
AVENGER_ODDS = 0.6
RESISTANCE_DELAY_S = (7 * DAY, 60 * DAY)
REVIVAL_DELAY_S = (30 * DAY, 365 * DAY)
SUCCESSOR_ODDS = 0.4  # otherwise the same faction returns, rebuilding

# --- Agendas in the world tick (W6) --------------------------------------------------------

# On average, how long an active faction or key NPC goes between moves of their own.
FACTION_MOVE_MEAN_S = 7 * DAY
NPC_MOVE_MEAN_S = 5 * DAY

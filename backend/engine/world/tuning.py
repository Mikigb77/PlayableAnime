"""The living world's numbers: delays, reach, odds and caps (W2, W5, W10, W13, W15, K8).

Rough figures, as A9 asks: news takes about an hour to get around a district, not 53 minutes. All
times are in-world seconds (W10), never turns. The T15 and T17 evals tune them.
"""

from engine.base import DAY, HOUR, MINUTE, WEEK, YEAR
from engine.state.bible import Unions

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
# What a place is saying to someone who comes there later (W2, C6): the rumors that reached it,
# only while they are still talk. A brawl of last year is no longer news.
TALK_FRESH_S = 60 * DAY

# W17. Word of a move in a romance is carried to whoever it wronged when it was done within
# this much travel of where they are: there, people know them.
HOME_NEWS_S = DAY

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

# How sure anyone is who did a deed (W4): one person's word is an accusation, and it takes
# this many who saw it and can still say so, or a crowd, to put it beyond doubt.
PROOF_WITNESSES = 2
# Someone who came to face the doer with what they were told lets it rest, and comes for nothing
# more, once they are this afraid of them (`SILENT_FEAR`) or no longer think ill of them.
FORGIVEN_AFFINITY = 0

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
    "confront": (HOUR, 2 * DAY),
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
# How much those who tied what a deed left behind to its doer take it as so, next to a
# witness's word (1): the accuracy of the rumor a finding starts (`discovery.name_the_doer`).
TRACE_FINDING_WEIGHT = 0.8
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

# --- Families (N6) ---------------------------------------------------------------------------

GESTATION_S = 270 * DAY  # how long a child is carried; the same for every people for now (G23)

# --- Lives of their own (W6, W10) --------------------------------------------------------------

# Whom the world gives a life of their own: the key people and those the player character has
# met, those closest to the story first, up to this many, and the latest news of such lives
# kept on record, so a long story's state stays flat (K8).
LIVES_PEOPLE = 30
LIVES_KEPT = 200
# Nothing of the world's making comes to someone for this long after the player character was
# last in a scene with them: those days are the story's to tell, and a month away is no time
# for a wedding (Miki, 2026-11-13).
LIFE_QUIET_S = 90 * DAY
# How near the player character must live to hear what comes to someone as it happens, by the
# map's travel times: a farm outside the village hears of the village's weddings.
LIFE_NEAR_S = DAY
# Living that near, the two aren't apart, however long since a scene had them together, as
# long as nothing broke it: a few weeks away and back changes nothing, and coming home after
# years does not make old neighbours people seen yesterday. They are together again once a
# scene has them so.
LIFE_APART_S = 30 * DAY
# What a year brings, each as the chance of it in one year. The chance over any stretch
# follows from it, so a month brings next to nothing and ten years a great deal, and nothing
# is made to happen: many are found as they were left.
# Out of a hundred people, how many are settled as they are: nothing of the world's making
# comes to them alone, neither a partner nor a friend nor a foe, however long it has been
# (Miki, 2026-11-13: "maybe 10 years go by and the person is exactly the same"). It is theirs
# by who they are, for the whole story. A couple's life goes on whoever the two are.
LIFE_SETTLED = 25
PAIR_RATE = 0.08  # someone single finds a partner: about half do within ten years
PAIR_LATE = 0.25  # how much of that is left past the prime of life
PAIR_FROM_CAST = 0.5  # how often it is someone on record, where one of them fits
PAIR_AGE_GAP = 0.25  # how far apart in age two of the cast may be, as a part of the older...
PAIR_AGE_ROOM = 8  # ...and never less than this many years
NEWCOMER_AGE_ROOM = 4  # how many years older or younger a partner the record didn't have is
MARRY_RATE = 0.3  # a couple marry: most within a few years
CHILD_RATE_MARRIED, CHILD_RATE_TOGETHER = 0.2, 0.04
CHILD_GAP_S = YEAR  # at least this long between two children of a couple
MOST_CHILDREN = 3  # of one couple, by the world's doing
# A couple part, by the custom of the world: first a marriage, then two who are together or
# promised. A marriage that is for life is never left. The numbers lean on our own world
# (docs/REQUIREMENTS.md, W17): where couples part easily about four marriages in ten end, and
# where a marriage holds about one in five.
PART_RATE_MARRIED = {Unions.FOR_LIFE: 0.0, Unions.HELD: 0.008, Unions.EASY: 0.025}
PART_RATE_TOGETHER = {Unions.FOR_LIFE: 0.03, Unions.HELD: 0.04, Unions.EASY: 0.06}
PART_COLD = 3  # as many times likelier where one of the two hearts has gone cold
TIE_RATE = 0.03  # someone and another of the same place become close friends, or fall out
TIE_WARM = 0.65  # how often it is a friendship, between two with no ill will...
TIE_SOUR = 0.25  # ...and between two who already dislike each other
FRIEND_AT, FOE_AT = 50, -40  # how they feel about each other from then on, at the least
TIE_ROOM = 20  # and up to this much further
TIE_AGE = 14  # nobody younger makes a friend or a foe for life by the world's doing
PRIME = 0.55  # the part of a lifespan that is the prime of life, for a partner and children
LIFESPAN_YEARS = 80  # where a people's own isn't on record
# A people old age never takes (G23: a lifespan of 0 on record) lives as good as for ever.
AGELESS_YEARS = 1_000_000
# Old age (W6): from this part of someone's span on, the years may take them, the likelier the
# older, so that half of those who get that far are gone at the full span and next to nobody
# sees a fifth more than it. Nothing takes anyone younger.
OLD_AGE_FROM = 0.85
# The player character's own old age (N6, W6): the years stop this part of their span before
# the day it takes them, drawn between the two with the day, so the stop tells nobody how long
# is left (Miki, 2026-11-13). Of eighty years it is ten months to three years.
LAST_YEARS = (0.01, 0.04)
# Someone the world first finds older than their span has one of their own: as long again
# past their age as half of what they have outlived the span by.
OWN_SPAN = 0.5
# Climbing the world's ladders over the years (W6, G19). People take a climb up at this part
# of their people's span (twelve, of eighty years), and nobody is counted as having been at it
# for less than the second part (two years): from the years since, and how far they have come,
# the world reads how fast they climb.
CLIMB_FROM = 0.15
CLIMB_LEAST = 0.025
# With a rank full, the attempt at the next rung comes in its own time: on average after this
# part again of the work the rung took, so nobody at their peak breaks through overnight.
CLIMB_TRY_AFTER = 0.2
CLIMB_TRIES = 12  # attempts at most in one pass of the tick
# The chance in a year that a stroke of fortune lifts one named person a rung: one in a
# thousand years each, so a decade brings a village none and a century brings the world one.
FORTUNE_RATE = 0.001

# --- The wider world over the years (W6, W7) -----------------------------------------------------

# Two factions are at war while either's stance toward the other is this or worse.
WAR_AT = -60
# A war comes to a head no sooner than this after the world first saw it, or after the two
# last fought it out: a month away is no time for a kingdom to fall (Miki, 2026-11-13: "If a
# month went by, obviously there is no time for such things").
WAR_PAUSE_S = YEAR
# From then on, the chance in one year that it comes to a head. Most wars are fought out
# within ten years, some more than once, and some never: nothing is made to happen.
WAR_RATE = 0.3
# A side this many steps of might above the other wins with no throw (A2). Closer than that
# a throw decides, each step worth this much to the mightier side's chances.
WAR_SURE = 2
WAR_EDGE = 0.2
WAR_SPENT = 0.25  # how often an even fight leaves both sides the weaker and neither the winner
WAR_UNREST = 30  # how much less steady a place is once it has changed hands in a war (W7)
WAR_WASTE = 40  # and once nobody holds it
# A place nobody holds since a war is taken by a faction that can reach it: the chance in one
# year.
SEIZE_RATE = 0.15
# Whoever lives this near a place a war touched knows of it as it happens, by the map's travel
# times. Further off it is word that travels (W2), or what they find when they come back.
WAR_NEAR_S = DAY
WAR_NEWS_HOPS = 6  # how far word of it travels, place to place
CHANGES_KEPT = 100  # the latest news of the wider world kept on record (K8)

# --- Agendas in the world tick (W6) --------------------------------------------------------

# On average, how long an active faction or key NPC goes between moves of their own.
FACTION_MOVE_MEAN_S = 7 * DAY
NPC_MOVE_MEAN_S = 5 * DAY
# Whoever the world sends somewhere comes back (`engine.world.returns`): how long a key NPC
# stays where an outing of their own took them, and how long someone stays where an errand
# took them, to bring word or to face someone, once it is done. The way back comes on top.
OUTING_STAY_S = (DAY, 4 * DAY)
ERRAND_STAY_S = (2 * HOUR, DAY)
# Someone held where they went sets out for home this long after: a day at first, and then as
# long again as they have been held so far, up to a week, so a year in a cell asks once a week.
HELD_S = DAY
HELD_MAX_S = 7 * DAY

# W1, W4: what a bout both sides agreed to adds to affinity and trust between those who fought
# it, and up to where: bouts alone make nobody a close friend.
BOUT_REGARD = 2
BOUT_REGARD_MAX = 30
# W1: how much more trust a blow beyond the terms of a bout costs than an open attack, since it
# came under cover of a friendly fight.
BROKEN_TERMS_TRUST = 1.5

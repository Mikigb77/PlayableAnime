## The draft (en, teen)

> A 300-year-old elf ranger, still young for her kind, guarding a forest that humans have started to cut down.

_33.3 s, $0.084: 2330 tokens of thinking, 5146 of answer, 1 tries_

### What the draft's screen shows

The Verge of the Green
High Fantasy
solemn
Druidic nature magic: real, and rare.
Elven biology: real, and rare.
A medieval-era fantasy world of iron axes, hand-carved bows, and wooden wagons.
Peoples: Elves and Humans.
High Reach Logging Syndicate: A well-funded human enterprise driving the clearance of the forest for timber and settlement space.
The Wood-Wardens: A small, dedicated band of elven rangers sworn to defend the borders of Aethelwood at any cost.
Sylris, 300, Elves.
A vigilant elven ranger with a quiet, watchful grace.
Warden Sentry, The Wood-Wardens.
Expert: Archery and Stealth. Skilled: Forest Survival and Tracking.
Gifts: Elven Senses.
Cautious, protective and patient.
Forest Walk: Move through dense undergrowth and moss without leaving any physical trace or making a single sound (Does not function on paved human roads or stone surfaces.).
Woodland Speak: Sense the collective mood, pain, or distress of nearby plants and trees (Requires a moment of silent, physical contact with a living trunk or vine.).
Carries Elven Recurve Bow, Quiver of Fletched Arrows, Hunting Knife and Camo Cloak.
Elves live for thousands of years, maturing slowly and remaining physically youthful for centuries.
The ancient forest of Aethelwood is semi-sentient and bleeds amber sap when harmed.
Nature magic can accelerate growth and soothe beasts, but it cannot conjure matter from nothing.
Druidic nature magic: real, and rare.
Elven biology: real, and rare.

### On record (the player never sees this)

```json
{
 "world": {
  "title": "The Verge of the Green",
  "genre": "High Fantasy",
  "era": "A medieval-era fantasy world of iron axes, hand-carved bows, and wooden wagons"
 },
 "character": {
  "id": "player",
  "name": "Sylris",
  "aliases": [
   "The Whispering Arrow",
   "Sentry of the Green"
  ],
  "prominence": "key",
  "description": "A vigilant elven ranger with a quiet, watchful grace.",
  "appearance": "Slender, athletic build, long silver-gold hair braided tight, wearing green-and-brown leather armor that blends perfectly into the forest canopy, carrying a recurve bow.",
  "age": 300,
  "people_id": "elves",
  "location_id": "high-canopy",
  "memberships": [
   {
    "faction_id": "wood-wardens",
    "rank": "Warden Sentry",
    "loyalty": 90
   }
  ],
  "origin": {
   "kind": "premise"
  },
  "known_by": [
   "player"
  ],
  "met_by": [
   "player"
  ],
  "lifespan_years": 2000
 },
 "sheet": {
  "attributes": {
   "speed": 5,
   "wits": 4,
   "willpower": 4,
   "nerve": 5,
   "bearing": 4
  },
  "skills": [
   {
    "name": "Archery",
    "level": "expert"
   },
   {
    "name": "Stealth",
    "level": "expert"
   },
   {
    "name": "Forest Survival",
    "level": "skilled"
   },
   {
    "name": "Tracking",
    "level": "skilled"
   }
  ],
  "traits": [
   {
    "name": "Elven Senses",
    "kind": "gift",
    "description": "Allows you to see clearly in starlight and hear the softest brush of leaves a mile away."
   }
  ],
  "powers": [
   {
    "id": "forest-walk",
    "name": "Forest Walk",
    "description": "Move through dense undergrowth and moss without leaving any physical trace or making a single sound.",
    "limits": [
     "Does not function on paved human roads or stone surfaces."
    ]
   },
   {
    "id": "woodland-speak",
    "name": "Woodland Speak",
    "description": "Sense the collective mood, pain, or distress of nearby plants and trees.",
    "limits": [
     "Requires a moment of silent, physical contact with a living trunk or vine."
    ]
   }
  ],
  "disposition": {
   "temperament": {
    "traits": [
     "cautious",
     "protective",
     "patient"
    ],
    "values": [
     "harmony",
     "duty"
    ],
    "loves": [
     "the quiet canopy of the deep woods"
    ],
    "fears": [
     "the scent of burnt wood",
     "the dynamic destruction wrought by humans"
    ]
   }
  },
  "resources": {
   "items": [
    {
     "id": "elven-recurve-bow",
     "name": "Elven Recurve Bow",
     "kind": "weapon",
     "description": "A beautifully balanced bow carved from flexible ash wood."
    },
    {
     "id": "quiver-of-fletched-arrows",
     "name": "Quiver of Fletched Arrows",
     "kind": "gear",
     "description": "A leather quiver holding twenty sharp, iron-tipped arrows.",
     "quantity": 20
    },
    {
     "id": "hunting-knife",
     "name": "Hunting Knife",
     "kind": "weapon",
     "description": "A sharp, simple knife used for skinning or self-defense."
    },
    {
     "id": "camo-cloak",
     "name": "Camo Cloak",
     "kind": "gear",
     "description": "A hooded cloak patterned in shades of autumn moss."
    }
   ],
   "currency": "silver shards",
   "title": "Warden Ranger",
   "rank": "Sentry",
   "connections": [
    {
     "name": "Captain Eldrin",
     "kind": "trusts_them",
     "character_id": "eldrin",
     "note": "Your commanding officer, who has charged you with watching the western border."
    }
   ]
  },
  "axes": {
   "might": 2,
   "knowledge": 2,
   "stealth": 4
  },
  "backstory": [
   {
    "text": "You have spent three hundred years wandering the quiet paths of Aethelwood, still considered young among your slow-maturing kind."
   },
   {
    "text": "The sudden arrival of iron axes and greedy human settlements on the border has disrupted the ancient peace, forcing you to take up your bow in defense of the trees."
   }
  ]
 },
 "gift": "none",
 "extraordinary": [
  "druidic nature magic (rare): allowing practitioners to speak with flora, blend into shadows, and encourage rapid plant growth.",
  "elven biology (rare): granting lifespans of several thousand years and highly acute physical senses."
 ],
 "peoples": [
  {
   "id": "elves",
   "name": "Elves",
   "description": "An ancient, isolationist people deeply bonded with the deep forests.",
   "lifespan_years": 2000,
   "gifts": [
    "Night vision",
    "Uncanny balance"
   ],
   "culture": "A slow-moving, artistic culture focused on preservation and harmony with nature.",
   "relations": [
    "Tense stand-off with expanding human settlements that encroach upon ancient boundaries."
   ]
  },
  {
   "id": "humans",
   "name": "Humans",
   "description": "Ambitious, short-lived, and rapidly expanding settlers.",
   "lifespan_years": 80,
   "culture": "Industrious and pragmatic, valuing resource gathering, agriculture, and construction.",
   "relations": [
    "View the elven forest as an untapped source of valuable lumber and farmland."
   ]
  }
 ],
 "rules": [
  "Elves live for thousands of years, maturing slowly and remaining physically youthful for centuries.",
  "The ancient forest of Aethelwood is semi-sentient and bleeds amber sap when harmed.",
  "Nature magic can accelerate growth and soothe beasts, but it cannot conjure matter from nothing.",
  "Druidic nature magic: real, and rare.",
  "Elven biology: real, and rare."
 ],
 "others": [
  "Captain Eldrin, 1200, peak attribute 5",
  "Overseer Graves, 42, peak attribute 4"
 ],
 "people_in_the_world": 2,
 "years": {
  "age": 300.0,
  "lives_about": 2000,
  "the_record_says_so": true,
  "old": false,
  "told_the_end_is_close": false
 }
}
```

## Turn 1 (opening), 8.8 s, $0.048

_From Day 1, dawn, 06:00 to Day 1, dawn, 06:00 (0 s). Sylris is 300, alive._

Perched silently on a thick ironwood branch high in the canopy of Aethelwood, you watch the first light of dawn pierce the heavy morning mist. The wind carries a bitter scent that tightens your chest: the sharp, burning odor of green timber on a human campfire. Below, the rhythmic, metallic ring of iron axes strikes a brutal cadence against the ancient, semi-sentient trees, making the great branch beneath you tremble. The High Reach settlers have set up their camp within the western boundary, carving an ugly scar into the ancient green. Through your keen elven senses, you hear the distant, raucous laughter of the loggers and the groan of falling ironwood. This grove has stood untouched for thousands of years, and the Wood-Wardens expect their rangers to protect the trees at any cost. A sudden, sharp snap of dry undergrowth from the forest floor below breaks your focus. Looking down through the dense leaves, you spot a lone human scout bearing the emblem of the High Reach Logging Syndicate, moving cautiously toward the base of your lookout tree.

**Suggestions:**
1. Draw your recurve bow and quiet the scout from above. (thread)
2. Slip down silently using Forest Walk to ambush them. (personal)
3. Retreat back through the branches toward the Whispering Hollow outpost. (side)

**Issues:**
- start_told (thread:save-the-grove): the story told it

## What the screens show (turn 1)

### The Character screen

```json
{
 "character": {
  "name": "Sylris",
  "lines": [
   "Unhurt",
   "Forest Walk: ready",
   "Woodland Speak: ready",
   "0 silver shards",
   "Camo Cloak",
   "Elven Recurve Bow",
   "Hunting Knife",
   "Quiver of Fletched Arrows (20)"
  ]
 },
 "sheet": {
  "about": [
   "Warden Sentry, The Wood-Wardens",
   "Warden Ranger",
   "300 years old"
  ],
  "description": "A vigilant elven ranger with a quiet, watchful grace.",
  "condition": {
   "health": "unhurt",
   "health_label": "Unhurt"
  },
  "money_label": "0 silver shards",
  "items": [
   {
    "name": "Camo Cloak",
    "kind": "gear",
    "kind_label": "Gear",
    "description": "A hooded cloak patterned in shades of autumn moss.",
    "quantity": 1,
    "carried": true
   },
   {
    "name": "Elven Recurve Bow",
    "kind": "weapon",
    "kind_label": "Weapon",
    "description": "A beautifully balanced bow carved from flexible ash wood.",
    "quantity": 1,
    "carried": true
   },
   {
    "name": "Hunting Knife",
    "kind": "weapon",
    "kind_label": "Weapon",
    "description": "A sharp, simple knife used for skinning or self-defense.",
    "quantity": 1,
    "carried": true
   },
   {
    "name": "Quiver of Fletched Arrows",
    "kind": "gear",
    "kind_label": "Gear",
    "description": "A leather quiver holding twenty sharp, iron-tipped arrows.",
    "quantity": 20,
    "carried": true
   }
  ],
  "skills": [
   {
    "name": "Archery",
    "level": "expert",
    "level_label": "Expert",
    "dice": 4
   },
   {
    "name": "Stealth",
    "level": "expert",
    "level_label": "Expert",
    "dice": 4
   },
   {
    "name": "Forest Survival",
    "level": "skilled",
    "level_label": "Skilled",
    "dice": 3
   },
   {
    "name": "Tracking",
    "level": "skilled",
    "level_label": "Skilled",
    "dice": 3
   }
  ],
  "powers": [
   {
    "name": "Forest Walk",
    "description": "Move through dense undergrowth and moss without leaving any physical trace or making a single sound.",
    "limits": [
     "Does not function on paved human roads or stone surfaces."
    ],
    "ready": true,
    "ready_label": "Ready",
    "secret": false
   },
   {
    "name": "Woodland Speak",
    "description": "Sense the collective mood, pain, or distress of nearby plants and trees.",
    "limits": [
     "Requires a moment of silent, physical contact with a living trunk or vine."
    ],
    "ready": true,
    "ready_label": "Ready",
    "secret": false
   }
  ],
  "traits": [
   {
    "name": "Elven Senses",
    "kind": "gift",
    "kind_label": "Gift",
    "description": "Allows you to see clearly in starlight and hear the softest brush of leaves a mile away."
   }
  ],
  "temperament": [
   "cautious",
   "protective",
   "patient"
  ]
 },
 "reputation": [
  {
   "name": "High Reach Logging Syndicate",
   "label": "Neutral"
  },
  {
   "name": "The Wood-Wardens",
   "label": "Neutral"
  }
 ],
 "clock": {
  "world_s": 0,
  "label": "Day 1, dawn",
  "timeline_id": "main"
 },
 "since": [
  {
   "text": "The Wood-Wardens expect every ranger to protect the trees, even if it means open conflict.",
   "ago_label": "moments ago"
  },
  {
   "text": "Humans from High Reach have recently breached the forest boundaries with heavy logging equipment.",
   "ago_label": "moments ago"
  },
  {
   "text": "Aethelwood is an ancient forest that has stood untouched for thousands of years.",
   "ago_label": "moments ago"
  }
 ]
}
```

### Memory

```json
{
 "character": {
  "name": "Sylris",
  "lines": [
   "A vigilant elven ranger with a quiet, watchful grace.",
   "Warden Ranger",
   "Sentry"
  ]
 },
 "places": [
  {
   "id": "aethelwood",
   "name": "Aethelwood Forest",
   "lines": [
    "Wilds",
    "An ancient, towering forest of massive ironwood trees, shadowed hollows, and thick, mossy undergrowth.",
    "You haven't been there."
   ]
  },
  {
   "id": "loggers-camp",
   "name": "The Encroaching Scar",
   "lines": [
    "Wilds",
    "A muddy, bustling logging camp filled with stacks of freshly felled timber, smelling heavily of sawdust and pine resin.",
    "You haven't been there."
   ]
  },
  {
   "id": "high-canopy",
   "name": "The High Canopy Sentry",
   "lines": [
    "Wilds",
    "A lofty natural lookout branch high in a giant ironwood tree, offering a clear view over the western forest boundary."
   ]
  },
  {
   "id": "high-reach",
   "name": "High Reach Settlement",
   "lines": [
    "Village",
    "A rapidly growing human border town made of raw timber, busy with stone masons, builders, and eager pioneers.",
    "You haven't been there."
   ]
  },
  {
   "id": "ranger-outpost",
   "name": "The Whispering Hollow",
   "lines": [
    "Building",
    "A hidden sanctuary built inside the hollow trunk of a living sentinel tree, serving as a ranger outpost.",
    "You haven't been there."
   ]
  }
 ],
 "factions": [
  {
   "id": "high-reach-settlers",
   "name": "High Reach Logging Syndicate",
   "lines": [
    "Crew",
    "A well-funded human enterprise driving the clearance of the forest for timber and settlement space."
   ],
   "esteem": "neutral",
   "dread": "none",
   "standing_label": "Neutral"
  },
  {
   "id": "wood-wardens",
   "name": "The Wood-Wardens",
   "lines": [
    "Sect",
    "A small, dedicated band of elven rangers sworn to defend the borders of Aethelwood at any cost."
   ],
   "esteem": "neutral",
   "dread": "none",
   "standing_label": "Neutral"
  }
 ],
 "threads": [
  {
   "id": "save-the-grove",
   "title": "Guarding the Sacred Ironwood",
   "status": "open"
  }
 ]
}
```


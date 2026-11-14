## The draft (en, teen)

> A 300-year-old elf ranger, still young for her kind, guarding a forest that humans have started to cut down.

_38.1 s, $0.095_

### What the draft's screen shows

The Whispering Border
high fantasy nature conflict
tense and melancholic
Wood magic: real, and rare.
Medieval era with early logging mills: steel axes, ropes, and draft horses.
Peoples: Elves and Humans.
Greenwood Rangers: The elite elven scouts and wardens who patrol the boundaries and protect the forest from outside threats.
The Ironwood Syndicate: A ruthless human guild of loggers and merchants contracted to harvest high-quality timber.
Yvanna, 300, Elves.
A silent, sharp-eyed warden of the deep canopy who moves with fluid, predator-like grace.
Border Warden, Greenwood Rangers.
Expert: Archery and Stealth. Skilled: Tracking.
A knack: The Longbow (any shot or maneuver executed with a traditional bow).
Gifts: Lightfooted. Quirks: Arbor Bond.
Observant, vigilant and protective.
Forest Meld: Forest Meld (Must remain perfectly still.; Only works while in direct contact with living trees or thick brush.). Cost: Requires a brief rest after holding the meld for more than an hour.
Carries Elven Recurve Bow, Quiver of Arrows and Forest-Green Cloak. 15 silver coins.
Wood magic requires a direct connection to living plant life and fails completely in dead or deforested zones.
Elves can live for thousands of years, remaining physically in their prime for centuries.
Wood magic: real, and rare.

### On record (the player never sees this)

```json
{
 "world": {
  "title": "The Whispering Border",
  "genre": "high fantasy nature conflict",
  "era": "Medieval era with early logging mills: steel axes, ropes, and draft horses."
 },
 "character": {
  "id": "player",
  "name": "Yvanna",
  "aliases": [
   "The Sentinel",
   "Woodwalker"
  ],
  "prominence": "key",
  "description": "A silent, sharp-eyed warden of the deep canopy who moves with fluid, predator-like grace.",
  "appearance": "Slender and athletic, with long silver-braided hair, piercing green eyes, and wearing practical, forest-green leather armor that blends into the leaves.",
  "age": 300,
  "people_id": "elves",
  "location_id": "canopy-outpost",
  "memberships": [
   {
    "faction_id": "greenwood-rangers",
    "rank": "Border Warden",
    "loyalty": 95
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
   "nerve": 4
  },
  "skills": [
   {
    "name": "Archery",
    "level": "expert",
    "notes": "Deadly accurate with a recurve bow from the treetops."
   },
   {
    "name": "Stealth",
    "level": "expert",
    "notes": "Able to move through dense foliage without disturbing a single leaf."
   },
   {
    "name": "Tracking",
    "level": "skilled",
    "notes": "Can easily follow footprints, bent twigs, and crushed moss."
   }
  ],
  "traits": [
   {
    "name": "Lightfooted",
    "kind": "gift",
    "description": "Leaves no tracks on normal forest terrain and makes no sound when walking on dry leaves."
   },
   {
    "name": "Arbor Bond",
    "description": "Becomes deeply unsettled and angry in areas of clear-cut forest."
   }
  ],
  "talents": [
   {
    "id": "the-longbow",
    "name": "The Longbow",
    "covers": "any shot or maneuver executed with a traditional bow"
   }
  ],
  "powers": [
   {
    "id": "forest-meld",
    "name": "Forest Meld",
    "strength": "small",
    "limits": [
     "Must remain perfectly still.",
     "Only works while in direct contact with living trees or thick brush."
    ],
    "costs": [
     {
      "kind": "fatigue",
      "text": "Requires a brief rest after holding the meld for more than an hour."
     }
    ]
   }
  ],
  "disposition": {
   "temperament": {
    "traits": [
     "observant",
     "vigilant",
     "protective"
    ],
    "values": [
     "nature",
     "the treaty",
     "stealth"
    ],
    "loves": [
     "the whispering sound of the wind through the pines",
     "perfect silence"
    ],
    "fears": [
     "watching her ancient home turn to barren sawdust"
    ],
    "wants": [
     "To stop the human lumberjacks and preserve the forest border."
    ],
    "voice": "Soft, melodic, but carrying an underlying sharpness."
   }
  },
  "resources": {
   "items": [
    {
     "id": "elven-recurve-bow",
     "name": "Elven Recurve Bow",
     "kind": "weapon",
     "description": "Crafted from flexible heartwood, whisper-quiet when drawn."
    },
    {
     "id": "quiver-of-arrows",
     "name": "Quiver of Arrows",
     "kind": "gear",
     "description": "Fletched with hawk feathers, tipped with sharp steel.",
     "quantity": 24
    },
    {
     "id": "forest-green-cloak",
     "name": "Forest-Green Cloak",
     "kind": "armour",
     "description": "Muted green wool that breaks up your silhouette against the foliage."
    }
   ],
   "money": 15,
   "currency": "silver coins",
   "title": "Warden of the Southern Border",
   "rank": "Ranger",
   "connections": [
    {
     "name": "Commander Celene",
     "kind": "ally",
     "character_id": "celene",
     "note": "Your commanding officer, who has guided your patrols for a century."
    }
   ]
  },
  "condition": {
   "reserves": [
    {
     "name": "Stamina"
    }
   ]
  },
  "axes": {
   "might": 3,
   "influence": 2,
   "wealth": 2,
   "knowledge": 3,
   "stealth": 5
  },
  "backstory": [
   {
    "text": "You have spent the last century patrolling this very border, knowing every tree, stream, and deer path. The sudden human push across the river threatens everything you have sworn to protect."
   }
  ]
 },
 "gift": "small",
 "extraordinary": [
  "wood magic (rare): Allows practitioners to sense the vitality of plants, accelerate growth, or meld into foliage."
 ],
 "peoples": [
  {
   "id": "elves",
   "name": "Elves",
   "description": "An ancient, slow-lived people deeply attuned to the natural balance of the deep forests.",
   "lifespan_years": 2000,
   "gifts": [
    "Keen night vision",
    "Perfect balance"
   ],
   "culture": "A protective, insular society centered around preserving the great forest's ancient heartwood.",
   "relations": [
    "Strained peace with the expanding human kingdoms, now bordering on active skirmishes."
   ]
  },
  {
   "id": "humans",
   "name": "Humans",
   "description": "A short-lived, highly adaptable, and ambitious people seeking land and raw materials.",
   "lifespan_years": 80,
   "gifts": [
    "Great ambition",
    "Rapid learning"
   ],
   "culture": "Resource-hungry, focused on expansion, trade, and building settlements.",
   "relations": [
    "Eager to clear the forest for valuable timber, disregarding ancient elven territorial warnings."
   ]
  }
 ],
 "rules": [
  "Wood magic requires a direct connection to living plant life and fails completely in dead or deforested zones.",
  "Elves can live for thousands of years, remaining physically in their prime for centuries.",
  "Wood magic: real, and rare."
 ],
 "others": [
  "Commander Celene, 650, peak attribute 5",
  "Overseer Harlan, 45, peak attribute 4"
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


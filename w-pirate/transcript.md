## The draft (en, teen)

> I want to be a pirate.

_25.1 s, $0.052_

### What the draft's screen shows

Sails of the Obsidian Sea
swashbuckling pirate adventure
roguish and daring
Sea magic and curses: real, and rare.
The Archipelago of San Martin, 1718: flintlocks, cutlasses, galleons and spyglasses.
Pirate renown: scallywag, deckhand, quartermaster, captain, pirate_lord.
Peoples: Human.
The Royal Navy Fleet: The disciplined naval arm of the Crown sent to pacify the archipelago.
The Sea Dogs: A loose alliance of pirate captains and outlaws operating out of Tortuga Bay.
Edward Thorne, 21, Human.
A quick-witted, nimble lad with a fire in his eyes and a hunger for the sea.
scallywag.
Fair: Acrobatics. Novice: Swordsmanship and Sailing.
Gifts: Nimble-Footed.
Daring, roguish and adventurous.
Carries Steel Cutlass and Spyglass. 12 silver coins.
Sea magic always requires a toll paid in blood or a precious possession cast into the deep.
A wind-caller can manipulate currents and wind to speed up a vessel, but cannot create wind out of thin air.
Sea magic and curses: real, and rare.

### On record (the player never sees this)

```json
{
 "world": {
  "title": "Sails of the Obsidian Sea",
  "genre": "swashbuckling pirate adventure",
  "era": "The Archipelago of San Martin, 1718: flintlocks, cutlasses, galleons and spyglasses."
 },
 "character": {
  "id": "player",
  "name": "Edward Thorne",
  "aliases": [
   "Swift"
  ],
  "prominence": "key",
  "description": "A quick-witted, nimble lad with a fire in his eyes and a hunger for the sea.",
  "appearance": "Slender but athletic build, messy sun-bleached brown hair, wearing a loose-fitting white linen shirt, dark breeches, and a worn leather belt.",
  "age": 21,
  "people_id": "human",
  "location_id": "the-salty-galleon",
  "origin": {
   "kind": "premise"
  },
  "known_by": [
   "player"
  ],
  "met_by": [
   "player"
  ],
  "lifespan_years": 80
 },
 "sheet": {
  "attributes": {
   "speed": 4,
   "wits": 4,
   "knowledge": 2,
   "nerve": 4
  },
  "skills": [
   {
    "name": "Swordsmanship",
    "level": "novice",
    "notes": "Decent with a cutlass, though lacks formal training."
   },
   {
    "name": "Acrobatics",
    "notes": "Excellent balance, perfect for climbing rigging."
   },
   {
    "name": "Sailing",
    "level": "novice",
    "notes": "Knows how to raise a sail and tie basic knots."
   }
  ],
  "traits": [
   {
    "name": "Nimble-Footed",
    "kind": "gift",
    "description": "Incredibly agile and stable on a swaying ship deck."
   }
  ],
  "disposition": {
   "temperament": {
    "traits": [
     "daring",
     "roguish",
     "adventurous"
    ],
    "values": [
     "freedom",
     "fortune"
    ],
    "loves": [
     "the sound of the surf",
     "a good joke"
    ],
    "fears": [
     "being locked up",
     "drowning in a calm sea"
    ],
    "wants": [
     "Become a legendary pirate captain and sail the open ocean."
    ]
   }
  },
  "resources": {
   "items": [
    {
     "id": "steel-cutlass",
     "name": "Steel Cutlass",
     "kind": "weapon",
     "description": "A reliable, slightly rusted pirate saber."
    },
    {
     "id": "spyglass",
     "name": "Spyglass",
     "kind": "gear",
     "description": "A small brass spyglass with a cracked lens."
    }
   ],
   "money": 12,
   "currency": "silver coins"
  },
  "axes": {
   "influence": 2
  },
  "ladders": [
   {
    "ladder_id": "pirate-renown",
    "rung": 0
   }
  ],
  "backstory": [
   {
    "text": "Grew up as an orphan on the docks of Port Royal, watching galleons sail away."
   },
   {
    "text": "Fled to Tortuga Bay after accidentally pickpocketing a wealthy naval purser."
   },
   {
    "text": "Now seeks a captain willing to take on a fresh hand with big ambitions."
   }
  ]
 },
 "gift": "none",
 "extraordinary": [
  "sea magic and curses (rare): Mages can call the winds or curse a ship, but cannot summon hurricanes at will."
 ],
 "ladders": [
  {
   "id": "pirate-renown",
   "name": "pirate renown",
   "rungs": [
    "0: scallywag (tier 2, lives 0)",
    "1: deckhand (tier 4, lives 0)",
    "2: quartermaster (tier 6, lives 0)",
    "3: captain (tier 8, lives 0)",
    "4: pirate_lord (tier 10, lives 0)"
   ]
  }
 ],
 "peoples": [
  {
   "id": "human",
   "name": "Human",
   "lifespan_years": 80,
   "culture": "The rugged sailors, merchants, and naval officers of the San Martin Archipelago."
  }
 ],
 "rules": [
  "Sea magic always requires a toll paid in blood or a precious possession cast into the deep.",
  "A wind-caller can manipulate currents and wind to speed up a vessel, but cannot create wind out of thin air.",
  "Sea magic and curses: real, and rare."
 ],
 "others": [
  "Captain Brand, 48, peak attribute 5",
  "Governor Pennington, 55, peak attribute 5"
 ],
 "people_in_the_world": 2,
 "years": {
  "age": 21.0,
  "lives_about": 80,
  "the_record_says_so": true,
  "old": false,
  "told_the_end_is_close": false
 }
}
```


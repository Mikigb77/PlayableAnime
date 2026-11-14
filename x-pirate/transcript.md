## The draft (en, teen)

> I want to be a pirate.

_22.0 s, $0.064: 2735 tokens of thinking, 2584 of answer, 1 tries_

### What the draft's screen shows

Sails of Fortune
historical swashbuckler
adventure
Grounded: no magic and nothing supernatural, and that won't change.
The Caribbean, 1715: flintlocks, cutlasses, galleons, and spyglasses.
Peoples: Human.
Brethren of the Coast: A loose alliance of pirate captains and buccaneers.
The Royal Navy: The disciplined naval force of the British Crown, tasked with wiping out piracy.
Jack, 24.
A young, ambitious sailor with a hunger for freedom and gold.
Outlaw.
Skilled: Sailing. Fair: Swordsmanship and Pistol Shooting.
Gifts: Daring. Flaws: Wanted.
Ambitious and reckless. Wants I want to be a pirate.
No powers, since this world has none.
Carries Weathered Cutlass, Flintlock Pistol and Spyglass. 50 silver shillings.
Magic, monsters, and the supernatural do not exist; the sea is governed only by wind, tide, and iron.
The Royal Navy hunts pirates relentlessly, and the penalty for piracy is hanging.
The Brethren of the Coast follow a loose set of articles, but betrayal is common.
Grounded: no magic and nothing supernatural, and that won't change.

### On record (the player never sees this)

```json
{
 "world": {
  "title": "Sails of Fortune",
  "genre": "historical swashbuckler",
  "era": "The Caribbean, 1715: flintlocks, cutlasses, galleons, and spyglasses"
 },
 "character": {
  "id": "player",
  "name": "Jack",
  "aliases": [
   "Lucky Jack"
  ],
  "prominence": "key",
  "description": "A young, ambitious sailor with a hunger for freedom and gold.",
  "appearance": "Sun-bronzed skin, messy dark hair, wearing a loose white linen shirt, rugged leather boots, and a tricorn hat.",
  "age": 24,
  "location_id": "tortuga",
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
   "willpower": 4,
   "charm": 4,
   "nerve": 5
  },
  "skills": [
   {
    "name": "Sailing",
    "level": "skilled"
   },
   {
    "name": "Swordsmanship"
   },
   {
    "name": "Pistol Shooting"
   }
  ],
  "traits": [
   {
    "name": "Daring",
    "kind": "gift",
    "description": "Bold actions often work in your favor."
   },
   {
    "name": "Wanted",
    "kind": "flaw",
    "description": "The Navy recognizes your face from minor merchant ship mutinies."
   }
  ],
  "disposition": {
   "temperament": {
    "traits": [
     "ambitious",
     "reckless"
    ],
    "wants": [
     "I want to be a pirate."
    ]
   }
  },
  "resources": {
   "items": [
    {
     "id": "weathered-cutlass",
     "name": "Weathered Cutlass",
     "kind": "weapon",
     "description": "A sturdy, reliable sword perfect for boarding actions."
    },
    {
     "id": "flintlock-pistol",
     "name": "Flintlock Pistol",
     "kind": "weapon",
     "description": "A single-shot pistol that packs a punch but takes time to reload."
    },
    {
     "id": "spyglass",
     "name": "Spyglass",
     "kind": "gear",
     "description": "A brass telescope for spotting prey on the horizon."
    }
   ],
   "money": 50,
   "currency": "silver shillings",
   "title": "Captain",
   "rank": "Outlaw"
  },
  "backstory": [
   {
    "text": "You spent years as a merchant sailor, tired of low pay and harsh beatings, before deciding to take your fate into your own hands."
   }
  ]
 },
 "gift": "none",
 "extraordinary": [
  "magic or anything supernatural (none)"
 ],
 "peoples": [
  {
   "id": "human",
   "name": "Human",
   "lifespan_years": 80,
   "culture": "A mix of sailors, merchants, naval officers, and outlaws from various nations."
  }
 ],
 "rules": [
  "Magic, monsters, and the supernatural do not exist; the sea is governed only by wind, tide, and iron.",
  "The Royal Navy hunts pirates relentlessly, and the penalty for piracy is hanging.",
  "The Brethren of the Coast follow a loose set of articles, but betrayal is common.",
  "Grounded: no magic and nothing supernatural, and that won't change."
 ],
 "others": [
  "Captain Edward 'Blackbeak' Teach, 42, peak attribute 3",
  "Governor Edward Sterling, 55, peak attribute 3"
 ],
 "people_in_the_world": 2,
 "years": {
  "age": 24.0,
  "lives_about": 80,
  "the_record_says_so": true,
  "old": false,
  "told_the_end_is_close": false
 }
}
```

## Turn 1 (opening), 19.8 s, $0.040

_From Day 1, morning, 08:00 to Day 1, morning, 08:00 (0 s). Jack is 24, alive._

The salt air of Tortuga carries the stench of spilled rum, roasting meat, and rotting fish. You stand on the sun-baked timber of the docks, the deed to a weathered sloop clutched tightly in your hand. She is a beautiful thing in her own rugged way, her mast cutting clean against the bright Caribbean sky. You won her fair and square on a final roll of the dice, and now she is yours to command. 

"A fine piece of wood, if she doesn't take on water at the first swell," a gravelly voice rumbles beside you. 

You turn to find Captain Edward "Blackbeak" Teach leaning against a stack of cargo crates. Smoke from the slow-matches tucked beneath his tricorn hat drifts lazily around his bearded face. His dark eyes size you up with cold, calculated interest, weighing whether you are a captain worth knowing or just another fool destined for the gallows. He nods toward your new vessel. "A sloop like that needs a crew, and a crew needs gold. What is your play, Captain?"

**Suggestions:**
1. Address Blackbeak and ask him for advice on recruiting a crew. (thread)
2. Inspect the sloop's hull and sails to ensure she is seaworthy. (personal)
3. Head to the nearest tavern to celebrate your win and buy drinks. (side)

**Issues:**
- rejected (character captain-blackbeak: rung Captain): no ladder has that rung
- start_told (person:captain-blackbeak): the story told it

## What the screens show (turn 1)

### The Character screen

```json
{
 "character": {
  "name": "Jack",
  "lines": [
   "Unhurt",
   "50 silver shillings",
   "Flintlock Pistol",
   "Spyglass",
   "Weathered Cutlass"
  ]
 },
 "sheet": {
  "about": [
   "Captain",
   "Outlaw",
   "24 years old"
  ],
  "description": "A young, ambitious sailor with a hunger for freedom and gold.",
  "condition": {
   "health": "unhurt",
   "health_label": "Unhurt"
  },
  "money_label": "50 silver shillings",
  "items": [
   {
    "name": "Flintlock Pistol",
    "kind": "weapon",
    "kind_label": "Weapon",
    "description": "A single-shot pistol that packs a punch but takes time to reload.",
    "quantity": 1,
    "carried": true
   },
   {
    "name": "Spyglass",
    "kind": "gear",
    "kind_label": "Gear",
    "description": "A brass telescope for spotting prey on the horizon.",
    "quantity": 1,
    "carried": true
   },
   {
    "name": "Weathered Cutlass",
    "kind": "weapon",
    "kind_label": "Weapon",
    "description": "A sturdy, reliable sword perfect for boarding actions.",
    "quantity": 1,
    "carried": true
   }
  ],
  "skills": [
   {
    "name": "Sailing",
    "level": "skilled",
    "level_label": "Skilled",
    "dice": 3
   },
   {
    "name": "Swordsmanship",
    "level": "fair",
    "level_label": "Fair",
    "dice": 2
   },
   {
    "name": "Pistol Shooting",
    "level": "fair",
    "level_label": "Fair",
    "dice": 2
   }
  ],
  "traits": [
   {
    "name": "Daring",
    "kind": "gift",
    "kind_label": "Gift",
    "description": "Bold actions often work in your favor."
   },
   {
    "name": "Wanted",
    "kind": "flaw",
    "kind_label": "Flaw",
    "description": "The Navy recognizes your face from minor merchant ship mutinies."
   }
  ],
  "temperament": [
   "ambitious",
   "reckless"
  ]
 },
 "reputation": [
  {
   "name": "Brethren of the Coast",
   "label": "Neutral"
  },
  {
   "name": "The Royal Navy",
   "label": "Neutral"
  }
 ],
 "clock": {
  "world_s": 0,
  "label": "Day 1, morning",
  "timeline_id": "main"
 },
 "since": [
  {
   "text": "The Windward Passage is currently crawling with rich merchant ships.",
   "ago_label": "moments ago"
  },
  {
   "text": "The Royal Navy is offering a 500 gold doubloon bounty for Captain Blackbeak.",
   "ago_label": "moments ago"
  }
 ]
}
```

### Memory

```json
{
 "character": {
  "name": "Jack",
  "lines": [
   "A young, ambitious sailor with a hunger for freedom and gold.",
   "Captain",
   "Outlaw"
  ]
 },
 "people": [
  {
   "id": "captain-blackbeak",
   "name": "Captain Edward 'Blackbeak' Teach",
   "lines": [
    "A fearsome pirate lord with burning slow-matches tucked into his hat."
   ],
   "attitude": "neutral",
   "attitude_label": "Neutral",
   "status": "alive",
   "presumed": false,
   "status_label": "Alive"
  }
 ],
 "places": [
  {
   "id": "port-royal",
   "name": "Port Royal",
   "lines": [
    "City",
    "A wealthy English colony guarded by a massive stone fort.",
    "You haven't been there."
   ]
  },
  {
   "id": "tortuga",
   "name": "Tortuga",
   "lines": [
    "Island",
    "A lawless haven filled with taverns, brothels, and pirate crews."
   ]
  },
  {
   "id": "windward-passage",
   "name": "Windward Passage",
   "lines": [
    "Wilds",
    "A treacherous stretch of open ocean frequented by merchant ships and hunting navy vessels.",
    "You haven't been there."
   ]
  }
 ],
 "factions": [
  {
   "id": "brethren-of-the-coast",
   "name": "Brethren of the Coast",
   "lines": [
    "Sect",
    "A loose alliance of pirate captains and buccaneers."
   ],
   "esteem": "neutral",
   "dread": "none",
   "standing_label": "Neutral"
  },
  {
   "id": "royal-navy",
   "name": "The Royal Navy",
   "lines": [
    "Fleet",
    "The disciplined naval force of the British Crown, tasked with wiping out piracy."
   ],
   "esteem": "neutral",
   "dread": "none",
   "standing_label": "Neutral"
  }
 ]
}
```


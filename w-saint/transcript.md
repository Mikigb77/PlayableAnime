## The draft (en, teen)

> An 80-year-old sword saint who retired to a quiet mountain village decades ago. He was once the best swordsman in the kingdom.

_29.7 s, $0.076_

### What the draft's screen shows

The Sword Saint's Autumn
martial fantasy
bittersweet
Sword aura: real, and rare.
Medieval kingdom: steel blades, horse carriages, and parchment letters.
Martial Ranks: Novice, Swordsman, Sword Master, Sword Saint.
Peoples: Human.
The Flying Swords Sect: An ambitious martial arts sect looking to prove their dominance in the kingdom.
The Royal Court: The rulers of the realm, desperate for martial power to defend their borders.
Shin, 80, Human.
An old, unassuming mountain dweller with a sharp, piercing gaze that occasionally betrays his legendary past.
Retired Legend.
Sword Saint, late stage.
Master: Swordplay. Expert: Meditation. Fair: Survival.
Gifts: Unreadable Presence. Flaws: Aching Joints.
Serene, weary and disciplined.
Cloud-Cutting Aura: Cloud-Cutting Aura (Your physical body can only sustain intense aura projection for short bursts before your old muscles fail.). Cost: Using your full aura forces you to rest for several hours to recover from deep physical exhaustion.
Carries Old Wooden Training Sword. Owns Cloud-Cutter Katana. 50 copper coins.
Refining one's sword aura preserves the spirit and extends natural lifespan, but cannot heal structural physical decay.
Only a true martial master can project their sword aura outwardly to strike targets from a distance.
Sword aura: real, and rare.

### On record (the player never sees this)

```json
{
 "world": {
  "title": "The Sword Saint's Autumn",
  "genre": "martial fantasy",
  "era": "Medieval kingdom: steel blades, horse carriages, and parchment letters"
 },
 "character": {
  "id": "player",
  "name": "Shin",
  "aliases": [
   "Kensei Shin",
   "The Cloud-Cutter"
  ],
  "prominence": "key",
  "description": "An old, unassuming mountain dweller with a sharp, piercing gaze that occasionally betrays his legendary past.",
  "appearance": "A thin, elderly man with long white hair tied loosely, a weathered face marked by deep lines of wisdom, wearing simple, patched grey cotton robes.",
  "age": 80,
  "people_id": "human",
  "location_id": "saint-cabin",
  "origin": {
   "kind": "premise"
  },
  "known_by": [
   "player"
  ],
  "met_by": [
   "player"
  ],
  "lifespan_years": 110
 },
 "sheet": {
  "attributes": {
   "wits": 5,
   "knowledge": 5,
   "willpower": 5,
   "nerve": 5,
   "bearing": 5
  },
  "skills": [
   {
    "name": "Swordplay",
    "level": "master",
    "notes": "Even in old age, your form is flawless and your movements are effortless."
   },
   {
    "name": "Meditation",
    "level": "expert",
    "notes": "Used to refine aura and calm the mind."
   },
   {
    "name": "Survival",
    "notes": "Gathering herbs, woodcutting, and living off the mountain."
   }
  ],
  "traits": [
   {
    "name": "Aching Joints",
    "kind": "flaw",
    "description": "Old age and past battle wounds make your body stiff and painful in damp or cold weather."
   },
   {
    "name": "Unreadable Presence",
    "kind": "gift",
    "description": "You can completely mask your martial strength, appearing as nothing more than a fragile old farmer."
   }
  ],
  "powers": [
   {
    "id": "cloud-cutting-aura",
    "name": "Cloud-Cutting Aura",
    "strength": "rare",
    "limits": [
     "Your physical body can only sustain intense aura projection for short bursts before your old muscles fail."
    ],
    "costs": [
     {
      "kind": "fatigue",
      "text": "Using your full aura forces you to rest for several hours to recover from deep physical exhaustion."
     }
    ]
   }
  ],
  "techniques": [
   {
    "id": "first-form-flowing-water",
    "name": "First Form: Flowing Water",
    "style": "Cloud-Cutter Style",
    "effect": "Deflects incoming attacks using minimal physical effort.",
    "cost": "Minimal stamina",
    "requirements": "A sword or wooden staff"
   },
   {
    "id": "final-form-heaven-s-sever",
    "name": "Final Form: Heaven's Sever",
    "style": "Cloud-Cutter Style",
    "effect": "A single, blindingly fast slash reinforced with projected aura that can slice steel.",
    "cost": "High fatigue",
    "requirements": "A steel blade and focused aura"
   }
  ],
  "disposition": {
   "temperament": {
    "traits": [
     "serene",
     "weary",
     "disciplined"
    ],
    "values": [
     "peace",
     "discretion"
    ],
    "loves": [
     "quiet mornings",
     "well-brewed tea",
     "watching Mei progress"
    ],
    "fears": [
     "bringing blood and war to this peaceful village"
    ]
   }
  },
  "resources": {
   "items": [
    {
     "id": "old-wooden-training-sword",
     "name": "Old Wooden Training Sword",
     "kind": "weapon",
     "description": "An old practice sword made of heavy oak, smooth from years of use."
    },
    {
     "id": "cloud-cutter-katana",
     "name": "Cloud-Cutter Katana",
     "kind": "weapon",
     "description": "Your legendary steel sword, now wrapped in dusty cloth and hidden beneath your bed.",
     "carried": false
    }
   ],
   "money": 50,
   "currency": "copper coins",
   "title": "Sword Saint",
   "rank": "Retired Legend",
   "connections": [
    {
     "name": "Mei",
     "kind": "family",
     "character_id": "mei",
     "note": "Your devoted disciple and helper."
    }
   ]
  },
  "condition": {
   "reserves": [
    {
     "name": "Sword Qi"
    }
   ]
  },
  "axes": {
   "might": 8,
   "knowledge": 4,
   "stealth": 3
  },
  "ladders": [
   {
    "ladder_id": "martial-ranks",
    "rung": 3,
    "stage": "late"
   }
  ],
  "backstory": [
   {
    "text": "You fought in the Great Unification wars decades ago, earning the title of the kingdom's greatest swordsman."
   },
   {
    "text": "Disillusioned by the cruelty of the court, you fled into retirement, letting the world believe you had died of your wounds."
   }
  ]
 },
 "gift": "rare",
 "extraordinary": [
  "sword aura (rare): Enhancing physical strikes, cutting through solid stone with wind pressure, and sensing incoming attacks."
 ],
 "ladders": [
  {
   "id": "martial-ranks",
   "name": "Martial Ranks",
   "rungs": [
    "0: Novice (tier 2)",
    "1: Swordsman (tier 4)",
    "2: Sword Master (tier 6)",
    "3: Sword Saint (tier 8)"
   ]
  }
 ],
 "peoples": [
  {
   "id": "human",
   "name": "Human",
   "description": "The dominant people of the kingdom.",
   "lifespan_years": 80
  }
 ],
 "rules": [
  "Refining one's sword aura preserves the spirit and extends natural lifespan, but cannot heal structural physical decay.",
  "Only a true martial master can project their sword aura outwardly to strike targets from a distance.",
  "Sword aura: real, and rare."
 ],
 "others": [
  "Commander Reynold, 42, martial-ranks rung 1, peak attribute 4",
  "Mei, 18, martial-ranks rung 0, peak attribute 4"
 ],
 "people_in_the_world": 2
}
```

## Turn 1 (opening), 6.1 s, $0.042

_From Day 1, morning, 08:00 to Day 1, morning, 08:00 (0 s). Shin is 80, alive._

You sit by the crackling hearth sipping hot bamboo tea, resting your aching, eighty-year-old knees while young Mei sweeps the wooden floor with rhythmic, disciplined strokes of her broom. Outside, the damp mountain fog of the Misty Vales clings to the bamboo thatch of your cabin, making your ancient bones thrum with a dull, familiar ache. It has been thirty years since you were Kensei Shin, the legendary Cloud-Cutter whose blade once carved through iron as if it were soft butter. Today, you are simply a weary old farmer, your presence fully masked, watching your young disciple with quiet warmth. Mei stops sweeping, her dark eyes reflecting the hearth fire as she rests her chin on the broom handle. 'Master,' she says softly, her brow furrowing with gentle concern. 'The mountain wind is heavy today. I will boil more ginger to soothe your joints, but we are running low on dry firewood.' Before you can reply, the heavy silence of the mountain is broken by the distant, rhythmic crunch of iron-shod boots on gravel, marching steadily up the path from Yamasuki Village.

**Suggestions:**
1. Gently tell Mei to stay inside while you check the door. (thread)
2. Reach quietly beneath the bed to touch your hidden katana. (personal)
3. Ask Mei to brew more tea for whoever is coming. (side)

**Issues:**
- start_told (person:mei): the story told it

## Turn 2 (action), 8.3 s, $0.034

> I teach the village children their sword forms in the morning, then rest under the plum tree.

_From Day 1, morning, 08:00 to Day 1, midday, 11:00 (3.0 hours). Shin is 80, alive._

**Read and decided:**
- read as task, 'teach', 7200 s: I teach the village children their sword forms in the morning.
- read as rest, 'rest', 3600 s: I rest under the plum tree.
- I teach the village children their sword forms in the morning. [certain, success]: Nothing stands in the way.
- I rest under the plum tree. [certain, success]: Nothing stands in the way.
- heading: Three hours later

You take a slow, deliberate sip of your warm bamboo tea as the crunch of boots draws nearer on the path. You look up at Mei, giving her a reassuring nod, before you rise from the hearth to begin the morning's quiet routine.

To keep the peace of this mountain, you choose the familiar rhythm of daily life over the threat of steel. You gather the few village children who make the trek up the mountain, showing them how to find balance in their stance and align their small wooden practice blades. Your joints ache with every slow instruction, but your form remains flawless, an effortless display of mastery disguised as a simple farmer's lesson. By the time the lessons are finished and the children head back down the gravel trail, the midday sun has broken through the damp fog. You walk slowly to the old plum tree behind the cabin and sit in its cooling shade, letting your tired body rest. From the edge of the clearing, the heavy iron-shod boots finally come to a halt. A stern-faced man in the polished armor of a royal commander steps into the yard, his sharp eyes sweeping over the quiet cabin.

**Suggestions:**
1. Remain silent and let the commander speak first. (thread)
2. Offer the armored commander a cup of bamboo tea. (personal)
3. Quietly signal Mei to slip away inside the cabin. (side)

**Issues:**
- rejected (character commander-reynold: age): only the engine decides this
- rejected (character commander-reynold: meeting): the record has them elsewhere, and only the world brings them here
- rejected (character commander-reynold: rung Sword Master): only someone this scene brought in comes standing on it: nobody is lifted
- rejected (character commander-reynold: presence): the record has them elsewhere, and only the world brings them here

## Turn 3 (action), 7.8 s, $0.032

> I let a whole year pass like this, teaching the children and tending my garden.

_From Day 1, midday, 11:00 to Day 121, evening, 20:06 (120.4 days). Shin is 80, alive._

**Read and decided:**
- read as time_skip, 'wait', 31536000 s: I let a whole year pass like this, teaching the children and tending my garden.
- I let a whole year pass like this, teaching the children and tending my garden. [certain, success]: Nothing stands in the way.
- event: "Commander Reynold seeks you out"
- heading: Four months later

You let the days stretch out like the roots of the old plum tree, letting a year's quiet rhythm of garden-tending and instruction keep the world at bay.

But the empire's shadow is not so easily outpaced, and the four months that follow do not grant you the full cycle of seasons you sought. The damp, clinging cold of late autumn settles into the Misty Vales, and with it comes the familiar, heavy step you had hoped to forget. 

One misty evening, the crack of a dry twig announces the return of the Vanguard Commander. Commander Reynold steps out of the gray drizzle, his crimson cape damp and dark, his iron armor smelling of wet steel. He does not draw his blade, but his face is set in stone. He looks at you, then at Mei, who instantly shifts to stand closer to your side, her fingers white around the handle of her broom. 

"The kingdom is bleeding, Shin," Reynold says, his voice flat with the exhaustion of a long journey. "The capital's outer walls are under siege. I did not come to drag a corpse to the front, but the crown remembers its sworn saints. I need a legend to turn the tide. Will you answer the call, or must I draft every able-bodied youth from Yamasuki to build a wall of flesh?"

**Suggestions:**
1. Refuse him firmly, saying Kensei Shin died thirty years ago. (thread)
2. Offer to go with him if he spares the village. (thread)
3. Invite him inside for a cup of hot bamboo tea first. (personal)

**Issues:**
- start_told (person:commander-reynold): the story told it

## What the screens show (turn 3)

### The Character screen

```json
{
 "character": {
  "name": "Shin",
  "lines": [
   "Martial Ranks: Sword Saint",
   "Unhurt",
   "Sword Qi: 100%",
   "Cloud-Cutting Aura: ready",
   "Cloud-Cutting Aura, cost: Using your full aura forces you to rest for several hours to recover from deep physical exhaustion",
   "First Form: Flowing Water (technique, practiced, 0 of 15 uses)",
   "Final Form: Heaven's Sever (technique, practiced, 0 of 15 uses)",
   "50 copper coins",
   "Old Wooden Training Sword"
  ]
 },
 "sheet": {
  "about": [
   "Sword Saint",
   "Retired Legend",
   "80 years old"
  ],
  "description": "An old, unassuming mountain dweller with a sharp, piercing gaze that occasionally betrays his legendary past.",
  "condition": {
   "health": "unhurt",
   "health_label": "Unhurt",
   "reserves": [
    {
     "name": "Sword Qi",
     "level": 100
    }
   ]
  },
  "paths": [
   {
    "name": "Martial Ranks",
    "rungs": [
     {
      "name": "Novice"
     },
     {
      "name": "Swordsman"
     },
     {
      "name": "Sword Master"
     },
     {
      "name": "Sword Saint",
      "description": "A living legend whose blade is an extension of their soul. A rare peak of mortal cultivation."
     }
    ]
   }
  ],
  "money_label": "50 copper coins",
  "items": [
   {
    "name": "Old Wooden Training Sword",
    "kind": "weapon",
    "kind_label": "Weapon",
    "description": "An old practice sword made of heavy oak, smooth from years of use.",
    "quantity": 1,
    "carried": true
   },
   {
    "name": "Cloud-Cutter Katana",
    "kind": "weapon",
    "kind_label": "Weapon",
    "description": "Your legendary steel sword, now wrapped in dusty cloth and hidden beneath your bed.",
    "quantity": 1,
    "carried": false
   }
  ],
  "skills": [
   {
    "name": "Swordplay",
    "level": "master",
    "level_label": "Master",
    "dice": 5,
    "notes": "Even in old age, your form is flawless and your movements are effortless."
   },
   {
    "name": "Meditation",
    "level": "expert",
    "level_label": "Expert",
    "dice": 4,
    "notes": "Used to refine aura and calm the mind."
   },
   {
    "name": "Survival",
    "level": "fair",
    "level_label": "Fair",
    "dice": 2,
    "notes": "Gathering herbs, woodcutting, and living off the mountain."
   }
  ],
  "powers": [
   {
    "name": "Cloud-Cutting Aura",
    "limits": [
     "Your physical body can only sustain intense aura projection for short bursts before your old muscles fail."
    ],
    "cost": "Using your full aura forces you to rest for several hours to recover from deep physical exhaustion",
    "ready": true,
    "ready_label": "Ready",
    "secret": false
   }
  ],
  "techniques": [
   {
    "name": "First Form: Flowing Water",
    "style": "Cloud-Cutter Style",
    "effect": "Deflects incoming attacks using minimal physical effort.",
    "cost": "Minimal stamina",
    "mastery": "practiced",
    "mastery_label": "Practiced",
    "dice": 2,
    "uses": 0,
    "need": 15
   },
   {
    "name": "Final Form: Heaven's Sever",
    "style": "Cloud-Cutter Style",
    "effect": "A single, blindingly fast slash reinforced with projected aura that can slice steel.",
    "cost": "High fatigue",
    "mastery": "practiced",
    "mastery_label": "Practiced",
    "dice": 2,
    "uses": 0,
    "need": 15
   }
  ],
  "traits": [
   {
    "name": "Aching Joints",
    "kind": "flaw",
    "kind_label": "Flaw",
    "description": "Old age and past battle wounds make your body stiff and painful in damp or cold weather."
   },
   {
    "name": "Unreadable Presence",
    "kind": "gift",
    "kind_label": "Gift",
    "description": "You can completely mask your martial strength, appearing as nothing more than a fragile old farmer."
   }
  ],
  "temperament": [
   "serene",
   "weary",
   "disciplined"
  ]
 },
 "reputation": [
  {
   "name": "The Flying Swords Sect",
   "label": "Neutral"
  },
  {
   "name": "The Royal Court",
   "label": "Neutral"
  }
 ],
 "clock": {
  "world_s": 10411600,
  "label": "Day 121, evening",
  "timeline_id": "main"
 },
 "since": [
  {
   "text": "Your old bones ache in the mountain dampness, reminding you that even saints cannot escape time.",
   "ago_label": "4 months ago"
  },
  {
   "text": "Thirty years ago, you walked away from fame, glory, and blood to live in obscurity.",
   "ago_label": "4 months ago"
  },
  {
   "text": "You were once the celebrated Sword Saint of the kingdom.",
   "ago_label": "4 months ago"
  }
 ]
}
```

### On record (the player never sees this)

```json
{
 "world": {
  "title": "The Sword Saint's Autumn",
  "genre": "martial fantasy",
  "era": "Medieval kingdom: steel blades, horse carriages, and parchment letters"
 },
 "character": {
  "id": "player",
  "name": "Shin",
  "aliases": [
   "Kensei Shin",
   "The Cloud-Cutter"
  ],
  "prominence": "key",
  "description": "An old, unassuming mountain dweller with a sharp, piercing gaze that occasionally betrays his legendary past.",
  "appearance": "A thin, elderly man with long white hair tied loosely, a weathered face marked by deep lines of wisdom, wearing simple, patched grey cotton robes.",
  "age": 80,
  "people_id": "human",
  "location_id": "saint-cabin",
  "origin": {
   "kind": "premise"
  },
  "known_by": [
   "player"
  ],
  "met_by": [
   "player"
  ],
  "lifespan_years": 110
 },
 "sheet": {
  "attributes": {
   "wits": 5,
   "knowledge": 5,
   "willpower": 5,
   "nerve": 5,
   "bearing": 5
  },
  "skills": [
   {
    "name": "Swordplay",
    "level": "master",
    "notes": "Even in old age, your form is flawless and your movements are effortless."
   },
   {
    "name": "Meditation",
    "level": "expert",
    "notes": "Used to refine aura and calm the mind."
   },
   {
    "name": "Survival",
    "notes": "Gathering herbs, woodcutting, and living off the mountain."
   }
  ],
  "traits": [
   {
    "name": "Aching Joints",
    "kind": "flaw",
    "description": "Old age and past battle wounds make your body stiff and painful in damp or cold weather."
   },
   {
    "name": "Unreadable Presence",
    "kind": "gift",
    "description": "You can completely mask your martial strength, appearing as nothing more than a fragile old farmer."
   }
  ],
  "powers": [
   {
    "id": "cloud-cutting-aura",
    "name": "Cloud-Cutting Aura",
    "strength": "rare",
    "limits": [
     "Your physical body can only sustain intense aura projection for short bursts before your old muscles fail."
    ],
    "costs": [
     {
      "kind": "fatigue",
      "text": "Using your full aura forces you to rest for several hours to recover from deep physical exhaustion."
     }
    ]
   }
  ],
  "techniques": [
   {
    "id": "first-form-flowing-water",
    "name": "First Form: Flowing Water",
    "style": "Cloud-Cutter Style",
    "effect": "Deflects incoming attacks using minimal physical effort.",
    "cost": "Minimal stamina",
    "requirements": "A sword or wooden staff"
   },
   {
    "id": "final-form-heaven-s-sever",
    "name": "Final Form: Heaven's Sever",
    "style": "Cloud-Cutter Style",
    "effect": "A single, blindingly fast slash reinforced with projected aura that can slice steel.",
    "cost": "High fatigue",
    "requirements": "A steel blade and focused aura"
   }
  ],
  "disposition": {
   "temperament": {
    "traits": [
     "serene",
     "weary",
     "disciplined"
    ],
    "values": [
     "peace",
     "discretion"
    ],
    "loves": [
     "quiet mornings",
     "well-brewed tea",
     "watching Mei progress"
    ],
    "fears": [
     "bringing blood and war to this peaceful village"
    ]
   }
  },
  "resources": {
   "items": [
    {
     "id": "old-wooden-training-sword",
     "name": "Old Wooden Training Sword",
     "kind": "weapon",
     "description": "An old practice sword made of heavy oak, smooth from years of use."
    },
    {
     "id": "cloud-cutter-katana",
     "name": "Cloud-Cutter Katana",
     "kind": "weapon",
     "description": "Your legendary steel sword, now wrapped in dusty cloth and hidden beneath your bed.",
     "carried": false
    }
   ],
   "money": 50,
   "currency": "copper coins",
   "title": "Sword Saint",
   "rank": "Retired Legend",
   "connections": [
    {
     "name": "Mei",
     "kind": "family",
     "character_id": "mei",
     "note": "Your devoted disciple and helper."
    }
   ]
  },
  "condition": {
   "reserves": [
    {
     "name": "Sword Qi"
    }
   ]
  },
  "axes": {
   "might": 8,
   "knowledge": 4,
   "stealth": 3
  },
  "ladders": [
   {
    "ladder_id": "martial-ranks",
    "rung": 3,
    "stage": "late"
   }
  ],
  "backstory": [
   {
    "text": "You fought in the Great Unification wars decades ago, earning the title of the kingdom's greatest swordsman."
   },
   {
    "text": "Disillusioned by the cruelty of the court, you fled into retirement, letting the world believe you had died of your wounds."
   }
  ]
 },
 "gift": "rare",
 "extraordinary": [
  "sword aura (rare): Enhancing physical strikes, cutting through solid stone with wind pressure, and sensing incoming attacks."
 ],
 "ladders": [
  {
   "id": "martial-ranks",
   "name": "Martial Ranks",
   "rungs": [
    "0: Novice (tier 2, lives 0)",
    "1: Swordsman (tier 4, lives 0)",
    "2: Sword Master (tier 6, lives 0)",
    "3: Sword Saint (tier 8, lives 0)"
   ]
  }
 ],
 "peoples": [
  {
   "id": "human",
   "name": "Human",
   "description": "The dominant people of the kingdom.",
   "lifespan_years": 80
  }
 ],
 "rules": [
  "Refining one's sword aura preserves the spirit and extends natural lifespan, but cannot heal structural physical decay.",
  "Only a true martial master can project their sword aura outwardly to strike targets from a distance.",
  "Sword aura: real, and rare."
 ],
 "others": [
  "Commander Reynold, 42, martial-ranks rung 1, peak attribute 4",
  "Mei, 18, martial-ranks rung 0, peak attribute 4"
 ],
 "people_in_the_world": 2,
 "years": {
  "age": 80.3,
  "lives_about": 110,
  "the_record_says_so": true,
  "old": false,
  "told_the_end_is_close": false
 },
 "waiting": [
  "director.plays_out 'Commander Reynold seeks you out: left alone' in 1.0 days",
  "world.tick 'The world moves on' in 1.2 days",
  "world.old_age 'Your years run short' in 20.3 years (stops the player)"
 ]
}
```


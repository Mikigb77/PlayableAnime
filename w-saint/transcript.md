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


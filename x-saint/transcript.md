## The draft (en, teen)

> An 80-year-old sword saint who retired to a quiet mountain village decades ago. He was once the best swordsman in the kingdom.

_30.6 s, $0.077: 1997 tokens of thinking, 4685 of answer, 1 tries_

### What the draft's screen shows

The Retired Saint
Wuxia, Martial Arts
Nostalgic, peaceful, yet watchful
Aura channeling: real, and rare.
A medieval Eastern kingdom where steel swords and horse carriage travel prevail.
Martial Realms: Disciple, Expert, Grandmaster, Sword Saint.
Peoples: Humans.
The Imperial Court: The ruling authority of the kingdom, currently facing internal rebellion.
Master Jian, 80, Humans.
A calm, slow-moving old man with a deep, quiet presence that hints at a lifetime of supreme mastery.
Legend.
Sword Saint, at its peak.
Master: swordplay. Expert: meditation. Skilled: calligraphy.
Gifts: Unshakable Calm. Flaws: Aged Body.
Wise, serene and reflective.
Sword Aura Mastery: Allows you to channel your remaining vital energy into your sword, producing invisible waves of cutting force (Requires a sword or a sword-like object.). Cost: Using this power drains your elderly body's stamina rapidly.
Carries Worn Broom. Owns The Willow Blade. 15 silver coins.
Channeling aura grants immense power but inflicts severe physical strain on an elderly body.
By ancient custom, retired Sword Saints are exempt from royal conscription unless they brandish their blade in public.
Aura channeling: real, and rare.

### On record (the player never sees this)

```json
{
 "world": {
  "title": "The Retired Saint",
  "genre": "Wuxia, Martial Arts",
  "era": "A medieval Eastern kingdom where steel swords and horse carriage travel prevail."
 },
 "character": {
  "id": "player",
  "name": "Master Jian",
  "aliases": [
   "The Sword Saint",
   "Jianmu"
  ],
  "prominence": "key",
  "description": "A calm, slow-moving old man with a deep, quiet presence that hints at a lifetime of supreme mastery.",
  "appearance": "Long, snow-white hair tied in a simple bun, a weathered face etched with deep wisdom lines, and warm, sharp eyes. He wears faded gray cotton robes and straw sandals.",
  "age": 80,
  "people_id": "human",
  "location_id": "saint-cottage",
  "origin": {
   "kind": "premise"
  },
  "known_by": [
   "player"
  ],
  "met_by": [
   "player"
  ],
  "lifespan_years": 100
 },
 "sheet": {
  "attributes": {
   "speed": 4,
   "wits": 5,
   "knowledge": 5,
   "willpower": 5,
   "charm": 4,
   "nerve": 5,
   "bearing": 5
  },
  "skills": [
   {
    "name": "swordplay",
    "level": "master",
    "notes": "Your blade work is flawless, relying on muscle memory and supreme technique rather than raw brute strength."
   },
   {
    "name": "meditation",
    "level": "expert",
    "notes": "Allows you to keep your mind tranquil and focus your remaining aura."
   },
   {
    "name": "calligraphy",
    "level": "skilled",
    "notes": "A peaceful hobby that helps you channel your discipline."
   }
  ],
  "traits": [
   {
    "name": "Aged Body",
    "kind": "flaw",
    "description": "Your physical stamina is limited; long fights will exhaust your muscles and breath much faster than in your prime."
   },
   {
    "name": "Unshakable Calm",
    "kind": "gift",
    "description": "Having faced death hundreds of times, no threat or sudden crisis can break your concentration."
   }
  ],
  "powers": [
   {
    "id": "saint-aura",
    "name": "Sword Aura Mastery",
    "description": "Allows you to channel your remaining vital energy into your sword, producing invisible waves of cutting force.",
    "limits": [
     "Requires a sword or a sword-like object."
    ],
    "costs": [
     {
      "kind": "fatigue",
      "text": "Using this power drains your elderly body's stamina rapidly."
     }
    ]
   }
  ],
  "techniques": [
   {
    "id": "severing-wind",
    "name": "Severing Wind",
    "style": "Sword Saint Style",
    "effect": "A single swift slash that projects aura up to thirty paces, cleanly cutting wood, stone, or armor.",
    "cost": "Moderate stamina drain",
    "requirements": "A sword and a calm breath"
   }
  ],
  "disposition": {
   "temperament": {
    "traits": [
     "wise",
     "serene",
     "reflective"
    ],
    "values": [
     "peace",
     "humility"
    ],
    "loves": [
     "hot tea",
     "quiet mornings"
    ],
    "fears": [
     "the village being dragged into war"
    ]
   }
  },
  "resources": {
   "items": [
    {
     "id": "the-willow-blade",
     "name": "The Willow Blade",
     "kind": "weapon",
     "description": "Your legendary steel sword, now wrapped in coarse linen and hidden under the floorboards.",
     "carried": false
    },
    {
     "id": "worn-broom",
     "name": "Worn Broom",
     "kind": "gear",
     "description": "A simple bamboo broom used for sweeping the cottage porch."
    }
   ],
   "money": 15,
   "currency": "silver coins",
   "title": "Retired Sword Saint",
   "rank": "Legend",
   "connections": [
    {
     "name": "Xiaotian",
     "kind": "trusts_them",
     "character_id": "xiaotian",
     "note": "A local boy who looks up to you and begs for martial arts stories."
    }
   ]
  },
  "condition": {
   "reserves": [
    {
     "name": "aura"
    }
   ]
  },
  "axes": {
   "might": 8,
   "influence": 4,
   "wealth": 2,
   "knowledge": 5,
   "stealth": 3
  },
  "ladders": [
   {
    "ladder_id": "martial-realms",
    "rung": 3,
    "stage": "peak"
   }
  ],
  "backstory": [
   {
    "text": "You were once the undisputed master of the sword in the Jade Kingdom."
   },
   {
    "text": "Fifty years ago, sick of the blood, court intrigue, and endless challengers, you faked your death or simply walked away, finding refuge in this mountain valley."
   }
  ]
 },
 "gift": "none",
 "extraordinary": [
  "Aura channeling (rare): Enables masters to enhance their strikes, cut iron, and project deadly shockwaves."
 ],
 "ladders": [
  {
   "id": "martial-realms",
   "name": "Martial Realms",
   "rungs": [
    "0: Disciple (tier 2, lives 0)",
    "1: Expert (tier 4, lives 0)",
    "2: Grandmaster (tier 6, lives 0)",
    "3: Sword Saint (tier 8, lives 0)"
   ]
  }
 ],
 "peoples": [
  {
   "id": "human",
   "name": "Humans",
   "lifespan_years": 80,
   "culture": "A society deeply rooted in honor, martial sects, and agrarian tradition."
  }
 ],
 "rules": [
  "Channeling aura grants immense power but inflicts severe physical strain on an elderly body.",
  "By ancient custom, retired Sword Saints are exempt from royal conscription unless they brandish their blade in public.",
  "Aura channeling: real, and rare."
 ],
 "others": [
  "Commander Chen, 45, martial-realms rung 1, peak attribute 4",
  "Xiaotian, 14, peak attribute 4"
 ],
 "people_in_the_world": 2,
 "years": {
  "age": 80.0,
  "lives_about": 100,
  "the_record_says_so": true,
  "old": false,
  "told_the_end_is_close": false
 }
}
```

## Turn 1 (opening), 6.8 s, $0.043

_From Day 1, morning, 07:00 to Day 1, morning, 07:00 (0 s). Master Jian is 80, alive._

You drag the worn bamboo broom over the porch, its rhythmic scrape a comforting melody in the crisp mountain air. Wisps of steam rise from the rusted tea kettle on the brazier, carrying the faint, earthy scent of wild mountain leaves. For decades, this silence has been your shield. But the peace of the valley is easily startled, like a deer in the brush.

Young Xiaotian comes skidding around the bend of the dirt trail. He is panting, his wooden sword gripped tightly in his small, calloused fist. His thin chest heaves beneath his patched linen tunic, his cheeks flushed red from the sprint up the slope.

"Master Jian!" the boy gasps, leaning heavily on his wooden blade. His eyes are wide with a mixture of terror and awe. "Down by the village well... there are horses. Grand, sleek warhorses with silver-trimmed saddles. Men in dark blue silk robes are asking for a master of the white-hair style. They say they carry an imperial crest!"

You pause your sweeping, resting both hands on the smooth bamboo handle of your broom. The wind rustles through the bamboo grove behind your cottage, a cold reminder that the past never truly stays buried.

**Suggestions:**
1. Ask Xiaotian quietly how many soldiers are in the village. (thread)
2. Pour two cups of hot tea and invite the boy to sit. (personal)
3. Retrieve the Willow Blade from beneath the floorboards. (side)

**Issues:**
- start_told (person:xiaotian): the story told it

## What the screens show (turn 1)

### The Character screen

```json
{
 "character": {
  "name": "Master Jian",
  "lines": [
   "Martial Realms: Sword Saint",
   "Unhurt",
   "Aura: 100%",
   "Sword Aura Mastery: ready",
   "Sword Aura Mastery, cost: Using this power drains your elderly body's stamina rapidly",
   "Severing Wind (technique, practiced, 0 of 15 uses)",
   "15 silver coins",
   "Worn Broom"
  ]
 },
 "sheet": {
  "about": [
   "Retired Sword Saint",
   "Legend",
   "80 years old"
  ],
  "description": "A calm, slow-moving old man with a deep, quiet presence that hints at a lifetime of supreme mastery.",
  "condition": {
   "health": "unhurt",
   "health_label": "Unhurt",
   "reserves": [
    {
     "name": "Aura",
     "level": 100
    }
   ]
  },
  "paths": [
   {
    "name": "Martial Realms",
    "rungs": [
     {
      "name": "Disciple"
     },
     {
      "name": "Expert"
     },
     {
      "name": "Grandmaster"
     },
     {
      "name": "Sword Saint",
      "description": "A legendary status where the sword and soul are one, cutting through air itself."
     }
    ]
   }
  ],
  "money_label": "15 silver coins",
  "items": [
   {
    "name": "Worn Broom",
    "kind": "gear",
    "kind_label": "Gear",
    "description": "A simple bamboo broom used for sweeping the cottage porch.",
    "quantity": 1,
    "carried": true
   },
   {
    "name": "The Willow Blade",
    "kind": "weapon",
    "kind_label": "Weapon",
    "description": "Your legendary steel sword, now wrapped in coarse linen and hidden under the floorboards.",
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
    "notes": "Your blade work is flawless, relying on muscle memory and supreme technique rather than raw brute strength."
   },
   {
    "name": "Meditation",
    "level": "expert",
    "level_label": "Expert",
    "dice": 4,
    "notes": "Allows you to keep your mind tranquil and focus your remaining aura."
   },
   {
    "name": "Calligraphy",
    "level": "skilled",
    "level_label": "Skilled",
    "dice": 3,
    "notes": "A peaceful hobby that helps you channel your discipline."
   }
  ],
  "powers": [
   {
    "name": "Sword Aura Mastery",
    "description": "Allows you to channel your remaining vital energy into your sword, producing invisible waves of cutting force.",
    "limits": [
     "Requires a sword or a sword-like object."
    ],
    "cost": "Using this power drains your elderly body's stamina rapidly",
    "ready": true,
    "ready_label": "Ready",
    "secret": false
   }
  ],
  "techniques": [
   {
    "name": "Severing Wind",
    "style": "Sword Saint Style",
    "effect": "A single swift slash that projects aura up to thirty paces, cleanly cutting wood, stone, or armor.",
    "cost": "Moderate stamina drain",
    "mastery": "practiced",
    "mastery_label": "Practiced",
    "dice": 2,
    "uses": 0,
    "need": 15
   }
  ],
  "traits": [
   {
    "name": "Aged Body",
    "kind": "flaw",
    "kind_label": "Flaw",
    "description": "Your physical stamina is limited; long fights will exhaust your muscles and breath much faster than in your prime."
   },
   {
    "name": "Unshakable Calm",
    "kind": "gift",
    "kind_label": "Gift",
    "description": "Having faced death hundreds of times, no threat or sudden crisis can break your concentration."
   }
  ],
  "temperament": [
   "wise",
   "serene",
   "reflective"
  ]
 },
 "reputation": [
  {
   "name": "The Imperial Court",
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
   "text": "Decades ago, you retired to this quiet mountain village to escape the endless cycles of blood and ambition.",
   "ago_label": "moments ago"
  },
  {
   "text": "You were once the best swordsman in the kingdom, revered as the Sword Saint.",
   "ago_label": "moments ago"
  }
 ]
}
```

### Memory

```json
{
 "character": {
  "name": "Master Jian",
  "lines": [
   "A calm, slow-moving old man with a deep, quiet presence that hints at a lifetime of supreme mastery.",
   "Retired Sword Saint",
   "Legend",
   "Martial Realms: Sword Saint"
  ]
 },
 "people": [
  {
   "id": "xiaotian",
   "name": "Xiaotian",
   "lines": [
    "A bright-eyed village youth who dreams of becoming a legendary martial artist."
   ],
   "attitude": "warm",
   "attitude_label": "Warm",
   "status": "alive",
   "presumed": false,
   "status_label": "Alive"
  }
 ],
 "places": [
  {
   "id": "capital-city",
   "name": "The Jade Capital",
   "lines": [
    "City",
    "The bustling heart of the kingdom, filled with grand temples and martial schools.",
    "You haven't been there."
   ]
  },
  {
   "id": "mountain-village",
   "name": "Mountain Village",
   "lines": [
    "Village",
    "A quiet agrarian settlement where life revolves around farming and seasonal festivals.",
    "You haven't been there."
   ]
  },
  {
   "id": "saint-cottage",
   "name": "The Retired Saint's Cottage",
   "lines": [
    "Building",
    "A modest wooden home nestled against a bamboo grove at the village edge."
   ]
  },
  {
   "id": "serene-valley",
   "name": "Serene Valley",
   "lines": [
    "Region",
    "A mist-shrouded mountain region far from the capital's politics.",
    "You haven't been there."
   ]
  },
  {
   "id": "mountain-pass",
   "name": "Whispering Pass",
   "lines": [
    "Wilds",
    "The narrow, windy gateway that connects the valley to the outside world.",
    "You haven't been there."
   ]
  }
 ],
 "factions": [
  {
   "id": "imperial-court",
   "name": "The Imperial Court",
   "lines": [
    "Court",
    "The ruling authority of the kingdom, currently facing internal rebellion."
   ],
   "esteem": "neutral",
   "dread": "none",
   "standing_label": "Neutral"
  }
 ],
 "threads": [
  {
   "id": "peaceful-retirement",
   "title": "A Quiet Retirement Threatened",
   "status": "open"
  }
 ]
}
```


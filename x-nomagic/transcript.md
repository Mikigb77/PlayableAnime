## The draft (en, teen)

> Everyone in this world is born with magic. I'm the only one ever born without any. But magic doesn't work on me either.

_39.4 s, $0.088: 2535 tokens of thinking, 5429 of answer, 1 tries_

### What the draft's screen shows

The Null Spark
defiant fantasy
resolute and mysterious
Every child is born with a glowing magical Spark that dictates their potential and social standing.
A high-medieval world powered entirely by elemental magical technology.
Spark Tiers: Flicker, Flame, Blaze, Inferno and beyond.
Peoples: Human.
The Arcane Conclave: The ruling council of high-tier mages who govern Solaria with an iron fist, obsessed with magical purity.
The Unbound: A clandestine resistance movement composed of Flicker-tier mages fighting for equal rights.
Julian, 18.
A focused, athletic youth whose quiet, intense gaze shows the grit of someone who has had to survive through physical strength alone.
Expert: Athletics. Skilled: Close Combat and Stealth. Novice: Magic Lore.
Gifts: Immovable Mind. Flaws: Sparkless Void.
Determined, observant and guarded.
Void Immunity: Active magic spells cast directly at your body lose cohesion and harmlessly disperse into nothingness upon contact (Does not protect you from physical side-effects of magic, such as a magically-thrown boulder, collapsing structures, or natural fire ignited by a spell.).
Carries Sturdy Iron Dagger and Worn Leather Bracers. 15 silver shards.
Every child is born with a glowing magical Spark that dictates their potential and social standing.
The complete absence of a Spark makes a person completely invisible to and unaffected by direct magical spells.
Magical spells require a conduit of personal energy to find purchase; they cannot cling to pure void.

### On record (the player never sees this)

```json
{
 "world": {
  "title": "The Null Spark",
  "genre": "defiant fantasy",
  "era": "A high-medieval world powered entirely by elemental magical technology."
 },
 "character": {
  "id": "player",
  "name": "Julian",
  "aliases": [
   "The Null",
   "The Sparkless"
  ],
  "prominence": "key",
  "description": "A focused, athletic youth whose quiet, intense gaze shows the grit of someone who has had to survive through physical strength alone.",
  "appearance": "Strong, lean build honed by years of physical training; short, unruly dark hair; sharp gray eyes. Wearing a simple, patched gray tunic, leather trousers, and sturdy leather boots.",
  "age": 18,
  "location_id": "player-home",
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
   "strength": 4,
   "speed": 4,
   "toughness": 4,
   "wits": 4,
   "willpower": 5,
   "nerve": 5
  },
  "skills": [
   {
    "name": "Close Combat",
    "level": "skilled",
    "notes": "Trained by Elder Karl in direct physical swordplay and hand-to-hand fighting."
   },
   {
    "name": "Athletics",
    "level": "expert",
    "notes": "Excellent running, climbing, and physical endurance built up to compensate for lack of magic."
   },
   {
    "name": "Stealth",
    "level": "skilled",
    "notes": "Slinking through the shadows of the capital to avoid Sentinel patrols."
   },
   {
    "name": "Magic Lore",
    "level": "novice",
    "notes": "Basic knowledge of spells, gestures, and elemental signs studied to anticipate mage attacks."
   }
  ],
  "traits": [
   {
    "name": "Sparkless Void",
    "kind": "flaw",
    "description": "You possess zero magical mana. You cannot cast spells, activate magical machinery, or use magical items."
   },
   {
    "name": "Immovable Mind",
    "kind": "gift",
    "description": "Years of being an outcast have forged an unbreakable willpower; you are highly resistant to intimidation and mental stress."
   }
  ],
  "powers": [
   {
    "id": "void-shell",
    "name": "Void Immunity",
    "description": "Active magic spells cast directly at your body lose cohesion and harmlessly disperse into nothingness upon contact.",
    "strength": "overpowered",
    "limits": [
     "Does not protect you from physical side-effects of magic, such as a magically-thrown boulder, collapsing structures, or natural fire ignited by a spell."
    ]
   }
  ],
  "disposition": {
   "temperament": {
    "traits": [
     "determined",
     "observant",
     "guarded"
    ],
    "values": [
     "survival",
     "self-reliance"
    ],
    "loves": [
     "the quiet of the woods",
     "mastering a physical technique"
    ],
    "fears": [
     "being helpless",
     "losing the few people who accept them"
    ],
    "wants": [
     "To survive the Conclave's purge and uncover the truth of their body's immunity."
    ],
    "voice": "Direct, calm, and sparing with words."
   }
  },
  "resources": {
   "items": [
    {
     "id": "sturdy-iron-dagger",
     "name": "Sturdy Iron Dagger",
     "kind": "weapon",
     "description": "A well-balanced, non-magical dagger crafted from simple cold iron."
    },
    {
     "id": "worn-leather-bracers",
     "name": "Worn Leather Bracers",
     "kind": "armour",
     "description": "Scuffed leather guards that provide basic physical protection for your forearms."
    }
   ],
   "money": 15,
   "currency": "silver shards",
   "connections": [
    {
     "name": "Elder Karl",
     "kind": "family",
     "character_id": "elder-karl",
     "note": "Your gruff mentor who taught you how to fight without relying on a Spark."
    }
   ]
  }
 },
 "gift": "overpowered",
 "extraordinary": [
  "Spark Magic (common): Every human is born with an internal Spark that allows them to manifest magical energy, power machinery, and cast elemental spells."
 ],
 "ladders": [
  {
   "id": "spark-tiers",
   "name": "Spark Tiers",
   "rungs": [
    "0: Flicker (tier 2, lives 0)",
    "1: Flame (tier 4, lives 0)",
    "2: Blaze (tier 6, lives 0)",
    "3: Inferno (tier 8, lives 0)",
    "4: Sun (tier 10, lives 0)"
   ]
  }
 ],
 "peoples": [
  {
   "id": "human",
   "name": "Human",
   "lifespan_years": 80,
   "gifts": [
    "Spark magic channeling"
   ],
   "culture": "A highly stratified society where one's worth is measured entirely by the brilliance and tier of their magical Spark."
  }
 ],
 "rules": [
  "Every child is born with a glowing magical Spark that dictates their potential and social standing.",
  "The complete absence of a Spark makes a person completely invisible to and unaffected by direct magical spells.",
  "Magical spells require a conduit of personal energy to find purchase; they cannot cling to pure void."
 ],
 "others": [
  "Grand Mage Valerius, 72, spark-tiers rung 3, peak attribute 5",
  "Aria Valerius, 19, spark-tiers rung 2, peak attribute 5",
  "Elder Karl, 62, spark-tiers rung 0, peak attribute 5"
 ],
 "people_in_the_world": 3,
 "years": {
  "age": 18.0,
  "lives_about": 80,
  "the_record_says_so": true,
  "old": false,
  "told_the_end_is_close": false
 }
}
```

## Turn 1 (opening), 5.4 s, $0.041

_From Day 1, morning, 08:00 to Day 1, morning, 08:00 (0 s). Julian is 18, alive._

The low, brassy blare of the Conclave Sentinels' horn vibrates through the damp stone of your cellar floor. You sit on a rough wooden crate, your fingers tracing the hilt of your iron dagger, while Elder Karl leans heavily against the weapon rack across from you. His single eye fixes on you from beneath shaggy brows, dark with a gravity that makes the chilly morning air feel even colder.

"Three days, Julian," Karl rasps, his deep voice scraping against the walls. "Three days before the white-stone crystals at the Spellspire catalog every single Spark in this city. When your name is called, you won't have a flicker to show them. They will brand you. Unless you are already gone—or unless you can fool their testing stones."

He reaches down, picks up a blunt wooden training sword, and tosses it at your feet. The wood clatters against the dirt floor, stopping right beside your boots. He is offering you one last chance to hone your reflexes, but the weight of your choices already looms larger than any blade.

**Suggestions:**
1. "I need to test my Void Shell against real magic first." (thread)
2. Pick up the wooden sword and challenge Karl to a bout. (personal)
3. Slink out into the Ash Wastes to scout Sentinel patrol routes. (side)

**Issues:**
- start_told (person:elder-karl): the story told it
- start_told (thread:mystery-of-the-void): the story told it

## What the screens show (turn 1)

### The Character screen

```json
{
 "character": {
  "name": "Julian",
  "lines": [
   "Unhurt",
   "Void Immunity: ready",
   "15 silver shards",
   "Sturdy Iron Dagger",
   "Worn Leather Bracers"
  ]
 },
 "sheet": {
  "about": [
   "18 years old"
  ],
  "description": "A focused, athletic youth whose quiet, intense gaze shows the grit of someone who has had to survive through physical strength alone.",
  "condition": {
   "health": "unhurt",
   "health_label": "Unhurt"
  },
  "paths": [
   {
    "name": "Spark Tiers",
    "above": [
     {
      "name": "Flicker",
      "known": true,
      "note": "Confirmed before Elder Karl, day 1",
      "gap_below": false
     },
     {
      "name": "Flame",
      "known": false,
      "note": "Everyone has heard of it",
      "gap_below": false
     },
     {
      "name": "Blaze",
      "known": true,
      "note": "Confirmed before Aria Valerius, day 1",
      "gap_below": false
     },
     {
      "name": "Inferno",
      "known": true,
      "note": "Confirmed before Grand Mage Valerius, day 1",
      "gap_below": false
     }
    ]
   }
  ],
  "money_label": "15 silver shards",
  "items": [
   {
    "name": "Sturdy Iron Dagger",
    "kind": "weapon",
    "kind_label": "Weapon",
    "description": "A well-balanced, non-magical dagger crafted from simple cold iron.",
    "quantity": 1,
    "carried": true
   },
   {
    "name": "Worn Leather Bracers",
    "kind": "armour",
    "kind_label": "Armour",
    "description": "Scuffed leather guards that provide basic physical protection for your forearms.",
    "quantity": 1,
    "carried": true
   }
  ],
  "skills": [
   {
    "name": "Athletics",
    "level": "expert",
    "level_label": "Expert",
    "dice": 4,
    "notes": "Excellent running, climbing, and physical endurance built up to compensate for lack of magic."
   },
   {
    "name": "Close Combat",
    "level": "skilled",
    "level_label": "Skilled",
    "dice": 3,
    "notes": "Trained by Elder Karl in direct physical swordplay and hand-to-hand fighting."
   },
   {
    "name": "Stealth",
    "level": "skilled",
    "level_label": "Skilled",
    "dice": 3,
    "notes": "Slinking through the shadows of the capital to avoid Sentinel patrols."
   },
   {
    "name": "Magic Lore",
    "level": "novice",
    "level_label": "Novice",
    "dice": 1,
    "notes": "Basic knowledge of spells, gestures, and elemental signs studied to anticipate mage attacks."
   }
  ],
  "powers": [
   {
    "name": "Void Immunity",
    "description": "Active magic spells cast directly at your body lose cohesion and harmlessly disperse into nothingness upon contact.",
    "limits": [
     "Does not protect you from physical side-effects of magic, such as a magically-thrown boulder, collapsing structures, or natural fire ignited by a spell."
    ],
    "ready": true,
    "ready_label": "Ready",
    "secret": false
   }
  ],
  "traits": [
   {
    "name": "Sparkless Void",
    "kind": "flaw",
    "kind_label": "Flaw",
    "description": "You possess zero magical mana. You cannot cast spells, activate magical machinery, or use magical items."
   },
   {
    "name": "Immovable Mind",
    "kind": "gift",
    "kind_label": "Gift",
    "description": "Years of being an outcast have forged an unbreakable willpower; you are highly resistant to intimidation and mental stress."
   }
  ],
  "temperament": [
   "determined",
   "observant",
   "guarded"
  ]
 },
 "reputation": [
  {
   "name": "The Arcane Conclave",
   "label": "Neutral"
  },
  {
   "name": "The Unbound",
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
   "text": "Direct offensive spells cast at you simply vanish with a quiet hiss, leaving you totally unharmed.",
   "ago_label": "moments ago"
  },
  {
   "text": "The Conclave uses massive white-stone crystals to track the magical signatures of everyone in the city.",
   "ago_label": "moments ago"
  },
  {
   "text": "In Solaria, your Spark is your life; those without one are treated as sub-human outcasts.",
   "ago_label": "moments ago"
  }
 ]
}
```

### Memory

```json
{
 "character": {
  "name": "Julian",
  "lines": [
   "A focused, athletic youth whose quiet, intense gaze shows the grit of someone who has had to survive through physical strength alone."
  ]
 },
 "people": [
  {
   "id": "elder-karl",
   "name": "Elder Karl",
   "lines": [
    "A rugged, one-eyed veteran who lives in the slums, having long ago abandoned his weak magical Spark for the way of the blade."
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
   "id": "outcast-slums",
   "name": "The Ash Wastes",
   "lines": [
    "Village",
    "A dark, soot-covered slum at the edge of the capital where the lowest-tier mages reside.",
    "You haven't been there."
   ]
  },
  {
   "id": "solaria-kingdom",
   "name": "Kingdom of Solaria",
   "lines": [
    "Region",
    "A vast, sun-drenched realm powered entirely by the elemental energy of its citizens' Sparks.",
    "You haven't been there."
   ]
  },
  {
   "id": "capital-city",
   "name": "Oakhaven Capital",
   "lines": [
    "City",
    "The shimmering white-stone capital where magical lanterns glow day and night.",
    "You haven't been there."
   ]
  },
  {
   "id": "player-home",
   "name": "The Shabby Cellar",
   "lines": [
    "Room",
    "A damp, underground room filled with training dummies and hand-copied texts on physical martial arts."
   ]
  },
  {
   "id": "spellspire-academy",
   "name": "The Spellspire Academy",
   "lines": [
    "Building",
    "The grand glass-and-marble tower where the elite of Solaria train their Sparks.",
    "You haven't been there."
   ]
  },
  {
   "id": "whispering-woods",
   "name": "The Whispering Woods",
   "lines": [
    "Wilds",
    "A dense, primal forest teeming with wild magical energy and hostile beasts.",
    "You haven't been there."
   ]
  }
 ],
 "factions": [
  {
   "id": "arcane-conclave",
   "name": "The Arcane Conclave",
   "lines": [
    "Court",
    "The ruling council of high-tier mages who govern Solaria with an iron fist, obsessed with magical purity."
   ],
   "esteem": "neutral",
   "dread": "none",
   "standing_label": "Neutral"
  },
  {
   "id": "the-unbound",
   "name": "The Unbound",
   "lines": [
    "Sect",
    "A clandestine resistance movement composed of Flicker-tier mages fighting for equal rights."
   ],
   "esteem": "neutral",
   "dread": "none",
   "standing_label": "Neutral"
  }
 ],
 "threads": [
  {
   "id": "mystery-of-the-void",
   "title": "The Secrets of the Void Shell",
   "status": "open"
  }
 ]
}
```


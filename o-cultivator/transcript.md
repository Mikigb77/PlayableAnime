## The draft (en, teen)

> An old cultivator, 148 years old, stuck at the peak of Foundation Establishment. My lifespan of 150 years is almost spent: I break through to Core Formation or I die.

_44.3 s, $0.101_

### What the draft's screen shows

The Flickering Jade: A Cultivator's Last Stand
Cultivation / Xianxia
Desperate, resolute, and filled with the cold beauty of a dying flame
Qi cultivation: real, and everywhere.
Ancient Xianxia Era: spirit talismans, flying swords, and Qi-powered formations.
Cultivation realms: Qi Condensation, Foundation Establishment, Core Formation, Nascent Soul.
Peoples: Human.
Misty Cloud Sect: A struggling cultivation sect trying to preserve its small territory from aggressive neighbours.
Han Feng, 148, Human.
An ancient cultivator with a heavily lined face, a long grey beard, and eyes reflecting decades of patience and growing desperation.
Outer Elder, Misty Cloud Sect.
Foundation Establishment, at its peak.
Expert: Qi Refinement. Skilled: Sword Cultivation. Fair: Herbology.
Gifts: Tempered Will. Flaws: Brittle Meridians.
Cautious, resolute and weathered.
Foundation Qi Manipulation: You can manifest your liquid spiritual energy to form defensive shields, project blade beams, or glide short distances (Limited by your pool of spiritual energy.; Overexertion causes physical fatigue and strain on your meridians.). Cost: Strains your physical body if used continuously for more than a few minutes.
Carries Worn Flying Sword and Low-grade Qi-Gathering Pill. 120 spirit stones.
A cultivator's lifespan is bound to their realm; failing to break through before it expires leads to absolute mortality.
Condensing a Golden Core requires compressing one's spiritual liquid into a solid core, a process highly lethal without protective pills.
An aging body's meridians become brittle, exponentially increasing the pain and danger of Qi circulation during breakthrough attempts.
Cultivators of the Foundation Establishment realm and above can traverse vast distances on flying swords, bypassing earthly terrain.
Qi cultivation: real, and everywhere.

### On record (the player never sees this)

```json
{
 "world": {
  "title": "The Flickering Jade: A Cultivator's Last Stand",
  "genre": "Cultivation / Xianxia",
  "era": "Ancient Xianxia Era: spirit talismans, flying swords, and Qi-powered formations"
 },
 "character": {
  "id": "player",
  "name": "Han Feng",
  "aliases": [
   "Elder Han"
  ],
  "prominence": "key",
  "description": "An ancient cultivator with a heavily lined face, a long grey beard, and eyes reflecting decades of patience and growing desperation.",
  "appearance": "Thin, frail-looking frame concealed by loose, faded grey robes. Long, snow-white hair tied in a simple wooden topknot.",
  "age": 148,
  "people_id": "human",
  "location_id": "spirit-peak",
  "memberships": [
   {
    "faction_id": "misty-cloud",
    "rank": "Outer Elder",
    "loyalty": 40
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
  "lifespan_years": 150
 },
 "sheet": {
  "attributes": {
   "strength": 2,
   "wits": 4,
   "knowledge": 4,
   "willpower": 5,
   "nerve": 4,
   "bearing": 4
  },
  "skills": [
   {
    "name": "Qi Refinement",
    "level": "expert",
    "notes": "Decades of stagnation have made your control over your existing Qi exceptionally precise."
   },
   {
    "name": "Sword Cultivation",
    "level": "skilled",
    "notes": "Your swordsmanship is refined, though hindered by a physical body that tires quickly."
   },
   {
    "name": "Herbology",
    "notes": "Familiarity with common spiritual herbs from years of searching for a cure."
   }
  ],
  "traits": [
   {
    "name": "Brittle Meridians",
    "kind": "flaw",
    "description": "Your spiritual pathways are stiff and aged, making heavy Qi circulation painful and dangerous."
   },
   {
    "name": "Tempered Will",
    "kind": "gift",
    "description": "A century and a half of struggle has made your mind immune to ordinary illusions and spiritual intimidation."
   }
  ],
  "powers": [
   {
    "id": "foundation-qi",
    "name": "Foundation Qi Manipulation",
    "description": "You can manifest your liquid spiritual energy to form defensive shields, project blade beams, or glide short distances.",
    "limits": [
     "Limited by your pool of spiritual energy.",
     "Overexertion causes physical fatigue and strain on your meridians."
    ],
    "costs": [
     {
      "kind": "fatigue",
      "text": "Strains your physical body if used continuously for more than a few minutes."
     }
    ]
   }
  ],
  "techniques": [
   {
    "id": "misty-cloud-sword-stance",
    "name": "Misty Cloud Sword Stance",
    "style": "Misty Cloud Sword Art",
    "effect": "Creates deceptive phantoms of your blade to confuse the opponent's spiritual sense.",
    "cost": "Moderate Qi expenditure",
    "requirements": "A spiritual sword"
   }
  ],
  "disposition": {
   "temperament": {
    "traits": [
     "cautious",
     "resolute",
     "weathered"
    ],
    "values": [
     "Survival",
     "Dignity"
    ],
    "loves": [
     "The quiet of the mountains",
     "A well-brewed spiritual tea"
    ],
    "fears": [
     "Dying in obscurity",
     "Failing his disciple"
    ],
    "wants": [
     "Break through to Core Formation or I die."
    ],
    "voice": "Raspy, calm, and deliberate."
   }
  },
  "resources": {
   "items": [
    {
     "id": "worn-flying-sword",
     "name": "Worn Flying Sword",
     "kind": "weapon",
     "description": "A steel sword with a slightly dulled edge, but well-maintained and loyal to your spiritual signature."
    },
    {
     "id": "low-grade-qi-gathering-pill",
     "name": "Low-grade Qi-Gathering Pill",
     "kind": "consumable",
     "description": "A bitter pill that helps replenish lost spiritual energy over several hours.",
     "quantity": 3
    }
   ],
   "money": 120,
   "currency": "spirit stones",
   "title": "Elder of the Misty Cloud Sect",
   "rank": "Foundation Establishment (Peak)",
   "family_name": "Han",
   "connections": [
    {
     "name": "Chen Yi",
     "kind": "ally",
     "character_id": "disciple-chen",
     "note": "Your fiercely loyal sole disciple."
    }
   ]
  },
  "condition": {
   "reserves": [
    {
     "name": "Spiritual Qi"
    }
   ]
  },
  "axes": {
   "might": 4,
   "influence": 2,
   "wealth": 2,
   "knowledge": 3,
   "stealth": 2
  },
  "ladders": [
   {
    "ladder_id": "cultivation-realms",
    "rung": 1,
    "stage": "peak"
   }
  ],
  "backstory": [
   {
    "text": "You joined the Misty Cloud Sect as a young man with average talent."
   },
   {
    "text": "You reached the peak of Foundation Establishment eighty years ago, but the barrier to Core Formation remained completely impenetrable."
   },
   {
    "text": "As your lifespan dwindles to its absolute limit, you have retreated to Spirit-Severing Peak to make one final, desperate struggle for immortality."
   }
  ]
 },
 "gift": "none",
 "extraordinary": [
  "qi cultivation (common): Cultivators refine Qi to transcend mortality, manipulate elements, and fly through the heavens."
 ],
 "ladders": [
  {
   "id": "cultivation-realms",
   "name": "cultivation realms",
   "rungs": [
    "0: Qi Condensation (tier 2, lives 100)",
    "1: Foundation Establishment (tier 4, lives 150)",
    "2: Core Formation (tier 6, lives 500)",
    "3: Nascent Soul (tier 8, lives 2000)"
   ]
  }
 ],
 "peoples": [
  {
   "id": "human",
   "name": "Human",
   "description": "The dominant inhabitants of the mortal plains, many of whom seek the Dao to escape the cycle of reincarnation.",
   "lifespan_years": 80,
   "culture": "A society deeply structured by sect hierarchies and ancestral respect."
  }
 ],
 "rules": [
  "A cultivator's lifespan is bound to their realm; failing to break through before it expires leads to absolute mortality.",
  "Condensing a Golden Core requires compressing one's spiritual liquid into a solid core, a process highly lethal without protective pills.",
  "An aging body's meridians become brittle, exponentially increasing the pain and danger of Qi circulation during breakthrough attempts.",
  "Cultivators of the Foundation Establishment realm and above can traverse vast distances on flying swords, bypassing earthly terrain.",
  "Qi cultivation: real, and everywhere."
 ],
 "others": [
  "Sect Master Liu, 220, cultivation-realms rung 2, peak attribute 4",
  "Elder Song, 130, cultivation-realms rung 1, peak attribute 4",
  "Chen Yi, 24, cultivation-realms rung 0, peak attribute 4"
 ],
 "people_in_the_world": 3,
 "years": {
  "age": 148.0,
  "lives_about": 150,
  "the_record_says_so": true,
  "old": true,
  "told_the_end_is_close": false
 }
}
```

## Turn 1 (opening), 14.9 s, $0.042

_From Day 1, dawn, 06:00 to Day 1, dawn, 06:00 (0 s). Han Feng is 148, alive._

You sit cross-legged on the cold stone platform of Spirit-Severing Peak. The dawn wind is a blade of ice, cutting through your thin, faded grey robes. Your breath comes ragged and shallow, puffing into white mist. Your body feels like brittle dry wood.

Nearby, Chen Yi stands by the cracked stone incense burner, his honest eyes shadowed with a desperate worry. He is only twenty-four, full of youth, yet bound to a master whose flame is flickering out.

Only two years remain of your natural hundred-and-fifty-year lifespan. Without a Core-Assisting Pill, attempting the breakthrough to Core Formation is a ninety percent guarantee of death—your stiff, aged meridians will simply shatter under the pressure. Yet, Sect Master Liu has made his stance clear: the sect will not waste precious resources on an outer elder who has stagnated for eighty years.

Chen Yi steps forward, his hands clenched. "Master," his earnest voice trembles slightly. "The Pill Refinement Hall... Elder Song is preparing a new batch of Core-Assisting Pills this week. There must be a way to secure one, even if the Sect Master refuses us."

**Suggestions:**
1. Ask Chen Yi what it would take to acquire a pill. (thread)
2. Steel your brittle meridians and begin a cautious Qi circulation session. (personal)
3. Seek an audience with Sect Master Liu to demand your dues. (side)

**Issues:**
- start_told (goal:goal-1): the story told it
- start_told (person:alchemist-song): the story told it
- start_told (person:disciple-chen): the story told it
- start_told (person:sect-master): the story told it

**Counted:** {"goals_open": 1}

## What the screens show (turn 1)

### The Character screen

```json
{
 "character": {
  "name": "Han Feng",
  "lines": [
   "Cultivation realms: Foundation Establishment, at its peak",
   "Unhurt",
   "Spiritual Qi: 100%",
   "Foundation Qi Manipulation: ready",
   "Foundation Qi Manipulation, cost: Strains your physical body if used continuously for more than a few minutes",
   "Misty Cloud Sword Stance (technique, practiced, 0 of 15 uses)",
   "120 spirit stones",
   "Low-grade Qi-Gathering Pill (3)",
   "Worn Flying Sword"
  ]
 },
 "sheet": {
  "about": [
   "Outer Elder, Misty Cloud Sect",
   "Elder of the Misty Cloud Sect",
   "148 years old"
  ],
  "description": "An ancient cultivator with a heavily lined face, a long grey beard, and eyes reflecting decades of patience and growing desperation.",
  "condition": {
   "health": "unhurt",
   "health_label": "Unhurt",
   "reserves": [
    {
     "name": "Spiritual Qi",
     "level": 100
    }
   ]
  },
  "paths": [
   {
    "name": "Cultivation realms",
    "rungs": [
     {
      "name": "Qi Condensation"
     },
     {
      "name": "Foundation Establishment",
      "stage": "At its peak: you can try to break through",
      "filled": 1.0,
      "description": "Liquefying Qi into a spiritual sea to build the foundation of immortality."
     }
    ],
    "above": [
     {
      "name": "Core Formation",
      "known": true,
      "note": "Confirmed before Sect Master Liu, day 1",
      "said": [
       "The standard breakthrough to Core Formation has a ninety percent failure rate without a Core-Assisting Pill."
      ],
      "gap_below": false
     },
     {
      "name": "Nascent Soul",
      "known": false,
      "note": "Everyone has heard of it",
      "gap_below": false
     }
    ]
   }
  ],
  "money_label": "120 spirit stones",
  "items": [
   {
    "name": "Low-grade Qi-Gathering Pill",
    "kind": "consumable",
    "kind_label": "Consumable",
    "description": "A bitter pill that helps replenish lost spiritual energy over several hours.",
    "quantity": 3,
    "carried": true
   },
   {
    "name": "Worn Flying Sword",
    "kind": "weapon",
    "kind_label": "Weapon",
    "description": "A steel sword with a slightly dulled edge, but well-maintained and loyal to your spiritual signature.",
    "quantity": 1,
    "carried": true
   }
  ],
  "skills": [
   {
    "name": "Qi Refinement",
    "level": "expert",
    "level_label": "Expert",
    "dice": 4,
    "notes": "Decades of stagnation have made your control over your existing Qi exceptionally precise."
   },
   {
    "name": "Sword Cultivation",
    "level": "skilled",
    "level_label": "Skilled",
    "dice": 3,
    "notes": "Your swordsmanship is refined, though hindered by a physical body that tires quickly."
   },
   {
    "name": "Herbology",
    "level": "fair",
    "level_label": "Fair",
    "dice": 2,
    "notes": "Familiarity with common spiritual herbs from years of searching for a cure."
   }
  ],
  "powers": [
   {
    "name": "Foundation Qi Manipulation",
    "description": "You can manifest your liquid spiritual energy to form defensive shields, project blade beams, or glide short distances.",
    "limits": [
     "Limited by your pool of spiritual energy.",
     "Overexertion causes physical fatigue and strain on your meridians."
    ],
    "cost": "Strains your physical body if used continuously for more than a few minutes",
    "ready": true,
    "ready_label": "Ready",
    "secret": false
   }
  ],
  "techniques": [
   {
    "name": "Misty Cloud Sword Stance",
    "style": "Misty Cloud Sword Art",
    "effect": "Creates deceptive phantoms of your blade to confuse the opponent's spiritual sense.",
    "cost": "Moderate Qi expenditure",
    "mastery": "practiced",
    "mastery_label": "Practiced",
    "dice": 2,
    "uses": 0,
    "need": 15
   }
  ],
  "traits": [
   {
    "name": "Brittle Meridians",
    "kind": "flaw",
    "kind_label": "Flaw",
    "description": "Your spiritual pathways are stiff and aged, making heavy Qi circulation painful and dangerous."
   },
   {
    "name": "Tempered Will",
    "kind": "gift",
    "kind_label": "Gift",
    "description": "A century and a half of struggle has made your mind immune to ordinary illusions and spiritual intimidation."
   }
  ],
  "temperament": [
   "cautious",
   "resolute",
   "weathered"
  ]
 },
 "reputation": [
  {
   "name": "Misty Cloud Sect",
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
   "text": "Sect Master Liu considers you a liability and will not grant you any sect-owned breakthrough resources.",
   "ago_label": "moments ago"
  },
  {
   "text": "The standard breakthrough to Core Formation has a ninety percent failure rate without a Core-Assisting Pill.",
   "ago_label": "moments ago"
  },
  {
   "text": "You have exactly two years left of your natural 150-year lifespan.",
   "ago_label": "moments ago"
  }
 ]
}
```

### On record (the player never sees this)

```json
{
 "world": {
  "title": "The Flickering Jade: A Cultivator's Last Stand",
  "genre": "Cultivation / Xianxia",
  "era": "Ancient Xianxia Era: spirit talismans, flying swords, and Qi-powered formations"
 },
 "character": {
  "id": "player",
  "name": "Han Feng",
  "aliases": [
   "Elder Han"
  ],
  "prominence": "key",
  "description": "An ancient cultivator with a heavily lined face, a long grey beard, and eyes reflecting decades of patience and growing desperation.",
  "appearance": "Thin, frail-looking frame concealed by loose, faded grey robes. Long, snow-white hair tied in a simple wooden topknot.",
  "age": 148,
  "people_id": "human",
  "location_id": "spirit-peak",
  "memberships": [
   {
    "faction_id": "misty-cloud",
    "rank": "Outer Elder",
    "loyalty": 40
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
  "lifespan_years": 150
 },
 "sheet": {
  "attributes": {
   "strength": 2,
   "wits": 4,
   "knowledge": 4,
   "willpower": 5,
   "nerve": 4,
   "bearing": 4
  },
  "skills": [
   {
    "name": "Qi Refinement",
    "level": "expert",
    "notes": "Decades of stagnation have made your control over your existing Qi exceptionally precise."
   },
   {
    "name": "Sword Cultivation",
    "level": "skilled",
    "notes": "Your swordsmanship is refined, though hindered by a physical body that tires quickly."
   },
   {
    "name": "Herbology",
    "notes": "Familiarity with common spiritual herbs from years of searching for a cure."
   }
  ],
  "traits": [
   {
    "name": "Brittle Meridians",
    "kind": "flaw",
    "description": "Your spiritual pathways are stiff and aged, making heavy Qi circulation painful and dangerous."
   },
   {
    "name": "Tempered Will",
    "kind": "gift",
    "description": "A century and a half of struggle has made your mind immune to ordinary illusions and spiritual intimidation."
   }
  ],
  "powers": [
   {
    "id": "foundation-qi",
    "name": "Foundation Qi Manipulation",
    "description": "You can manifest your liquid spiritual energy to form defensive shields, project blade beams, or glide short distances.",
    "limits": [
     "Limited by your pool of spiritual energy.",
     "Overexertion causes physical fatigue and strain on your meridians."
    ],
    "costs": [
     {
      "kind": "fatigue",
      "text": "Strains your physical body if used continuously for more than a few minutes."
     }
    ]
   }
  ],
  "techniques": [
   {
    "id": "misty-cloud-sword-stance",
    "name": "Misty Cloud Sword Stance",
    "style": "Misty Cloud Sword Art",
    "effect": "Creates deceptive phantoms of your blade to confuse the opponent's spiritual sense.",
    "cost": "Moderate Qi expenditure",
    "requirements": "A spiritual sword"
   }
  ],
  "disposition": {
   "temperament": {
    "traits": [
     "cautious",
     "resolute",
     "weathered"
    ],
    "values": [
     "Survival",
     "Dignity"
    ],
    "loves": [
     "The quiet of the mountains",
     "A well-brewed spiritual tea"
    ],
    "fears": [
     "Dying in obscurity",
     "Failing his disciple"
    ],
    "wants": [
     "Break through to Core Formation or I die."
    ],
    "voice": "Raspy, calm, and deliberate."
   }
  },
  "resources": {
   "items": [
    {
     "id": "worn-flying-sword",
     "name": "Worn Flying Sword",
     "kind": "weapon",
     "description": "A steel sword with a slightly dulled edge, but well-maintained and loyal to your spiritual signature."
    },
    {
     "id": "low-grade-qi-gathering-pill",
     "name": "Low-grade Qi-Gathering Pill",
     "kind": "consumable",
     "description": "A bitter pill that helps replenish lost spiritual energy over several hours.",
     "quantity": 3
    }
   ],
   "money": 120,
   "currency": "spirit stones",
   "title": "Elder of the Misty Cloud Sect",
   "rank": "Foundation Establishment (Peak)",
   "family_name": "Han",
   "connections": [
    {
     "name": "Chen Yi",
     "kind": "ally",
     "character_id": "disciple-chen",
     "note": "Your fiercely loyal sole disciple."
    }
   ]
  },
  "condition": {
   "reserves": [
    {
     "name": "Spiritual Qi"
    }
   ]
  },
  "axes": {
   "might": 4,
   "influence": 2,
   "wealth": 2,
   "knowledge": 3,
   "stealth": 2
  },
  "ladders": [
   {
    "ladder_id": "cultivation-realms",
    "rung": 1,
    "stage": "peak"
   }
  ],
  "rungs_heard": [
   {
    "ladder_id": "cultivation-realms",
    "rung": 2,
    "heard_s": 0,
    "known_s": 0,
    "known_from": "sect-master"
   }
  ],
  "backstory": [
   {
    "text": "You joined the Misty Cloud Sect as a young man with average talent."
   },
   {
    "text": "You reached the peak of Foundation Establishment eighty years ago, but the barrier to Core Formation remained completely impenetrable."
   },
   {
    "text": "As your lifespan dwindles to its absolute limit, you have retreated to Spirit-Severing Peak to make one final, desperate struggle for immortality."
   }
  ]
 },
 "gift": "none",
 "extraordinary": [
  "qi cultivation (common): Cultivators refine Qi to transcend mortality, manipulate elements, and fly through the heavens."
 ],
 "ladders": [
  {
   "id": "cultivation-realms",
   "name": "cultivation realms",
   "rungs": [
    "0: Qi Condensation (tier 2, lives 100)",
    "1: Foundation Establishment (tier 4, lives 150)",
    "2: Core Formation (tier 6, lives 500)",
    "3: Nascent Soul (tier 8, lives 2000)"
   ]
  }
 ],
 "peoples": [
  {
   "id": "human",
   "name": "Human",
   "description": "The dominant inhabitants of the mortal plains, many of whom seek the Dao to escape the cycle of reincarnation.",
   "lifespan_years": 80,
   "culture": "A society deeply structured by sect hierarchies and ancestral respect."
  }
 ],
 "rules": [
  "A cultivator's lifespan is bound to their realm; failing to break through before it expires leads to absolute mortality.",
  "Condensing a Golden Core requires compressing one's spiritual liquid into a solid core, a process highly lethal without protective pills.",
  "An aging body's meridians become brittle, exponentially increasing the pain and danger of Qi circulation during breakthrough attempts.",
  "Cultivators of the Foundation Establishment realm and above can traverse vast distances on flying swords, bypassing earthly terrain.",
  "Qi cultivation: real, and everywhere."
 ],
 "others": [
  "Sect Master Liu, 220, cultivation-realms rung 2, peak attribute 4",
  "Elder Song, 130, cultivation-realms rung 1, peak attribute 4",
  "Chen Yi, 24, cultivation-realms rung 0, peak attribute 4"
 ],
 "people_in_the_world": 3,
 "years": {
  "age": 148.0,
  "lives_about": 150,
  "the_record_says_so": true,
  "old": true,
  "told_the_end_is_close": false
 },
 "waiting": [
  "world.tick 'The world moves on' in 1.0 days",
  "world.clock_step 'Lifespan Depletion: The first signs of grey rot touch your spiritual veins, slowing your Qi flow.' in 243.3 days",
  "world.old_age 'Your years run short' in 13.9 years (stops the player)"
 ]
}
```

## Turn 2 (action), 30.9 s, $0.063

> I sit down, circulate my qi and attempt the breakthrough to Core Formation right now, without the pill.

_From Day 1, dawn, 06:00 to Day 1, morning, 07:00 (1.0 hours). Han Feng is 148, alive._

**Read and decided:**
- read as work, 'cultivate' on player, 3600 s: Circulate my Qi and attempt the lethal breakthrough to Core Formation without the protective pill.
- Circulate my Qi and attempt the lethal breakthrough to Core Formation without the protective pill. [ruled_out, failure]: Condensing a Golden Core requires compressing one's spiritual liquid into a solid core, a process highly lethal without protective pills.

You close your eyes, ignoring Chen Yi's desperate plea, and begin to circulate your liquid spiritual energy. You draw the chill of Spirit-Severing Peak into your lungs, forcing your Foundation Qi through pathways that feel like dry, splintering reeds. You attempt to compress the swirling liquid in your dantian, trying to crystallize it into a solid Golden Core by sheer willpower alone.

The moment you press the energy inward, a blinding spasm of agony tears through your chest. Your brittle meridians groaning under the sheer, unyielding pressure, warning you that one more ounce of force will shatter them instantly, turning your body into an empty husk of ash. The ancient laws of cultivation cannot be bypassed by resolve alone; without a Core-Assisting Pill, the bottleneck is an iron wall that will claim your life before you can even touch the threshold. Coughing up a dark, bitter drop of blood onto the frost-rimed stone, you are forced to disperse the gathered Qi before it tears you apart. Chen Yi drops to his knees beside you, his hands trembling as he reaches out to support your shaking frame. "Master! Please, do not throw your life away," he begs, his voice cracking with raw emotion. "The Pill Refinement Hall is our only hope. Or... or we search the Black Abyss Forest ourselves."

**Suggestions:**
1. Ask Chen Yi how we can infiltrate the Pill Refinement Hall. (thread)
2. Resolve to travel to the Black Abyss Forest for rare herbs. (personal)
3. Descend to Misty River Market to trade my remaining stones. (side)

**Issues:**
- read_again

**Counted:** {"refused": 1, "goals_open": 1}

## What the screens show (turn 2)

### The Character screen

```json
{
 "character": {
  "name": "Han Feng",
  "lines": [
   "Cultivation realms: Foundation Establishment, at its peak",
   "Unhurt",
   "Spiritual Qi: 100%",
   "Foundation Qi Manipulation: ready",
   "Foundation Qi Manipulation, cost: Strains your physical body if used continuously for more than a few minutes",
   "Misty Cloud Sword Stance (technique, practiced, 0 of 15 uses)",
   "120 spirit stones",
   "Low-grade Qi-Gathering Pill (3)",
   "Worn Flying Sword"
  ]
 },
 "sheet": {
  "about": [
   "Outer Elder, Misty Cloud Sect",
   "Elder of the Misty Cloud Sect",
   "148 years old"
  ],
  "description": "An ancient cultivator with a heavily lined face, a long grey beard, and eyes reflecting decades of patience and growing desperation.",
  "condition": {
   "health": "unhurt",
   "health_label": "Unhurt",
   "reserves": [
    {
     "name": "Spiritual Qi",
     "level": 100
    }
   ]
  },
  "paths": [
   {
    "name": "Cultivation realms",
    "rungs": [
     {
      "name": "Qi Condensation"
     },
     {
      "name": "Foundation Establishment",
      "stage": "At its peak: you can try to break through",
      "filled": 1.0,
      "description": "Liquefying Qi into a spiritual sea to build the foundation of immortality."
     }
    ],
    "above": [
     {
      "name": "Core Formation",
      "known": true,
      "note": "Confirmed before Sect Master Liu, day 1",
      "said": [
       "The standard breakthrough to Core Formation has a ninety percent failure rate without a Core-Assisting Pill."
      ],
      "gap_below": false
     },
     {
      "name": "Nascent Soul",
      "known": false,
      "note": "Everyone has heard of it",
      "gap_below": false
     }
    ]
   }
  ],
  "money_label": "120 spirit stones",
  "items": [
   {
    "name": "Low-grade Qi-Gathering Pill",
    "kind": "consumable",
    "kind_label": "Consumable",
    "description": "A bitter pill that helps replenish lost spiritual energy over several hours.",
    "quantity": 3,
    "carried": true
   },
   {
    "name": "Worn Flying Sword",
    "kind": "weapon",
    "kind_label": "Weapon",
    "description": "A steel sword with a slightly dulled edge, but well-maintained and loyal to your spiritual signature.",
    "quantity": 1,
    "carried": true
   }
  ],
  "skills": [
   {
    "name": "Qi Refinement",
    "level": "expert",
    "level_label": "Expert",
    "dice": 4,
    "notes": "Decades of stagnation have made your control over your existing Qi exceptionally precise."
   },
   {
    "name": "Sword Cultivation",
    "level": "skilled",
    "level_label": "Skilled",
    "dice": 3,
    "notes": "Your swordsmanship is refined, though hindered by a physical body that tires quickly."
   },
   {
    "name": "Herbology",
    "level": "fair",
    "level_label": "Fair",
    "dice": 2,
    "notes": "Familiarity with common spiritual herbs from years of searching for a cure."
   }
  ],
  "powers": [
   {
    "name": "Foundation Qi Manipulation",
    "description": "You can manifest your liquid spiritual energy to form defensive shields, project blade beams, or glide short distances.",
    "limits": [
     "Limited by your pool of spiritual energy.",
     "Overexertion causes physical fatigue and strain on your meridians."
    ],
    "cost": "Strains your physical body if used continuously for more than a few minutes",
    "ready": true,
    "ready_label": "Ready",
    "secret": false
   }
  ],
  "techniques": [
   {
    "name": "Misty Cloud Sword Stance",
    "style": "Misty Cloud Sword Art",
    "effect": "Creates deceptive phantoms of your blade to confuse the opponent's spiritual sense.",
    "cost": "Moderate Qi expenditure",
    "mastery": "practiced",
    "mastery_label": "Practiced",
    "dice": 2,
    "uses": 0,
    "need": 15
   }
  ],
  "traits": [
   {
    "name": "Brittle Meridians",
    "kind": "flaw",
    "kind_label": "Flaw",
    "description": "Your spiritual pathways are stiff and aged, making heavy Qi circulation painful and dangerous."
   },
   {
    "name": "Tempered Will",
    "kind": "gift",
    "kind_label": "Gift",
    "description": "A century and a half of struggle has made your mind immune to ordinary illusions and spiritual intimidation."
   }
  ],
  "temperament": [
   "cautious",
   "resolute",
   "weathered"
  ]
 },
 "reputation": [
  {
   "name": "Misty Cloud Sect",
   "label": "Neutral"
  }
 ],
 "clock": {
  "world_s": 3600,
  "label": "Day 1, morning",
  "timeline_id": "main"
 },
 "since": [
  {
   "text": "Sect Master Liu considers you a liability and will not grant you any sect-owned breakthrough resources.",
   "ago_label": "an hour ago"
  },
  {
   "text": "The standard breakthrough to Core Formation has a ninety percent failure rate without a Core-Assisting Pill.",
   "ago_label": "an hour ago"
  },
  {
   "text": "You have exactly two years left of your natural 150-year lifespan.",
   "ago_label": "an hour ago"
  }
 ]
}
```

### On record (the player never sees this)

```json
{
 "world": {
  "title": "The Flickering Jade: A Cultivator's Last Stand",
  "genre": "Cultivation / Xianxia",
  "era": "Ancient Xianxia Era: spirit talismans, flying swords, and Qi-powered formations"
 },
 "character": {
  "id": "player",
  "name": "Han Feng",
  "aliases": [
   "Elder Han"
  ],
  "prominence": "key",
  "description": "An ancient cultivator with a heavily lined face, a long grey beard, and eyes reflecting decades of patience and growing desperation.",
  "appearance": "Thin, frail-looking frame concealed by loose, faded grey robes. Long, snow-white hair tied in a simple wooden topknot.",
  "age": 148,
  "people_id": "human",
  "location_id": "spirit-peak",
  "memberships": [
   {
    "faction_id": "misty-cloud",
    "rank": "Outer Elder",
    "loyalty": 40
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
  "lifespan_years": 150
 },
 "sheet": {
  "attributes": {
   "strength": 2,
   "wits": 4,
   "knowledge": 4,
   "willpower": 5,
   "nerve": 4,
   "bearing": 4
  },
  "skills": [
   {
    "name": "Qi Refinement",
    "level": "expert",
    "notes": "Decades of stagnation have made your control over your existing Qi exceptionally precise."
   },
   {
    "name": "Sword Cultivation",
    "level": "skilled",
    "notes": "Your swordsmanship is refined, though hindered by a physical body that tires quickly."
   },
   {
    "name": "Herbology",
    "notes": "Familiarity with common spiritual herbs from years of searching for a cure."
   }
  ],
  "traits": [
   {
    "name": "Brittle Meridians",
    "kind": "flaw",
    "description": "Your spiritual pathways are stiff and aged, making heavy Qi circulation painful and dangerous."
   },
   {
    "name": "Tempered Will",
    "kind": "gift",
    "description": "A century and a half of struggle has made your mind immune to ordinary illusions and spiritual intimidation."
   }
  ],
  "powers": [
   {
    "id": "foundation-qi",
    "name": "Foundation Qi Manipulation",
    "description": "You can manifest your liquid spiritual energy to form defensive shields, project blade beams, or glide short distances.",
    "limits": [
     "Limited by your pool of spiritual energy.",
     "Overexertion causes physical fatigue and strain on your meridians."
    ],
    "costs": [
     {
      "kind": "fatigue",
      "text": "Strains your physical body if used continuously for more than a few minutes."
     }
    ]
   }
  ],
  "techniques": [
   {
    "id": "misty-cloud-sword-stance",
    "name": "Misty Cloud Sword Stance",
    "style": "Misty Cloud Sword Art",
    "effect": "Creates deceptive phantoms of your blade to confuse the opponent's spiritual sense.",
    "cost": "Moderate Qi expenditure",
    "requirements": "A spiritual sword"
   }
  ],
  "disposition": {
   "temperament": {
    "traits": [
     "cautious",
     "resolute",
     "weathered"
    ],
    "values": [
     "Survival",
     "Dignity"
    ],
    "loves": [
     "The quiet of the mountains",
     "A well-brewed spiritual tea"
    ],
    "fears": [
     "Dying in obscurity",
     "Failing his disciple"
    ],
    "wants": [
     "Break through to Core Formation or I die."
    ],
    "voice": "Raspy, calm, and deliberate."
   }
  },
  "resources": {
   "items": [
    {
     "id": "worn-flying-sword",
     "name": "Worn Flying Sword",
     "kind": "weapon",
     "description": "A steel sword with a slightly dulled edge, but well-maintained and loyal to your spiritual signature."
    },
    {
     "id": "low-grade-qi-gathering-pill",
     "name": "Low-grade Qi-Gathering Pill",
     "kind": "consumable",
     "description": "A bitter pill that helps replenish lost spiritual energy over several hours.",
     "quantity": 3
    }
   ],
   "money": 120,
   "currency": "spirit stones",
   "title": "Elder of the Misty Cloud Sect",
   "rank": "Foundation Establishment (Peak)",
   "family_name": "Han",
   "connections": [
    {
     "name": "Chen Yi",
     "kind": "ally",
     "character_id": "disciple-chen",
     "note": "Your fiercely loyal sole disciple."
    }
   ]
  },
  "condition": {
   "reserves": [
    {
     "name": "Spiritual Qi"
    }
   ]
  },
  "axes": {
   "might": 4,
   "influence": 2,
   "wealth": 2,
   "knowledge": 3,
   "stealth": 2
  },
  "ladders": [
   {
    "ladder_id": "cultivation-realms",
    "rung": 1,
    "stage": "peak"
   }
  ],
  "rungs_heard": [
   {
    "ladder_id": "cultivation-realms",
    "rung": 2,
    "heard_s": 0,
    "known_s": 0,
    "known_from": "sect-master"
   }
  ],
  "backstory": [
   {
    "text": "You joined the Misty Cloud Sect as a young man with average talent."
   },
   {
    "text": "You reached the peak of Foundation Establishment eighty years ago, but the barrier to Core Formation remained completely impenetrable."
   },
   {
    "text": "As your lifespan dwindles to its absolute limit, you have retreated to Spirit-Severing Peak to make one final, desperate struggle for immortality."
   }
  ]
 },
 "gift": "none",
 "extraordinary": [
  "qi cultivation (common): Cultivators refine Qi to transcend mortality, manipulate elements, and fly through the heavens."
 ],
 "ladders": [
  {
   "id": "cultivation-realms",
   "name": "cultivation realms",
   "rungs": [
    "0: Qi Condensation (tier 2, lives 100)",
    "1: Foundation Establishment (tier 4, lives 150)",
    "2: Core Formation (tier 6, lives 500)",
    "3: Nascent Soul (tier 8, lives 2000)"
   ]
  }
 ],
 "peoples": [
  {
   "id": "human",
   "name": "Human",
   "description": "The dominant inhabitants of the mortal plains, many of whom seek the Dao to escape the cycle of reincarnation.",
   "lifespan_years": 80,
   "culture": "A society deeply structured by sect hierarchies and ancestral respect."
  }
 ],
 "rules": [
  "A cultivator's lifespan is bound to their realm; failing to break through before it expires leads to absolute mortality.",
  "Condensing a Golden Core requires compressing one's spiritual liquid into a solid core, a process highly lethal without protective pills.",
  "An aging body's meridians become brittle, exponentially increasing the pain and danger of Qi circulation during breakthrough attempts.",
  "Cultivators of the Foundation Establishment realm and above can traverse vast distances on flying swords, bypassing earthly terrain.",
  "Qi cultivation: real, and everywhere."
 ],
 "others": [
  "Sect Master Liu, 220, cultivation-realms rung 2, peak attribute 4",
  "Elder Song, 130, cultivation-realms rung 1, peak attribute 4",
  "Chen Yi, 24, cultivation-realms rung 0, peak attribute 4"
 ],
 "people_in_the_world": 3,
 "years": {
  "age": 148.0,
  "lives_about": 150,
  "the_record_says_so": true,
  "old": true,
  "told_the_end_is_close": false
 },
 "waiting": [
  "world.tick 'The world moves on' in 23.0 hours",
  "world.clock_step 'Lifespan Depletion: The first signs of grey rot touch your spiritual veins, slowing your Qi flow.' in 243.3 days",
  "world.old_age 'Your years run short' in 13.9 years (stops the player)"
 ]
}
```


## The draft (en, mature)

> A beautiful courtesan and spy in the imperial capital. She can make almost anyone fall for her, and she uses it to steal secrets for the rebellion.

_37.8 s, $0.088_

### What the draft's screen shows

Whispers of the Jade Pavilion
historical fantasy spy drama
seductive, tense, and treacherous
Mind-weaving: real, and hidden from most people.
Imperial Xijing: carriages, matchlock muskets, gas-lit teahouses, and paper mail.
Peoples: Human.
The Sisterhood of the Jade Pavilion: An influential guild of performers and hostesses who hold the secrets of Xijing's elite.
The Dragon Throne: The ruling class of ministers, eunuchs, and royals who maintain absolute control over the empire.
The Red Lotus Rebellion: A secretive network of freedom fighters, disgraced scholars, and lower-class workers aiming to overthrow the dynasty.
Mei Lin, 22, Human.
An incredibly elegant and poised woman whose presence is magnetic, with a soft voice that commands attention.
Prima Courtesan, The Sisterhood of the Jade Pavilion; Infiltrator, The Red Lotus Rebellion.
Master: Seduction. Expert: Sleight of Hand and Deception. Skilled: Eavesdropping.
One of a kind: The Art of Allure (any action or skill involving the manipulation of someone's affection or desire).
Gifts: Siren's Grace. Quirks: Shadow Agent.
Confident, daring, calculating and perceptive.
Siren's Whisper: Siren's Whisper (Requires eye contact and a low, intimate tone of voice.; Does not work on targets with extreme, unwavering willpower or holy protection.). Cost: Requires an hour of rest or deep meditation if used on multiple targets in a row.
Carries Lockpicking Hairpin, Vial of Sleeping Powder and Silk Fan. 80 silver taels.
Mind-weaving is a strictly forbidden art, and anyone caught practicing it is executed by the Inquisition.
Mental influence cannot force a target to commit acts that completely violate their deepest-held morals.
Messages travel across the empire via carrier pigeons or mounted imperial riders.
Mind-weaving: real, and hidden from most people.

### On record (the player never sees this)

```json
{
 "world": {
  "title": "Whispers of the Jade Pavilion",
  "genre": "historical fantasy spy drama",
  "era": "Imperial Xijing: carriages, matchlock muskets, gas-lit teahouses, and paper mail."
 },
 "character": {
  "id": "player",
  "name": "Mei Lin",
  "aliases": [
   "The Jewel of the Pavilion",
   "Agent Lotus-Six"
  ],
  "prominence": "key",
  "description": "An incredibly elegant and poised woman whose presence is magnetic, with a soft voice that commands attention.",
  "appearance": "Slender with porcelain skin, deep dark eyes, and long black hair held together by ornate jade hairpins, dressed in a flowing silk emerald qipao.",
  "age": 22,
  "people_id": "human",
  "location_id": "player-chambers",
  "memberships": [
   {
    "faction_id": "courtesan-guild",
    "rank": "Prima Courtesan",
    "loyalty": 60
   },
   {
    "faction_id": "red-lotus",
    "rank": "Infiltrator",
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
  "lifespan_years": 80
 },
 "sheet": {
  "attributes": {
   "strength": 2,
   "toughness": 2,
   "wits": 4,
   "willpower": 4,
   "charm": 5,
   "nerve": 5,
   "bearing": 4
  },
  "skills": [
   {
    "name": "Seduction",
    "level": "master",
    "notes": "Unmatched at reading desires and playing the perfect confidante."
   },
   {
    "name": "Sleight of Hand",
    "level": "expert",
    "notes": "Capable of picking pockets, lifting keys, and palming small items unnoticed."
   },
   {
    "name": "Deception",
    "level": "expert",
    "notes": "Excellent at maintaining covers and lying to authority figures."
   },
   {
    "name": "Eavesdropping",
    "level": "skilled",
    "notes": "Extracting key details from muffled background conversations."
   }
  ],
  "traits": [
   {
    "name": "Siren's Grace",
    "kind": "gift",
    "description": "Your striking beauty and elegant manners make others reluctant to suspect you of any wrongdoing."
   },
   {
    "name": "Shadow Agent",
    "description": "You are highly observant, always locating exits and loose floorboards in any room you enter."
   }
  ],
  "talents": [
   {
    "id": "the-art-of-allure",
    "name": "The Art of Allure",
    "covers": "any action or skill involving the manipulation of someone's affection or desire.",
    "strength": "one_of_a_kind",
    "reason": "She has honed her unique voice, micro-expressions, and natural charm to absolute perfection."
   }
  ],
  "powers": [
   {
    "id": "mind-allure",
    "name": "Siren's Whisper",
    "strength": "rare",
    "limits": [
     "Requires eye contact and a low, intimate tone of voice.",
     "Does not work on targets with extreme, unwavering willpower or holy protection."
    ],
    "costs": [
     {
      "kind": "fatigue",
      "text": "Requires an hour of rest or deep meditation if used on multiple targets in a row."
     }
    ]
   }
  ],
  "techniques": [
   {
    "id": "viper-s-kiss",
    "name": "Viper's Kiss",
    "style": "Subtle Seduction",
    "effect": "Allows you to slip a powder or poison into a target's drink while kissing them or leaning in close.",
    "cost": "None",
    "requirements": "Target must be infatuated or highly distracted by you."
   }
  ],
  "disposition": {
   "temperament": {
    "traits": [
     "confident",
     "daring",
     "calculating",
     "perceptive"
    ],
    "values": [
     "freedom",
     "loyalty to the oppressed"
    ],
    "loves": [
     "tea",
     "traditional lute music",
     "outwitting arrogant nobles"
    ],
    "fears": [
     "being locked in a dungeon",
     "causing the death of innocent rebel contacts"
    ],
    "wants": [
     "To steal the palace security blueprints and secure the rebellion's safety."
    ]
   }
  },
  "resources": {
   "items": [
    {
     "id": "lockpicking-hairpin",
     "name": "Lockpicking Hairpin",
     "kind": "gear",
     "description": "A beautiful brass hairpin that can easily be disassembled into a functional set of lockpicks."
    },
    {
     "id": "vial-of-sleeping-powder",
     "name": "Vial of Sleeping Powder",
     "kind": "consumable",
     "description": "A fine, odorless powder that slips into wine to put a grown man to sleep within minutes.",
     "quantity": 2
    },
    {
     "id": "silk-fan",
     "name": "Silk Fan",
     "kind": "gear",
     "description": "A hand-painted fan used to coyly hide facial expressions and distract targets."
    }
   ],
   "money": 80,
   "currency": "silver taels",
   "title": "Prima Courtesan",
   "rank": "Elite Hostess",
   "connections": [
    {
     "name": "Li Wei",
     "kind": "ally",
     "character_id": "li-wei",
     "note": "Your trusted contact and handler in the Red Lotus Rebellion."
    }
   ]
  },
  "axes": {
   "influence": 3,
   "wealth": 2,
   "knowledge": 3,
   "stealth": 4
  },
  "backstory": [
   {
    "text": "Orphaned at a young age when her home province was heavily taxed and starved by the crown, she was taken in by the Jade Pavilion."
   },
   {
    "text": "Discovered her latent mind-weaving abilities during her early training and chose to use them to undermine the corrupt elite rather than just serve them."
   },
   {
    "text": "Formed an alliance with the Red Lotus to use her status as a weapon for change."
   }
  ]
 },
 "gift": "rare",
 "extraordinary": [
  "mind-weaving (hidden): Allows the user to subtly alter emotions, lower inhibitions, and plant suggestions through voice and touch."
 ],
 "peoples": [
  {
   "id": "human",
   "name": "Human",
   "lifespan_years": 80,
   "culture": "The people of Xijing value poetry, hierarchy, tea ceremonies, and strict social standing."
  }
 ],
 "rules": [
  "Mind-weaving is a strictly forbidden art, and anyone caught practicing it is executed by the Inquisition.",
  "Mental influence cannot force a target to commit acts that completely violate their deepest-held morals.",
  "Messages travel across the empire via carrier pigeons or mounted imperial riders.",
  "Mind-weaving: real, and hidden from most people."
 ],
 "others": [
  "Li Wei, 26, peak attribute 5",
  "Madam Yume, 47, peak attribute 5",
  "Minister Gong, 52, peak attribute 4"
 ],
 "people_in_the_world": 3,
 "years": {
  "age": 22.0,
  "lives_about": 80,
  "the_record_says_so": true,
  "old": false,
  "told_the_end_is_close": false
 }
}
```

## Turn 1 (opening), 7.9 s, $0.045

_From Day 1, evening, 20:00 to Day 1, evening, 20:00 (0 s). Mei Lin is 22, alive._

Your slender fingers brush against the embroidered purple silk of Minister Gong's sash, moving with a ghost's light touch. While he focuses on pouring the dark, spiced wine from the silver decanter, his stout frame swaying slightly under the weight of your soft gaze, you slide the delicate brass key from his belt and slip it into the wide emerald sleeve of your qipao.

The key vanishes into the silk without a single click. When Gong turns back, his eyes are heavy, utterly captured by the lingering thread of your Siren's Whisper. He offers you the silver cup with a sluggish smile, quite unaware that the instrument to his undoing is already in your possession. That key unlocks his private lockbox—the very one currently resting inside his heavy leather carriage downstairs, which contains the inner palace guard schedules. You must decide whether to slip your sleeping powder into his wine to slip away to the carriages, or keep him charmed here while you devise a cleaner escape.

**Suggestions:**
1. Slip the sleeping powder into his wine as you lean close. (thread)
2. Drink with him and use your allure to learn where the box is kept. (personal)
3. Excuse yourself to find Madam Yume and have her create a distraction. (side)

**Issues:**
- rejected (character minister-gong: rung low): no ladder has that rung
- start_told (goal:goal-1): the story told it
- start_told (person:madam-yume): the story told it
- start_told (person:minister-gong): the story told it
- start_told (thread:steal-blueprints): the story told it

**Counted:** {"goals_open": 2}

## What the screens show (turn 1)

### Memory

```json
{
 "character": {
  "name": "Mei Lin",
  "lines": [
   "An incredibly elegant and poised woman whose presence is magnetic, with a soft voice that commands attention.",
   "Prima Courtesan",
   "Elite Hostess"
  ]
 },
 "people": [
  {
   "id": "madam-yume",
   "name": "Madam Yume",
   "lines": [
    "The shrewd, elegantly aging keeper of the Jade Pavilion who knows how to leverage every secret."
   ],
   "attitude": "friendly",
   "attitude_label": "Friendly",
   "status": "alive",
   "presumed": false,
   "status_label": "Alive"
  },
  {
   "id": "minister-gong",
   "name": "Minister Gong",
   "lines": [
    "A corrupt, middle-aged imperial minister who oversees capital security. He is obsessed with the finer things in life."
   ],
   "attitude": "friendly",
   "attitude_label": "Friendly",
   "status": "alive",
   "presumed": false,
   "status_label": "Alive"
  }
 ],
 "places": [
  {
   "id": "jade-pavilion",
   "name": "The Jade Pavilion",
   "lines": [
    "Building",
    "The capital's most exclusive pleasure house, draped in heavy silks, smelling of incense and expensive plum wine.",
    "You haven't been there."
   ]
  },
  {
   "id": "player-chambers",
   "name": "Mei Lin's Private Chambers",
   "lines": [
    "Room",
    "A lavishly decorated room behind paper screens, featuring a plush daybed, carved vanity, and hidden floorboards."
   ]
  },
  {
   "id": "imperial-palace",
   "name": "The Obsidian Palace",
   "lines": [
    "Building",
    "The heavily guarded, grand seat of the Solaris Emperor, rising high above Xijing.",
    "You haven't been there."
   ]
  },
  {
   "id": "rebel-safehouse",
   "name": "The Willow District Cellar",
   "lines": [
    "Wilds",
    "An abandoned, damp coal storage cellar converted into a clandestine planning room for the rebellion.",
    "You haven't been there."
   ]
  },
  {
   "id": "xijing",
   "name": "Xijing Imperial Capital",
   "lines": [
    "City",
    "A sprawling metropolis of stone walls, grand pagodas, and gas-lit avenues reflecting in dark canals.",
    "You haven't been there."
   ]
  }
 ],
 "factions": [
  {
   "id": "imperial-court",
   "name": "The Dragon Throne",
   "lines": [
    "Court",
    "The ruling class of ministers, eunuchs, and royals who maintain absolute control over the empire."
   ],
   "esteem": "neutral",
   "dread": "none",
   "standing_label": "Neutral"
  },
  {
   "id": "red-lotus",
   "name": "The Red Lotus Rebellion",
   "lines": [
    "Sect",
    "A secretive network of freedom fighters, disgraced scholars, and lower-class workers aiming to overthrow the dynasty."
   ],
   "esteem": "neutral",
   "dread": "none",
   "standing_label": "Neutral"
  },
  {
   "id": "courtesan-guild",
   "name": "The Sisterhood of the Jade Pavilion",
   "lines": [
    "Family",
    "An influential guild of performers and hostesses who hold the secrets of Xijing's elite."
   ],
   "esteem": "neutral",
   "dread": "none",
   "standing_label": "Neutral"
  }
 ],
 "goals": [
  {
   "id": "goal-1",
   "text": "Steal the palace guard schedules from Minister Gong",
   "kind": "own",
   "origin": "start",
   "origin_label": "Yours from the start"
  }
 ],
 "threads": [
  {
   "id": "steal-blueprints",
   "title": "Steal the Palace Guard Schedules",
   "status": "open"
  }
 ]
}
```


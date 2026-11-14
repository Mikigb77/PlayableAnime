## The draft (en, teen)

> Everyone in this world is born with magic. I'm the only one ever born without any. But magic doesn't work on me either.

_61.0 s, $0.116_

### What the draft's screen shows

Untouchable
High Fantasy
wonder and tension
Every living human is born with a mana core and can cast spells, except for the rare anomaly.
A high-medieval fantasy era: magical hearths, crystal lanterns, and floating skyships powered by mana.
Mana ranks: Apprentice, Journeyman, Mage, Archmage.
Peoples: Human.
House Valerius: An ancient noble family famous for producing high-tier elemental mages.
The Archmage Council: The ruling body of Lumina, comprised of the most powerful spellcasters in the land.
Why was I born without magic, yet immune to it?
Karen, 18.
A focused, resilient youth with watchful eyes, carrying the quiet confidence of someone who has had to rely entirely on their own physical limits.
Disgraced Heir, House Valerius.
Expert: Observation. Skilled: Athletics. Fair: Melee Combat.
One of a kind: Null Body (any physical training or martial move you attempt to master).
Gifts: Iron Will. Flaws: Magically Blind.
Observant, determined and guarded.
Absolute Magic Immunity: Your lack of a mana core prevents spells from interacting with or affecting your body in any way (Does not protect against indirect magical physical hazards, like a magically thrown boulder or a collapsing ceiling.).
Carries Steel Dagger. Owns Practice Wooden Sword. 15 silver pieces.
Every living human is born with a mana core and can cast spells, except for the rare anomaly.
Magic has no effect on a person who does not possess a mana core.
Mana can be stored in physical crystals to power machines, skyships, and cities.

### On record (the player never sees this)

```json
{
 "world": {
  "title": "Untouchable",
  "genre": "High Fantasy",
  "era": "A high-medieval fantasy era: magical hearths, crystal lanterns, and floating skyships powered by mana."
 },
 "character": {
  "id": "player",
  "name": "Karen",
  "prominence": "key",
  "description": "A focused, resilient youth with watchful eyes, carrying the quiet confidence of someone who has had to rely entirely on their own physical limits.",
  "appearance": "Athletic build, short dark hair, wearing a simple leather training vest and trousers that contrast with the ornate robes of the academy students.",
  "age": 18,
  "location_id": "lumina-academy",
  "memberships": [
   {
    "faction_id": "house-valerius",
    "rank": "Disgraced Heir",
    "loyalty": 10
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
  "parent_ids": [
   "lord-valerius"
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
    "name": "Athletics",
    "level": "skilled",
    "notes": "Years of physical training to compensate for a lack of magic."
   },
   {
    "name": "Melee Combat",
    "notes": "Proficient in basic hand-to-hand and sword techniques."
   },
   {
    "name": "Observation",
    "level": "expert",
    "notes": "You have learned to watch a mage's hands and focus to predict their spells."
   }
  ],
  "traits": [
   {
    "name": "Iron Will",
    "kind": "gift",
    "description": "Resistant to fear and psychological pressure, hardened by years of being an outcast."
   },
   {
    "name": "Magically Blind",
    "kind": "flaw",
    "description": "You cannot sense ambient mana or see invisible magical constructs with the naked eye."
   }
  ],
  "talents": [
   {
    "id": "null-body",
    "name": "Null Body",
    "covers": "any physical training or martial move you attempt to master",
    "strength": "one_of_a_kind",
    "reason": "Because your body is completely free of mana, your muscles, reflexes, and physical senses adapt to physical training at an unnatural speed."
   }
  ],
  "powers": [
   {
    "id": "absolute-immunity",
    "name": "Absolute Magic Immunity",
    "description": "Your lack of a mana core prevents spells from interacting with or affecting your body in any way.",
    "strength": "overpowered",
    "limits": [
     "Does not protect against indirect magical physical hazards, like a magically thrown boulder or a collapsing ceiling."
    ]
   }
  ],
  "disposition": {
   "temperament": {
    "traits": [
     "observant",
     "determined",
     "guarded"
    ],
    "values": [
     "self-reliance",
     "physical competence"
    ],
    "loves": [
     "quiet study",
     "physical challenges"
    ],
    "fears": [
     "being completely helpless in a physical trap"
    ]
   }
  },
  "resources": {
   "items": [
    {
     "id": "steel-dagger",
     "name": "Steel Dagger",
     "kind": "weapon",
     "description": "A well-balanced steel blade, entirely un-enchanted."
    },
    {
     "id": "practice-wooden-sword",
     "name": "Practice Wooden Sword",
     "kind": "weapon",
     "description": "Chipped and worn from thousands of swings.",
     "carried": false
    }
   ],
   "money": 15,
   "currency": "silver pieces",
   "family_name": "Valerius",
   "connections": [
    {
     "name": "Sister Lyra",
     "kind": "family",
     "character_id": "sister-lyra",
     "note": "The only member of your family who still shows you genuine warmth."
    }
   ]
  },
  "axes": {
   "might": 2,
   "knowledge": 2,
   "stealth": 2
  }
 },
 "gift": "overpowered",
 "extraordinary": [
  "spellcasting and mana manipulation (common): Casting spells to manipulate elements, heal wounds, or power machines, up to bending space itself."
 ],
 "ladders": [
  {
   "id": "magic-ranks",
   "name": "mana ranks",
   "rungs": [
    "0: Apprentice (tier 2, lives 0)",
    "1: Journeyman (tier 4, lives 0)",
    "2: Mage (tier 6, lives 0)",
    "3: Archmage (tier 8, lives 0)"
   ]
  }
 ],
 "peoples": [
  {
   "id": "human",
   "name": "Human",
   "lifespan_years": 80,
   "culture": "A society deeply divided by magical aptitude and lineage, where spellcasting is the measure of worth."
  }
 ],
 "rules": [
  "Every living human is born with a mana core and can cast spells, except for the rare anomaly.",
  "Magic has no effect on a person who does not possess a mana core.",
  "Mana can be stored in physical crystals to power machines, skyships, and cities."
 ],
 "others": [
  "Headmaster Vane, 62, magic-ranks rung 3, peak attribute 5",
  "Lord Valerius, 48, magic-ranks rung 2, peak attribute 5",
  "Lyra Valerius, 16, magic-ranks rung 1, peak attribute 5"
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


## The draft (en, teen)

> A knight in his thirties serving a minor lord on the border. Decent with a sword, nothing special.

_41.0 s, $0.097_

### What the draft's screen shows

The Border Knight
grounded medieval drama
gritty and realistic
Magic and the supernatural do not exist; the physical laws of nature are absolute.
High Medieval borderlands: steel swords, chainmail, and horse-travel.
Peoples: Human.
The Red Cap Bandits: A ruthless gang of outlaws and deserters who raid isolated farms along the border.
House Oswald: A minor noble house tasked with holding this barren stretch of the realm's frontier.
Ser Thomas, 34, Human.
A quiet, weathered knight in his thirties who knows his duty and does it without complaint.
Knight, House Oswald.
Fair: Swordsmanship and Horsemanship. Novice: Shield-work.
Gifts: Duty-Bound. Flaws: Patrol Weariness.
Practical, quiet and reliable.
No powers, since this world has none.
Carries Iron Sword, Weathered Chainmail and Wooden Shield. Owns Patrol Horse. 15 silver coins.
Lord Oswald.
Magic and the supernatural do not exist; the physical laws of nature are absolute.
A knight is bound by holy oath to serve their lord, and breaking fealty brings absolute ruin.
Wounds fester easily and diseases kill; there are no magical cures, only basic herbalism and amputations.

### On record (the player never sees this)

```json
{
 "world": {
  "title": "The Border Knight",
  "genre": "grounded medieval drama",
  "era": "High Medieval borderlands: steel swords, chainmail, and horse-travel"
 },
 "character": {
  "id": "player",
  "name": "Ser Thomas",
  "prominence": "key",
  "description": "A quiet, weathered knight in his thirties who knows his duty and does it without complaint.",
  "appearance": "An average, unassuming build, dark brown hair cut short, wearing a faded green surcoat over simple steel chainmail.",
  "age": 34,
  "people_id": "human",
  "location_id": "border-keep",
  "memberships": [
   {
    "faction_id": "house-oswald",
    "rank": "Knight",
    "loyalty": 85
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
  "lifespan_years": 75
 },
 "sheet": {
  "skills": [
   {
    "name": "Swordsmanship",
    "notes": "Decent with an iron blade, though no match for a true champion."
   },
   {
    "name": "Horsemanship",
    "notes": "Capable of riding in formation and handling long, exhausting patrols."
   },
   {
    "name": "Shield-work",
    "level": "novice",
    "notes": "Trained to keep a wooden shield between himself and incoming blows."
   }
  ],
  "traits": [
   {
    "name": "Duty-Bound",
    "kind": "gift",
    "description": "He takes his knightly oath seriously, earning him the respect of his lord."
   },
   {
    "name": "Patrol Weariness",
    "kind": "flaw",
    "description": "Years of riding in cold rain have left him with stiff joints that ache on damp mornings."
   }
  ],
  "disposition": {
   "temperament": {
    "traits": [
     "practical",
     "quiet",
     "reliable"
    ],
    "values": [
     "duty",
     "survival"
    ],
    "loves": [
     "the warmth of the barracks hearth"
    ],
    "fears": [
     "failing his oath and dishonoring his name"
    ]
   }
  },
  "resources": {
   "items": [
    {
     "id": "iron-sword",
     "name": "Iron Sword",
     "kind": "weapon",
     "description": "A simple, well-balanced arming sword showing signs of regular sharpening."
    },
    {
     "id": "weathered-chainmail",
     "name": "Weathered Chainmail",
     "kind": "armour",
     "description": "A sturdy suit of iron mail links, worn over a padded gambeson."
    },
    {
     "id": "wooden-shield",
     "name": "Wooden Shield",
     "kind": "armour",
     "description": "A heater-style shield painted with the fading oak leaf of House Oswald."
    },
    {
     "id": "patrol-horse",
     "name": "Patrol Horse",
     "kind": "vehicle",
     "description": "A reliable, short-tempered gelding suited for rough terrain.",
     "carried": false
    }
   ],
   "money": 15,
   "currency": "silver coins",
   "title": "Ser",
   "rank": "Knight",
   "connections": [
    {
     "name": "Lord Oswald",
     "kind": "trusts_them",
     "character_id": "lord-oswald",
     "note": "Thomas has served him faithfully for nearly a decade."
    }
   ]
  },
  "backstory": [
   {
    "text": "Thomas was knighted after defending a supply wagon during a border skirmish in his twenties."
   },
   {
    "text": "He has spent his entire knightly career in service to House Oswald, patrolling the same muddy forests."
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
   "lifespan_years": 75,
   "culture": "Feudal borderland culture, focused on hard labor, duty, and keeping watch against raids."
  }
 ],
 "rules": [
  "Magic and the supernatural do not exist; the physical laws of nature are absolute.",
  "A knight is bound by holy oath to serve their lord, and breaking fealty brings absolute ruin.",
  "Wounds fester easily and diseases kill; there are no magical cures, only basic herbalism and amputations."
 ],
 "others": [
  "Karl One-Eye, 41, peak attribute 3",
  "Lord Oswald, 58, peak attribute 3",
  "Ser Rodrick, 45, peak attribute 3"
 ],
 "people_in_the_world": 3,
 "years": {
  "age": 34.0,
  "lives_about": 75,
  "the_record_says_so": true,
  "old": false,
  "told_the_end_is_close": false
 }
}
```

## Turn 1 (opening), 5.6 s, $0.041

_From Day 1, morning, 08:00 to Day 1, morning, 08:00 (0 s). Ser Thomas is 34, alive._

You stand in the drafty great hall of Oswald Keep, the damp cold of a border morning seeping right through your weathered chainmail. Heavy grey clouds loom outside the narrow arrow slits, and the fire in the hearth does little to dispel the chill. Lord Oswald is studying a crude parchment map on the long oak table, his heavy brow furrowed as he traces the line of the river. By the hearth, Ser Rodrick stands warming his hands, his scarred face grim. Lord Oswald taps a thick finger on the parchment, right over the mark for Lowbridge Village. 'The Red Cap Bandits were spotted at the ford yesterday,' the old lord says, his voice raspy. 'They are raiding closer to our walls than they dare in summer. Thomas, Rodrick, we cannot let them burn the winter stores.' Rodrick spits into the embers with a dry sigh. 'Our men are tired, my Lord, and we have no coin for steel.' Lord Oswald looks up, his stern eyes settling on you, waiting to hear how you intend to secure the border road.

**Suggestions:**
1. Offer to lead a patrol down to Lowbridge Village immediately. (thread)
2. Ask Rodrick how many able-bodied men remain in the garrison. (personal)
3. Suggest strengthening the guard at the keep's gate first. (side)

**Issues:**
- start_told (person:lord-oswald): the story told it
- start_told (person:ser-rodrick): the story told it
- start_told (thread:border-defense): the story told it

## What the screens show (turn 1)

### Memory

```json
{
 "character": {
  "name": "Ser Thomas",
  "lines": [
   "A quiet, weathered knight in his thirties who knows his duty and does it without complaint.",
   "Ser",
   "Knight"
  ]
 },
 "people": [
  {
   "id": "lord-oswald",
   "name": "Lord Oswald",
   "lines": [
    "An aging, stern frontier lord who values duty and order above all else."
   ],
   "attitude": "friendly",
   "attitude_label": "Friendly",
   "status": "alive",
   "presumed": false,
   "status_label": "Alive"
  },
  {
   "id": "ser-rodrick",
   "name": "Ser Rodrick",
   "lines": [
    "A cynical veteran knight who has spent twenty years on these borders and expects little from life."
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
   "id": "garrison-yard",
   "name": "The Garrison Yard",
   "lines": [
    "Wilds",
    "A muddy training yard within the keep's wooden palisade, smelling of horse dung and wet hay.",
    "You haven't been there."
   ]
  },
  {
   "id": "border-village",
   "name": "Lowbridge Village",
   "lines": [
    "Village",
    "A cluster of thatched peasant huts huddled near a strategic river crossing.",
    "You haven't been there."
   ]
  },
  {
   "id": "border-keep",
   "name": "Oswald Keep",
   "lines": [
    "Building",
    "A drafty stone fortress weathered by the northern wind, standing watch over the border lands."
   ]
  },
  {
   "id": "wild-woods",
   "name": "The Wild Woods",
   "lines": [
    "Wilds",
    "A dense, ancient forest stretching past the border, unclaimed by any king and home to outlaws.",
    "You haven't been there."
   ]
  }
 ],
 "factions": [
  {
   "id": "house-oswald",
   "name": "House Oswald",
   "lines": [
    "Family",
    "A minor noble house tasked with holding this barren stretch of the realm's frontier."
   ],
   "esteem": "neutral",
   "dread": "none",
   "standing_label": "Neutral"
  },
  {
   "id": "border-bandits",
   "name": "The Red Cap Bandits",
   "lines": [
    "Crew",
    "A ruthless gang of outlaws and deserters who raid isolated farms along the border."
   ],
   "esteem": "neutral",
   "dread": "none",
   "standing_label": "Neutral"
  }
 ],
 "threads": [
  {
   "id": "border-defense",
   "title": "Defending the Border",
   "status": "open"
  }
 ]
}
```


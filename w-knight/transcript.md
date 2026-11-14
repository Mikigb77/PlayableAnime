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

## Turn 2 (action), 8.9 s, $0.047

> I offer to lead a patrol to Lowbridge at dawn and ask Ser Rodrick to ride with me.

_From Day 1, morning, 08:00 to Day 1, morning, 08:00 (30 s). Ser Thomas is 34, alive._

**Read and decided:**
- read as conversation, 'persuade' on lord-oswald, ser-rodrick, 30 s: I offer to lead a patrol to Lowbridge at dawn and ask Ser Rodrick to ride with me.
- I offer to lead a patrol to Lowbridge at dawn and ask Ser Rodrick to ride with me. [contested, success]: Horsemanship (fair), 2 dice, against Ser Rodrick, level 2; one more at their side (+5); your Duty-Bound (-5): 26 against 17, passed.
- dice: hand 2 (Horsemanship (fair), 2 dice), number 17, 26 of 40 against Lord Oswald's cautious nature and the weary cynicism of Ser Rodrick.: passed

You step closer to the long oak table, your hand resting naturally near the hilt of your iron sword. Looking directly at the old lord, you say, "I will lead a patrol to Lowbridge at dawn." You then turn your gaze to the older knight by the hearth. "Rodrick, ride with me."

Your words carry the quiet weight of your decades of service, and your duty-bound tone leaves little room for argument. Lord Oswald pauses, his calloused hand remaining flat upon the map. He looks from the parchment to you, a faint nod of approval touching his grim features. "Lowbridge is where they will strike first if they mean to starve us out," the lord says, his raspy voice low. Ser Rodrick lets out a dry cough, rubbing his scarred hands together before pulling them away from the warmth of the fire. He looks at you with tired, dark eyes, but the cynical edge of his expression softens slightly at your readiness. "The dawn is damp, Thomas, and my joints are already screaming," Rodrick grunts, though he reaches for his heavy wool cloak hanging by the door. "But I'll not have you riding into a hornets' nest alone. We ride at dawn."

**Suggestions:**
1. Ask Lord Oswald for extra scouts from the garrison. (thread)
2. Discuss a defense plan for the Lowbridge ford with Rodrick. (thread)
3. Head down to the stables to inspect your patrol horse. (wild)

## Turn 3 (action), 8.0 s, $0.032

> That evening I find the widow who keeps the inn at Lowbridge, buy her a drink and try to seduce her.

_From Day 1, morning, 08:00 to Day 1, morning, 10:30 (2.5 hours). Ser Thomas is 34, alive._

**Read and decided:**
- read as travel, 'travel', 7200 s: Travel to Lowbridge Village
- read as conversation, 'persuade', 1800 s: Find the widow at the inn, buy her a drink, and try to seduce her
- Travel to Lowbridge Village [certain, success]: Nothing stands in the way.
- Find the widow at the inn, buy her a drink, and try to seduce her [contested, success]: Charm, 2 dice, against a real effort, level 2: 25 against 17, passed.
- dice: hand 2 (Charm, 2 dice), number 17, 25 of 40 against A close call.: passed
- meanwhile: ["Ser Rodrick tells House Oswald"]
- heading: Three hours later

That evening, though you had spoken of dawn, you ride early to Lowbridge Village. In the dim, drafty tavern, you find the widow who runs the place. You pull up a bench, call for a cup of small beer, and slide a coin across the scarred wood to buy her a drink. Leaning close, you speak softly, letting your rugged charm do the work.

The journey down the muddy border road takes you through the damp, quiet woods under the grey morning sky. You arrive in Lowbridge Village, a cluster of thatched roofs clinging to the wet earth. Inside the damp warmth of the inn, the widow, a weary woman named Clara, looks you over with cautious interest. She accepts the drink, the silver coin clinking on the wood as the tavern keeper pours the brew. Your quiet confidence and smooth words find their mark; she smiles faintly, the sharp lines of her face softening as she leans in to listen to your low voice.

**Suggestions:**
1. Ask Clara if she has heard rumors of the Red Caps. (thread)
2. Whisper a promise to return to her bed once patrol ends. (personal)
3. Settle your tab and walk out to check the horses. (side)

**Issues:**
- rejected (character clara-widow: rung None): no ladder has that rung

## What the screens show (turn 3)

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
    "A cluster of thatched peasant huts huddled near a strategic river crossing."
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
 "deeds": [
  {
   "id": "deed-1",
   "text": "I offer to lead a patrol to Lowbridge at dawn and ask Ser Rodrick to ride with me. (it worked)",
   "when_label": "Day 1, morning",
   "seen": "seen",
   "known_label": "Seen by Lord Oswald and Ser Rodrick"
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
  "location_id": "border-village",
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
   "money": 14,
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
  "Clara, peak attribute 3",
  "Karl One-Eye, 41, peak attribute 3",
  "Lord Oswald, 58, peak attribute 3",
  "Ser Rodrick, 45, peak attribute 3"
 ],
 "people_in_the_world": 4,
 "years": {
  "age": 34.0,
  "lives_about": 75,
  "the_record_says_so": true,
  "old": false,
  "told_the_end_is_close": false
 },
 "waiting": [
  "world.word 'Word of a deed may get out' in 1488 s",
  "world.clock_step 'The Red Cap Raid: Bandit scouts are spotted in the forest fringes near Lowbridge Village.' in 21.5 hours",
  "world.tick 'The world moves on' in 21.5 hours",
  "world.old_age 'Your years run short' in 44.4 years (stops the player)"
 ]
}
```


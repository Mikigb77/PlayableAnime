## The draft (en, mature)

> I'm the best hacker in Night City. Corporations pay fortunes to keep me out of their systems.

_31.8 s, $0.080_

### What the draft's screen shows

Cybernetic Horizon
Cyberpunk
gritty, neon-noir, high-tech low-life
Cybernetic augmentations: real, and everywhere.
Neural netrunning and hacking: real, and everywhere.
Night City, 2077: cybernetic implants, flying vehicles, and lethal corporate intranets.
Netrunner Ranks: Script Kid, Code Jockey, Sysop, Glitcher, Netrunner and beyond.
Peoples: Human.
Arasaka Corporation: A mega-conglomerate specializing in corporate security, banking, and defense systems.
Netwatch: The online police force tasked with keeping the Net safe from rogue AIs and high-tier hackers.
Zero, 26, Human.
A pale, incredibly focused specialist who speaks in short, precise bursts and exists mostly inside digital space.
Legend of the Net.
Legend of the Net, early stage.
Master: Hacking. Expert: Stealth. Skilled: Electronics. Novice: Handguns.
One of a kind: The Sword of Code (any program or code intrusion technique you watch another netrunner perform).
Gifts: Neural Interface Pro. Flaws: Cyber-Addiction.
Introverted, unshakeable and calculating.
Neural Overheat: Neural Overheat (Requires a line of sight or an active local subnet connection to the target.). Cost: Causes mild neural fatigue and a brief cooldown of 10 seconds.
Carries Legendary Cyberdeck (Militech Sovereign) and Smart Pistol (Arasaka Yukimura). 75,000 eddies.
Netrunning directly exposes a hacker's brain to lethal feedback loops and Black ICE programs.
Pushing past human neural limits with excessive cybernetics risks mental collapse and cyberpsychosis.
Megacorporations operate entirely above local law inside their designated physical and digital territories.
Data and messages travel instantly across the global Net, making physical isolation the only true privacy.
Cybernetic augmentations: real, and everywhere.
Neural netrunning and hacking: real, and everywhere.

### On record (the player never sees this)

```json
{
 "world": {
  "title": "Cybernetic Horizon",
  "genre": "Cyberpunk",
  "era": "Night City, 2077: cybernetic implants, flying vehicles, and lethal corporate intranets"
 },
 "character": {
  "id": "player",
  "name": "Zero",
  "aliases": [
   "The Ghost",
   "Null Pointer"
  ],
  "prominence": "key",
  "description": "A pale, incredibly focused specialist who speaks in short, precise bursts and exists mostly inside digital space.",
  "appearance": "Sleek, glowing chrome neural ports along the neck, reflective cybernetic eyes that pulse with data, and dark, oversized techwear hoodie hiding a lean frame.",
  "age": 26,
  "people_id": "human",
  "location_id": "player-hideout",
  "origin": {
   "kind": "premise"
  },
  "known_by": [
   "player"
  ],
  "met_by": [
   "player"
  ],
  "lifespan_years": 85
 },
 "sheet": {
  "attributes": {
   "strength": 2,
   "toughness": 2,
   "wits": 5,
   "knowledge": 5,
   "willpower": 4,
   "nerve": 4
  },
  "skills": [
   {
    "name": "Hacking",
    "level": "master",
    "notes": "Unmatched speed and intuition with raw code."
   },
   {
    "name": "Stealth",
    "level": "expert",
    "notes": "Expert at avoiding both camera sweeps and physical sentries."
   },
   {
    "name": "Electronics",
    "level": "skilled",
    "notes": "Quick with rewiring panels and bypassing physical locks."
   },
   {
    "name": "Handguns",
    "level": "novice",
    "notes": "Basic training in case the street gets too loud."
   }
  ],
  "traits": [
   {
    "name": "Neural Interface Pro",
    "kind": "gift",
    "description": "Plugs directly into the net with significantly higher data-transfer speeds."
   },
   {
    "name": "Cyber-Addiction",
    "kind": "flaw",
    "description": "Suffers physical shaking and severe headaches if disconnected from the Net for too long."
   }
  ],
  "talents": [
   {
    "id": "the-sword-of-code",
    "name": "The Sword of Code",
    "covers": "any program or code intrusion technique you watch another netrunner perform.",
    "strength": "one_of_a_kind",
    "reason": "Possesses a highly advanced, copycat-optimized ocular implant."
   }
  ],
  "powers": [
   {
    "id": "neural-overload",
    "name": "Neural Overheat",
    "strength": "rare",
    "limits": [
     "Requires a line of sight or an active local subnet connection to the target."
    ],
    "costs": [
     {
      "kind": "fatigue",
      "text": "Causes mild neural fatigue and a brief cooldown of 10 seconds."
     }
    ]
   }
  ],
  "techniques": [
   {
    "id": "glitch-shift",
    "name": "Glitch Shift",
    "style": "Electronic Countermeasures",
    "effect": "Temporarily blinds all nearby optical cybernetics and cameras for five seconds.",
    "cost": "Minor cyberdeck battery drain",
    "requirements": "Requires an active wireless transmitter"
   }
  ],
  "disposition": {
   "temperament": {
    "traits": [
     "introverted",
     "unshakeable",
     "calculating"
    ],
    "values": [
     "mastery",
     "freedom"
    ],
    "loves": [
     "clean, elegant code",
     "the quiet hum of a server room"
    ],
    "fears": [
     "losing consciousness",
     "becoming a corporate shell"
    ],
    "wants": [
     "Maintain supremacy over the Net and keep corporate hands off your freedom."
    ]
   }
  },
  "resources": {
   "items": [
    {
     "id": "legendary-cyberdeck-militech-sovereign",
     "name": "Legendary Cyberdeck (Militech Sovereign)",
     "kind": "gear",
     "description": "A top-of-the-line neural deck modified with experimental cooling."
    },
    {
     "id": "smart-pistol-arasaka-yukimura",
     "name": "Smart Pistol (Arasaka Yukimura)",
     "kind": "weapon",
     "description": "A compact smart-linked pistol with target tracking."
    }
   ],
   "money": 75000,
   "currency": "eddies",
   "rank": "Legend of the Net",
   "connections": [
    {
     "name": "Cipher",
     "character_id": "cipher",
     "note": "A highly skilled rival who keeps you on your toes."
    },
    {
     "name": "Vance",
     "character_id": "vance",
     "note": "Your primary source of high-paying corporate bounties."
    }
   ]
  },
  "condition": {
   "reserves": [
    {
     "name": "Neural Memory"
    }
   ]
  },
  "axes": {
   "might": 2,
   "influence": 3,
   "wealth": 4,
   "knowledge": 5,
   "stealth": 14
  },
  "ladders": [
   {
    "ladder_id": "netrunner-rank",
    "rung": 6,
    "stage": "early"
   }
  ],
  "backstory": [
   {
    "text": "Raised in the neon-soaked lower-slums, you taught yourself how to program using discarded corp tablets."
   },
   {
    "text": "At age twenty, you pulled off your first major heist against a Militech research laboratory, earning your reputation."
   },
   {
    "text": "Since then, your name has become a whispered ghost story in boardrooms, with corporations paying fortunes just to secure their nodes against you."
   }
  ]
 },
 "gift": "rare",
 "extraordinary": [
  "cybernetic augmentations (common): Full-body conversion, neural integration, and sensory enhancement.",
  "neural netrunning and hacking (common): Direct mental interface with global networks, lethal digital defense programs, and mind-rewriting."
 ],
 "ladders": [
  {
   "id": "netrunner-rank",
   "name": "Netrunner Ranks",
   "rungs": [
    "0: Script Kid (tier 2, lives 0)",
    "1: Code Jockey (tier 4, lives 0)",
    "2: Sysop (tier 6, lives 0)",
    "3: Glitcher (tier 8, lives 0)",
    "4: Netrunner (tier 10, lives 0)",
    "5: Elite Runner (tier 12, lives 0)",
    "6: Legend of the Net (tier 14, lives 0)"
   ]
  }
 ],
 "peoples": [
  {
   "id": "human",
   "name": "Human",
   "lifespan_years": 90,
   "culture": "A highly stratified global urban population surviving under corporate hegemony."
  }
 ],
 "rules": [
  "Netrunning directly exposes a hacker's brain to lethal feedback loops and Black ICE programs.",
  "Pushing past human neural limits with excessive cybernetics risks mental collapse and cyberpsychosis.",
  "Megacorporations operate entirely above local law inside their designated physical and digital territories.",
  "Data and messages travel instantly across the global Net, making physical isolation the only true privacy.",
  "Cybernetic augmentations: real, and everywhere.",
  "Neural netrunning and hacking: real, and everywhere."
 ],
 "others": [
  "Cipher, 27, netrunner-rank rung 5, peak attribute 5",
  "Director Saito, 51, peak attribute 5",
  "Vance, 45, peak attribute 4"
 ],
 "people_in_the_world": 3,
 "years": {
  "age": 26.0,
  "lives_about": 90,
  "the_record_says_so": true,
  "old": false,
  "told_the_end_is_close": false
 }
}
```


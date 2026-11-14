## The draft (ca, teen)

> Sóc un pescador vell de Cadaqués, de setanta-vuit anys. Un matí trobo una sirena ferida a la xarxa.

_37.2 s, $0.089_

### What the draft's screen shows

La Sirena de Cadaqués
realisme màgic mariner
melangiós i de meravella
Les sirenes són reals, però viuen completament amagades dels humans per protegir-se.
Cadaqués, anys 1930: barques de pesca de fusta, ràdios de galena i camins de carro.
Pobles: Humans i Gent del Mar.
Confraria de Pescadors: El gremi local on es reuneixen els pescadors de Cadaqués per subhastar el peix i discutir el temps.
Destacament de la Guàrdia Civil: La parella de guàrdies encarregats d'evitar el contraband de tabac i alcohol des de França.
La febre de la sirena ferida: d'aquí a 4 dies.
La Sirena ferida: Una jove de la Gent del Mar, espantada i feble, amb una ferida profunda a la cua causada per una hèlix de motor.
Pere, 78, Humans.
Un pescador vell de pell colrada pel sol i mans endurides pel fil de pescar i el vent de tramuntana.
Sòci històric, Confraria de Pescadors.
Perícia: Navegació a vela llatina i Pesca tradicional. Nocions: Remeis casolans.
Dons: Llop de mar. Defectes: Xacres de la vellesa.
Pacient, observador i solitari.
Porta Navalla de butxaca marinera, Pipa de fusta de bruc i Xarxa de pesca de cànem. 15 pesetes.
Les sirenes són reals, però viuen completament amagades dels humans per protegir-se.
L'aigua de la mar profunda té propietats regeneradores per a les criatures de l'oceà.
El que es troba a la mar pertany a qui ho recull, excepte si posa en perill el poble.

### On record (the player never sees this)

```json
{
 "world": {
  "title": "La Sirena de Cadaqués",
  "genre": "realisme màgic mariner",
  "era": "Cadaqués, anys 1930: barques de pesca de fusta, ràdios de galena i camins de carro"
 },
 "character": {
  "id": "player",
  "name": "Pere",
  "aliases": [
   "Vell Pere",
   "Pere el de la barca"
  ],
  "prominence": "key",
  "description": "Un pescador vell de pell colrada pel sol i mans endurides pel fil de pescar i el vent de tramuntana.",
  "appearance": "Cabells blancs com l'escuma de la mar, esquena lleugerament corbada pels anys, armilla de llana blava gastada i pantalons de pana fosca tacats de sal.",
  "age": 78,
  "people_id": "humans",
  "location_id": "barca-player",
  "memberships": [
   {
    "faction_id": "confraria-pescadors",
    "rank": "Sòci històric",
    "loyalty": 70
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
   "speed": 2,
   "wits": 4,
   "knowledge": 4,
   "willpower": 5,
   "nerve": 4
  },
  "skills": [
   {
    "name": "Navegació a vela llatina",
    "level": "expert",
    "notes": "Coneixes cada corrent i cada roca de la costa de Cadaqués millor que el palmell de la teva mà."
   },
   {
    "name": "Pesca tradicional",
    "level": "expert",
    "notes": "Saps on trobar el millor peix segons la lluna i el vent."
   },
   {
    "name": "Remeis casolans",
    "level": "novice",
    "notes": "Coneixes algunes herbes del Cap de Creus que serveixen per curar talls o calmar el dolor."
   }
  ],
  "traits": [
   {
    "name": "Llop de mar",
    "kind": "gift",
    "description": "La mar no et fa por, i saps llegir els canvis de temps molt abans que arribi la tempesta."
   },
   {
    "name": "Xacres de la vellesa",
    "kind": "flaw",
    "description": "El fred i l'artritis et fan anar més lent del que voldries quan has de fer moviments ràpids."
   }
  ],
  "disposition": {
   "temperament": {
    "traits": [
     "pacient",
     "observador",
     "solitari"
    ],
    "values": [
     "el respecte a la mar",
     "la tranquil·litat"
    ],
    "loves": [
     "el soroll de les ones contra la fusta",
     "la pipa del vespre"
    ],
    "fears": [
     "haver de deixar de navegar",
     "que es perdi la vida marinera d'abans"
    ],
    "wants": [
     "Curar la sirena ferida"
    ]
   }
  },
  "resources": {
   "items": [
    {
     "id": "navalla-de-butxaca-marinera",
     "name": "Navalla de butxaca marinera",
     "kind": "weapon",
     "description": "Una navalla vella de mànec de banya que fas servir per tallar cordes i xarxes."
    },
    {
     "id": "pipa-de-fusta-de-bruc",
     "name": "Pipa de fusta de bruc",
     "kind": "gear",
     "description": "La teva pipa de tota la vida, acompanyada d'una bosseta de tabac negre de contraban."
    },
    {
     "id": "xarxa-de-pesca-de-canem",
     "name": "Xarxa de pesca de cànem",
     "kind": "gear",
     "description": "La xarxa on ha quedat atrapada la sirena, ara una mica estripada pels seus moviments."
    }
   ],
   "money": 15,
   "currency": "pesetes",
   "title": "Pescador veterà",
   "rank": "Patró de llagut",
   "family_name": "Cabanelles",
   "connections": [
    {
     "name": "Mateu 'El Vell'",
     "kind": "trusts_them",
     "character_id": "mateu",
     "note": "El teu amic més antic, amb qui has compartit taverna i temporals."
    }
   ]
  },
  "axes": {
   "influence": 2,
   "knowledge": 3,
   "stealth": 2
  },
  "backstory": [
   {
    "text": "Has nascut, crescut i envellit a Cadaqués."
   },
   {
    "text": "Vares perdre la teva dona, la Maria, fa deu anys, i des de llavors vius sol a la teva caseta de la cala."
   },
   {
    "text": "Has vist com el poble canviava a poc a poc, però tu has seguit sortint a pescar cada matí de la teva vida."
   }
  ]
 },
 "gift": "none",
 "extraordinary": [
  "sirenes i criatures marines de llegenda (hidden): Criatures marines antigues capaces de viure sota l'aigua i amb un cant que pot calmar les aigües o confondre els homes."
 ],
 "peoples": [
  {
   "id": "humans",
   "name": "Humans",
   "lifespan_years": 80,
   "culture": "La gent de l'Empordà, tancada, treballadora i molt lligada als cicles de la tramuntana i la mar."
  },
  {
   "id": "gent-del-mar",
   "name": "Gent del Mar",
   "lifespan_years": 150,
   "gifts": [
    "Respiració aquàtica",
    "Resistència a la pressió"
   ],
   "culture": "Comunitats nòmades i secretes que viuen a les profunditats de la Mediterrània.",
   "relations": [
    "Eviten el contacte amb els humans des de fa segles."
   ]
  }
 ],
 "rules": [
  "Les sirenes són reals, però viuen completament amagades dels humans per protegir-se.",
  "L'aigua de la mar profunda té propietats regeneradores per a les criatures de l'oceà.",
  "El que es troba a la mar pertany a qui ho recull, excepte si posa en perill el poble."
 ],
 "others": [
  "La Sirena ferida, 22, peak attribute 5",
  "Mateu 'El Vell', 80, peak attribute 5",
  "Sergent Torres, 48, peak attribute 4"
 ],
 "people_in_the_world": 3,
 "years": {
  "age": 78.0,
  "lives_about": 80,
  "the_record_says_so": true,
  "old": true,
  "told_the_end_is_close": false
 }
}
```

## Turn 1 (opening), 6.2 s, $0.043

_From Day 1, dawn, 06:00 to Day 1, dawn, 06:00 (0 s). Pere is 78, alive._

La fusta vella del llagut 'Sardinal' cruix sota els teus peus mentre la claror de l'alba comença a pintar de lila el cel de la Mar d'Amunt. La llevantada d'ahir s'ha calmat, deixant només un balanceig suau i una olor espessa de sal i algues. Però el pes que has arrossegat a bord no s'assembla a cap captura dels teus setanta-vuit anys de mariner. Allà, a la popa de la barca, mig embolicada entre els nusos aspres de la teva xarxa de cànem, hi ha una sirena de debò. Les seves escates platejades brillen amb feblesa sota el cel grisenc, i la pell fina del seu tors de dona tremola de fred i por. Una ferida lletja, un tall profund causat per l'hèlix d'algun vaixell de motor que deu haver creuat de nit el Cap de Creus, li sagna lentament a la cua. Els seus ulls, grans i foscos com les profunditats on no arriba la llum del sol, et miren fixament, demanant un auxili que no pot demanar amb paraules. Saps molt bé que amagar una criatura de la mar és buscar-se la ruïna en aquest poble ple de tafaners, i la Guàrdia Civil del Sergent Torres aviat vigilarà el port. Però no pots deixar-la morir així.

**Suggestions:**
1. Aparcar les teves pors i parlar-li amb veu suau per calmar-la (thread)
2. Tallar la xarxa amb la navalla per alliberar-la amb cura (personal)
3. Netejar la ferida de la cua amb aigua del cubell (side)

**Issues:**
- rejected (character sirena: rung sirena-comuna): no ladder has that rung
- start_told (goal:goal-1): the story told it
- start_told (person:sergent-torres): the story told it
- start_told (thread:el-secret-mari): the story told it
- start_told (thread:esquivar-la-llei): the story told it

**Counted:** {"goals_open": 1}

## What the screens show (turn 1)

### On record (the player never sees this)

```json
{
 "world": {
  "title": "La Sirena de Cadaqués",
  "genre": "realisme màgic mariner",
  "era": "Cadaqués, anys 1930: barques de pesca de fusta, ràdios de galena i camins de carro"
 },
 "character": {
  "id": "player",
  "name": "Pere",
  "aliases": [
   "Vell Pere",
   "Pere el de la barca"
  ],
  "prominence": "key",
  "description": "Un pescador vell de pell colrada pel sol i mans endurides pel fil de pescar i el vent de tramuntana.",
  "appearance": "Cabells blancs com l'escuma de la mar, esquena lleugerament corbada pels anys, armilla de llana blava gastada i pantalons de pana fosca tacats de sal.",
  "age": 78,
  "people_id": "humans",
  "location_id": "barca-player",
  "memberships": [
   {
    "faction_id": "confraria-pescadors",
    "rank": "Sòci històric",
    "loyalty": 70
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
   "speed": 2,
   "wits": 4,
   "knowledge": 4,
   "willpower": 5,
   "nerve": 4
  },
  "skills": [
   {
    "name": "Navegació a vela llatina",
    "level": "expert",
    "notes": "Coneixes cada corrent i cada roca de la costa de Cadaqués millor que el palmell de la teva mà."
   },
   {
    "name": "Pesca tradicional",
    "level": "expert",
    "notes": "Saps on trobar el millor peix segons la lluna i el vent."
   },
   {
    "name": "Remeis casolans",
    "level": "novice",
    "notes": "Coneixes algunes herbes del Cap de Creus que serveixen per curar talls o calmar el dolor."
   }
  ],
  "traits": [
   {
    "name": "Llop de mar",
    "kind": "gift",
    "description": "La mar no et fa por, i saps llegir els canvis de temps molt abans que arribi la tempesta."
   },
   {
    "name": "Xacres de la vellesa",
    "kind": "flaw",
    "description": "El fred i l'artritis et fan anar més lent del que voldries quan has de fer moviments ràpids."
   }
  ],
  "disposition": {
   "temperament": {
    "traits": [
     "pacient",
     "observador",
     "solitari"
    ],
    "values": [
     "el respecte a la mar",
     "la tranquil·litat"
    ],
    "loves": [
     "el soroll de les ones contra la fusta",
     "la pipa del vespre"
    ],
    "fears": [
     "haver de deixar de navegar",
     "que es perdi la vida marinera d'abans"
    ],
    "wants": [
     "Curar la sirena ferida"
    ]
   }
  },
  "resources": {
   "items": [
    {
     "id": "navalla-de-butxaca-marinera",
     "name": "Navalla de butxaca marinera",
     "kind": "weapon",
     "description": "Una navalla vella de mànec de banya que fas servir per tallar cordes i xarxes."
    },
    {
     "id": "pipa-de-fusta-de-bruc",
     "name": "Pipa de fusta de bruc",
     "kind": "gear",
     "description": "La teva pipa de tota la vida, acompanyada d'una bosseta de tabac negre de contraban."
    },
    {
     "id": "xarxa-de-pesca-de-canem",
     "name": "Xarxa de pesca de cànem",
     "kind": "gear",
     "description": "La xarxa on ha quedat atrapada la sirena, ara una mica estripada pels seus moviments."
    }
   ],
   "money": 15,
   "currency": "pesetes",
   "title": "Pescador veterà",
   "rank": "Patró de llagut",
   "family_name": "Cabanelles",
   "connections": [
    {
     "name": "Mateu 'El Vell'",
     "kind": "trusts_them",
     "character_id": "mateu",
     "note": "El teu amic més antic, amb qui has compartit taverna i temporals."
    }
   ]
  },
  "axes": {
   "influence": 2,
   "knowledge": 3,
   "stealth": 2
  },
  "backstory": [
   {
    "text": "Has nascut, crescut i envellit a Cadaqués."
   },
   {
    "text": "Vares perdre la teva dona, la Maria, fa deu anys, i des de llavors vius sol a la teva caseta de la cala."
   },
   {
    "text": "Has vist com el poble canviava a poc a poc, però tu has seguit sortint a pescar cada matí de la teva vida."
   }
  ]
 },
 "gift": "none",
 "extraordinary": [
  "sirenes i criatures marines de llegenda (hidden): Criatures marines antigues capaces de viure sota l'aigua i amb un cant que pot calmar les aigües o confondre els homes."
 ],
 "peoples": [
  {
   "id": "humans",
   "name": "Humans",
   "lifespan_years": 80,
   "culture": "La gent de l'Empordà, tancada, treballadora i molt lligada als cicles de la tramuntana i la mar."
  },
  {
   "id": "gent-del-mar",
   "name": "Gent del Mar",
   "lifespan_years": 150,
   "gifts": [
    "Respiració aquàtica",
    "Resistència a la pressió"
   ],
   "culture": "Comunitats nòmades i secretes que viuen a les profunditats de la Mediterrània.",
   "relations": [
    "Eviten el contacte amb els humans des de fa segles."
   ]
  }
 ],
 "rules": [
  "Les sirenes són reals, però viuen completament amagades dels humans per protegir-se.",
  "L'aigua de la mar profunda té propietats regeneradores per a les criatures de l'oceà.",
  "El que es troba a la mar pertany a qui ho recull, excepte si posa en perill el poble."
 ],
 "others": [
  "La Sirena ferida, 22, peak attribute 5",
  "Mateu 'El Vell', 80, peak attribute 5",
  "Sergent Torres, 48, peak attribute 4"
 ],
 "people_in_the_world": 3,
 "years": {
  "age": 78.0,
  "lives_about": 80,
  "the_record_says_so": true,
  "old": true,
  "told_the_end_is_close": false
 },
 "waiting": [
  "world.clock_step 'La febre de la sirena ferida: La sirena respira amb dificultat i necessita aigua marina neta per netejar la ferida de la cua.' in 1.0 days",
  "world.tick 'The world moves on' in 1.0 days",
  "world.clock_step 'La vigilància del Sergent Torres: El sergent nota un moviment estrany a la teva barca al port.' in 1.5 days",
  "world.old_age 'Your years run short' in 8.5 years (stops the player)"
 ]
}
```


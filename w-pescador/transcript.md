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

## Turn 2 (action), 13.0 s, $0.055

> Tallo la xarxa amb la navalla, la tapo amb una lona i me l'emporto a casa d'amagat per curar-li la ferida.

_From Day 1, dawn, 06:00 to Day 1, morning, 07:32 (1.5 hours). Pere is 78, alive._

**Read and decided:**
- read as task, 'cut' on sirena, 120 s: Tallo la xarxa de cànem amb la navalla i cobreixo la sirena amb una lona per protegir-la de mirades indiscretes.
- read as travel, 'travel' on sirena, 5400 s: Me l'emporto cap a casa d'amagat per curar-li la ferida a la cua.
- Tallo la xarxa de cànem amb la navalla i cobreixo la sirena amb una lona per protegir-la de mirades indiscretes. [certain, success]: Nothing stands in the way.
- Me l'emporto cap a casa d'amagat per curar-li la ferida a la cua. [certain, success]: Navegació a vela llatina (expert), 4 dice, against a real effort, level 2: no throw, there is no real doubt.

Treus la navalla de banya de la butxaca, obres la fulla desgastada i comences a tallar, amb pols tremolós però segur, els nusos aspres de cànem que empresonen la criatura. Els ulls de la sirena segueixen cada moviment teu, plens d'un recel antic. Un cop lliure, agafes una lona de vela vella de sota la bancada de la barca i la cobreixes amb delicadesa, amagant les escates platejades de qualsevol mirada indiscreta de bon matí.

Carregues la criatura, sorprenentment lleugera però freda com el gel profund, i amures el 'Sardinal' aprofitant el vent suau que comença a bufar de xaloc. Governes el timó amb una sola mà, buscant els racons més ombrívols de la costa que tan bé coneixes. Arribes a la petita cala privada davant de la teva llar sense aixecar cap sospita. Amb l'esforç que et demanen els teus setanta-vuit anys, transportes la sirena embolicada en la lona fins a l'interior de la teva casa de pescador, on l'olor de fusta, fum de pipa i salitrosa ho impregna tot. La deixes suaument sobre la taula gran de fusta, on ella comença a respirar amb un xiulet feble.

**Suggestions:**
1. Buscar herbes i draps nets per mirar de tancar la ferida. (thread)
2. Anar a buscar en Mateu 'El Vell' per demanar-li consell discretament. (personal)
3. Encendre la llar de foc per escalfar l'habitació abans de fer res. (side)

**Issues:**
- start_told (person:mateu): the story told it

**Counted:** {"goals_open": 1}

## Turn 3 (action), 11.0 s, $0.038

> La cuido fins que està curada i la torno al mar. Després segueixo amb la meva vida de pescador: deixo passar els mesos, pescant cada matí.

_From Day 1, morning, 07:32 to Day 2, morning, 07:32 (1.0 days). Pere is 78, alive._

**Read and decided:**
- read as task, 'heal' on sirena, 86400 s: La cuido fins que està curada.
- read as travel, 'transport' on sirena, 2700 s: La torno al mar.
- read as time_skip, 'work', 7776000 s: Deixo passar els mesos, pescant cada matí.
- La cuido fins que està curada. [ruled_out, failure]: You have no herbes de la contrada on you.
- unplayed: ["La torno al mar.", "Deixo passar els mesos, pescant cada matí."]
- heading: L'endemà

Agafes ràpidament un drap net i aigua dolça per netejar la lletja ferida de la cua de la sirena, disposat a buscar les herbes de la contrada que tant et convenen per tancar el tall.

El teu intent de guarir-la topa immediatament amb la realitat de la teva vellesa i d'un rebost buit de remeis. En obrir el calaix on guardaves la farigola seca i l'oli de cop de tota la vida, trobes els pots buits, només amb pols i olor de ranci. Mentrestant, la cua platejada de la criatura batega feblement sobre la taula, deixant anar una mica més de sang sota la llum tènue del matí de Cadaqués. Sense les herbes adequades, saps que un tall així, fet pel ferro d'un motor, s'acabarà podrint amb el salnitre. A fora, el dia comença a moure's: el soroll de les primeres xarxes a la platja i el pas d'un carro pel carreró et recorden que la teva tranquil·litat és molt prima. Sents el xiulet feble del pit de la sirena, que et mira de reüll amb uns ulls foscos on el recel es barreja amb una freda resignació marinera.

**Suggestions:**
1. Sortir a buscar herbes curatives pels penya-segats del Cap de Creus. (thread)
2. Demanar ajuda al meu vell amic Mateu, arriscant el secret. (personal)
3. Buscar una mica d'alcohol fort al rebost per netejar la ferida. (side)

**Issues:**
- unknown_response (goal-1): not an open thread or lead

**Counted:** {"refused": 1, "goals_open": 1}

## Turn 4 (action), 10.2 s, $0.037

> Deixo passar dos anys més, pescant i anant cada vespre a la cala per si la torno a veure.

_From Day 2, morning, 07:32 to Day 153, evening, 21:54 (151.6 days). Pere is 78, alive._

**Read and decided:**
- read as time_skip, 'wait' on sirena, 63072000 s: Deixes passar dos anys, dedicant-te a pescar i a anar cada vespre a la cala amb l'esperança de tornar a veure la sirena.
- Deixes passar dos anys, dedicant-te a pescar i a anar cada vespre a la cala amb l'esperança de tornar a veure la sirena. [certain, success]: Nothing stands in the way.
- event: "An old friend in trouble"
- heading: Cinc mesos després

T'assegues a la cadira de boga, mirant el calaix buit, i penses en els dies que vindran, en les matinades de feina i en les nits que passaràs buscant la seva lluentor a la cala.

El temps s'escola com la sorra fina entre els dits. Cinc mesos passen ràpids sota la fressa de la tramuntana i el balanceig diari del 'Sardinal'. Cada matí surts a feinejar, i cada vespre, quan el sol es pon darrere el Pení, camines fins al racó de la cala amb els ulls posats en l'aigua fosca, somiant retrobar aquella mirada de mar profunda. Avui, la nit de tardor ja ha caigut sobre Cadaqués. Ets dins de casa, amb el caliu de la llar i la pipa encesa, quan sentis un truc fort i precipitat a la porta de fusta emblanquinada. Quan obres, et trobes la silueta de l'amic Mateu. Va amarat d'aigua, esbufegant, amb la cara pàl·lida i els ulls plens de por sota la gorra de llana.

**Suggestions:**
1. Fer entrar en Mateu de pressa i tancar de cop la porta. (thread)
2. Preguntar-li què ha passat abans de deixar-lo passar a dins. (thread)
3. Oferir-li un vas de conyac vell vora el caliu de la llar. (personal)

**Issues:**
- unknown_response (goal-1): not an open thread or lead
- rejected (character sirena: rung Humans): no ladder has that rung
- rejected (character mateu: rung Humans): no ladder has that rung

**Counted:** {"goals_open": 1}

## What the screens show (turn 4)

### The Character screen

```json
{
 "character": {
  "name": "Pere",
  "lines": [
   "Sense ferides",
   "15 pesetes",
   "Navalla de butxaca marinera",
   "Pipa de fusta de bruc",
   "Xarxa de pesca de cànem"
  ]
 },
 "sheet": {
  "about": [
   "Sòci històric, Confraria de Pescadors",
   "Pescador veterà",
   "78 anys"
  ],
  "description": "Un pescador vell de pell colrada pel sol i mans endurides pel fil de pescar i el vent de tramuntana.",
  "condition": {
   "health": "unhurt",
   "health_label": "Sense ferides"
  },
  "money_label": "15 pesetes",
  "items": [
   {
    "name": "Navalla de butxaca marinera",
    "kind": "weapon",
    "kind_label": "Arma",
    "description": "Una navalla vella de mànec de banya que fas servir per tallar cordes i xarxes.",
    "quantity": 1,
    "carried": true
   },
   {
    "name": "Pipa de fusta de bruc",
    "kind": "gear",
    "kind_label": "Equip",
    "description": "La teva pipa de tota la vida, acompanyada d'una bosseta de tabac negre de contraban.",
    "quantity": 1,
    "carried": true
   },
   {
    "name": "Xarxa de pesca de cànem",
    "kind": "gear",
    "kind_label": "Equip",
    "description": "La xarxa on ha quedat atrapada la sirena, ara una mica estripada pels seus moviments.",
    "quantity": 1,
    "carried": true
   }
  ],
  "skills": [
   {
    "name": "Navegació a vela llatina",
    "level": "expert",
    "level_label": "Perícia",
    "dice": 4,
    "notes": "Coneixes cada corrent i cada roca de la costa de Cadaqués millor que el palmell de la teva mà."
   },
   {
    "name": "Pesca tradicional",
    "level": "expert",
    "level_label": "Perícia",
    "dice": 4,
    "notes": "Saps on trobar el millor peix segons la lluna i el vent."
   },
   {
    "name": "Remeis casolans",
    "level": "novice",
    "level_label": "Nocions",
    "dice": 1,
    "notes": "Coneixes algunes herbes del Cap de Creus que serveixen per curar talls o calmar el dolor."
   }
  ],
  "traits": [
   {
    "name": "Llop de mar",
    "kind": "gift",
    "kind_label": "Do",
    "description": "La mar no et fa por, i saps llegir els canvis de temps molt abans que arribi la tempesta."
   },
   {
    "name": "Xacres de la vellesa",
    "kind": "flaw",
    "kind_label": "Defecte",
    "description": "El fred i l'artritis et fan anar més lent del que voldries quan has de fer moviments ràpids."
   }
  ],
  "temperament": [
   "pacient",
   "observador",
   "solitari"
  ]
 },
 "reputation": [
  {
   "name": "Confraria de Pescadors",
   "label": "Neutral"
  },
  {
   "name": "Destacament de la Guàrdia Civil",
   "label": "Neutral"
  }
 ],
 "clock": {
  "world_s": 13190061,
  "label": "Dia 153, vespre",
  "timeline_id": "main"
 },
 "since": [
  {
   "text": "Les sirenes han estat sempre part del cançoner i les històries velles dels mariners d'aquestes cales.",
   "ago_label": "fa 5 mesos"
  },
  {
   "text": "La Guàrdia Civil controla ferriament el port buscant contraban de tabac.",
   "ago_label": "fa 5 mesos"
  },
  {
   "text": "Cadaqués és un lloc on la gent té els ulls molt oberts i les llengües massa llargues si passa res fora del normal.",
   "ago_label": "fa 5 mesos"
  }
 ]
}
```

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
  "location_id": "casa-player",
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
  "age": 78.4,
  "lives_about": 80,
  "the_record_says_so": true,
  "old": true,
  "told_the_end_is_close": false
 },
 "waiting": [
  "world.tick 'The world moves on' in 10.4 hours",
  "director.plays_out 'An old friend in trouble: left alone' in 1.0 days",
  "world.old_age 'Your years run short' in 8.1 years (stops the player)"
 ]
}
```


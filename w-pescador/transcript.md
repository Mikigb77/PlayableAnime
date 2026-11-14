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


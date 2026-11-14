## The draft (ca, teen)

> Sóc un pescador vell de Cadaqués, de setanta-vuit anys. Un matí trobo una sirena ferida a la xarxa.

_54.0 s, $0.077: 2336 tokens of thinking, 4420 of answer, 1 tries_

### What the draft's screen shows

El Secret de la Mar de Cadaqués
realisme màgic mariner
melancòlic i misteriós
Sirenes i criatures de la mar: existeix, i gairebé ningú no ho sap.
Cadaqués, 1925: barques de pesca de fusta, llums de petroli i camins de carro.
Pobles: Humans i Sirenes.
Confraria de Pescadors de Cadaqués: El gremi local que regula la pesca i protegeix els interessos dels mariners del poble.
Guàrdia Civil: La força de la llei de l'Estat, poc acostumada als secrets de la gent de mar i molt estricta.
Joan, 78.
Un pescador vell, de mans calloses i mirada cansada però sàvia, que ha passat tota la seva vida lligat a la mar.
Pescador veterà, Confraria de Pescadors de Cadaqués.
Perícia: Pesca tradicional. Destresa: Navegació. Soltesa: Supervivència marina.
Dons: Cames de mar. Defectes: Fatiga dels anys.
Cautelós, compassiu i solitari.
Porta Ganivet de mariner i Pipa de fusta. 45 pessetes.
Les sirenes viuen en secret a les profunditats de la mar i eviten qualsevol contacte amb el món dels humans.
La sang i el cant d'una sirena tenen propietats curatives extraordinàries si es tracten amb respecte.
Sirenes i criatures de la mar: existeix, i gairebé ningú no ho sap.

### On record (the player never sees this)

```json
{
 "world": {
  "title": "El Secret de la Mar de Cadaqués",
  "genre": "realisme màgic mariner",
  "era": "Cadaqués, 1925: barques de pesca de fusta, llums de petroli i camins de carro."
 },
 "character": {
  "id": "player",
  "name": "Joan",
  "prominence": "key",
  "description": "Un pescador vell, de mans calloses i mirada cansada però sàvia, que ha passat tota la seva vida lligat a la mar.",
  "appearance": "Home gran d'estatura mitjana, cabells blancs esbullats, barba de pocs dies també blanca, rostre profundament arrugat pel sol i el vent marí. Vesteix un jersei de llana gruixuda de color blau fosc i uns pantalons de treball gastats.",
  "age": 78,
  "location_id": "mar-cadaques",
  "memberships": [
   {
    "faction_id": "confraria-cadaques",
    "rank": "pescador veterà"
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
   "willpower": 4,
   "nerve": 4
  },
  "skills": [
   {
    "name": "Pesca tradicional",
    "level": "expert",
    "notes": "Coneixes els millors llocs per pescar i com llançar la xarxa fins i tot amb mala mar."
   },
   {
    "name": "Navegació",
    "level": "skilled",
    "notes": "Saps governar la teva petita barca de fusta sota qualsevol tempesta."
   },
   {
    "name": "Supervivència marina",
    "notes": "Saps com curar petites ferides de peix i sobreviure al fred."
   }
  ],
  "traits": [
   {
    "name": "Cames de mar",
    "kind": "gift",
    "description": "Tens un equilibri perfecte a sobre de qualsevol embarcació, sense importar com de brava estigui la mar."
   },
   {
    "name": "Fatiga dels anys",
    "kind": "flaw",
    "description": "El teu cos de setanta-vuit anys es cansa ràpidament sota esforços físics intensos."
   }
  ],
  "disposition": {
   "temperament": {
    "traits": [
     "cautelós",
     "compassiu",
     "solitari"
    ],
    "values": [
     "el respecte a la mar",
     "la discreció",
     "la independència"
    ],
    "loves": [
     "el silenci de l'alba",
     "el tabac de pipa",
     "el soroll de les ones"
    ],
    "fears": [
     "morir lluny de la mar",
     "fer mal a un ésser indefens"
    ],
    "wants": [
     "Ajudar la sirena a curar-se i retornar-la sana i estàlvia a la mar."
    ]
   }
  },
  "resources": {
   "items": [
    {
     "id": "ganivet-de-mariner",
     "name": "Ganivet de mariner",
     "kind": "weapon",
     "description": "Un ganivet vell però ben esmolat, essencial per tallar cordes i netejar peix."
    },
    {
     "id": "pipa-de-fusta",
     "name": "Pipa de fusta",
     "kind": "gear",
     "description": "Una pipa de fusta fosca amb una mica de tabac sec."
    }
   ],
   "money": 45,
   "currency": "pessetes",
   "connections": [
    {
     "name": "Mateu",
     "character_id": "mateu",
     "note": "El teu company de pesca de tota la vida, encara que de vegades és massa xerraire."
    }
   ]
  },
  "backstory": [
   {
    "text": "Has viscut a Cadaqués des que vas néixer, treballant a la mar des dels deu anys."
   },
   {
    "text": "Vas perdre la teva dona fa molts anys i des d'aleshores vius sol a la teva petita cabana de la platja."
   },
   {
    "text": "Coneixes totes les llegendes sobre els secrets de la mar, però mai hauries pensat que una d'elles fos real."
   }
  ]
 },
 "gift": "none",
 "extraordinary": [
  "sirenes i criatures de la mar (hidden): La màgia de les sirenes pot calmar les tempestes i curar ferides, però també pot embruixar la ment dels humans."
 ],
 "peoples": [
  {
   "id": "humans",
   "name": "Humans",
   "lifespan_years": 80,
   "culture": "Gent de mar treballadora, supersticiosa i molt lligada a les tradicions locals de Cadaqués."
  },
  {
   "id": "sirenes-poble",
   "name": "Sirenes",
   "lifespan_years": 300,
   "culture": "Criatures antigues de la mar que es comuniquen amb cants i protegeixen els secrets de l'abisme."
  }
 ],
 "rules": [
  "Les sirenes viuen en secret a les profunditats de la mar i eviten qualsevol contacte amb el món dels humans.",
  "La sang i el cant d'una sirena tenen propietats curatives extraordinàries si es tracten amb respecte.",
  "Sirenes i criatures de la mar: existeix, i gairebé ningú no ho sap."
 ],
 "others": [
  "Marina, 25, peak attribute 5",
  "Mateu, 75, peak attribute 3"
 ],
 "people_in_the_world": 2,
 "years": {
  "age": 78.0,
  "lives_about": 80,
  "the_record_says_so": true,
  "old": true,
  "told_the_end_is_close": false
 }
}
```

## Turn 1 (opening), 10.5 s, $0.050

_From Day 1, dawn, 06:00 to Day 1, dawn, 06:00 (0 s). Joan is 78, alive._

La fredor de l'alba se't clava als ossos vells mentre estires la xarxa de cànem, pesant i xopa de salnitre. Però avui la mar de Cadaqués no et torna sards ni molls. Entre les cordes aspres, sota la llum tènue de la llanterna, batega una criatura que mai hauries cregut veure fora de les rondalles de taverna.

És una noia de pell blanca com l'escuma de les ones, amb uns llargs cabells daurats que s'enreden entre els ploms de la xarxa. En lloc de cames, una cua d'escates platejades batega feblement, brillants sota l'aigua de mar que inunda el fons de la barca. Està ferida; un fil de sang vermella i espessa li banya el costat esquerre. Ella et mira fixament amb uns ulls profunds com l'abisme, tremolant de fred i de terror pur, bloquejada entre les cordes. El silenci de la Mar Ampla només el trenca el xiuxiueig de l'aigua contra la fusta.

Tens el ganivet de mariner al cinturó i les mans et tremolen una mica per la fatiga dels anys i la sorpresa. Cadaqués és lluny, rere la boira de l'alba, però aviat sortiran altres barques.

**Suggestions:**
1. Tallar la xarxa amb el ganivet per alliberar-la (thread)
2. Parlar-li amb veu suau per intentar calmar el seu terror (personal)
3. Examinar la seva ferida abans de fer res més (side)

## What the screens show (turn 1)

### The Character screen

```json
{
 "character": {
  "name": "Joan",
  "lines": [
   "Sense ferides",
   "45 pessetes",
   "Ganivet de mariner",
   "Pipa de fusta"
  ]
 },
 "sheet": {
  "about": [
   "Pescador veterà, Confraria de Pescadors de Cadaqués",
   "78 anys"
  ],
  "description": "Un pescador vell, de mans calloses i mirada cansada però sàvia, que ha passat tota la seva vida lligat a la mar.",
  "condition": {
   "health": "unhurt",
   "health_label": "Sense ferides"
  },
  "money_label": "45 pessetes",
  "items": [
   {
    "name": "Ganivet de mariner",
    "kind": "weapon",
    "kind_label": "Arma",
    "description": "Un ganivet vell però ben esmolat, essencial per tallar cordes i netejar peix.",
    "quantity": 1,
    "carried": true
   },
   {
    "name": "Pipa de fusta",
    "kind": "gear",
    "kind_label": "Equip",
    "description": "Una pipa de fusta fosca amb una mica de tabac sec.",
    "quantity": 1,
    "carried": true
   }
  ],
  "skills": [
   {
    "name": "Pesca tradicional",
    "level": "expert",
    "level_label": "Perícia",
    "dice": 4,
    "notes": "Coneixes els millors llocs per pescar i com llançar la xarxa fins i tot amb mala mar."
   },
   {
    "name": "Navegació",
    "level": "skilled",
    "level_label": "Destresa",
    "dice": 3,
    "notes": "Saps governar la teva petita barca de fusta sota qualsevol tempesta."
   },
   {
    "name": "Supervivència marina",
    "level": "fair",
    "level_label": "Soltesa",
    "dice": 2,
    "notes": "Saps com curar petites ferides de peix i sobreviure al fred."
   }
  ],
  "traits": [
   {
    "name": "Cames de mar",
    "kind": "gift",
    "kind_label": "Do",
    "description": "Tens un equilibri perfecte a sobre de qualsevol embarcació, sense importar com de brava estigui la mar."
   },
   {
    "name": "Fatiga dels anys",
    "kind": "flaw",
    "kind_label": "Defecte",
    "description": "El teu cos de setanta-vuit anys es cansa ràpidament sota esforços físics intensos."
   }
  ],
  "temperament": [
   "cautelós",
   "compassiu",
   "solitari"
  ]
 },
 "reputation": [
  {
   "name": "Confraria de Pescadors de Cadaqués",
   "label": "Neutral"
  },
  {
   "name": "Guàrdia Civil",
   "label": "Neutral"
  }
 ],
 "clock": {
  "world_s": 0,
  "label": "Dia 1, alba",
  "timeline_id": "main"
 },
 "since": [
  {
   "text": "Si algú descobreix la sirena, la seva vida correrà un perill immens.",
   "ago_label": "fa un moment"
  },
  {
   "text": "La gent del poble no creu en sirenes, les consideren només contes per a nens o dimonis de la mar.",
   "ago_label": "fa un moment"
  },
  {
   "text": "Ets un pescador vell que coneix cada racó d'aquesta mar.",
   "ago_label": "fa un moment"
  }
 ]
}
```

### Memory

```json
{
 "character": {
  "name": "Joan",
  "lines": [
   "Un pescador vell, de mans calloses i mirada cansada però sàvia, que ha passat tota la seva vida lligat a la mar."
  ]
 },
 "places": [
  {
   "id": "cadaques",
   "name": "Cadaqués",
   "lines": [
    "Village",
    "Un aïllat i bell poble de pescadors de cases blanques, encerclat per les muntanyes i la mar.",
    "Encara no hi has estat."
   ]
  },
  {
   "id": "casa-joan",
   "name": "Casa d'en Joan",
   "lines": [
    "Building",
    "Una casa petita i humil vora la platja, plena de xarxes velles, olor de sal i records d'una vida a la mar.",
    "Encara no hi has estat."
   ]
  },
  {
   "id": "mar-cadaques",
   "name": "La Mar Ampla",
   "lines": [
    "Wilds",
    "Les aigües profundes i blaves del Cap de Creus, on la tramuntana bufa amb força."
   ]
  },
  {
   "id": "portlligat",
   "name": "Portlligat",
   "lines": [
    "Wilds",
    "Una cala tranquil·la i arrecerada, ideal per amagar coses lluny de les mirades curioses del poble.",
    "Encara no hi has estat."
   ]
  }
 ],
 "factions": [
  {
   "id": "confraria-cadaques",
   "name": "Confraria de Pescadors de Cadaqués",
   "lines": [
    "Sect",
    "El gremi local que regula la pesca i protegeix els interessos dels mariners del poble."
   ],
   "esteem": "neutral",
   "dread": "none",
   "standing_label": "Neutral"
  },
  {
   "id": "guardia-civil",
   "name": "Guàrdia Civil",
   "lines": [
    "Court",
    "La força de la llei de l'Estat, poc acostumada als secrets de la gent de mar i molt estricta."
   ],
   "esteem": "neutral",
   "dread": "none",
   "standing_label": "Neutral"
  }
 ],
 "threads": [
  {
   "id": "salvar-la",
   "title": "Salvar la sirena ferida",
   "status": "open"
  }
 ]
}
```


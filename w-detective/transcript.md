## The draft (es, teen)

> Soy una detective brillante en el Madrid de 1920. Nadie me toma en serio por ser mujer, pero resuelvo los casos que la policía no puede.

_28.6 s, $0.073_

### What the draft's screen shows

Sombras sobre Madrid
grounded crime
noir
No existen los milagros ni los fenómenos mágicos; cada crimen tiene una resolución puramente lógica y terrenal.
Madrid, 1920: tranvías, automóviles de época, periódicos impresos y teléfonos de manivela.
Pueblos: Humanos.
Cuerpo de Policía de Madrid: La fuerza del orden pública, sobrecargada de trabajo y reacia a aceptar la ayuda de civiles, especialmente de mujeres.
Elena Valenzuela, 27.
Una joven de mirada penetrante, postura impecable y un aire de absoluta seguridad que desconcierta a los hombres de ley.
Investigadora Independiente.
Pericia: Investigación y Deducción. Destreza: Sigilo y Discreción. Nociones: Ganzúa y Cerrajería.
Facilidad: Intuición observadora (Cualquier intento de detectar mentiras o inconsistencias en los testimonios de los sospechosos).
Dones: Mente Analítica. Defectos: Ignorada por la Ley.
Brillante, observadora y tenaz.
Sin poderes, porque en este mundo no existen.
Lleva Lupa de precisión, Cuaderno de notas y estilográfica y Juego de ganzúas finas. 120 pesetas.
No existen los milagros ni los fenómenos mágicos; cada crimen tiene una resolución puramente lógica y terrenal.
La sociedad de 1920 no acepta de buen grado que una mujer ejerza tareas de investigación, lo que dificultará que consigas información por vías oficiales.

### On record (the player never sees this)

```json
{
 "world": {
  "title": "Sombras sobre Madrid",
  "genre": "grounded crime",
  "era": "Madrid, 1920: tranvías, automóviles de época, periódicos impresos y teléfonos de manivela."
 },
 "character": {
  "id": "player",
  "name": "Elena Valenzuela",
  "aliases": [
   "La Detective de la Sombra"
  ],
  "prominence": "key",
  "description": "Una joven de mirada penetrante, postura impecable y un aire de absoluta seguridad que desconcierta a los hombres de ley.",
  "appearance": "Cabello oscuro recogido en un moño elegante y práctico, ojos oscuros y expresivos. Viste un traje de chaqueta de tweed de corte sobrio y calza zapatos cómodos pero refinados.",
  "age": 27,
  "location_id": "oficina-detective",
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
   "wits": 5,
   "knowledge": 4,
   "willpower": 4,
   "charm": 4,
   "nerve": 4,
   "bearing": 4
  },
  "skills": [
   {
    "name": "Investigación",
    "level": "expert",
    "notes": "Tu capacidad para analizar escenas del crimen e identificar pistas sutiles es inigualable."
   },
   {
    "name": "Deducción",
    "level": "expert",
    "notes": "Hilvanas datos inconexos para reconstruir los hechos con precisión quirúrgica."
   },
   {
    "name": "Sigilo y Discreción",
    "level": "skilled",
    "notes": "Sabes moverte sin llamar la atención en lugares donde tu presencia no es bienvenida."
   },
   {
    "name": "Ganzúa y Cerrajería",
    "level": "novice",
    "notes": "Adquiriste nociones básicas para abrir cerraduras sencillas cuando las puertas se te cierran."
   }
  ],
  "traits": [
   {
    "name": "Mente Analítica",
    "kind": "gift",
    "description": "Los detalles que otros pasan por alto debido a la prisa o al prejuicio se revelan ante ti con total claridad."
   },
   {
    "name": "Ignorada por la Ley",
    "kind": "flaw",
    "description": "Debido a las convenciones de tu época, los agentes de la ley rara vez te escucharán o cooperarán contigo voluntariamente."
   }
  ],
  "talents": [
   {
    "id": "intuicion-observadora",
    "name": "Intuición observadora",
    "covers": "Cualquier intento de detectar mentiras o inconsistencias en los testimonios de los sospechosos."
   }
  ],
  "disposition": {
   "temperament": {
    "traits": [
     "brillante",
     "observadora",
     "tenaz"
    ],
    "values": [
     "la justicia pura",
     "la verdad lógica"
    ],
    "loves": [
     "un buen misterio no resuelto",
     "el olor a café por la mañana"
    ],
    "fears": [
     "fallarle a alguien que depende de ti",
     "quedar atrapada en el anonimato impuesto por tu época"
    ]
   }
  },
  "resources": {
   "items": [
    {
     "id": "lupa-de-precision",
     "name": "Lupa de precisión",
     "kind": "gear",
     "description": "Una pequeña lupa con montura de plata que perteneció a tu abuelo."
    },
    {
     "id": "cuaderno-de-notas-y-estilografica",
     "name": "Cuaderno de notas y estilográfica",
     "kind": "gear",
     "description": "Donde registras minuciosamente cada pista y sospechoso."
    },
    {
     "id": "juego-de-ganzuas-finas",
     "name": "Juego de ganzúas finas",
     "kind": "gear",
     "description": "Herramientas delgadas de metal ocultas en el forro de tu abrigo."
    }
   ],
   "money": 120,
   "currency": "pesetas",
   "title": "Detective Privada (no oficial)",
   "rank": "Investigadora Independiente",
   "connections": [
    {
     "name": "Carlos Sanz",
     "kind": "ally",
     "character_id": "carlos-sanz",
     "note": "Tu contacto en la prensa que te proporciona pistas de primera mano."
    }
   ]
  },
  "axes": {
   "influence": 2,
   "wealth": 2,
   "knowledge": 4,
   "stealth": 3
  },
  "backstory": [
   {
    "text": "Hija de un reputado médico forense, creciste rodeada de manuales de criminología y debates científicos."
   },
   {
    "text": "Tras la muerte de tu padre, decidiste utilizar tus conocimientos para resolver aquellos casos que la rígida estructura policial madrileña prefiere despachar con prisas."
   },
   {
    "text": "Has abierto un modesto despacho en la calle Alcalá, camuflado como una oficina de traducciones para evitar miradas indiscretas."
   }
  ]
 },
 "gift": "none",
 "extraordinary": [
  "magia o cualquier elemento sobrenatural (none): No existe ningún tipo de magia ni fuerza sobrenatural en este mundo."
 ],
 "peoples": [
  {
   "id": "humanos",
   "name": "Humanos",
   "lifespan_years": 80,
   "culture": "La sociedad madrileña de los años veinte, dividida entre la aristocracia conservadora y las clases populares en plena ebullición social."
  }
 ],
 "rules": [
  "No existen los milagros ni los fenómenos mágicos; cada crimen tiene una resolución puramente lógica y terrenal.",
  "La sociedad de 1920 no acepta de buen grado que una mujer ejerza tareas de investigación, lo que dificultará que consigas información por vías oficiales."
 ],
 "others": [
  "Carlos Sanz, 24, peak attribute 4",
  "Inspector Julián Valdez, 48, peak attribute 4"
 ],
 "people_in_the_world": 2,
 "years": {
  "age": 27.0,
  "lives_about": 80,
  "the_record_says_so": true,
  "old": false,
  "told_the_end_is_close": false
 }
}
```


"""The starter premises in Spanish (S10): what Discover shows a player whose app is in Spanish.

Keyed by the starter's id in `graph.drafting.catalog`. Only the words the player reads are here:
each premise, and below them the words of its genre's template, which a Spanish story is drafted
with (`TEMPLATE_SPANISH`). A test checks that every starter has its Spanish, so a new starter
needs an entry here too (Spanish from Spain, with "tú").
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PremiseText:
    """The words of a starter premise in one language."""

    title: str
    genre: str
    tagline: str
    premise: str


SPANISH: dict[str, PremiseText] = {
    "outer-disciple": PremiseText(
        title="El último discípulo externo",
        genre="Cultivo",
        tagline="El discípulo más débil de la secta, a dos días del torneo de clasificación.",
        premise=(
            "Eres el discípulo externo más débil de la Secta de la Nube Celeste, atascado en la "
            "tercera etapa de Condensación de Qi mientras todos a tu alrededor avanzan. El torneo "
            "de clasificación empieza dentro de dos días, y los discípulos que queden últimos "
            "serán expulsados de la montaña para siempre."
        ),
    ),
    "ashen-squire": PremiseText(
        title="El escudero de la Corona Cenicienta",
        genre="Caballeros y aura",
        tagline="Nueve días para la prueba de caballería, sin aura y con tu maestro muerto.",
        premise=(
            "En el reino de Valdmark, los caballeros se clasifican por el aura que son capaces de "
            "invocar: escudero, caballero, maestro del aura, santo de la espada. Tú eres un "
            "escudero que nunca ha invocado ni una chispa. La prueba de caballería es dentro de "
            "nueve días, y esta mañana han encontrado a tu maestro muerto en los establos, con la "
            "espada todavía envainada."
        ),
    ),
    "beast-tide": PremiseText(
        title="Cuando llegue la marea de bestias",
        genre="Razas y monstruos",
        tagline="Cuatro pueblos tras una misma muralla, y la marea de bestias se adelanta.",
        premise=(
            "Elfos, enanos, hombres bestia y humanos comparten Atalaya Gris, una ciudad fronteriza "
            "amurallada, y ninguno se fía de los demás. Cada diez años la marea de bestias brota "
            "del Bosque Hondo, y los exploradores dicen que esta vez llega antes de tiempo. Eres "
            "un cazador de monstruos semielfo que debe al gremio enano más de lo que puede pagar."
        ),
    ),
    "three-heartbeats": PremiseText(
        title="Tres latidos",
        genre="Reencarnación",
        tagline="Renaces en un mundo de sectas, con el poder de detener el tiempo.",
        premise=(
            "Moriste en nuestro mundo y despertaste como un discípulo externo de dieciséis años "
            "de la Secta de la Luna Caída, con todos los recuerdos de tu vida anterior y un poder "
            "que nadie más tiene: puedes detener el tiempo durante tres latidos. El chico en cuyo "
            "cuerpo despertaste tenía enemigos, y uno de ellos ya te espera junto al pozo."
        ),
    ),
    "demon-lord-accountant": PremiseText(
        title="El contable del Señor Demonio",
        genre="Reencarnación",
        tagline="Renaces sin dotes de combate y te contratan para salvar un ejército oscuro en "
        "quiebra.",
        premise=(
            "Renaciste en un mundo de fantasía sin ninguna dote de combate, solo con un talento "
            "asombroso para los números. El ejército del Señor Demonio está en quiebra, y su "
            "temible señor acaba de contratarte para cuadrar las cuentas antes de que lleguen los "
            "héroes."
        ),
    ),
    "sword-tomb": PremiseText(
        title="El guardián de la Tumba de las Espadas",
        genre="Cultivo",
        tagline="Un sirviente sin qi, a tres días de la Elección de la Espada.",
        premise=(
            "Barres la Tumba de las Espadas de la Secta del Filo Celestial, donde yacen enterradas "
            "diez mil espadas de maestros muertos, y nunca has logrado reunir ni una hebra de qi. "
            "Anoche una de esas espadas pronunció tu nombre. Dentro de tres días los discípulos "
            "entrarán en la tumba para la Elección de la Espada, y la espada dice que no elegirá a "
            "nadie más que a ti."
        ),
    ),
    "river-saint": PremiseText(
        title="El santo junto al río",
        genre="Caballeros y aura",
        tagline="Un santo de la espada enemigo cruzó la frontera solo y preguntó por ti.",
        premise=(
            "Eres un caballero que apenas logra invocar el aura, al mando de un fuerte fronterizo "
            "de once soldados en el límite del reino de Aldreth. Esta mañana, un santo de la "
            "espada del Imperio de Varn cruzó solo el río helado y se sentó en la nieve ante tu "
            "puerta. Pregunta por ti por tu nombre, y dice que esperará tres días."
        ),
    ),
    "ninth-floor": PremiseText(
        title="Abandonado en el noveno piso",
        genre="Razas y monstruos",
        tagline="Te dieron por muerto en la Aguja, junto a un huevo de dragón que empieza a "
        "romperse.",
        premise=(
            "La Aguja surgió del desierto hace un año, y aventureros de todas las razas suben sus "
            "pisos llenos de monstruos en busca de tesoros. Tu propio grupo te dio por muerto en "
            "el noveno piso. Despertaste en una cámara oculta junto a un huevo de dragón que ha "
            "empezado a agrietarse, y oyes a tu antiguo grupo volver a por él."
        ),
    ),
    "seven-day-villainess": PremiseText(
        title="A la villana le quedan siete días",
        genre="Reencarnación",
        tagline="Renaces como la villana de una novela, una semana antes de su caída.",
        premise=(
            "Moriste en nuestro mundo y despertaste como la villana de una novela romántica que "
            "leíste una vez, la hija de un duque prometida al príncipe heredero. Dentro de siete "
            "días, en el baile de primavera, él romperá el compromiso delante de todos, y en el "
            "libro ella es desterrada esa misma noche. Recuerdas cómo sigue la historia, y la "
            "heroína ya te mira de una forma extraña."
        ),
    ),
    "naples-vendetta": PremiseText(
        title="La sucesión de los Esposito",
        genre="Crimen realista",
        tagline="Nápoles, 1974. Alguien de dentro de la familia mató a tu padre.",
        premise=(
            "Nápoles, 1974. Eres el hijo del jefe de la familia Esposito, al que mataron a tiros "
            "hace una semana a la puerta de su propio club. Estás seguro de que el asesino es "
            "alguien de dentro de la familia, y el consejo familiar nombrará al próximo jefe "
            "dentro de diez días."
        ),
    ),
    "kestrel-debt": PremiseText(
        title="La deuda del Cernícalo",
        genre="Ciencia ficción",
        tagline="Treinta días para pagar, y en la bodega una caja por la que vale la pena matar.",
        premise=(
            "Capitaneas el Cernícalo, un carguero destartalado con cuatro tripulantes y una deuda "
            "con el Sindicato Halloran que vence dentro de treinta días. El trabajo que debía "
            "saldarla te dejó una caja sellada en la bodega, y tres facciones distintas acaban de "
            "ofrecerte comprarla, o quitártela."
        ),
    ),
    "night-shift": PremiseText(
        title="Turno de noche",
        genre="Lo sobrenatural oculto",
        tagline="Lisboa, hoy. El muerto de tu ambulancia acaba de incorporarse.",
        premise=(
            "Lisboa, hoy. Conduces en el turno de noche del servicio de ambulancias de la ciudad, "
            "y hace una hora el muerto que llevabas detrás se incorporó, te dio las gracias y se "
            "marchó hacia la oscuridad. Desde entonces, gente que no se refleja en los espejos ha "
            "empezado a preguntar por ti."
        ),
    ),
    "hollowmere": PremiseText(
        title="Último examen en Hollowmere",
        genre="Fantasía de academia",
        tagline="Suspende el examen final y tus recuerdos saldrán a subasta.",
        premise=(
            "Eres un estudiante becado en Hollowmere, una academia de magia en una isla del cielo "
            "donde a quien suspende el examen final le subastan los recuerdos. El examen empieza "
            "dentro de siete días, y tu magia sigue sin responderte."
        ),
    ),
    "drowned-capital": PremiseText(
        title="El ronin de la capital ahogada",
        genre="Drama de samuráis",
        tagline="Los clanes luchan por los tejados de una ciudad que se tragó el mar.",
        premise=(
            "La antigua capital se hundió bajo el mar hace un siglo, y sus clanes aún luchan por "
            "los tejados que siguen asomando sobre las olas. Eres un espadachín sin señor que "
            "acaba de despertar con el sello roto del heredero de un clan en la mano."
        ),
    ),
    "dead-god-courier": PremiseText(
        title="Mensajero de un dios muerto",
        genre="Fantasía urbana de neón",
        tagline="El dios murió ayer. El paquete de tu bolsa va a su nombre.",
        premise=(
            "En Lumen, una ciudad portuaria, a los dioses se los adora como a ídolos del pop, y "
            "uno de ellos murió ayer. Eres un mensajero del turno de noche, y el paquete que "
            "llevas en la bolsa va dirigido a ese dios."
        ),
    ),
    "mask-maker": PremiseText(
        title="El mascarero de Venecia",
        genre="Misterio realista",
        tagline="Venecia, carnaval de 1750. Un asesino llevaba la máscara que hiciste tú.",
        premise=(
            "Venecia, carnaval de 1750. Haces máscaras para la nobleza, y hace tres noches un "
            "desconocido te pagó en oro una máscara con la cara de un senador, cicatriz incluida. "
            "Esta mañana han encontrado al senador muerto en un canal, y la guardia tiene tu "
            "máscara. Nombrarán al asesino antes de que acabe el carnaval, dentro de cinco días, "
            "y ahora mismo el asesino eres tú."
        ),
    ),
    "war-frame": PremiseText(
        title="El armazón que te eligió",
        genre="Mecha",
        tagline="El armazón de guerra más viejo del hangar despertó y se vinculó a su mecánico.",
        premise=(
            "En Halcyon, una ciudad fortaleza, gigantescos armazones de guerra contienen al "
            "enjambre, y cada uno se vincula de por vida a un único piloto. Eres un mecánico "
            "novato, y anoche el armazón más viejo del hangar, callado desde hace cuarenta años, "
            "se vinculó a ti en lugar de al heredero del comandante. La próxima oleada del "
            "enjambre llega a las murallas dentro de cinco días."
        ),
    ),
    "ashgrove": PremiseText(
        title="Trece noches en Ashgrove",
        genre="Terror gótico",
        tagline="Duerme trece noches en la mansión para heredarla. Algo sabe tu nombre.",
        premise=(
            "Inglaterra, 1893. Has heredado Ashgrove, una mansión en los páramos del norte, de una "
            "tía abuela a la que nunca conociste. Su testamento dice que solo será tuya si duermes "
            "bajo su techo trece noches seguidas. La primera noche, alguien tras la puerta cerrada "
            "con llave del ala este te llamó por un apodo de tu infancia que nadie vivo debería "
            "conocer."
        ),
    ),
    "won-at-cards": PremiseText(
        title="Ganado a las cartas",
        genre="Fantasía pirata",
        tagline="Ganaste un barco pirata a las cartas. La armada asoma en el horizonte.",
        premise=(
            "Anoche, en una taberna de las Islas Rotas, ganaste a las cartas el barco pirata "
            "Gaviota Dorada. Ahora eres su capitán, con una tripulación que cree que hiciste "
            "trampa, un antiguo capitán que quiere recuperar su barco y una fragata de la armada "
            "en el horizonte. Doblada dentro de la escritura hay una carta náutica de una isla "
            "que ningún mapa ha nombrado jamás."
        ),
    ),
    "old-net": PremiseText(
        title="La chica de la red antigua",
        genre="Cyberpunk",
        tagline="Alguien vive dentro de un servidor muerto, y lo borran mañana a medianoche.",
        premise=(
            "Sable City, 2091. Buceas en la red antigua abandonada en busca de datos de desecho, "
            "para pagar la clínica que te instaló el conector neural. Hoy, en un servidor que "
            "nadie tocaba desde hace treinta años, has encontrado a alguien que vive allí: una "
            "chica que dice que la subieron a la red de niña. La corporación dueña del servidor "
            "lo borra mañana a medianoche."
        ),
    ),
    "last-lantern": PremiseText(
        title="Una habitación para el dragón",
        genre="Fantasía acogedora",
        tagline="Tu posada se hunde, y el único huésped es un dragón que paga con acertijos.",
        premise=(
            "Has heredado el Último Farol, una posada que se cae a pedazos donde se cruzan los "
            "caminos de tres reinos, junto con todas sus deudas. El recaudador de impuestos llega "
            "con la primera nevada, dentro de treinta días. Tu único huésped es un viejo dragón "
            "con forma humana que quiere una habitación para el invierno y paga con acertijos en "
            "lugar de monedas."
        ),
    ),
    "dry-basin": PremiseText(
        title="Dos días hasta el pozo",
        genre="Postapocalíptico",
        tagline="Una caravana muerta junto a barriles de agua llenos, a dos días del pozo.",
        premise=(
            "Treinta años después de las bombas, el agua es dinero. Guías una caravana de seis "
            "carros a través de la Cuenca seca, a dos días del próximo pozo. Esta mañana has "
            "encontrado la caravana que salió un día antes que vosotros: todos los viajeros "
            "muertos, todos los barriles de agua llenos e intactos, y un único rastro de botas "
            "que se aleja hacia el norte."
        ),
    ),
    "what-things-remember": PremiseText(
        title="Lo que recuerdan las cosas",
        genre="Superpoderes",
        tagline="Tu poder despertó hoy: lo que sostienes te muestra sus recuerdos.",
        premise=(
            "En Port Vesper, uno de cada cien adolescentes despierta con un poder a los dieciséis "
            "años. El tuyo llegó esta mañana: cualquier cosa que sostienes te muestra lo que "
            "recuerda. Lo primero que cogiste fue el móvil de tu hermana desaparecida, y lo que te "
            "mostró no es lo que le contaron a la policía."
        ),
    ),
}

# What a starter's template says in words the player reads (S10): its fixed rules, the kinds that
# exist and how far they reach, the ladder with its rungs, and the peoples, each by the English
# it stands for in `graph.drafting.catalog`. A test checks that every such text is here, so a new
# starter's template needs its Spanish too. They match the premises above: "Condensación de Qi",
# "maestro del aura", "hombres bestia", "armazón de guerra", "la Aguja".
TEMPLATE_SPANISH: dict[str, str] = {
    # Rules.
    "Qi cultivation is real, and the strong climb the realms.": (
        "El cultivo del qi es real, y los fuertes ascienden por los reinos."
    ),
    "Aura is real: trained knights draw it to strengthen body and blade.": (
        "El aura es real: los caballeros entrenados la invocan para fortalecer el cuerpo y la "
        "espada."
    ),
    "Humans, elves, dwarves and beastkin share this world, and monsters roam its wilds.": (
        "Humanos, elfos, enanos y hombres bestia comparten este mundo, y los monstruos recorren "
        "sus tierras salvajes."
    ),
    "Magic is real, and monsters carry it in their cores.": (
        "La magia es real, y los monstruos la llevan en sus núcleos."
    ),
    "A rare few can bend time, and almost nobody knows.": (
        "Unos pocos pueden doblegar el tiempo, y casi nadie lo sabe."
    ),
    "Magic and monsters are real, and so is the Demon Lord.": (
        "La magia y los monstruos son reales, y el Señor Demonio también."
    ),
    "A rare few ancient swords hold a spirit that can speak.": (
        "Unas pocas espadas antiguas guardan un espíritu capaz de hablar."
    ),
    "Humans, elves, dwarves and lizardfolk climb the Spire side by side, and monsters fill "
    "its floors.": (
        "Humanos, elfos, enanos y hombres lagarto suben la Aguja codo con codo, y los monstruos "
        "llenan sus pisos."
    ),
    "Magic is real, and the royal academy teaches it to nobles.": (
        "La magia es real, y la academia real se la enseña a los nobles."
    ),
    "Grounded: no magic and nothing supernatural, and that won't change.": (
        "Realista: sin magia ni nada sobrenatural, y eso no cambiará."
    ),
    "Nobody can do more than a real person could.": (
        "Nadie puede hacer más de lo que podría una persona real."
    ),
    "No magic and nothing supernatural: only science, and that won't change.": (
        "Sin magia ni nada sobrenatural: solo ciencia, y eso no cambiará."
    ),
    "Jump drives carry ships between stars in days, and no message travels faster than a ship.": (
        "Los motores de salto llevan las naves de una estrella a otra en días, y ningún mensaje "
        "viaja más rápido que una nave."
    ),
    "Vampires are real, and they hide among the living.": (
        "Los vampiros son reales, y se esconden entre los vivos."
    ),
    "Magic is real, and Hollowmere teaches it.": "La magia es real, y Hollowmere la enseña.",
    "Gods are real, worshipped like pop idols, and mortal.": (
        "Los dioses son reales, se los adora como a ídolos del pop, y son mortales."
    ),
    "Giant war-frames are real, and each one bonds with a single pilot for life.": (
        "Los gigantescos armazones de guerra son reales, y cada uno se vincula a un solo piloto "
        "de por vida."
    ),
    "The dead can linger, and almost nobody believes it.": (
        "Los muertos pueden quedarse entre los vivos, y casi nadie lo cree."
    ),
    "Magic is rare: a few storm-callers can speak to wind and wave.": (
        "La magia es rara: unos pocos invocadores de tormentas saben hablar al viento y a las olas."
    ),
    "Cybernetic implants are everywhere, and anyone with a neural jack can dive into the net.": (
        "Los implantes cibernéticos están por todas partes, y cualquiera con un conector neural "
        "puede bucear en la red."
    ),
    "Magic and dragons are real, though most folk never meet either.": (
        "La magia y los dragones son reales, aunque la mayoría de la gente nunca ve ni lo uno "
        "ni lo otro."
    ),
    "One person in a hundred gains a power at sixteen, and everyone knows it.": (
        "Una persona de cada cien despierta con un poder a los dieciséis años, y todo el mundo "
        "lo sabe."
    ),
    # Kinds, and how far they reach.
    "qi cultivation": "cultivo del qi",
    "Realms from Qi Condensation to Nascent Soul and beyond.": (
        "Reinos desde la Condensación de Qi hasta el Alma Naciente y más allá."
    ),
    "aura": "aura",
    "From squire to saint.": "De escudero a santo.",
    "magic": "magia",
    "powers over time": "poderes sobre el tiempo",
    "sword spirits": "espíritus de espada",
    "magic or anything supernatural": "magia o cualquier cosa sobrenatural",
    "vampires": "vampiros",
    "gods and their miracles": "dioses y sus milagros",
    "bonded war-frames": "armazones de guerra vinculados",
    "A frame stands as tall as a tower and answers only its pilot.": (
        "Un armazón es tan alto como una torre y solo responde a su piloto."
    ),
    "ghosts": "fantasmas",
    "sea magic": "magia del mar",
    "cybernetics": "cibernética",
    "Implants push a body past its limits, at a price.": (
        "Los implantes llevan el cuerpo más allá de sus límites, a un precio."
    ),
    "magic and dragons": "magia y dragones",
    "superpowers": "superpoderes",
    # Ladders and their rungs.
    "cultivation realms": "reinos de cultivo",
    "Qi Condensation": "Condensación de Qi",
    "Foundation Establishment": "Establecimiento de la Base",
    "Core Formation": "Formación del Núcleo",
    "Nascent Soul": "Alma Naciente",
    "Soul Transformation": "Transformación del Alma",
    "aura ranks": "rangos de aura",
    "Squire": "Escudero",
    "Knight": "Caballero",
    "Aura Master": "Maestro del Aura",
    "Sword Saint": "Santo de la Espada",
    "hunter ranks": "rangos de cazador",
    "Iron": "Hierro",
    "Bronze": "Bronce",
    "Silver": "Plata",
    "Gold": "Oro",
    "Mithril": "Mithril",
    "adventurer ranks": "rangos de aventurero",
    "D-rank": "Rango D",
    "C-rank": "Rango C",
    "B-rank": "Rango B",
    "A-rank": "Rango A",
    "S-rank": "Rango S",
    # Peoples.
    "humans": "humanos",
    "elves": "elfos",
    "dwarves": "enanos",
    "beastkin": "hombres bestia",
    "lizardfolk": "hombres lagarto",
}

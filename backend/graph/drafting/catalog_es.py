"""The starter premises in Spanish (S10): what Discover shows a player whose app is in Spanish.

Keyed by the starter's id in `graph.drafting.catalog`. Only the words the player reads are here;
the genre's template, its rules and its ladder stay with the starter. A test checks that every
starter has its Spanish, so a new starter needs an entry here too (Spanish from Spain, with "tú").
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
}

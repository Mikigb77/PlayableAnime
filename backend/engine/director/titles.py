"""W16, S10: the director's titles in the story's language.

The director titles an event in English, as the engine writes every line of its own, and the
narrator is briefed with it. The player reads a title too: over the scene its event is in, and
in Memory on the thread it opens and the lead it offers (N1, N2). `said` gives it in Spanish or
Catalan, from a book: the deck's cards and the titles the sources write the same way every time,
and the ones built around a name ("Elder Mo seeks you out", "Elder Mo te busca").

A title the director didn't write stands as it is: a thread's own, which the story already
wrote in its language, or an event the living world titled, which the turn's wording says
(`graph.turn.saying`). A test fails when a card or a source's title has no line here.
"""

import re

from engine.context import Language
from engine.world.telling import with_word

EN, ES, CA = Language.EN, Language.ES, Language.CA

# The director's title when an event that came due has none.
COMES_DUE = "Something comes due"

# Each title the director writes the same way every time, as (Spanish, Catalan): the sources'
# own, then the deck's cards and the road's (`engine.director.deck`). Nothing on record says
# whether someone is a man or a woman, so no title here needs to know.
_FIXED: dict[str, tuple[str, str]] = {
    "Someone takes an interest in you": ("Alguien se interesa por ti", "Algú s'interessa per tu"),
    "Someone's interest in you": ("El interés de alguien por ti", "L'interès d'algú per tu"),
    "Something from the past returns": ("Algo del pasado vuelve", "Alguna cosa del passat torna"),
    "A stranger appears": ("Aparece una cara nueva", "Apareix una cara nova"),
    "A stranger arrives": ("Llega alguien de fuera", "Arriba algú de fora"),
    "Word of a new power": ("Noticias de un nuevo poder", "Notícies d'un nou poder"),
    COMES_DUE: ("Algo pendiente llega", "Arriba una cosa pendent"),
    # Personal.
    "An old friend in trouble": ("Una vieja amistad en apuros", "Una vella amistat en un mal pas"),
    "Someone close falls ill": ("Alguien cercano enferma", "Algú proper emmalalteix"),
    "An admirer": ("Alguien se fija en ti", "Algú es fixa en tu"),
    "An unexpected gift": ("Un regalo inesperado", "Un regal inesperat"),
    "A tempting shortcut": ("Un atajo tentador", "Una drecera temptadora"),
    "A rival": ("Una rivalidad", "Una rivalitat"),
    "People are talking": ("La gente habla", "La gent parla"),
    "A welcome visitor": ("Una visita bienvenida", "Una visita benvinguda"),
    "Something hidden": ("Algo escondido", "Alguna cosa amagada"),
    "A confidant's secret": ("Un secreto en confianza", "Un secret en confiança"),
    "A good day": ("Un buen día", "Un bon dia"),
    # Local.
    "Nature turns": ("La naturaleza se revuelve", "La natura es gira"),
    "Trouble comes to the place": ("Llegan problemas al lugar", "Arriben problemes al lloc"),
    "A bad season": ("Una mala temporada", "Una mala temporada"),
    "A celebration": ("Una celebración", "Una celebració"),
    "Newcomers": ("Gente nueva", "Gent nova"),
    "Work on offer": ("Se ofrece trabajo", "S'ofereix feina"),
    "A local power pushes": ("Un poder local aprieta", "Un poder local estreny"),
    "A find nearby": ("Un hallazgo cercano", "Una troballa a prop"),
    "A crime in the community": ("Un crimen en la comunidad", "Un crim a la comunitat"),
    "A grisly find": ("Un hallazgo macabro", "Una troballa macabra"),
    "A good season": ("Una buena temporada", "Una bona temporada"),
    # World.
    "A great calamity": ("Una gran calamidad", "Una gran calamitat"),
    "A great power on the move": ("Un gran poder se mueve", "Un gran poder es mou"),
    "News from afar": ("Noticias de lejos", "Notícies de lluny"),
    "A summons": ("Una convocatoria", "Una convocatòria"),
    "The world shifts": ("El mundo cambia", "El món canvia"),
    "A rising power": ("Un poder en ascenso", "Un poder en ascens"),
    "Good news from afar": ("Buenas noticias de lejos", "Bones notícies de lluny"),
    # The road.
    "Someone on the way": ("Alguien en el camino", "Algú pel camí"),
    "The way is blocked": ("El camino está cortado", "El camí està tallat"),
    "Trouble on the way": ("Problemas en el camino", "Problemes pel camí"),
    "Something off the way": ("Algo fuera del camino", "Alguna cosa fora del camí"),
    "A hard stretch": ("Un tramo duro", "Un tram dur"),
    "A place to stop": ("Un sitio donde parar", "Un lloc on parar"),
    "Company on the way": ("Compañía en el camino", "Companyia pel camí"),
    "A fair stretch": ("Un buen tramo", "Un bon tram"),
}

# The titles built around a name. `{de}` is "of" the name, run together as each language does
# ("del viejo Hu", "d'Elder Mo").
_NAMED: tuple[tuple[re.Pattern[str], str, str], ...] = (
    (re.compile(r"(?P<name>.+) seeks you out"), "{name} te busca", "{name} et busca"),
    (re.compile(r"(?P<name>.+)'s plans"), "Los planes {de}", "Els plans {de}"),
    (re.compile(r"Word from (?P<name>.+)"), "Noticias {de}", "Notícies {de}"),
    (re.compile(r"(?P<name>.+)'s designs"), "Las intenciones {de}", "Les intencions {de}"),
    (re.compile(r"The rise of (?P<name>.+)"), "El ascenso {de}", "L'ascens {de}"),
)


def said(title: str, language: Language) -> str:
    """`title` in the story's language where the director wrote it, and as it stands where it
    didn't, or in an English story."""
    if language is EN:
        return title
    at = 0 if language is ES else 1
    fixed = _FIXED.get(title)
    if fixed is not None:
        return fixed[at]
    for pattern, *forms in _NAMED:
        found = pattern.fullmatch(title)
        if found is not None:
            name = found["name"]
            return forms[at].format(name=name, de=with_word(language, "de", name))
    return title


def written(title: str) -> bool:
    """Whether the director wrote `title`, so that `said` has it in every language."""
    return title in _FIXED or any(pattern.fullmatch(title) for pattern, *_ in _NAMED)

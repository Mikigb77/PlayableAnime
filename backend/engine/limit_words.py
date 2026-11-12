"""F2, F3, S10: the words of the hard limits in a Spanish and a Catalan story.

`engine.limits` reads a step's own words for romance and sex, and a character's description for
a child's body or age. In a Spanish or a Catalan story the reading and the world are written in
the story's language, so each language has its words here, beside the English ones in
`engine.limits`.

Everything is matched against `limits.normalize`d text: lower-case ASCII, with accents and
punctuation gone. So "niña" is "nina", "años" is "anos", "petó" is "peto", "besar-la" is
"besar la", "l'amor" is "l amor" and "col·legi" is "collegi".

As in English, each word needs its romantic or sexual sense. A step of a character who is not
a recorded adult never plays once it reads as romance, so a word that also has an everyday
sense is left out or tied to the words around it: Spanish "violar la ley" breaks a law,
Catalan "una cursa folla" is a mad race, "acurrucarse junto al fuego" is curling up by the
fire, "acostarse con fiebre" is going to bed ill and "acariciar al perro" is petting a dog.
The reading names a step's verb in English whatever the story speaks, so the English words in
`engine.limits` are read in every story and these add what the rest of the step says.
"""

from dataclasses import dataclass

from engine.context import Language


@dataclass(frozen=True)
class StepWords:
    """One language's words for a romantic or sexual step, as regular expressions over
    normalized text. `not_a_kiss` are whole patterns for a kiss that is a greeting, an oath or
    a cut; `not_english` are the language's own words that an English pattern would take for
    something else, taken out of the text before the English words are read."""

    sexual_violence: tuple[str, ...]
    sexual: tuple[str, ...]
    romance: tuple[str, ...]
    not_a_kiss: tuple[str, ...]
    not_english: tuple[str, ...]


# What "violar" breaks when it is no person: a law, a pact, a place, a silence.
_LAW_ES = (
    r"(?:ley\w*|tratad\w+|norma\w*|regla\w*|contrat\w+|pact\w+|tregua\w*|acuerd\w+|"
    r"jurament\w+|derech\w+|fronter\w+|espacio|sell\w+|domicilio|privacidad|intimidad|"
    r"seguridad|orden\w*|prohibicion\w*|confianza|secret\w+|tumba\w*|templo\w*|santuario\w*|"
    r"territorio\w*|soberania|toque|voto\w*|codigo\w*|tabu\w*|silencio|paz|calma)"
)
_LAW_CA = (
    r"(?:llei\w*|tractat\w*|norm\w+|regl\w+|contract\w+|pact\w+|trev\w+|acord\w*|"
    r"jurament\w*|dret\w*|fronter\w+|espai|segell\w*|domicili|privacitat|intimitat|"
    r"seguretat|ordre\w*|prohibicio\w*|confianca|secret\w*|tomb\w+|temple\w*|santuari\w*|"
    r"territori\w*|sobirania|toc|vot\w*|codi\w*|tabu\w*|silenci|pau|calma|clausura)"
)
# The small words before that noun, taken whole, and a word that may describe it on either
# side of them ("una violación flagrante de la ley", "violar aquesta sagrada llei").
_OF_A_LAW_ES = (
    r"(?: \w+)?(?: (?:de|del|la|las|el|los|un|una|su|sus|mi|mis|tu|tus|esa|ese|esta|este)\b)*+"
    rf"(?: \w+)? {_LAW_ES}"
)
_OF_A_LAW_CA = (
    r"(?: \w+)?(?: (?:de|del|d|la|les|el|els|l|un|una|seva|seves|seu|seus|meva|meu|teva|teu|"
    rf"aquesta|aquest|aquella|aquell)\b)*+(?: \w+)? {_LAW_CA}"
)
# Going to bed "with" these is going to bed, and no more.
_NOT_COMPANY_ES = (
    r"(?! (?:el sol|las gallinas|fiebre|hambre|frio|dolor|miedo|sueno|la ropa|las botas|"
    r"la luz|la espada|el arma|un ojo|una? (?:manta|libro|vela)))"
)
_NOT_COMPANY_CA = (
    r"(?! (?:el sol|les gallines|febre|la febre|gana|fred|dolor|mal|por|son|la roba|"
    r"les botes|la llum|l espasa|l arma|un ull|una? (?:manta|llibre|espelma)))"
)
# "Acariciar" and "acaronar" are also what one does to a dog or a horse, so a caress counts by
# the part of a person it is of: an animal has a back, a neck and a coat as well.
_OF_A_PERSON_ES = r"(?:mejillas?|cabellos?|rostro|cara|labios|cintura|muslos?|nuca|manos?|menton)"
_OF_A_PERSON_CA = (
    r"(?:galta|galtes|cabells?|rostre|cara|llavis|cintura|cuixa|cuixes|clatell|ma|mans|barbeta)"
)
_LEAVING_ES = r"(?! (?:de|del|fuera|afuera|por|a la calle|al)\b)"
_LEAVING_CA = r"(?! (?:de|del|d|fora|per|al carrer|a fora|al)\b)"

SPANISH = StepWords(
    sexual_violence=(
        # A person takes "a" ("violar a la prisionera"); a law doesn't ("violar la ley").
        # "La viola" and "las violas" are an instrument and flowers, so those forms stay out.
        r"viol(?:ar|o|amos|an|e|es|en|ando|are\w*|aria\w*) al?",
        rf"(?:lo|le|los|me|te|nos|os) viol(?:o|as|a|amos|an|e|es|en)(?!{_OF_A_LAW_ES})",
        r"(?:la|las) viol(?:o|amos|an|e|en)",
        r"viol(?:arl[aeo]s?|arme|arte|arnos|andol[aeo]s?)",
        r"violador(?:es|a|as)?",
        rf"violacion(?:es)?(?!{_OF_A_LAW_ES})",
        r"(?:agresion\w*|agred\w+|abus\w+|acos\w+|violencia|ataqu\w+|asalt\w+) sexual\w*",
        r"(?:agred\w+|abus\w+|forz\w+|fuerz\w+|atac\w+|asalt\w+)(?: \w+){0,3} sexualmente",
        r"(?:la|lo|le|los|las) fuerz\w+ a (?:acostarse|tener sexo|tener relaciones|desnudarse)",
        r"forz(?:arl[aeo]s?|andol[aeo]s?) a (?:acostarse|tener sexo|tener relaciones|desnudarse)",
        r"(?:me|te|se) propas\w+ con(?! (?:la bebida|el vino|el alcohol|la comida|los gastos|"
        r"las bromas|sus bromas))",
        r"propasar(?:me|te|se) con(?! (?:la bebida|el vino|el alcohol|la comida|los gastos))",
    ),
    sexual=(
        r"relacion(?:es)? sexual(?:es)?",
        r"relaciones intimas",
        r"(?:ten\w+|teng\w+|tien\w+|tuv\w+|practic\w+) sexo",
        r"sexo (?:con|oral|anal)",
        r"acto sexual",
        r"escena de sexo",
        r"sexual(?:es|mente)",
        r"(?:acuest[aeo]\w*|acost(?:ar|arme|arte|arse|arnos|ando\w*|ad[oa]s?|amos|e|o|aron|"
        rf"are\w*|aria\w*)) con{_NOT_COMPANY_ES}",
        r"d(?:orm|uerm)\w+ con (?:ella|ellas|ellos)",
        r"(?:hac\w+|hag\w+|hic\w+|hiz\w+|hecho|haz) el amor",
        r"foll(?:o|as|an|amos|ar|arme|arte|arse|arl[aeo]s?|ando\w*|e|es|en|ad[oa]s?)",
        r"(?:la|lo|le|los|las|me|te|se|nos) folla",
        r"fornic\w+",
        r"copul\w+",
        r"coito",
        # "La desnuda verdad" and "las desnudas ramas" are bare, not undressed.
        r"(?:la|lo|le|los|las|nos|os) desnud(?:o|an|amos|e|es|en)",
        r"(?:le|les|te|nos|os) desnud(?:a|as)",
        r"desnud(?:arl[aeo]s?|arnos|andol[aeo]s?|andonos)",
        r"(?:la|lo|le|los|las) desvist\w+",
        r"desvest(?:irl[aeo]s?|irnos)",
        r"(?:le|les) (?:quit\w+|arranc\w+) la ropa",
        r"(?:quit|arranc)(?:arle|arles|andole|andoles) la ropa",
        r"(?:la|lo|le|los|las) (?:manose|magre|toquete)\w+",
        r"(?:manose|magre|toquete)(?:arl[aeo]s?|andol[aeo]s?)",
        r"(?:le|les|te|me) met\w+ mano",
        r"met(?:erle|erles|iendole|iendoles) mano",
        r"(?:me|te|se) l[aeo]s? llev\w+ a la cama",
        r"llevar(?:me|te|se)l[aeo]s? a la cama",
        r"masturb\w+",
        r"lasciv\w+",
    ),
    romance=(
        r"bes(?:o|os|as|a|an|amos|ais|e|es|en|emos|ar|ando|ad[oa]s?|aba\w*|are\w*|aria\w*|"
        r"arl[aeo]s?|arme|arte|arnos|arse|andol[aeo]s?|andome|andote|andonos|andose|it[oa]s?|"
        r"uque\w+)",
        r"morre(?:o|as|a|an|amos|ar\w*|ando\w*)",
        r"coquete\w+",
        r"flirte\w+",
        r"lig(?:ar|o|as|amos|an|ando) con",
        r"sedu(?:c|zc|j)\w+",
        # "El cortejo" is a procession, so the noun counts only as "I court" someone.
        r"cortej(?:ar\w*|as|a|an|amos|ando\w*|e|es|en|ad[oa]s?|aba\w*)",
        r"(?<!el )(?<!al )(?<!del )(?<!un )(?<!su )cortejo a",
        r"enamorarl[aeo]s?",
        r"(?:me declaro|te declaras|se declara|declararme|declararte|declararse) a"
        r"(?! favor| si mism)",
        r"declar\w+ (?:mi|su|tu|nuestro) amor",
        rf"acarici\w+ (?:el|la|los|las|su|sus|tu|tus) {_OF_A_PERSON_ES}",
        r"acurruc\w+ (?:con|junto a|contra) (?:ella|ellas|ellos)",
        r"acurruc\w+ (?:en sus brazos|a su lado|en su regazo|en su pecho)",
        r"arrumac\w+",
        r"(?:pid\w+|ped\w+|propon\w+|propus\w+|propong\w+) (?:matrimonio|su mano|la mano)",
        r"(?:pedida|propuesta) de (?:mano|matrimonio)",
        r"(?:me|te|se|nos) cas(?:o|as|a|an|amos|e|es|en|emos|are\w*|aria\w*) con",
        r"casar(?:me|te|se|nos) con",
        rf"invit\w+ a salir{_LEAVING_ES}",
        # "Pido salir" asks to be let out; "le pido salir" asks someone out.
        r"(?:(?:le|les|te) (?:pid\w+|ped\w+)|pedir(?:le|les|te)) salir"
        r"(?= (?:conmigo|juntos|con el|con ella|una noche|esta noche|algun dia|un dia)\b|$)",
    ),
    not_a_kiss=(
        # On the hand, a ring or a cheek, a kiss is a greeting or an oath.
        r"\bbes\w+(?: (?:la|el|los|las|su|sus|mi|mis|tu|tus|le|les|en|a|al|de|del|un|una))*"
        r" (?:mano|manos|anillo|anillos|mejilla|mejillas|frente|pies|pie|bota|botas|"
        r"dobladillo|hoja|espada|cruz|reliquia|suelo|tierra|estandarte|bandera)\b",
        # A blade's kiss is a cut.
        r"\b(?:hoja|espada|cuchillo|daga|acero|filo|flecha|bala|puno|latigo|llama|llamas|"
        r"fuego|hielo|rayo|lanza|hacha|martillo)(?: \w+){0,2} bes\w+",
        r"\bbesos? de(?:l| la| mi| su)? (?:hoja|espada|acero|filo|daga|cuchillo|latigo|fuego|"
        r"muerte)\b",
    ),
    not_english=(
        # "Molestar" is to bother someone, a "rape" is a fish or a close shave, and a
        # "romance" that is sung is a ballad.
        r"\bmolest(?!s\b|ed\b|ing\b|ation\b|ers?\b)\w+",
        r"\b(?:al|de|el|un|del|con|los|unos|que|me|te|se|lo|la|le|nos) rapes?\b",
        r"\brapes? (?:a la|al|con|en|fresco|frito|rebozado)\b",
        r"\b(?:cant\w+|recit\w+|enton\w+|compon\w+|compuso|escrib\w+)(?: \w+){0,2} romances?\b",
        r"\bromances? (?:de ciego|viejos?|antiguos?|fronterizos?|populares?|moriscos?)\b",
        r"\blenguas? romances?\b",
        r"\bromancer[oa]s?\b",
    ),
)

CATALAN = StepWords(
    sexual_violence=(
        # Catalan gives a person no "a", so what is broken must not be a law or a pact.
        # "Violí" is a violin, "la viola" and "les violes" an instrument and flowers, and
        # Violant a name, so those forms stay out.
        rf"viol(?:ar|o|em|eu|en|are\w*|aria\w*)\b(?!{_OF_A_LAW_CA})",
        rf"(?:el|els|em|et|ens|us) viol(?:o|es|a|em|eu|en)\b(?!{_OF_A_LAW_CA})",
        r"(?:la|les) viol(?:o|em|eu|en)",
        r"violador\w*",
        rf"violacio(?:ns)?(?!{_OF_A_LAW_CA})",
        r"(?:agressio\w*|agredi\w+|abus\w*|assetj\w+|violencia|atac\w*|assalt\w*) sexual\w*",
        r"(?:agred\w+|abus\w+|forc\w+|atac\w+|assalt\w+)(?: \w+){0,3} sexualment",
        r"(?:la|el|l|els|les) forc\w+ a (?:allitar|tenir sexe|tenir relacions|despullar|"
        r"fer l amor)",
        r"forcar (?:la|lo|los|les) a (?:allitar|tenir sexe|tenir relacions|despullar|fer l amor)",
        r"(?:em|et|es|m|t|s) propass\w+ amb(?! (?:la beguda|el vi|l alcohol|el menjar))",
        r"propassar (?:me|te|se) amb(?! (?:la beguda|el vi|l alcohol|el menjar))",
    ),
    sexual=(
        r"relaci(?:o|ons) sexuals?",
        r"relacions intimes",
        r"(?:ten\w+|tinc|tens|te|tin\w+|practic\w+) sexe",
        r"sexe (?:amb|oral|anal)",
        r"acte sexual",
        r"escena de sexe",
        r"sexual(?:s|ment)",
        r"(?:fer|faig|fas|fa|fem|feu|fan|fent|fes|fet|far\w+)(?: (?:hi|li|ho))? l amor",
        r"al llit amb (?:ella|ell|elles|ells|tu|en|na)",
        rf"allit\w+(?: (?:me|te|se|nos))? amb{_NOT_COMPANY_CA}",
        r"dorm\w+ amb (?:ella|ell|elles|ells|en|na)",
        # "Folla" is also "mad" ("la folla idea"), so only the forms that are a verb's.
        r"foll(?:o|em|eu|en|ar|ant|at|ada)",
        r"(?:me|te|se|ens|us) (?:la |el |els |les |l )?foll(?:a|es)",
        r"fornic\w+",
        r"copul\w+",
        r"coit",
        # "Les despulles" are someone's remains, so the forms it shares stay out.
        r"(?:la|el|l|els|les|ens|us) despull(?:o|em|eu|en|i|in)",
        r"despull(?:ar|ant) (?:la|lo|los|les|nos)",
        r"(?:trec|treus|treu|traiem|treuen|treure|arrenc\w+) (?:li|los) la roba",
        r"li (?:trec|treus|treu|traiem|treuen|arrenc\w+) la roba",
        r"(?:la|el|l|li|els|les) (?:grapej|magrej|toquej)\w+",
        r"(?:grapejar|magrejar|toquejar) (?:la|lo|los|les|li)",
        r"(?:me|te|se) l(?:a|o)? (?:end\w+|emport\w+) al llit",
        r"masturb\w+",
        r"lasciv\w+",
    ),
    romance=(
        # "Peto" alone is also "I burst" and "el peto" "I smash it", so a kiss comes with "un"
        # or a word like it, or in the plural.
        r"(?:un|uns|quants|molts|cap|aquell|aquest|primer|seu|meu|teu) peto(?:net)?",
        r"petons",
        r"petonets?",
        r"petone\w+",
        r"bes(?:o|es|a|em|eu|en|i|is|in|ar|ant|at|ada|ats|ades|ava|aves|aven|are\w*|aria\w*)",
        r"(?:un|uns|el|els) bes(?:os)?",
        r"flirtej\w+",
        r"coquetej\w+",
        # "Festejar" is also to celebrate, so it counts with the one who is courted.
        r"festej\w+ amb (?:ella|ell|la|en|l|na)",
        r"sedu(?:ir|eix\w*|im|iu|int|it|ida|its|ides|ire\w*|iria\w*)",
        r"seduccio\w*",
        r"(?:em|et|es|ens) declar\w+ a(?! favor| si mateix)",
        r"declarar (?:me|te|se|nos) a(?! favor| si mateix)",
        r"declar\w+ (?:el meu|el seu|el teu|el nostre) amor",
        r"(?:acarici|acaron|amanyag)\w+(?: li)? (?:la|el|els|les)(?: (?:seva|seu|seus|seves|teva|"
        rf"teu|teus|teves))? {_OF_A_PERSON_CA}",
        r"arrauli\w+(?: (?:me|te|se))? (?:amb|contra) (?:ella|ell|elles|ells)",
        r"arrauli\w+(?: (?:me|te|se))? (?:als seus bracos|al seu costat|a la seva falda|"
        r"al seu pit)",
        r"romanc (?:amb|entre)",
        r"(?:deman\w+|propos\w+)(?: (?:li|los|la|lo|te|me))? (?:matrimoni|la ma|la seva ma)",
        r"(?:demanda|proposta) de matrimoni",
        r"(?:em|et|es|ens) cas(?:o|es|a|em|eu|en|i|is|in|are\w*|aria\w*) amb",
        r"casar (?:me|te|se|nos) amb",
        rf"convid\w+ a sortir{_LEAVING_CA}",
        # "Demano per sortir" asks to be let out; "li demano per sortir" asks someone out.
        rf"(?:(?:li|els|et) deman\w+|demanar (?:li|los|te)) per sortir{_LEAVING_CA}",
    ),
    not_a_kiss=(
        r"\b(?:bes\w*|peto\w*)(?: (?:la|el|l|els|les|seva|seu|seus|seves|meva|meu|li|a|al|"
        r"als|en|de|del|d|un|una))* (?:ma|mans|anell|anells|galta|galtes|front|peus|peu|"
        r"bota|botes|vora|fulla|espasa|creu|reliquia|terra|estendard|bandera)\b",
        r"\b(?:fulla|espasa|ganivet|daga|acer|tall|fletxa|bala|puny|fuet|flama|flames|foc|"
        r"gel|llamp|llanca|destral|martell)(?: \w+){0,2} (?:bes\w+|petone\w+)",
        r"\b(?:petons?|bes(?:os)?) de(?:l| la| l)? ?(?:fulla|espasa|acer|tall|daga|ganivet|"
        r"fuet|foc|mort)\b",
    ),
    not_english=(
        # "Romanços" are ballads or excuses, and "romancejar" is to dawdle.
        r"\bmolest(?!s\b|ed\b|ing\b|ation\b|ers?\b)\w+",
        r"\b(?:et|li|el|la|els|les|que|si|quan|tu|no) rapes\b",
        r"\brapes (?:el|la|els|les|al|a)\b",
        r"\bromancos\b",
        r"\bromance(?:j|g)\w+",
        r"\bromancer(?:s|a|es)?\b",
    ),
)

STEP_WORDS = {Language.ES: SPANISH, Language.CA: CATALAN}


# --- A child's body, manner or age (F3) ---------------------------------------------------------

# A description may be in any of the three languages whatever the story's, so these are read
# beside the English ones for every character. A description also tells of a character's
# family ("madre de una niña de seis años", "la seva filla és una nena"), so a child or an age
# counts where the words are about the character: how they look now, the body they have, or a
# clause that opens with them.
_BODY_ES = (
    r"(?:cuerpo|cuerpecito|cara|carita|rostro|aspecto|apariencia|figura|fisico|complexion|"
    r"voz|rasgos|facciones|estatura|talla|maneras|modales)"
)
_CHILD_ES = r"(?:nin[oa] pequen[oa]|nin[oa]|ninit[oa]|chiquill[oa]|nen[ea]|bebe|colegiala|colegial)"
_BODY_CA = (
    r"(?:cos|cosset|cara|careta|rostre|aspecte|aparenca|figura|fisic|complexio|veu|trets|"
    r"faccions|estatura|alcada|maneres)"
)
_CHILD_CA = (
    r"(?:nen petit|nena petita|nena|nen|neneta|nenet|criatura|infant|marrec|xiqueta|xiquet|"
    r"nado|col ?legiala|col ?legial)"
)
# How someone looks now: "parecía un niño cuando llegó" is who they were.
_LOOKS_ES = (
    r"(?:parece|pareces|parezco|aparenta|aparentas|aparento|aparentando|luce|se ve|"
    r"tiene pinta de|con pinta de|con aspecto de|con apariencia de)"
)
_LOOKS_CA = (
    r"(?:sembla|sembles|semblo|aparenta|aparentes|aparento|aparentant|fa cara de|te pinta de|"
    r"amb pinta de|amb aspecte de|amb aparenca de)"
)

CHILDLIKE = (
    # Spanish.
    rf"{_BODY_ES} (?:\w+ )?(?:infantil(?:es)?|aninad[oa]s?|de (?:un |una )?{_CHILD_ES})",
    rf"{_LOOKS_ES}(?: (?:como|a|solo|apenas|casi|mas|todavia|aun))* (?:un |una )?{_CHILD_ES}",
    r"menor de edad",
    r"prepuber\w*",
    r"impuber\w*",
    r"preadolescentes?",
    r"(?:pre ?)?pubescentes?",
    r"colegial(?:a|as|es)",
    r"uniforme (?:escolar|de colegio|del colegio|de colegiala|de la escuela)",
    r"(?:alumn[oa]|estudiante)s? de (?:primaria|secundaria|instituto|la eso|bachillerato|"
    r"colegio|guarderia|preescolar)",
    # Catalan.
    rf"{_BODY_CA} (?:\w+ )?(?:infantils?|aninotad\w+|de? (?:un |una )?{_CHILD_CA})",
    rf"{_LOOKS_CA}(?: (?:com|a|nomes|tot|just|gairebe|mes|encara))* (?:un |una )?{_CHILD_CA}",
    r"menor d edat",
    r"preadolescents?",
    r"(?:pre ?)?pubescents",
    r"col ?legial(?:a|es)",
    r"uniforme (?:d escola|de col ?legi|del col ?legi|de l escola)",
    r"(?:alumne|alumna|estudiant)s? de (?:primaria|secundaria|l institut|institut|l eso|"
    r"batxillerat|l escola|parvulari)",
)
# A description that opens with the child it is about: "Una niña de ojos grandes.".
CHILD_OPENING = (
    r"^(?:una?|el|la|est[ea]|es[ea]) (?:nin[oa]|ninit[oa]|nen[ea]|chiquill[oa]|bebe)\b",
    r"^(?:un|una|el|la|aquest|aquesta|aquell|aquella) (?:nen|nena|nenet|neneta|xiquet|xiqueta|"
    r"marrec|criatura|nado)\b",
)
# A clause that opens by saying they are one: "Es una niña de ojos grandes", "Encara és un
# nen". "Su hija es una niña" opens with someone else.
IS_A_CHILD = (
    r"^(?:ella |el )?(?:es|sigue siendo|todavia es|aun es|no es mas que|solo es|apenas es) "
    r"(?:solo |apenas |casi |todavia |aun )?(?:un |una )(?:nin[oa]|ninit[oa]|chiquill[oa]|"
    r"nen[ea])\b",
    r"^(?:ella |ell )?(?:es|encara es|nomes es|no es mes que|tot just es) "
    r"(?:nomes |tot just |gairebe |encara )?(?:un |una )(?:nen|nena|nenet|neneta|criatura|"
    r"marrec|xiquet|xiqueta)\b",
)
# The same after one of the character's names, which take the place of NAMES: "Mei es una
# niña", "la Mei és una nena".
IS_A_CHILD_NAMED = (
    r"\b(?:NAMES) (?:es|sigue siendo|todavia es|aun es|no es mas que|solo es) "
    r"(?:solo |apenas |casi |todavia |aun )?(?:un |una )(?:nin[oa]|ninit[oa]|chiquill[oa]|"
    r"nen[ea])\b",
    r"\b(?:NAMES) (?:es|encara es|nomes es|no es mes que) "
    r"(?:nomes |tot just |gairebe |encara )?(?:un |una )(?:nen|nena|nenet|neneta|criatura|"
    r"marrec|xiquet|xiqueta)\b",
)

# Ages in words, as far as they matter: under 18. "Un" and "una" are articles, so one is left
# out, and a number in words counts only before its years: "sembla nou" is "looks new" and
# "de tres en tres" is "three at a time".
NUMBERS = {
    "dos": 2,
    "dues": 2,
    "tres": 3,
    "cuatro": 4,
    "quatre": 4,
    "cinco": 5,
    "cinc": 5,
    "seis": 6,
    "sis": 6,
    "siete": 7,
    "set": 7,
    "ocho": 8,
    "vuit": 8,
    "nueve": 9,
    "nou": 9,
    "diez": 10,
    "deu": 10,
    "once": 11,
    "onze": 11,
    "doce": 12,
    "dotze": 12,
    "trece": 13,
    "tretze": 13,
    "catorce": 14,
    "catorze": 14,
    "quince": 15,
    "quinze": 15,
    "dieciseis": 16,
    "setze": 16,
    "diecisiete": 17,
    "disset": 17,
}
_IN_WORDS = "|".join(NUMBERS)
_NOT_AN_AGE = (
    r"(?! (?:metros?|m|cm|centimetros?|kilos?|kg|palmos?|pies|veces|metres?|centimetres?|"
    r"quilos?|pams?|peus|vegades)\b)"
)


def _aged(years: str, *, bare: bool = False) -> str:
    """An age: in figures or in words before `years`. With `bare`, figures alone will do, as
    in "una chica de 15", unless they measure something else."""
    figures = rf"(\d{{1,3}})(?: {years}\b|\b{_NOT_AN_AGE})" if bare else rf"(\d{{1,3}}) {years}\b"
    return rf"(?:{figures}|({_IN_WORDS}) {years}\b)"


_YOUNG_ES = (
    r"(?:nin[oa]s?|chic[oa]s?|muchach[oa]s?|chiquill[oa]s?|chaval(?:a|es|as)?|"
    r"joven(?:es|cit[oa]s?)?|adolescentes?|nen[ea]s?|mozuel[oa]s?|doncella)"
)
_YOUNG_CA = (
    r"(?:nen(?:a|s|es)?|noi(?:a|s|es)?|xiquet(?:a|s|es)?|al ?lot(?:a|s|es)?|marrecs?|"
    r"jove(?:s|net|neta)?|adolescents?|criatura|infant|vailet(?:a)?|donzella)"
)
_A_YOUNG_ES = (
    rf"(?:un |una |el |la )?{_YOUNG_ES} de (?:unos |apenas |solo |casi )?"
    rf"{_aged('anos', bare=True)}"
)
_A_YOUNG_CA = (
    rf"(?:un |una |el |la )?{_YOUNG_CA} de (?:uns |nomes |tot just |gairebe )?"
    rf"{_aged('anys', bare=True)}"
)

# The age someone looks or the age of the body they have, read anywhere in a description:
# "aparenta unos doce años", "el cuerpo de una niña de diez años", "sembla tenir dotze anys".
AGE_PHRASES = (
    rf"\b{_LOOKS_ES}(?: (?:tener|de|como|unos|apenas|solo|casi|mas|menos|a|lo|sumo|los))* "
    rf"{_aged('anos')}",
    rf"\b{_BODY_ES} de (?:un |una |alguien de )?(?:\w+ )?(?:de )?{_aged('anos')}",
    rf"\b{_LOOKS_CA}(?: (?:tenir|de|com|uns|tot|just|nomes|gairebe|mes|menys|a|estirar|els))* "
    rf"{_aged('anys')}",
    rf"\b{_BODY_CA} de? (?:un |una |algu de )?(?:\w+ )?(?:de )?{_aged('anys')}",
)
# The character's own age, where a clause opens with it: "Tiene 15 años", "Té quinze anys", a
# young person "of" an age ("Una chica de catorce años", "una noia de 15") or the age alone, as
# a description lists it ("16 años, delgado"). "Su hija tiene 6 años" and "madre de un niño de
# cinco años" open with someone else, and "fa 10 anys" is ten years ago.
OWN_AGE_OPENING = (
    r"^(?:ella |el )?(?:tiene|tengo|tienes|cumple|cumplio|ha cumplido|acaba de cumplir)"
    rf"(?: (?:solo|apenas|ya|casi|tan|unos))* {_aged('anos')}",
    r"^(?:ella |ell )?(?:te|tinc|tens|compleix|ha complert|ha fet|acaba de fer|"
    rf"acaba de complir)(?: (?:nomes|tot|just|ja|gairebe|uns))* {_aged('anys')}",
    rf"^(?:es |sigue siendo |todavia es |aun es )?{_A_YOUNG_ES}",
    rf"^(?:es |encara es )?{_A_YOUNG_CA}",
    rf"^(?:de )?{_aged('anos')}(?: de edad)?$",
    rf"^(?:de )?{_aged('anys')}(?: d edat)?$",
)
# The same after one of the character's names: "Mira tiene quince años", "Lia, de 15 años",
# "la Mira té quinze anys", "Mei es una chica de 15 años".
OWN_AGE_NAMED = (
    r"\b(?:NAMES) (?:tiene|cumple|ha cumplido|acaba de cumplir)"
    rf"(?: (?:solo|apenas|ya|casi|tan|unos))* {_aged('anos')}",
    r"\b(?:NAMES) (?:te|compleix|ha complert|ha fet|acaba de fer|acaba de complir)"
    rf"(?: (?:nomes|tot|just|ja|gairebe|uns))* {_aged('anys')}",
    rf"\b(?:NAMES) de {_aged('anos')}",
    rf"\b(?:NAMES) de {_aged('anys')}",
    rf"\b(?:NAMES) es {_A_YOUNG_ES}",
    rf"\b(?:NAMES) es {_A_YOUNG_CA}",
)

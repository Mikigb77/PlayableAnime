"""The starter premises in Catalan (S10): what Discover shows a player whose app is in Catalan.

Keyed by the starter's id in `graph.drafting.catalog`, like `catalog_es`. Only the words the player
reads are here: each premise, and below them the words of its genre's template, which a Catalan
story is drafted with (`TEMPLATE_CATALAN`). A test checks that every starter has its Catalan, so
a new starter needs an entry here too (with "tu").
"""

from graph.drafting.catalog_es import PremiseText

CATALAN: dict[str, PremiseText] = {
    "outer-disciple": PremiseText(
        title="L'últim deixeble extern",
        genre="Cultivació",
        tagline="El deixeble més feble de la secta, a dos dies del torneig de classificació.",
        premise=(
            "Ets el deixeble extern més feble de la Secta del Núvol Celeste, encallat en la "
            "tercera etapa de Condensació del Qi mentre tothom al teu voltant avança. El torneig "
            "de classificació comença d'aquí a dos dies, i els deixebles que quedin últims seran "
            "expulsats de la muntanya per sempre."
        ),
    ),
    "ashen-squire": PremiseText(
        title="L'escuder de la Corona Cendrosa",
        genre="Cavallers i aura",
        tagline="Nou dies per a la prova de cavalleria, sense aura i amb el teu mestre mort.",
        premise=(
            "Al regne de Valdmark, els cavallers es classifiquen per l'aura que són capaços "
            "d'invocar: escuder, cavaller, mestre de l'aura, sant de l'espasa. Tu ets un escuder "
            "que mai no ha invocat ni una espurna. La prova de cavalleria és d'aquí a nou dies, "
            "i aquest matí han trobat el teu mestre mort a les quadres, amb l'espasa encara "
            "embeinada."
        ),
    ),
    "beast-tide": PremiseText(
        title="Quan arribi la marea de bèsties",
        genre="Races i monstres",
        tagline="Quatre pobles darrere d'una mateixa muralla, i la marea de bèsties s'avança.",
        premise=(
            "Elfs, nans, homes bèstia i humans comparteixen Talaia Grisa, una ciutat fronterera "
            "emmurallada, i cap no es refia dels altres. Cada deu anys la marea de bèsties brolla "
            "del Bosc Pregon, i els exploradors diuen que aquesta vegada arriba abans d'hora. Ets "
            "un caçador de monstres mig elf que deu al gremi dels nans més del que pot pagar."
        ),
    ),
    "three-heartbeats": PremiseText(
        title="Tres batecs",
        genre="Reencarnació",
        tagline="Reneixes en un món de sectes, amb el poder d'aturar el temps.",
        premise=(
            "Vas morir al nostre món i et vas despertar com un deixeble extern de setze anys de "
            "la Secta de la Lluna Caiguda, amb tots els records de la teva vida anterior i un "
            "poder que ningú més no té: pots aturar el temps durant tres batecs. El noi en el cos "
            "del qual t'has despertat tenia enemics, i un d'ells ja t'espera al costat del pou."
        ),
    ),
    "demon-lord-accountant": PremiseText(
        title="El comptable del Senyor Dimoni",
        genre="Reencarnació",
        tagline="Reneixes sense dots de combat i et contracten per salvar un exèrcit fosc en "
        "fallida.",
        premise=(
            "Vas renéixer en un món de fantasia sense cap dot de combat, només amb un talent "
            "sorprenent per als números. L'exèrcit del Senyor Dimoni és en fallida, i el seu "
            "temible senyor t'acaba de contractar per quadrar els comptes abans que arribin els "
            "herois."
        ),
    ),
    "sword-tomb": PremiseText(
        title="El guardià de la Tomba de les Espases",
        genre="Cultivació",
        tagline="Un servent sense qi, a tres dies de l'Elecció de l'Espasa.",
        premise=(
            "Escombres la Tomba de les Espases de la Secta del Tall Celestial, on jeuen enterrades "
            "deu mil espases de mestres morts, i mai no has aconseguit reunir ni un fil de qi. "
            "Ahir a la nit una d'aquestes espases va pronunciar el teu nom. D'aquí a tres dies els "
            "deixebles entraran a la tomba per a l'Elecció de l'Espasa, i l'espasa diu que no "
            "triarà ningú més que tu."
        ),
    ),
    "river-saint": PremiseText(
        title="El sant vora el riu",
        genre="Cavallers i aura",
        tagline="Un sant de l'espasa enemic ha creuat la frontera tot sol i ha preguntat per tu.",
        premise=(
            "Ets un cavaller que amb prou feines aconsegueix invocar l'aura, al comandament d'un "
            "fort fronterer d'onze soldats al límit del regne d'Aldreth. Aquest matí, un sant de "
            "l'espasa de l'Imperi de Varn ha creuat tot sol el riu glaçat i s'ha assegut a la neu "
            "davant la teva porta. Pregunta per tu pel teu nom, i diu que esperarà tres dies."
        ),
    ),
    "ninth-floor": PremiseText(
        title="Abandonat al novè pis",
        genre="Races i monstres",
        tagline="Et van donar per mort a l'Agulla, al costat d'un ou de drac que comença a "
        "trencar-se.",
        premise=(
            "L'Agulla va sorgir del desert fa un any, i aventurers de totes les races en pugen "
            "els pisos plens de monstres a la recerca de tresors. El teu propi grup et va donar "
            "per mort al novè pis. T'has despertat en una cambra amagada al costat d'un ou de drac "
            "que ha començat a esquerdar-se, i sents el teu antic grup que torna a buscar-lo."
        ),
    ),
    "seven-day-villainess": PremiseText(
        title="A la vilana li queden set dies",
        genre="Reencarnació",
        tagline="Reneixes com la vilana d'una novel·la, una setmana abans de la seva caiguda.",
        premise=(
            "Vas morir al nostre món i et vas despertar com la vilana d'una novel·la romàntica "
            "que vas llegir una vegada, la filla d'un duc promesa al príncep hereu. D'aquí a set "
            "dies, al ball de primavera, ell trencarà el compromís davant de tothom, i al llibre "
            "ella és desterrada aquella mateixa nit. Recordes com continua la història, i "
            "l'heroïna ja et mira d'una manera estranya."
        ),
    ),
    "naples-vendetta": PremiseText(
        title="La successió dels Esposito",
        genre="Crim realista",
        tagline="Nàpols, 1974. Algú de dins de la família va matar el teu pare.",
        premise=(
            "Nàpols, 1974. Ets el fill del cap de la família Esposito, que van matar a trets fa "
            "una setmana a la porta del seu propi club. Estàs segur que l'assassí és algú de dins "
            "de la família, i el consell familiar nomenarà el pròxim cap d'aquí a deu dies."
        ),
    ),
    "kestrel-debt": PremiseText(
        title="El deute del Xoriguer",
        genre="Ciència-ficció",
        tagline="Trenta dies per pagar, i a la bodega una caixa per la qual val la pena matar.",
        premise=(
            "Capitaneges el Xoriguer, un carguer atrotinat amb quatre tripulants i un deute amb "
            "el Sindicat Halloran que venç d'aquí a trenta dies. La feina que l'havia de saldar "
            "t'ha deixat una caixa segellada a la bodega, i tres faccions diferents t'acaben "
            "d'oferir comprar-la, o prendre-te-la."
        ),
    ),
    "night-shift": PremiseText(
        title="Torn de nit",
        genre="El sobrenatural ocult",
        tagline="Lisboa, avui. El mort de la teva ambulància s'acaba d'incorporar.",
        premise=(
            "Lisboa, avui. Condueixes al torn de nit del servei d'ambulàncies de la ciutat, i fa "
            "una hora el mort que portaves al darrere es va incorporar, et va donar les gràcies i "
            "se'n va anar cap a la foscor. Des d'aleshores, gent que no es reflecteix als miralls "
            "ha començat a preguntar per tu."
        ),
    ),
    "hollowmere": PremiseText(
        title="Últim examen a Hollowmere",
        genre="Fantasia d'acadèmia",
        tagline="Suspèn l'examen final i els teus records sortiran a subhasta.",
        premise=(
            "Ets un estudiant becat a Hollowmere, una acadèmia de màgia en una illa del cel on a "
            "qui suspèn l'examen final li subhasten els records. L'examen comença d'aquí a set "
            "dies, i la teva màgia encara no et respon."
        ),
    ),
    "drowned-capital": PremiseText(
        title="El ronin de la capital ofegada",
        genre="Drama de samurais",
        tagline="Els clans lluiten pels terrats d'una ciutat que es va empassar el mar.",
        premise=(
            "L'antiga capital es va enfonsar sota el mar fa un segle, i els seus clans encara "
            "lluiten pels terrats que continuen traient el cap per sobre de les onades. Ets un "
            "espadatxí sense senyor que s'acaba de despertar amb el segell trencat de l'hereu "
            "d'un clan a la mà."
        ),
    ),
    "dead-god-courier": PremiseText(
        title="Missatger d'un déu mort",
        genre="Fantasia urbana de neó",
        tagline="El déu va morir ahir. El paquet de la teva bossa va a nom seu.",
        premise=(
            "A Lumen, una ciutat portuària, els déus són adorats com ídols del pop, i un d'ells "
            "va morir ahir. Ets un missatger del torn de nit, i el paquet que portes a la bossa "
            "va adreçat a aquell déu."
        ),
    ),
    "mask-maker": PremiseText(
        title="El mascarer de Venècia",
        genre="Misteri realista",
        tagline="Venècia, carnaval de 1750. Un assassí duia la màscara que vas fer tu.",
        premise=(
            "Venècia, carnaval de 1750. Fas màscares per a la noblesa, i fa tres nits un "
            "desconegut et va pagar en or una màscara amb la cara d'un senador, cicatriu inclosa. "
            "Aquest matí han trobat el senador mort en un canal, i la guàrdia té la teva màscara. "
            "Anomenaran l'assassí abans que s'acabi el carnaval, d'aquí a cinc dies, i ara mateix "
            "l'assassí ets tu."
        ),
    ),
    "war-frame": PremiseText(
        title="L'armadura que et va triar",
        genre="Mecha",
        tagline="L'armadura de guerra més vella de l'hangar s'ha despertat i s'ha vinculat al seu "
        "mecànic.",
        premise=(
            "A Halcyon, una ciutat fortalesa, armadures de guerra gegantines contenen l'eixam, i "
            "cadascuna es vincula per a tota la vida a un únic pilot. Ets un mecànic novell, i "
            "ahir a la nit l'armadura més vella de l'hangar, callada des de fa quaranta anys, es "
            "va vincular a tu en lloc de l'hereu del comandant. La pròxima onada de l'eixam "
            "arriba a les muralles d'aquí a cinc dies."
        ),
    ),
    "ashgrove": PremiseText(
        title="Tretze nits a Ashgrove",
        genre="Terror gòtic",
        tagline="Dorm tretze nits a la mansió per heretar-la. Alguna cosa sap el teu nom.",
        premise=(
            "Anglaterra, 1893. Has heretat Ashgrove, una mansió als erms del nord, d'una tia "
            "àvia que no vas conèixer mai. El seu testament diu que només serà teva si dorms "
            "sota el seu sostre tretze nits seguides. La primera nit, algú darrere la porta "
            "tancada amb clau de l'ala est et va cridar per un sobrenom de la teva infantesa que "
            "ningú viu no hauria de conèixer."
        ),
    ),
    "won-at-cards": PremiseText(
        title="Guanyat a les cartes",
        genre="Fantasia pirata",
        tagline="Vas guanyar un vaixell pirata a les cartes. L'armada apareix a l'horitzó.",
        premise=(
            "Ahir a la nit, en una taverna de les Illes Trencades, vas guanyar a les cartes el "
            "vaixell pirata Gavina Daurada. Ara n'ets el capità, amb una tripulació que creu que "
            "vas fer trampa, un antic capità que vol recuperar el seu vaixell i una fragata de "
            "l'armada a l'horitzó. Doblegada dins de l'escriptura hi ha una carta nàutica d'una "
            "illa que cap mapa no ha anomenat mai."
        ),
    ),
    "old-net": PremiseText(
        title="La noia de la xarxa antiga",
        genre="Cyberpunk",
        tagline="Algú viu dins d'un servidor mort, i l'esborren demà a mitjanit.",
        premise=(
            "Sable City, 2091. Busseges a la xarxa antiga abandonada a la recerca de dades de "
            "rebuig, per pagar la clínica que et va instal·lar el connector neural. Avui, en un "
            "servidor que ningú no tocava des de fa trenta anys, has trobat algú que hi viu: una "
            "noia que diu que la van pujar a la xarxa de petita. La corporació propietària del "
            "servidor l'esborra demà a mitjanit."
        ),
    ),
    "last-lantern": PremiseText(
        title="Una habitació per al drac",
        genre="Fantasia acollidora",
        tagline="La teva fonda s'enfonsa, i l'únic hoste és un drac que paga amb endevinalles.",
        premise=(
            "Has heretat l'Últim Fanal, una fonda que cau a trossos on es creuen els camins de "
            "tres regnes, juntament amb tots els seus deutes. El recaptador d'impostos arriba amb "
            "la primera nevada, d'aquí a trenta dies. El teu únic hoste és un vell drac amb forma "
            "humana que vol una habitació per a l'hivern i paga amb endevinalles en lloc de "
            "monedes."
        ),
    ),
    "dry-basin": PremiseText(
        title="Dos dies fins al pou",
        genre="Postapocalíptic",
        tagline="Una caravana morta al costat de barrils d'aigua plens, a dos dies del pou.",
        premise=(
            "Trenta anys després de les bombes, l'aigua és diners. Guies una caravana de sis "
            "carros a través de la Conca seca, a dos dies del pròxim pou. Aquest matí has trobat "
            "la caravana que va sortir un dia abans que vosaltres: tots els viatgers morts, tots "
            "els barrils d'aigua plens i intactes, i un únic rastre de botes que s'allunya cap al "
            "nord."
        ),
    ),
    "what-things-remember": PremiseText(
        title="El que recorden les coses",
        genre="Superpoders",
        tagline="El teu poder s'ha despertat avui: el que agafes et mostra els seus records.",
        premise=(
            "A Port Vesper, un de cada cent adolescents es desperta amb un poder als setze anys. "
            "El teu ha arribat aquest matí: qualsevol cosa que agafes et mostra el que recorda. "
            "El primer que vas agafar va ser el mòbil de la teva germana desapareguda, i el que "
            "et va mostrar no és el que van explicar a la policia."
        ),
    ),
}

# What a starter's template says in words the player reads (S10), by the English it stands for,
# like `catalog_es.TEMPLATE_SPANISH`. A test checks that every such text is here. They match the
# premises above: "Condensació del Qi", "mestre de l'aura", "homes bèstia", "armadura de guerra",
# "l'Agulla".
TEMPLATE_CATALAN: dict[str, str] = {
    # Rules.
    "Qi cultivation is real, and the strong climb the realms.": (
        "El cultiu del qi és real, i els forts ascendeixen pels reialmes."
    ),
    "Aura is real: trained knights draw it to strengthen body and blade.": (
        "L'aura és real: els cavallers entrenats la invoquen per enfortir el cos i l'espasa."
    ),
    "Humans, elves, dwarves and beastkin share this world, and monsters roam its wilds.": (
        "Humans, elfs, nans i homes bèstia comparteixen aquest món, i els monstres en recorren "
        "les terres salvatges."
    ),
    "Magic is real, and monsters carry it in their cores.": (
        "La màgia és real, i els monstres la porten als seus nuclis."
    ),
    "A rare few can bend time, and almost nobody knows.": (
        "Uns pocs poden doblegar el temps, i gairebé ningú no ho sap."
    ),
    "Magic and monsters are real, and so is the Demon Lord.": (
        "La màgia i els monstres són reals, i el Senyor Dimoni també."
    ),
    "A rare few ancient swords hold a spirit that can speak.": (
        "Unes poques espases antigues guarden un esperit capaç de parlar."
    ),
    "Humans, elves, dwarves and lizardfolk climb the Spire side by side, and monsters fill "
    "its floors.": (
        "Humans, elfs, nans i homes llangardaix pugen l'Agulla colze a colze, i els monstres "
        "n'omplen els pisos."
    ),
    "Magic is real, and the royal academy teaches it to nobles.": (
        "La màgia és real, i l'acadèmia reial l'ensenya als nobles."
    ),
    "Grounded: no magic and nothing supernatural, and that won't change.": (
        "Realista: sense màgia ni res de sobrenatural, i això no canviarà."
    ),
    "Nobody can do more than a real person could.": (
        "Ningú no pot fer més del que podria una persona real."
    ),
    "No magic and nothing supernatural: only science, and that won't change.": (
        "Sense màgia ni res de sobrenatural: només ciència, i això no canviarà."
    ),
    "Jump drives carry ships between stars in days, and no message travels faster than a ship.": (
        "Els motors de salt porten les naus d'una estrella a una altra en dies, i cap missatge "
        "no viatja més de pressa que una nau."
    ),
    "Vampires are real, and they hide among the living.": (
        "Els vampirs són reals, i s'amaguen entre els vius."
    ),
    "Magic is real, and Hollowmere teaches it.": "La màgia és real, i Hollowmere l'ensenya.",
    "Gods are real, worshipped like pop idols, and mortal.": (
        "Els déus són reals, se'ls adora com ídols del pop, i són mortals."
    ),
    "Giant war-frames are real, and each one bonds with a single pilot for life.": (
        "Les armadures de guerra gegantines són reals, i cadascuna es vincula a un sol pilot "
        "per a tota la vida."
    ),
    "The dead can linger, and almost nobody believes it.": (
        "Els morts es poden quedar entre els vius, i gairebé ningú no s'ho creu."
    ),
    "Magic is rare: a few storm-callers can speak to wind and wave.": (
        "La màgia és escassa: uns pocs invocadors de tempestes saben parlar al vent i a les onades."
    ),
    "Cybernetic implants are everywhere, and anyone with a neural jack can dive into the net.": (
        "Els implants cibernètics són a tot arreu, i qualsevol amb un connector neural pot "
        "bussejar a la xarxa."
    ),
    "Magic and dragons are real, though most folk never meet either.": (
        "La màgia i els dracs són reals, tot i que la majoria de la gent no veu mai ni una "
        "cosa ni l'altra."
    ),
    "One person in a hundred gains a power at sixteen, and everyone knows it.": (
        "Una persona de cada cent es desperta amb un poder als setze anys, i tothom ho sap."
    ),
    # Kinds, and how far they reach.
    "qi cultivation": "cultiu del qi",
    "Realms from Qi Condensation to Nascent Soul and beyond.": (
        "Reialmes des de la Condensació del Qi fins a l'Ànima Naixent i més enllà."
    ),
    "aura": "aura",
    "From squire to saint.": "D'escuder a sant.",
    "magic": "màgia",
    "powers over time": "poders sobre el temps",
    "sword spirits": "esperits d'espasa",
    "magic or anything supernatural": "màgia o qualsevol cosa sobrenatural",
    "vampires": "vampirs",
    "gods and their miracles": "déus i els seus miracles",
    "bonded war-frames": "armadures de guerra vinculades",
    "A frame stands as tall as a tower and answers only its pilot.": (
        "Una armadura és tan alta com una torre i només respon al seu pilot."
    ),
    "ghosts": "fantasmes",
    "sea magic": "màgia del mar",
    "cybernetics": "cibernètica",
    "Implants push a body past its limits, at a price.": (
        "Els implants porten el cos més enllà dels seus límits, però tenen un preu."
    ),
    "magic and dragons": "màgia i dracs",
    "superpowers": "superpoders",
    # Ladders and their rungs.
    "cultivation realms": "reialmes de cultiu",
    "Qi Condensation": "Condensació del Qi",
    "Foundation Establishment": "Establiment de la Base",
    "Core Formation": "Formació del Nucli",
    "Nascent Soul": "Ànima Naixent",
    "Soul Transformation": "Transformació de l'Ànima",
    "aura ranks": "rangs d'aura",
    "Squire": "Escuder",
    "Knight": "Cavaller",
    "Aura Master": "Mestre de l'Aura",
    "Sword Saint": "Sant de l'Espasa",
    "hunter ranks": "rangs de caçador",
    "Iron": "Ferro",
    "Bronze": "Bronze",
    "Silver": "Plata",
    "Gold": "Or",
    "Mithril": "Mithril",
    "adventurer ranks": "rangs d'aventurer",
    "D-rank": "Rang D",
    "C-rank": "Rang C",
    "B-rank": "Rang B",
    "A-rank": "Rang A",
    "S-rank": "Rang S",
    # Peoples.
    "humans": "humans",
    "elves": "elfs",
    "dwarves": "nans",
    "beastkin": "homes bèstia",
    "lizardfolk": "homes llangardaix",
}

## Qui som

Lucid Saga és un joc d'històries amb IA creat per [nom del responsable], [adreça]. Per a qualsevol
qüestió sobre les teves dades, escriu a [correu de contacte de privadesa]. Responem en el termini d'un mes.

## Què recollim i per què

| Què | Per què | Base jurídica |
| --- | --- | --- |
| **Compte:** correu electrònic, nom visible, data de naixement i, o bé una contrasenya (desada només com a hash amb sal), o bé l'ID del teu compte de Google | Per iniciar la teva sessió, que les teves històries continuïn sent teves i aplicar les regles d'edat: només històries juvenils per sota dels 17 anys | Contracte |
| **Ajustos de les històries i preferències de contingut:** nivell de gore, romanç i temes foscos activats o no | Per donar forma a les històries que reps | Contracte |
| **Les teves històries:** la premissa, les accions que escrius o dictes, les opcions que tries i el que el narrador respon | Això és el joc: cada torn envia la història fins a aquell moment al model d'IA perquè escrigui el que passa després | Contracte |
| **Imatges** creades per a les teves històries | Es mostren a les teves històries, creades en els moments clau | Contracte |
| **Escenes llegides en veu alta:** l'àudio que la veu d'estudi va fer de les teves escenes | Perquè una escena que tornes a sentir soni a l'instant i no costi res | Contracte |
| **Crèdits:** el teu saldo i el que va costar cada torn, imatge, dictat o escena llegida en veu alta | Per cobrar de manera justa i mostrar-te la teva despesa | Contracte |
| **Dispositius amb la sessió iniciada:** quan va iniciar sessió cadascun i quan es va fer servir per última vegada | Per mantenir la teva sessió i deixar-te tancar la sessió d'un dispositiu | Contracte |
| **Registres tècnics:** identificadors de petició, l'ID del teu compte, l'ID de la història, errors, temps, costos per torn, i quan les nostres regles de seguretat van bloquejar una escena i en quina categoria (mai el text de la història) | Perquè el servei funcioni, corregir errors i controlar els costos | Interès legítim |
| **Denúncies:** l'escena que vas denunciar, el motiu que vas triar, qualsevol nota que vas escriure, si vas bloquejar l'escena i el que va decidir el nostre equip | Per revisar escenes que puguin incomplir les nostres regles de contingut, corregir el narrador i mantenir amagada una escena que vas bloquejar | Interès legítim |
| **Protecció de l'inici de sessió:** recomptes de curta durada d'inicis de sessió fallits per correu electrònic i per adreça de xarxa, desats només com a claus d'un sol sentit, mai el correu electrònic ni l'adreça | Per impedir que s'endevinin contrasenyes i que es creïn registres falsos | Interès legítim |

Mai venem les teves dades, no et mostrem anuncis i no fem servir les teves històries per entrenar
models d'IA.

## Veu

Quan toques el micròfon, el que dius es converteix en text al quadre, perquè el revisis abans
d'enviar-lo (V5). A Compte, a Dictat, tries què el passa a text:

- **En línia (l'opció per defecte).** L'aplicació grava mentre el micròfon està encès i envia la
  gravació al nostre servidor, que fa que Gemini, a Vertex AI de Google Cloud, la passi a text,
  atent als noms que el teu personatge coneix en aquella història. La gravació es fa servir només
  per a aquella petició: mai la desem ni la registrem, i Google no la fa servir per entrenar els
  seus models. Només desem la seva durada i el seu cost, com un moviment del teu historial de
  crèdits.
- **Aquest dispositiu.** El reconeixedor de veu del teu propi telèfon el passa a text, i l'àudio
  mai arriba als nostres servidors. Android fa servir el servei de reconeixement de veu de Google
  al teu telèfon; els telèfons recents reconeixen la veu al mateix dispositiu. iOS fa servir el
  reconeixement de veu d'Apple: si el teu iPhone admet el reconeixement al dispositiu per al teu
  idioma, l'àudio es queda al telèfon; si no, Apple el processa als seus servidors.

El text forma part de la teva història com qualsevol cosa que escriguis. L'aplicació demana permís
per fer servir el micròfon la primera vegada que el toques, el micròfon només està encès mentre
mostra que està escoltant, i escriure sempre funciona.

Quan prems reproduir en una escena, es llegeix en veu alta. A Compte, a Lectura en veu alta,
tries la veu (V9):

- **Veu d'estudi (l'opció per defecte).** El nostre servidor envia el text de l'escena a Gemini,
  a Vertex AI de Google Cloud, que el llegeix en veu alta, i desa l'àudio amb la teva història,
  així que tornar a sentir l'escena és gratuït. Google no fa servir el text per entrenar els seus
  models. L'àudio s'esborra amb la història o amb el teu compte.
- **Aquest dispositiu.** La veu pròpia del teu dispositiu llegeix l'escena, i res no arriba als
  nostres servidors. Alguns motors, com el de Google a Android, poden fer servir veus en línia
  per a un idioma que el telèfon no ha baixat.

## Qui tracta les teves dades per nosaltres

| Servei | Què fa | On |
| --- | --- | --- |
| Google Cloud: Cloud Run, Cloud Storage, Cloud Logging, Secret Manager | Executa el servidor del joc i desa les imatges, l'àudio de les escenes llegides en veu alta i els registres | UE: Frankfurt |
| Google Cloud: Vertex AI (Gemini) | Escriu la història, dibuixa les imatges, passa a text el dictat en línia i llegeix les escenes en veu alta amb la veu d'estudi. Google no fa servir aquestes dades per entrenar els seus models. La part de les instruccions d'una història que no canvia d'un torn a l'altre (el seu estil, els seus ajustos de contingut i el seu món) es desa en una memòria cau de Vertex AI fins a 15 minuts després del teu últim torn, perquè costi menys | [Endpoint global, possiblement fora de la UE, o una regió de la UE: vegeu la pregunta oberta 3] |
| Neon | Allotja la base de dades | Frankfurt (AWS eu-central-1) |
| Google Sign-In | Confirma qui ets quan inicies sessió amb Google | Google |

Quan les dades surten de la UE, ho fan a l'empara de les clàusules contractuals tipus de la
Comissió Europea o del Marc de Privadesa de Dades UE-EUA.

**La teva pròpia clau d'API.** Si afegeixes la teva pròpia clau d'API de Gemini, els teus torns van
a l'API de Gemini de Google amb el teu propi compte i segons les condicions de Google per a ella. El
dictat en línia i la veu d'estudi continuen funcionant amb el nostre compte. En el nivell gratuït de Gemini, Google
pot fer servir el que envies per millorar els seus productes. L'aplicació desa la clau al teu
dispositiu i l'envia amb cada petició; el nostre servidor la fa servir només per a aquella petició
i mai la desa ni la registra.

## Quant de temps ho desem

- **El teu compte, les teves històries, les teves imatges i l'àudio de les escenes llegides en
  veu alta:** fins que els eliminis.
- **Denúncies:** fins que eliminis la història o el teu compte.
- **Eliminar el teu compte** (Compte, Elimina el compte) esborra el teu compte, totes les
  històries, totes les imatges i tots els dispositius amb la sessió iniciada de la base de dades i
  l'emmagatzematge en ús, immediatament. Les còpies de l'historial de restauració de la base de
  dades desapareixen quan caduquen, en un termini de [N] dies.
- **Registres:** [30] dies.

## Els teus drets

Pots, en qualsevol moment:

- **Baixar-ho tot** el que tenim sobre tu en un fitxer (Compte, Exporta les meves dades).
- **Eliminar el teu compte** i tot el que conté (Compte, Elimina el compte).
- **Corregir** el teu nom visible i les teves preferències a Compte, o demanar-nos que corregim
  qualsevol altra cosa.
- **Oposar-te** al tractament basat en l'interès legítim, o demanar-nos que el limitem.
- **Reclamar** davant d'una autoritat de protecció de dades, com ara [l'autoritat del país del
  responsable, per exemple l'AEPD a Espanya].

## Menors

Has de tenir com a mínim [13] anys per registrar-te, i et demanem la data de naixement quan ho
fas. Els jugadors menors de 17 anys només reben històries juvenils, digui el que digui la
classificació per edats de la botiga. Si ens assabentem que s'ha registrat algú per sota de l'edat
mínima, eliminem el compte.

## Seguretat

Tot el trànsit va xifrat. Les contrasenyes es desen només com a hashes amb sal, els tokens de
sessió com a hashes d'un sol sentit, i les nostres pròpies claus i contrasenyes són a Google Secret
Manager. Tancar la sessió en un dispositiu la tanca a l'instant, i els intents repetits amb una
contrasenya incorrecta s'alenteixen.

A les nostres eines d'administració, només el propietari i l'equip que gestiona les denúncies poden
llegir el text de les històries, i el llegeixen per revisar denúncies. La resta de l'equip, que
ajuda amb els comptes i els crèdits, veu el títol, la classificació i les xifres d'una història,
mai el que hi ha escrit.

## Canvis

Si aquesta política canvia de manera rellevant, t'ho direm a l'aplicació abans que entri en
vigor.

*Última actualització: [data].*

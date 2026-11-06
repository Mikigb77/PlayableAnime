import '../json.dart';
import 'fake_backend.dart';
import 'fake_data.dart';

/// Fake starter premises (S1), the same ones as the backend's catalog
/// (`backend/graph/drafting/catalog.py`), in its order: the flagship genres first. A few have no
/// cover, as a starter can until its cover is drawn. Owned by the discover work (WS15).
const fakePremises = <JsonMap>[
  {
    'id': 'outer-disciple',
    'title': 'The Last Outer Disciple',
    'genre': 'Cultivation',
    'tagline': 'The weakest disciple of the sect, two days before the ranking tournament.',
    'premise':
        'You are the weakest outer disciple of the Azure Cloud Sect, stuck at the third stage of '
        'Qi Condensation while everyone around you breaks through. The ranking tournament starts '
        'in two days, and the disciples who finish last are sent down the mountain for good.',
    'flagship': true,
    'cover_url': FakeAssets.peaks,
  },
  {
    'id': 'ashen-squire',
    'title': 'Squire of the Ashen Crown',
    'genre': 'Knights and aura',
    'tagline': 'Nine days to the trial of knighthood, no aura, and a dead master.',
    'premise':
        'In the kingdom of Valdmark, knights are ranked by the aura they can draw: squire, knight, '
        'aura master, sword saint. You are a squire who has never drawn a spark of it. The trial of '
        'knighthood is in nine days, and this morning your master was found dead in the stables '
        'with his sword still in its sheath.',
    'flagship': true,
    'cover_url': FakeAssets.castle,
  },
  {
    'id': 'beast-tide',
    'title': 'When the Beast Tide Comes',
    'genre': 'Races and monsters',
    'tagline': 'Four peoples behind one wall, and the beast tide is coming early.',
    'premise':
        'Elves, dwarves, beastkin and humans share the walled frontier town of Greywatch, and none '
        'of them trust each other. Every ten years the beast tide pours out of the Deepwood, and '
        'the scouts say this one is coming early. You are a half-elf monster hunter who owes the '
        'dwarven guild more than you can pay.',
    'flagship': true,
    'cover_url': FakeAssets.forest,
  },
  {
    'id': 'three-heartbeats',
    'title': 'Three Heartbeats',
    'genre': 'Reincarnation',
    'tagline': 'Reborn in a world of sects, with the power to stop time.',
    'premise':
        'You died in our world and woke up as a sixteen-year-old outer disciple of the Moonfall '
        'Sect, with every memory of your past life and a power nobody else has: you can stop time '
        'for three heartbeats. The boy whose body you woke in had enemies, and one of them is '
        'already waiting for you by the well.',
    'flagship': true,
    'cover_url': FakeAssets.dawn,
  },
  {
    'id': 'demon-lord-accountant',
    'title': 'The Demon Lord\'s Accountant',
    'genre': 'Reincarnation',
    'tagline': 'Reborn with no combat skills, hired to save a bankrupt dark army.',
    'premise':
        'You were reborn in a fantasy world with no combat skills, only an uncanny talent for '
        'numbers. The Demon Lord\'s army is bankrupt, and its terrifying lord has just hired you to '
        'fix the books before the heroes arrive.',
    'flagship': true,
    'cover_url': null,
  },
  {
    'id': 'sword-tomb',
    'title': 'Keeper of the Sword Tomb',
    'genre': 'Cultivation',
    'tagline': 'A servant with no qi, three days before the Sword Choosing.',
    'premise':
        'You sweep the Sword Tomb of the Heavenly Edge Sect, where ten thousand swords of dead '
        'masters lie buried, and you have never drawn a strand of qi. Last night one of those '
        'swords spoke your name. In three days the disciples enter the tomb for the Sword '
        'Choosing, and the sword says it will choose no one but you.',
    'flagship': true,
    'cover_url': FakeAssets.peaks,
  },
  {
    'id': 'river-saint',
    'title': 'The Saint at the River',
    'genre': 'Knights and aura',
    'tagline': 'An enemy sword saint crossed the border alone, and asked for you.',
    'premise':
        'You are a knight who can barely draw aura, holding a border fort of eleven soldiers at '
        'the edge of the kingdom of Aldreth. This morning a sword saint of the Varn Empire crossed '
        'the frozen river alone and sat down in the snow outside your gate. He asks for you by '
        'name, and says he will wait three days.',
    'flagship': true,
    'cover_url': FakeAssets.castle,
  },
  {
    'id': 'ninth-floor',
    'title': 'Left on the Ninth Floor',
    'genre': 'Races and monsters',
    'tagline': 'Left for dead in the Spire, beside a dragon egg that\'s starting to hatch.',
    'premise':
        'The Spire rose out of the desert a year ago, and adventurers of every race climb its '
        'monster-filled floors for treasure. Your own party left you for dead on the ninth floor. '
        'You woke in a hidden chamber beside a dragon egg that has started to crack, and you can '
        'hear your old party coming back for it.',
    'flagship': true,
    'cover_url': FakeAssets.forest,
  },
  {
    'id': 'seven-day-villainess',
    'title': 'The Villainess Has Seven Days',
    'genre': 'Reincarnation',
    'tagline': 'Reborn as a novel\'s villainess, a week before her downfall.',
    'premise':
        'You died in our world and woke up as the villainess of a romance novel you once read, a '
        'duke\'s daughter engaged to the crown prince. In seven days, at the spring ball, he '
        'breaks off the engagement in front of everyone, and in the book she is exiled that night. '
        'You remember how the story goes, and the heroine is already watching you strangely.',
    'flagship': true,
    'cover_url': FakeAssets.castle,
  },
  {
    'id': 'naples-vendetta',
    'title': 'The Esposito Succession',
    'genre': 'Grounded crime',
    'tagline': 'Naples, 1974. Someone inside the family killed your father.',
    'premise':
        'Naples, 1974. You are the son of the boss of the Esposito family, who was shot dead '
        'outside his own club a week ago. You\'re sure the killer is someone inside the family, and '
        'the family council will name the next boss in ten days.',
    'flagship': false,
    'cover_url': FakeAssets.city,
  },
  {
    'id': 'kestrel-debt',
    'title': 'The Kestrel\'s Debt',
    'genre': 'Science fiction',
    'tagline': 'Thirty days to pay, and a crate in the hold worth killing for.',
    'premise':
        'You captain the Kestrel, a battered cargo hauler with a crew of four and a debt to the '
        'Halloran Syndicate that comes due in thirty days. The job that was meant to clear it left '
        'a sealed crate in your hold, and three different factions have just offered to buy it, or '
        'take it.',
    'flagship': false,
    'cover_url': FakeAssets.nebula,
  },
  {
    'id': 'night-shift',
    'title': 'Night Shift',
    'genre': 'Hidden supernatural',
    'tagline': 'Lisbon, today. The dead man in your ambulance just sat up.',
    'premise':
        'Lisbon, today. You drive the night shift for the city\'s ambulance service, and an hour ago '
        'the dead man in the back of your ambulance sat up, thanked you, and walked off into the '
        'dark. Since then, people who don\'t show up in mirrors have started asking about you.',
    'flagship': false,
    'cover_url': FakeAssets.city,
  },
  {
    'id': 'hollowmere',
    'title': 'Last Exam at Hollowmere',
    'genre': 'Academy fantasy',
    'tagline': 'Fail the final exam and your memories go to auction.',
    'premise':
        'You are a scholarship student at Hollowmere, a sky-island academy of magic where anyone '
        'who fails the final exam has their memories auctioned off. The exam starts in seven days, '
        'and your magic still refuses to answer you.',
    'flagship': false,
    'cover_url': null,
  },
  {
    'id': 'drowned-capital',
    'title': 'Ronin of the Drowned Capital',
    'genre': 'Samurai drama',
    'tagline': 'Clans fight over the rooftops of a city the sea swallowed.',
    'premise':
        'The old capital sank beneath the sea a century ago, and its clans still fight over the '
        'rooftops that remain above the waves. You are a masterless swordsman who just woke up '
        'holding a clan heir\'s broken seal.',
    'flagship': false,
    'cover_url': FakeAssets.dawn,
  },
  {
    'id': 'dead-god-courier',
    'title': 'Courier for a Dead God',
    'genre': 'Neon urban fantasy',
    'tagline': 'The god died yesterday. The package in your bag is addressed to them.',
    'premise':
        'In the harbour city of Lumen, gods are worshipped like pop idols, and one of them died '
        'yesterday. You are a night-shift courier, and the package in your bag is addressed to that '
        'god.',
    'flagship': false,
    'cover_url': null,
  },
  {
    'id': 'mask-maker',
    'title': 'The Mask-Maker of Venice',
    'genre': 'Grounded mystery',
    'tagline': 'Venice, carnival of 1750. A murderer wore the mask you made.',
    'premise':
        'Venice, carnival of 1750. You make masks for the nobility, and three nights ago a '
        'stranger paid you in gold for a mask of a senator\'s face, down to the scar. This morning '
        'the senator was found dead in a canal, and the guard has your mask. They will name the '
        'killer before the carnival ends in five days, and right now that is you.',
    'flagship': false,
    'cover_url': FakeAssets.city,
  },
  {
    'id': 'war-frame',
    'title': 'The Frame That Chose You',
    'genre': 'Mecha',
    'tagline': 'The oldest war-frame in the hangar woke up and bonded with its mechanic.',
    'premise':
        'In the fortress city of Halcyon, giant war-frames hold back the swarm, and each one bonds '
        'with a single pilot for life. You are a junior mechanic, and last night the oldest frame '
        'in the hangar, silent for forty years, bonded with you instead of the commander\'s heir. '
        'The swarm\'s next wave reaches the walls in five days.',
    'flagship': false,
    'cover_url': FakeAssets.nebula,
  },
  {
    'id': 'ashgrove',
    'title': 'Thirteen Nights at Ashgrove',
    'genre': 'Gothic horror',
    'tagline': 'Sleep thirteen nights in the manor to inherit it. Something knows your name.',
    'premise':
        'England, 1893. You inherited Ashgrove, a manor on the northern moors, from a great-aunt '
        'you never met. Her will says it is yours only if you sleep under its roof for thirteen '
        'nights in a row. On the first night, someone behind the locked door of the east wing '
        'called you by a childhood nickname nobody alive should know.',
    'flagship': false,
    'cover_url': null,
  },
  {
    'id': 'won-at-cards',
    'title': 'Won at Cards',
    'genre': 'Pirate fantasy',
    'tagline': 'You won a pirate ship at cards. The navy is on the horizon.',
    'premise':
        'Last night, in a tavern on the Shattered Isles, you won the pirate ship Gilded Gull at '
        'cards. Now you are its captain, with a crew who think you cheated, an old captain who '
        'wants his ship back, and a navy frigate on the horizon. Folded into the deed is a chart '
        'of an island no map has ever named.',
    'flagship': false,
    'cover_url': FakeAssets.dawn,
  },
  {
    'id': 'old-net',
    'title': 'The Girl in the Old Net',
    'genre': 'Cyberpunk',
    'tagline': 'Someone lives inside a dead server, and it\'s wiped at midnight tomorrow.',
    'premise':
        'Sable City, 2091. You dive the abandoned old net for scrap data, to pay off the clinic '
        'that fitted your neural jack. Today, in a server untouched for thirty years, you found '
        'someone living there: a girl who says she was uploaded as a child. The corporation that '
        'owns the server wipes it at midnight tomorrow.',
    'flagship': false,
    'cover_url': FakeAssets.city,
  },
  {
    'id': 'last-lantern',
    'title': 'A Room for the Dragon',
    'genre': 'Cozy fantasy',
    'tagline': 'Your inn is failing, and the only guest is a dragon who pays in riddles.',
    'premise':
        'You inherited the Last Lantern, a crumbling inn where the roads of three kingdoms meet, '
        'along with every one of its debts. The tax collector comes with the first snow, in thirty '
        'days. Your only guest is an old dragon in human shape who wants a room for the winter, '
        'and pays in riddles instead of coin.',
    'flagship': false,
    'cover_url': FakeAssets.forest,
  },
  {
    'id': 'dry-basin',
    'title': 'Two Days to the Well',
    'genre': 'Post-apocalyptic',
    'tagline': 'A caravan lies dead beside full water barrels, two days from the well.',
    'premise':
        'Thirty years after the bombs, water is money. You lead a caravan of six wagons across the '
        'dry Basin, two days from the next well. This morning you found the caravan that left a '
        'day ahead of you: every traveller dead, every water barrel full and untouched, and one '
        'set of boot prints leading north.',
    'flagship': false,
    'cover_url': null,
  },
  {
    'id': 'what-things-remember',
    'title': 'What Things Remember',
    'genre': 'Superpowers',
    'tagline': 'Your power woke today: what you hold shows you its memories.',
    'premise':
        'In Port Vesper, one teenager in a hundred wakes up with a power at sixteen. Yours came '
        'this morning: anything you hold shows you what it remembers. The first thing you picked '
        'up was your missing sister\'s phone, and what it showed you is not what the police were '
        'told.',
    'flagship': false,
    'cover_url': FakeAssets.city,
  },
];

void registerPremiseRoutes(FakeBackend b) {
  b.route('GET', '/v1/premises', (_) => FakeResponse.json(fakePremises));
}

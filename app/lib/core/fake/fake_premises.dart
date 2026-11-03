import '../json.dart';
import 'fake_backend.dart';
import 'fake_data.dart';

/// Fake starter premises (S1), the same eleven as the backend's catalog
/// (`backend/graph/drafting/catalog.py`): the flagship genres first. A few have no cover, as a
/// starter can until its cover is drawn. Owned by the discover work (WS15).
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
];

void registerPremiseRoutes(FakeBackend b) {
  b.route('GET', '/v1/premises', (_) => FakeResponse.json(fakePremises));
}

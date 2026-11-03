import '../json.dart';
import 'fake_backend.dart';
import 'fake_data.dart';

/// Fake starter premises (S1): the flagship genres first. Owned by the discover work (WS15).
const fakePremises = <JsonMap>[
  {
    'id': 'ninth-peak',
    'title': 'The Ninth Peak',
    'genre': 'Cultivation',
    'tagline': 'Crippled meridians. A forbidden library. A voice that knows your name.',
    'premise':
        'You are an outer disciple of the Azure Cloud Sect whose meridians were shattered in a '
        'duel. On the night you are to be expelled, a voice speaks to you from a sealed scroll in '
        'the forbidden library.',
    'flagship': true,
    'cover_url': FakeAssets.peaks,
  },
  {
    'id': 'ember-oath',
    'title': 'Oath of the Ember Knight',
    'genre': 'Knights and aura',
    'tagline': 'Your aura is the colour of the traitor king\'s.',
    'premise':
        'A squire in a kingdom where knights fight with aura, you awaken a crimson aura on the eve '
        'of your knighting. Only one man ever had that colour: the king your order executed.',
    'flagship': true,
    'cover_url': FakeAssets.castle,
  },
  {
    'id': 'guildless',
    'title': 'Guildless',
    'genre': 'Many races and monsters',
    'tagline': 'Ogres run the markets. Elves run the banks. You hunt without a licence.',
    'premise':
        'In Varrow, a river city of a dozen races, only guild hunters may take monster bounties. '
        'You take them anyway, and tonight the bounty board lists your own name.',
    'flagship': true,
    'cover_url': FakeAssets.forest,
  },
  {
    'id': 'second-dawn',
    'title': 'Second Dawn',
    'genre': 'Reincarnation',
    'tagline': 'You died on a crosswalk. You woke as a forgotten prince.',
    'premise':
        'Hit by a truck in Osaka, you wake as the sickly third prince of a dying kingdom, with your '
        'old memories and a gift no one has seen in a thousand years: you can stop time.',
    'flagship': true,
    'cover_url': FakeAssets.dawn,
  },
  {
    'id': 'naples-1974',
    'title': 'Naples, 1974',
    'genre': 'Grounded modern',
    'tagline': 'Everyone knows who shot your brother. No one will say it.',
    'premise':
        'Your brother was shot outside a café on Via Toledo. The families say it was a robbery. '
        'You have a week before the funeral, a borrowed Fiat and a debt to the wrong people.',
    'flagship': false,
    'cover_url': FakeAssets.city,
  },
  {
    'id': 'ninefold-drift',
    'title': 'Ninefold Drift',
    'genre': 'Science fiction',
    'tagline': 'The wreck is alive, and it wants to go home.',
    'premise':
        'A salvage pilot on the edge of charted space, you find a living ship inside the wreck of '
        'a war that officially never happened. Three fleets want it. It wants you.',
    'flagship': false,
    'cover_url': FakeAssets.nebula,
  },
  {
    'id': 'night-archive',
    'title': 'The Night Archive',
    'genre': 'Hidden supernatural',
    'tagline': 'Lisbon\'s vampires keep their contracts in your basement.',
    'premise':
        'You take the night shift at Lisbon\'s municipal archive and learn why it pays so well: the '
        'city\'s hidden houses file their treaties here, and one of them has gone missing.',
    'flagship': false,
    'cover_url': FakeAssets.city,
  },
];

void registerPremiseRoutes(FakeBackend b) {
  b.route('GET', '/v1/premises', (_) => FakeResponse.json(fakePremises));
}

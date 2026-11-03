import '../json.dart';
import 'fake_auth.dart';
import 'fake_backend.dart';
import 'fake_data.dart';
import 'fake_premises.dart';
import 'fake_stories.dart';

/// Fake drafting (docs/API.md, "Drafting a world and a character", G1, G2). Owned by the create
/// work (WS15).
///
/// Drafting is metered like the real one: a create, a revision or an edit that needs the model
/// checks the balance first (`402 out_of_credits`) and is charged per model call, unless it runs on
/// the player's own key (K2, K6). Edits that need no model are free, by the same rules as the
/// backend's `chain.plan_edit`. To try the app's error handling, put a trigger in the premise or
/// the instruction: `[fail:out_of_credits]`, `[fail:rate_limited]`, `[fail:quota_exceeded]`,
/// `[fail:unreadable_action]`, `[fail:bad_key]`, `[fail:llm_unavailable]` or
/// `[fail:version_conflict]`. `[fail:real_person]` in a premise, an instruction, a line or a rule
/// is refused at that field as naming a real person (G12), at no cost.
class FakeDraftState {
  final drafts = <String, (String ownerId, JsonMap draft)>{};

  /// The draft each started story came from, so its memory can show the drafted character.
  final byStory = <String, JsonMap>{};

  JsonMap get(String id, String userId) {
    final entry = drafts[id];
    if (entry == null || entry.$1 != userId) throw const FakeError.notFound('No such draft');
    return entry.$2;
  }

  /// A draft about to change: not started yet, and at the version the app last saw (T10).
  JsonMap editable(FakeRequest r) {
    final draft = get(r.param('id'), r.userId!);
    if (draft['story_id'] case final String storyId) {
      throw FakeError(403, 'forbidden', 'This draft has started.', {'story_id': storyId});
    }
    final expected = (r.json['expected_version'] as num?)?.toInt();
    if (expected != null && expected != draft['version']) {
      throw FakeError(409, 'version_conflict', 'The draft changed.', {
        'current_version': draft['version'],
      });
    }
    return draft;
  }
}

/// What a draft call costs in the fake, per model call.
const _draftCents = 3;

void registerDraftRoutes(FakeBackend b) {
  final state = b.data.drafts;

  b.route('POST', '/v1/drafts', (r) async {
    final premiseId = r.json['premise_id'] as String?;
    final starter = fakePremises.where((p) => p['id'] == premiseId).firstOrNull;
    if (premiseId != null && starter == null) {
      throw const FakeError.validation('No starter premise has this id.');
    }
    final premise = (r.json['premise'] as String? ?? starter?['premise'] as String? ?? '').trim();
    if (premise.length < 10 || premise.length > 4000) {
      throw const FakeError.validation('A premise is 10 to 4000 characters.');
    }
    final rating = r.json['rating'] as String? ?? 'teen';
    _checkRating(b, r, rating);
    if (r.json['premise'] case final String own) _refuseRealPeople([('premise', own)]);
    _failOn(premise);
    await _meter(b, r, calls: 1);
    _failOn(premise, model: true);

    final id = b.data.id('draft');
    final now = b.now().toUtc().toIso8601String();
    final drafted = _drafted(starter, premise);
    final draft = <String, dynamic>{
      'id': id,
      'premise': premise,
      'premise_id': starter?['id'],
      'rating': rating,
      ...drafted,
      'version': 1,
      'story_id': null,
      'created_at': now,
      'updated_at': now,
    };
    if (r.json['advanced'] case final JsonMap advanced) _applyAdvanced(draft, advanced);
    state.drafts[id] = (r.userId!, draft);
    _charge(b, r, calls: 1);
    return FakeResponse.json(draft, status: 201);
  });

  b.route('GET', '/v1/drafts/:id', (r) => FakeResponse.json(state.get(r.param('id'), r.userId!)));

  b.route('PATCH', '/v1/drafts/:id', (r) async {
    final draft = state.editable(r);
    final body = r.json;
    if (body['rating'] case final String rating) _checkRating(b, r, rating);
    for (final key in ['world_lines', 'character_lines']) {
      final lines = body[key] as List?;
      if (lines != null && (lines.length > 20 || lines.any((l) => (l as String).length > 300))) {
        throw const FakeError.validation('Up to 20 lines of 300 characters each.');
      }
    }
    final advanced = body['advanced'] as JsonMap? ?? const {};
    if (advanced['rules'] case final List rules
        when rules.any((rule) => ((rule as JsonMap)['text'] as String? ?? '').isEmpty)) {
      throw const FakeError.validation('A rule is 1 to 300 characters.');
    }
    _refuseRealPeople([
      ..._newTexts('world_lines', body['world_lines'] as List?, draft['world_lines'] as List),
      ..._newTexts(
        'character_lines',
        body['character_lines'] as List?,
        draft['character_lines'] as List,
      ),
      ..._newTexts(
        'advanced.rules',
        [for (final rule in advanced['rules'] as List? ?? const []) (rule as JsonMap)['text']],
        [
          for (final rule in (draft['advanced'] as JsonMap)['rules'] as List)
            (rule as JsonMap)['text'],
        ],
        leaf: '.text',
      ),
    ]);
    final calls = _editCalls(draft, body, advanced);
    final words = [
      ...?body['world_lines'] as List?,
      ...?body['character_lines'] as List?,
    ].join(' ');
    _failOn(words);
    await _meter(b, r, calls: calls);
    _failOn(words, model: true);

    for (final key in ['world_lines', 'character_lines']) {
      if (body[key] case final List lines) draft[key] = _clean(lines);
    }
    if (body['rating'] case final String rating) draft['rating'] = rating;
    _applyAdvanced(draft, advanced);
    _charge(b, r, calls: calls);
    return FakeResponse.json(_saved(b, draft));
  });

  b.route('POST', '/v1/drafts/:id/revise', (r) async {
    final draft = state.editable(r);
    final key = r.json['target'] == 'character' ? 'character_lines' : 'world_lines';
    final instruction = (r.json['instruction'] as String? ?? '').trim();
    if (instruction.isEmpty || instruction.length > 1000) {
      throw const FakeError.validation('Say what to change, in up to 1000 characters.');
    }
    _refuseRealPeople([('instruction', instruction)]);
    _failOn(instruction);
    await _meter(b, r, calls: 1);
    _failOn(instruction, model: true);
    final lines = [...draft[key] as List, _asLine(instruction)];
    draft[key] = lines.length > 10 ? [lines.first, ...lines.skip(lines.length - 9)] : lines;
    _charge(b, r, calls: 1);
    return FakeResponse.json(_saved(b, draft));
  });

  b.route('POST', '/v1/drafts/:id/start', (r) {
    final draft = state.get(r.param('id'), r.userId!);
    // Starting again returns the same story.
    if (draft['story_id'] case final String storyId) {
      return FakeResponse.json({'story_id': storyId, 'version': 1});
    }
    final story = b.data.stories.add(
      FakeStory(
        id: b.data.id('story'),
        ownerId: r.userId!,
        title: draft['title'] as String,
        genre: draft['genre'] as String,
        premise: draft['premise'] as String,
        rating: draft['rating'] as String,
        updatedAt: b.now(),
        coverUrl:
            fakePremises.where((p) => p['id'] == draft['premise_id']).firstOrNull?['cover_url']
                as String? ??
            FakeAssets.forGenre(draft['genre'] as String),
      ),
    );
    final advanced = draft['advanced'] as JsonMap;
    story.settings = {
      ...story.settings,
      'difficulty': advanced['difficulty'],
      'event_frequency': advanced['event_frequency'],
      ...?r.json['settings'] as JsonMap?,
    };
    story.version = 1;
    draft['story_id'] = story.id;
    state.byStory[story.id] = draft;
    return FakeResponse.json({'story_id': story.id, 'version': story.version});
  });
}

JsonMap _saved(FakeBackend b, JsonMap draft) => draft
  ..['version'] = (draft['version'] as int) + 1
  ..['updated_at'] = b.now().toUtc().toIso8601String();

/// F8: an account under 17 drafts Teen only.
void _checkRating(FakeBackend b, FakeRequest r, String rating) {
  if (rating != 'teen' && rating != 'mature') {
    throw const FakeError.validation('A rating is teen or mature.');
  }
  final limit = fakeMaxRating(b.data.auth.users[r.userId]?['birth_date'] as String?, b.now());
  if (rating == 'mature' && limit != 'mature') {
    throw const FakeError(403, 'forbidden', 'This rating is above your account\'s limit.');
  }
}

/// G12: a text of the player's that names a real living person is refused at its field, before
/// any model call. The fake's real person is the `[fail:real_person]` trigger.
void _refuseRealPeople(List<(String, Object?)> texts) {
  for (final (field, text) in texts) {
    if (text is String && text.contains('[fail:real_person]')) {
      const message =
          'The person you named is a real person, and stories only have fictional people. '
          'Try someone made up instead.';
      throw FakeError(400, 'validation_error', message, {
        'fields': [
          {'field': field, 'source': 'body', 'message': message, 'type': 'real_person'},
        ],
      });
    }
  }
}

/// The player's own texts in a list, by dotted path: those not already in the draft.
List<(String, Object?)> _newTexts(
  String field,
  List<Object?>? texts,
  List<Object?> kept, {
  String leaf = '',
}) {
  final same = {for (final text in kept) _normal(text)};
  return [
    for (final (i, text) in (texts ?? const []).indexed)
      if (!same.contains(_normal(text))) ('$field.$i$leaf', text),
  ];
}

/// Answers with the error a `[fail:code]` trigger names, as the real backend would: the meter's
/// refusals before any model call, and the model's own failures ([model]) after the time a call
/// takes.
void _failOn(String text, {bool model = false}) {
  final trigger = RegExp(r'\[fail:(\w+)\]').firstMatch(text)?.group(1);
  const fromModel = {'unreadable_action', 'bad_key', 'llm_unavailable'};
  if (trigger == null || fromModel.contains(trigger) != model) return;
  final error = switch (trigger) {
    'out_of_credits' => const FakeError(402, 'out_of_credits', 'Not enough credits.', {
      'balance_cents': 1.5,
      'available_cents': 1.5,
    }),
    'rate_limited' => const FakeError(429, 'rate_limited', 'Slow down.', {'retry_after_s': 20}),
    'quota_exceeded' => const FakeError(429, 'quota_exceeded', 'Daily limit reached.', {
      'resets_at': '2026-11-04T00:00:00Z',
    }),
    'unreadable_action' => const FakeError(422, 'unreadable_action', 'The request was blocked.'),
    'bad_key' => const FakeError(422, 'bad_key', 'The provider rejected the key.'),
    'llm_unavailable' => const FakeError(503, 'llm_unavailable', 'The model failed twice.'),
    'version_conflict' => const FakeError(409, 'version_conflict', 'The draft changed.', {
      'current_version': 99,
    }),
    _ => null,
  };
  if (error != null) throw error;
}

/// Checks the balance before a model call, then takes the time drafting takes.
Future<void> _meter(FakeBackend b, FakeRequest r, {required int calls}) async {
  if (calls == 0) return;
  final balance = b.data.account.balanceOf(r.userId!);
  if (!r.usesOwnKey && balance < _draftCents) {
    throw FakeError(402, 'out_of_credits', 'Not enough credits.', {
      'balance_cents': balance,
      'available_cents': balance,
    });
  }
  if (b.pace.drafting > Duration.zero) await Future<void>.delayed(b.pace.drafting);
}

void _charge(FakeBackend b, FakeRequest r, {required int calls}) {
  if (calls == 0 || r.usesOwnKey) return;
  b.data.account.charge(r.userId!, kind: 'draft', cents: _draftCents * calls, now: b.now());
}

String _normal(Object? text) => (text as String? ?? '').split(RegExp(r'\s+')).join(' ').trim();

List<String> _clean(List<Object?> lines) => [
  for (final line in lines)
    if (_normal(line).isNotEmpty) _normal(line),
];

/// How many model calls an edit needs, by the backend's rules (`chain.plan_edit`): rewritten
/// lines, rules or gift, and lowering the rating to Teen.
int _editCalls(JsonMap draft, JsonMap body, JsonMap advanced) {
  var world = false;
  var character = false;
  if (body['rating'] == 'teen' && draft['rating'] == 'mature') world = character = true;
  if (advanced['rules'] case final List rules) {
    // The player's words normalized, the drafted ones as they are, as `plan_edit` compares.
    final after = [
      for (final rule in rules.cast<JsonMap>())
        if (_normal(rule['text']).isNotEmpty) '${rule['id']}|${_normal(rule['text'])}',
    ];
    final before = [
      for (final rule in ((draft['advanced'] as JsonMap)['rules'] as List).cast<JsonMap>())
        '${rule['id']}|${rule['text']}',
    ];
    if (after.join('\n') != before.join('\n')) world = true;
  }
  if (body['world_lines'] case final List lines
      when _clean(lines).join('\n') != (draft['world_lines'] as List).join('\n')) {
    world = true;
  }
  if (body['character_lines'] case final List lines
      when _clean(lines).join('\n') != (draft['character_lines'] as List).join('\n')) {
    character = true;
  }
  final gift = advanced['gift_strength'];
  if (gift != null && gift != 'none' && gift != (draft['advanced'] as JsonMap)['gift_strength']) {
    character = true;
  }
  return (world ? 1 : 0) + (character ? 1 : 0);
}

void _applyAdvanced(JsonMap draft, JsonMap advanced) {
  final current = draft['advanced'] as JsonMap;
  for (final key in ['physics', 'difficulty', 'event_frequency']) {
    if (advanced[key] case final String value) current[key] = value;
  }
  if (advanced['rules'] case final List rules) {
    final taken = <String>{};
    current['rules'] = [
      for (final rule in rules.cast<JsonMap>())
        if (_normal(rule['text']).isNotEmpty)
          {
            'id': _ruleId(rule, current['rules'] as List, taken),
            'text': _normal(rule['text']),
            'fixed': rule['fixed'] ?? true,
          },
    ];
  }
  if (advanced['gift_strength'] case final String gift when gift != current['gift_strength']) {
    current['gift_strength'] = gift;
    final lines = [
      for (final line in draft['character_lines'] as List)
        if (!(line as String).startsWith('Gift:')) line,
    ];
    draft['character_lines'] = [...lines, ?_giftLine(gift)];
  }
}

String _ruleId(JsonMap rule, List<Object?> current, Set<String> taken) {
  final known = current.cast<JsonMap>().any((r) => r['id'] == rule['id']);
  var id = known && rule['id'] != null
      ? rule['id'] as String
      : _normal(rule['text']).toLowerCase().replaceAll(RegExp(r'[^a-z0-9]+'), '-');
  if (id.length > 40) id = id.substring(0, 40);
  var unique = id;
  for (var n = 2; taken.contains(unique); n++) {
    unique = '$id-$n';
  }
  taken.add(unique);
  return unique;
}

String? _giftLine(String gift) => switch (gift) {
  'small' => 'Gift: a small edge, a feel for danger a moment before it arrives.',
  'rare' => 'Gift: a rare talent the world has seen only a handful of times.',
  'overpowered' => 'Gift: time stop that lasts three heartbeats and needs a breath to recharge.',
  _ => null,
};

/// A plain-words change, as a line of the summary: "add hidden vampires" becomes
/// "Hidden vampires."
String _asLine(String instruction) {
  var text = instruction.replaceAll(RegExp(r'\[[^\]]*\]'), '').trim();
  text = text.replaceFirst(
    RegExp(r'^(please\s+)?(add|include|give me|make it|make)\s+', caseSensitive: false),
    '',
  );
  if (text.isEmpty) text = instruction;
  text = text[0].toUpperCase() + text.substring(1);
  return RegExp(r'[.!?]$').hasMatch(text) ? text : '$text.';
}

JsonMap _rule(String id, String text, {bool fixed = true}) => {
  'id': id,
  'text': text,
  'fixed': fixed,
};

/// The drafted world and character: written out for the flagship starters and the Naples story,
/// and a general draft that follows the premise for the rest.
JsonMap _drafted(JsonMap? starter, String premise) {
  final drafted = switch (starter?['id']) {
    'outer-disciple' => <String, dynamic>{
      'tone': 'Hungry, proud and a little desperate',
      'world_lines': [
        'Cultivation world: qi is real and everywhere, and that won\'t change.',
        'Realms run from Qi Condensation through Foundation Establishment and Core Formation to '
            'Nascent Soul and beyond.',
        'The Azure Cloud Sect rules the eastern ranges from nine peaks: an outer court, an inner '
            'court and the elders above them.',
        'The ranking tournament starts in two days. The last ten outer disciples are sent down '
            'the mountain.',
        'Rival sects test the Azure Cloud for weakness while its patriarch stays in seclusion.',
        'Senior Brother Zhao leads the outer court\'s strongest clique, and he has noticed you.',
      ],
      'character_lines': [
        'Lin Feng, 16. Third stage of Qi Condensation, the lowest in the outer court.',
        'Stubborn and patient, better at reading people than at fighting them.',
        'Knows every shortcut on the outer peak and every cook in the kitchens.',
        'Carries a cracked jade pendant from a mother he never met.',
      ],
      'rules': [
        _rule('qi-is-real', 'Qi cultivation is real, and everyone knows it.'),
        _rule(
          'realm-gap',
          'A cultivator a full realm above you is out of reach in a straight fight.',
          fixed: false,
        ),
        _rule('dead-stay-dead', 'The dead stay dead.'),
      ],
      'gift_strength': 'none',
    },
    'three-heartbeats' => <String, dynamic>{
      'tone': 'Quiet menace with flashes of wonder',
      'world_lines': [
        'Cultivation world: qi is real and everywhere, and that won\'t change.',
        'Nobody here knows that souls can cross between worlds. Nobody would believe you.',
        'The Moonfall Sect trains disciples from Qi Condensation up, and its outer court is cruel '
            'to the weak.',
        'The boy whose body you woke in made enemies, and one of them waits for you by the well.',
        'As far as anyone knows, time stop exists only in you.',
      ],
      'character_lines': [
        'Wei Lan, 16. Second stage of Qi Condensation, in a borrowed body.',
        'Every memory of a past life in our world, as a programmer who died at thirty-one.',
        'Calm under pressure, curious, and short on patience for bullies.',
        'Gift: time stop that lasts three heartbeats and needs a breath to recharge.',
      ],
      'rules': [
        _rule('qi-is-real', 'Qi cultivation is real, and everyone knows it.'),
        _rule(
          'time-stop-limits',
          'Time stop lasts three heartbeats and needs a breath to recharge.',
          fixed: false,
        ),
        _rule('dead-stay-dead', 'The dead stay dead.'),
      ],
      'gift_strength': 'overpowered',
    },
    'ashen-squire' => <String, dynamic>{
      'tone': 'Grim chivalry with a stubborn heart',
      'world_lines': [
        'Knights and aura: aura is real and ranks every knight, and that won\'t change.',
        'Ranks run from squire to knight, aura master and sword saint.',
        'The kingdom of Valdmark, its royal order, and three ducal houses that hate each other.',
        'The trial of knighthood is in nine days.',
        'Your master was found dead in the stables this morning, his sword still sheathed.',
      ],
      'character_lines': [
        'Edric Vale, 19. A squire who has never drawn a spark of aura.',
        'Quick with a sword, quicker with excuses, loyal to a fault.',
        'Owns a borrowed horse, a dead man\'s sword and a debt to the quartermaster.',
      ],
      'rules': [
        _rule('aura-is-real', 'Aura is real, and every knight is ranked by it.'),
        _rule(
          'aura-ranks',
          'A knight a rank above you wins a fair duel, unless you change the terms.',
          fixed: false,
        ),
        _rule('dead-stay-dead', 'The dead stay dead.'),
      ],
      'gift_strength': 'none',
    },
    'naples-vendetta' => <String, dynamic>{
      'tone': 'Slow-burning noir',
      'world_lines': [
        'Grounded: no magic and nothing supernatural, and that won\'t change.',
        'Naples, 1974. Phones, cars and pistols, and police who can mostly be bought.',
        'The Esposito family has three crews, and its council names the next boss in ten days.',
        'Your father was shot outside his own club a week ago. The family says it was an '
            'outsider.',
        'Carmine, the underboss, already acts as if the chair is his.',
      ],
      'character_lines': [
        'Luca Esposito, 24. Steady nerves, good with a pistol and a knife, a hot temper.',
        'No powers, since this world has none.',
        'His father\'s name, three loyal soldiers and a grudge.',
      ],
      'rules': [
        _rule('no-supernatural', 'Nothing supernatural exists.'),
        _rule('slow-healing', 'Wounds heal the way they do in our world: slowly.'),
        _rule('word-travels', 'Word travels by phone within minutes.', fixed: false),
      ],
      'gift_strength': 'none',
    },
    _ => <String, dynamic>{
      'tone': 'Tense, with room for wonder',
      'world_lines': [
        'Where it starts: ${_firstSentence(premise)}',
        'What is real in this world holds for the whole story; how far it goes can still change.',
        'Three factions want the same thing, and only one of them knows you exist.',
        'News travels at the speed of a fast horse, and rumours travel faster.',
      ],
      'character_lines': [
        'Someone with more nerve than standing.',
        'Owes a favour to the wrong person.',
        'Carries one thing they would die before losing.',
      ],
      'rules': [
        _rule('dead-stay-dead', 'The dead stay dead.'),
        _rule('power-has-a-price', 'Power grows through effort, teachers and luck.', fixed: false),
      ],
      'gift_strength': 'none',
    },
  };
  return {
    'title': starter?['title'] ?? 'A story of your own',
    'genre': starter?['genre'] ?? 'Your own',
    'tone': drafted['tone'],
    'world_lines': drafted['world_lines'],
    'character_lines': drafted['character_lines'],
    'advanced': {
      'physics': 'fun_first',
      'rules': drafted['rules'],
      'gift_strength': drafted['gift_strength'],
      'difficulty': 'balanced',
      'event_frequency': 'normal',
    },
  };
}

String _firstSentence(String premise) {
  final text = premise.replaceAll(RegExp(r'\[[^\]]*\]'), '').trim();
  final end = RegExp(r'[.!?](\s|$)').firstMatch(text)?.end ?? text.length;
  final sentence = text.substring(0, end).trim();
  return sentence.length <= 200 ? sentence : '${sentence.substring(0, 199).trimRight()}…';
}

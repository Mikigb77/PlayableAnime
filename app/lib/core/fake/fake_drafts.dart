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
/// `[fail:version_conflict]`. `[fail:real_person]` in a premise, an instruction, a plain field or
/// a rule is refused at that field as naming a real person (G12), at no cost.
///
/// A draft is kept as its records (`_world`, `_character`, `_said`, `_hidden`), and what the app
/// gets is written from them each time ([draftView]), as the backend writes its summary from the
/// world: the plain fields change at once (G1, G2), and how the story starts shows only when the
/// player's own words name it (G1).
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
    // S10: the draft is written in the app's language, and its story starts in it.
    final language = r.json['language'] as String? ?? 'en';
    if (!const {'en', 'es', 'ca'}.contains(language)) {
      throw const FakeError.validation('Unsupported language.');
    }
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
      'language': language,
      ...drafted,
      '_said': premise,
      'version': 1,
      'story_id': null,
      'created_at': now,
      'updated_at': now,
    };
    if (r.json['advanced'] case final JsonMap advanced) _applyAdvanced(draft, advanced);
    state.drafts[id] = (r.userId!, draft);
    _charge(b, r, calls: 1);
    return FakeResponse.json(draftView(draft), status: 201);
  });

  b.route(
    'GET',
    '/v1/drafts/:id',
    (r) => FakeResponse.json(draftView(state.get(r.param('id'), r.userId!))),
  );

  b.route('PATCH', '/v1/drafts/:id', (r) async {
    final draft = state.editable(r);
    final body = r.json;
    if (body['rating'] case final String rating) _checkRating(b, r, rating);
    final advanced = body['advanced'] as JsonMap? ?? const {};
    if (advanced['rules'] case final List rules
        when rules.any((rule) => ((rule as JsonMap)['text'] as String? ?? '').isEmpty)) {
      throw const FakeError.validation('A rule is 1 to 300 characters.');
    }
    final fields = _plainFields(draft, body);
    _refuseRealPeople([
      for (final MapEntry(:key, :value) in fields.entries)
        if (value is String) (key, value),
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
    final words = fields.values.whereType<String>().join(' ');
    _failOn(words);
    await _meter(b, r, calls: calls);
    _failOn(words, model: true);

    _applyFields(draft, fields);
    if (body['rating'] case final String rating) draft['rating'] = rating;
    _applyAdvanced(draft, advanced);
    _charge(b, r, calls: calls);
    return FakeResponse.json(draftView(_saved(b, draft)));
  });

  b.route('POST', '/v1/drafts/:id/revise', (r) async {
    final draft = state.editable(r);
    final character = r.json['target'] == 'character';
    final instruction = (r.json['instruction'] as String? ?? '').trim();
    if (instruction.isEmpty || instruction.length > 1000) {
      throw const FakeError.validation('Say what to change, in up to 1000 characters.');
    }
    final about = r.json['about'] as String?;
    if (about != null && !_kinds.contains(about)) {
      throw const FakeError.validation('No part of the summary is called that.');
    }
    _refuseRealPeople([('instruction', instruction)]);
    _failOn(instruction);
    await _meter(b, r, calls: 1);
    _failOn(instruction, model: true);
    // What the change names of how the story starts shows from here on (G1).
    draft['_said'] = '${draft['_said']}\n$instruction';
    final parts = (draft[character ? '_character' : '_world'] as List).cast<JsonMap>();
    final line = _asLine(instruction);
    // Asked at a part, the change lands there; else it is a new line of its own.
    final at = parts.where((part) => part['kind'] == about).firstOrNull;
    if (at != null) {
      at['text'] = '${at['text']} $line';
    } else {
      parts.add({'kind': character ? 'nature' : 'faction', 'text': line});
    }
    _charge(b, r, calls: 1);
    return FakeResponse.json(draftView(_saved(b, draft)));
  });

  b.route('POST', '/v1/drafts/:id/start', (r) {
    final draft = state.get(r.param('id'), r.userId!);
    // Starting again returns the same story.
    if (draft['story_id'] case final String storyId) {
      return FakeResponse.json({'story_id': storyId, 'version': 1});
    }
    // A stale copy starts nothing (T10).
    state.editable(r);
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
      // S10: the story starts in the draft's language, whatever an older app sends.
      'language': draft['language'] ?? 'en',
    };
    story.version = 1;
    draft['story_id'] = story.id;
    state.byStory[story.id] = draftView(draft);
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

/// How many model calls an edit needs, by the backend's rules (`chain.plan_edit`): rewritten
/// rules, a new gift, and lowering the rating to Teen. The plain fields need none.
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
    final parts = (draft['_character'] as List).cast<JsonMap>()
      ..removeWhere((part) => part['kind'] == 'power');
    if (_giftLine(gift) case final line?) parts.add({'kind': 'power', 'text': line});
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

/// The kinds a line of the summary has (docs/API.md, `DraftPartKind`).
const _kinds = {
  ...{'rule', 'era', 'ladder', 'peoples', 'faction'},
  ...{'deadline', 'question', 'person', 'connections', 'goal'},
  ...{'who', 'manner', 'standing', 'rank', 'skills', 'talents', 'traits', 'nature', 'power'},
  'belongings',
};

/// What tells of how the story starts, and what each kind counts as when it is kept back (G1).
const _openers = {
  'deadline': 'events',
  'question': 'questions',
  'person': 'people',
  'connections': 'people',
  'goal': null,
};

/// One screen of lines (G1).
const _screen = 10;

/// The draft as the app gets it: the summary written from the draft's records, part by part and
/// as plain lines, the character's plain fields, the ladder, and a count of what the story keeps
/// back of its start. A line of how the story starts is in it only when the player's own words
/// name it (`named`, G1).
JsonMap draftView(JsonMap draft) {
  final said = (draft['_said'] as String).toLowerCase();
  final kept = {...draft['_hidden'] as JsonMap};
  List<JsonMap> shown(String key) {
    final parts = <JsonMap>[];
    for (final part in (draft[key] as List).cast<JsonMap>()) {
      final opener = _openers.containsKey(part['kind']);
      if (!opener || (part['named'] as List).any((word) => said.contains(word as String))) {
        parts.add({'kind': part['kind'], 'text': part['text']});
      } else if (_openers[part['kind']] case final count?) {
        // Kept back: counted, never told.
        kept[count] = (kept[count] as int) + 1;
      }
    }
    return parts;
  }

  final character = draft['character'] as JsonMap;
  final rules = ((draft['advanced'] as JsonMap)['rules'] as List).cast<JsonMap>();
  final world = [
    for (final rule in [...rules.where((r) => r['fixed'] == true)].take(3))
      {'kind': 'rule', 'text': rule['text']},
    ...shown('_world'),
  ];
  final who = [character['name'], if (character['age'] != null) character['age']].join(', ');
  final person = [
    {'kind': 'who', 'text': '$who.'},
    if (character['manner'] case final String manner when manner.isNotEmpty)
      {'kind': 'manner', 'text': manner},
    if (character['standing'] case final String standing when standing.isNotEmpty)
      {'kind': 'standing', 'text': '$standing.'},
    ...shown('_character'),
  ];
  return {
    for (final MapEntry(:key, :value) in draft.entries)
      if (!key.startsWith('_')) key: value,
    'world_parts': world,
    'character_parts': person,
    'world_lines': [for (final part in world.take(_screen)) part['text']],
    'character_lines': [for (final part in person.take(_screen)) part['text']],
    'kept': kept,
  };
}

/// The plain fields an edit changes (G1, G2), by field as the API names them: the texts
/// normalized, a blank one refused at its field, and one sent back as it is left out.
Map<String, Object> _plainFields(JsonMap draft, JsonMap body) {
  final character = draft['character'] as JsonMap;
  final sent = body['character'] as JsonMap? ?? const {};
  final now = <String, Object?>{
    'title': draft['title'],
    'tone': draft['tone'],
    'character.name': character['name'],
    'character.looks': character['looks'],
    'character.manner': character['manner'],
  };
  final texts = <String, Object?>{
    'title': body['title'],
    'tone': body['tone'],
    'character.name': sent['name'],
    'character.looks': sent['looks'],
    'character.manner': sent['manner'],
  };
  final fields = <String, Object>{};
  for (final MapEntry(key: field, value: text) in texts.entries) {
    if (text == null) continue;
    final words = _normal(text);
    final most = field.endsWith('looks') || field.endsWith('manner') ? 300 : 80;
    if (words.isEmpty) {
      throw _fieldError(field, 'Write something here, or leave it as it is.', 'empty');
    }
    if (words.runes.length > most) {
      throw _fieldError(field, 'At most $most characters.', 'string_too_long');
    }
    if (words != now[field]) fields[field] = words;
  }
  if (sent['age'] case final Object age) {
    if (age is! int || age < 0 || age > 100000) {
      throw _fieldError('character.age', 'An age is a whole number from 0 up.', 'int_range');
    }
    if (age != character['age']) fields['character.age'] = age;
  }
  return fields;
}

FakeError _fieldError(String field, String message, String type) =>
    FakeError(400, 'validation_error', message, {
      'fields': [
        {'field': field, 'source': 'body', 'message': message, 'type': type},
      ],
    });

/// Writes the plain fields in, at once (G1, G2). A new name takes the old one's place wherever
/// the draft says it, and a new age where the looks give the old one as a number.
void _applyFields(JsonMap draft, Map<String, Object> fields) {
  final character = draft['character'] as JsonMap;
  if (fields['character.name'] case final String name) {
    final old = character['name'] as String;
    final first = old.split(' ').first;
    String renamed(String text) {
      text = text.replaceAll(old, name);
      // Their own first name too, but not a family's ("the Esposito family").
      return first.length >= 3 && first != old
          ? text.replaceAll(RegExp('\\b${RegExp.escape(first)}\\b'), name.split(' ').first)
          : text;
    }

    for (final key in ['_world', '_character']) {
      for (final part in (draft[key] as List).cast<JsonMap>()) {
        part['text'] = renamed(part['text'] as String);
      }
    }
    character['name'] = name;
  }
  if (fields['character.age'] case final int age) {
    if (character['age'] case final int old) {
      character['looks'] = (character['looks'] as String).replaceAll(RegExp('\\b$old\\b'), '$age');
    }
    character['age'] = age;
  }
  if (fields['title'] case final String title) draft['title'] = title;
  if (fields['tone'] case final String tone) draft['tone'] = tone;
  if (fields['character.looks'] case final String looks) character['looks'] = looks;
  if (fields['character.manner'] case final String manner) character['manner'] = manner;
}

JsonMap _part(String kind, String text, {List<String> named = const []}) => {
  'kind': kind,
  'text': text,
  'named': named,
};

/// The drafted world and character: written out for the flagship starters and the Naples story,
/// and a general draft that follows the premise for the rest. `named` are the words that name a
/// line of how the story starts, in lower case: it shows once the player's own words say one.
JsonMap _drafted(JsonMap? starter, String premise) {
  final genius = RegExp(r'\b(genius|prodigy)\b', caseSensitive: false).hasMatch(premise);
  final drafted = switch (starter?['id']) {
    'outer-disciple' => <String, dynamic>{
      'tone': 'Hungry, proud and a little desperate',
      'world': [
        _part('era', 'The eastern ranges, ruled from the nine peaks of the Azure Cloud Sect.'),
        _part(
          'ladder',
          'Cultivation realms: Qi Condensation, Foundation Establishment, Core Formation, '
              'Nascent Soul and beyond.',
        ),
        _part(
          'faction',
          'The Azure Cloud Sect: an outer court, an inner court and the elders above them.',
        ),
        _part(
          'faction',
          'The rival sects: they test the Azure Cloud for weakness while its patriarch stays in '
              'seclusion.',
        ),
        _part('deadline', 'The ranking tournament: in 2 days', named: ['tournament']),
        _part(
          'person',
          'Senior Brother Zhao: he leads the outer court\'s strongest clique, and he has noticed '
              'you.',
          named: ['zhao'],
        ),
      ],
      'character': {
        'name': 'Lin Feng',
        'age': 16,
        'people': 'Human',
        'standing': 'Outer disciple of the Azure Cloud Sect',
        'looks':
            'Thin and sharp-eyed, with a topknot gone loose and grey outer-court robes patched '
            'at both elbows.',
        'manner': 'Stubborn and patient, better at reading people than at fighting them.',
      },
      'parts': [
        _part('rank', 'Qi Condensation, early stage.'),
        _part('skills', 'Fair: the sword, herb lore. Novice: footwork.'),
        if (genius) _part('talents', 'One of a kind: The sword (anything fought with a blade).'),
        _part('nature', 'Stubborn, patient.'),
        _part('belongings', 'Carries a cracked jade pendant. 3 spirit stones.'),
        _part('goal', 'Goal: Keep your place on the mountain.', named: ['my goal', 'i want']),
      ],
      'ladder': {
        'name': 'Cultivation realms',
        'rungs': ['Qi Condensation', 'Foundation Establishment', 'Core Formation', 'Nascent Soul'],
        'more': true,
        'at': 0,
        'stage': 'early stage',
      },
      'hidden': {'people': 4, 'events': 2, 'questions': 2},
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
      'world': [
        _part('era', 'The Moonfall ranges, where nobody knows that souls can cross worlds.'),
        _part(
          'ladder',
          'Cultivation realms: Qi Condensation, Foundation Establishment, Core Formation and '
              'beyond.',
        ),
        _part(
          'faction',
          'The Moonfall Sect: it trains disciples from Qi Condensation up, and its outer court '
              'is cruel to the weak.',
        ),
        _part(
          'person',
          'The boy by the well: an enemy the body you woke in made.',
          named: ['well', 'enemy'],
        ),
      ],
      'character': {
        'name': 'Wei Lan',
        'age': 16,
        'people': 'Human',
        'standing': 'Outer disciple of the Moonfall Sect',
        'looks': 'Slight, with ink-stained fingers and a borrowed body\'s bruises still fading.',
        'manner': 'Calm under pressure, curious, and short on patience for bullies.',
      },
      'parts': [
        _part('rank', 'Qi Condensation, early stage.'),
        _part('skills', 'Skilled: logic and numbers. Novice: the sword.'),
        if (genius) _part('talents', 'Genius: Formations (patterns and their flaws).'),
        _part('nature', 'Calm, curious.'),
        _part(
          'power',
          'Time stop: the world holds still for three heartbeats. Needs a breath to recharge. '
              'Nobody knows of it.',
        ),
        _part('belongings', 'Carries a dead boy\'s sect token.'),
      ],
      'ladder': {
        'name': 'Cultivation realms',
        'rungs': ['Qi Condensation', 'Foundation Establishment', 'Core Formation'],
        'more': true,
        'at': 0,
        'stage': 'early stage',
      },
      'hidden': {'people': 3, 'events': 2, 'questions': 3},
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
      'world': [
        _part('era', 'The kingdom of Valdmark, three generations after the great fire.'),
        _part('ladder', 'Aura ranks: Squire, Knight, Aura master, Sword saint.'),
        _part('faction', 'The royal order: it grants knighthood and holds the trial.'),
        _part('faction', 'The three ducal houses: old, proud, and at each other\'s throats.'),
        _part('deadline', 'The trial of knighthood: in 9 days', named: ['trial']),
        _part(
          'question',
          'Who killed your master, and why was his sword still sheathed?',
          named: ['master'],
        ),
        _part(
          'person',
          'Ser Garrick: a knight of the order who wants you gone before the trial.',
          named: ['garrick'],
        ),
      ],
      'character': {
        'name': 'Edric Vale',
        'age': 19,
        'people': 'Human',
        'standing': 'Squire of the royal order',
        'looks':
            'Wiry and sunburnt, with cropped brown hair, a split lip that never quite heals and '
            'a gambeson handed down twice.',
        'manner': 'Quick with a sword, quicker with excuses, loyal to a fault.',
      },
      'parts': [
        _part('rank', 'Squire.'),
        _part('skills', 'Skilled: the sword. Fair: riding, mending tack.'),
        if (genius) _part('talents', 'One of a kind: The sword (anything fought with a blade).'),
        _part('nature', 'Loyal, proud. Slow to ask for help.'),
        _part('belongings', 'Carries a dead man\'s sword. Owns a borrowed horse. 4 copper marks.'),
        _part('goal', 'Goal: Earn your knighthood.', named: ['my goal', 'i want']),
      ],
      'ladder': {
        'name': 'Aura ranks',
        'rungs': ['Squire', 'Knight', 'Aura master', 'Sword saint'],
        'more': false,
        'at': 0,
        'stage': '',
      },
      'hidden': {'people': 4, 'events': 2, 'questions': 1},
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
      'world': [
        _part(
          'era',
          'Naples, 1974. Phones, cars and pistols, and police who can mostly be bought.',
        ),
        _part('faction', 'The Esposito family: three crews, and a council that names its boss.'),
        _part('deadline', 'The council names the next boss: in 10 days', named: ['council']),
        _part('question', 'Who inside the family killed your father?', named: ['killer', 'killed']),
        _part(
          'person',
          'Carmine: the underboss, who already acts as if the chair is his.',
          named: ['carmine'],
        ),
      ],
      'character': {
        'name': 'Luca Esposito',
        'age': 24,
        'people': '',
        'standing': 'Son of the boss of the Esposito family',
        'looks': '24, lean, dark hair combed back, a grey suit a size too sharp for a funeral.',
        'manner': 'Steady nerves and a hot temper he keeps on a short leash.',
      },
      'parts': [
        _part('skills', 'Skilled: pistols, knives. Fair: reading a room.'),
        _part('nature', 'Steady, hot-tempered.'),
        _part('power', 'No powers, since this world has none.'),
        _part('belongings', 'Carries his father\'s lighter and a pistol. 40,000 lire.'),
        _part('connections', 'Three loyal soldiers.', named: ['soldiers', 'loyal']),
      ],
      'ladder': null,
      'hidden': {'people': 5, 'events': 1, 'questions': 1},
      'rules': [
        _rule('no-supernatural', 'Nothing supernatural exists.'),
        _rule('slow-healing', 'Wounds heal the way they do in our world: slowly.'),
        _rule('word-travels', 'Word travels by phone within minutes.', fixed: false),
      ],
      'gift_strength': 'none',
    },
    _ => <String, dynamic>{
      'tone': 'Tense, with room for wonder',
      'world': [
        _part('era', 'Where it starts: ${_firstSentence(premise)}'),
        _part(
          'faction',
          'Three factions: they want the same thing, and only one of them knows you exist.',
        ),
        _part('deadline', 'The reckoning: in 3 days', named: ['three days', '3 days']),
        _part('person', 'Garrick: your rival.', named: ['garrick']),
      ],
      'character': {
        'name': 'Rowan',
        'age': 19,
        'people': '',
        'standing': '',
        'looks': 'Lean and weathered, with watchful eyes and a coat that has seen better roads.',
        'manner': 'More nerve than standing.',
      },
      'parts': [
        _part('skills', 'Fair: getting out of trouble. Novice: staying out of it.'),
        if (genius) _part('talents', 'One of a kind: The sword (anything fought with a blade).'),
        _part('nature', 'Restless, stubborn. Owes a favour to the wrong person.'),
        _part('belongings', 'Carries one thing they would die before losing.'),
      ],
      'ladder': null,
      'hidden': {'people': 3, 'events': 2, 'questions': 2},
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
    'character': drafted['character'],
    'ladder': drafted['ladder'],
    '_world': drafted['world'],
    '_character': drafted['parts'],
    '_hidden': drafted['hidden'],
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

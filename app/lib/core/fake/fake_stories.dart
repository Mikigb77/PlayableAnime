import 'dart:math' as math;

import '../../design/accent.dart';
import '../json.dart';
import 'fake_backend.dart';
import 'fake_data.dart';

/// Fake stories, memory and status (docs/API.md, "Stories"). The play screen work (WS14) owns
/// turns and status; the library and memory work (WS15) owns the list and memory.
class FakeStory {
  FakeStory({
    required this.id,
    required this.ownerId,
    required this.title,
    required this.genre,
    required this.premise,
    required this.updatedAt,
    this.rating = 'mature',
    this.coverUrl,
  });

  final String id;
  final String ownerId;
  String title;
  final String genre;
  final String premise;
  final String rating;
  String? coverUrl;
  DateTime updatedAt;

  int version = 0;

  /// In-world seconds since the story's epoch (W10).
  int worldS = 0;
  JsonMap settings = {
    'narration_length': 'medium',
    'difficulty': 'balanced',
    'event_frequency': 'normal',
    'images': 'key_moments',
    'suggestions': true,
    'language': 'en',
  };
  final scenes = <JsonMap>[];

  /// Whether the player has met Senior Sister Lan, whose first scene plans her portrait.
  bool metLan = false;

  /// How the story ended (N6), once it has: then it takes no more turns.
  JsonMap? ending;

  /// The player character, by id and name: the one an ending names (N6).
  String playerId = 'shen_yu';
  String playerName = 'Shen Yu';

  /// Who was drawn to carry the story on after its ending, until the player starts as them (N6).
  JsonMap? successor;

  /// The player character's heirs, offered at their ending (N6): a fake story has none unless a
  /// test or a demo gives it some.
  List<JsonMap> heirs = [];

  /// Someone new carries the story on, and their opening is still to be told (N6). [situation] is
  /// the moment it opens on.
  bool openingDue = false;
  String situation = '';

  int get turn => scenes.isEmpty ? 0 : scenes.last['turn'] as int;

  /// How many scenes back a death in the next scene could be rewound (C8): up to 5 on Story, 1 on
  /// Balanced and none on Brutal, and never back past the newest opening, so a rewind never
  /// reaches into someone else's story.
  int get rewindReach {
    final most = switch (settings['difficulty']) {
      'story' => 5,
      'balanced' => 1,
      _ => 0,
    };
    final opening = scenes.lastIndexWhere((s) => s['kind'] == 'opening');
    return math.min(most, scenes.length - math.max(opening, 0));
  }

  JsonMap get clock => {'world_s': worldS, 'label': fakeWorldLabel(worldS), 'timeline_id': 'main'};

  JsonMap toSummary() => {
    'id': id,
    'title': title,
    'genre': genre,
    'rating': rating,
    'turn': turn,
    'world_time_label': fakeWorldLabel(worldS),
    'cover_url': coverUrl,
    'ending': ending,
    'accent': settings['accent'],
    'updated_at': updatedAt.toUtc().toIso8601String(),
  };

  JsonMap toJson({int last = 20, bool allScenes = false}) => {
    'id': id,
    'title': title,
    'genre': genre,
    'rating': rating,
    'version': version,
    'settings': settings,
    'clock': clock,
    'scenes': allScenes ? scenes : scenes.sublist(scenes.length > last ? scenes.length - last : 0),
    'cover_url': coverUrl,
    'premise': premise,
    'ending': ending,
    'successor': ending == null ? null : successor,
    'heirs': ending == null || ending?['closed'] == true ? const <JsonMap>[] : heirs,
    'opening_due': openingDue,
  };
}

class FakeStoryState {
  final _stories = <String, FakeStory>{};

  Iterable<FakeStory> ownedBy(String userId) => _stories.values.where((s) => s.ownerId == userId);

  FakeStory add(FakeStory story) => _stories[story.id] = story;

  /// The caller's own story, or a 404 (a story that isn't yours looks like it doesn't exist).
  FakeStory get(String id, String userId) {
    final story = _stories[id];
    if (story == null || story.ownerId != userId) throw const FakeError.notFound('No such story');
    return story;
  }

  void delete(String id) => _stories.remove(id);

  void deleteAllOf(String userId) => _stories.removeWhere((_, s) => s.ownerId == userId);

  void seed({required String ownerId}) {
    final story = add(
      FakeStory(
        id: 'story_ninth_peak',
        ownerId: ownerId,
        title: 'The Ninth Peak',
        genre: 'Cultivation',
        premise:
            'An outer disciple with shattered meridians hears a voice in the forbidden library.',
        updatedAt: DateTime.utc(2026, 11, 3, 18, 40),
        coverUrl: FakeAssets.peaks,
      ),
    );
    story.scenes.addAll(_seedScenes());
    story.worldS = 60 * 8;
    story.version = 3;
  }
}

/// What drawing someone to carry a story on costs: one drafting call (N6, K2).
const _drawCents = 3;

/// Refuses a story that isn't at an ending the player left open (N6).
void _atOpenEnding(FakeStory story) {
  final (type, message) = switch (story.ending) {
    null => ('not_ended', 'This story hasn\'t reached an ending, so nobody needs to carry it on.'),
    {'closed': true} => ('closed', 'This story is closed. Start again from its premise instead.'),
    _ => (null, ''),
  };
  if (type == null) return;
  throw FakeError(400, 'validation_error', message, {
    'fields': [
      {'field': 'story_id', 'source': 'path', 'type': type, 'message': message},
    ],
  });
}

/// An heir as the drafter fills them in, grown up to 16 when they had years to grow (N6).
JsonMap _grownUp(JsonMap heir, int draws) {
  final unborn = heir['unborn'] == true;
  final name = unborn ? 'Shen Lian' : heir['name'] as String;
  final years = heir['years'] as int? ?? 0;
  final age = years > 0 ? 16 : heir['age'] as int?;
  return {
    'name': name,
    'age': age,
    'station': 'common',
    'one_in': 1,
    'master': false,
    'place': 'Azure Cloud Town',
    'people': null,
    'lines': [
      '$name, ${age ?? 16}.',
      'Raised at the foot of the mountain on stories of a parent who never came home.',
    ],
    'situation': 'On the morning $name turns ${age ?? 16}, a letter arrives from the sect.',
    'draws': draws,
    'heir': heir,
  };
}

/// The people drawn in turn to carry a story on: common folk first, then rarer ones.
const _successors = <JsonMap>[
  {
    'name': 'Mei Lin',
    'age': 23,
    'station': 'common',
    'one_in': 1,
    'master': false,
    'place': 'Azure Cloud Town',
    'people': null,
    'lines': [
      'Mei Lin, 23.',
      'A tea seller at the foot of the mountain, quick with sums and quicker with gossip.',
      'Skilled: brewing, haggling.',
    ],
    'situation': 'At dawn, Mei Lin sets out cups for the disciples who come down from the sect.',
  },
  {
    'name': 'Old Bo',
    'age': 54,
    'station': 'skilled',
    'one_in': 1000,
    'master': true,
    'place': 'Azure Cloud Town',
    'people': null,
    'lines': [
      'Old Bo, 54.',
      'The town\'s blacksmith, who hums while he works and never seems to tire.',
      'Expert: smithing. Master: the sword, though nobody has seen him hold one.',
    ],
    'situation': 'The forge is already hot when a sect messenger knocks at Old Bo\'s door.',
  },
  {
    'name': 'Lady Qiao Yun',
    'age': 31,
    'station': 'noble',
    'one_in': 1000,
    'master': false,
    'place': 'The capital',
    'people': null,
    'lines': [
      'Lady Qiao Yun, 31.',
      'A minor noble of the capital, sent to the sect with a letter she has not read.',
      'Skilled: etiquette, calligraphy.',
    ],
    'situation': 'Lady Qiao Yun\'s carriage stops at the sect gate as the bell rings noon.',
  },
];

void registerStoryRoutes(FakeBackend b) {
  final stories = b.data.stories;

  b.route('GET', '/v1/stories', (r) {
    final list = stories.ownedBy(r.userId!).toList()
      ..sort((a, b) => b.updatedAt.compareTo(a.updatedAt));
    return FakeResponse.json([for (final s in list) s.toSummary()]);
  });

  b.route('GET', '/v1/stories/:id', (r) {
    final last = _count(r.query('scenes'), fallback: 20, min: 0);
    return FakeResponse.json(stories.get(r.param('id'), r.userId!).toJson(last: last));
  });

  // Older scenes for scrollback, oldest first.
  b.route('GET', '/v1/stories/:id/scenes', (r) {
    final story = stories.get(r.param('id'), r.userId!);
    final before = int.tryParse(r.query('before') ?? '') ?? story.turn + 1;
    final limit = _count(r.query('limit'), fallback: 20, min: 1);
    final older = story.scenes.where((s) => (s['turn'] as int) < before).toList();
    return FakeResponse.json(older.sublist(older.length > limit ? older.length - limit : 0));
  });

  // A settings change applies from the next scene and doesn't move the version (S6, T10).
  b.route('PATCH', '/v1/stories/:id', (r) {
    final story = stories.get(r.param('id'), r.userId!);
    final title = r.json['title'];
    if (title != null) {
      final text = title is String ? title.trim() : '';
      if (text.isEmpty || text.length > 120) {
        throw const FakeError.validation('A title is 1 to 120 characters.');
      }
    }
    // S10: a story stays in the language it was set up in, so an older app's language is ignored.
    final settings = switch (r.json['settings']) {
      final JsonMap settings => {...settings}..remove('language'),
      final other => other,
    };
    if (settings != null) {
      if (settings is! JsonMap) throw const FakeError.validation('Settings are an object.');
      _checkSettings(settings);
    }
    if (title case final String title) story.title = title.trim();
    if (settings case final JsonMap settings) {
      story.settings = {...story.settings, ...settings}..removeWhere((_, v) => v == null);
    }
    return FakeResponse.json(story.toJson());
  });

  // N6: closes a story at its ending. Closing a closed story changes nothing.
  b.route('POST', '/v1/stories/:id/close', (r) {
    final story = stories.get(r.param('id'), r.userId!);
    final ending = story.ending;
    if (ending == null) {
      throw const FakeError.validation(
        'This story hasn\'t reached an ending. End it with /end first.',
      );
    }
    story.ending = {...ending, 'closed': true, 'rewind': 0};
    return FakeResponse.json(story.toJson());
  });

  // C8: takes a story back a few scenes from a death, to the world as it was then.
  b.route('POST', '/v1/stories/:id/rewind', (r) {
    final story = stories.get(r.param('id'), r.userId!);
    final expected = (r.json['expected_version'] as num?)?.toInt();
    if (expected != story.version) {
      throw FakeError(409, 'version_conflict', 'The story moved on.', {
        'current_version': story.version,
      });
    }
    final ending = story.ending;
    if (ending == null) {
      throw const FakeError.validation(
        'This story hasn\'t reached an ending, so there is nothing to rewind.',
      );
    }
    _atOpenEnding(story);
    final scenes = (r.json['scenes'] as num?)?.toInt() ?? 0;
    final most = ending['rewind'] as int? ?? 0;
    if (scenes < 1 || scenes > most) {
      throw FakeError(400, 'validation_error', 'This ending can\'t be rewound that far.', {
        'fields': [
          {
            'field': 'scenes',
            'source': 'body',
            'type': 'too_far',
            'message': 'This ending can\'t be rewound that far.',
          },
        ],
      });
    }
    story.scenes.removeRange(story.scenes.length - scenes, story.scenes.length);
    story
      ..worldS = (story.scenes.last['time'] as JsonMap?)?['world_end_s'] as int? ?? story.worldS
      ..ending = null
      ..successor = null
      ..version += 1
      ..updatedAt = b.now();
    return FakeResponse.json(story.toJson());
  });

  // N6: draws someone to carry the story on, charged like a draft. Drawing again replaces them.
  b.route('POST', '/v1/stories/:id/successor', (r) async {
    final story = stories.get(r.param('id'), r.userId!);
    _atOpenEnding(story);
    final balance = b.data.account.balanceOf(r.userId!);
    if (!r.usesOwnKey && balance < _drawCents) {
      throw FakeError(402, 'out_of_credits', 'Not enough credits.', {
        'balance_cents': balance,
        'available_cents': balance,
      });
    }
    final heirId = r.query('heir_id');
    final heir = heirId == null ? null : story.heirs.where((h) => h['id'] == heirId).firstOrNull;
    if (heirId != null && heir == null) {
      throw const FakeError(400, 'validation_error', 'Nobody by that id can carry this story on.', {
        'fields': [
          {
            'field': 'heir_id',
            'source': 'query',
            'type': 'unknown_heir',
            'message': 'Nobody by that id can carry this story on.',
          },
        ],
      });
    }
    if (heir?['lost'] == true) {
      // Fake-only: an heir who doesn't live through the years before they could act.
      final message = '${heir!['name']} didn\'t live to carry the story on. Choose someone else.';
      throw FakeError(400, 'validation_error', message, {
        'fields': [
          {'field': 'heir_id', 'source': 'query', 'type': 'heir_lost', 'message': message},
        ],
      });
    }
    if (b.pace.drafting > Duration.zero) await Future<void>.delayed(b.pace.drafting);
    final draws = ((story.successor?['draws'] as int?) ?? 0) + 1;
    story.successor = heir == null
        ? {..._successors[(draws - 1) % _successors.length], 'draws': draws}
        : _grownUp(heir, draws);
    if (!r.usesOwnKey) {
      b.data.account.charge(r.userId!, kind: 'draft', cents: _drawCents, now: b.now());
    }
    return FakeResponse.json(story.successor);
  });

  // N6: starts as the person drawn. The ending is lifted, and the next turn is their opening.
  b.route('POST', '/v1/stories/:id/carry-on', (r) {
    final story = stories.get(r.param('id'), r.userId!);
    final expected = (r.json['expected_version'] as num?)?.toInt();
    if (expected != story.version) {
      throw FakeError(409, 'version_conflict', 'The story moved on.', {
        'current_version': story.version,
      });
    }
    _atOpenEnding(story);
    final drawn = story.successor;
    if (drawn == null) {
      throw const FakeError(400, 'validation_error', 'Draw someone to carry the story on first.', {
        'fields': [
          {
            'field': 'story_id',
            'source': 'path',
            'type': 'no_successor',
            'message': 'Draw someone to carry the story on first.',
          },
        ],
      });
    }
    // An heir too young to act starts once the world has run on to the day they can.
    final years = (drawn['heir'] as JsonMap?)?['years'] as int? ?? 0;
    story
      ..worldS += years * 365 * 24 * 3600
      ..playerId = 'pc-${story.version}'
      ..playerName = drawn['name'] as String
      ..situation = drawn['situation'] as String
      ..ending = null
      ..successor = null
      ..heirs = []
      ..openingDue = true
      ..version += 1
      ..updatedAt = b.now();
    return FakeResponse.json(story.toJson());
  });

  b.route('DELETE', '/v1/stories/:id', (r) {
    stories.get(r.param('id'), r.userId!);
    stories.delete(r.param('id'));
    return FakeResponse.noContent;
  });

  b.route('GET', '/v1/stories/:id/memory', (r) {
    final story = stories.get(r.param('id'), r.userId!);
    if (story.id == 'story_ninth_peak') return FakeResponse.json(_seedMemory);
    return FakeResponse.json(_newMemory(b.data.drafts.byStory[story.id]));
  });

  b.route('GET', '/v1/stories/:id/status', (r) {
    final story = stories.get(r.param('id'), r.userId!);
    return FakeResponse.json({
      'character': {
        'name': 'Shen Yu',
        'lines': [
          'Outer disciple of the Azure Cloud Sect, to be expelled at dawn.',
          'Meridians: cut, not shattered, says the voice in the scroll.',
        ],
        // The seeded story's portrait is drawn; a new one's isn't yet.
        if (story.id == 'story_ninth_peak')
          'portrait_url': (_seedMemory['character'] as JsonMap)['portrait_url'],
      },
      'reputation': [
        {'name': 'Azure Cloud Sect', 'label': 'A failure they would rather forget'},
        {'name': 'Senior Sister Lan', 'label': 'Worried about you'},
      ],
      'clock': story.clock,
      'since': [
        {'text': 'The duel that broke you', 'ago_label': '3 months ago'},
        {'text': 'Elder Wen\'s verdict', 'ago_label': '6 hours ago'},
      ],
    });
  });
}

int _count(String? text, {required int fallback, required int min}) =>
    (int.tryParse(text ?? '') ?? fallback).clamp(min, 50);

/// The checks of the real endpoint: each setting takes one of its values, and a null tone or
/// color clears it (the color goes back to the genre's, S13).
void _checkSettings(JsonMap settings) {
  const choices = {
    'narration_length': {'short', 'medium', 'long'},
    'difficulty': {'story', 'balanced', 'brutal'},
    'event_frequency': {'calm', 'normal', 'dramatic'},
    'images': {'off', 'key_moments', 'more'},
  };
  // The server's `Accent` (backend/engine/context.py) has the app's accents.
  final accents = {for (final accent in GenreAccent.values) accent.name};
  for (final MapEntry(:key, :value) in settings.entries) {
    final ok = switch (key) {
      'tone' => value == null || (value is String && value.length <= 200),
      'accent' => value == null || accents.contains(value),
      'suggestions' => value is bool,
      _ => choices[key]?.contains(value) ?? false,
    };
    if (!ok) throw FakeError.validation('Unsupported $key.');
  }
}

/// "Day 1, dawn" style labels in the fake world's calendar. Stories open at 06:00 on day 1.
String fakeWorldLabel(int worldS) {
  final total = 6 * 3600 + worldS;
  final day = total ~/ 86400 + 1;
  final hour = (total % 86400) ~/ 3600;
  final part = switch (hour) {
    >= 5 && < 7 => 'dawn',
    >= 7 && < 12 => 'morning',
    >= 12 && < 17 => 'afternoon',
    >= 17 && < 20 => 'dusk',
    _ => 'night',
  };
  return 'Day $day, $part';
}

/// "+8 h", "+40 min", "+12 s".
String fakeDurationLabel(int seconds) => switch (seconds) {
  < 60 => '+$seconds s',
  < 3600 => '+${seconds ~/ 60} min',
  < 86400 => '+${seconds ~/ 3600} h',
  _ => '+${seconds ~/ 86400} d',
};

JsonMap _time(int start, int end) => {
  'world_start_s': start,
  'world_end_s': end,
  'label': fakeWorldLabel(end),
  // An opening takes no time, so it has no duration to show.
  if (end > start) 'duration_label': fakeDurationLabel(end - start),
};

/// A fresh copy each time, so one fake backend's changes never leak into another's.
List<JsonMap> _seedScenes() => <JsonMap>[
  {
    'turn': 1,
    'kind': 'opening',
    'narration':
        'The bell of the Azure Cloud Sect tolls nine times, and every stroke is meant for you.\n\n'
        'By dawn your name will be struck from the register of outer disciples. Elder Wen said it '
        'plainly, with the courtesy of a man closing a door: shattered meridians do not mend, and a '
        'sect is not a hospital.\n\n'
        'So you are here, in the forbidden library, where the lamps burn without oil and the shelves '
        'breathe dust like sleeping animals. You came to steal one book before they throw you down '
        'the mountain. Instead, a sealed scroll on the highest shelf has begun to whisper your name.',
    'choices': [
      {'id': 'c1', 'label': 'Break the seal and unroll the scroll', 'kind': 'thread'},
      {'id': 'c2', 'label': 'Answer the voice, quietly', 'kind': 'thread'},
      {'id': 'c3', 'label': 'Find Senior Sister Lan before dawn', 'kind': 'personal'},
    ],
    'standing_actions': ['wait', 'observe'],
    'time': _time(0, 0),
    'details': {'steps': <Object>[]},
    'image': {
      'planned': true,
      'kind': 'scene',
      'status': 'ready',
      'image_id': 'img_story_ninth_peak_1',
      'url': FakeAssets.peaks,
    },
    'portraits': <Object>[],
    'blocked': false,
    'created_at': '2026-11-03T18:31:00Z',
  },
  {
    'turn': 2,
    'kind': 'action',
    'player_action': 'I answer the voice, quietly. Who are you?',
    'input_mode': 'voice',
    'narration':
        'Your own voice sounds small in the stacks. For a long moment nothing answers but the '
        'lamps.\n\n'
        'Then the scroll unrolls itself a hand\'s width, and the voice comes again, closer, dry as '
        'old paper. *Someone who also had a door closed on them,* it says. *Nine hundred years ago, '
        'on this mountain. Your meridians are not shattered, child. They were cut. Carefully.*\n\n'
        'Footsteps on the stair below. Lantern light swings across the ceiling: Old Gu, the night '
        'warden, is making his round early.',
    'choices': [
      {'id': 'c1', 'label': 'Take the scroll and run for the window', 'kind': 'thread'},
      {'id': 'c2', 'label': 'Hide behind the shelves and listen', 'kind': 'thread'},
      {'id': 'c3', 'label': 'Greet Old Gu and lie', 'kind': 'personal'},
      {'id': 'c4', 'label': 'Ask the voice to prove it, right now', 'kind': 'wild'},
    ],
    'standing_actions': ['wait', 'observe'],
    'time': _time(0, 120),
    'details': {
      'steps': [
        {
          'text': 'Speak to the voice',
          'class': 'certain',
          'reason': 'Nothing stops you from talking.',
        },
      ],
    },
    'portraits': [
      {'character_id': 'voice', 'name': 'The voice in the scroll', 'url': FakeAssets.portrait(1)},
    ],
    'blocked': false,
    'created_at': '2026-11-03T18:35:00Z',
  },
  {
    'turn': 3,
    'kind': 'choice',
    'player_action': 'Take the scroll and run for the window',
    'input_mode': 'choice',
    'narration':
        'The scroll is warm, like something alive. You tuck it inside your robe and run.\n\n'
        'You are three steps from the window when the wards wake. Every lamp in the library flares '
        'white, and somewhere above, the great bronze bell begins to ring out of turn. Not the slow '
        'nine strokes of your expulsion: the fast, ragged alarm the sect has not sounded in your '
        'lifetime.\n\n'
        'Below the window the cliff path is empty. Across the courtyard, doors are opening.',
    'choices': [
      {'id': 'c1', 'label': 'Climb down the cliff path in the dark', 'kind': 'thread'},
      {
        'id': 'c2',
        'label': 'Hide the scroll in the library and walk out empty-handed',
        'kind': 'thread',
      },
      {'id': 'c3', 'label': 'Run to Senior Sister Lan\'s pavilion', 'kind': 'personal'},
    ],
    'standing_actions': ['wait', 'observe'],
    'time': _time(120, 480),
    'event': {'size': 'local', 'title': 'The library alarm wakes the sect'},
    'details': {
      'steps': [
        {
          'text': 'Take the scroll from the shelf',
          'class': 'certain',
          'reason': 'It sits within reach, and nothing guards it but the wards.',
        },
        {
          'text': 'Reach the window before the wards wake',
          'class': 'contested',
          'reason': 'The wards answer anyone who carries a sealed text past the threshold.',
          'roll': {'odds_label': 'about even', 'result': 'failure', 'seed': 'fake-3-2'},
        },
      ],
      'stopped_at_step': 1,
    },
    'image': {'planned': true, 'kind': 'scene', 'status': 'planned'},
    'portraits': [
      {'character_id': 'voice', 'name': 'The voice in the scroll', 'url': FakeAssets.portrait(1)},
      {'character_id': 'gu', 'name': 'Old Gu', 'url': FakeAssets.portrait(2)},
    ],
    'blocked': false,
    'created_at': '2026-11-03T18:40:00Z',
  },
];

/// The seeded story's memory: only what Shen Yu knows (C6), worded as `engine.visibility` words it.
const _seedMemory = <String, Object?>{
  'character': {
    'name': 'Shen Yu',
    'lines': [
      'Outer disciple of the Azure Cloud Sect, to be expelled at dawn.',
      'Meridians cut, not shattered, says the voice in the scroll.',
      'Carries a sealed scroll that speaks.',
    ],
    'portrait_url': 'asset:assets/fake/portrait-3.jpg',
  },
  'people': [
    {
      'id': 'voice',
      'name': 'The voice in the scroll',
      'lines': ['Claims to have been cast out of this sect nine hundred years ago.'],
      'attitude_label': 'Curious about you',
      'portrait_url': 'asset:assets/fake/portrait-2.jpg',
      'status_label': 'Bound to the scroll',
    },
    {
      'id': 'lan',
      'name': 'Senior Sister Lan',
      'lines': ['The only one who visited you after the duel.'],
      'attitude_label': 'Fond of you',
      'portrait_url': 'asset:assets/fake/portrait-4.jpg',
      'status_label': 'Alive',
    },
    {
      'id': 'gu',
      'name': 'Old Gu',
      'lines': ['Night warden of the library. Started his round early.'],
      'attitude_label': 'Wary',
      'portrait_url': 'asset:assets/fake/portrait-1.jpg',
      'status_label': 'Alive',
    },
    {
      'id': 'wen',
      'name': 'Elder Wen',
      'lines': ['Signed your expulsion.'],
      'status_label': 'Alive',
    },
    {
      'id': 'master-hu',
      'name': 'Master Hu',
      'lines': ['Your first teacher. Fell from the cliff path last winter, they say.'],
      'status_label': 'Presumed dead',
    },
  ],
  'places': [
    {
      'id': 'library',
      'name': 'The forbidden library',
      'lines': ['Lamps that burn without oil. Wards on every sealed text.'],
      'image_url': 'asset:assets/fake/scene-peaks.jpg',
    },
    {
      'id': 'cliff-path',
      'name': 'The cliff path',
      'lines': ['The back way down the outer peak, unlit and unguarded.'],
    },
  ],
  'factions': [
    {
      'id': 'azure',
      'name': 'Azure Cloud Sect',
      'lines': ['Ninth-ranked sect of the eastern ranges.'],
      'standing_label': 'They see a failure; nobody fears you',
    },
  ],
  'goals': [
    {'id': 'g1', 'text': 'Find out who cut your meridians'},
  ],
  'leads': [
    {'id': 'l1', 'text': 'The voice says the cut was careful', 'expires_label': null},
    {
      'id': 'l2',
      'text': 'Senior Sister Lan will wait at her pavilion',
      'expires_label': 'Until dawn',
    },
  ],
  'rumors': [
    {
      'id': 'r1',
      'text': 'Elder Wen once studied forbidden arts',
      'heard_label': 'Heard from a kitchen servant',
      'certainty': 'unconfirmed',
      'unconfirmed': true,
    },
    {
      'id': 'r2',
      'text': 'Shen Yu lost the outer court ranking in the first round',
      'heard_label': 'Heard an hour ago',
      'certainty': 'confirmed',
      'unconfirmed': false,
    },
  ],
  'deeds': [
    {
      'id': 'd1',
      'text': 'Stole a sealed scroll from the forbidden library',
      'when_label': 'Day 1, dawn',
      'known_label': 'No one saw, as far as you know',
    },
  ],
  'threads': [
    {'id': 't1', 'title': 'The voice in the scroll', 'status': 'open'},
    {'id': 't2', 'title': 'The ranking of the outer court', 'status': 'failed'},
  ],
};

/// A story just started from a draft knows only its character.
JsonMap _newMemory(JsonMap? draft) {
  final lines = [for (final line in draft?['character_lines'] as List? ?? const []) line as String];
  final name = switch (lines.firstOrNull?.split(RegExp(r'[,.]')).first.trim()) {
    final name? when name.isNotEmpty && name.split(' ').length <= 4 => name,
    _ => 'You',
  };
  return {
    'character': {'name': name, 'lines': lines},
  };
}

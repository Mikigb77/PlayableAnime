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
  };
  final scenes = <JsonMap>[];

  /// Whether the player has met Senior Sister Lan, whose first scene plans her portrait.
  bool metLan = false;

  int get turn => scenes.isEmpty ? 0 : scenes.last['turn'] as int;

  JsonMap get clock => {'world_s': worldS, 'label': fakeWorldLabel(worldS), 'timeline_id': 'main'};

  JsonMap toSummary() => {
    'id': id,
    'title': title,
    'genre': genre,
    'rating': rating,
    'turn': turn,
    'world_time_label': fakeWorldLabel(worldS),
    'cover_url': coverUrl,
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
    final settings = r.json['settings'];
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

/// The checks of the real endpoint: each setting takes one of its values, and a null tone clears it.
void _checkSettings(JsonMap settings) {
  const choices = {
    'narration_length': {'short', 'medium', 'long'},
    'difficulty': {'story', 'balanced', 'brutal'},
    'event_frequency': {'calm', 'normal', 'dramatic'},
    'images': {'off', 'key_moments', 'more'},
  };
  for (final MapEntry(:key, :value) in settings.entries) {
    final ok = switch (key) {
      'tone' => value == null || (value is String && value.length <= 200),
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
      'unconfirmed': true,
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

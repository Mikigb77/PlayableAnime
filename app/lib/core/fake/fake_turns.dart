import 'dart:math' as math;

import '../json.dart';
import 'fake_backend.dart';
import 'fake_data.dart';
import 'fake_stories.dart';

/// Fake streamed turns (docs/API.md, "Turns"), as the real endpoint answers them. Owned by the
/// play screen work (WS14).
///
/// To try the app's error handling, put a trigger in the action text:
/// - `[fail:out_of_credits]`, `[fail:rate_limited]`, `[fail:quota_exceeded]` or
///   `[fail:version_conflict]` answer with that error before the stream starts. Out of credits
///   acts as an empty balance, so the player's own key gets past it (K6);
/// - `[fail:llm_unavailable]` streams a few words, then sends an `error` event;
/// - `[fail:unreadable_action]`, `[fail:bad_key]`, `[fail:limit]` (a hard limit, with
///   `details.category`) and `[fail:lost_race]` (another turn was saved first) arrive as the
///   stream's `error` event right after `turn.started`, as the real interpret step's do;
/// - `[fail:dropped]` saves the turn, then the connection drops before `scene.completed`;
/// - `[reset]` streams a few words, then `narration.reset` and a cut-away (F4);
/// - `[fail:picture]` plans a picture that is then skipped, as a blocked one would be (M3).
///
/// The action's words shape the scene: "attack" or "duel" is a fight with a roll and a picture
/// (M1 counts fights), "then" chains steps that stop where one fails (R6), "stop time" runs the
/// two clocks apart (W10a) with a cause-and-effect chain (A9), "leap" is a long shot and "fly" is
/// ruled out (A2). Every third turn plans a picture too, and the first meeting with Senior Sister
/// Lan plans her portrait.
void registerTurnRoutes(FakeBackend b) {
  b.route('POST', '/v1/stories/:id/turns', (r) {
    final story = b.data.stories.get(r.param('id'), r.userId!);
    final kind = r.json['kind'] as String? ?? 'action';
    final action = (r.json['action'] as String? ?? '').trim();
    final trigger = RegExp(r'\[fail:(\w+)\]').firstMatch(action)?.group(1);

    final expected = (r.json['expected_version'] as num?)?.toInt();
    if (expected != story.version || trigger == 'version_conflict') {
      throw FakeError(409, 'version_conflict', 'Another turn won.', {
        'current_version': story.version,
      });
    }
    _validate(kind, r.json, story);
    final byok = r.usesOwnKey;
    if (_preStreamError(byok && trigger == 'out_of_credits' ? null : trigger) case final error?) {
      throw error;
    }
    if (!byok && b.data.account.balanceOf(r.userId!) < _turnCents) {
      throw FakeError(402, 'out_of_credits', 'Not enough credits.', {
        'balance_cents': b.data.account.balanceOf(r.userId!),
        'available_cents': b.data.account.balanceOf(r.userId!),
      });
    }

    final turn = story.turn + 1;
    final scene = _buildScene(b, story, r.json, turn);
    if (trigger == 'picture') b.data.pictures.failing.add('${story.id}-$turn');
    final narration = scene['narration'] as String;
    final chunks = _chunks(narration);
    final pace = b.pace;

    void save() {
      // The turn is saved only once it completes (all or nothing).
      story.scenes.add(scene);
      story.version += 1;
      story.worldS = (scene['time'] as JsonMap)['world_end_s'] as int;
      story.updatedAt = b.now();
      if ((scene['image'] as JsonMap?)?['kind'] == 'portrait') story.metLan = true;
      if (!byok) {
        b.data.account.charge(
          r.userId!,
          kind: 'turn',
          cents: _turnCents,
          now: b.now(),
          storyId: story.id,
          turn: turn,
        );
      }
    }

    Iterable<(Duration, String, Object?)> events() sync* {
      yield (Duration.zero, 'turn.started', {'turn': turn});
      if (_streamError(trigger, story) case final error?) {
        yield (pace.firstWords, 'error', error);
        return;
      }
      if (trigger == 'llm_unavailable' || action.contains('[reset]')) {
        for (final (i, chunk) in chunks.take(6).indexed) {
          yield (i == 0 ? pace.firstWords : pace.perChunk, 'narration.delta', {'text': chunk});
        }
        if (trigger == 'llm_unavailable') {
          yield (
            pace.perChunk,
            'error',
            {
              'code': 'llm_unavailable',
              'message': 'The storyteller is unavailable. Try again.',
              'details': <String, Object?>{},
            },
          );
          return;
        }
        yield (pace.perChunk, 'narration.reset', {'reason': 'cutaway'});
      }
      for (final (i, chunk) in chunks.indexed) {
        yield (i == 0 ? pace.firstWords : pace.perChunk, 'narration.delta', {'text': chunk});
      }
      save();
      if (trigger == 'dropped') {
        // Saved, but the connection drops before the app hears so.
        yield (pace.perChunk, _dropConnection, null);
        return;
      }
      yield (
        pace.perChunk,
        'scene.completed',
        {
          'scene': scene,
          'story': {'version': story.version, 'clock': story.clock},
        },
      );
    }

    return FakeResponse.sse(pacedEvents(events()));
  });
}

/// An event name [pacedEvents] reads as a dropped connection.
const _dropConnection = fakeDroppedConnection;

const _turnCents = 2;

/// The request checks of the real endpoint: each kind takes only its own field, and the opening
/// comes first, once.
void _validate(String kind, JsonMap body, FakeStory story) {
  const fields = {'action': 'action', 'choice': 'choice_id', 'standing': 'standing'};
  if (!const {'action', 'choice', 'standing', 'opening'}.contains(kind)) {
    throw FakeError.validation('Unknown turn kind $kind.');
  }
  for (final MapEntry(key: other, value: field) in fields.entries) {
    if (other != kind && body[field] != null) {
      throw FakeError.validation('A $kind turn takes no $field.');
    }
  }
  if (kind == 'opening') {
    if (story.scenes.isNotEmpty) throw const FakeError.validation('The story has opened.');
    return;
  }
  if (story.scenes.isEmpty) throw const FakeError.validation('Play the opening first.');
  switch (kind) {
    case 'action':
      final action = (body['action'] as String? ?? '').trim();
      if (action.isEmpty || action.length > 2000) {
        throw const FakeError.validation('An action is 1 to 2000 characters.');
      }
      if (body['input_mode'] == 'choice') {
        throw const FakeError.validation('An action is typed or spoken.');
      }
    case 'choice':
      final choices = story.scenes.last['choices'] as List;
      if (!choices.any((c) => (c as JsonMap)['id'] == body['choice_id'])) {
        throw const FakeError.validation('That choice is no longer offered.');
      }
    case 'standing':
      if (body['standing'] != 'wait' && body['standing'] != 'observe') {
        throw const FakeError.validation('Standing actions are wait and observe.');
      }
  }
}

FakeError? _preStreamError(String? trigger) => switch (trigger) {
  'out_of_credits' => const FakeError(402, 'out_of_credits', 'Not enough credits.', {
    'balance_cents': 0.4,
    'available_cents': 0.4,
  }),
  'rate_limited' => const FakeError(429, 'rate_limited', 'Slow down.', {'retry_after_s': 20}),
  'quota_exceeded' => const FakeError(429, 'quota_exceeded', 'Daily limit reached.', {
    'resets_at': '2026-11-04T00:00:00Z',
  }),
  _ => null,
};

/// The errors that arrive after `turn.started`, as the real interpret step's do.
JsonMap? _streamError(String? trigger, FakeStory story) => switch (trigger) {
  'unreadable_action' => {
    'code': 'unreadable_action',
    'message': 'That action can\'t be read.',
    'details': <String, Object?>{},
  },
  'limit' => {
    'code': 'unreadable_action',
    'message': 'Stories here never depict real, living people. Try a character of your own.',
    'details': {'category': 'real_person'},
  },
  'bad_key' => {
    'code': 'bad_key',
    'message': 'The provider rejected the key.',
    'details': <String, Object?>{},
  },
  'lost_race' => {
    'code': 'version_conflict',
    'message': 'Another turn was saved first.',
    'details': {'current_version': story.version},
  },
  _ => null,
};

final _fightWords = RegExp(
  r'attack|strike|duel|fight|punch|sword|blade|kill|charge|stab',
  caseSensitive: false,
);
final _timeStop = RegExp(r'stop time|time stop|freeze time', caseSensitive: false);
final _longShot = RegExp(r'\bleap|\bjump across|\bswing across', caseSensitive: false);
final _ruledOut = RegExp(r'\bfly\b|\bteleport', caseSensitive: false);
final _rope = RegExp(r'\brope\b', caseSensitive: false);

JsonMap _buildScene(FakeBackend b, FakeStory story, JsonMap body, int turn) {
  final kind = body['kind'] as String? ?? 'action';
  // Saved as sent, as the real endpoint does; the triggers don't shape the scene.
  final sent = (body['action'] as String? ?? '').trim();
  final action = sent.replaceAll(RegExp(r'\[[^\]]*\]'), '').trim();
  final previous = story.scenes.isEmpty ? null : story.scenes.last;
  final choiceLabel = kind == 'choice'
      ? ((previous!['choices'] as List).cast<JsonMap>().firstWhere(
              (c) => c['id'] == body['choice_id'],
            )['label']
            as String)
      : null;
  final standing = body['standing'] as String?;
  final said = kind == 'choice' ? choiceLabel! : action;
  final fight = _fightWords.hasMatch(said);
  final timeStop = _timeStop.hasMatch(said);

  final duration = switch ((kind, standing)) {
    ('opening', _) => 0,
    ('standing', 'wait') => 30 * 60,
    ('standing', _) => 5 * 60,
    _ when timeStop => 0,
    _ when RegExp(r'sleep|rest', caseSensitive: false).hasMatch(said) => 8 * 3600,
    _ when RegExp(r'travel|ride|walk to', caseSensitive: false).hasMatch(said) => 2 * 3600,
    _ when fight => 40,
    _ => 3 * 60,
  };
  final start = story.worldS;
  final end = start + duration;

  final narration = _lengthOf(story.settings['narration_length'] as String?, switch ((
    kind,
    standing,
  )) {
    ('opening', _) => '${story.premise}\n\n$_openingLine',
    ('standing', 'wait') => _waitNarration,
    ('standing', _) => _observeNarration,
    _ when timeStop => _timeStopNarration,
    _ when fight => _fightNarration,
    _ => _narrations[turn % _narrations.length],
  });

  final suggestions = story.settings['suggestions'] != false;
  final pool = [..._choicePool]..shuffle(math.Random(turn));
  final meetsLan = turn.isEven && kind != 'opening';
  final images = story.settings['images'] as String? ?? 'key_moments';
  // A key moment gets a scene picture (M1); otherwise a first meeting gets a portrait.
  final pictureKind = switch (images) {
    'off' => null,
    _ when kind == 'opening' || fight || timeStop => 'scene',
    _ when meetsLan && !story.metLan => 'portrait',
    _
        when turn % (images == 'more' ? 2 : 3) == 0 ||
            (body['action'] as String? ?? '').contains('[fail:picture]') =>
      'scene',
    _ => null,
  };
  final eventSize = turn % 4 == 0 ? const ['personal', 'local', 'world'][(turn ~/ 4) % 3] : null;

  return {
    'turn': turn,
    'kind': kind,
    if (kind == 'action') 'player_action': sent,
    if (kind == 'choice') 'player_action': choiceLabel,
    // As the server does: the standing action's wire name, which the app shows in its own words.
    if (kind == 'standing') 'player_action': standing,
    'input_mode': switch (kind) {
      'opening' => null,
      'action' => body['input_mode'] ?? 'typed',
      _ => 'choice',
    },
    'narration': narration,
    'choices': suggestions ? pool.take(3).toList() : <Object>[],
    'standing_actions': ['wait', 'observe'],
    'time': {
      'world_start_s': start,
      'world_end_s': end,
      'label': fakeWorldLabel(end),
      'duration_label': duration == 0 && !timeStop ? '' : fakeDurationLabel(duration),
      if (timeStop) 'personal_label': 'World: +0 s. You: +40 s.',
    },
    'details': kind == 'opening' ? <String, Object?>{} : _details(said, turn, fight, timeStop),
    if (eventSize != null) 'event': {'size': eventSize, 'title': _eventTitles[eventSize]},
    if (pictureKind != null) 'image': {'planned': true, 'kind': pictureKind, 'status': 'planned'},
    'portraits': [
      if (meetsLan)
        {'character_id': 'lan', 'name': 'Senior Sister Lan', 'url': FakeAssets.portrait(3)},
      if (fight)
        {'character_id': 'foe', 'name': 'The masked disciple', 'url': FakeAssets.portrait(1)},
    ],
    'blocked': false,
    'created_at': b.now().toUtc().toIso8601String(),
  };
}

/// Why the scene went the way it did, the way the engine records it (A2, A8, A9, R6).
JsonMap _details(String said, int turn, bool fight, bool timeStop) {
  JsonMap step(String text, String outcome, String reason, [String? odds, String? result]) => {
    'text': text,
    'class': outcome,
    'reason': reason,
    if (odds != null) 'roll': {'odds_label': odds, 'result': result, 'seed': 'fake-$turn-$text'},
  };
  final parts = said
      .split(RegExp(r',?\s+then\s+', caseSensitive: false))
      .map((p) => p.trim())
      .where((p) => p.isNotEmpty)
      .toList();
  if (timeStop) {
    return {
      'steps': [
        step('Stop time', 'certain', 'Your gift answers, and the world holds its breath.'),
        step(
          'Strike while nothing moves',
          'certain',
          'A foe who cannot see, dodge or block is no contest.',
        ),
      ],
      'chain': [
        {
          'link': 'The blow lands in stopped time',
          'class': 'certain',
          'reason': 'Nothing in the world can answer it.',
        },
        {
          'link': 'Time starts again, and the force arrives all at once',
          'class': 'certain',
          'reason': 'What you did in the stop happens the moment it ends.',
        },
        {
          'link': 'The crowd sees only the result',
          'class': 'contested',
          'reason': 'Someone sharp-eyed might still wonder.',
        },
      ],
    };
  }
  if (parts.length > 1) {
    // A chained plan: the first step works, the second meets resistance and fails, and the plan
    // stops there (R6).
    return {
      'steps': [
        step(parts[0], 'certain', 'Nothing stands in the way.'),
        step(
          parts[1],
          'contested',
          'Someone is watching, and they are quicker than they look.',
          'about even',
          'failure',
        ),
      ],
      'stopped_at_step': 1,
    };
  }
  if (_rope.hasMatch(said)) {
    // R2: the rope wasn't in the scene, but nothing says it can't be there.
    return {
      'steps': [
        {
          ...step(
            said,
            'contested',
            'It is a long way down, and the rope is old.',
            'good',
            'success',
          ),
          'beats': [
            {
              'beat': 'Find a rope',
              'thing': 'a coil of rope by the bell tower',
              'verdict': 'made_canon',
              'reason': 'A bell tower keeps rope for its bell, and nothing said there was none.',
            },
          ],
        },
      ],
    };
  }
  if (_ruledOut.hasMatch(said)) {
    return {
      'steps': [step(said, 'ruled_out', 'Nobody in this world can do that, and neither can you.')],
    };
  }
  if (_longShot.hasMatch(said)) {
    return {
      'steps': [
        step(
          said,
          'long_shot',
          'The gap is wider than you would like, and the stone is wet.',
          'a long shot',
          turn.isEven ? 'success' : 'partial',
        ),
      ],
    };
  }
  if (fight) {
    return {
      'steps': [
        step(
          'Land the blow before they can answer',
          'contested',
          'They are quick, but they did not see you coming.',
          'better than even',
          turn % 3 == 0 ? 'partial' : 'success',
        ),
      ],
    };
  }
  return {
    'steps': [step(said.isEmpty ? 'Take your time' : said, 'certain', 'Nothing stops you.')],
  };
}

/// Narration at the story's length setting (S6): short keeps the first paragraph, long adds one.
String _lengthOf(String? length, String narration) => switch (length) {
  'short' => narration.split('\n\n').first,
  'long' => '$narration\n\n$_longCoda',
  _ => narration,
};

/// Splits narration into chunks of one to three words, keeping spaces and line breaks, the way a
/// model's tokens arrive.
List<String> _chunks(String text) {
  final parts = RegExp(r'\S+\s*').allMatches(text).map((m) => m.group(0)!).toList();
  final chunks = <String>[];
  for (var i = 0; i < parts.length;) {
    final take = 1 + (i % 3);
    chunks.add(parts.skip(i).take(take).join());
    i += take;
  }
  return chunks;
}

const _openingLine =
    'The air is cold and full of possibility. Somewhere ahead, the first choice is already '
    'waiting for you.';

const _narrations = [
  'It takes longer than you expect, and less than you feared. When it is done the air feels '
      'different, as if the place itself has noticed you.\n\nSomewhere close, a door closes softly. '
      'Someone has been listening.',
  'The first try goes wrong in a small, instructive way. The second goes right.\n\nWhen you look up, '
      'the light has moved across the floor, and you are no longer alone. A figure waits at the edge '
      'of the lamplight, *patient as a cat*, to see what you will do next.',
  'Nothing happens at once. Then everything happens together: a shout, the scrape of a door, the '
      'smell of smoke on the wind.\n\nWhatever you have started, it is moving now without you.',
];

const _fightNarration =
    'You move first. Your opponent is quick, but quick is not the same as ready, and your strike '
    'lands where their guard was a heartbeat ago.\n\nThey stagger back against the railing, eyes '
    'wide behind the mask. For the first time tonight, they look at you as a threat.';

const _timeStopNarration =
    'You close your hand, and the world stops with it. A falling leaf hangs at the height of your '
    'eyes; the bell\'s last note waits, unfinished, in the air.\n\nYou walk between the frozen '
    'disciples and do what you came to do. When you let go, time rushes back in all at once, and '
    'to everyone watching, nothing moved at all.';

const _waitNarration =
    'You wait. The world does not.\n\nShadows lengthen across the courtyard. Voices rise and fall '
    'beyond the wall, and a messenger hurries past without seeing you, a letter sealed in black wax '
    'pressed to his chest.';

const _observeNarration =
    'You stay still and watch.\n\nThe guard at the gate shifts his weight every few breaths, '
    'favouring his left leg. The lamp above him gutters whenever the wind turns. And the crowd '
    'thins, just slightly, each time the temple bell rings.';

const _longCoda =
    'Later you will remember small things about this moment: the cold of the stone under your '
    'palm, the smell of incense from somewhere below, the way your own breathing sounded too loud. '
    'For now there is only what comes next.';

const _eventTitles = {
  'personal': 'A letter with your mother\'s seal',
  'local': 'Fire in the lower market',
  'world': 'The Emperor is dead',
};

const _choicePool = <JsonMap>[
  {'id': 'p1', 'label': 'Follow the figure into the dark', 'kind': 'thread'},
  {'id': 'p2', 'label': 'Ask what they want from you', 'kind': 'thread'},
  {'id': 'p3', 'label': 'Write to your sister before it is too late', 'kind': 'personal'},
  {'id': 'p4', 'label': 'Visit the herbalist in the lower town', 'kind': 'side'},
  {'id': 'p5', 'label': 'Climb onto the roof and shout your name', 'kind': 'wild'},
  {'id': 'p6', 'label': 'Draw your blade and attack', 'kind': 'thread'},
];

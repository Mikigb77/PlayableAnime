import 'dart:math' as math;

import '../json.dart';
import 'fake_backend.dart';
import 'fake_data.dart';
import 'fake_stories.dart';

/// Fake streamed turns (docs/API.md, "Turns"). Owned by the play screen work (WS14).
///
/// To try the app's error handling, put a trigger in the action text:
/// - `[fail:out_of_credits]`, `[fail:rate_limited]`, `[fail:quota_exceeded]`,
///   `[fail:unreadable_action]`, `[fail:bad_key]` or `[fail:version_conflict]` answer with that
///   error before the stream starts;
/// - `[fail:llm_unavailable]` streams a few words, then sends an `error` event;
/// - `[reset]` streams a few words, then `narration.reset` and a cut-away (F4);
/// - `[fail:picture]` plans a picture that is then skipped, as a blocked one would be (M3).
///
/// Words such as "attack" or "duel" plan a picture (M1 counts fights), as does every third turn.
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
    if (_preStreamError(trigger) case final error?) throw error;
    final byok = r.usesOwnKey;
    if (!byok && b.data.account.balanceOf(r.userId!) < _turnCents) {
      throw FakeError(402, 'out_of_credits', 'Not enough credits.', {
        'balance_cents': b.data.account.balanceOf(r.userId!),
      });
    }

    final turn = story.turn + 1;
    final scene = _buildScene(b, story, r.json, turn);
    if (trigger == 'picture') b.data.pictures.failing.add('${story.id}-$turn');
    final narration = scene['narration'] as String;
    final chunks = _chunks(narration);
    final pace = b.pace;

    Iterable<(Duration, String, Object?)> events() sync* {
      yield (Duration.zero, 'turn.started', {'turn': turn});
      if (trigger == 'llm_unavailable' || action.contains('[reset]')) {
        for (final (i, chunk) in chunks.take(6).indexed) {
          yield (i == 0 ? pace.firstWords : pace.perChunk, 'narration.delta', {'text': chunk});
        }
        if (trigger == 'llm_unavailable') {
          yield (
            pace.perChunk,
            'error',
            {'code': 'llm_unavailable', 'message': 'The storyteller is unavailable. Try again.'},
          );
          return;
        }
        yield (pace.perChunk, 'narration.reset', {'reason': 'cutaway'});
      }
      for (final (i, chunk) in chunks.indexed) {
        yield (i == 0 ? pace.firstWords : pace.perChunk, 'narration.delta', {'text': chunk});
      }
      // The turn is saved only once it completes (all or nothing).
      story.scenes.add(scene);
      story.version += 1;
      story.worldS = (scene['time'] as JsonMap)['world_end_s'] as int;
      story.updatedAt = b.now();
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

const _turnCents = 2;

void _validate(String kind, JsonMap body, FakeStory story) {
  switch (kind) {
    case 'action':
      final action = (body['action'] as String? ?? '').trim();
      if (action.isEmpty || action.length > 2000) {
        throw const FakeError.validation('An action is 1 to 2000 characters.');
      }
    case 'choice':
      final choices = story.scenes.isEmpty ? const [] : story.scenes.last['choices'] as List;
      if (!choices.any((c) => (c as JsonMap)['id'] == body['choice_id'])) {
        throw const FakeError.validation('That choice is no longer offered.');
      }
    case 'standing':
      if (body['standing'] != 'wait' && body['standing'] != 'observe') {
        throw const FakeError.validation('Standing actions are wait and observe.');
      }
    case 'opening':
      if (story.scenes.isNotEmpty) throw const FakeError.validation('The story has opened.');
    default:
      throw FakeError.validation('Unknown turn kind $kind.');
  }
}

FakeError? _preStreamError(String? trigger) => switch (trigger) {
  'out_of_credits' => const FakeError(402, 'out_of_credits', 'Not enough credits.', {
    'balance_cents': 0.4,
  }),
  'rate_limited' => const FakeError(429, 'rate_limited', 'Slow down.', {'retry_after_s': 20}),
  'quota_exceeded' => const FakeError(429, 'quota_exceeded', 'Daily limit reached.', {
    'resets_at': '2026-11-04T00:00:00Z',
  }),
  'unreadable_action' => const FakeError(422, 'unreadable_action', 'That action can\'t be read.'),
  'bad_key' => const FakeError(422, 'bad_key', 'The provider rejected the key.'),
  _ => null,
};

final _fightWords = RegExp(
  r'attack|strike|duel|fight|punch|sword|blade|kill|charge|stab',
  caseSensitive: false,
);

JsonMap _buildScene(FakeBackend b, FakeStory story, JsonMap body, int turn) {
  final kind = body['kind'] as String? ?? 'action';
  final action = (body['action'] as String? ?? '').replaceAll(RegExp(r'\[[^\]]*\]'), '').trim();
  final previous = story.scenes.isEmpty ? null : story.scenes.last;
  final choiceLabel = kind == 'choice'
      ? ((previous!['choices'] as List).cast<JsonMap>().firstWhere(
              (c) => c['id'] == body['choice_id'],
            )['label']
            as String)
      : null;
  final standing = body['standing'] as String?;
  final fight = _fightWords.hasMatch(action) || _fightWords.hasMatch(choiceLabel ?? '');

  final duration = switch ((kind, standing)) {
    ('opening', _) => 0,
    ('standing', 'wait') => 30 * 60,
    ('standing', _) => 5 * 60,
    _ when RegExp(r'sleep|rest', caseSensitive: false).hasMatch(action) => 8 * 3600,
    _ when RegExp(r'travel|ride|walk to', caseSensitive: false).hasMatch(action) => 2 * 3600,
    _ when fight => 40,
    _ => 3 * 60,
  };
  final start = story.worldS;
  final end = start + duration;

  final narration = switch ((kind, standing)) {
    ('opening', _) => '${story.premise}\n\n$_openingLine',
    ('standing', 'wait') => _waitNarration,
    ('standing', _) => _observeNarration,
    _ when fight => _fightNarration,
    _ => _narrations[turn % _narrations.length],
  };

  final suggestions = story.settings['suggestions'] != false;
  final pool = [..._choicePool]..shuffle(math.Random(turn));
  final picture =
      kind == 'opening' ||
      fight ||
      turn % 3 == 0 ||
      (body['action'] as String? ?? '').contains('[fail:picture]');
  final eventSize = turn % 4 == 0 ? const ['personal', 'local', 'world'][(turn ~/ 4) % 3] : null;

  return {
    'turn': turn,
    'kind': kind,
    if (kind == 'action') 'player_action': action,
    if (kind == 'choice') 'player_action': choiceLabel,
    if (kind == 'standing') 'player_action': standing == 'wait' ? 'Wait' : 'Observe',
    'input_mode': body['input_mode'],
    'narration': narration,
    'choices': suggestions ? pool.take(3).toList() : <Object>[],
    'standing_actions': ['wait', 'observe'],
    'time': {
      'world_start_s': start,
      'world_end_s': end,
      'label': fakeWorldLabel(end),
      'duration_label': fakeDurationLabel(duration),
    },
    'details': {
      'steps': [
        if (fight)
          {
            'text': 'Land the blow before they can answer',
            'class': 'contested',
            'reason': 'They are quick, but they did not see you coming.',
            'roll': {'odds_label': 'better than even', 'result': 'success', 'seed': 'fake-$turn-1'},
          }
        else
          {
            'text': 'Do what you set out to do',
            'class': 'certain',
            'reason': 'Nothing stands in the way.',
          },
      ],
    },
    if (eventSize != null) 'event': {'size': eventSize, 'title': _eventTitles[eventSize]},
    if (picture) 'image': {'planned': true, 'kind': 'scene', 'status': 'planned'},
    'portraits': [
      if (turn.isEven)
        {'character_id': 'lan', 'name': 'Senior Sister Lan', 'url': FakeAssets.portrait(3)},
      if (fight)
        {'character_id': 'foe', 'name': 'The masked disciple', 'url': FakeAssets.portrait(1)},
    ],
    'created_at': b.now().toUtc().toIso8601String(),
  };
}

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

const _waitNarration =
    'You wait. The world does not.\n\nShadows lengthen across the courtyard. Voices rise and fall '
    'beyond the wall, and a messenger hurries past without seeing you, a letter sealed in black wax '
    'pressed to his chest.';

const _observeNarration =
    'You stay still and watch.\n\nThe guard at the gate shifts his weight every few breaths, '
    'favouring his left leg. The lamp above him gutters whenever the wind turns. And the crowd '
    'thins, just slightly, each time the temple bell rings.';

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

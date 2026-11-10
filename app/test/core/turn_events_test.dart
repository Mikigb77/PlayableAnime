import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:playable_anime/core/api/api_error.dart';
import 'package:playable_anime/core/api/sse.dart';
import 'package:playable_anime/core/api/turn_events.dart';

Stream<SseEvent> events(String body) async* {
  yield* Stream.fromIterable(await SseParser.parseString(body));
}

void main() {
  test('maps a successful turn and ends at scene.completed', () async {
    final out = await parseTurnEvents(
      events(
        '${encodeSseEvent('turn.started', {'turn': 4})}'
        '${encodeSseEvent('narration.delta', {'text': 'Rain '})}'
        '${encodeSseEvent('narration.reset', {'reason': 'cutaway'})}'
        '${encodeSseEvent('future.event', {'x': 1})}'
        '${encodeSseEvent('scene.completed', {
          'scene': {'turn': 4},
          'story': {
            'version': 9,
            'clock': {'label': 'Day 2, night'},
          },
        })}'
        '${encodeSseEvent('narration.delta', {'text': 'ignored after the end'})}',
      ),
    ).toList();
    expect(out.map((e) => e.runtimeType), [
      TurnStarted,
      NarrationDelta,
      NarrationReset,
      SceneCompleted,
    ]);
    final done = out.last as SceneCompleted;
    expect(done.version, 9);
    expect(done.clock['label'], 'Day 2, night');
    expect((out[1] as NarrationDelta).text, 'Rain ');
    expect((out[2] as NarrationReset).reason, 'cutaway');
  });

  test('the steps the engine decided arrive as they are, before the story (A3)', () async {
    final out = await parseTurnEvents(
      events(
        '${encodeSseEvent('turn.started', {'turn': 4})}'
        '${encodeSseEvent('steps.decided', {
          'turn': 4,
          'details': {
            'steps': [
              {'text': 'Leap', 'class': 'long_shot', 'reason': 'Wet stone.'},
            ],
          },
        })}'
        '${encodeSseEvent('narration.delta', {'text': 'You '})}'
        '${encodeSseEvent('scene.completed', {
          'scene': {'turn': 4},
          'story': {'version': 4, 'clock': <String, Object?>{}},
        })}',
      ),
    ).toList();
    final decided = out[1] as StepsDecided;
    expect(decided.turn, 4);
    expect((decided.details['steps'] as List).single, containsPair('text', 'Leap'));
    final started = out.first as TurnStarted;
    expect((started.resumed, started.kind, started.action), (false, null, null));
  });

  test('a turn the story owed says so as it starts, with what the player did (A3)', () async {
    final out = await parseTurnEvents(
      events(
        encodeSseEvent('turn.started', {
          'turn': 7,
          'resumed': true,
          'kind': 'action',
          'action': 'I leap',
        }),
      ),
    ).toList();
    final started = out.first as TurnStarted;
    expect(
      (started.turn, started.resumed, started.kind, started.action),
      (7, true, 'action', 'I leap'),
    );
  });

  test('an error event becomes TurnFailed with its code', () async {
    final out = await parseTurnEvents(
      events(encodeSseEvent('error', {'code': 'llm_unavailable', 'message': 'down'})),
    ).toList();
    expect(out.single, isA<TurnFailed>());
    expect((out.single as TurnFailed).error.code, ApiErrorCode.llmUnavailable);
  });

  test('a stream that ends early fails as a network error', () async {
    final out = await parseTurnEvents(
      events(encodeSseEvent('narration.delta', {'text': 'a'})),
    ).toList();
    expect(out.last, isA<TurnFailed>());
    expect((out.last as TurnFailed).error.code, ApiErrorCode.network);
  });

  test('a dropped connection fails as a network error', () async {
    final controller = StreamController<SseEvent>();
    final out = parseTurnEvents(controller.stream).toList();
    controller
      ..add(const SseEvent(event: 'turn.started', data: '{"turn": 1}'))
      ..addError(Exception('socket closed'));
    await controller.close();
    final result = await out;
    expect((result.last as TurnFailed).error.code, ApiErrorCode.network);
  });

  test('an idle timeout keeps its code', () async {
    final controller = StreamController<SseEvent>();
    final out = parseTurnEvents(controller.stream).toList();
    controller.addError(const ApiException(ApiErrorCode.timeout));
    await controller.close();
    expect(((await out).single as TurnFailed).error.code, ApiErrorCode.timeout);
  });

  test('a malformed event fails as a server error', () async {
    final out = await parseTurnEvents(
      Stream.value(const SseEvent(event: 'scene.completed', data: '{"scene": 3}')),
    ).toList();
    expect((out.single as TurnFailed).error.code, ApiErrorCode.server);
  });

  test('a scene that ends the story carries its ending', () async {
    final out = await parseTurnEvents(
      events(
        encodeSseEvent('scene.completed', {
          'scene': {'turn': 4, 'kind': 'end'},
          'story': {
            'version': 9,
            'clock': {'label': 'Day 2, night'},
            'ending': {'kind': 'chosen', 'character': 'Shen Yu'},
          },
        }),
      ),
    ).toList();
    expect((out.single as SceneCompleted).ending?['kind'], 'chosen');
  });

  test('a refused ending ends the stream with what was refused', () async {
    final out = await parseTurnEvents(
      events(
        '${encodeSseEvent('turn.started', {'turn': 4})}'
        '${encodeSseEvent('ending.refused', {
          'message': 'Not yet.',
          'refused': [
            {'text': 'take the throne', 'reason': 'Nobody follows you.', 'class': 'long_shot'},
          ],
        })}'
        '${encodeSseEvent('narration.delta', {'text': 'ignored after the end'})}',
      ),
    ).toList();
    expect(out.map((e) => e.runtimeType), [TurnStarted, EndingRefused]);
    final refused = out.last as EndingRefused;
    expect(refused.message, 'Not yet.');
    final part = refused.refused.single;
    expect(
      (part.text, part.reason, part.outcomeClass),
      ('take the throne', 'Nobody follows you.', 'long_shot'),
    );
  });
}

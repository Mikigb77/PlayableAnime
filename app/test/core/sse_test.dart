import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:playable_anime/core/api/sse.dart';

Future<List<SseEvent>> parseChunks(List<List<int>> chunks) =>
    const SseParser().bind(Stream.fromIterable(chunks)).toList();

void main() {
  test('parses named events with JSON data', () async {
    final events = await SseParser.parseString(
      'event: turn.started\ndata: {"turn": 4}\n\nevent: narration.delta\ndata: {"text": "Rain"}\n\n',
    );
    expect(events.map((e) => e.event), ['turn.started', 'narration.delta']);
    expect((events.last.json as Map)['text'], 'Rain');
  });

  test('joins multi-line data, ignores comments and unknown fields, defaults to message', () async {
    final events = await SseParser.parseString(
      ': keep-alive\nretry: 3000\nfoo: bar\ndata: one\ndata:two\nid: 7\n\n',
    );
    expect(events, hasLength(1));
    expect(events.single.event, 'message');
    expect(events.single.data, 'one\ntwo');
    expect(events.single.id, '7');
  });

  test('handles CRLF and CR line ends', () async {
    final events = await SseParser.parseString('event: a\r\ndata: 1\r\n\r\nevent: b\rdata: 2\r\r');
    expect(events.map((e) => '${e.event}=${e.data}'), ['a=1', 'b=2']);
  });

  test('survives chunks split inside a line, a CRLF and a UTF-8 character', () async {
    final bytes = utf8.encode('event: narration.delta\r\ndata: {"text": "café — 夜"}\r\n\r\n');
    // Split into 1-byte chunks: every boundary is exercised.
    final events = await parseChunks([
      for (final b in bytes) [b],
    ]);
    expect(events, hasLength(1));
    expect((events.single.json as Map)['text'], 'café — 夜');
  });

  test('drops an event the stream cut off before its blank line', () async {
    final events = await SseParser.parseString('data: complete\n\ndata: cut off');
    expect(events.map((e) => e.data), ['complete']);
  });

  test('skips events without data and strips a leading byte-order mark', () async {
    final events = await SseParser.parseString('﻿event: ping\n\ndata: x\n\n');
    expect(events.map((e) => e.data), ['x']);
  });

  test('encodeSseEvent round-trips', () async {
    final events = await SseParser.parseString(encodeSseEvent('scene.completed', {'a': 'b\nc'}));
    expect(events.single.event, 'scene.completed');
    expect(events.single.json, {'a': 'b\nc'});
  });

  test('passes stream errors through', () async {
    final controller = StreamController<List<int>>();
    final events = const SseParser().bind(controller.stream);
    final result = expectLater(
      events,
      emitsInOrder([isA<SseEvent>(), emitsError(isA<StateError>())]),
    );
    controller
      ..add(utf8.encode('data: 1\n\n'))
      ..addError(StateError('dropped'));
    await controller.close();
    await result;
  });
}

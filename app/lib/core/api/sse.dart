import 'dart:async';
import 'dart:convert';

/// One server-sent event.
class SseEvent {
  const SseEvent({required this.event, required this.data, this.id});

  /// The `event:` field, or `message` when the server sent none.
  final String event;

  /// The `data:` lines joined with newlines.
  final String data;

  final String? id;

  /// [data] decoded as JSON.
  Object? get json => jsonDecode(data);

  @override
  String toString() => 'SseEvent($event, $data)';
}

/// Parses a `text/event-stream` body into [SseEvent]s, following the WHATWG rules: UTF-8 split
/// anywhere across chunks, `\n`, `\r\n` or `\r` line ends, comment lines, multi-line data, an
/// optional space after the colon, and an unfinished event at the end of the stream dropped.
class SseParser extends StreamTransformerBase<List<int>, SseEvent> {
  const SseParser();

  @override
  Stream<SseEvent> bind(Stream<List<int>> stream) => Stream<SseEvent>.eventTransformed(
    stream.transform(utf8.decoder).transform(const LineSplitter()),
    (EventSink<SseEvent> sink) => _SseSink(sink),
  );

  /// Parses complete text, for tests and the fake API.
  static Future<List<SseEvent>> parseString(String body) =>
      const SseParser().bind(Stream.value(utf8.encode(body))).toList();
}

class _SseSink implements EventSink<String> {
  _SseSink(this._out);

  final EventSink<SseEvent> _out;
  final _data = StringBuffer();
  var _hasData = false;
  String? _event;
  String? _lastId;
  var _first = true;

  @override
  void add(String line) {
    // A byte-order mark may start the stream.
    if (_first) {
      _first = false;
      if (line.startsWith('﻿')) line = line.substring(1);
    }
    if (line.isEmpty) {
      _dispatch();
      return;
    }
    if (line.startsWith(':')) return;
    final colon = line.indexOf(':');
    final field = colon < 0 ? line : line.substring(0, colon);
    var value = colon < 0 ? '' : line.substring(colon + 1);
    if (value.startsWith(' ')) value = value.substring(1);
    switch (field) {
      case 'event':
        _event = value;
      case 'data':
        if (_hasData) _data.write('\n');
        _data.write(value);
        _hasData = true;
      case 'id':
        if (!value.contains('\u0000')) _lastId = value;
      default:
        // `retry` and unknown fields are ignored.
        break;
    }
  }

  void _dispatch() {
    if (_hasData) {
      final event = _event;
      _out.add(
        SseEvent(
          event: event == null || event.isEmpty ? 'message' : event,
          data: _data.toString(),
          id: _lastId,
        ),
      );
    }
    _data.clear();
    _hasData = false;
    _event = null;
  }

  @override
  void addError(Object error, [StackTrace? stackTrace]) => _out.addError(error, stackTrace);

  @override
  void close() => _out.close();
}

/// Encodes one event the way the backend does, for the fake API and tests.
String encodeSseEvent(String event, Object? data) => 'event: $event\ndata: ${jsonEncode(data)}\n\n';

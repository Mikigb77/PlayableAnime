import '../json.dart';
import 'api_error.dart';
import 'sse.dart';

/// The events of one streamed turn (docs/API.md, "Turns"). The play screen (WS14) turns these
/// into its own scene model.
sealed class TurnEvent {
  const TurnEvent();
}

/// Sent at once, so the app can show the action and a typing state.
class TurnStarted extends TurnEvent {
  const TurnStarted(this.turn);
  final int turn;
}

/// More narration, as it is written.
class NarrationDelta extends TurnEvent {
  const NarrationDelta(this.text);
  final String text;
}

/// The narration is being rewritten, so the partial text is cleared: it was blocked (F4), or the
/// model failed partway and is being retried once (T7).
class NarrationReset extends TurnEvent {
  const NarrationReset(this.reason);

  /// `cutaway`, `template` or `retry`.
  final String reason;
}

/// The turn is saved. Always the last event of a successful turn.
class SceneCompleted extends TurnEvent {
  const SceneCompleted({required this.scene, required this.version, required this.clock});

  /// The `Scene` object as JSON.
  final JsonMap scene;

  /// The story's new version, for the next turn's `expected_version` (T10).
  final int version;

  /// The `Clock` object as JSON.
  final JsonMap clock;
}

/// The turn failed after streaming began: `unreadable_action`, `llm_unavailable`, `bad_key`,
/// `version_conflict` or `internal_error`. Nothing was saved and nothing was charged, so the app
/// discards the partial scene and offers a retry or a rephrase. A stream that ends without
/// [SceneCompleted] also ends with this, as a [ApiErrorCode.network] error.
class TurnFailed extends TurnEvent {
  const TurnFailed(this.error);
  final ApiException error;
}

/// Maps raw server-sent events to [TurnEvent]s. Unknown event names are skipped, so the backend
/// can add events without breaking older apps. The stream always ends with [SceneCompleted] or
/// [TurnFailed].
Stream<TurnEvent> parseTurnEvents(Stream<SseEvent> events) async* {
  try {
    await for (final event in events) {
      final TurnEvent? mapped;
      try {
        mapped = _map(event);
      } on Object {
        // A malformed event is a contract bug on the server, not a connection problem.
        yield TurnFailed(ApiException(ApiErrorCode.server, message: 'Malformed ${event.event}'));
        return;
      }
      if (mapped == null) continue;
      yield mapped;
      if (mapped is SceneCompleted || mapped is TurnFailed) return;
    }
  } on ApiException catch (e) {
    yield TurnFailed(e);
    return;
  } on Object {
    // The connection dropped mid-stream.
    yield const TurnFailed(ApiException(ApiErrorCode.network));
    return;
  }
  yield const TurnFailed(
    ApiException(ApiErrorCode.network, message: 'The stream ended before the scene was saved'),
  );
}

TurnEvent? _map(SseEvent event) {
  JsonMap data() => event.json as JsonMap;
  switch (event.event) {
    case 'turn.started':
      return TurnStarted((data()['turn'] as num).toInt());
    case 'narration.delta':
      return NarrationDelta(data()['text'] as String? ?? '');
    case 'narration.reset':
      return NarrationReset(data()['reason'] as String? ?? 'cutaway');
    case 'scene.completed':
      final d = data();
      final story = d['story'] as JsonMap? ?? const {};
      return SceneCompleted(
        scene: d['scene'] as JsonMap,
        version: (story['version'] as num?)?.toInt() ?? 0,
        clock: story['clock'] as JsonMap? ?? const {},
      );
    case 'error':
      final d = data();
      return TurnFailed(
        ApiException(
          ApiErrorCode.fromWire(d['code'] as String?),
          message: d['message'] as String? ?? '',
          details: d['details'] as JsonMap? ?? const {},
        ),
      );
    default:
      return null;
  }
}

import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/foundation.dart';

import '../../core/api/api_error.dart';
import '../../core/api/turn_events.dart';
import 'story_models.dart';
import 'story_repository.dart';

/// Where the turn in flight stands.
enum TurnPhase {
  /// Sent; waiting for the server to accept it and start writing.
  starting,

  /// The narration is streaming in (S3).
  streaming,

  /// It failed. Nothing was saved, so the same turn can be tried again.
  failed,
}

/// The turn in flight, or the one that just failed.
@immutable
class PendingTurn {
  const PendingTurn({
    required this.input,
    this.label,
    this.spoken = false,
    this.phase = TurnPhase.starting,
    this.text = '',
    this.error,
  });

  final TurnInput input;

  /// What the player did, shown above the scene. None for the opening.
  final String? label;

  /// The action was dictated (V7).
  final bool spoken;
  final TurnPhase phase;

  /// The narration streamed so far.
  final String text;
  final ApiException? error;

  bool get failed => phase == TurnPhase.failed;
  bool get isOpening => input.kind == 'opening';

  PendingTurn copyWith({TurnPhase? phase, String? text, ApiException? error}) => PendingTurn(
    input: input,
    label: label,
    spoken: spoken,
    phase: phase ?? this.phase,
    text: text ?? this.text,
    error: error ?? this.error,
  );
}

/// Something the play screen tells the player once, outside the feed.
sealed class PlayNotice {
  const PlayNotice();
}

/// Another turn won (T10): the story was fetched again. [action] is what the player wrote for the
/// turn that lost, for the screen to give back.
class StoryMovedOn extends PlayNotice {
  const StoryMovedOn({this.action});
  final String? action;
}

/// A turn or an Illustrate needs credits the player doesn't have (K2, M7). The screen opens the
/// out-of-credits sheet, and once the player adds their own key (K6) tries it again.
class OutOfCredits extends PlayNotice {
  const OutOfCredits(this.error, {this.turn, this.picture});
  final ApiException error;

  /// The turn that was refused. Nothing was saved or charged.
  final PendingTurn? turn;

  /// The scene whose Illustrate was refused (M2).
  final int? picture;
}

/// A scene was saved or a picture was drawn, either of which may have spent credits (K2, M7): the
/// balance shown elsewhere is out of date.
class CreditsSpent extends PlayNotice {
  const CreditsSpent();
}

/// A turn was refused for a reason the feed doesn't show, such as a choice that is no longer
/// offered.
class TurnRefused extends PlayNotice {
  const TurnRefused(this.error);
  final ApiException error;
}

/// A scene was saved and joins the feed. Sent just before the feed changes, so the screen can
/// keep the words the player is reading where they are.
class SceneSaved extends PlayNotice {
  const SceneSaved(this.turn);
  final int turn;
}

/// Closing the story at its ending failed (N6); it can be tried again.
class CloseFailed extends PlayNotice {
  const CloseFailed(this.error);
  final ApiException error;
}

/// Rewinding the story failed (C8); it can be tried again.
class RewindFailed extends PlayNotice {
  const RewindFailed(this.error);
  final ApiException error;
}

/// What the world refused of an ending's note (N6). Nothing was saved or charged: the player plays
/// on, or ends without it.
@immutable
class EndingRefusal {
  const EndingRefusal({required this.turn, required this.parts});

  /// The end turn that was refused, to send again without what was refused.
  final PendingTurn turn;
  final List<RefusedPart> parts;
}

/// Runs one story on the play screen: loading it and its older scenes, the turn in flight and its
/// stream (S3, T10), every error the API can answer (T7), pictures after the text (M3, M4),
/// reports and blocks (F6) and settings (S6). The screen draws what this holds.
class PlayController extends ChangeNotifier {
  PlayController({
    required this.repository,
    required this.storyId,
    Story? initialStory,
    DateTime Function()? clock,
    this.pageSize = 20,
    this.pictureInterval = const Duration(milliseconds: 1500),
  }) : _initial = initialStory,
       _now = clock ?? DateTime.now;

  final StoryRepository repository;
  final String storyId;
  final int pageSize;

  /// How long to wait before asking again for a picture that is still being painted.
  final Duration pictureInterval;

  final Story? _initial;
  final DateTime Function() _now;

  final _notices = StreamController<PlayNotice>.broadcast(sync: true);
  final _sleeps = <Timer, Completer<void>>{};
  StreamSubscription<TurnEvent>? _turn;
  bool _disposed = false;
  bool _openingAsked = false;

  /// The turn number the server gave the turn in flight (`turn.started`).
  int? _startedTurn;

  /// Counts replacements of the loaded scenes, so a scrollback page that arrives after one is
  /// dropped instead of leaving a gap.
  int _generation = 0;

  /// Notices for the screen: snackbars and sheets.
  Stream<PlayNotice> get notices => _notices.stream;

  Story? get story => _story;
  Story? _story;

  /// Why the story couldn't load, while there is no story to show.
  Object? get loadError => _loadError;
  Object? _loadError;

  bool get loading => _loading;
  bool _loading = false;

  PendingTurn? get pending => _pending;
  PendingTurn? _pending;

  /// A turn is under way, so another can't start.
  bool get busy => _pending != null && !_pending!.failed;

  /// The story has its opening, hasn't reached its ending, and the player can act.
  bool get canAct => (_story?.scenes.isNotEmpty ?? false) && !opening && !ended && !busy;

  /// The next turn is an opening: the story has no scenes yet, or someone new carries it on (N6).
  bool get opening {
    final story = _story;
    return story != null && story.ending == null && (story.scenes.isEmpty || story.openingDue);
  }

  /// The story reached its ending (N6): it takes no more turns.
  bool get ended => _story?.ending != null;

  /// What the world refused of the last ending's note, until the player plays on or ends without
  /// it (N6).
  EndingRefusal? get refusal => _refusal;
  EndingRefusal? _refusal;

  /// Closing the story is under way.
  bool get closing => _closing;
  bool _closing = false;

  /// A rewind is under way (C8).
  bool get rewinding => _rewinding;
  bool _rewinding = false;

  /// The first turn of the first load. Older scenes are laid out above it, so loading them never
  /// moves what the player is looking at.
  int get anchorTurn => _anchorTurn;
  int _anchorTurn = 1;

  bool get loadingOlder => _loadingOlder;
  bool _loadingOlder = false;
  Object? get olderError => _olderError;
  Object? _olderError;

  /// Every scene back to the opening is loaded.
  bool get reachedStart => _reachedStart;
  bool _reachedStart = true;

  /// Scenes blocked on this screen. The server marks them `blocked` from then on (F6).
  final _blocked = <int>{};

  /// Whether a scene's text is hidden: the player blocked it (F6).
  bool isBlocked(Scene scene) => scene.blocked || _blocked.contains(scene.turn);

  // Pictures (M3, M4). Ready pictures are kept by image id, so a portrait or place reused across
  // scenes shows one URL, loads once, and gets one fresh URL when it expires.
  final _pictures = <String, SceneImage>{};
  final _painting = <int>{};
  final _refreshedAt = <String, DateTime>{};
  final _refreshing = <String, Future<SceneImage?>>{};

  // ---- Loading ----------------------------------------------------------------------------

  /// Opens the story: the one passed in, or fetched. A story with no scenes yet (just started
  /// from a draft), or carried on by someone new (N6), plays its opening turn at once.
  Future<void> start() async {
    if (_initial case final story?) {
      _replace(story);
      _changed();
      _afterLoad();
    } else {
      await reload();
    }
  }

  /// Fetches the story again: after a conflict, a dropped stream, or the player's retry.
  Future<void> reload() async {
    if (_disposed) return;
    _loading = true;
    if (_story == null) _loadError = null;
    _changed();
    try {
      final fresh = await repository.get(storyId, scenes: pageSize);
      if (_disposed) return;
      _loadError = null;
      if (_story == null) {
        _replace(fresh);
      } else {
        _merge(fresh);
      }
    } on Object catch (e) {
      if (_disposed) return;
      if (_story == null) _loadError = e;
    } finally {
      _loading = false;
    }
    _changed();
    _afterLoad();
  }

  void _afterLoad() {
    final story = _story;
    if (story == null) return;
    _paintPlanned();
    if (opening && !_openingAsked && _pending == null) {
      _openingAsked = true;
      unawaited(begin());
    }
  }

  void _replace(Story story) {
    _generation++;
    _story = story;
    _remember(story.scenes);
    _anchorTurn = story.scenes.firstOrNull?.turn ?? 1;
    _reachedStart = story.scenes.isEmpty || story.scenes.first.turn <= 1;
  }

  /// Folds a fresh copy of the story into what is loaded. When the fresh scenes don't join up
  /// with the loaded ones (many turns played elsewhere), or the story was rewound elsewhere (C8),
  /// the loaded ones are dropped, so the feed never has a gap or a scene taken back.
  void _merge(Story fresh) {
    final current = _story!;
    final loaded = current.scenes;
    final latest = fresh.scenes.lastOrNull?.turn ?? 0;
    final rewound =
        fresh.version > current.version && loaded.isNotEmpty && loaded.last.turn > latest;
    if (rewound ||
        (fresh.scenes.isNotEmpty &&
            loaded.isNotEmpty &&
            fresh.scenes.first.turn > loaded.last.turn + 1)) {
      _blocked.removeWhere((turn) => turn > latest);
      _replace(fresh);
      return;
    }
    final byTurn = {for (final s in loaded) s.turn: s};
    for (final scene in fresh.scenes) {
      final old = byTurn[scene.turn];
      // A different scene in the same turn: a rewind elsewhere took the old one back and it was
      // played anew (C8). Nothing this screen knew of the old one carries over.
      final same = old != null && old.narration == scene.narration;
      if (old != null && !same) _blocked.remove(scene.turn);
      // A picture this screen already has is newer than a fetched "planned".
      byTurn[scene.turn] =
          same && old.image != null && !old.image!.isPending && scene.image?.isPending == true
          ? scene.withImage(old.image)
          : scene;
    }
    final scenes = byTurn.values.toList()..sort((a, b) => a.turn.compareTo(b.turn));
    _remember(fresh.scenes);
    _story = Story(
      id: fresh.id,
      title: fresh.title,
      scenes: scenes,
      genre: fresh.genre,
      premise: fresh.premise ?? current.premise,
      rating: fresh.rating,
      version: fresh.version,
      clockLabel: fresh.clockLabel,
      coverUrl: fresh.coverUrl,
      settings: fresh.settings,
      // A copy older than the one loaded doesn't take back an ending a scene brought.
      ending: fresh.version >= current.version ? fresh.ending : current.ending,
      successor: fresh.successor,
      heirs: fresh.heirs,
      openingDue: fresh.version >= current.version ? fresh.openingDue : current.openingDue,
    );
    if (scenes.isNotEmpty && scenes.first.turn < _anchorTurn) _anchorTurn = scenes.first.turn;
  }

  /// Loads the scenes before the oldest one loaded (scrollback).
  Future<void> loadOlder() async {
    final story = _story;
    if (story == null || _loadingOlder || _reachedStart || story.scenes.isEmpty) return;
    _loadingOlder = true;
    _olderError = null;
    _changed();
    final generation = _generation;
    try {
      final before = story.scenes.first.turn;
      final older = await repository.olderScenes(storyId, before: before, limit: pageSize);
      if (_disposed) return;
      // The story was replaced meanwhile (many turns played elsewhere): this page no longer
      // joins up with it.
      if (generation != _generation) return;
      final current = _story!;
      final known = {for (final s in current.scenes) s.turn};
      final added = [
        for (final s in older)
          if (s.turn < before && !known.contains(s.turn)) s,
      ];
      _remember(added);
      _story = current.copyWith(
        scenes: [...added, ...current.scenes]..sort((a, b) => a.turn.compareTo(b.turn)),
      );
      final first = _story!.scenes.first.turn;
      _reachedStart = first <= 1 || older.length < pageSize || added.isEmpty;
      _paintPlanned();
    } on Object catch (e) {
      if (_disposed) return;
      _olderError = e;
    } finally {
      _loadingOlder = false;
    }
    _changed();
  }

  // ---- Turns ------------------------------------------------------------------------------

  /// Plays the opening scene of a story that has none (`kind: "opening"`).
  Future<bool> begin() => _take(const TurnInput.opening());

  /// Does what the player wrote or said. Resolves true once the server took the turn and started
  /// writing it, which is when the screen empties the box.
  Future<bool> act(String text, {required String inputMode}) => _take(
    TurnInput.action(text, inputMode: inputMode),
    label: text,
    spoken: inputMode == 'voice' || inputMode == 'voice_edited',
  );

  Future<bool> choose(Choice choice) => _take(TurnInput.choice(choice.id), label: choice.label);

  /// Wait or observe (S2). [label] is the action's name in the player's language.
  Future<bool> stand(String standing, {required String label}) =>
      _take(TurnInput.standing(standing), label: label);

  /// Ends the story (N6): an epilogue from things as they stand, or from [note], the player's
  /// words on how it should end. [label] is what the feed shows above it.
  Future<bool> end({String? note, String inputMode = 'typed', required String label}) => _take(
    TurnInput.end(note, inputMode: inputMode),
    label: label,
    spoken: note != null && (inputMode == 'voice' || inputMode == 'voice_edited'),
  );

  /// Ends the story without what the world refused of the note (N6).
  Future<bool> endWithoutRefused() {
    final refused = _refusal;
    if (refused == null) return Future.value(false);
    final turn = refused.turn;
    return _take(turn.input.withoutRefused(), label: turn.label, spoken: turn.spoken);
  }

  /// Plays on after an ending was refused (N6): nothing changed.
  void playOn() {
    if (_refusal == null) return;
    _refusal = null;
    _changed();
  }

  /// Closes the story at its ending (N6). It stays in the Library to read.
  Future<void> close() async {
    if (_closing || !ended || _disposed) return;
    _closing = true;
    _changed();
    try {
      final fresh = await repository.close(storyId);
      if (_disposed) return;
      _merge(fresh);
    } on ApiException catch (e) {
      if (_disposed) return;
      _notice(CloseFailed(e));
    } on Object {
      if (_disposed) return;
      _notice(const CloseFailed(ApiException(ApiErrorCode.unknown)));
    } finally {
      _closing = false;
    }
    _changed();
  }

  /// Takes the story back [scenes] scenes from its ending (C8): the world as it was then, and the
  /// scenes after it gone from the feed. Another device that moved the story on wins (T10).
  Future<bool> rewind(int scenes) async {
    final story = _story;
    if (_rewinding || _closing || story == null || _disposed) return false;
    if (!(story.ending?.canRewind ?? false)) return false;
    _rewinding = true;
    _changed();
    var done = false;
    try {
      final fresh = await repository.rewind(
        storyId,
        expectedVersion: story.version,
        scenes: scenes,
      );
      if (_disposed) return false;
      _refusal = null;
      // The scenes taken back may have been blocked here; the ones played anew in their turns
      // are not (F6).
      final latest = fresh.scenes.lastOrNull?.turn ?? 0;
      _blocked.removeWhere((turn) => turn > latest);
      _replace(fresh);
      done = true;
    } on ApiException catch (e) {
      if (_disposed) return false;
      if (e.code == ApiErrorCode.versionConflict) {
        _notice(const StoryMovedOn());
        unawaited(reload());
      } else {
        _notice(RewindFailed(e));
      }
    } on Object {
      if (_disposed) return false;
      _notice(const RewindFailed(ApiException(ApiErrorCode.unknown)));
    } finally {
      _rewinding = false;
    }
    _changed();
    if (done) _afterLoad();
    return done;
  }

  /// The story carried on by someone new (N6), as `POST /carry-on` answered it: the ending is
  /// lifted, and their opening plays at once.
  void carriedOn(Story fresh) {
    if (_disposed) return;
    _refusal = null;
    _openingAsked = false;
    if (_story == null) {
      _replace(fresh);
    } else {
      _merge(fresh);
    }
    _changed();
    _afterLoad();
  }

  /// Tries the failed turn again, exactly as it was.
  Future<bool> retry() {
    final failed = _pending;
    if (failed == null || !failed.failed) return Future.value(false);
    return again(failed);
  }

  /// Takes [turn] again as it was, as after the player added their own key to a turn refused for
  /// credits (K6).
  Future<bool> again(PendingTurn turn) => _take(turn.input, label: turn.label, spoken: turn.spoken);

  /// Drops the failed turn.
  void dismissFailure() {
    if (_pending?.failed ?? false) {
      _pending = null;
      _changed();
    }
  }

  Future<bool> _take(TurnInput input, {String? label, bool spoken = false}) async {
    final story = _story;
    // A story at its ending takes no more turns, and someone new starts with their opening (N6).
    if (story == null || busy || _disposed || story.ending != null) return false;
    if (story.openingDue && input.kind != 'opening') return false;
    _refusal = null;
    _pending = PendingTurn(input: input, label: label, spoken: spoken);
    _startedTurn = null;
    _changed();
    final version = story.version;
    final Stream<TurnEvent> events;
    try {
      events = await repository.takeTurn(storyId, input, expectedVersion: version);
    } on Object catch (e, stack) {
      if (_disposed) return false;
      final error = switch (e) {
        final ApiException api => api,
        _ => const ApiException(ApiErrorCode.unknown),
      };
      // Anything but an API error is a bug: it is reported, and the screen still recovers.
      if (e is! ApiException) {
        FlutterError.reportError(
          FlutterErrorDetails(exception: e, stack: stack, library: 'play screen'),
        );
      }
      _refused(error);
      return false;
    }
    if (_disposed) {
      // The player left while the turn started. The server still finishes it; stop listening.
      unawaited(events.listen(null).cancel());
      return false;
    }
    _pending = _pending!.copyWith(phase: TurnPhase.streaming);
    _changed();
    await _turn?.cancel();
    _turn = events.listen(
      (event) => _onEvent(event, version),
      onError: (Object e) => _onEvent(
        TurnFailed(e is ApiException ? e : const ApiException(ApiErrorCode.network)),
        version,
      ),
      onDone: () => _turn = null,
      cancelOnError: true,
    );
    return true;
  }

  /// A turn the server refused before it started: nothing was saved or charged.
  void _refused(ApiException error) {
    switch (error.code) {
      case ApiErrorCode.versionConflict:
        final action = _pending?.input.action;
        _pending = null;
        _changed();
        _notice(StoryMovedOn(action: action));
        unawaited(reload());
      case ApiErrorCode.outOfCredits:
        final turn = _pending;
        _pending = null;
        _changed();
        _notice(OutOfCredits(error, turn: turn));
      case ApiErrorCode.unauthenticated:
        // The session is over and the router takes the player to sign in.
        _pending = null;
        _changed();
      case ApiErrorCode.validationError || ApiErrorCode.storyEnded:
        // Most likely a choice that is no longer offered, or a story that reached its ending
        // elsewhere (N6): show the story as it is now.
        _pending = null;
        _changed();
        _notice(TurnRefused(error));
        unawaited(reload());
      default:
        _pending = _pending?.copyWith(phase: TurnPhase.failed, text: '', error: error);
        _changed();
    }
  }

  void _onEvent(TurnEvent event, int sentVersion) {
    final pending = _pending;
    if (_disposed || pending == null || pending.failed) return;
    switch (event) {
      case TurnStarted(:final turn):
        _startedTurn = turn;
      case NarrationDelta(:final text):
        _pending = pending.copyWith(text: pending.text + text);
        _changed();
      case NarrationReset():
        // Blocked and rewritten (F4), or retried after a failure (T7): start the text over.
        _pending = pending.copyWith(text: '');
        _changed();
      case EndingRefused(:final refused):
        // N6: nothing was saved or charged. The player plays on, or ends without it.
        _refusal = EndingRefusal(turn: pending, parts: refused);
        _pending = null;
        _changed();
      case SceneCompleted(:final scene, :final version, :final clock, :final ending):
        final Scene saved;
        try {
          saved = Scene.fromJson(scene);
        } on Object catch (e, stack) {
          // The turn was saved, but its scene can't be read: a contract bug. Show the story as the
          // server has it.
          FlutterError.reportError(
            FlutterErrorDetails(exception: e, stack: stack, library: 'play screen'),
          );
          unawaited(_checkLanded(sentVersion, const ApiException(ApiErrorCode.server)));
          return;
        }
        _notice(SceneSaved(saved.turn));
        _story = _story!.withScene(
          saved,
          version: math.max(version, _story!.version),
          clockLabel: clock['label'] as String?,
          ending: StoryEnding.maybe(ending),
        );
        _remember([saved]);
        _pending = null;
        _changed();
        _notice(const CreditsSpent());
        _paintPlanned();
      case TurnFailed(:final error):
        if (error.code == ApiErrorCode.versionConflict) {
          // Another turn was saved first (T10): show the story as it is now, and give the player
          // their words back.
          _pending = null;
          _changed();
          _notice(StoryMovedOn(action: pending.input.action));
          unawaited(reload());
        } else if (error.code == ApiErrorCode.network || error.code == ApiErrorCode.timeout) {
          // The connection dropped: the turn may still have been saved. Look before offering a
          // retry; a retry would be refused as a conflict anyway.
          unawaited(_checkLanded(sentVersion, error));
        } else {
          // Nothing was saved and nothing was charged: drop the partial scene (T7).
          _pending = pending.copyWith(phase: TurnPhase.failed, text: '', error: error);
          _changed();
        }
    }
  }

  /// The stream ended without the saved scene. Looks at the story: the turn may have been saved
  /// (then it joins the feed), another turn may have been saved instead (then the story moved on),
  /// or nothing changed (then the turn failed and can be retried).
  Future<void> _checkLanded(int sentVersion, ApiException error) async {
    final input = _pending?.input;
    final expected = _startedTurn ?? (_story?.scenes.lastOrNull?.turn ?? 0) + 1;
    try {
      final fresh = await repository.get(storyId, scenes: pageSize);
      if (_disposed) return;
      if (fresh.version > sentVersion) {
        final mine = fresh.scenes.where((s) => s.turn == expected).firstOrNull;
        final landed = mine != null && input != null && _isTurn(mine, input);
        if (landed) _notice(SceneSaved(mine.turn));
        _merge(fresh);
        _pending = null;
        _changed();
        if (!landed) _notice(StoryMovedOn(action: input?.action));
        _paintPlanned();
        return;
      }
    } on Object {
      // Still offline: offer the retry below.
    }
    if (_disposed) return;
    _pending = _pending?.copyWith(phase: TurnPhase.failed, text: '', error: error);
    _changed();
  }

  /// Whether a saved scene is the turn the player sent, and not one played elsewhere.
  static bool _isTurn(Scene scene, TurnInput input) =>
      scene.kind == input.kind &&
      (input.kind != 'action' || scene.playerAction?.trim() == input.action?.trim());

  // ---- Pictures ---------------------------------------------------------------------------

  /// The picture a scene shows: the scene's own, or the same picture's newest URL when another
  /// scene already has it (M4).
  SceneImage? imageOf(Scene scene) {
    final image = scene.image;
    final id = image?.imageId;
    if (image == null || id == null || !image.isReady) return image;
    final cached = _pictures[id];
    return cached != null && cached.isReady ? cached : image;
  }

  void _remember(Iterable<Scene> scenes) {
    for (final scene in scenes) {
      final image = scene.image;
      final id = image?.imageId;
      if (image == null || id == null || !image.isReady) continue;
      final known = _pictures[id];
      // Keep the URL already in use while it works, so the picture isn't loaded twice.
      if (known == null || _expired(known)) _pictures[id] = image;
    }
  }

  bool _expired(SceneImage image) {
    final at = image.expiresAt;
    return at != null && !at.isAfter(_now().add(const Duration(seconds: 30)));
  }

  /// Asks for every planned picture that hasn't arrived (M3): after a scene completes, and for
  /// pictures that never arrived before the story was closed.
  void _paintPlanned() {
    for (final scene in _story?.scenes ?? const <Scene>[]) {
      if (scene.image?.isPending ?? false) unawaited(_paint(scene.turn));
    }
  }

  /// Illustrate (M2): a picture of any scene, paid in credits, also one that was skipped.
  Future<void> illustrate(int turn) => _paint(turn, illustrate: true);

  /// Asks for a scene's picture until it is ready or skipped. A picture is never an error (M3):
  /// failures retry quietly while they might pass, then leave the scene without one.
  Future<void> _paint(int turn, {bool illustrate = false}) async {
    if (!_painting.add(turn)) return;
    final before = _scene(turn)?.image;
    try {
      if (illustrate) {
        _setImage(
          turn,
          SceneImage(status: 'planned', kind: before?.kind ?? 'scene', planned: false),
        );
      }
      final kind = _scene(turn)?.image?.kind ?? 'scene';
      var wait = pictureInterval;
      for (var tries = 0; tries < 20 && !_disposed; tries++) {
        SceneImage result;
        try {
          result = illustrate
              ? await repository.illustrate(storyId, turn, kind: kind)
              : await repository.picture(storyId, turn, kind: kind);
        } on ApiException catch (e) {
          if (_disposed) return;
          if (illustrate && e.code == ApiErrorCode.outOfCredits) {
            // The player asked and can't pay: the scene stays as it was, and the sheet offers
            // their own key.
            _setImage(turn, before ?? SceneImage(status: 'skipped', kind: kind, planned: false));
            _notice(OutOfCredits(e, picture: turn));
            return;
          }
          if (!e.code.isRetryable || e.code == ApiErrorCode.versionConflict) {
            _setImage(turn, SceneImage(status: 'skipped', kind: kind));
            return;
          }
          await _sleep(e.retryAfter ?? wait);
          wait = _longer(wait);
          continue;
        }
        if (_disposed) return;
        if (!result.isPending) {
          _setImage(turn, result);
          if (result.isReady) _notice(const CreditsSpent());
          return;
        }
        await _sleep(wait);
        wait = _longer(wait);
      }
      if (!_disposed && (_scene(turn)?.image?.isPending ?? false)) {
        _setImage(turn, SceneImage(status: 'skipped', kind: kind));
      }
    } finally {
      _painting.remove(turn);
    }
  }

  Duration _longer(Duration wait) =>
      Duration(milliseconds: math.min(wait.inMilliseconds * 3 ~/ 2, 6000));

  /// A ready picture failed to load: its signed URL most likely expired. Asks for a fresh URL by
  /// its image id (never draws), once in a while at most; otherwise the scene goes on without it.
  Future<void> pictureFailed(int turn) async {
    final scene = _scene(turn);
    final image = scene == null ? null : imageOf(scene);
    if (image == null || !image.isReady) return;
    final id = image.imageId;
    if (id == null) {
      _giveUp(turn, image);
      return;
    }
    // Scenes that share the picture wait for the same refresh.
    var refresh = _refreshing[id];
    if (refresh == null) {
      final last = _refreshedAt[id];
      if (last != null && _now().difference(last) < const Duration(minutes: 5)) {
        _giveUp(turn, image);
        return;
      }
      _refreshedAt[id] = _now();
      refresh = _refreshing[id] = _refresh(id, image.kind);
    }
    final fresh = await refresh;
    if (_disposed) return;
    // The same URL again would fail again: the scene goes on without it.
    if (fresh != null && fresh.isReady && fresh.url != image.url) {
      _pictures[id] = fresh;
      _changed();
    } else {
      _giveUp(turn, image);
    }
  }

  Future<SceneImage?> _refresh(String id, String kind) async {
    try {
      return await repository.refreshPicture(storyId, id, kind: kind);
    } on ApiException {
      return null;
    } finally {
      unawaited(_refreshing.remove(id));
    }
  }

  /// The scene goes on without a picture that won't load. Its URL is forgotten, so no other scene
  /// tries it again.
  void _giveUp(int turn, SceneImage image) {
    if (image.imageId case final id?) _pictures.remove(id);
    _setImage(turn, image.copyWith(status: 'skipped'));
  }

  Scene? _scene(int turn) => _story?.scenes.where((s) => s.turn == turn).firstOrNull;

  void _setImage(int turn, SceneImage image) {
    final story = _story;
    if (story == null || _disposed) return;
    final id = image.imageId;
    if (image.isReady && id != null) _pictures[id] = image;
    _story = story.copyWith(
      scenes: [for (final s in story.scenes) s.turn == turn ? s.withImage(image) : s],
    );
    _changed();
  }

  // ---- Hiding, reporting and settings -----------------------------------------------------

  /// Reports a scene (F6). With [block], its text is hidden at once, and for good. Throws
  /// [ApiException] for the report sheet to show.
  Future<void> report(
    int turn, {
    required String category,
    String? note,
    required bool block,
  }) async {
    await repository.report(storyId, turn, category: category, note: note, block: block);
    if (block && !_disposed && _blocked.add(turn)) _changed();
  }

  /// Saves the story's title and the settings that changed (S6). Throws [ApiException] for the
  /// sheet to show.
  Future<void> save({String? title, Json? settings}) async {
    final saved = await repository.update(storyId, title: title, settings: settings);
    if (_disposed) return;
    final story = _story;
    if (story == null) return;
    _story = story.copyWith(
      title: saved.title,
      settings: saved.settings,
      version: math.max(saved.version, story.version),
    );
    _changed();
  }

  // ---- Plumbing ---------------------------------------------------------------------------

  void _notice(PlayNotice notice) {
    if (!_disposed) _notices.add(notice);
  }

  void _changed() {
    if (!_disposed) notifyListeners();
  }

  /// A delay that ends at once when the controller is disposed, so no timer outlives the screen.
  Future<void> _sleep(Duration duration) {
    final done = Completer<void>();
    late final Timer timer;
    timer = Timer(duration, () {
      _sleeps.remove(timer);
      done.complete();
    });
    _sleeps[timer] = done;
    return done.future;
  }

  @override
  void dispose() {
    _disposed = true;
    unawaited(_turn?.cancel());
    for (final MapEntry(key: timer, value: done) in _sleeps.entries) {
      timer.cancel();
      done.complete();
    }
    _sleeps.clear();
    unawaited(_notices.close());
    super.dispose();
  }
}

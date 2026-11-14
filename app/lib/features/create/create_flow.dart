import 'package:flutter/foundation.dart';

import '../../core/api/api_error.dart';
import 'draft.dart';
import 'draft_repository.dart';

/// Where the create flow stands: writing the premise, waiting for the draft, then reviewing it
/// a screen at a time, the world first and the character after it (Miki, 2026-11-14).
enum CreateStage {
  premise,
  drafting,
  world,
  character;

  /// Whether the draft is under review, on either of its screens.
  bool get isReview => this == world || this == character;
}

/// The create flow (G1, G2, S1): a premise becomes a draft, the player reviews and changes it,
/// then starts the story. Every change sends the version last seen, and a stale draft is reloaded
/// before the player tries again (T10).
class CreateFlow extends ChangeNotifier {
  CreateFlow(
    this._drafts, {
    this.onCharged,
    this.landingPoll = const Duration(seconds: 4),
    this.landingWait = const Duration(minutes: 3),
  });

  final DraftRepository _drafts;

  /// How often the draft is read again after a change's reply was lost, and for how long from
  /// the start of the change: as long as the server may still be working on it ([_landed]).
  final Duration landingPoll;
  final Duration landingWait;

  /// Called after each request that may have spent credits (K2), whatever its outcome, so the
  /// balance shown elsewhere can be read again.
  final VoidCallback? onCharged;

  CreateStage _stage = CreateStage.premise;
  Draft? _draft;
  Object? _error;
  Redraft _redrafting = Redraft.none;
  bool _saving = false;
  bool _starting = false;
  bool _disposed = false;

  CreateStage get stage => _stage;

  /// The premise being drafted, to quote back while the player waits.
  String? get draftingPremise => _draftingPremise;
  String? _draftingPremise;

  /// The draft under review.
  Draft? get draft => _draft;

  /// Why drafting or starting failed, shown where the player is.
  Object? get error => _error;

  /// The parts being redrafted by a change in flight.
  Redraft get redrafting => _redrafting;

  /// Whether a draft is being made, a change saved or the story started. One at a time, so
  /// nothing changes under a start.
  bool get busy => _stage == CreateStage.drafting || _saving || _starting;

  bool get starting => _starting;

  /// Whether leaving now would lose drafted work: a draft is coming or under review, and no story
  /// holds it yet.
  bool get hasUnsavedDraft =>
      _stage == CreateStage.drafting || (_draft != null && _draft!.storyId == null);

  void _notify() {
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }

  /// Drafts the world and the character, in [language] (S10). With a [premiseId] and no
  /// [premise], the starter's own text is the premise; [quote] is what the player sees of it
  /// meanwhile.
  Future<void> create({
    String? premise,
    String? premiseId,
    String? quote,
    required Rating rating,
    String language = 'en',
    DraftChoices choices = const DraftChoices(),
  }) async {
    if (_stage == CreateStage.drafting) return;
    _draftingPremise = quote ?? premise;
    _stage = CreateStage.drafting;
    _error = null;
    _notify();
    try {
      _draft = await _drafts.create(
        premise: premise,
        premiseId: premiseId,
        rating: rating,
        language: language,
        choices: choices,
      );
      _stage = CreateStage.world;
    } on Object catch (e) {
      _error = e;
      _stage = CreateStage.premise;
    }
    _notify();
    if (!_disposed) onCharged?.call();
  }

  /// Moves between the two screens of the review. A change in flight carries on, and shows on
  /// whichever screen it redrafts. The screen stays put while the story starts.
  void show(CreateStage screen) {
    assert(screen.isReview);
    if (!_stage.isReview || _stage == screen || _starting) return;
    _stage = screen;
    _error = null;
    _notify();
  }

  /// Saves a direct edit. Returns null when it saved, or the failure for the player to see. A
  /// version conflict reloads the draft first.
  Future<Object?> edit(DraftEdit edit) {
    final draft = _draft!;
    return _change(redraftFor(draft, edit), () => _drafts.edit(draft, edit));
  }

  /// A change in plain words to one part, asked at the lines that tell of [about] when given.
  /// Always one model call.
  Future<Object?> revise(DraftPart part, String instruction, {LineKind? about}) {
    final draft = _draft!;
    return _change(
      Redraft(world: part == DraftPart.world, character: part == DraftPart.character),
      () => _drafts.revise(draft, part, instruction, about: about),
    );
  }

  Future<Object?> _change(Redraft cost, Future<Draft> Function() save) async {
    if (busy) return StateError('Another change is being saved');
    final sent = _draft!;
    final waited = Stopwatch()..start();
    _redrafting = cost;
    _saving = true;
    _notify();
    try {
      _draft = await save();
      return null;
    } on ApiException catch (e) {
      if (e.code == ApiErrorCode.versionConflict) await reload();
      if (e.startedStoryId case final storyId?) _draft = _draft?.started(storyId);
      if (e.lostTheReply) {
        // A connection that dropped leaves the server working on a change that calls the model.
        // A page from a proxy in place of an answer says nothing either way: one look.
        final working = !cost.isFree && e.code != ApiErrorCode.server;
        if (await _landed(sent, waited, working: working)) return null;
      }
      return e;
    } on Object catch (e) {
      return e;
    } finally {
      _redrafting = Redraft.none;
      _saving = false;
      _notify();
      if (!cost.isFree && !_disposed) onCharged?.call();
    }
  }

  /// Whether a change whose reply never came was saved all the same. The server finishes a
  /// change whatever becomes of the connection, and a phone drops a request that stays silent
  /// for a minute or two: on 2026-11-11 a change that took the model 111 s was shown as failed,
  /// and asking again failed too, against the draft the first one had changed. So the draft is
  /// read again until its version has moved on, for as long as the server may still be
  /// [working]: [landingWait] from the start of the change, or one look when it can't be. The
  /// change stays in flight meanwhile, so nothing else is sent under it.
  Future<bool> _landed(Draft sent, Stopwatch waited, {required bool working}) async {
    while (!_disposed) {
      try {
        final latest = await _drafts.get(sent.id);
        if (latest.version > sent.version) {
          _draft = latest;
          return true;
        }
      } on Object {
        // Still no connection: look again.
      }
      if (!working || waited.elapsed + landingPoll > landingWait) return false;
      await Future<void>.delayed(landingPoll);
    }
    return false;
  }

  /// Fetches the draft as the server has it now.
  Future<void> reload() async {
    final draft = _draft;
    if (draft == null) return;
    try {
      _draft = await _drafts.get(draft.id);
      _notify();
    } on Object {
      // The next change answers with the same conflict, and reloads again.
    }
  }

  /// Starts the story and returns its id, or null when it failed ([error] says why). A draft
  /// that already started returns its story.
  Future<String?> start() async {
    final draft = _draft;
    if (draft == null || busy) return null;
    if (draft.storyId case final storyId?) return storyId;
    _starting = true;
    _error = null;
    _notify();
    try {
      final storyId = await _drafts.start(draft);
      _draft = draft.started(storyId);
      return storyId;
    } on ApiException catch (e) {
      if (e.startedStoryId case final storyId?) {
        _draft = draft.started(storyId);
        return storyId;
      }
      if (e.code == ApiErrorCode.versionConflict) await reload();
      _error = e;
      return null;
    } on Object catch (e) {
      _error = e;
      return null;
    } finally {
      _starting = false;
      _notify();
    }
  }

  /// Clears a shown failure.
  void clearError() {
    if (_error == null) return;
    _error = null;
    _notify();
  }
}

extension on ApiException {
  /// The request may have reached the server, and only its reply was lost on the way back.
  bool get lostTheReply =>
      code == ApiErrorCode.network || code == ApiErrorCode.timeout || code == ApiErrorCode.server;

  /// `403 forbidden` on a draft that has started carries its story (docs/API.md).
  String? get startedStoryId => code == ApiErrorCode.forbidden && details['story_id'] is String
      ? details['story_id'] as String
      : null;
}

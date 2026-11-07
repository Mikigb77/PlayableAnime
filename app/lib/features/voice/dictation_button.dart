import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/l10n.dart';
import '../../design/design.dart';
import 'dictation_controller.dart';
import 'dictation_mode.dart';
import 'input_mode.dart';
import 'speech_engine.dart';

/// The microphone button for any text box (V1): put it in a [Composer]'s mic slot or a text
/// field's suffix. It hides where the platform or browser can't record or recognize speech, asks
/// for permission on the first tap (V5), and explains how to allow the mic if the player said no.
/// Give it the story or draft the box belongs to, so online dictation knows its names (V6, C6).
class DictationButton extends ConsumerStatefulWidget {
  const DictationButton({
    super.key,
    required this.tracker,
    this.localeId = storyLanguage,
    this.storyId,
    this.draftId,
  });

  /// The box's tracker, which also records that words were dictated (V7).
  final InputModeTracker tracker;
  final String? localeId;
  final String? storyId;
  final String? draftId;

  @override
  ConsumerState<DictationButton> createState() => _DictationButtonState();
}

class _DictationButtonState extends ConsumerState<DictationButton> {
  late SpeechEngine _engine;
  late DictationController _dictation;
  late final AppLifecycleListener _lifecycle;
  bool _supported = false;
  SpeechFailure? _shownFailure;

  @override
  void initState() {
    super.initState();
    _use(ref.read(speechEngineProvider));
    // Leaving the app turns the mic off, keeping what was said: the mic is on only while the
    // button shows it (V5).
    _lifecycle = AppLifecycleListener(onHide: _hidden);
    // The player can switch between online and on-device dictation in Account.
    ref.listenManual(speechEngineProvider, (_, engine) {
      if (!identical(engine, _engine)) setState(() => _swap(engine));
    });
  }

  void _use(SpeechEngine engine) {
    _engine = engine;
    _supported = false;
    _dictation = DictationController(
      engine: engine,
      tracker: widget.tracker,
      localeId: widget.localeId,
      context: SpeechContext(storyId: widget.storyId, draftId: widget.draftId),
    )..addListener(_changed);
    engine.isSupported().then((supported) {
      if (mounted && identical(engine, _engine)) setState(() => _supported = supported);
    });
  }

  void _swap(SpeechEngine engine) {
    _dictation
      ..removeListener(_changed)
      ..dispose();
    _use(engine);
  }

  @override
  void didUpdateWidget(DictationButton old) {
    super.didUpdateWidget(old);
    // The story's language changed (S10): the next dictation listens for the new one.
    _dictation.localeId = widget.localeId;
  }

  void _hidden() {
    final phase = _dictation.phase;
    if (phase == DictationPhase.listening || phase == DictationPhase.starting) _dictation.stop();
  }

  @override
  void dispose() {
    _lifecycle.dispose();
    _dictation
      ..removeListener(_changed)
      ..dispose();
    super.dispose();
  }

  void _changed() {
    if (!mounted) return;
    final failure = _dictation.failure;
    if (failure != null && failure != _shownFailure) {
      _shownFailure = failure;
      final l10n = context.l10n;
      final message = switch (failure.code) {
        SpeechFailure.offline => l10n.micOffline,
        SpeechFailure.outOfCredits => l10n.micOutOfCredits,
        SpeechFailure.limited => l10n.micLimited,
        _ => l10n.micError,
      };
      ScaffoldMessenger.maybeOf(context)?.showSnackBar(SnackBar(content: Text(message)));
    }
    if (_dictation.phase == DictationPhase.unavailable) {
      ScaffoldMessenger.maybeOf(
        context,
      )?.showSnackBar(SnackBar(content: Text(context.l10n.micUnavailable)));
    }
    setState(() {});
  }

  Future<void> _retryOrExplain() async {
    if (!await _dictation.retryPermission() && mounted) _explainDenied();
  }

  void _explainDenied() {
    final l10n = context.l10n;
    showAppSheet<void>(
      context: context,
      title: l10n.micDeniedTitle,
      builder: (context) => Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            l10n.micDeniedBody,
            style: Theme.of(
              context,
            ).textTheme.bodyLarge!.copyWith(color: context.lucid.textSecondary),
          ),
          const SizedBox(height: Space.xl),
          FilledButton(onPressed: () => Navigator.of(context).pop(), child: Text(l10n.gotIt)),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (!_supported || _dictation.phase == DictationPhase.unavailable) {
      return const SizedBox.shrink();
    }
    final phase = _dictation.phase;
    // Sending waits for the words: the mic spins until they land, and can't come back on.
    final finishing = _dictation.finishing;
    return MicButton(
      visual: switch (phase) {
        _ when finishing => MicVisual.transcribing,
        DictationPhase.idle || DictationPhase.unavailable => MicVisual.idle,
        DictationPhase.starting => MicVisual.starting,
        DictationPhase.listening => MicVisual.listening,
        DictationPhase.transcribing => MicVisual.transcribing,
        DictationPhase.denied => MicVisual.denied,
      },
      level: _dictation.level,
      onPressed: switch (phase) {
        _ when finishing => null,
        DictationPhase.denied => _retryOrExplain,
        DictationPhase.transcribing => null, // the words are on their way
        _ => _dictation.toggle,
      },
    );
  }
}

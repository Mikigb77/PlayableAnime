import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/l10n.dart';
import '../../design/design.dart';
import 'dictation_controller.dart';
import 'input_mode.dart';
import 'speech_engine.dart';

/// The microphone button for any text box (V1): put it in a [Composer]'s mic slot or a text
/// field's suffix. It hides where the platform or browser can't recognize speech, asks for
/// permission on the first tap (V5), and explains how to allow the mic if the player said no.
class DictationButton extends ConsumerStatefulWidget {
  const DictationButton({super.key, required this.tracker, this.localeId});

  /// The box's tracker, which also records that words were dictated (V7).
  final InputModeTracker tracker;
  final String? localeId;

  @override
  ConsumerState<DictationButton> createState() => _DictationButtonState();
}

class _DictationButtonState extends ConsumerState<DictationButton> {
  late final SpeechEngine _engine = ref.read(speechEngineProvider);
  late final DictationController _dictation = DictationController(
    engine: _engine,
    tracker: widget.tracker,
    localeId: widget.localeId,
  )..addListener(_changed);
  bool _supported = false;
  SpeechFailure? _shownFailure;

  @override
  void initState() {
    super.initState();
    _engine.isSupported().then((supported) {
      if (mounted) setState(() => _supported = supported);
    });
  }

  @override
  void dispose() {
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
      ScaffoldMessenger.maybeOf(
        context,
      )?.showSnackBar(SnackBar(content: Text(context.l10n.micError)));
    }
    if (_dictation.phase == DictationPhase.unavailable) {
      ScaffoldMessenger.maybeOf(
        context,
      )?.showSnackBar(SnackBar(content: Text(context.l10n.micUnavailable)));
    }
    setState(() {});
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
    return MicButton(
      visual: switch (phase) {
        DictationPhase.idle || DictationPhase.unavailable => MicVisual.idle,
        DictationPhase.starting => MicVisual.starting,
        DictationPhase.listening => MicVisual.listening,
        DictationPhase.denied => MicVisual.denied,
      },
      level: _dictation.level,
      onPressed: phase == DictationPhase.denied ? _explainDenied : _dictation.toggle,
    );
  }
}

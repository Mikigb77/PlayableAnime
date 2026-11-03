import 'package:flutter/material.dart';

import '../../core/l10n.dart';
import '../motion.dart';
import '../theme.dart';
import '../tokens.dart';

/// Where a suggested choice leads (S2): along the current thread, or away from it.
enum ChoiceKind {
  thread,
  personal,
  side,
  wild;

  static ChoiceKind fromWire(String? value) => switch (value) {
    'personal' => personal,
    'side' => side,
    'wild' => wild,
    _ => thread,
  };

  IconData get icon => switch (this) {
    thread => Icons.arrow_forward_rounded,
    personal => Icons.favorite_border_rounded,
    side => Icons.alt_route_rounded,
    wild => Icons.auto_awesome_outlined,
  };

  String label(AppLocalizations l10n) => switch (this) {
    thread => l10n.choiceKindThread,
    personal => l10n.choiceKindPersonal,
    side => l10n.choiceKindSide,
    wild => l10n.choiceKindWild,
  };
}

/// One suggested choice.
@immutable
class StoryChoice {
  const StoryChoice({required this.id, required this.label, this.kind = ChoiceKind.thread});

  final String id;
  final String label;
  final ChoiceKind kind;
}

/// The standing actions every scene offers (S2).
enum StandingAction {
  wait,
  observe;

  String get wire => name;

  IconData get icon => switch (this) {
    wait => Icons.hourglass_empty_rounded,
    observe => Icons.visibility_outlined,
  };

  String label(AppLocalizations l10n) => switch (this) {
    wait => l10n.standingWait,
    observe => l10n.standingObserve,
  };
}

/// The scene's suggested choices as full-width tiles, then the standing actions. Tiles fade up one
/// after another when a scene's choices appear.
class StoryChoices extends StatelessWidget {
  const StoryChoices({
    super.key,
    required this.choices,
    required this.onChoice,
    this.standing = StandingAction.values,
    this.onStanding,
    this.enabled = true,
  });

  final List<StoryChoice> choices;
  final ValueChanged<StoryChoice> onChoice;
  final List<StandingAction> standing;
  final ValueChanged<StandingAction>? onStanding;
  final bool enabled;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (final (i, choice) in choices.indexed)
          _Entrance(
            key: ValueKey(choice.id),
            index: i,
            child: Padding(
              padding: const EdgeInsets.only(bottom: Space.sm),
              child: StoryChoiceTile(
                choice: choice,
                onPressed: enabled ? () => onChoice(choice) : null,
              ),
            ),
          ),
        if (onStanding != null && standing.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(top: Space.xs),
            child: Wrap(
              spacing: Space.sm,
              runSpacing: Space.sm,
              children: [
                for (final action in standing)
                  ActionChip(
                    avatar: Icon(action.icon, size: 18),
                    label: Text(action.label(l10n)),
                    onPressed: enabled ? () => onStanding!(action) : null,
                  ),
              ],
            ),
          ),
      ],
    );
  }
}

/// A single suggested choice: the kind's icon and the label, wrapping as long as it needs.
class StoryChoiceTile extends StatelessWidget {
  const StoryChoiceTile({super.key, required this.choice, required this.onPressed});

  final StoryChoice choice;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = context.lucid;
    final enabled = onPressed != null;
    final away = choice.kind != ChoiceKind.thread;
    return Semantics(
      button: true,
      enabled: enabled,
      hint: choice.kind.label(context.l10n),
      child: Material(
        color: theme.colorScheme.surfaceContainerLow,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(14),
          side: BorderSide(color: theme.colorScheme.outlineVariant),
        ),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onPressed,
          child: ConstrainedBox(
            constraints: const BoxConstraints(minHeight: Layout.minTouch + 4),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: Space.lg, vertical: Space.md),
              child: Row(
                children: [
                  Icon(
                    choice.kind.icon,
                    size: 18,
                    color: enabled
                        ? (away ? colors.accent : colors.textSecondary)
                        : colors.textMuted.withValues(alpha: 0.6),
                  ),
                  const SizedBox(width: Space.md),
                  Expanded(
                    child: Text(
                      choice.label,
                      style: theme.textTheme.bodyLarge!.copyWith(
                        color: enabled ? colors.textPrimary : colors.textMuted,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Fades and lifts a child in, delayed by its [index] so a list cascades.
class _Entrance extends StatefulWidget {
  const _Entrance({super.key, required this.index, required this.child});

  final int index;
  final Widget child;

  @override
  State<_Entrance> createState() => _EntranceState();
}

class _EntranceState extends State<_Entrance> with SingleTickerProviderStateMixin {
  static const _stagger = Duration(milliseconds: 40);

  // The delay is part of the animation (an Interval), so no timer outlives the widget.
  late final _controller = AnimationController(
    vsync: this,
    duration: Motion.base + _stagger * widget.index,
  );
  late final _curve = CurvedAnimation(
    parent: _controller,
    curve: Interval(
      (_stagger * widget.index).inMicroseconds / _controller.duration!.inMicroseconds,
      1,
      curve: Motion.emphasized,
    ),
  );
  bool _started = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_started) return;
    _started = true;
    if (Motion.reduced(context)) {
      _controller.value = 1;
    } else {
      _controller.forward();
    }
  }

  @override
  void dispose() {
    _curve.dispose();
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return FadeTransition(
      opacity: _curve,
      child: SlideTransition(
        position: Tween(begin: const Offset(0, 0.15), end: Offset.zero).animate(_curve),
        child: widget.child,
      ),
    );
  }
}

import 'package:flutter/material.dart';

import '../../core/l10n.dart';
import '../theme.dart';
import '../tokens.dart';
import 'pills.dart';
import 'rise_in.dart';

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

/// The scene's suggested choices as full-width tiles, the first one lit, then the standing
/// actions as quiet pills. Tiles rise in one after another when a scene's choices appear.
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
          RiseIn(
            key: ValueKey(choice.id),
            order: i,
            child: Padding(
              padding: const EdgeInsets.only(bottom: 9),
              child: StoryChoiceTile(
                choice: choice,
                first: i == 0,
                onPressed: enabled ? () => onChoice(choice) : null,
              ),
            ),
          ),
        if (onStanding != null && standing.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(top: Space.xs),
            child: Wrap(
              spacing: 10,
              children: [
                for (final action in standing)
                  GhostPill(
                    large: true,
                    icon: action.icon,
                    label: action.label(l10n),
                    onPressed: enabled ? () => onStanding!(action) : null,
                  ),
              ],
            ),
          ),
      ],
    );
  }
}

/// A single suggested choice: the kind's icon in a round of the accent, the kind in small
/// capitals and the label, wrapping as long as it needs. The [first] of a scene's choices wears
/// a ring and a glow in the accent: the way the story is already going.
class StoryChoiceTile extends StatelessWidget {
  const StoryChoiceTile({
    super.key,
    required this.choice,
    required this.onPressed,
    this.first = false,
  });

  final StoryChoice choice;
  final VoidCallback? onPressed;
  final bool first;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final colors = context.lucid;
    final enabled = onPressed != null;
    final kind = choice.kind.label(context.l10n);
    return Semantics(
      button: true,
      enabled: enabled,
      hint: kind,
      child: DecoratedBox(
        decoration: BoxDecoration(
          borderRadius: Radii.card,
          boxShadow: [
            if (first && enabled)
              BoxShadow(color: colors.accent.withValues(alpha: 0.1), blurRadius: 26),
          ],
        ),
        child: Material(
          type: MaterialType.transparency,
          shape: RoundedRectangleBorder(
            borderRadius: Radii.card,
            side: BorderSide(
              color: first && enabled
                  ? colors.accent.withValues(alpha: 0.4)
                  : scheme.outlineVariant,
            ),
          ),
          clipBehavior: Clip.antiAlias,
          child: Ink(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [scheme.surfaceContainer, scheme.surface],
              ),
            ),
            child: InkWell(
              onTap: onPressed,
              child: ConstrainedBox(
                constraints: const BoxConstraints(minHeight: 62),
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(13, 12, 14, 12),
                  child: Row(
                    children: [
                      Container(
                        width: 38,
                        height: 38,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          color: enabled ? colors.accent.withValues(alpha: 0.12) : colors.veil,
                        ),
                        child: Icon(
                          choice.kind.icon,
                          size: 19,
                          color: enabled ? colors.accent : colors.textMuted.withValues(alpha: 0.6),
                        ),
                      ),
                      const SizedBox(width: 14),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            // The screen reader has the kind as the button's hint.
                            ExcludeSemantics(
                              child: Text(
                                kind.toUpperCase(),
                                style: context.lucidText.overline.copyWith(
                                  fontSize: 10,
                                  height: 1.2,
                                  color: colors.textMuted,
                                ),
                              ),
                            ),
                            const SizedBox(height: 4),
                            Text(
                              choice.label,
                              style: theme.textTheme.bodyLarge!.copyWith(
                                fontSize: 15.5,
                                height: 1.32,
                                fontWeight: FontWeight.w500,
                                color: enabled ? colors.textPrimary : colors.textMuted,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

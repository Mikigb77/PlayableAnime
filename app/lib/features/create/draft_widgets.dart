import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/api_error.dart';
import '../../core/api/api_error_text.dart';
import '../../core/l10n.dart';
import '../../core/session/session_controller.dart';
import '../../design/design.dart';
import '../account/account_repository.dart';
import '../account/out_of_credits_sheet.dart';
import 'draft.dart';

/// The highest rating the signed-in account may choose (F8). An account under 17 gets Teen only,
/// and the server lifts the limit on the 17th birthday. The account as `GET /v1/me` last read it
/// decides, and the session's copy of the user until then. Without a known limit, Teen.
final maxRatingProvider = Provider<Rating>((ref) {
  if (ref.watch(meProvider).value case final me?) {
    return me.matureAllowed ? Rating.mature : Rating.teen;
  }
  return Rating.fromWire(ref.watch(sessionProvider).session?.user['max_rating']);
});

/// Offers the out-of-credits sheet (K2) when [error] is `402 out_of_credits`, and says whether the
/// player added their own key there, so the caller tries again on it (K6). The caller tries
/// again itself, so the note says so ([retrying]).
Future<bool> offerOwnKey(BuildContext context, Object? error, {bool retrying = true}) async {
  if (error is! ApiException || error.code != ApiErrorCode.outOfCredits || !context.mounted) {
    return false;
  }
  final added = await showOutOfCreditsSheet(context, error) == OutOfCreditsOutcome.keyAdded;
  if (added && retrying && context.mounted) {
    ScaffoldMessenger.maybeOf(context)
      ?..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(context.l10n.oocKeySavedRetrying)));
  }
  return added;
}

extension DraftChoiceLabels on AppLocalizations {
  String rating(Rating rating) => switch (rating) {
    Rating.teen => ratingTeen,
    Rating.mature => ratingMature,
  };

  String ratingBody(Rating rating) => switch (rating) {
    Rating.teen => ratingTeenBody,
    Rating.mature => ratingMatureBody,
  };

  String physics(Physics physics) => switch (physics) {
    Physics.funFirst => physicsFunFirst,
    Physics.strict => physicsStrict,
  };

  String physicsBody(Physics physics) => switch (physics) {
    Physics.funFirst => physicsFunFirstBody,
    Physics.strict => physicsStrictBody,
  };

  String difficulty(Difficulty difficulty) => switch (difficulty) {
    Difficulty.story => difficultyStory,
    Difficulty.balanced => difficultyBalanced,
    Difficulty.brutal => difficultyBrutal,
  };

  String difficultyBody(Difficulty difficulty) => switch (difficulty) {
    Difficulty.story => difficultyStoryBody,
    Difficulty.balanced => difficultyBalancedBody,
    Difficulty.brutal => difficultyBrutalBody,
  };

  String events(EventFrequency events) => switch (events) {
    EventFrequency.calm => eventsCalm,
    EventFrequency.normal => eventsNormal,
    EventFrequency.dramatic => eventsDramatic,
  };

  String eventsBody(EventFrequency events) => switch (events) {
    EventFrequency.calm => eventsCalmBody,
    EventFrequency.normal => eventsNormalBody,
    EventFrequency.dramatic => eventsDramaticBody,
  };

  String gift(GiftStrength gift) => switch (gift) {
    GiftStrength.none => giftNone,
    GiftStrength.small => giftSmall,
    GiftStrength.rare => giftRare,
    GiftStrength.overpowered => giftOverpowered,
  };

  String giftBody(GiftStrength gift) => switch (gift) {
    GiftStrength.none => giftNoneBody,
    GiftStrength.small => giftSmallBody,
    GiftStrength.rare => giftRareBody,
    GiftStrength.overpowered => giftOverpoweredBody,
  };

  /// What a change costs, in words, before the player makes it.
  String cost(Redraft redraft) => switch (redraft) {
    Redraft(isFree: true) => costFree,
    Redraft(world: true, character: true) => costBoth,
    Redraft(world: true) => costWorld,
    _ => costCharacter,
  };
}

/// A small label above a group of controls in a form or sheet.
class FieldLabel extends StatelessWidget {
  const FieldLabel(this.text, {super.key, this.top = Space.xl});

  final String text;
  final double top;

  @override
  Widget build(BuildContext context) => Padding(
    padding: EdgeInsets.only(top: top, bottom: Space.sm),
    child: Semantics(
      header: true,
      child: Text(text.toUpperCase(), style: context.lucidText.overline),
    ),
  );
}

/// One choice out of a few (physics, difficulty, events, gift), as chips with the chosen one's
/// meaning spelled out underneath.
class ChoiceField<T> extends StatelessWidget {
  const ChoiceField({
    super.key,
    required this.label,
    required this.values,
    required this.value,
    required this.labelOf,
    required this.bodyOf,
    required this.onChanged,
  });

  final String label;
  final List<T> values;
  final T value;
  final String Function(T) labelOf;
  final String Function(T) bodyOf;
  final ValueChanged<T>? onChanged;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        FieldLabel(label),
        Wrap(
          spacing: Space.sm,
          runSpacing: Space.sm,
          children: [
            for (final option in values)
              ChoiceChip(
                label: Text(labelOf(option)),
                selected: option == value,
                showCheckmark: false,
                onSelected: onChanged == null ? null : (_) => onChanged!(option),
              ),
          ],
        ),
        const SizedBox(height: Space.sm),
        AnimatedSwitcher(
          duration: Motion.of(context, Motion.fast),
          child: Text(
            bodyOf(value),
            key: ValueKey(value),
            style: theme.textTheme.bodyMedium!.copyWith(color: context.lucid.textSecondary),
          ),
        ),
      ],
    );
  }
}

/// Teen or Mature 17+ (F2), as two tiles that say what each allows. Mature is locked for an
/// account under 17 (F8).
class RatingChoice extends ConsumerWidget {
  const RatingChoice({super.key, required this.value, required this.onChanged, this.costOf});

  final Rating value;
  final ValueChanged<Rating>? onChanged;

  /// What switching to a rating would cost, shown under it when it isn't free.
  final Redraft Function(Rating)? costOf;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = context.l10n;
    final max = ref.watch(maxRatingProvider);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (final rating in Rating.values) ...[
          if (rating != Rating.values.first) const SizedBox(height: Space.sm),
          _ChoiceTile(
            title: l10n.rating(rating),
            body: l10n.ratingBody(rating),
            note: switch (rating) {
              Rating.mature when max == Rating.teen => l10n.ratingMatureLocked,
              _ when rating != value && costOf != null && !costOf!(rating).isFree => l10n.cost(
                costOf!(rating),
              ),
              _ => null,
            },
            selected: rating == value,
            locked: rating == Rating.mature && max == Rating.teen,
            onTap: onChanged == null ? null : () => onChanged!(rating),
          ),
        ],
      ],
    );
  }
}

class _ChoiceTile extends StatelessWidget {
  const _ChoiceTile({
    required this.title,
    required this.body,
    required this.selected,
    this.note,
    this.locked = false,
    this.onTap,
  });

  final String title;
  final String body;
  final String? note;
  final bool selected;
  final bool locked;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = context.lucid;
    final scheme = theme.colorScheme;
    final muted = locked ? colors.textMuted : null;
    return Semantics(
      inMutuallyExclusiveGroup: true,
      checked: selected,
      enabled: !locked && onTap != null,
      button: true,
      child: AnimatedContainer(
        duration: Motion.of(context, Motion.fast),
        decoration: BoxDecoration(
          color: selected ? colors.accentSoft : scheme.surfaceContainerLow,
          borderRadius: Radii.card,
          border: Border.all(
            color: selected ? colors.accent.withValues(alpha: 0.7) : scheme.outlineVariant,
          ),
        ),
        child: Material(
          type: MaterialType.transparency,
          child: InkWell(
            borderRadius: Radii.card,
            onTap: locked ? null : onTap,
            child: Padding(
              padding: const EdgeInsets.all(Space.lg),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          title,
                          style: theme.textTheme.titleMedium!.copyWith(
                            color: muted ?? (selected ? colors.onAccentSoft : null),
                          ),
                        ),
                        const SizedBox(height: Space.xs),
                        Text(
                          body,
                          style: theme.textTheme.bodyMedium!.copyWith(
                            color: muted ?? colors.textSecondary,
                          ),
                        ),
                        if (note case final note?) ...[
                          const SizedBox(height: Space.sm),
                          Text(
                            note,
                            style: context.lucidText.meta.copyWith(color: colors.textMuted),
                          ),
                        ],
                      ],
                    ),
                  ),
                  const SizedBox(width: Space.md),
                  ExcludeSemantics(
                    child: Icon(
                      locked
                          ? Icons.lock_outline_rounded
                          : selected
                          ? Icons.check_circle_rounded
                          : Icons.circle_outlined,
                      size: 22,
                      color: locked
                          ? colors.textMuted
                          : selected
                          ? colors.accent
                          : scheme.outline,
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

/// What a change costs, said before the player makes it: free, or which parts get redrafted.
class CostNote extends StatelessWidget {
  const CostNote(this.redraft, {super.key, this.busy = false, this.busyText});

  final Redraft redraft;
  final bool busy;
  final String? busyText;

  @override
  Widget build(BuildContext context) {
    final colors = context.lucid;
    final text = busy && busyText != null ? busyText! : context.l10n.cost(redraft);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        ExcludeSemantics(
          child: Padding(
            padding: const EdgeInsets.only(top: 1),
            child: Icon(
              redraft.isFree ? Icons.check_circle_outline_rounded : Icons.toll_outlined,
              size: 16,
              color: redraft.isFree ? colors.success : colors.textMuted,
            ),
          ),
        ),
        const SizedBox(width: Space.sm),
        Expanded(
          child: Text(text, style: context.lucidText.meta.copyWith(color: colors.textSecondary)),
        ),
      ],
    );
  }
}

/// The server's words about one field of a `validation_error`, such as a real person named in it
/// (G12, docs/API.md): shown under that field as they are. Null when [error] says nothing about
/// [field].
String? fieldMessage(Object? error, String field) {
  if (error case ApiException(code: ApiErrorCode.validationError, :final fields)) {
    for (final entry in fields) {
      if (entry case {
        'field': final String f,
        'message': final String message,
      } when f == field && message.isNotEmpty) {
        return message;
      }
    }
  }
  return null;
}

/// A real person named somewhere in a change (G12): the server's message, which names who.
String? _realPerson(Object error) {
  if (error case ApiException(code: ApiErrorCode.validationError, :final fields)) {
    for (final entry in fields) {
      if (entry case {'type': 'real_person', 'message': final String message}) return message;
    }
  }
  return null;
}

/// A failure in the player's words, in place, with what to do next (T7). Out of credits opens
/// the sheet again, where the player can add their own key and carry on ([onKeyAdded]); a real
/// person named (G12) shows the server's message, which says who.
class InlineError extends StatelessWidget {
  const InlineError(this.error, {super.key, this.onKeyAdded});

  final Object error;

  /// Tries the failed request again once the player added their own key.
  final VoidCallback? onKeyAdded;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final described = describeError(context.l10n, error);
    final copy = switch (_realPerson(error)) {
      final message? => (title: described.title, message: message),
      null => described,
    };
    final outOfCredits = switch (error) {
      ApiException(code: ApiErrorCode.outOfCredits) => true,
      _ => false,
    };
    return Semantics(
      liveRegion: true,
      child: Container(
        padding: const EdgeInsets.all(Space.lg),
        decoration: BoxDecoration(color: scheme.errorContainer, borderRadius: Radii.card),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            ExcludeSemantics(
              child: Icon(ErrorState.iconFor(error), color: scheme.onErrorContainer, size: 22),
            ),
            const SizedBox(width: Space.md),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    copy.title,
                    style: theme.textTheme.titleSmall!.copyWith(color: scheme.onErrorContainer),
                  ),
                  const SizedBox(height: Space.xxs),
                  Text(copy.message, style: theme.textTheme.bodyMedium),
                  if (outOfCredits)
                    Padding(
                      padding: const EdgeInsets.only(top: Space.xs),
                      child: TextButton(
                        style: TextButton.styleFrom(
                          padding: EdgeInsets.zero,
                          foregroundColor: scheme.onErrorContainer,
                        ),
                        onPressed: () async {
                          final retry = onKeyAdded;
                          if (await offerOwnKey(context, error, retrying: retry != null)) {
                            retry?.call();
                          }
                        },
                        child: Text(context.l10n.oocCarryOn),
                      ),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Limits a field to [max] Unicode code points, the way the server counts a string's length, so
/// text with emoji or accents the app accepted is never refused as too long. Flutter's own
/// `maxLength` counts characters as the eye sees them, which can be fewer.
class CodePointLimit extends TextInputFormatter {
  const CodePointLimit(this.max);

  final int max;

  @override
  TextEditingValue formatEditUpdate(TextEditingValue oldValue, TextEditingValue newValue) {
    if (newValue.text.runes.length <= max) return newValue;
    // Keep whole characters: drop from the end until the code points fit.
    final characters = newValue.text.characters.toList();
    var text = '';
    var runes = 0;
    for (final character in characters) {
      final n = character.runes.length;
      if (runes + n > max) break;
      text += character;
      runes += n;
    }
    final offset = newValue.selection.baseOffset.clamp(0, text.length);
    return TextEditingValue(
      text: text,
      selection: TextSelection.collapsed(offset: offset),
    );
  }
}

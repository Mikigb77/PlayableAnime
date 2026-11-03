import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api/api_error.dart';
import '../../core/l10n.dart';
import '../../design/design.dart';
import '../../router.dart';
import 'account_repository.dart';
import 'credits_format.dart';
import 'own_key_editor.dart';

/// How the out-of-credits sheet ended.
enum OutOfCreditsOutcome {
  /// The player saved their own key: try the request again, and it uses no credits (K6).
  keyAdded,

  /// Closed, or left for the credit history.
  dismissed,
}

/// The upsell for `402 out_of_credits` (K2): the balance, top-ups coming soon (K4, K5), and the
/// player's own Gemini key as the way to carry on now (S9, K6). Turns, drafts and pictures call
/// it with the error they got:
///
/// ```dart
/// on ApiException catch (e) {
///   if (e.code == ApiErrorCode.outOfCredits) {
///     final outcome = await showOutOfCreditsSheet(context, e);
///     if (outcome == OutOfCreditsOutcome.keyAdded) retry();
///   }
/// }
/// ```
Future<OutOfCreditsOutcome> showOutOfCreditsSheet(
  BuildContext context, [
  ApiException? error,
]) async {
  final outcome = await showAppSheet<OutOfCreditsOutcome>(
    context: context,
    builder: (_) => OutOfCreditsSheet(error: error),
  );
  return outcome ?? OutOfCreditsOutcome.dismissed;
}

class OutOfCreditsSheet extends ConsumerStatefulWidget {
  const OutOfCreditsSheet({super.key, this.error});

  /// The `out_of_credits` error, for `details.balance_cents` and `details.available_cents`.
  final ApiException? error;

  @override
  ConsumerState<OutOfCreditsSheet> createState() => _OutOfCreditsSheetState();
}

class _OutOfCreditsSheetState extends ConsumerState<OutOfCreditsSheet> {
  var _addingKey = false;

  @override
  void initState() {
    super.initState();
    // The balance shown elsewhere is out of date now.
    Future.microtask(() {
      if (mounted) ref.invalidate(meProvider);
    });
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final theme = Theme.of(context);
    final colors = context.lucid;
    final details = widget.error?.details ?? const {};
    final balance =
        details['balance_cents'] as num? ?? ref.watch(meProvider).value?.balanceCents ?? 0;
    final available = details['available_cents'] as num?;
    final hasKey = ref.watch(ownKeyProvider).value?.isNotEmpty ?? false;
    final body = theme.textTheme.bodyLarge!.copyWith(color: colors.textSecondary);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            Container(
              width: 48,
              height: 48,
              decoration: BoxDecoration(color: colors.accentSoft, shape: BoxShape.circle),
              child: Icon(Icons.toll_outlined, color: colors.onAccentSoft),
            ),
            const SizedBox(width: Space.lg),
            Expanded(
              child: Semantics(
                header: true,
                child: Text(l10n.oocTitle, style: theme.textTheme.headlineSmall),
              ),
            ),
          ],
        ),
        const SizedBox(height: Space.lg),
        Text(l10n.oocBalance(formatCredits(context, balance)), style: body),
        if (available != null && available < balance) ...[
          const SizedBox(height: Space.sm),
          Text(l10n.oocHeld, style: body),
        ],
        const SizedBox(height: Space.md),
        Text(l10n.oocTopUps, style: body),
        const SizedBox(height: Space.xl),
        AnimatedSize(
          duration: Motion.of(context, Motion.base),
          curve: Motion.standard,
          alignment: Alignment.topCenter,
          child: _addingKey
              ? Padding(
                  padding: const EdgeInsets.only(bottom: Space.lg),
                  child: OwnKeyEditor(
                    autofocus: true,
                    onSaved: () {
                      ScaffoldMessenger.maybeOf(
                        context,
                      )?.showSnackBar(SnackBar(content: Text(l10n.oocKeySaved)));
                      Navigator.of(context).pop(OutOfCreditsOutcome.keyAdded);
                    },
                  ),
                )
              : const SizedBox(width: double.infinity),
        ),
        if (!_addingKey && !hasKey)
          FilledButton.icon(
            key: const Key('ooc.useKey'),
            onPressed: () => setState(() => _addingKey = true),
            icon: const Icon(Icons.key_rounded),
            label: Text(l10n.oocUseKey),
          ),
        const SizedBox(height: Space.sm),
        OutlinedButton(
          onPressed: () {
            final router = GoRouter.of(context);
            Navigator.of(context).pop(OutOfCreditsOutcome.dismissed);
            router.push(Routes.credits);
          },
          child: Text(l10n.oocHistory),
        ),
        const SizedBox(height: Space.sm),
        TextButton(
          onPressed: () => Navigator.of(context).pop(OutOfCreditsOutcome.dismissed),
          child: Text(l10n.close),
        ),
      ],
    );
  }
}

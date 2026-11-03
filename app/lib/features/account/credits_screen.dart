import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../core/l10n.dart';
import '../../design/design.dart';
import '../../router.dart';
import 'account_models.dart';
import 'account_repository.dart';
import 'credits_format.dart';

/// The balance and what was spent on what, newest first (K1, K2). Read fresh each time it opens.
class CreditsScreen extends ConsumerWidget {
  const CreditsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = context.l10n;
    final history = ref.watch(creditsHistoryProvider);
    final titles = ref.watch(ledgerStoryTitlesProvider).value ?? const {};
    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.creditsTitle),
        leading: context.canPop()
            ? const BackButton()
            : IconButton(
                tooltip: l10n.close,
                icon: const Icon(Icons.close_rounded),
                onPressed: () => context.go(Routes.account),
              ),
      ),
      body: AsyncValueView(
        value: history,
        onRetry: () => ref.invalidate(creditsHistoryProvider),
        loading: (_) => const SkeletonList(imageHeight: 56),
        builder: (history) => RefreshIndicator(
          onRefresh: () => ref.refresh(creditsHistoryProvider.future),
          child: ListView(
            padding: const EdgeInsets.only(bottom: Space.xxxl),
            children: [
              ContentColumn(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Padding(
                      padding: const EdgeInsets.fromLTRB(Space.gutter, Space.lg, Space.gutter, 0),
                      child: BalanceCard(
                        balanceCents: history.balanceCents,
                        unlimited: history.unlimited,
                      ),
                    ),
                    SectionLabel(l10n.creditsHistory),
                    if (history.entries.isEmpty)
                      Padding(
                        padding: const EdgeInsets.symmetric(vertical: Space.xl),
                        child: EmptyState(
                          icon: Icons.receipt_long_outlined,
                          title: l10n.creditsEmptyTitle,
                          message: l10n.creditsEmptyBody,
                        ),
                      )
                    else ...[
                      for (final entry in history.entries)
                        LedgerTile(entry: entry, storyTitle: titles[entry.storyId]),
                      if (history.entries.length >= 100)
                        Padding(
                          padding: const EdgeInsets.all(Space.gutter),
                          child: Text(
                            l10n.creditsLatest(history.entries.length),
                            style: context.lucidText.meta,
                          ),
                        ),
                    ],
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// The balance in large type, or "Unlimited" for the owner (K7), with how to get more.
class BalanceCard extends StatelessWidget {
  const BalanceCard({
    super.key,
    required this.balanceCents,
    required this.unlimited,
    this.onHistory,
  });

  final num balanceCents;
  final bool unlimited;

  /// Shows a History button when set.
  final VoidCallback? onHistory;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final theme = Theme.of(context);
    final colors = context.lucid;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(Space.xl),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(l10n.accountBalance.toUpperCase(), style: context.lucidText.overline),
                      const SizedBox(height: Space.xs),
                      Text(
                        unlimited ? l10n.accountUnlimited : formatCredits(context, balanceCents),
                        key: const Key('credits.balance'),
                        style: theme.textTheme.displaySmall!.copyWith(color: colors.accent),
                      ),
                    ],
                  ),
                ),
                if (onHistory case final onHistory?)
                  TextButton.icon(
                    onPressed: onHistory,
                    icon: const Icon(Icons.receipt_long_outlined, size: 18),
                    label: Text(l10n.accountCreditHistory),
                  ),
              ],
            ),
            const SizedBox(height: Space.md),
            Text(
              unlimited ? l10n.accountUnlimitedBody : l10n.accountCreditsBody,
              style: theme.textTheme.bodyMedium!.copyWith(color: colors.textSecondary),
            ),
            if (!unlimited) ...[
              const SizedBox(height: Space.sm),
              Text(
                l10n.accountTopUpsSoon,
                style: theme.textTheme.bodyMedium!.copyWith(color: colors.textSecondary),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

/// One ledger entry: what it was for, when, the amount and the balance after it.
class LedgerTile extends StatelessWidget {
  const LedgerTile({super.key, required this.entry, this.storyTitle});

  final LedgerEntry entry;
  final String? storyTitle;

  static IconData iconFor(LedgerKind kind) => switch (kind) {
    LedgerKind.starter => Icons.redeem_outlined,
    LedgerKind.turn => Icons.auto_stories_outlined,
    LedgerKind.draft => Icons.edit_note_rounded,
    LedgerKind.image => Icons.image_outlined,
    LedgerKind.topup => Icons.add_card_outlined,
    LedgerKind.adjustment => Icons.tune_rounded,
  };

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final theme = Theme.of(context);
    final colors = context.lucid;
    final locale = Localizations.localeOf(context).toLanguageTag();
    final kind = switch (entry.kind) {
      LedgerKind.starter => l10n.creditsKindStarter,
      LedgerKind.turn => l10n.creditsKindTurn,
      LedgerKind.draft => l10n.creditsKindDraft,
      LedgerKind.image => l10n.creditsKindImage,
      LedgerKind.topup => l10n.creditsKindTopup,
      LedgerKind.adjustment => l10n.creditsKindAdjustment,
    };
    final where = switch ((storyTitle, entry.turn)) {
      (final String story, final int turn) => l10n.creditsStoryTurn(story, turn),
      (final String story, null) => story,
      (null, final int turn) => l10n.creditsTurn(turn),
      _ => null,
    };
    final when = DateFormat.yMMMd(locale).add_jm().format(entry.createdAt);
    final amount = entry.amountCents;
    return ListTile(
      leading: CircleAvatar(
        radius: 20,
        backgroundColor: theme.colorScheme.surfaceContainerHigh,
        child: Icon(iconFor(entry.kind), size: 20, color: colors.textSecondary),
      ),
      title: Text(kind),
      subtitle: Text(where == null ? when : '$where\n$when'),
      isThreeLine: where != null,
      trailing: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Text(
            amount == 0 ? l10n.creditsFree : formatCredits(context, amount, signed: true),
            style: theme.textTheme.titleMedium!.copyWith(
              color: amount > 0 ? colors.success : colors.textPrimary,
              fontFeatures: const [FontFeature.tabularFigures()],
            ),
          ),
          Text(
            l10n.creditsBalanceAfter(formatCredits(context, entry.balanceAfterCents)),
            style: context.lucidText.meta,
          ),
        ],
      ),
    );
  }
}

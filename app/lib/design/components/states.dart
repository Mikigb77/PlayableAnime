import 'package:flutter/material.dart';

import '../../core/api/api_error.dart';
import '../../core/api/api_error_text.dart';
import '../../core/l10n.dart';
import '../theme.dart';
import '../tokens.dart';

/// A calm, centered message for an empty list or screen, with an optional action.
class EmptyState extends StatelessWidget {
  const EmptyState({
    super.key,
    required this.icon,
    required this.title,
    this.message,
    this.actionLabel,
    this.onAction,
  }) : _error = false;

  /// The error flavour: same layout, the error color for the icon.
  const EmptyState._error({
    required this.icon,
    required this.title,
    this.message,
    this.actionLabel,
    this.onAction,
  }) : _error = true;

  final IconData icon;
  final String title;
  final String? message;
  final String? actionLabel;
  final VoidCallback? onAction;
  final bool _error;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = context.lucid;
    final (background, foreground) = _error
        ? (theme.colorScheme.errorContainer, theme.colorScheme.onErrorContainer)
        : (colors.accentSoft, colors.onAccentSoft);
    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(Space.xxl),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 420),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 64,
                height: 64,
                decoration: BoxDecoration(color: background, shape: BoxShape.circle),
                child: Icon(icon, size: 30, color: foreground),
              ),
              const SizedBox(height: Space.lg),
              Semantics(
                header: true,
                child: Text(
                  title,
                  textAlign: TextAlign.center,
                  style: theme.textTheme.headlineSmall,
                ),
              ),
              if (message case final message?) ...[
                const SizedBox(height: Space.sm),
                Text(
                  message,
                  textAlign: TextAlign.center,
                  style: theme.textTheme.bodyLarge!.copyWith(color: colors.textSecondary),
                ),
              ],
              if (actionLabel != null && onAction != null) ...[
                const SizedBox(height: Space.xl),
                FilledButton(onPressed: onAction, child: Text(actionLabel!)),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

/// A failed load, described in the player's words with a retry (T7). Pass any error: an
/// [ApiException] gets its specific copy, anything else a generic message. Errors a retry can't
/// fix (not found, forbidden) show no retry.
class ErrorState extends StatelessWidget {
  const ErrorState({super.key, required this.error, this.onRetry});

  final Object error;
  final VoidCallback? onRetry;

  static IconData iconFor(Object error) => switch (error) {
    ApiException(code: ApiErrorCode.network) => Icons.cloud_off_rounded,
    ApiException(code: ApiErrorCode.timeout) => Icons.hourglass_disabled_rounded,
    ApiException(code: ApiErrorCode.notFound) => Icons.search_off_rounded,
    ApiException(code: ApiErrorCode.unauthenticated || ApiErrorCode.forbidden) =>
      Icons.lock_outline_rounded,
    ApiException(code: ApiErrorCode.outOfCredits) => Icons.toll_outlined,
    _ => Icons.error_outline_rounded,
  };

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final copy = describeError(l10n, error);
    // Trying again can't bring back what is gone or was never allowed.
    final hopeless = switch (error) {
      ApiException(code: ApiErrorCode.notFound || ApiErrorCode.forbidden) => true,
      _ => false,
    };
    final retry = hopeless ? null : onRetry;
    return EmptyState._error(
      icon: iconFor(error),
      title: copy.title,
      message: copy.message,
      actionLabel: retry == null ? null : l10n.retry,
      onAction: retry,
    );
  }
}

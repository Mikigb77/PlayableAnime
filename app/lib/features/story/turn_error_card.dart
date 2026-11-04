import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_error.dart';
import '../../core/api/api_error_text.dart';
import '../../core/l10n.dart';
import '../../design/design.dart';

/// A turn that failed, in the feed where its scene would be (T7). It says what happened in plain
/// words and offers the way on: try again, say it another way (F4), or fix the key in Account.
/// Nothing was saved, so the story is exactly as it was.
class TurnErrorCard extends StatefulWidget {
  const TurnErrorCard({
    super.key,
    required this.error,
    this.onRetry,
    this.onRephrase,
    this.onAccount,
    this.onDismiss,
  });

  final ApiException error;
  final VoidCallback? onRetry;

  /// Puts the action back in the box to say it another way (`unreadable_action`, F4).
  final VoidCallback? onRephrase;

  /// Opens Account, for a rejected key or the daily quota (S9, T9).
  final VoidCallback? onAccount;
  final VoidCallback? onDismiss;

  @override
  State<TurnErrorCard> createState() => _TurnErrorCardState();
}

class _TurnErrorCardState extends State<TurnErrorCard> {
  Timer? _tick;

  /// Seconds left before a rate-limited turn can be tried again.
  int _left = 0;

  @override
  void initState() {
    super.initState();
    _countdown();
  }

  @override
  void didUpdateWidget(TurnErrorCard old) {
    super.didUpdateWidget(old);
    if (!identical(old.error, widget.error)) _countdown();
  }

  /// A rate limit says how long to wait (T9): the retry stays off until then.
  void _countdown() {
    _tick?.cancel();
    final wait = widget.error.code == ApiErrorCode.rateLimited ? widget.error.retryAfter : null;
    _left = wait == null ? 0 : (wait.inMilliseconds / 1000).ceil();
    if (_left <= 0) return;
    _tick = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (!mounted) return;
      setState(() => _left--);
      if (_left <= 0) timer.cancel();
    });
  }

  @override
  void dispose() {
    _tick?.cancel();
    super.dispose();
  }

  /// An action that crosses one of the content limits (G7, F4). The server says which, in words
  /// the player can act on, and the same words would be refused again.
  bool get _limit =>
      widget.error.code == ApiErrorCode.unreadableAction &&
      widget.error.details['category'] is String &&
      widget.error.message.trim().isNotEmpty;

  /// What a retry can't fix: a story that is gone or not allowed, a refused key, today's quota,
  /// a content limit.
  bool get _retryHelps => switch (widget.error.code) {
    ApiErrorCode.notFound ||
    ApiErrorCode.forbidden ||
    ApiErrorCode.badKey ||
    ApiErrorCode.quotaExceeded => false,
    _ => !_limit,
  };

  bool get _needsAccount =>
      widget.error.code == ApiErrorCode.badKey || widget.error.code == ApiErrorCode.quotaExceeded;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = context.l10n;
    final copy = _limit
        ? (title: l10n.turnLimitTitle, message: widget.error.message.trim())
        : describeError(l10n, widget.error);
    final onError = theme.colorScheme.onErrorContainer;
    final seconds = _left;
    final unreadable = widget.error.code == ApiErrorCode.unreadableAction;

    final actions = <Widget>[
      if (unreadable && widget.onRephrase != null)
        FilledButton.tonal(onPressed: widget.onRephrase, child: Text(l10n.turnRephrase)),
      if (_retryHelps && widget.onRetry != null)
        if (unreadable)
          OutlinedButton(onPressed: widget.onRetry, child: Text(l10n.retry))
        else
          FilledButton.tonal(
            onPressed: seconds > 0 ? null : widget.onRetry,
            child: Text(seconds > 0 ? l10n.turnRetryIn(seconds) : l10n.retry),
          ),
      if (_needsAccount && widget.onAccount != null)
        FilledButton.tonal(onPressed: widget.onAccount, child: Text(l10n.turnOpenAccount)),
      if (widget.onDismiss != null)
        TextButton(
          onPressed: widget.onDismiss,
          style: TextButton.styleFrom(foregroundColor: onError),
          child: Text(l10n.turnDismiss),
        ),
    ];

    return Semantics(
      liveRegion: true,
      container: true,
      child: Container(
        padding: const EdgeInsets.all(Space.lg),
        decoration: BoxDecoration(
          color: theme.colorScheme.errorContainer,
          borderRadius: BorderRadius.circular(Radii.lg),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Padding(
                  padding: const EdgeInsets.only(top: 1),
                  child: Icon(ErrorState.iconFor(widget.error), size: 20, color: onError),
                ),
                const SizedBox(width: Space.md),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        copy.title,
                        style: theme.textTheme.titleMedium!.copyWith(color: onError),
                      ),
                      const SizedBox(height: Space.xs),
                      Text(
                        copy.message,
                        style: theme.textTheme.bodyMedium!.copyWith(color: onError),
                      ),
                    ],
                  ),
                ),
              ],
            ),
            if (actions.isNotEmpty) ...[
              const SizedBox(height: Space.md),
              Wrap(spacing: Space.sm, runSpacing: Space.sm, children: actions),
            ],
          ],
        ),
      ),
    );
  }
}

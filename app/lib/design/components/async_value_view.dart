import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'skeleton.dart';
import 'states.dart';

/// Renders an [AsyncValue]: a skeleton while loading, the friendly error state with a retry, or
/// the data. Data already shown stays on screen during a refresh.
class AsyncValueView<T> extends StatelessWidget {
  const AsyncValueView({
    super.key,
    required this.value,
    required this.builder,
    this.onRetry,
    this.loading,
  });

  final AsyncValue<T> value;
  final Widget Function(T data) builder;
  final VoidCallback? onRetry;

  /// What to show while loading; a list of skeleton cards by default.
  final WidgetBuilder? loading;

  @override
  Widget build(BuildContext context) {
    return value.when(
      skipLoadingOnRefresh: true,
      data: builder,
      loading: () => loading?.call(context) ?? const SkeletonList(),
      error: (error, _) => ErrorState(error: error, onRetry: onRetry),
    );
  }
}

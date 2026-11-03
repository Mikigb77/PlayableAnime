import 'package:flutter/material.dart';

import '../tokens.dart';

/// Opens a bottom sheet in the app's style: a drag handle, a title in the display serif, safe-area
/// aware, scrollable when tall, and no wider than the reading column on large screens.
Future<T?> showAppSheet<T>({
  required BuildContext context,
  required WidgetBuilder builder,
  String? title,
  bool scrollable = true,
}) {
  return showModalBottomSheet<T>(
    context: context,
    useSafeArea: true,
    isScrollControlled: true,
    showDragHandle: true,
    constraints: const BoxConstraints(maxWidth: Layout.readingWidth + 40),
    builder: (context) => AppSheet(title: title, scrollable: scrollable, child: builder(context)),
  );
}

/// The body of a sheet opened with [showAppSheet].
class AppSheet extends StatelessWidget {
  const AppSheet({super.key, required this.child, this.title, this.scrollable = true});

  final String? title;
  final Widget child;
  final bool scrollable;

  @override
  Widget build(BuildContext context) {
    final body = Padding(
      padding: EdgeInsets.fromLTRB(
        Space.gutter,
        0,
        Space.gutter,
        Space.xl + MediaQuery.viewInsetsOf(context).bottom,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (title case final title?)
            Padding(
              padding: const EdgeInsets.only(bottom: Space.lg),
              child: Semantics(
                header: true,
                child: Text(title, style: Theme.of(context).textTheme.headlineSmall),
              ),
            ),
          child,
        ],
      ),
    );
    return scrollable ? SingleChildScrollView(child: body) : body;
  }
}

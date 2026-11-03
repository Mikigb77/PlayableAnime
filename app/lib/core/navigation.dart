import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

/// The app bar's back button for a screen a link can open with nothing under it, such as a
/// shared story URL on the web: it goes to [fallback] instead of leaving no way back.
Widget? backOr(BuildContext context, String fallback) =>
    GoRouter.of(context).canPop() ? null : BackButton(onPressed: () => context.go(fallback));

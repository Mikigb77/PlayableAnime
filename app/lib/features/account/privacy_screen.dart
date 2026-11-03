import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/l10n.dart';
import '../../design/design.dart';
import 'policy_view.dart';

/// The privacy policy shipped with the app (T12), a copy of `docs/PRIVACY.md` that a test keeps
/// in step. One file per language; English when there is none for the player's.
final privacyPolicyProvider = FutureProvider.family<List<PolicyBlock>, String>((
  ref,
  language,
) async {
  String text;
  try {
    text = await rootBundle.loadString('assets/legal/privacy_$language.md');
  } on FlutterError {
    text = await rootBundle.loadString('assets/legal/privacy_en.md');
  }
  return parsePolicy(text);
});

/// Reachable signed out too, from the sign-in screens, and at `/privacy` for the store listings.
class PrivacyScreen extends ConsumerWidget {
  const PrivacyScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = context.l10n;
    final language = Localizations.localeOf(context).languageCode;
    final policy = ref.watch(privacyPolicyProvider(language));
    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.privacyTitle),
        leading: context.canPop()
            ? const BackButton()
            : IconButton(
                tooltip: l10n.close,
                icon: const Icon(Icons.close_rounded),
                // The start: welcome when signed out, Discover when signed in.
                onPressed: () => context.go('/'),
              ),
      ),
      body: AsyncValueView(
        value: policy,
        onRetry: () => ref.invalidate(privacyPolicyProvider(language)),
        loading: (_) => const SkeletonList(count: 2, imageHeight: 0),
        builder: (blocks) => SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(Space.gutter, 0, Space.gutter, Space.xxxl),
          child: ContentColumn.reading(
            child: SelectionArea(child: PolicyView(blocks: blocks)),
          ),
        ),
      ),
    );
  }
}

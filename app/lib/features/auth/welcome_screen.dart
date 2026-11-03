import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/api_error.dart';
import '../../core/api/api_error_text.dart';
import '../../core/api/api_providers.dart';
import '../../core/config.dart';
import '../../core/fake/fake_auth.dart';
import '../../core/l10n.dart';
import '../../core/session/session_controller.dart';
import '../../design/design.dart';

/// The signed-out start. The accounts work (WS13) replaces the buttons with Google and email
/// sign-in and the birth-date step; the session hook it needs is `SessionController.signIn`.
class WelcomeScreen extends ConsumerStatefulWidget {
  const WelcomeScreen({super.key});

  @override
  ConsumerState<WelcomeScreen> createState() => _WelcomeScreenState();
}

class _WelcomeScreenState extends ConsumerState<WelcomeScreen> {
  bool _busy = false;

  Future<void> _demoSignIn() async {
    setState(() => _busy = true);
    try {
      final json = await ref.read(authApiClientProvider).post('/v1/auth/login', {
        'email': FakeAuthState.demoEmail,
        'password': FakeAuthState.demoPassword,
      }, authenticated: false);
      await ref.read(sessionProvider.notifier).signIn(json! as Map<String, dynamic>);
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(describeError(context.l10n, e).message)));
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final theme = Theme.of(context);
    final colors = context.lucid;
    return Scaffold(
      body: DecoratedBox(
        decoration: BoxDecoration(
          gradient: RadialGradient(
            center: const Alignment(0.7, -0.9),
            radius: 1.4,
            colors: [colors.accentSoft, colors.background],
          ),
        ),
        child: SafeArea(
          child: Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(Space.xxl),
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 440),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Icon(Icons.auto_awesome_rounded, color: colors.accent, size: 36),
                    const SizedBox(height: Space.xl),
                    Semantics(
                      header: true,
                      child: Text(l10n.appTitle, style: theme.textTheme.displayLarge),
                    ),
                    const SizedBox(height: Space.md),
                    Text(
                      l10n.welcomeTagline,
                      style: context.lucidText.narration.copyWith(color: colors.textSecondary),
                    ),
                    const SizedBox(height: Space.xxl),
                    for (final (icon, text) in [
                      (Icons.mic_none_rounded, l10n.welcomePointSpeak),
                      (Icons.public_rounded, l10n.welcomePointWorld),
                      (Icons.image_outlined, l10n.welcomePointPictures),
                    ])
                      Padding(
                        padding: const EdgeInsets.only(bottom: Space.lg),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Icon(icon, size: 20, color: colors.accent),
                            const SizedBox(width: Space.md),
                            Expanded(child: Text(text, style: theme.textTheme.bodyLarge)),
                          ],
                        ),
                      ),
                    const SizedBox(height: Space.xl),
                    if (AppConfig.isFake)
                      FilledButton(
                        onPressed: _busy ? null : _demoSignIn,
                        child: Text(l10n.welcomeDemoSignIn),
                      ),
                    const SizedBox(height: Space.md),
                    Text(
                      l10n.welcomeSignInSoon,
                      textAlign: TextAlign.center,
                      style: theme.textTheme.bodySmall,
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

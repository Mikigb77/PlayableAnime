import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/api_error.dart';
import '../../core/api/api_error_text.dart';
import '../../core/config.dart';
import '../../core/fake/fake_auth.dart';
import '../../core/l10n.dart';
import '../../design/design.dart';
import 'auth_repository.dart';
import 'auth_widgets.dart';
import 'birth_date_screen.dart';
import 'email_auth_screen.dart';
import 'google_auth.dart';
import 'google_button.dart';

/// The signed-out start (T8): what the game is, then Google or email. A first Google sign-in
/// goes through the birth-date step (F8). Once signed in, the router opens where the player was
/// going (`/welcome?to=…`) or Discover.
class WelcomeScreen extends ConsumerStatefulWidget {
  const WelcomeScreen({super.key});

  @override
  ConsumerState<WelcomeScreen> createState() => _WelcomeScreenState();
}

class _WelcomeScreenState extends ConsumerState<WelcomeScreen> {
  /// What is signing in, if anything: everything waits for it, and only its own button spins.
  _Busy? _busy;
  String? _error;
  StreamSubscription<String>? _webTokens;

  @override
  void initState() {
    super.initState();
    final google = ref.read(googleAuthProvider);
    if (google.isAvailable && !google.drawsOwnButton) {
      // The web: Google's own button signs in and its tokens arrive here.
      _webTokens = google.idTokens.listen(
        _sendGoogleToken,
        onError: (Object _) {
          if (mounted) setState(() => _error = context.l10n.authGoogleFailed);
        },
      );
    }
  }

  @override
  void dispose() {
    unawaited(_webTokens?.cancel());
    super.dispose();
  }

  Future<void> _google() async {
    setState(() => _error = null);
    final String? token;
    try {
      token = await ref.read(googleAuthProvider).signIn(context);
    } on GoogleSignInFailure {
      if (mounted) setState(() => _error = context.l10n.authGoogleFailed);
      return;
    }
    if (token != null) await _sendGoogleToken(token);
  }

  Future<void> _sendGoogleToken(String token) async {
    if (!mounted || _busy != null) return;
    final l10n = context.l10n;
    setState(() {
      _busy = _Busy.google;
      _error = null;
    });
    try {
      await ref.read(authRepositoryProvider).signInWithGoogle(token);
    } on ApiException catch (e) {
      if (!mounted) return;
      if (e.code == ApiErrorCode.birthDateRequired) {
        unawaited(
          Navigator.of(
            context,
          ).push(MaterialPageRoute<void>(builder: (_) => BirthDateScreen(idToken: token))),
        );
      } else {
        setState(
          () => _error = switch (e.code) {
            ApiErrorCode.unauthenticated => l10n.authGoogleFailed,
            ApiErrorCode.forbidden => l10n.authGoogleUnverified,
            _ => describeError(l10n, e).message,
          },
        );
      }
    } finally {
      if (mounted) setState(() => _busy = null);
    }
  }

  Future<void> _demoSignIn() async {
    setState(() {
      _busy = _Busy.demo;
      _error = null;
    });
    try {
      await ref
          .read(authRepositoryProvider)
          .logIn(email: FakeAuthState.demoEmail, password: FakeAuthState.demoPassword);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = describeError(context.l10n, e).message);
    } finally {
      if (mounted) setState(() => _busy = null);
    }
  }

  void _email(EmailAuthMode mode) => Navigator.of(
    context,
  ).push(MaterialPageRoute<void>(builder: (_) => EmailAuthScreen(initialMode: mode)));

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final theme = Theme.of(context);
    final colors = context.lucid;
    final google = ref.watch(googleAuthProvider);
    final busy = _busy != null;
    return AuthScaffold(
      showBack: false,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          ExcludeSemantics(
            child: Align(
              alignment: AlignmentDirectional.centerStart,
              child: Container(
                width: 56,
                height: 56,
                decoration: BoxDecoration(color: colors.accentSoft, shape: BoxShape.circle),
                child: Icon(Icons.auto_awesome_rounded, color: colors.accent, size: 28),
              ),
            ),
          ),
          const SizedBox(height: Space.xl),
          Semantics(header: true, child: Text(l10n.appTitle, style: theme.textTheme.displayLarge)),
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
          const SizedBox(height: Space.xxl),
          if (_error case final message?) ...[
            FormMessage(message),
            const SizedBox(height: Space.lg),
          ],
          if (google.isAvailable) ...[
            if (google.drawsOwnButton)
              GoogleButton(busy: _busy == _Busy.google, onPressed: busy ? null : _google)
            else
              Center(
                child: LayoutBuilder(
                  builder: (context, constraints) =>
                      google.buildWebButton(context, constraints.maxWidth),
                ),
              ),
            const SizedBox(height: Space.md),
          ],
          OutlinedButton.icon(
            onPressed: busy ? null : () => _email(EmailAuthMode.register),
            icon: const Icon(Icons.mail_outline_rounded),
            label: Text(l10n.authSignUpWithEmail),
          ),
          const SizedBox(height: Space.sm),
          TextButton(
            onPressed: busy ? null : () => _email(EmailAuthMode.signIn),
            child: Text(l10n.authHaveAccount),
          ),
          if (AppConfig.isFake)
            TextButton(onPressed: busy ? null : _demoSignIn, child: Text(l10n.welcomeDemoSignIn)),
          const SizedBox(height: Space.lg),
          const AgreementText(),
        ],
      ),
    );
  }
}

enum _Busy { google, demo }

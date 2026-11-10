import 'dart:async';
import 'dart:math' as math;

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

/// The signed-out start (T8): the forest gate from the app's icon and the website, fading into
/// the page among its fireflies, the headline, then Google or email. A first Google sign-in
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
    final headline = theme.textTheme.displayLarge!.copyWith(height: 1.05, letterSpacing: -0.9);
    return Scaffold(
      body: LayoutBuilder(
        builder: (context, page) {
          final inset = MediaQuery.paddingOf(context);
          // The painting is square: the mock's size on a phone, smaller on a short screen.
          final art = math.min(_artSize, math.max(page.maxHeight * 0.62, 320.0));
          // The app's name sits on the painting; the headline starts where it has dimmed.
          final top = inset.top + 14;
          final gap = math.max(Space.xl, art * 0.55 - top - _brandSize);
          final side = math.max(26.0, (page.maxWidth - _contentWidth) / 2);
          final air = math.min(page.maxWidth, _artSize);
          return SingleChildScrollView(
            child: ConstrainedBox(
              constraints: BoxConstraints(minHeight: page.maxHeight),
              child: Stack(
                fit: StackFit.passthrough,
                children: [
                  Positioned(
                    top: -18,
                    left: (page.maxWidth - art) / 2,
                    width: art,
                    height: art,
                    child: _Gate(
                      key: const Key('welcome.gate'),
                      size: art,
                      fadeSides: page.maxWidth > art,
                    ),
                  ),
                  // The page's color over the very top, so the status bar and the app's name
                  // read on the painting.
                  Positioned(
                    top: 0,
                    left: 0,
                    right: 0,
                    height: inset.top + 130,
                    child: IgnorePointer(
                      child: DecoratedBox(
                        decoration: BoxDecoration(
                          gradient: LinearGradient(
                            begin: Alignment.topCenter,
                            end: Alignment.bottomCenter,
                            colors: [
                              colors.background.withValues(alpha: 0.82),
                              colors.background.withValues(alpha: 0),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ),
                  Positioned(
                    top: 0,
                    bottom: 0,
                    left: (page.maxWidth - air) / 2,
                    width: air,
                    child: const Ambient(
                      glow: null,
                      motes: Ambient.forest,
                      belowSystemInset: false,
                    ),
                  ),
                  Padding(
                    padding: EdgeInsets.fromLTRB(side, top, side, inset.bottom + Space.xl),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        const Align(
                          alignment: AlignmentDirectional.centerStart,
                          child: BrandMark(size: _brandSize),
                        ),
                        Padding(
                          padding: EdgeInsets.only(top: gap),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              RiseIn(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.stretch,
                                  children: [
                                    // One heading for a screen reader, in both its colors.
                                    Semantics(
                                      header: true,
                                      label:
                                          '${l10n.welcomeHeadline} ${l10n.welcomeHeadlineAccent}',
                                      excludeSemantics: true,
                                      child: HeadlineScaling(
                                        child: Column(
                                          crossAxisAlignment: CrossAxisAlignment.start,
                                          children: [
                                            Text(l10n.welcomeHeadline, style: headline),
                                            GradientText(
                                              l10n.welcomeHeadlineAccent,
                                              style: headline,
                                              balanced: true,
                                            ),
                                          ],
                                        ),
                                      ),
                                    ),
                                    const SizedBox(height: Space.md),
                                    Text(
                                      l10n.welcomeTagline,
                                      style: context.lucidText.narration.copyWith(
                                        fontStyle: FontStyle.italic,
                                        fontSize: 18.5,
                                        height: 1.42,
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                              const SizedBox(height: Space.xl),
                              RiseIn(
                                order: 2,
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.stretch,
                                  children: [
                                    if (_error case final message?) ...[
                                      FormMessage(message),
                                      const SizedBox(height: Space.lg),
                                    ],
                                    if (google.isAvailable) ...[
                                      if (google.drawsOwnButton)
                                        GoogleButton(
                                          busy: _busy == _Busy.google,
                                          onPressed: busy ? null : _google,
                                        )
                                      else
                                        Center(
                                          child: LayoutBuilder(
                                            builder: (context, constraints) => google
                                                .buildWebButton(context, constraints.maxWidth),
                                          ),
                                        ),
                                      const SizedBox(height: Space.md),
                                    ],
                                    OutlinedButton.icon(
                                      onPressed: busy ? null : () => _email(EmailAuthMode.register),
                                      icon: const Icon(Icons.mail_outline_rounded, size: 19),
                                      label: Text(l10n.authSignUpWithEmail),
                                    ),
                                    const SizedBox(height: Space.xs),
                                    TextButton(
                                      onPressed: busy ? null : () => _email(EmailAuthMode.signIn),
                                      child: Text(l10n.authHaveAccount),
                                    ),
                                    if (AppConfig.isFake)
                                      TextButton(
                                        onPressed: busy ? null : _demoSignIn,
                                        child: Text(l10n.welcomeDemoSignIn),
                                      ),
                                    const SizedBox(height: Space.sm),
                                    const AgreementText(),
                                  ],
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  /// The painting's width and height on a phone, and the column of words under it.
  static const _artSize = 520.0;
  static const _contentWidth = 440.0;
  static const _brandSize = 34.0;
}

/// The forest gate, from the app's icon: square, with warm light at its heart, fading out
/// towards its foot so the page's words can stand on it. On a page wider than the painting, its
/// sides fade out too.
class _Gate extends StatelessWidget {
  const _Gate({super.key, required this.size, required this.fadeSides});

  final double size;
  final bool fadeSides;

  static const asset = 'assets/brand/gate.jpg';

  static const _solid = Color(0xFF000000);
  static const _clear = Color(0x00000000);

  @override
  Widget build(BuildContext context) {
    final dpr = MediaQuery.devicePixelRatioOf(context);
    Widget art = Stack(
      fit: StackFit.expand,
      children: [
        Image.asset(
          asset,
          fit: BoxFit.cover,
          cacheWidth: math.min(1200, (size * dpr).round()),
          // A build without the painting keeps the page and its fireflies.
          errorBuilder: (_, _, _) => const SizedBox.expand(),
        ),
        // The light in the gate, a little brighter than it was painted.
        const DecoratedBox(
          decoration: BoxDecoration(
            backgroundBlendMode: BlendMode.screen,
            gradient: RadialGradient(
              colors: [Color(0x57FFD68C), Color(0x1FFFC46E), Color(0x00FFC46E)],
              stops: [0, 0.36, 0.72],
            ),
          ),
        ),
      ],
    );
    art = ShaderMask(
      blendMode: BlendMode.dstIn,
      shaderCallback: (bounds) => const LinearGradient(
        begin: Alignment.topCenter,
        end: Alignment.bottomCenter,
        colors: [_solid, _solid, _clear],
        stops: [0, 0.56, 0.88],
      ).createShader(bounds),
      child: art,
    );
    if (fadeSides) {
      art = ShaderMask(
        blendMode: BlendMode.dstIn,
        shaderCallback: (bounds) => const LinearGradient(
          colors: [_clear, _solid, _solid, _clear],
          stops: [0, 0.2, 0.8, 1],
        ).createShader(bounds),
        child: art,
      );
    }
    return ExcludeSemantics(child: IgnorePointer(child: art));
  }
}

enum _Busy { google, demo }

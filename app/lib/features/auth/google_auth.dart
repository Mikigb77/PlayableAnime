import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:google_sign_in/google_sign_in.dart';

import '../../core/config.dart';
import '../../core/fake/fake_auth.dart';
import '../../core/l10n.dart';
import '../../design/design.dart';
import 'google_web_button_stub.dart'
    if (dart.library.js_interop) 'google_web_button_web.dart'
    as web_button;

/// The OAuth clients in the `playable-anime` GCP project, set at build time (T8):
///
/// ```bash
/// flutter run --dart-define=GOOGLE_WEB_CLIENT_ID=… --dart-define=GOOGLE_IOS_CLIENT_ID=…
/// ```
///
/// The web client signs in on the web and is the ID token's audience on Android; iOS has its own
/// client. Every one of them must be in the backend's `GOOGLE_OAUTH_CLIENT_IDS`. Without the
/// client for a platform, the app offers email sign-in only.
abstract final class GoogleClientIds {
  static const web = String.fromEnvironment('GOOGLE_WEB_CLIENT_ID');
  static const ios = String.fromEnvironment('GOOGLE_IOS_CLIENT_ID');
}

/// Google sign-in failed for a reason other than the player backing out.
class GoogleSignInFailure implements Exception {
  const GoogleSignInFailure(this.reason);

  final String reason;

  @override
  String toString() => 'GoogleSignInFailure($reason)';
}

/// Gets a Google ID token for `POST /v1/auth/google`. The backend checks it once and from then
/// on only our own tokens are used (T8).
abstract interface class GoogleAuth {
  /// Whether this build can offer Google sign-in here.
  bool get isAvailable;

  /// Whether the app draws its own button and calls [signIn]. On the web Google's own button
  /// signs in instead ([buildWebButton]), and its tokens arrive on [idTokens].
  bool get drawsOwnButton;

  /// Asks Google for an ID token. Null when the player backs out; [GoogleSignInFailure] when it
  /// fails.
  Future<String?> signIn(BuildContext context);

  /// ID tokens from Google's own button, on the web.
  Stream<String> get idTokens;

  /// Google's own button, on the web.
  Widget buildWebButton(BuildContext context, double width);

  /// Forgets the Google account on this device, so the next sign-in asks which one. Never throws.
  Future<void> signOut();
}

/// The real thing, through `google_sign_in`.
class PluginGoogleAuth implements GoogleAuth {
  PluginGoogleAuth._({
    required this.isAvailable,
    required this.drawsOwnButton,
    this.clientId,
    this.serverClientId,
  });

  /// Set up for the platform the app runs on, from [GoogleClientIds].
  factory PluginGoogleAuth.forThisPlatform() {
    String? orNull(String id) => id.isEmpty ? null : id;
    if (kIsWeb) {
      return PluginGoogleAuth._(
        isAvailable: GoogleClientIds.web.isNotEmpty,
        drawsOwnButton: false,
        clientId: orNull(GoogleClientIds.web),
      );
    }
    return switch (defaultTargetPlatform) {
      // Android signs in through Credential Manager, which needs the web client as the server
      // client to issue an ID token.
      TargetPlatform.android => PluginGoogleAuth._(
        isAvailable: GoogleClientIds.web.isNotEmpty,
        drawsOwnButton: true,
        serverClientId: orNull(GoogleClientIds.web),
      ),
      // iOS also needs the client's reversed id as a URL scheme in Info.plist (see app/README.md).
      TargetPlatform.iOS => PluginGoogleAuth._(
        isAvailable: GoogleClientIds.ios.isNotEmpty,
        drawsOwnButton: true,
        clientId: orNull(GoogleClientIds.ios),
        serverClientId: orNull(GoogleClientIds.web),
      ),
      _ => PluginGoogleAuth._(isAvailable: false, drawsOwnButton: true),
    };
  }

  @override
  final bool isAvailable;
  @override
  final bool drawsOwnButton;
  final String? clientId;
  final String? serverClientId;

  Future<void>? _initialized;

  Future<void> _init() => _initialized ??= GoogleSignIn.instance.initialize(
    clientId: clientId,
    serverClientId: serverClientId,
  );

  @override
  Future<String?> signIn(BuildContext context) async {
    try {
      await _init();
      final account = await GoogleSignIn.instance.authenticate();
      final token = account.authentication.idToken;
      if (token == null || token.isEmpty) throw const GoogleSignInFailure('no_id_token');
      return token;
    } on GoogleSignInException catch (e) {
      if (_backedOut(e)) return null;
      throw GoogleSignInFailure(e.code.name);
    }
  }

  @override
  Stream<String> get idTokens async* {
    await _init();
    yield* GoogleSignIn.instance.authenticationEvents.transform(
      StreamTransformer<GoogleSignInAuthenticationEvent, String>.fromHandlers(
        handleData: (event, sink) {
          if (event case GoogleSignInAuthenticationEventSignIn(:final user)) {
            final token = user.authentication.idToken;
            if (token != null && token.isNotEmpty) sink.add(token);
          }
        },
        handleError: (error, stack, sink) {
          if (error is GoogleSignInException && _backedOut(error)) return;
          sink.addError(GoogleSignInFailure('$error'), stack);
        },
      ),
    );
  }

  static bool _backedOut(GoogleSignInException e) =>
      e.code == GoogleSignInExceptionCode.canceled ||
      e.code == GoogleSignInExceptionCode.interrupted;

  @override
  Widget buildWebButton(BuildContext context, double width) => FutureBuilder<void>(
    future: _init(),
    builder: (context, snapshot) => snapshot.connectionState == ConnectionState.done
        ? web_button.googleWebButton(
            dark: Theme.of(context).brightness == Brightness.dark,
            width: width,
          )
        : const SizedBox(height: 44),
  );

  @override
  Future<void> signOut() async {
    if (!isAvailable) return;
    try {
      await _init();
      await GoogleSignIn.instance.signOut();
    } on Object catch (e) {
      debugPrint('Google sign-out failed: ${e.runtimeType}');
    }
  }
}

/// `API_MODE=fake`: a stand-in for Google's account picker that sends the fake backend's tokens
/// ([FakeGoogleTokens]), so every sign-in path works offline.
class FakeGoogleAuth implements GoogleAuth {
  const FakeGoogleAuth();

  @override
  bool get isAvailable => true;

  @override
  bool get drawsOwnButton => true;

  @override
  Future<String?> signIn(BuildContext context) => showAppSheet<String>(
    context: context,
    title: context.l10n.fakeGoogleTitle,
    builder: (context) => const _FakeGooglePicker(),
  );

  @override
  Stream<String> get idTokens => const Stream.empty();

  @override
  Widget buildWebButton(BuildContext context, double width) => const SizedBox.shrink();

  @override
  Future<void> signOut() async {}
}

class _FakeGooglePicker extends StatelessWidget {
  const _FakeGooglePicker();

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final accounts = [
      (FakeGoogleTokens.demo, l10n.fakeGoogleDemo, FakeAuthState.demoEmail),
      (FakeGoogleTokens.newPlayer, l10n.fakeGoogleNew, 'new.player@gmail.test'),
      (FakeGoogleTokens.owner, l10n.fakeGoogleOwner, 'owner@lucid.test'),
    ];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          l10n.fakeGoogleBody,
          style: Theme.of(
            context,
          ).textTheme.bodyMedium!.copyWith(color: context.lucid.textSecondary),
        ),
        const SizedBox(height: Space.md),
        for (final (token, name, email) in accounts)
          ListTile(
            contentPadding: EdgeInsets.zero,
            leading: PortraitAvatar(name: name, size: 40),
            title: Text(name),
            subtitle: Text(email),
            onTap: () => Navigator.of(context).pop(token),
          ),
      ],
    );
  }
}

final googleAuthProvider = Provider<GoogleAuth>(
  (ref) => AppConfig.isFake ? const FakeGoogleAuth() : PluginGoogleAuth.forThisPlatform(),
);

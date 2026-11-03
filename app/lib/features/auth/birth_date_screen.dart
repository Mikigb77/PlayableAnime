import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/api_error.dart';
import '../../core/api/api_error_text.dart';
import '../../core/l10n.dart';
import '../../design/design.dart';
import 'auth_repository.dart';
import 'auth_widgets.dart';

/// The birth-date step of a first Google sign-in (F8): the server answered
/// `birth_date_required`, so ask once and send the same ID token again with the date.
class BirthDateScreen extends ConsumerStatefulWidget {
  const BirthDateScreen({super.key, required this.idToken});

  /// Google's ID token. It lasts an hour, which is plenty for this step.
  final String idToken;

  @override
  ConsumerState<BirthDateScreen> createState() => _BirthDateScreenState();
}

class _BirthDateScreenState extends ConsumerState<BirthDateScreen> {
  DateTime? _birthDate;
  var _busy = false;
  String? _fieldError;
  String? _formError;

  Future<void> _submit() async {
    final l10n = context.l10n;
    final date = _birthDate;
    if (date == null) {
      setState(() => _fieldError = l10n.authNeedBirthDate);
      return;
    }
    setState(() {
      _busy = true;
      _fieldError = null;
      _formError = null;
    });
    try {
      await ref.read(authRepositoryProvider).signInWithGoogle(widget.idToken, birthDate: date);
      // Signed in: the router replaces the signed-out screens.
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        switch (e.code) {
          case ApiErrorCode.validationError:
            _fieldError = fieldErrors(l10n, e)['birth_date'];
            if (_fieldError == null) _formError = describeError(l10n, e).message;
          case ApiErrorCode.unauthenticated:
            _formError = l10n.authGoogleExpired;
          case ApiErrorCode.forbidden:
            _formError = l10n.authGoogleUnverified;
          default:
            _formError = describeError(l10n, e).message;
        }
      });
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return AuthScaffold(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          AuthHeading(title: l10n.authBirthDateTitle, subtitle: l10n.authBirthDateBody),
          if (_formError case final message?) ...[
            FormMessage(message),
            const SizedBox(height: Space.lg),
          ],
          BirthDateField(
            key: const Key('auth.birthDate'),
            value: _birthDate,
            enabled: !_busy,
            errorText: _fieldError,
            onChanged: (date) => setState(() {
              _birthDate = date;
              _fieldError = null;
              _formError = null;
            }),
          ),
          const SizedBox(height: Space.xl),
          FilledButton(
            key: const Key('auth.submit'),
            onPressed: _busy ? null : _submit,
            child: _busy
                ? SizedBox.square(
                    dimension: 20,
                    child: CircularProgressIndicator(strokeWidth: 2, color: context.lucid.onAccent),
                  )
                : Text(l10n.authContinue),
          ),
          const SizedBox(height: Space.lg),
          const AgreementText(),
        ],
      ),
    );
  }
}

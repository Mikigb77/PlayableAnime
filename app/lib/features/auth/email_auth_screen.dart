import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/api_error.dart';
import '../../core/api/api_error_text.dart';
import '../../core/l10n.dart';
import '../../design/design.dart';
import 'auth_repository.dart';
import 'auth_widgets.dart';

enum EmailAuthMode { signIn, register }

/// Email and password: sign in, or create an account with a name and a birth date (T8, F8).
/// Opened over the welcome screen; once signed in, the router takes the player where they were
/// going.
class EmailAuthScreen extends ConsumerStatefulWidget {
  const EmailAuthScreen({super.key, this.initialMode = EmailAuthMode.register});

  final EmailAuthMode initialMode;

  @override
  ConsumerState<EmailAuthScreen> createState() => _EmailAuthScreenState();
}

class _EmailAuthScreenState extends ConsumerState<EmailAuthScreen> {
  late var _mode = widget.initialMode;
  final _name = TextEditingController();
  final _email = TextEditingController();
  final _password = TextEditingController();
  DateTime? _birthDate;
  var _obscure = true;
  var _busy = false;

  /// Shown once the player has tried to submit, so an empty form isn't red from the start.
  var _submitted = false;

  /// What the server said, by field, until that field changes.
  var _serverErrors = <String, String>{};
  String? _formError;

  bool get _registering => _mode == EmailAuthMode.register;

  @override
  void dispose() {
    _name.dispose();
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  void _switchMode() => setState(() {
    _mode = _registering ? EmailAuthMode.signIn : EmailAuthMode.register;
    _submitted = false;
    _serverErrors = {};
    _formError = null;
  });

  void _edited(String field) {
    if (_serverErrors.containsKey(field) || _formError != null) {
      setState(() {
        _serverErrors = {..._serverErrors}..remove(field);
        _formError = null;
      });
    }
  }

  /// The client's own checks; the server checks everything again.
  Map<String, String> _localErrors(AppLocalizations l10n) {
    final email = _email.text.trim();
    return {
      if (_registering && _name.text.trim().isEmpty) 'display_name': l10n.authNeedName,
      if (email.isEmpty)
        'email': l10n.authNeedEmail
      else if (!RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$').hasMatch(email))
        'email': l10n.authBadEmail,
      if (_password.text.isEmpty)
        'password': l10n.authNeedPassword
      else if (_registering && _password.text.length < 8)
        'password': l10n.authPasswordShort,
      if (_registering && _birthDate == null) 'birth_date': l10n.authNeedBirthDate,
    };
  }

  String? _errorFor(AppLocalizations l10n, String field) =>
      _serverErrors[field] ?? (_submitted ? _localErrors(l10n)[field] : null);

  Future<void> _submit() async {
    final l10n = context.l10n;
    FocusScope.of(context).unfocus();
    setState(() {
      _submitted = true;
      _serverErrors = {};
      _formError = null;
    });
    if (_localErrors(l10n).isNotEmpty) return;
    setState(() => _busy = true);
    final auth = ref.read(authRepositoryProvider);
    try {
      if (_registering) {
        await auth.register(
          email: _email.text,
          password: _password.text,
          displayName: _name.text,
          birthDate: _birthDate!,
        );
      } else {
        await auth.logIn(email: _email.text, password: _password.text);
      }
      // Signed in: the router replaces the signed-out screens.
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        switch (e.code) {
          case ApiErrorCode.validationError:
            final fields = fieldErrors(l10n, e);
            const shown = {'display_name', 'email', 'password', 'birth_date'};
            _serverErrors = {
              for (final entry in fields.entries)
                if (shown.contains(entry.key)) entry.key: entry.value,
            };
            if (_serverErrors.isEmpty) _formError = describeError(l10n, e).message;
          case ApiErrorCode.unauthenticated:
            _formError = l10n.authWrongPassword;
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
    final colors = context.lucid;
    const gap = SizedBox(height: Space.lg);
    return AuthScaffold(
      child: AutofillGroup(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            AnimatedSwitcher(
              duration: Motion.of(context, Motion.base),
              child: AuthHeading(
                key: ValueKey(_mode),
                title: _registering ? l10n.authRegisterTitle : l10n.authSignInTitle,
                subtitle: _registering ? l10n.authRegisterSubtitle : l10n.authSignInSubtitle,
              ),
            ),
            if (_formError case final message?) ...[FormMessage(message), gap],
            AnimatedSize(
              duration: Motion.of(context, Motion.base),
              curve: Motion.standard,
              alignment: Alignment.topCenter,
              child: _registering
                  ? Padding(
                      padding: const EdgeInsets.only(bottom: Space.lg),
                      child: TextField(
                        key: const Key('auth.name'),
                        controller: _name,
                        enabled: !_busy,
                        textCapitalization: TextCapitalization.words,
                        textInputAction: TextInputAction.next,
                        autofillHints: const [AutofillHints.name],
                        onChanged: (_) => _edited('display_name'),
                        decoration: InputDecoration(
                          labelText: l10n.authNameLabel,
                          errorText: _errorFor(l10n, 'display_name'),
                        ),
                      ),
                    )
                  : const SizedBox(width: double.infinity),
            ),
            TextField(
              key: const Key('auth.email'),
              controller: _email,
              enabled: !_busy,
              keyboardType: TextInputType.emailAddress,
              autocorrect: false,
              enableSuggestions: false,
              textInputAction: TextInputAction.next,
              autofillHints: const [AutofillHints.email],
              onChanged: (_) => _edited('email'),
              decoration: InputDecoration(
                labelText: l10n.authEmailLabel,
                errorText: _errorFor(l10n, 'email'),
                errorMaxLines: 3,
              ),
            ),
            gap,
            TextField(
              key: const Key('auth.password'),
              controller: _password,
              enabled: !_busy,
              obscureText: _obscure,
              autocorrect: false,
              enableSuggestions: false,
              textInputAction: _registering ? TextInputAction.next : TextInputAction.done,
              autofillHints: [_registering ? AutofillHints.newPassword : AutofillHints.password],
              onChanged: (_) => _edited('password'),
              onSubmitted: _registering ? null : (_) => _submit(),
              decoration: InputDecoration(
                labelText: l10n.authPasswordLabel,
                helperText: _registering ? l10n.authPasswordHelper : null,
                errorText: _errorFor(l10n, 'password'),
                errorMaxLines: 3,
                suffixIcon: IconButton(
                  tooltip: _obscure ? l10n.authShowPassword : l10n.authHidePassword,
                  icon: Icon(_obscure ? Icons.visibility_outlined : Icons.visibility_off_outlined),
                  onPressed: () => setState(() => _obscure = !_obscure),
                ),
              ),
            ),
            AnimatedSize(
              duration: Motion.of(context, Motion.base),
              curve: Motion.standard,
              alignment: Alignment.topCenter,
              child: _registering
                  ? Padding(
                      padding: const EdgeInsets.only(top: Space.lg),
                      child: BirthDateField(
                        key: const Key('auth.birthDate'),
                        value: _birthDate,
                        enabled: !_busy,
                        errorText: _errorFor(l10n, 'birth_date'),
                        onChanged: (date) {
                          setState(() => _birthDate = date);
                          _edited('birth_date');
                        },
                      ),
                    )
                  : const SizedBox(width: double.infinity),
            ),
            const SizedBox(height: Space.xl),
            FilledButton(
              key: const Key('auth.submit'),
              onPressed: _busy ? null : _submit,
              child: _busy
                  ? SizedBox.square(
                      dimension: 20,
                      child: CircularProgressIndicator(strokeWidth: 2, color: colors.onAccent),
                    )
                  : Text(_registering ? l10n.authCreateAccount : l10n.authSignIn),
            ),
            const SizedBox(height: Space.sm),
            TextButton(
              onPressed: _busy ? null : _switchMode,
              child: Text(_registering ? l10n.authToSignIn : l10n.authToRegister),
            ),
            if (_registering) ...[const SizedBox(height: Space.md), const AgreementText()],
          ],
        ),
      ),
    );
  }
}

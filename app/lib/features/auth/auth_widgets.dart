import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../core/l10n.dart';
import '../../design/design.dart';
import '../../router.dart';

/// The frame of the signed-out forms: the night air behind the page ([Ambient]), an optional
/// back button, and a centered column no wider than a phone.
class AuthScaffold extends StatelessWidget {
  const AuthScaffold({super.key, required this.child, this.showBack = true});

  final Widget child;
  final bool showBack;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      extendBodyBehindAppBar: true,
      appBar: showBack
          ? AppBar(backgroundColor: Colors.transparent, leading: const BackButton())
          : null,
      body: Stack(
        children: [
          const Positioned.fill(child: Ambient()),
          SafeArea(
            child: LayoutBuilder(
              builder: (context, constraints) => SingleChildScrollView(
                padding: EdgeInsets.fromLTRB(
                  Space.xl,
                  showBack ? kToolbarHeight : Space.xxl,
                  Space.xl,
                  Space.xl,
                ),
                child: ConstrainedBox(
                  constraints: BoxConstraints(
                    minHeight:
                        (constraints.maxHeight - (showBack ? kToolbarHeight : Space.xxl) - Space.xl)
                            .clamp(0, double.infinity),
                  ),
                  child: Center(
                    child: ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 440),
                      child: child,
                    ),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// The serif title and the line under it, at the top of a sign-in form.
class AuthHeading extends StatelessWidget {
  const AuthHeading({super.key, required this.title, required this.subtitle});

  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Semantics(header: true, child: Text(title, style: theme.textTheme.displaySmall)),
        const SizedBox(height: Space.sm),
        Text(
          subtitle,
          style: theme.textTheme.bodyLarge!.copyWith(color: context.lucid.textSecondary),
        ),
        const SizedBox(height: Space.xl),
      ],
    );
  }
}

/// A problem with the whole form, such as a wrong password, in a quiet error panel that screen
/// readers announce.
class FormMessage extends StatelessWidget {
  const FormMessage(this.message, {super.key});

  final String message;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Semantics(
      liveRegion: true,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: Space.lg, vertical: Space.md),
        decoration: BoxDecoration(
          color: scheme.errorContainer,
          borderRadius: BorderRadius.circular(Radii.md),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(Icons.error_outline_rounded, size: 20, color: scheme.onErrorContainer),
            const SizedBox(width: Space.md),
            Expanded(
              child: Text(
                message,
                style: Theme.of(
                  context,
                ).textTheme.bodyMedium!.copyWith(color: scheme.onErrorContainer),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// "By continuing, you accept the privacy policy", with the policy as a link.
class AgreementText extends StatefulWidget {
  const AgreementText({super.key});

  @override
  State<AgreementText> createState() => _AgreementTextState();
}

class _AgreementTextState extends State<AgreementText> {
  late final _tap = TapGestureRecognizer()..onTap = () => context.push(Routes.privacy);

  @override
  void dispose() {
    _tap.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final style = Theme.of(context).textTheme.bodySmall!;
    // The sentence is translated whole, with a marker where the link goes, so the link can sit
    // anywhere in it.
    const marker = '\u0000';
    final parts = l10n.authAgreement(marker).split(marker);
    return Text.rich(
      TextSpan(
        children: [
          TextSpan(text: parts.first),
          TextSpan(
            text: l10n.authPolicyLink,
            recognizer: _tap,
            style: TextStyle(
              color: context.lucid.accent,
              decoration: TextDecoration.underline,
              decorationColor: context.lucid.accent,
            ),
          ),
          if (parts.length > 1) TextSpan(text: parts.sublist(1).join()),
        ],
      ),
      textAlign: TextAlign.center,
      style: style,
    );
  }
}

/// A birth date (F8): a field that opens the date picker in typing mode, with no date filled in,
/// so the form never suggests an age.
class BirthDateField extends StatelessWidget {
  const BirthDateField({
    super.key,
    required this.value,
    required this.onChanged,
    this.errorText,
    this.enabled = true,
  });

  final DateTime? value;
  final ValueChanged<DateTime> onChanged;
  final String? errorText;
  final bool enabled;

  Future<void> _pick(BuildContext context) async {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final l10n = context.l10n;
    final picked = await showDatePicker(
      context: context,
      initialDate: value,
      firstDate: DateTime(today.year - 120),
      lastDate: today,
      initialEntryMode: DatePickerEntryMode.input,
      initialDatePickerMode: DatePickerMode.year,
      helpText: l10n.authBirthDateLabel,
      fieldLabelText: l10n.authBirthDateLabel,
    );
    if (picked != null) onChanged(picked);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final theme = Theme.of(context);
    final date = value;
    final text = date == null
        ? null
        : DateFormat.yMMMMd(Localizations.localeOf(context).toLanguageTag()).format(date);
    return Semantics(
      button: true,
      label: l10n.authBirthDateLabel,
      value: text,
      hint: errorText ?? l10n.authBirthDateHelper,
      enabled: enabled,
      // The field's own semantics are left out, so the tap is given here.
      onTap: enabled ? () => _pick(context) : null,
      excludeSemantics: true,
      child: InkWell(
        onTap: enabled ? () => _pick(context) : null,
        borderRadius: Radii.field,
        child: InputDecorator(
          isEmpty: date == null,
          isFocused: false,
          decoration: InputDecoration(
            labelText: l10n.authBirthDateLabel,
            hintText: l10n.authBirthDateHint,
            helperText: l10n.authBirthDateHelper,
            helperMaxLines: 3,
            errorText: errorText,
            errorMaxLines: 3,
            enabled: enabled,
            suffixIcon: const Icon(Icons.calendar_month_outlined),
          ),
          child: Text(text ?? '', style: theme.textTheme.bodyLarge),
        ),
      ),
    );
  }
}

import 'package:flutter/material.dart';

import '../../core/api/api_error.dart';
import '../../core/api/api_error_text.dart';
import '../../core/l10n.dart';
import '../../design/design.dart';

/// What the scene menu can do.
enum SceneAction { illustrate, report }

/// The menu on every scene: Illustrate (M2), and report or block it (F6).
Future<SceneAction?> showSceneMenu(BuildContext context, {required bool canIllustrate}) {
  final l10n = context.l10n;
  return showAppSheet<SceneAction>(
    context: context,
    builder: (sheet) {
      Widget tile(SceneAction action, IconData icon, String title, [String? subtitle]) => ListTile(
        contentPadding: EdgeInsets.zero,
        leading: Icon(icon),
        title: Text(title),
        subtitle: subtitle == null ? null : Text(subtitle),
        onTap: () => Navigator.of(sheet).pop(action),
      );
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (canIllustrate)
            tile(
              SceneAction.illustrate,
              Icons.brush_outlined,
              l10n.sceneIllustrate,
              l10n.sceneIllustrateBody,
            ),
          tile(SceneAction.report, Icons.flag_outlined, l10n.sceneReport, l10n.sceneReportBody),
        ],
      );
    },
  );
}

/// The report categories (docs/API.md, Reports).
const reportCategories = ['sexual', 'minor', 'hate', 'real_person', 'self_harm', 'other'];

String reportCategoryLabel(AppLocalizations l10n, String category) => switch (category) {
  'sexual' => l10n.reportSexual,
  'minor' => l10n.reportMinor,
  'hate' => l10n.reportHate,
  'real_person' => l10n.reportRealPerson,
  'self_harm' => l10n.reportSelfHarm,
  _ => l10n.reportOther,
};

/// Sends a report. Throws [ApiException] when it can't.
typedef ReportSender =
    Future<void> Function({required String category, String? note, required bool block});

/// Reporting a scene (F6): what is wrong, an optional note, and whether to block it, which hides
/// its text at once and for good. Pops with whether it was blocked, or null when the player backs
/// out.
Future<bool?> showReportSheet(BuildContext context, {required ReportSender send}) =>
    showAppSheet<bool>(
      context: context,
      title: context.l10n.reportTitle,
      builder: (_) => ReportForm(send: send),
    );

class ReportForm extends StatefulWidget {
  const ReportForm({super.key, required this.send});

  final ReportSender send;

  @override
  State<ReportForm> createState() => _ReportFormState();
}

class _ReportFormState extends State<ReportForm> {
  final _note = TextEditingController();
  String? _category;
  bool _block = true;
  bool _sending = false;
  ApiException? _error;

  @override
  void dispose() {
    _note.dispose();
    super.dispose();
  }

  Future<void> _send() async {
    final category = _category;
    if (category == null || _sending) return;
    setState(() {
      _sending = true;
      _error = null;
    });
    try {
      await widget.send(category: category, note: _note.text, block: _block);
      if (mounted) Navigator.of(context).pop(_block);
    } on ApiException catch (e) {
      if (mounted) {
        setState(() {
          _sending = false;
          _error = e;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = context.lucid;
    final l10n = context.l10n;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          l10n.reportIntro,
          style: theme.textTheme.bodyLarge!.copyWith(color: colors.textSecondary),
        ),
        const SizedBox(height: Space.md),
        RadioGroup<String>(
          groupValue: _category,
          onChanged: (value) => setState(() => _category = value),
          child: Column(
            children: [
              for (final category in reportCategories)
                RadioListTile<String>(
                  value: category,
                  contentPadding: EdgeInsets.zero,
                  title: Text(reportCategoryLabel(l10n, category)),
                ),
            ],
          ),
        ),
        const SizedBox(height: Space.sm),
        TextField(
          controller: _note,
          minLines: 1,
          maxLines: 4,
          maxLength: 1000,
          textCapitalization: TextCapitalization.sentences,
          decoration: InputDecoration(labelText: l10n.reportNote),
        ),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          value: _block,
          onChanged: (value) => setState(() => _block = value),
          title: Text(l10n.reportHide),
          subtitle: Text(l10n.reportHideBody),
        ),
        if (_error case final error?) ...[
          const SizedBox(height: Space.sm),
          Text(
            describeError(l10n, error).message,
            style: theme.textTheme.bodyMedium!.copyWith(color: theme.colorScheme.error),
          ),
        ],
        const SizedBox(height: Space.lg),
        FilledButton(
          onPressed: _category == null || _sending ? null : _send,
          child: _sending
              ? SizedBox.square(
                  dimension: 20,
                  child: CircularProgressIndicator(strokeWidth: 2, color: colors.textMuted),
                )
              : Text(l10n.reportSend),
        ),
      ],
    );
  }
}

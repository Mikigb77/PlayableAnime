import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/api/api_error.dart';
import '../../core/l10n.dart';
import '../../design/design.dart';
import '../voice/dictation_button.dart';
import '../voice/input_mode.dart';
import '../voice/speech_engine.dart';
import 'create_flow.dart';
import 'draft.dart';
import 'draft_widgets.dart';

/// How a sheet's change ended: saved (with what it redrafted) or refused because the draft was
/// stale and has been reloaded (T10). A sheet closed without saving returns null.
sealed class SheetOutcome {
  const SheetOutcome();
}

class Saved extends SheetOutcome {
  const Saved(this.redraft);

  final Redraft redraft;
}

class Stale extends SheetOutcome {
  const Stale();
}

/// Opens the sheet of a change, and tells the player how the change ended, in a snackbar.
///
/// The screen's messenger and its words are taken before the sheet opens: the row that opened it
/// is often gone by the time it closes, replaced by its card's "redrafting" lines.
Future<void> _changeSheet(
  BuildContext context, {
  required String title,
  required WidgetBuilder builder,
}) async {
  final l10n = context.l10n;
  final messenger = ScaffoldMessenger.of(context);
  final outcome = await showAppSheet<SheetOutcome>(
    context: context,
    title: title,
    builder: builder,
  );
  if (outcome == null || !messenger.mounted) return;
  final text = switch (outcome) {
    Stale() => l10n.reviewConflict,
    Saved(redraft: Redraft(world: true, character: true)) => l10n.reviewBothRedrafted,
    Saved(redraft: Redraft(world: true)) => l10n.reviewWorldRedrafted,
    Saved(redraft: Redraft(character: true)) => l10n.reviewCharacterRedrafted,
    Saved() => l10n.reviewSaved,
  };
  // How the last change ended is the one thing to say: nothing older waits its turn before it.
  messenger
    ..clearSnackBars()
    ..showSnackBar(SnackBar(content: Text(text)));
}

/// Runs a change from a sheet: closes it when the change saved or the draft was stale, and keeps
/// it open with the failure otherwise, so nothing the player wrote is lost. Out of credits offers
/// the player's own key, and makes the same change on it once they add one (K2, K6). A sheet the
/// player closed meanwhile is closed already, even while it still slides away, so nothing else is
/// closed in its place.
Future<Object?> _runChange(
  BuildContext context,
  Redraft cost,
  Future<Object?> Function() change,
) async {
  final navigator = Navigator.of(context);
  final sheet = ModalRoute.of(context);
  void close(SheetOutcome outcome) {
    if (sheet != null && sheet.isCurrent) navigator.pop(outcome);
  }

  while (true) {
    final failure = await change();
    if (failure == null) {
      close(Saved(cost));
      return null;
    }
    if (failure case ApiException(code: ApiErrorCode.versionConflict)) {
      close(const Stale());
      return null;
    }
    if (!context.mounted || !await offerOwnKey(context, failure)) return failure;
  }
}

/// The save row at the foot of a sheet: what the change costs, any failure, and the button.
class _SheetActions extends StatelessWidget {
  const _SheetActions({
    required this.flow,
    required this.cost,
    required this.label,
    required this.onSave,
    this.error,
    this.onRetry,
    this.secondary,
  });

  final CreateFlow flow;
  final Redraft cost;
  final String label;
  final VoidCallback? onSave;
  final Object? error;

  /// Makes the failed change again, once the player added their own key.
  final VoidCallback? onRetry;
  final Widget? secondary;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return ListenableBuilder(
      listenable: flow,
      builder: (context, _) {
        final busy = flow.busy;
        final redrafting = flow.redrafting;
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const SizedBox(height: Space.lg),
            CostNote(
              cost,
              busy: busy && !redrafting.isFree,
              busyText: _redraftingText(l10n, redrafting),
            ),
            if (error case final error?) ...[
              const SizedBox(height: Space.md),
              InlineError(error, onKeyAdded: onRetry),
            ],
            const SizedBox(height: Space.lg),
            Row(
              children: [
                // The second action takes the room the button leaves, so a long label wraps
                // instead of pushing the button off the sheet.
                Expanded(
                  child: Align(alignment: AlignmentDirectional.centerStart, child: secondary),
                ),
                const SizedBox(width: Space.sm),
                FilledButton(
                  onPressed: busy ? null : onSave,
                  child: busy
                      ? SizedBox.square(
                          dimension: 18,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            color: Theme.of(context).colorScheme.onSurface,
                            semanticsLabel: _redraftingText(l10n, redrafting) ?? l10n.reviewSaving,
                          ),
                        )
                      : Text(label),
                ),
              ],
            ),
          ],
        );
      },
    );
  }
}

/// What a change in flight is redrafting, or null when it redrafts nothing.
String? _redraftingText(AppLocalizations l10n, Redraft redrafting) => switch (redrafting) {
  Redraft(world: true, character: true) => l10n.reviewRedraftingBoth,
  Redraft(world: true) => l10n.reviewRedraftingWorld,
  Redraft(character: true) => l10n.reviewRedraftingCharacter,
  _ => null,
};

/// A text box in the review's style, with the mic as its suffix (V1).
class _ReviewField extends StatelessWidget {
  const _ReviewField({
    required this.tracker,
    required this.draft,
    required this.maxLength,
    this.label,
    this.hint,
    this.minLines = 2,
    this.maxLines = 8,
    this.autofocus = false,
    this.errorText,
    this.helper,
    this.capitalization = TextCapitalization.sentences,
  });

  final InputModeTracker tracker;

  /// The draft the words are for, so dictation hears its names (V6, C6) in its language (S10).
  final Draft draft;
  final int maxLength;
  final String? label;
  final String? hint;
  final int minLines;
  final int maxLines;
  final bool autofocus;

  /// The server's refusal of these words, such as a real person named (G12).
  final String? errorText;

  /// What the field is for, under it.
  final String? helper;
  final TextCapitalization capitalization;

  @override
  Widget build(BuildContext context) => TextField(
    controller: tracker.controller,
    autofocus: autofocus,
    minLines: minLines,
    maxLines: maxLines,
    maxLength: maxLength,
    maxLengthEnforcement: MaxLengthEnforcement.enforced,
    inputFormatters: [
      CodePointLimit(maxLength),
      // One line stays one line, as the server keeps it.
      if (maxLines == 1) FilteringTextInputFormatter.singleLineFormatter,
    ],
    textCapitalization: capitalization,
    style: context.lucidText.narration.copyWith(fontSize: 17),
    decoration: InputDecoration(
      labelText: label,
      hintText: hint,
      helperText: helper,
      helperMaxLines: 3,
      errorText: errorText,
      errorMaxLines: 4,
      alignLabelWithHint: true,
      suffixIcon: Align(
        alignment: Alignment.topRight,
        widthFactor: 1,
        heightFactor: 1,
        child: DictationButton(
          tracker: tracker,
          draftId: draft.id,
          localeId: speechLocale(draft.language),
        ),
      ),
    ),
  );
}

/// A plain field of the draft, which the player changes themselves (G1, G2): the server writes it
/// in at once, with no model call and at no cost.
enum PlainField {
  title('title', DraftLimits.short),
  tone('tone', DraftLimits.short),
  looks('character.looks', DraftLimits.long),
  manner('character.manner', DraftLimits.long);

  const PlainField(this.field, this.maxLength);

  /// The field as the API names it, where a refusal of its words is told.
  final String field;
  final int maxLength;

  bool get oneLine => this == title || this == tone;

  String of(Draft draft) => switch (this) {
    title => draft.title,
    tone => draft.tone,
    looks => draft.character.looks,
    manner => draft.character.manner,
  };

  DraftEdit edit(String text) => switch (this) {
    title => DraftEdit(title: text),
    tone => DraftEdit(tone: text),
    looks => DraftEdit(looks: text),
    manner => DraftEdit(manner: text),
  };
}

/// Type a new title, tone, look or manner (G1, G2). Saved at once, free.
Future<void> showFieldSheet(
  BuildContext context, {
  required CreateFlow flow,
  required PlainField field,
}) {
  final l10n = context.l10n;
  return _changeSheet(
    context,
    title: switch (field) {
      PlainField.title => l10n.titleSheetTitle,
      PlainField.tone => l10n.toneSheetTitle,
      PlainField.looks => l10n.looksSheetTitle,
      PlainField.manner => l10n.mannerSheetTitle,
    },
    builder: (_) => _FieldSheet(flow: flow, field: field),
  );
}

class _FieldSheet extends StatefulWidget {
  const _FieldSheet({required this.flow, required this.field});

  final CreateFlow flow;
  final PlainField field;

  @override
  State<_FieldSheet> createState() => _FieldSheetState();
}

class _FieldSheetState extends State<_FieldSheet> {
  /// The draft as the sheet opened on it. A saved change closes the sheet, so this never goes
  /// stale while the player can act; it keeps the sheet whole while it closes.
  late final Draft _draft = widget.flow.draft!;
  late final _original = widget.field.of(_draft);
  late final _text = TextEditingController(text: _original);
  late final _tracker = InputModeTracker(_text);
  Object? _error;

  /// The words last sent, so a refusal shows under them only while they are still there.
  String? _sent;

  @override
  void dispose() {
    _tracker.dispose();
    _text.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    _sent = _text.text;
    final edit = widget.field.edit(normalizeLine(_text.text));
    final failure = await _runChange(context, Redraft.none, () => widget.flow.edit(edit));
    if (mounted) setState(() => _error = failure);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final field = widget.field;
    return ListenableBuilder(
      listenable: _text,
      builder: (context, _) {
        final text = normalizeLine(_text.text);
        final changed = text.isNotEmpty && text != normalizeLine(_original);
        final refusal = _text.text == _sent ? fieldMessage(_error, field.field) : null;
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _ReviewField(
              tracker: _tracker,
              draft: _draft,
              maxLength: field.maxLength,
              minLines: field.oneLine ? 1 : 3,
              maxLines: field.oneLine ? 1 : 8,
              autofocus: true,
              errorText: refusal,
              helper: switch (field) {
                PlainField.looks => l10n.looksHelp,
                _ when text.isEmpty => l10n.fieldEmpty,
                _ => null,
              },
            ),
            _SheetActions(
              flow: widget.flow,
              cost: Redraft.none,
              label: l10n.save,
              error: fieldMessage(_error, field.field) == null ? _error : null,
              onSave: changed ? _save : null,
              onRetry: changed ? _save : null,
            ),
          ],
        );
      },
    );
  }
}

/// Type the character's name and age (G2). Saved at once, free: the new name takes the old one's
/// place wherever the draft says it.
Future<void> showNameSheet(BuildContext context, {required CreateFlow flow}) => _changeSheet(
  context,
  title: context.l10n.nameSheetTitle,
  builder: (_) => _NameSheet(flow: flow),
);

class _NameSheet extends StatefulWidget {
  const _NameSheet({required this.flow});

  final CreateFlow flow;

  @override
  State<_NameSheet> createState() => _NameSheetState();
}

class _NameSheetState extends State<_NameSheet> {
  late final Draft _draft = widget.flow.draft!;
  late final _name = TextEditingController(text: _draft.character.name);
  late final _age = TextEditingController(text: _draft.character.age?.toString() ?? '');
  late final _tracker = InputModeTracker(_name);
  Object? _error;

  /// The name and the age last sent, so a refusal shows under them only while they are there.
  (String, String)? _sent;

  @override
  void dispose() {
    _tracker.dispose();
    _name.dispose();
    _age.dispose();
    super.dispose();
  }

  /// Only what changed. An age left empty stays as it is.
  DraftEdit get _edit {
    final name = normalizeLine(_name.text);
    final age = int.tryParse(_age.text);
    return DraftEdit(
      name: name.isEmpty || name == normalizeLine(_draft.character.name) ? null : name,
      age: age == _draft.character.age ? null : age,
    );
  }

  Future<void> _save() async {
    final edit = _edit;
    _sent = (_name.text, _age.text);
    final failure = await _runChange(context, Redraft.none, () => widget.flow.edit(edit));
    if (mounted) setState(() => _error = failure);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return ListenableBuilder(
      listenable: Listenable.merge([_name, _age]),
      builder: (context, _) {
        final edit = _edit;
        final changed = edit.name != null || edit.age != null;
        final sent = _sent == (_name.text, _age.text);
        final atName = sent ? fieldMessage(_error, 'character.name') : null;
        final atAge = sent ? fieldMessage(_error, 'character.age') : null;
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _ReviewField(
              tracker: _tracker,
              draft: _draft,
              maxLength: DraftLimits.short,
              label: l10n.nameLabel,
              minLines: 1,
              maxLines: 1,
              autofocus: true,
              errorText: atName,
              capitalization: TextCapitalization.words,
              helper: normalizeLine(_name.text).isEmpty ? l10n.fieldEmpty : null,
            ),
            const SizedBox(height: Space.md),
            TextField(
              controller: _age,
              keyboardType: TextInputType.number,
              inputFormatters: [
                FilteringTextInputFormatter.digitsOnly,
                LengthLimitingTextInputFormatter('${DraftLimits.ageMax}'.length - 1),
              ],
              style: context.lucidText.narration.copyWith(fontSize: 17),
              decoration: InputDecoration(labelText: l10n.ageLabel, errorText: atAge),
            ),
            _SheetActions(
              flow: widget.flow,
              cost: Redraft.none,
              label: l10n.save,
              error: atName == null && atAge == null ? _error : null,
              onSave: changed ? _save : null,
              onRetry: changed ? _save : null,
            ),
          ],
        );
      },
    );
  }
}

/// Ask for something different in plain words, such as "add hidden vampires" (G1, G2). Asked at
/// a row of the summary ([about], with the row's [aboutLabel] and its text), the change is told
/// which part it is about, so "more of this" says what "this" is.
Future<void> showReviseSheet(
  BuildContext context, {
  required CreateFlow flow,
  required DraftPart part,
  LineKind? about,
  String? aboutLabel,
  String? aboutText,
}) {
  final l10n = context.l10n;
  return _changeSheet(
    context,
    title: switch (part) {
      DraftPart.world => l10n.reviseWorldTitle,
      DraftPart.character => l10n.reviseCharacterTitle,
    },
    builder: (_) => _ReviseSheet(
      flow: flow,
      part: part,
      about: about,
      aboutLabel: aboutLabel,
      aboutText: aboutText,
    ),
  );
}

class _ReviseSheet extends StatefulWidget {
  const _ReviseSheet({
    required this.flow,
    required this.part,
    this.about,
    this.aboutLabel,
    this.aboutText,
  });

  final CreateFlow flow;
  final DraftPart part;
  final LineKind? about;
  final String? aboutLabel;
  final String? aboutText;

  @override
  State<_ReviseSheet> createState() => _ReviseSheetState();
}

class _ReviseSheetState extends State<_ReviseSheet> {
  final _text = TextEditingController();
  late final _tracker = InputModeTracker(_text);
  Object? _error;

  /// The words last sent, so a refusal shows under them only while they are still there.
  String? _sent;

  Redraft get _cost =>
      Redraft(world: widget.part == DraftPart.world, character: widget.part == DraftPart.character);

  @override
  void dispose() {
    _tracker.dispose();
    _text.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final instruction = _text.text.trim();
    _sent = instruction;
    final failure = await _runChange(
      context,
      _cost,
      () => widget.flow.revise(widget.part, instruction, about: widget.about),
    );
    if (mounted) setState(() => _error = failure);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return ListenableBuilder(
      listenable: _text,
      builder: (context, _) => Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (widget.aboutLabel case final label?) ...[
            _About(label: label, text: widget.aboutText ?? ''),
            const SizedBox(height: Space.lg),
          ],
          _ReviewField(
            tracker: _tracker,
            draft: widget.flow.draft!,
            maxLength: DraftLimits.instruction,
            label: l10n.reviseLabel,
            hint: switch (widget.part) {
              _ when widget.about != null => null,
              DraftPart.world => l10n.reviseWorldHint,
              DraftPart.character => l10n.reviseCharacterHint,
            },
            minLines: 3,
            autofocus: true,
            errorText: _text.text.trim() == _sent ? fieldMessage(_error, 'instruction') : null,
          ),
          _SheetActions(
            flow: widget.flow,
            cost: _cost,
            label: l10n.reviseAction,
            error: fieldMessage(_error, 'instruction') == null ? _error : null,
            onSave: _text.text.trim().isEmpty ? null : _save,
            onRetry: _text.text.trim().isEmpty ? null : _save,
          ),
        ],
      ),
    );
  }
}

/// The row of the summary a change is asked at: its label and what it says now.
class _About extends StatelessWidget {
  const _About({required this.label, required this.text});

  final String label;
  final String text;

  @override
  Widget build(BuildContext context) {
    final colors = context.lucid;
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.all(Space.md),
      decoration: BoxDecoration(
        color: scheme.surfaceContainerLow,
        borderRadius: Radii.field,
        border: Border.all(color: scheme.outlineVariant),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            context.l10n.reviseAbout(label),
            style: context.lucidText.meta.copyWith(color: colors.accent),
          ),
          if (text.isNotEmpty) ...[
            const SizedBox(height: Space.xs),
            Text(
              text,
              maxLines: 4,
              overflow: TextOverflow.ellipsis,
              style: Theme.of(context).textTheme.bodyMedium!.copyWith(color: colors.textSecondary),
            ),
          ],
        ],
      ),
    );
  }
}

/// Change one rule of the world, or add one ([index] null): its words, and whether it holds for
/// the whole story or is true for now (G6, G7). Flipping that is free; new words redraft the
/// world to match.
Future<void> showRuleSheet(BuildContext context, {required CreateFlow flow, int? index}) {
  final l10n = context.l10n;
  return _changeSheet(
    context,
    title: index == null ? l10n.ruleSheetNew : l10n.ruleSheetTitle,
    builder: (_) => _RuleSheet(flow: flow, index: index),
  );
}

class _RuleSheet extends StatefulWidget {
  const _RuleSheet({required this.flow, this.index});

  final CreateFlow flow;
  final int? index;

  @override
  State<_RuleSheet> createState() => _RuleSheetState();
}

class _RuleSheetState extends State<_RuleSheet> {
  late final Draft _draft = widget.flow.draft!;
  late final DraftRule _original = switch (widget.index) {
    final index? => _draft.advanced.rules[index],
    null => const DraftRule(text: ''),
  };
  late final _text = TextEditingController(text: _original.text);
  late final _tracker = InputModeTracker(_text);
  late bool _fixed = _original.fixed;
  Object? _error;

  /// The words last sent, so a refusal shows under them only while they are still there.
  String? _sent;

  /// Whether the last change sent removed the rule, to make it again after a key is added.
  var _removing = false;

  @override
  void dispose() {
    _tracker.dispose();
    _text.dispose();
    super.dispose();
  }

  /// The whole list the player sees, with this rule changed, added or taken out.
  DraftEdit _edit({bool remove = false}) {
    final rules = [..._draft.advanced.rules];
    final rule = _original.copyWith(text: _text.text, fixed: _fixed);
    switch (widget.index) {
      case final index? when remove:
        rules.removeAt(index);
      case final index?:
        rules[index] = rule;
      case null:
        rules.add(rule);
    }
    return DraftEdit(rules: rules);
  }

  /// Where the server tells a refusal of this rule's words.
  String get _field => 'advanced.rules.${widget.index ?? _draft.advanced.rules.length}.text';

  Future<void> _save({bool remove = false}) async {
    final edit = _edit(remove: remove);
    _removing = remove;
    _sent = _text.text;
    final cost = redraftFor(_draft, edit);
    final failure = await _runChange(context, cost, () => widget.flow.edit(edit));
    if (mounted) setState(() => _error = failure);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final theme = Theme.of(context);
    return ListenableBuilder(
      // The flow too, so Remove is disabled while a change is saved.
      listenable: Listenable.merge([_text, widget.flow]),
      builder: (context, _) {
        final text = normalizeLine(_text.text);
        final changed =
            text.isNotEmpty && (text != normalizeLine(_original.text) || _fixed != _original.fixed);
        final refusal = _text.text == _sent ? fieldMessage(_error, _field) : null;
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _ReviewField(
              tracker: _tracker,
              draft: _draft,
              maxLength: DraftLimits.line,
              hint: l10n.ruleHint,
              autofocus: widget.index == null,
              errorText: refusal,
            ),
            const SizedBox(height: Space.sm),
            MergeSemantics(
              child: Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(l10n.ruleHolds, style: theme.textTheme.titleSmall),
                        const SizedBox(height: Space.xxs),
                        Text(
                          l10n.ruleHoldsBody,
                          style: theme.textTheme.bodySmall!.copyWith(
                            color: context.lucid.textSecondary,
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(width: Space.md),
                  Switch(value: _fixed, onChanged: (fixed) => setState(() => _fixed = fixed)),
                ],
              ),
            ),
            _SheetActions(
              flow: widget.flow,
              // What the enabled action costs: Save once something changed, else Remove.
              cost: redraftFor(_draft, _edit(remove: !changed && widget.index != null)),
              label: l10n.save,
              error: fieldMessage(_error, _field) == null ? _error : null,
              onSave: changed ? _save : null,
              onRetry: () => _save(remove: _removing),
              secondary: widget.index == null
                  ? null
                  : TextButton.icon(
                      onPressed: widget.flow.busy ? null : () => _save(remove: true),
                      icon: const Icon(Icons.delete_outline_rounded, size: 20),
                      label: Text(l10n.ruleRemove),
                    ),
            ),
          ],
        );
      },
    );
  }
}

/// A choice about how the story plays that redrafts something (lowering the rating to Teen, a
/// new gift): what it means and what it costs, before the player makes it (F2, G22).
Future<void> showChoiceSheet(
  BuildContext context, {
  required CreateFlow flow,
  required String title,
  required String choice,
  required String body,
  required DraftEdit edit,
}) => _changeSheet(
  context,
  title: title,
  builder: (_) => _ChoiceSheet(flow: flow, choice: choice, body: body, edit: edit),
);

class _ChoiceSheet extends StatefulWidget {
  const _ChoiceSheet({
    required this.flow,
    required this.choice,
    required this.body,
    required this.edit,
  });

  final CreateFlow flow;
  final String choice;
  final String body;
  final DraftEdit edit;

  @override
  State<_ChoiceSheet> createState() => _ChoiceSheetState();
}

class _ChoiceSheetState extends State<_ChoiceSheet> {
  late final Draft _draft = widget.flow.draft!;
  Object? _error;

  Future<void> _save() async {
    final cost = redraftFor(_draft, widget.edit);
    final failure = await _runChange(context, cost, () => widget.flow.edit(widget.edit));
    if (mounted) setState(() => _error = failure);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(widget.choice, style: theme.textTheme.titleMedium),
        const SizedBox(height: Space.xs),
        Text(
          widget.body,
          style: theme.textTheme.bodyMedium!.copyWith(color: context.lucid.textSecondary),
        ),
        _SheetActions(
          flow: widget.flow,
          cost: redraftFor(_draft, widget.edit),
          label: context.l10n.choiceChange,
          error: _error,
          onSave: _save,
          onRetry: _save,
        ),
      ],
    );
  }
}

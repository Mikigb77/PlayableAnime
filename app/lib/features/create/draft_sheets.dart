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

/// Tells the player how a change ended, in a snackbar.
void reportOutcome(BuildContext context, SheetOutcome? outcome) {
  if (outcome == null) return;
  final l10n = context.l10n;
  final text = switch (outcome) {
    Stale() => l10n.reviewConflict,
    Saved(redraft: Redraft(world: true, character: true)) => l10n.reviewBothRedrafted,
    Saved(redraft: Redraft(world: true)) => l10n.reviewWorldRedrafted,
    Saved(redraft: Redraft(character: true)) => l10n.reviewCharacterRedrafted,
    Saved() => l10n.reviewSaved,
  };
  ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
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
                ?secondary,
                const Spacer(),
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
    this.autofocus = false,
    this.errorText,
  });

  final InputModeTracker tracker;

  /// The draft the words are for, so dictation hears its names (V6, C6) in its language (S10).
  final Draft draft;
  final int maxLength;
  final String? label;
  final String? hint;
  final int minLines;
  final bool autofocus;

  /// The server's refusal of these words, such as a real person named (G12).
  final String? errorText;

  @override
  Widget build(BuildContext context) => TextField(
    controller: tracker.controller,
    autofocus: autofocus,
    minLines: minLines,
    maxLines: 8,
    maxLength: maxLength,
    maxLengthEnforcement: MaxLengthEnforcement.enforced,
    inputFormatters: [CodePointLimit(maxLength)],
    textCapitalization: TextCapitalization.sentences,
    style: context.lucidText.narration.copyWith(fontSize: 17),
    decoration: InputDecoration(
      labelText: label,
      hintText: hint,
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

/// Change one line of the world or the character, or remove it (G1, G2). Either redrafts that
/// part to match.
Future<void> showLineSheet(
  BuildContext context, {
  required CreateFlow flow,
  required DraftPart part,
  required int index,
}) async {
  final outcome = await showAppSheet<SheetOutcome>(
    context: context,
    title: context.l10n.lineSheetTitle,
    builder: (_) => _LineSheet(flow: flow, part: part, index: index),
  );
  if (context.mounted) reportOutcome(context, outcome);
}

class _LineSheet extends StatefulWidget {
  const _LineSheet({required this.flow, required this.part, required this.index});

  final CreateFlow flow;
  final DraftPart part;
  final int index;

  @override
  State<_LineSheet> createState() => _LineSheetState();
}

class _LineSheetState extends State<_LineSheet> {
  /// The draft as the sheet opened on it. A saved change closes the sheet, so this never goes
  /// stale while the player can act; it keeps the sheet whole while it closes.
  late final Draft _draft = widget.flow.draft!;
  late final _original = _draft.linesOf(widget.part)[widget.index];
  late final _text = TextEditingController(text: _original);
  late final _tracker = InputModeTracker(_text);
  Object? _error;

  /// The words last sent, so a refusal shows under them only while they are still there.
  String? _sent;

  /// Whether the last change sent removed the line, to make it again after a key is added.
  var _removing = false;

  String get _field => '${widget.part.wire}_lines.${widget.index}';

  @override
  void dispose() {
    _tracker.dispose();
    _text.dispose();
    super.dispose();
  }

  DraftEdit _edit({bool remove = false}) {
    final lines = [..._draft.linesOf(widget.part)];
    if (remove) {
      lines.removeAt(widget.index);
    } else {
      lines[widget.index] = _text.text;
    }
    return DraftEdit.lines(widget.part, lines);
  }

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
    return ListenableBuilder(
      // The flow too, so Remove is disabled while a change is saved.
      listenable: Listenable.merge([_text, widget.flow]),
      builder: (context, _) {
        final text = normalizeLine(_text.text);
        final changed = text != normalizeLine(_original);
        final removable = _draft.linesOf(widget.part).length > 1;
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _ReviewField(
              tracker: _tracker,
              draft: _draft,
              maxLength: DraftLimits.line,
              autofocus: true,
              errorText: _text.text == _sent ? fieldMessage(_error, _field) : null,
            ),
            if (text.isEmpty)
              Text(
                l10n.lineEmpty,
                style: Theme.of(
                  context,
                ).textTheme.bodySmall!.copyWith(color: context.lucid.textMuted),
              ),
            _SheetActions(
              flow: widget.flow,
              // What the enabled action costs: Save once the line changed, else Remove, which
              // redrafts the part as a rewrite does.
              cost: redraftFor(_draft, _edit(remove: !changed && removable)),
              label: l10n.save,
              error: fieldMessage(_error, _field) == null ? _error : null,
              onSave: changed && text.isNotEmpty ? _save : null,
              onRetry: () => _save(remove: _removing),
              secondary: removable
                  ? TextButton.icon(
                      onPressed: widget.flow.busy ? null : () => _save(remove: true),
                      icon: const Icon(Icons.delete_outline_rounded, size: 20),
                      label: Text(l10n.lineRemove),
                    )
                  : null,
            ),
          ],
        );
      },
    );
  }
}

/// Ask for something different in plain words, such as "add hidden vampires" (G1, G2).
Future<void> showReviseSheet(
  BuildContext context, {
  required CreateFlow flow,
  required DraftPart part,
}) async {
  final l10n = context.l10n;
  final outcome = await showAppSheet<SheetOutcome>(
    context: context,
    title: switch (part) {
      DraftPart.world => l10n.reviseWorldTitle,
      DraftPart.character => l10n.reviseCharacterTitle,
    },
    builder: (_) => _ReviseSheet(flow: flow, part: part),
  );
  if (context.mounted) reportOutcome(context, outcome);
}

class _ReviseSheet extends StatefulWidget {
  const _ReviseSheet({required this.flow, required this.part});

  final CreateFlow flow;
  final DraftPart part;

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
      () => widget.flow.revise(widget.part, instruction),
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
          _ReviewField(
            tracker: _tracker,
            draft: widget.flow.draft!,
            maxLength: DraftLimits.instruction,
            label: l10n.reviseLabel,
            hint: switch (widget.part) {
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

/// Teen or Mature 17+ (F2, F8). Lowering to Teen redrafts the world and the character within it.
Future<void> showRatingSheet(BuildContext context, {required CreateFlow flow}) async {
  final outcome = await showAppSheet<SheetOutcome>(
    context: context,
    title: context.l10n.ratingSheetTitle,
    builder: (_) => _RatingSheet(flow: flow),
  );
  if (context.mounted) reportOutcome(context, outcome);
}

class _RatingSheet extends StatefulWidget {
  const _RatingSheet({required this.flow});

  final CreateFlow flow;

  @override
  State<_RatingSheet> createState() => _RatingSheetState();
}

class _RatingSheetState extends State<_RatingSheet> {
  late Rating _rating = widget.flow.draft!.rating;
  Object? _error;

  Redraft _costOf(Rating rating) => redraftFor(widget.flow.draft!, DraftEdit(rating: rating));

  Future<void> _save() async {
    final edit = DraftEdit(rating: _rating);
    final failure = await _runChange(context, _costOf(_rating), () => widget.flow.edit(edit));
    if (mounted) setState(() => _error = failure);
  }

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      RatingChoice(
        value: _rating,
        costOf: _costOf,
        onChanged: (rating) => setState(() => _rating = rating),
      ),
      _SheetActions(
        flow: widget.flow,
        cost: _costOf(_rating),
        label: context.l10n.save,
        error: _error,
        onSave: _rating == widget.flow.draft!.rating ? null : _save,
        onRetry: _rating == widget.flow.draft!.rating ? null : _save,
      ),
    ],
  );
}

/// The advanced fields (G1): physics (A9), the gift (G22), difficulty (A5), world events (W16)
/// and the rules of the world, fixed or open (G6, G7).
Future<void> showAdvancedSheet(BuildContext context, {required CreateFlow flow}) async {
  final outcome = await showAppSheet<SheetOutcome>(
    context: context,
    title: context.l10n.advancedTitle,
    builder: (_) => _AdvancedSheet(flow: flow),
  );
  if (context.mounted) reportOutcome(context, outcome);
}

class _RuleField {
  _RuleField(DraftRule rule)
    : id = rule.id,
      fixed = rule.fixed,
      text = TextEditingController(text: rule.text) {
    tracker = InputModeTracker(text);
  }

  final String? id;
  final TextEditingController text;
  late final InputModeTracker tracker;
  bool fixed;

  DraftRule get rule => DraftRule(id: id, text: text.text, fixed: fixed);

  void dispose() {
    tracker.dispose();
    text.dispose();
  }
}

class _AdvancedSheet extends StatefulWidget {
  const _AdvancedSheet({required this.flow});

  final CreateFlow flow;

  @override
  State<_AdvancedSheet> createState() => _AdvancedSheetState();
}

class _AdvancedSheetState extends State<_AdvancedSheet> {
  late final DraftAdvanced _start = widget.flow.draft!.advanced;
  late Physics _physics = _start.physics;
  late GiftStrength _gift = _start.giftStrength;
  late Difficulty _difficulty = _start.difficulty;
  late EventFrequency _events = _start.eventFrequency;
  late final List<_RuleField> _rules = [for (final rule in _start.rules) _RuleField(rule)];
  Object? _error;

  /// The rules last sent, with their words then, to place a refusal under the one it is about.
  List<(_RuleField, String)> _sent = const [];

  @override
  void dispose() {
    for (final rule in _rules) {
      rule.dispose();
    }
    super.dispose();
  }

  /// The rules to send: blank ones are left out, as the server refuses an empty rule.
  List<_RuleField> get _kept => [
    for (final rule in _rules)
      if (normalizeLine(rule.text.text).isNotEmpty) rule,
  ];

  /// Only what changed, so an untouched field never costs anything.
  DraftEdit get _edit {
    final rules = [for (final rule in _kept) rule.rule];
    return DraftEdit(
      physics: _physics == _start.physics ? null : _physics,
      giftStrength: _gift == _start.giftStrength ? null : _gift,
      difficulty: _difficulty == _start.difficulty ? null : _difficulty,
      eventFrequency: _events == _start.eventFrequency ? null : _events,
      rules: _sameRules(rules) ? null : rules,
    );
  }

  bool _sameRules(List<DraftRule> rules) =>
      rules.length == _start.rules.length &&
      [
        for (final (i, rule) in rules.indexed)
          rule.id == _start.rules[i].id &&
              normalizeLine(rule.text) == normalizeLine(_start.rules[i].text) &&
              rule.fixed == _start.rules[i].fixed,
      ].every((same) => same);

  bool get _changed {
    final edit = _edit;
    return edit.physics != null ||
        edit.giftStrength != null ||
        edit.difficulty != null ||
        edit.eventFrequency != null ||
        edit.rules != null;
  }

  void _addRule() => setState(() => _rules.add(_RuleField(const DraftRule(text: ''))));

  void _removeRule(_RuleField rule) => setState(() {
    _rules.remove(rule);
    rule.dispose();
  });

  Future<void> _save() async {
    final edit = _edit;
    _sent = [for (final rule in _kept) (rule, rule.text.text)];
    final cost = redraftFor(widget.flow.draft!, edit);
    final failure = await _runChange(context, cost, () => widget.flow.edit(edit));
    if (mounted) setState(() => _error = failure);
  }

  /// The server's refusal of a rule's words (G12), while they are still there.
  String? _refusalOf(_RuleField rule) {
    for (final (i, (sent, text)) in _sent.indexed) {
      if (sent == rule && rule.text.text == text) {
        return fieldMessage(_error, 'advanced.rules.$i.text');
      }
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final theme = Theme.of(context);
    final colors = context.lucid;
    final atRule = [
      for (final (i, _) in _sent.indexed) fieldMessage(_error, 'advanced.rules.$i.text'),
    ].nonNulls.isNotEmpty;
    return ListenableBuilder(
      // Rebuilt as rule texts change, so the cost stays right.
      listenable: Listenable.merge([for (final rule in _rules) rule.text]),
      builder: (context, _) => Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          ChoiceField<Physics>(
            label: l10n.physicsLabel,
            values: Physics.values,
            value: _physics,
            labelOf: l10n.physics,
            bodyOf: l10n.physicsBody,
            onChanged: (value) => setState(() => _physics = value),
          ),
          ChoiceField<GiftStrength>(
            label: l10n.giftLabel,
            values: GiftStrength.values,
            value: _gift,
            labelOf: l10n.gift,
            bodyOf: l10n.giftBody,
            onChanged: (value) => setState(() => _gift = value),
          ),
          ChoiceField<Difficulty>(
            label: l10n.difficultyLabel,
            values: Difficulty.values,
            value: _difficulty,
            labelOf: l10n.difficulty,
            bodyOf: l10n.difficultyBody,
            onChanged: (value) => setState(() => _difficulty = value),
          ),
          ChoiceField<EventFrequency>(
            label: l10n.eventsLabel,
            values: EventFrequency.values,
            value: _events,
            labelOf: l10n.events,
            bodyOf: l10n.eventsBody,
            onChanged: (value) => setState(() => _events = value),
          ),
          FieldLabel(l10n.rulesLabel),
          Text(
            l10n.rulesBody,
            style: theme.textTheme.bodyMedium!.copyWith(color: colors.textSecondary),
          ),
          for (final rule in _rules)
            Padding(
              key: ObjectKey(rule),
              padding: const EdgeInsets.only(top: Space.md),
              child: _RuleEditor(
                rule: rule,
                draft: widget.flow.draft!,
                errorText: _refusalOf(rule),
                onFixed: (fixed) => setState(() => rule.fixed = fixed),
                onRemove: () => _removeRule(rule),
              ),
            ),
          const SizedBox(height: Space.sm),
          Align(
            alignment: AlignmentDirectional.centerStart,
            child: _rules.length < DraftLimits.rules
                ? TextButton.icon(
                    onPressed: _addRule,
                    icon: const Icon(Icons.add_rounded),
                    label: Text(l10n.ruleAdd),
                  )
                : Text(l10n.rulesFull, style: context.lucidText.meta),
          ),
          _SheetActions(
            flow: widget.flow,
            cost: redraftFor(widget.flow.draft!, _edit),
            label: l10n.save,
            error: atRule ? null : _error,
            onSave: _changed ? _save : null,
            onRetry: _changed ? _save : null,
          ),
        ],
      ),
    );
  }
}

class _RuleEditor extends StatelessWidget {
  const _RuleEditor({
    required this.rule,
    required this.draft,
    required this.onFixed,
    required this.onRemove,
    this.errorText,
  });

  final _RuleField rule;
  final Draft draft;
  final String? errorText;
  final ValueChanged<bool> onFixed;
  final VoidCallback onRemove;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.fromLTRB(Space.md, Space.md, Space.xs, Space.xs),
      decoration: BoxDecoration(
        color: scheme.surfaceContainerLow,
        borderRadius: Radii.card,
        border: Border.all(color: scheme.outlineVariant),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          TextField(
            controller: rule.text,
            minLines: 1,
            maxLines: 4,
            maxLength: DraftLimits.line,
            maxLengthEnforcement: MaxLengthEnforcement.enforced,
            inputFormatters: const [CodePointLimit(DraftLimits.line)],
            textCapitalization: TextCapitalization.sentences,
            decoration: InputDecoration(
              hintText: l10n.ruleHint,
              errorText: errorText,
              errorMaxLines: 4,
              counterText: '',
              filled: false,
              border: InputBorder.none,
              enabledBorder: InputBorder.none,
              focusedBorder: InputBorder.none,
              isDense: true,
              suffixIcon: DictationButton(
                tracker: rule.tracker,
                draftId: draft.id,
                localeId: speechLocale(draft.language),
              ),
            ),
          ),
          Row(
            children: [
              Expanded(
                child: MergeSemantics(
                  child: Row(
                    children: [
                      Switch(value: rule.fixed, onChanged: onFixed),
                      const SizedBox(width: Space.sm),
                      Flexible(child: Text(l10n.ruleFixed)),
                    ],
                  ),
                ),
              ),
              IconButton(
                onPressed: onRemove,
                tooltip: l10n.ruleRemove,
                icon: const Icon(Icons.delete_outline_rounded),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

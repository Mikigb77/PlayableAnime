import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/l10n.dart';
import '../../core/preferences.dart';
import '../../design/design.dart';
import '../discover/premises.dart';
import '../voice/dictation_button.dart';
import '../voice/input_mode.dart';
import '../voice/speech_engine.dart';
import 'create_flow.dart';
import 'draft.dart';
import 'draft_widgets.dart';

/// What the player has written and chosen on the first step. It outlives the step, which is
/// rebuilt after drafting fails, so nothing is lost however long the failure took.
class PremiseForm {
  PremiseForm({String? premise}) : text = TextEditingController(text: premise);

  final TextEditingController text;

  /// Teen until the player picks Mature, which only an adult account can (F8).
  Rating rating = Rating.teen;
  Physics? physics;
  GiftStrength? gift;
  Difficulty? difficulty;
  EventFrequency? events;
  bool advancedOpen = false;

  void dispose() => text.dispose();
}

/// The first step: the premise, typed or dictated (V1), or a starter's own text to keep or change
/// (S1); the rating (F2, F8); and, folded away, the advanced choices (G1). [onDraft] drafts what
/// [form] holds.
class PremiseStep extends ConsumerStatefulWidget {
  const PremiseStep({
    super.key,
    required this.flow,
    required this.form,
    required this.onDraft,
    this.starter,
  });

  final CreateFlow flow;
  final PremiseForm form;
  final VoidCallback onDraft;
  final Premise? starter;

  @override
  ConsumerState<PremiseStep> createState() => _PremiseStepState();
}

class _PremiseStepState extends ConsumerState<PremiseStep> {
  PremiseForm get _form => widget.form;
  TextEditingController get _premise => _form.text;
  late final _tracker = InputModeTracker(_premise);

  @override
  void dispose() {
    _tracker.dispose();
    super.dispose();
  }

  /// The server's refusal of the premise, while the box still holds the words it refused.
  String? _refused() {
    final message = fieldMessage(widget.flow.error, 'premise');
    if (message == null || _premise.text.trim() != widget.flow.draftingPremise) return null;
    return message;
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final theme = Theme.of(context);
    final colors = context.lucid;
    final starter = widget.starter;
    // A limit learned after the screen opened still holds (F8).
    final rating = ref.watch(maxRatingProvider) == Rating.teen ? Rating.teen : _form.rating;

    return ListView(
      padding: const EdgeInsets.only(bottom: Space.xxxl),
      children: [
        if (starter?.coverUrl case final cover?)
          ContentColumn.reading(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(Space.gutter, Space.sm, Space.gutter, 0),
              child: PictureSlot(
                status: PictureStatus.ready,
                url: cover,
                aspectRatio: 16 / 9,
                alignment: coverFocus,
                semanticLabel: starter!.title,
              ),
            ),
          ),
        ContentColumn.reading(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(Space.gutter, Space.xl, Space.gutter, 0),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                if (starter != null && starter.genre.isNotEmpty) ...[
                  Text(
                    starter.genre.toUpperCase(),
                    style: context.lucidText.overline.copyWith(color: colors.accent),
                  ),
                  const SizedBox(height: Space.xs),
                ],
                Semantics(
                  header: true,
                  child: Text(
                    starter?.title ?? l10n.createHeading,
                    style: theme.textTheme.headlineLarge,
                  ),
                ),
                const SizedBox(height: Space.sm),
                Text(
                  starter?.tagline ?? l10n.createSubheading,
                  style: theme.textTheme.bodyLarge!.copyWith(color: colors.textSecondary),
                ),
                const SizedBox(height: Space.xl),
                ListenableBuilder(
                  listenable: Listenable.merge([_premise, widget.flow]),
                  builder: (context, _) => TextField(
                    controller: _premise,
                    minLines: 5,
                    maxLines: 12,
                    maxLength: DraftLimits.premiseMax,
                    maxLengthEnforcement: MaxLengthEnforcement.enforced,
                    inputFormatters: const [CodePointLimit(DraftLimits.premiseMax)],
                    textCapitalization: TextCapitalization.sentences,
                    style: context.lucidText.narration.copyWith(fontSize: 17),
                    // The counter only near the limit.
                    buildCounter:
                        (context, {required currentLength, required isFocused, maxLength}) =>
                            currentLength > DraftLimits.premiseMax - 400
                            ? Text(l10n.composerCount(currentLength, DraftLimits.premiseMax))
                            : null,
                    decoration: InputDecoration(
                      labelText: l10n.createPremiseLabel,
                      hintText: l10n.createPremiseHint,
                      helperText: starter == null ? null : l10n.createStarterPremiseHelp,
                      helperMaxLines: 2,
                      // A refusal about these very words, such as a real person named (G12).
                      errorText: _refused(),
                      errorMaxLines: 4,
                      alignLabelWithHint: true,
                      suffixIcon: Align(
                        alignment: Alignment.topRight,
                        widthFactor: 1,
                        heightFactor: 1,
                        // The story will start in the app's language (S10).
                        child: DictationButton(
                          tracker: _tracker,
                          localeId: speechLocale(ref.watch(appLanguageCodeProvider)),
                        ),
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: Space.lg),
                const _Decide(),
                // Whole ideas for an empty page, gone once there are words a tap would replace.
                if (starter == null)
                  ListenableBuilder(
                    listenable: _premise,
                    builder: (context, _) => AnimatedSize(
                      duration: Motion.of(context, Motion.base),
                      curve: Motion.standard,
                      alignment: Alignment.topCenter,
                      child: _premise.text.trim().isEmpty
                          ? _Sparks(onPick: (text) => _tracker.controller.text = text)
                          : const SizedBox(width: double.infinity),
                    ),
                  ),
                FieldLabel(l10n.createRatingLabel),
                RatingChoice(
                  value: rating,
                  onChanged: (rating) => setState(() => _form.rating = rating),
                ),
                const SizedBox(height: Space.lg),
                _AdvancedChoices(
                  open: _form.advancedOpen,
                  onToggle: () => setState(() => _form.advancedOpen = !_form.advancedOpen),
                  physics: _form.physics ?? Physics.funFirst,
                  gift: _form.gift,
                  difficulty: _form.difficulty ?? Difficulty.balanced,
                  events: _form.events ?? EventFrequency.normal,
                  onPhysics: (value) => setState(() => _form.physics = value),
                  onGift: (value) => setState(() => _form.gift = value),
                  onDifficulty: (value) => setState(() => _form.difficulty = value),
                  onEvents: (value) => setState(() => _form.events = value),
                ),
                ListenableBuilder(
                  listenable: Listenable.merge([_premise, widget.flow]),
                  builder: (context, _) {
                    final length = _premise.text.trim().length;
                    final short = length < DraftLimits.premiseMin;
                    return Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        if (widget.flow.error case final error?
                            when fieldMessage(error, 'premise') == null) ...[
                          const SizedBox(height: Space.xl),
                          InlineError(error, onKeyAdded: widget.onDraft),
                        ],
                        const SizedBox(height: Space.xl),
                        FilledButton.icon(
                          onPressed: short || widget.flow.busy ? null : widget.onDraft,
                          icon: const Icon(Icons.auto_awesome_rounded),
                          label: Text(l10n.createDraftAction),
                        ),
                        const SizedBox(height: Space.sm),
                        Text(
                          short && length > 0 ? l10n.createTooShort : l10n.createDraftCost,
                          textAlign: TextAlign.center,
                          style: context.lucidText.meta.copyWith(color: colors.textMuted),
                        ),
                      ],
                    );
                  },
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

/// What a premise can settle before the story starts, each with an example in plain words: who
/// the character is, what sets them apart, what is coming and who is in their life. What the
/// premise names, the draft shows; the rest stays the story's surprise (G1).
class _Decide extends StatelessWidget {
  const _Decide();

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final theme = Theme.of(context);
    final colors = context.lucid;
    final examples = [
      (Icons.person_outline_rounded, l10n.createDecideWho, l10n.createDecideWhoExample),
      (Icons.auto_awesome_outlined, l10n.createDecideSpecial, l10n.createDecideSpecialExample),
      (Icons.hourglass_bottom_rounded, l10n.createDecideComing, l10n.createDecideComingExample),
      (Icons.group_outlined, l10n.createDecidePeople, l10n.createDecidePeopleExample),
    ];
    return Card(
      margin: EdgeInsets.zero,
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(Space.lg, Space.lg, Space.lg, Space.sm),
            child: Semantics(
              header: true,
              child: Text(l10n.createDecideLabel, style: theme.textTheme.titleSmall),
            ),
          ),
          for (final (icon, kind, example) in examples)
            MergeSemantics(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: Space.lg, vertical: Space.sm),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Padding(
                      padding: const EdgeInsets.only(top: Space.xxs),
                      child: ExcludeSemantics(child: Icon(icon, size: 20, color: colors.accent)),
                    ),
                    const SizedBox(width: Space.md),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(kind, style: theme.textTheme.labelLarge),
                          const SizedBox(height: Space.xxs),
                          Text(
                            example,
                            style: context.lucidText.playerAction.copyWith(
                              fontSize: 15,
                              color: colors.textSecondary,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
          const SizedBox(height: Space.sm),
          ColoredBox(
            color: colors.accentSoft,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: Space.lg, vertical: Space.md),
              child: Text(
                l10n.createDecideNote,
                style: theme.textTheme.bodySmall!.copyWith(color: colors.onAccentSoft),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// Example premises for a blank page (G1's own examples). Picking one fills the box.
class _Sparks extends StatelessWidget {
  const _Sparks({required this.onPick});

  final ValueChanged<String> onPick;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final colors = context.lucid;
    final sparks = [l10n.createSparkNaples, l10n.createSparkCultivation, l10n.createSparkSalvage];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        FieldLabel(l10n.createSparkLabel, top: Space.lg),
        for (final spark in sparks)
          Padding(
            padding: const EdgeInsets.only(bottom: Space.sm),
            child: Material(
              color: Theme.of(context).colorScheme.surfaceContainerLow,
              borderRadius: Radii.card,
              child: InkWell(
                borderRadius: Radii.card,
                onTap: () => onPick(spark),
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: Space.lg, vertical: Space.md),
                  child: Row(
                    children: [
                      ExcludeSemantics(
                        child: Icon(Icons.format_quote_rounded, size: 20, color: colors.accent),
                      ),
                      const SizedBox(width: Space.md),
                      Expanded(
                        child: Text(
                          spark,
                          style: context.lucidText.playerAction.copyWith(
                            fontSize: 15,
                            color: colors.textSecondary,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
      ],
    );
  }
}

/// The advanced choices, folded away until asked for (G1). Rules come with the draft and are
/// edited in its review.
class _AdvancedChoices extends StatelessWidget {
  const _AdvancedChoices({
    required this.open,
    required this.onToggle,
    required this.physics,
    required this.gift,
    required this.difficulty,
    required this.events,
    required this.onPhysics,
    required this.onGift,
    required this.onDifficulty,
    required this.onEvents,
  });

  final bool open;
  final VoidCallback onToggle;
  final Physics physics;

  /// Null leaves it to the premise: a starter with time stop drafts it, and one without doesn't.
  final GiftStrength? gift;
  final Difficulty difficulty;
  final EventFrequency events;
  final ValueChanged<Physics> onPhysics;
  final ValueChanged<GiftStrength> onGift;
  final ValueChanged<Difficulty> onDifficulty;
  final ValueChanged<EventFrequency> onEvents;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final theme = Theme.of(context);
    final colors = context.lucid;
    final scheme = theme.colorScheme;
    return DecoratedBox(
      decoration: BoxDecoration(
        borderRadius: Radii.card,
        border: Border.all(color: scheme.outlineVariant),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Semantics(
            expanded: open,
            button: true,
            child: InkWell(
              borderRadius: Radii.card,
              onTap: onToggle,
              child: Padding(
                padding: const EdgeInsets.all(Space.lg),
                child: Row(
                  children: [
                    ExcludeSemantics(child: Icon(Icons.tune_rounded, color: colors.textSecondary)),
                    const SizedBox(width: Space.md),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(l10n.createAdvancedLabel, style: theme.textTheme.titleMedium),
                          const SizedBox(height: Space.xxs),
                          Text(
                            l10n.createAdvancedBody,
                            style: theme.textTheme.bodySmall!.copyWith(color: colors.textSecondary),
                          ),
                        ],
                      ),
                    ),
                    AnimatedRotation(
                      turns: open ? 0.5 : 0,
                      duration: Motion.of(context, Motion.base),
                      child: Icon(Icons.expand_more_rounded, color: colors.textMuted),
                    ),
                  ],
                ),
              ),
            ),
          ),
          AnimatedSize(
            duration: Motion.of(context, Motion.slow),
            curve: Motion.standard,
            alignment: Alignment.topCenter,
            child: open
                ? Padding(
                    padding: const EdgeInsets.fromLTRB(Space.lg, 0, Space.lg, Space.lg),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        ChoiceField<Physics>(
                          label: l10n.physicsLabel,
                          values: Physics.values,
                          value: physics,
                          labelOf: l10n.physics,
                          bodyOf: l10n.physicsBody,
                          onChanged: onPhysics,
                        ),
                        if (gift case final gift?)
                          ChoiceField<GiftStrength>(
                            label: l10n.giftLabel,
                            values: GiftStrength.values,
                            value: gift,
                            labelOf: l10n.gift,
                            bodyOf: l10n.giftBody,
                            onChanged: onGift,
                          )
                        else
                          _GiftPicker(onGift: onGift),
                        ChoiceField<Difficulty>(
                          label: l10n.difficultyLabel,
                          values: Difficulty.values,
                          value: difficulty,
                          labelOf: l10n.difficulty,
                          bodyOf: l10n.difficultyBody,
                          onChanged: onDifficulty,
                        ),
                        ChoiceField<EventFrequency>(
                          label: l10n.eventsLabel,
                          values: EventFrequency.values,
                          value: events,
                          labelOf: l10n.events,
                          bodyOf: l10n.eventsBody,
                          onChanged: onEvents,
                        ),
                      ],
                    ),
                  )
                : const SizedBox(width: double.infinity),
          ),
        ],
      ),
    );
  }
}

/// The gift before the player picks one: left to the premise, so nothing is chosen yet.
class _GiftPicker extends StatelessWidget {
  const _GiftPicker({required this.onGift});

  final ValueChanged<GiftStrength> onGift;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        FieldLabel(l10n.giftLabel),
        Wrap(
          spacing: Space.sm,
          runSpacing: Space.sm,
          children: [
            for (final gift in GiftStrength.values)
              ChoiceChip(
                label: Text(l10n.gift(gift)),
                selected: false,
                showCheckmark: false,
                onSelected: (_) => onGift(gift),
              ),
          ],
        ),
        const SizedBox(height: Space.sm),
        Text(
          l10n.giftFromPremise,
          style: Theme.of(
            context,
          ).textTheme.bodyMedium!.copyWith(color: context.lucid.textSecondary),
        ),
      ],
    );
  }
}

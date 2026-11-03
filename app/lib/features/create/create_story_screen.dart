import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/l10n.dart';
import '../../core/navigation.dart';
import '../../design/design.dart';
import '../account/account_repository.dart';
import '../discover/premises.dart';
import '../library/library.dart';
import 'create_flow.dart';
import 'draft.dart';
import 'draft_repository.dart';
import 'draft_review.dart';
import 'draft_widgets.dart';
import 'drafting_view.dart';
import 'premise_step.dart';

/// A new story (G1, G2, S1): a premise from Discover or the player's own idea, then the drafted
/// world and character to review, change and start. Starting opens the play screen, which plays
/// the opening scene.
class CreateStoryScreen extends ConsumerStatefulWidget {
  const CreateStoryScreen({super.key, this.premise, this.premiseId});

  /// The starter, when Discover passed it along.
  final Premise? premise;

  /// The starter's id, from the link, for when the starter itself didn't come along (a reload).
  final String? premiseId;

  @override
  ConsumerState<CreateStoryScreen> createState() => _CreateStoryScreenState();
}

class _CreateStoryScreenState extends ConsumerState<CreateStoryScreen> {
  late final _flow = CreateFlow(
    ref.read(draftRepositoryProvider),
    // Drafting spends credits: the balance shown elsewhere is read again (K2).
    onCharged: () {
      if (mounted) ref.read(meProvider.notifier).refreshQuietly();
    },
  );

  /// The premise step's words and choices, kept here so a failed draft returns to them.
  PremiseForm? _form;

  @override
  void dispose() {
    _flow.dispose();
    _form?.dispose();
    super.dispose();
  }

  /// Back from a link with nothing under it goes to Discover, asking first like a pop would.
  Widget? _back(BuildContext context) {
    if (GoRouter.of(context).canPop()) return null;
    return BackButton(
      onPressed: () async {
        if (_flow.hasUnsavedDraft && !await _confirmLeave()) return;
        if (context.mounted) context.go('/discover');
      },
    );
  }

  /// Drafts what the premise step holds. Out of credits offers the player's own key, and drafts
  /// again on it once they add one (K2, K6).
  Future<void> _draft(Premise? starter) async {
    final form = _form!;
    final text = form.text.text.trim();
    // The starter's own words go by id, so the draft keeps them word for word.
    final own = starter == null || normalizeLine(text) != normalizeLine(starter.premise);
    await _flow.create(
      premise: own ? text : null,
      premiseId: starter?.id,
      quote: text,
      rating: ref.read(maxRatingProvider) == Rating.teen ? Rating.teen : form.rating,
      choices: DraftChoices(
        physics: form.physics,
        giftStrength: form.gift,
        difficulty: form.difficulty,
        eventFrequency: form.events,
      ),
    );
    if (mounted && await offerOwnKey(context, _flow.error) && mounted) await _draft(starter);
  }

  Future<void> _start() async {
    final storyId = await _flow.start();
    if (storyId == null || !mounted) return;
    ref.invalidate(storiesProvider);
    context.pushReplacement('/story/${Uri.encodeComponent(storyId)}');
  }

  Future<bool> _confirmLeave() async {
    final l10n = context.l10n;
    final leave = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(l10n.reviewLeaveTitle),
        content: Text(l10n.reviewLeaveBody),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: Text(l10n.reviewLeaveStay),
          ),
          TextButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: Text(l10n.reviewLeave),
          ),
        ],
      ),
    );
    return leave ?? false;
  }

  @override
  Widget build(BuildContext context) {
    final id = widget.premise?.id ?? widget.premiseId;
    if (widget.premise == null && id != null) {
      // Opened from a link: find the starter first. An unknown one starts from a blank page.
      return ref
          .watch(premiseProvider(id))
          .when(
            skipLoadingOnRefresh: true,
            data: (starter) => _screen(context, starter),
            error: (_, _) => _screen(context, null),
            loading: () => _Loading(label: context.l10n.createLoadingStarter),
          );
    }
    return _screen(context, widget.premise);
  }

  Widget _screen(BuildContext context, Premise? starter) {
    final l10n = context.l10n;
    return ListenableBuilder(
      listenable: _flow,
      builder: (context, _) {
        final stage = _flow.stage;
        final genre = _flow.draft?.genre ?? starter?.genre;
        return PopScope(
          canPop: !_flow.hasUnsavedDraft,
          onPopInvokedWithResult: (didPop, _) async {
            if (didPop) return;
            final navigator = Navigator.of(context);
            if (await _confirmLeave()) navigator.pop();
          },
          child: StoryTheme(
            genre: genre,
            child: Builder(
              builder: (context) => Scaffold(
                appBar: AppBar(
                  leading: _back(context),
                  title: Text(switch (stage) {
                    CreateStage.review => l10n.reviewTitle,
                    _ when starter != null => l10n.createStartTitle,
                    _ => l10n.createNewTitle,
                  }),
                ),
                body: SafeArea(
                  bottom: stage != CreateStage.review,
                  child: AnimatedSwitcher(
                    duration: Motion.of(context, Motion.slow),
                    switchInCurve: Motion.standard,
                    switchOutCurve: Motion.exit,
                    child: switch (stage) {
                      CreateStage.premise => PremiseStep(
                        key: const ValueKey(CreateStage.premise),
                        flow: _flow,
                        form: _form ??= PremiseForm(premise: starter?.premise),
                        onDraft: () => _draft(starter),
                        starter: starter,
                      ),
                      CreateStage.drafting => DraftingView(
                        key: const ValueKey(CreateStage.drafting),
                        premise: _flow.draftingPremise ?? '',
                      ),
                      CreateStage.review => DraftReview(
                        key: const ValueKey(CreateStage.review),
                        flow: _flow,
                        starter: starter,
                      ),
                    },
                  ),
                ),
                bottomNavigationBar: stage == CreateStage.review
                    ? StartBar(flow: _flow, onStart: _start)
                    : null,
              ),
            ),
          ),
        );
      },
    );
  }
}

class _Loading extends StatelessWidget {
  const _Loading({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(leading: backOr(context, '/discover')),
    body: Semantics(
      label: label,
      child: const ContentColumn.reading(
        child: Padding(
          padding: EdgeInsets.all(Space.gutter),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              SkeletonBox(height: 180, radius: Radii.md),
              SizedBox(height: Space.xl),
              SkeletonText(lines: 4),
            ],
          ),
        ),
      ),
    ),
  );
}

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api/api_error_text.dart';
import '../../core/l10n.dart';
import '../../core/navigation.dart';
import '../../design/design.dart';
import '../story/story_models.dart';
import '../story/story_repository.dart';
import '../voice/dictation_button.dart';
import '../voice/input_mode.dart';

/// Starts a new story, from a Discover premise or the player's own idea, which they can type or
/// dictate (V1). The create work (WS15) turns this into the drafting flow (G1, G2).
class CreateStoryScreen extends ConsumerStatefulWidget {
  const CreateStoryScreen({super.key, this.premise});

  final Premise? premise;

  @override
  ConsumerState<CreateStoryScreen> createState() => _CreateStoryScreenState();
}

class _CreateStoryScreenState extends ConsumerState<CreateStoryScreen> {
  late final _title = TextEditingController(text: widget.premise?.title);
  late final _premise = TextEditingController(text: widget.premise?.premise);
  late final _premiseMode = InputModeTracker(_premise);
  bool _busy = false;
  Object? _error;

  @override
  void dispose() {
    _premiseMode.dispose();
    _title.dispose();
    _premise.dispose();
    super.dispose();
  }

  Future<void> _start() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final story = await ref
          .read(storyRepositoryProvider)
          .create(premise: _premise.text.trim(), title: _title.text.trim());
      ref.invalidate(storiesProvider);
      if (mounted) context.pushReplacement('/story/${story.id}', extra: story);
    } catch (e) {
      if (mounted) setState(() => _error = e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final theme = Theme.of(context);
    final colors = context.lucid;
    final premise = widget.premise;
    return StoryTheme(
      genre: premise?.genre,
      child: Builder(
        builder: (context) => Scaffold(
          appBar: AppBar(
            leading: backOr(context, '/discover'),
            title: Text(premise == null ? l10n.createNewTitle : l10n.createStartTitle),
          ),
          body: SafeArea(
            child: ListView(
              padding: const EdgeInsets.fromLTRB(Space.gutter, Space.sm, Space.gutter, Space.xxl),
              children: [
                ContentColumn.reading(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      if (premise != null) ...[
                        PictureSlot(
                          status: premise.coverUrl == null
                              ? PictureStatus.skipped
                              : PictureStatus.ready,
                          url: premise.coverUrl,
                          aspectRatio: 21 / 9,
                        ),
                        const SizedBox(height: Space.xl),
                        Text(premise.genre.toUpperCase(), style: context.lucidText.overline),
                        const SizedBox(height: Space.xs),
                      ],
                      Text(
                        premise?.title ?? l10n.createHeading,
                        style: theme.textTheme.headlineLarge,
                      ),
                      const SizedBox(height: Space.sm),
                      Text(
                        premise?.tagline ?? l10n.createSubheading,
                        style: theme.textTheme.bodyLarge!.copyWith(color: colors.textSecondary),
                      ),
                      const SizedBox(height: Space.xl),
                      TextField(
                        controller: _premise,
                        minLines: 5,
                        maxLines: 12,
                        textCapitalization: TextCapitalization.sentences,
                        style: context.lucidText.narration.copyWith(fontSize: 17),
                        decoration: InputDecoration(
                          labelText: l10n.createPremiseLabel,
                          hintText: l10n.createPremiseHint,
                          alignLabelWithHint: true,
                          suffixIcon: Align(
                            alignment: Alignment.topRight,
                            widthFactor: 1,
                            heightFactor: 1,
                            child: DictationButton(tracker: _premiseMode),
                          ),
                        ),
                      ),
                      const SizedBox(height: Space.lg),
                      TextField(
                        controller: _title,
                        textCapitalization: TextCapitalization.words,
                        decoration: InputDecoration(labelText: l10n.createTitleLabel),
                      ),
                      if (_error case final error?) ...[
                        const SizedBox(height: Space.lg),
                        Text(
                          describeError(l10n, error).message,
                          style: theme.textTheme.bodyMedium!.copyWith(
                            color: theme.colorScheme.error,
                          ),
                        ),
                      ],
                      const SizedBox(height: Space.xl),
                      ListenableBuilder(
                        listenable: _premise,
                        builder: (context, _) {
                          final short = _premise.text.trim().length < 10;
                          return Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              FilledButton.icon(
                                onPressed: _busy || short ? null : _start,
                                icon: _busy
                                    ? SizedBox.square(
                                        dimension: 18,
                                        child: CircularProgressIndicator(
                                          strokeWidth: 2,
                                          color: colors.onAccent,
                                        ),
                                      )
                                    : const Icon(Icons.play_arrow_rounded),
                                label: Text(l10n.createBegin),
                              ),
                              if (short && _premise.text.isNotEmpty) ...[
                                const SizedBox(height: Space.sm),
                                Text(
                                  l10n.createTooShort,
                                  textAlign: TextAlign.center,
                                  style: theme.textTheme.bodySmall,
                                ),
                              ],
                            ],
                          );
                        },
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

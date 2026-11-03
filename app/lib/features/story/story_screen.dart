import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/async_value_view.dart';
import 'story_models.dart';
import 'story_repository.dart';

/// The play screen: the scene feed, the offered choices and a free-text action box.
class StoryScreen extends ConsumerStatefulWidget {
  const StoryScreen({super.key, required this.storyId, this.initialStory});

  final String storyId;

  /// Passed when navigating straight from story creation, to skip a fetch.
  final Story? initialStory;

  @override
  ConsumerState<StoryScreen> createState() => _StoryScreenState();
}

class _StoryScreenState extends ConsumerState<StoryScreen> {
  final _action = TextEditingController();
  final _scroll = ScrollController();
  late Story? _story = widget.initialStory;
  Object? _loadError;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    if (_story == null) _load();
  }

  @override
  void dispose() {
    _action.dispose();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() => _loadError = null);
    try {
      final story = await ref.read(storyRepositoryProvider).get(widget.storyId);
      if (mounted) setState(() => _story = story);
    } catch (e) {
      if (mounted) setState(() => _loadError = e);
    }
  }

  Future<void> _takeTurn({String? choiceId, String? action}) async {
    setState(() => _busy = true);
    try {
      final turn = await ref
          .read(storyRepositoryProvider)
          .takeTurn(widget.storyId, choiceId: choiceId, action: action);
      if (!mounted) return;
      setState(() => _story = _story!.withTurn(turn));
      _action.clear();
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (_scroll.hasClients) {
          _scroll.animateTo(
            _scroll.position.maxScrollExtent,
            duration: const Duration(milliseconds: 300),
            curve: Curves.easeOut,
          );
        }
      });
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$e')));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final story = _story;
    return Scaffold(
      appBar: AppBar(
        title: Text(story?.title ?? 'Story'),
        actions: [
          IconButton(
            tooltip: 'Memory',
            icon: const Icon(Icons.psychology_outlined),
            onPressed: () => context.push('/story/${widget.storyId}/memory'),
          ),
        ],
      ),
      body: switch ((story, _loadError)) {
        (null, final Object error) => ErrorView(message: '$error', onRetry: _load),
        (null, _) => const Center(child: CircularProgressIndicator()),
        (final Story story, _) => Column(
          children: [
            Expanded(
              child: ListView.builder(
                controller: _scroll,
                padding: const EdgeInsets.all(16),
                itemCount: story.scenes.length,
                itemBuilder: (_, i) => _SceneView(scene: story.scenes[i]),
              ),
            ),
            if (_busy) const LinearProgressIndicator(),
            _ActionBar(
              choices: story.scenes.isEmpty ? const [] : story.scenes.last.choices,
              controller: _action,
              enabled: !_busy,
              onChoice: (choice) => _takeTurn(choiceId: choice.id),
              onAction: (text) => _takeTurn(action: text),
            ),
          ],
        ),
      },
    );
  }
}

class _SceneView extends StatelessWidget {
  const _SceneView({required this.scene});

  final Scene scene;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: 24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (scene.playerAction case final action?)
            Align(
              alignment: Alignment.centerRight,
              child: Container(
                margin: const EdgeInsets.only(bottom: 12, left: 48),
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                decoration: BoxDecoration(
                  color: theme.colorScheme.primaryContainer,
                  borderRadius: BorderRadius.circular(16),
                ),
                child: Text(action, style: TextStyle(color: theme.colorScheme.onPrimaryContainer)),
              ),
            ),
          if (scene.imageUrl case final url?)
            Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(12),
                child: Image.network(url, fit: BoxFit.cover),
              ),
            ),
          Text(scene.narration, style: theme.textTheme.bodyLarge?.copyWith(height: 1.5)),
        ],
      ),
    );
  }
}

class _ActionBar extends StatelessWidget {
  const _ActionBar({
    required this.choices,
    required this.controller,
    required this.enabled,
    required this.onChoice,
    required this.onAction,
  });

  final List<Choice> choices;
  final TextEditingController controller;
  final bool enabled;
  final ValueChanged<Choice> onChoice;
  final ValueChanged<String> onAction;

  void _submit() {
    final text = controller.text.trim();
    if (text.isNotEmpty) onAction(text);
  }

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Theme.of(context).colorScheme.surfaceContainer,
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(12, 8, 12, 8),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              for (final choice in choices)
                Padding(
                  padding: const EdgeInsets.only(bottom: 6),
                  child: OutlinedButton(
                    onPressed: enabled ? () => onChoice(choice) : null,
                    child: Text(choice.label, textAlign: TextAlign.center),
                  ),
                ),
              TextField(
                controller: controller,
                enabled: enabled,
                textInputAction: TextInputAction.send,
                onSubmitted: (_) => _submit(),
                decoration: InputDecoration(
                  hintText: 'Or do something else…',
                  suffixIcon: IconButton(
                    icon: const Icon(Icons.send),
                    onPressed: enabled ? _submit : null,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

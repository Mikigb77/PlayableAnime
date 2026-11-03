import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../story/story_models.dart';
import '../story/story_repository.dart';

/// Starts a new story, either from a Discover premise or from the user's own idea.
class CreateStoryScreen extends ConsumerStatefulWidget {
  const CreateStoryScreen({super.key, this.premise});

  final Premise? premise;

  @override
  ConsumerState<CreateStoryScreen> createState() => _CreateStoryScreenState();
}

class _CreateStoryScreenState extends ConsumerState<CreateStoryScreen> {
  late final _title = TextEditingController(text: widget.premise?.title);
  late final _premise = TextEditingController(text: widget.premise?.premise);
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
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
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(widget.premise == null ? 'New story' : 'Start story')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          TextField(
            controller: _title,
            decoration: const InputDecoration(labelText: 'Title (optional)'),
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _premise,
            minLines: 5,
            maxLines: 12,
            decoration: const InputDecoration(
              labelText: 'Premise',
              hintText: 'Who are you, where are you, and what is about to go wrong?',
              alignLabelWithHint: true,
            ),
          ),
          if (_error != null) ...[
            const SizedBox(height: 12),
            Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
          ],
          const SizedBox(height: 24),
          ListenableBuilder(
            listenable: _premise,
            builder: (context, _) => FilledButton.icon(
              onPressed: _busy || _premise.text.trim().length < 10 ? null : _start,
              icon: _busy
                  ? const SizedBox.square(
                      dimension: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.play_arrow),
              label: const Text('Begin'),
            ),
          ),
        ],
      ),
    );
  }
}

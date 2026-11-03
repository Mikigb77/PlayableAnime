import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/async_value_view.dart';
import 'story_models.dart';
import 'story_repository.dart';

/// What the story remembers: summary, goals, characters, factions and pinned facts.
class MemoryScreen extends ConsumerWidget {
  const MemoryScreen({super.key, required this.storyId});

  final String storyId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Scaffold(
      appBar: AppBar(title: const Text('Memory')),
      body: AsyncValueView(
        value: ref.watch(memoryProvider(storyId)),
        onRetry: () => ref.invalidate(memoryProvider(storyId)),
        builder: (state) => ListView(
          padding: const EdgeInsets.only(bottom: 24),
          children: [
            _Section('Story so far', [
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: Text(state.summary.isEmpty ? 'Nothing yet.' : state.summary),
              ),
            ]),
            _Section('Goals', [
              for (final goal in state.goals)
                ListTile(leading: const Icon(Icons.flag_outlined), title: Text(goal)),
            ]),
            _Section('Characters', [for (final c in state.characters) _CharacterTile(c)]),
            _Section('Factions', [
              for (final f in state.factions)
                ListTile(
                  leading: const Icon(Icons.shield_outlined),
                  title: Text(f.name),
                  subtitle: f.description.isEmpty ? null : Text(f.description),
                  trailing: Text(f.stance),
                ),
            ]),
            _Section('Facts', [
              for (final fact in state.facts.reversed)
                ListTile(
                  dense: true,
                  leading: _IconValue(Icons.star_rounded, fact.importance),
                  title: Text(fact.text),
                  trailing: Text('T${fact.turn}'),
                ),
            ]),
          ],
        ),
      ),
    );
  }
}

class _CharacterTile extends StatelessWidget {
  const _CharacterTile(this.character);

  final Character character;

  @override
  Widget build(BuildContext context) {
    final dead = character.isDead;
    return ListTile(
      leading: Icon(dead ? Icons.heart_broken_outlined : Icons.person_outline),
      title: Text(
        character.name,
        style: dead ? const TextStyle(decoration: TextDecoration.lineThrough) : null,
      ),
      subtitle: character.description.isEmpty ? null : Text(character.description),
      trailing: dead ? const Text('dead') : _IconValue(Icons.favorite, character.affinity),
    );
  }
}

/// A small icon followed by a number, e.g. a heart with an affinity score.
class _IconValue extends StatelessWidget {
  const _IconValue(this.icon, this.value);

  final IconData icon;
  final int value;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [Icon(icon, size: 16), const SizedBox(width: 4), Text('$value')],
    );
  }
}

class _Section extends StatelessWidget {
  const _Section(this.title, this.children);

  final String title;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 20, 16, 8),
          child: Text(title, style: Theme.of(context).textTheme.titleMedium),
        ),
        if (children.isEmpty)
          const Padding(padding: EdgeInsets.symmetric(horizontal: 16), child: Text('—'))
        else
          ...children,
      ],
    );
  }
}

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/l10n.dart';
import '../../core/names.dart';
import '../../design/design.dart';
import 'memory.dart';

/// What the character knows, in the world's words (C6, G16): who they are, the people, places
/// and factions they have met, their goals and leads, rumors marked unconfirmed, their own deeds
/// and who saw them, and the story's threads (N1). The server sends only what the character
/// knows, so nothing here can spoil the story.
class MemoryScreen extends ConsumerStatefulWidget {
  const MemoryScreen({super.key, required this.storyId, this.accent});

  final String storyId;

  /// The story's accent (its genre's, or the one the player chose, S13) when the play screen
  /// opened this page. The app's own otherwise.
  final GenreAccent? accent;

  @override
  ConsumerState<MemoryScreen> createState() => _MemoryScreenState();
}

class _MemoryScreenState extends ConsumerState<MemoryScreen> {
  /// The one group shown, or every group when null.
  MemorySection? _only;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final memory = memoryProvider(widget.storyId);
    return StoryTheme.accent(
      accent: widget.accent ?? GenreAccent.lucid,
      child: Scaffold(
        appBar: AppBar(title: Text(l10n.memoryTitle)),
        body: AsyncValueView(
          value: ref.watch(memory),
          onRetry: () => ref.invalidate(memory),
          builder: (view) {
            final sections = view.sections;
            final only = sections.contains(_only) ? _only : null;
            return RefreshIndicator(
              onRefresh: () => ref.refresh(memory.future),
              child: ListView(
                padding: const EdgeInsets.only(bottom: Space.xxxl),
                children: [
                  ContentColumn.reading(
                    child: Padding(
                      padding: const EdgeInsets.fromLTRB(Space.gutter, 0, Space.gutter, Space.lg),
                      child: Text(
                        l10n.memorySubtitle,
                        style: Theme.of(
                          context,
                        ).textTheme.bodyLarge!.copyWith(color: context.lucid.textSecondary),
                      ),
                    ),
                  ),
                  if (view.character case final character?)
                    ContentColumn.reading(child: _CharacterCard(character: character)),
                  if (sections.isEmpty)
                    EmptyState(
                      icon: Icons.menu_book_outlined,
                      title: l10n.memoryEmptyTitle,
                      message: l10n.memoryEmptyBody,
                    )
                  else ...[
                    if (sections.length > 1)
                      _Filters(
                        sections: sections,
                        view: view,
                        selected: only,
                        onSelected: (section) => setState(() => _only = section),
                      ),
                    for (final section in sections)
                      if (only == null || only == section)
                        ContentColumn.reading(
                          child: _Section(section: section, view: view),
                        ),
                  ],
                ],
              ),
            );
          },
        ),
      ),
    );
  }
}

String _sectionTitle(AppLocalizations l10n, MemorySection section) => switch (section) {
  MemorySection.people => l10n.memoryPeople,
  MemorySection.places => l10n.memoryPlaces,
  MemorySection.factions => l10n.memoryFactions,
  MemorySection.goals => l10n.memoryGoals,
  MemorySection.rumors => l10n.memoryRumors,
  MemorySection.deeds => l10n.memoryDeeds,
  MemorySection.threads => l10n.memoryThreads,
};

/// Chips to show one group at a time. They scroll sideways on a narrow screen.
class _Filters extends StatelessWidget {
  const _Filters({
    required this.sections,
    required this.view,
    required this.selected,
    required this.onSelected,
  });

  final List<MemorySection> sections;
  final MemoryView view;
  final MemorySection? selected;
  final ValueChanged<MemorySection?> onSelected;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    Widget chip(String label, MemorySection? section) => Padding(
      padding: const EdgeInsets.only(right: Space.sm),
      child: ChoiceChip(
        label: Text(label),
        selected: selected == section,
        showCheckmark: false,
        onSelected: (_) => onSelected(section),
      ),
    );
    return Align(
      alignment: Alignment.topCenter,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: Layout.readingWidth),
        child: SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          padding: const EdgeInsets.fromLTRB(Space.gutter, Space.lg, Space.gutter, 0),
          child: Row(
            children: [
              chip(l10n.memoryAll, null),
              for (final section in sections)
                chip('${_sectionTitle(l10n, section)} ${view.count(section)}', section),
            ],
          ),
        ),
      ),
    );
  }
}

/// The player character as they know themselves, in the world's words (G16).
class _CharacterCard extends StatelessWidget {
  const _CharacterCard({required this.character});

  final MemoryCharacter character;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = context.lucid;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: Space.gutter),
      child: Card(
        margin: EdgeInsets.zero,
        child: Padding(
          padding: const EdgeInsets.all(Space.lg),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  PortraitAvatar(
                    name: character.name,
                    url: character.portraitUrl,
                    size: 64,
                    ring: true,
                  ),
                  const SizedBox(width: Space.lg),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          context.l10n.memoryYou.toUpperCase(),
                          style: context.lucidText.overline.copyWith(color: colors.accent),
                        ),
                        const SizedBox(height: Space.xxs),
                        Semantics(
                          header: true,
                          child: Text(
                            character.name.asHeading,
                            style: theme.textTheme.headlineSmall,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              if (character.lines.isNotEmpty) const SizedBox(height: Space.md),
              for (final line in character.lines)
                Padding(
                  padding: const EdgeInsets.only(top: Space.xs),
                  child: Text(
                    line,
                    style: context.lucidText.narration.copyWith(fontSize: 16, height: 1.5),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Section extends StatelessWidget {
  const _Section({required this.section, required this.view});

  final MemorySection section;
  final MemoryView view;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final entries = switch (section) {
      MemorySection.people => [for (final p in view.people) _PersonEntry(person: p)],
      MemorySection.places => [for (final p in view.places) _PlaceEntry(place: p)],
      MemorySection.factions => [for (final f in view.factions) _FactionEntry(faction: f)],
      MemorySection.goals => [
        for (final goal in view.goals)
          _NoteEntry(note: goal, icon: Icons.flag_outlined, kind: l10n.memoryGoal),
        for (final lead in view.leads)
          _NoteEntry(note: lead, icon: Icons.explore_outlined, kind: l10n.memoryLead),
      ],
      MemorySection.rumors => [
        for (final rumor in view.rumors)
          _NoteEntry(note: rumor, icon: Icons.hearing_outlined, unconfirmed: true),
      ],
      MemorySection.deeds => [
        for (final deed in view.deeds) _NoteEntry(note: deed, icon: Icons.history_edu_outlined),
      ],
      MemorySection.threads => [for (final t in view.threads) _ThreadEntry(thread: t)],
    };
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [SectionLabel(_sectionTitle(l10n, section)), ...entries],
    );
  }
}

/// An entry's frame: a leading mark, the title, a label on the right and the lines below.
class _Entry extends StatelessWidget {
  const _Entry({
    required this.leading,
    required this.title,
    this.titleStyle,
    this.tag,
    this.trailing,
    this.lines = const [],
    this.footer,
  });

  final Widget leading;
  final String title;
  final TextStyle? titleStyle;

  /// A short state next to the title, such as "Presumed dead".
  final String? tag;
  final String? trailing;
  final List<String> lines;
  final Widget? footer;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = context.lucid;
    return MergeSemantics(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: Space.gutter, vertical: Space.sm),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            leading,
            const SizedBox(width: Space.md),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Wrap(
                    spacing: Space.sm,
                    runSpacing: Space.xxs,
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: [
                      Text(title, style: titleStyle ?? theme.textTheme.titleMedium),
                      if (tag case final tag?) _Tag(tag),
                    ],
                  ),
                  if (trailing case final trailing?) ...[
                    const SizedBox(height: Space.xxs),
                    Text(trailing, style: context.lucidText.meta.copyWith(color: colors.accent)),
                  ],
                  for (final line in lines)
                    Padding(
                      padding: const EdgeInsets.only(top: Space.xxs),
                      child: Text(
                        line,
                        style: theme.textTheme.bodyMedium!.copyWith(color: colors.textSecondary),
                      ),
                    ),
                  ?footer,
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _Tag extends StatelessWidget {
  const _Tag(this.text, {this.color});

  final String text;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final colors = context.lucid;
    final tint = color ?? colors.textMuted;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: Space.sm, vertical: 2),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(Radii.pill),
        border: Border.all(color: tint.withValues(alpha: 0.6)),
      ),
      child: Text(text.toUpperCase(), style: context.lucidText.overline.copyWith(color: tint)),
    );
  }
}

/// A round mark for entries without a picture.
class _Mark extends StatelessWidget {
  const _Mark(this.icon, {this.size = 44});

  final IconData icon;
  final double size;

  @override
  Widget build(BuildContext context) => ExcludeSemantics(
    child: Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surfaceContainerHigh,
        borderRadius: BorderRadius.circular(Radii.md),
      ),
      child: Icon(icon, size: size * 0.48, color: context.lucid.textSecondary),
    ),
  );
}

class _PersonEntry extends StatelessWidget {
  const _PersonEntry({required this.person});

  final MemoryPerson person;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = context.lucid;
    final fate = person.fate;
    final gone = fate == Fate.dead || fate == Fate.presumedDead;
    return _Entry(
      leading: Opacity(
        opacity: gone ? 0.55 : 1,
        child: PortraitAvatar(name: person.name, url: person.portraitUrl, size: 44),
      ),
      title: person.name.asHeading,
      titleStyle: theme.textTheme.titleMedium!.copyWith(
        color: gone ? colors.textMuted : null,
        decoration: fate == Fate.dead ? TextDecoration.lineThrough : null,
        decorationColor: colors.textMuted,
      ),
      tag: fate == Fate.alive ? null : person.statusLabel,
      trailing: gone ? null : person.attitudeLabel,
      lines: person.lines,
    );
  }
}

class _PlaceEntry extends StatelessWidget {
  const _PlaceEntry({required this.place});

  final MemoryPlace place;

  @override
  Widget build(BuildContext context) {
    final dpr = MediaQuery.devicePixelRatioOf(context);
    final url = place.imageUrl;
    return _Entry(
      leading: url == null
          ? const _Mark(Icons.place_outlined)
          : ClipRRect(
              borderRadius: BorderRadius.circular(Radii.md),
              child: SizedBox(
                width: 64,
                height: 44,
                child: Image(
                  image: appImage(url, cacheWidth: (64 * dpr).round()),
                  fit: BoxFit.cover,
                  excludeFromSemantics: true,
                  errorBuilder: (_, _, _) => const _Mark(Icons.place_outlined),
                ),
              ),
            ),
      title: place.name.asHeading,
      lines: place.lines,
    );
  }
}

class _FactionEntry extends StatelessWidget {
  const _FactionEntry({required this.faction});

  final MemoryFaction faction;

  @override
  Widget build(BuildContext context) => _Entry(
    leading: const _Mark(Icons.shield_outlined),
    title: faction.name.asHeading,
    trailing: faction.standingLabel.isEmpty ? null : faction.standingLabel,
    lines: faction.lines,
  );
}

class _NoteEntry extends StatelessWidget {
  const _NoteEntry({required this.note, required this.icon, this.kind, this.unconfirmed = false});

  final MemoryNote note;
  final IconData icon;

  /// Goal or lead, where both share a group.
  final String? kind;

  /// Rumors are never confirmed here (C6): the character only heard them.
  final bool unconfirmed;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = context.lucid;
    return _Entry(
      leading: _Mark(icon, size: 36),
      title: note.text,
      titleStyle: unconfirmed
          ? context.lucidText.playerAction.copyWith(color: colors.textPrimary)
          : theme.textTheme.bodyLarge,
      tag: kind,
      lines: const [],
      footer: Padding(
        padding: const EdgeInsets.only(top: Space.xxs),
        child: Wrap(
          spacing: Space.sm,
          runSpacing: Space.xxs,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            if (unconfirmed) _Tag(context.l10n.memoryUnconfirmed, color: colors.caution),
            if (note.labels.isNotEmpty)
              Text(
                note.labels.join(' · '),
                style: context.lucidText.meta.copyWith(color: colors.textSecondary),
              ),
          ],
        ),
      ),
    );
  }
}

class _ThreadEntry extends StatelessWidget {
  const _ThreadEntry({required this.thread});

  final MemoryThread thread;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final theme = Theme.of(context);
    final colors = context.lucid;
    final status = thread.status;
    final label = switch (status) {
      ThreadStatus.open => l10n.threadOpen,
      ThreadStatus.dormant => l10n.threadDormant,
      ThreadStatus.resolved => l10n.threadResolved,
      ThreadStatus.failed => l10n.threadFailed,
      ThreadStatus.abandoned => l10n.threadAbandoned,
      ThreadStatus.resolvedWithoutPlayer => l10n.threadResolvedWithoutPlayer,
    };
    return _Entry(
      leading: _Mark(status.isClosed ? Icons.check_rounded : Icons.timeline_rounded, size: 36),
      title: thread.title,
      titleStyle: theme.textTheme.bodyLarge!.copyWith(
        color: status.isClosed ? colors.textMuted : null,
      ),
      tag: label,
    );
  }
}

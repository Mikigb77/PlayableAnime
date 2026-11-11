import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/l10n.dart';
import '../../core/names.dart';
import '../../design/design.dart';
import 'memory.dart';
import 'record_widgets.dart';

/// What the character knows, in the world's words (C6, G16), a group at a time: what they are
/// after (their goals, the leads on offer and the story's threads, N1), the people they know
/// and how each takes them, where they stand with the world's factions, the places they have
/// been, what they have heard, marked unconfirmed unless they know for themselves whether it
/// is so, and what was done and who saw it. The server sends only what the character knows,
/// so nothing here can spoil the story.
class MemoryScreen extends ConsumerStatefulWidget {
  const MemoryScreen({super.key, required this.storyId, this.accent});

  final String storyId;

  /// The story's accent (its genre's, or the one the player chose, S13) when the play screen
  /// opened this page. The app's own otherwise.
  final GenreAccent? accent;

  /// How many entries a group shows among the others. Alone, or opened, it shows them all.
  static const glance = 5;

  @override
  ConsumerState<MemoryScreen> createState() => _MemoryScreenState();
}

class _MemoryScreenState extends ConsumerState<MemoryScreen> {
  /// The one group shown, or every group when null.
  MemorySection? _only;

  /// The groups opened in full among the others.
  final _opened = <MemorySection>{};

  /// Whether the threads that ended are shown.
  bool _closedShown = false;

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
              // Each entry is a child of the list, so a long story builds only what is in view.
              child: ListView(
                physics: const AlwaysScrollableScrollPhysics(),
                padding: const EdgeInsets.only(bottom: Space.xxxl),
                children: [
                  _Gutter(
                    child: Padding(
                      padding: const EdgeInsets.only(bottom: Space.lg),
                      child: Text(
                        l10n.memorySubtitle,
                        style: Theme.of(
                          context,
                        ).textTheme.bodyLarge!.copyWith(color: context.lucid.textSecondary),
                      ),
                    ),
                  ),
                  if (view.character case final character?)
                    _Gutter(child: _CharacterCard(character: character)),
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
                      if (only == null || only == section) ...[
                        ContentColumn.reading(child: SectionLabel(_sectionTitle(l10n, section))),
                        ..._entries(
                          view,
                          section,
                          whole:
                              only == section || sections.length == 1 || _opened.contains(section),
                        ),
                      ],
                  ],
                ],
              ),
            );
          },
        ),
      ),
    );
  }

  /// A group's entries, each a row of the page. Among the other groups it shows its first
  /// few and a way to the rest.
  List<Widget> _entries(MemoryView view, MemorySection section, {required bool whole}) {
    final l10n = context.l10n;
    final List<Widget> entries;
    switch (section) {
      case MemorySection.objectives:
        // Never cut short: what they are after is all of it wanted at a glance.
        return _objectives(view);
      case MemorySection.people:
        entries = [for (final person in view.people) _PersonEntry(person: person)];
      case MemorySection.factions:
        entries = [for (final faction in view.factions) _FactionEntry(faction: faction)];
      case MemorySection.places:
        entries = [for (final place in view.places) _PlaceEntry(place: place)];
      // The server sends what was heard and what was done oldest first. The latest leads here.
      case MemorySection.rumors:
        entries = [for (final rumor in view.rumors.reversed) _RumorEntry(rumor: rumor)];
      case MemorySection.deeds:
        entries = [for (final deed in view.deeds.reversed) _DeedEntry(deed: deed)];
    }
    final shown = whole ? entries : entries.take(MemoryScreen.glance);
    return [
      for (final entry in shown) _Gutter(child: entry),
      if (shown.length < entries.length)
        _Gutter(
          child: Align(
            alignment: AlignmentDirectional.centerStart,
            child: TextButton.icon(
              key: ValueKey('memory.more.${section.name}'),
              onPressed: () => setState(() => _opened.add(section)),
              icon: const Icon(Icons.expand_more_rounded, size: 20),
              label: Text(l10n.memoryShowAll(entries.length)),
            ),
          ),
        ),
    ];
  }

  /// What the character is after: what they set themselves, what is on offer, and the story's
  /// threads still running (N1), with the ones that ended folded away under them.
  List<Widget> _objectives(MemoryView view) {
    final l10n = context.l10n;
    final open = view.openThreads.toList();
    final closed = view.closedThreads.toList();
    final groups = <(String, List<Widget>)>[
      if (view.goals.isNotEmpty)
        (l10n.memoryGoals, [for (final goal in view.goals) _GoalEntry(goal: goal)]),
      if (view.leads.isNotEmpty)
        (l10n.memoryLeads, [for (final lead in view.leads) _LeadEntry(lead: lead)]),
      if (open.isNotEmpty)
        (l10n.memoryThreads, [for (final thread in open) _ThreadEntry(thread: thread)]),
    ];
    return [
      for (final (i, (label, entries)) in groups.indexed) ...[
        _Gutter(child: RecordGroupLabel(label, first: i == 0)),
        for (final entry in entries) _Gutter(child: entry),
      ],
      if (closed.isNotEmpty) ...[
        _Gutter(
          child: _Fold(
            label: l10n.memoryClosed,
            count: closed.length,
            open: _closedShown,
            onTap: () => setState(() => _closedShown = !_closedShown),
          ),
        ),
        if (_closedShown)
          for (final thread in closed) _Gutter(child: _ThreadEntry(thread: thread)),
      ],
    ];
  }
}

String _sectionTitle(AppLocalizations l10n, MemorySection section) => switch (section) {
  MemorySection.objectives => l10n.memoryObjectives,
  MemorySection.people => l10n.memoryPeople,
  MemorySection.factions => l10n.memoryFactions,
  MemorySection.places => l10n.memoryPlaces,
  MemorySection.rumors => l10n.memoryRumors,
  MemorySection.deeds => l10n.memoryDeeds,
};

/// A row of the page: in the reading column, clear of the screen's edges.
class _Gutter extends StatelessWidget {
  const _Gutter({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) => ContentColumn.reading(
    child: Padding(
      padding: const EdgeInsets.symmetric(horizontal: Space.gutter),
      child: child,
    ),
  );
}

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
    return RecordCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              PortraitAvatar(
                name: character.name,
                url: character.portraitUrl,
                size: 56,
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
                      child: Text(character.name.asHeading, style: theme.textTheme.headlineSmall),
                    ),
                  ],
                ),
              ),
            ],
          ),
          if (character.lines.isNotEmpty) const SizedBox(height: Space.sm),
          for (final line in character.lines) RecordLine(line),
        ],
      ),
    );
  }
}

/// A line under an entry with a small mark before it: until when, since when, who saw.
class _Note extends StatelessWidget {
  const _Note(this.text, {this.icon, this.color});

  final String text;
  final IconData? icon;

  /// The mark's color and the words'. Quiet without one.
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final tint = color ?? context.lucid.textMuted;
    return Padding(
      padding: const EdgeInsets.only(top: Space.xs),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (icon case final icon?) ...[
            // Level with the first line of the words, at any text size.
            Padding(
              padding: const EdgeInsets.only(top: 1),
              child: ExcludeSemantics(child: Icon(icon, size: 15, color: tint)),
            ),
            const SizedBox(width: 6),
          ],
          Flexible(
            child: Text(text, style: context.lucidText.meta.copyWith(color: tint)),
          ),
        ],
      ),
    );
  }
}

/// A header that folds what is under it away: its name, how many it holds, and which way it
/// is turned.
class _Fold extends StatelessWidget {
  const _Fold({required this.label, required this.count, required this.open, required this.onTap});

  final String label;
  final int count;
  final bool open;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = context.lucid;
    return Padding(
      padding: const EdgeInsets.only(top: Space.xs, bottom: Space.xs),
      child: Semantics(
        button: true,
        expanded: open,
        child: InkWell(
          key: const ValueKey('memory.closed'),
          onTap: onTap,
          borderRadius: BorderRadius.circular(Radii.md),
          child: ConstrainedBox(
            constraints: const BoxConstraints(minHeight: Layout.minTouch),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: Space.xs),
              child: Row(
                children: [
                  Icon(
                    open ? Icons.expand_less_rounded : Icons.expand_more_rounded,
                    size: 20,
                    color: colors.textSecondary,
                  ),
                  const SizedBox(width: Space.sm),
                  Expanded(
                    child: Text(
                      label,
                      style: theme.textTheme.labelLarge!.copyWith(color: colors.textSecondary),
                    ),
                  ),
                  Text('$count', style: context.lucidText.meta),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Something the character means to do (N2).
class _GoalEntry extends StatelessWidget {
  const _GoalEntry({required this.goal});

  final MemoryGoal goal;

  @override
  Widget build(BuildContext context) =>
      RecordEntry(icon: Icons.flag_outlined, lit: true, title: goal.text);
}

/// Something on offer (W13), and until when where it runs out.
class _LeadEntry extends StatelessWidget {
  const _LeadEntry({required this.lead});

  final MemoryLead lead;

  @override
  Widget build(BuildContext context) => RecordEntry(
    icon: Icons.explore_outlined,
    title: lead.text,
    titleStyle: Theme.of(context).textTheme.bodyLarge,
    children: [
      if (lead.expiresLabel case final expires?)
        _Note(expires, icon: Icons.schedule_rounded, color: context.lucid.caution),
    ],
  );
}

/// One of the story's threads (N1): running, quiet for now, or how it ended.
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
      ThreadStatus.open => null,
      ThreadStatus.dormant => l10n.threadDormant,
      ThreadStatus.resolved => l10n.threadResolved,
      ThreadStatus.failed => l10n.threadFailed,
      ThreadStatus.abandoned => l10n.threadAbandoned,
      ThreadStatus.resolvedWithoutPlayer => l10n.threadResolvedWithoutPlayer,
    };
    final icon = switch (status) {
      ThreadStatus.open || ThreadStatus.dormant => Icons.timeline_rounded,
      ThreadStatus.resolved || ThreadStatus.resolvedWithoutPlayer => Icons.check_rounded,
      ThreadStatus.failed => Icons.close_rounded,
      ThreadStatus.abandoned => Icons.remove_rounded,
    };
    return RecordEntry(
      icon: icon,
      title: thread.title,
      titleStyle: theme.textTheme.titleMedium!.copyWith(
        color: status.isClosed ? colors.textMuted : null,
      ),
      trailing: label == null
          ? null
          : RecordKind(
              label,
              color: switch (status) {
                ThreadStatus.resolved => colors.success,
                ThreadStatus.failed => colors.danger,
                _ => null,
              },
            ),
    );
  }
}

/// Someone the character knows: how they take them, whether they live as far as the
/// character knows (C1), and what is known of them.
class _PersonEntry extends StatelessWidget {
  const _PersonEntry({required this.person});

  final MemoryPerson person;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = context.lucid;
    final fate = person.fate;
    final gone = fate == Fate.dead || fate == Fate.presumedDead;
    final tone = switch (person.attitude) {
      Attitude.warm || Attitude.friendly => colors.success,
      Attitude.cold => colors.caution,
      Attitude.hostile => colors.danger,
      Attitude.neutral || null => null,
    };
    return RecordEntry(
      // Their name follows, so the portrait says nothing of its own to a screen reader.
      leading: ExcludeSemantics(
        child: Opacity(
          opacity: gone ? 0.55 : 1,
          child: PortraitAvatar(name: person.name, url: person.portraitUrl, size: 44),
        ),
      ),
      title: person.name.asHeading,
      titleStyle: theme.textTheme.titleMedium!.copyWith(
        color: gone ? colors.textMuted : null,
        decoration: fate == Fate.dead ? TextDecoration.lineThrough : null,
        decorationColor: colors.textMuted,
      ),
      tag: fate == Fate.alive || person.statusLabel.isEmpty
          ? null
          : RecordKind(person.statusLabel, color: gone ? null : colors.caution),
      // How the dead took them is no longer how things stand.
      trailing: switch (person.attitudeLabel) {
        final attitude? when !gone => RecordChip(attitude, tone: tone),
        _ => null,
      },
      children: [for (final line in person.lines) RecordLine(line)],
    );
  }
}

/// A faction the character knows of, and where they stand with it (W3).
class _FactionEntry extends StatelessWidget {
  const _FactionEntry({required this.faction});

  final MemoryFaction faction;

  @override
  Widget build(BuildContext context) {
    final colors = context.lucid;
    final tone = switch (faction.esteem) {
      Esteem.admired || Esteem.respected => colors.success,
      Esteem.disliked => colors.caution,
      Esteem.despised => colors.danger,
      // Fear alone is no friend's regard.
      Esteem.neutral => faction.feared ? colors.caution : null,
    };
    return RecordEntry(
      icon: Icons.shield_outlined,
      title: faction.name.asHeading,
      trailing: faction.standingLabel.isEmpty
          ? null
          : RecordChip(faction.standingLabel, tone: tone),
      children: [for (final line in faction.lines) RecordLine(line)],
    );
  }
}

/// A place the character has been or heard of, with its picture where it has one.
class _PlaceEntry extends StatelessWidget {
  const _PlaceEntry({required this.place});

  final MemoryPlace place;

  @override
  Widget build(BuildContext context) => RecordEntry(
    leading: _PlacePicture(url: place.imageUrl),
    title: place.name.asHeading,
    children: [for (final line in place.lines) RecordLine(line)],
  );
}

/// A place's picture, or a mark of the same size where it has none, so names line up.
class _PlacePicture extends StatelessWidget {
  const _PlacePicture({required this.url});

  final String? url;

  static const double _width = 56;
  static const double _height = 44;

  @override
  Widget build(BuildContext context) {
    final dpr = MediaQuery.devicePixelRatioOf(context);
    final mark = ColoredBox(
      color: Theme.of(context).colorScheme.surfaceContainerHigh,
      child: Icon(Icons.place_outlined, size: 20, color: context.lucid.textSecondary),
    );
    return ExcludeSemantics(
      child: ClipRRect(
        borderRadius: BorderRadius.circular(Radii.md),
        child: SizedBox(
          width: _width,
          height: _height,
          child: switch (url) {
            null => mark,
            final url => Image(
              image: appImage(url, cacheWidth: (_width * dpr).round()),
              fit: BoxFit.cover,
              errorBuilder: (_, _, _) => mark,
            ),
          },
        ),
      ),
    );
  }
}

/// Something people say (W2), set as talk, with what the character knows of it (C6) and when
/// it reached them.
class _RumorEntry extends StatelessWidget {
  const _RumorEntry({required this.rumor});

  final MemoryRumor rumor;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final colors = context.lucid;
    final (label, tone, icon) = switch (rumor.certainty) {
      RumorCertainty.unconfirmed => (
        l10n.memoryUnconfirmed,
        colors.caution,
        Icons.help_outline_rounded,
      ),
      RumorCertainty.confirmed => (l10n.memoryConfirmed, colors.success, Icons.check_rounded),
      RumorCertainty.wrong => (l10n.memoryFalse, colors.danger, Icons.close_rounded),
    };
    return RecordEntry(
      icon: Icons.format_quote_rounded,
      title: rumor.text,
      titleStyle: context.lucidText.playerAction.copyWith(color: colors.textPrimary),
      children: [
        Padding(
          padding: const EdgeInsets.only(top: Space.sm),
          child: Wrap(
            spacing: Space.md,
            runSpacing: Space.xs,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              RecordChip(label, tone: tone, icon: icon),
              if (rumor.heardLabel case final heard?)
                Text(heard, style: context.lucidText.meta.copyWith(color: colors.textMuted)),
            ],
          ),
        ),
      ],
    );
  }
}

/// Something done (W1): what, when, who saw it as far as the character knows (W2), and what
/// they know became of it since (W11, C6).
class _DeedEntry extends StatelessWidget {
  const _DeedEntry({required this.deed});

  final MemoryDeed deed;

  @override
  Widget build(BuildContext context) {
    final colors = context.lucid;
    return RecordEntry(
      // Someone else's deed is led in by how it reached the character.
      icon: switch (deed.seen) {
        DeedSeen.watched => Icons.visibility_outlined,
        DeedSeen.heardOf => Icons.hearing_outlined,
        _ => Icons.history_edu_outlined,
      },
      title: deed.text,
      titleStyle: Theme.of(context).textTheme.bodyLarge,
      children: [
        if (deed.whenLabel case final date?) _Note(date),
        if (deed.knownLabel case final known?)
          // Their own deed says who knows of it: lit where someone does.
          switch (deed.seen) {
            DeedSeen.seen => _Note(known, icon: Icons.visibility_outlined, color: colors.accent),
            DeedSeen.public => _Note(known, icon: Icons.groups_outlined, color: colors.accent),
            DeedSeen.unseen => _Note(known, icon: Icons.visibility_off_outlined),
            _ => _Note(known),
          },
        // What became of it since, as far as they know: lit where word is on its way or
        // someone came, quiet for what only closes a door.
        for (final line in deed.trail)
          switch (line.kind) {
            DeedTrailKind.went => _Note(
              line.text,
              icon: Icons.directions_run_rounded,
              color: colors.caution,
            ),
            DeedTrailKind.dead => _Note(line.text, icon: Icons.remove_circle_outline_rounded),
            DeedTrailKind.heard => _Note(line.text, icon: Icons.hearing_outlined),
            DeedTrailKind.came => _Note(
              line.text,
              icon: Icons.person_pin_circle_outlined,
              color: colors.accent,
            ),
            null => _Note(line.text),
          },
        if (deed.openLabel case final open?) _Note(open, icon: Icons.help_outline_rounded),
      ],
    );
  }
}

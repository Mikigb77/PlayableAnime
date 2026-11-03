import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import 'core/l10n.dart';
import 'design/design.dart';

/// The frame around the tabs: a bottom bar on phones, a side rail on wide screens.
class HomeShell extends StatelessWidget {
  const HomeShell({super.key, required this.shell});

  final StatefulNavigationShell shell;

  void _go(int index) => shell.goBranch(index, initialLocation: index == shell.currentIndex);

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final destinations = [
      (Icons.explore_outlined, Icons.explore, l10n.navDiscover),
      (Icons.auto_stories_outlined, Icons.auto_stories, l10n.navLibrary),
      (Icons.person_outline_rounded, Icons.person_rounded, l10n.navAccount),
    ];
    final wide = MediaQuery.sizeOf(context).width >= Layout.railBreakpoint;
    if (wide) {
      return Scaffold(
        body: Row(
          children: [
            NavigationRail(
              selectedIndex: shell.currentIndex,
              onDestinationSelected: _go,
              labelType: NavigationRailLabelType.all,
              groupAlignment: -0.85,
              leading: Padding(
                padding: const EdgeInsets.symmetric(vertical: Space.lg),
                child: ExcludeSemantics(
                  child: Icon(Icons.auto_awesome_rounded, size: 28, color: context.lucid.accent),
                ),
              ),
              destinations: [
                for (final (icon, selected, label) in destinations)
                  NavigationRailDestination(
                    icon: Icon(icon),
                    selectedIcon: Icon(selected),
                    label: Text(label),
                  ),
              ],
            ),
            VerticalDivider(width: 1, color: Theme.of(context).colorScheme.outlineVariant),
            Expanded(child: shell),
          ],
        ),
      );
    }
    return Scaffold(
      body: shell,
      bottomNavigationBar: DecoratedBox(
        decoration: BoxDecoration(
          border: Border(top: BorderSide(color: Theme.of(context).colorScheme.outlineVariant)),
        ),
        child: NavigationBar(
          selectedIndex: shell.currentIndex,
          onDestinationSelected: _go,
          destinations: [
            for (final (icon, selected, label) in destinations)
              NavigationDestination(icon: Icon(icon), selectedIcon: Icon(selected), label: label),
          ],
        ),
      ),
    );
  }
}

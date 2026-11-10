import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import 'core/l10n.dart';
import 'design/design.dart';
import 'features/update/update_banner.dart';

/// The frame around the tabs: on phones a bar of glass that floats over the page, on wide
/// screens a side rail under the app's mark, with the app's update offer just above the bar or
/// at the bottom of the page (S12).
///
/// On a phone a tab's page runs on behind the bar, so each tab ends its scroll with a
/// [PageEnd], which leaves the bar's height free.
class HomeShell extends StatelessWidget {
  const HomeShell({super.key, required this.shell});

  final StatefulNavigationShell shell;

  void _go(int index) => shell.goBranch(index, initialLocation: index == shell.currentIndex);

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final tabs = [
      LucidTab(icon: Icons.explore_outlined, selectedIcon: Icons.explore, label: l10n.navDiscover),
      LucidTab(
        icon: Icons.auto_stories_outlined,
        selectedIcon: Icons.auto_stories,
        label: l10n.navLibrary,
      ),
      LucidTab(
        icon: Icons.person_outline_rounded,
        selectedIcon: Icons.person_rounded,
        label: l10n.navAccount,
      ),
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
              leading: const Padding(
                padding: EdgeInsets.symmetric(vertical: Space.lg),
                child: BrandMark(size: 36, showName: false),
              ),
              destinations: [
                for (final tab in tabs)
                  NavigationRailDestination(
                    icon: Icon(tab.icon),
                    selectedIcon: Icon(tab.selectedIcon),
                    label: Text(tab.label),
                  ),
              ],
            ),
            VerticalDivider(width: 1, color: context.lucid.hairline),
            Expanded(
              child: Column(
                children: [
                  Expanded(child: shell),
                  const SafeArea(top: false, child: UpdateBanner()),
                ],
              ),
            ),
          ],
        ),
      );
    }
    return Scaffold(
      // The page shows through the glass.
      extendBody: true,
      body: shell,
      bottomNavigationBar: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const UpdateBanner(),
          LucidTabBar(tabs: tabs, selected: shell.currentIndex, onSelected: _go),
        ],
      ),
    );
  }
}

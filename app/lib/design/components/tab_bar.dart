import 'package:flutter/material.dart';

import '../motion.dart';
import '../theme.dart';
import '../tokens.dart';
import 'glass.dart';

/// One of the app's tabs.
@immutable
class LucidTab {
  const LucidTab({required this.icon, required this.selectedIcon, required this.label});

  final IconData icon;
  final IconData selectedIcon;
  final String label;
}

/// The tabs at the bottom of a phone: a pill of [Glass] that floats over the page, with the tab
/// the player is on lit in the accent. Every tab shows its name when there is room. On a narrow
/// phone, in a long language or at a large text size, the tabs draw closer first, in two steps,
/// and then only the lit one keeps its name; the others stay as icons. Every tab is named for
/// screen readers and on a long press.
class LucidTabBar extends StatelessWidget {
  const LucidTabBar({
    super.key,
    required this.tabs,
    required this.selected,
    required this.onSelected,
  });

  final List<LucidTab> tabs;
  final int selected;
  final ValueChanged<int> onSelected;

  static const _margin = Layout.barInset;
  static const _inner = 6.0;
  static const _icon = 22.0;

  /// The line around a tab, which its shape adds to its width on each side.
  static const _edge = 1.0;

  /// How strong the accent is at the bright end of the lit tab's own light.
  static const litWash = 0.24;

  /// The color of the lit tab's icon and name: the end of the accent's gradient that reads on
  /// the tab's own light, bright at night and deep on paper.
  static Color litForeground(LucidColors colors, Brightness brightness) =>
      brightness == Brightness.dark ? colors.accentHi : colors.accentLo;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scaler = MediaQuery.textScalerOf(context);
    final style = theme.textTheme.labelLarge!.copyWith(fontSize: 14, height: 1.2);
    return SafeArea(
      top: false,
      minimum: const EdgeInsets.only(bottom: Space.md),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(_margin, 0, _margin, Space.xs),
        child: Center(
          heightFactor: 1,
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 420),
            child: Glass(
              padding: const EdgeInsets.all(_inner),
              child: LayoutBuilder(
                builder: (context, constraints) {
                  final icons = tabs.length * _icon;
                  double needs(_Fit fit) {
                    final names = style.copyWith(fontSize: fit.size);
                    var labels = 0.0;
                    for (final tab in tabs) {
                      labels += _width(tab.label, names, scaler, context);
                    }
                    return labels +
                        icons +
                        tabs.length * (fit.gap + _edge * 2) +
                        (tabs.length - 1) * fit.side * 2 +
                        fit.side +
                        fit.litEnd;
                  }

                  final fit = _Fit.named.firstWhere(
                    (fit) => needs(fit) <= constraints.maxWidth,
                    orElse: () => _Fit.iconsOnly,
                  );
                  return Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      for (final (i, tab) in tabs.indexed)
                        // The lit tab keeps its name even when the others lose theirs, and
                        // gives way last: a name too long for the room left ends in an ellipsis.
                        Flexible(
                          flex: i == selected ? 1 : 0,
                          child: _TabButton(
                            tab: tab,
                            lit: i == selected,
                            fit: fit,
                            style: style,
                            onTap: () => onSelected(i),
                          ),
                        ),
                    ],
                  );
                },
              ),
            ),
          ),
        ),
      ),
    );
  }

  static double _width(String text, TextStyle style, TextScaler scaler, BuildContext context) {
    final painter = TextPainter(
      text: TextSpan(text: text, style: style),
      textDirection: Directionality.of(context),
      textScaler: scaler,
      maxLines: 1,
    )..layout();
    final width = painter.width;
    painter.dispose();
    return width + 1;
  }
}

/// How closely the tabs sit: the gap between an icon and its name, the room at a tab's sides,
/// the wider end of the lit tab, and the size of the names.
enum _Fit {
  roomy(gap: 8, side: 14, litEnd: 18, size: 14),
  close(gap: 6, side: 10, litEnd: 14, size: 14),
  tight(gap: 5, side: 7, litEnd: 10, size: 13),
  iconsOnly(gap: 6, side: 12, litEnd: 16, size: 14);

  const _Fit({required this.gap, required this.side, required this.litEnd, required this.size});

  final double gap;
  final double side;
  final double litEnd;
  final double size;

  /// The fits that name every tab, from the most room to the least.
  static const named = [roomy, close, tight];
}

class _TabButton extends StatelessWidget {
  const _TabButton({
    required this.tab,
    required this.lit,
    required this.fit,
    required this.style,
    required this.onTap,
  });

  final LucidTab tab;
  final bool lit;
  final _Fit fit;
  final TextStyle style;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final colors = context.lucid;
    final named = lit || fit != _Fit.iconsOnly;
    final foreground = lit
        ? LucidTabBar.litForeground(colors, Theme.of(context).brightness)
        : colors.textMuted;
    final button = Semantics(
      button: true,
      selected: lit,
      label: tab.label,
      // The name replaces the icon and the words, so the tap is given again here.
      onTap: onTap,
      excludeSemantics: true,
      child: InkWell(
        onTap: onTap,
        customBorder: const StadiumBorder(),
        child: AnimatedContainer(
          duration: Motion.of(context, Motion.base),
          curve: Motion.standard,
          constraints: const BoxConstraints(minHeight: 52, minWidth: Layout.minTouch),
          padding: EdgeInsets.only(left: fit.side, right: lit && named ? fit.litEnd : fit.side),
          decoration: ShapeDecoration(
            shape: StadiumBorder(
              side: BorderSide(color: colors.accent.withValues(alpha: lit ? 0.4 : 0)),
            ),
            gradient: LinearGradient(
              begin: Alignment.centerLeft,
              end: Alignment.centerRight,
              colors: [
                colors.accent.withValues(alpha: lit ? LucidTabBar.litWash : 0),
                colors.accent.withValues(alpha: lit ? 0.1 : 0),
              ],
            ),
            shadows: [
              if (lit) BoxShadow(color: colors.accent.withValues(alpha: 0.14), blurRadius: 24),
            ],
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(lit ? tab.selectedIcon : tab.icon, size: LucidTabBar._icon, color: foreground),
              if (named) ...[
                SizedBox(width: fit.gap),
                Flexible(
                  child: Text(
                    tab.label,
                    maxLines: 1,
                    softWrap: false,
                    overflow: TextOverflow.ellipsis,
                    style: style.copyWith(fontSize: fit.size, color: foreground),
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
    // The name on hover and on a long press, as a navigation bar gives it. A screen reader has
    // it from the button already.
    return Tooltip(message: tab.label, excludeFromSemantics: true, child: button);
  }
}

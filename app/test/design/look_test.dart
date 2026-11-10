import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:playable_anime/design/design.dart';

import '../helpers.dart';

/// The pieces the app's look is made of: gold lettering, glass, the night air, the way a page
/// arrives, the drop capital that opens a story, and the small things that sit beside it.
void main() {
  group('GradientText', () {
    const headline = 'The story never ends.';
    const style = TextStyle(fontSize: 20, height: 1.2);

    int linesAt(double width) {
      final painter = TextPainter(
        text: const TextSpan(text: headline, style: style),
        textDirection: TextDirection.ltr,
      )..layout(maxWidth: width);
      final lines = painter.computeLineMetrics().length;
      painter.dispose();
      return lines;
    }

    testWidgets('draws its words through the accent\'s gradient', (tester) async {
      await tester.pumpWidget(wrap(const Center(child: GradientText(headline, style: style))));
      expect(find.byType(ShaderMask), findsOneWidget);
      // The letters are only a mask, so the gradient shows at full strength.
      expect(tester.widget<Text>(find.text(headline)).style!.color, const Color(0xFFFFFFFF));
      // A little room under the words, so the mask keeps the tails of g and y.
      expect(
        tester.getSize(find.byType(ShaderMask)).height,
        greaterThan(tester.getSize(find.text(headline)).height),
      );
    });

    testWidgets('a balanced headline breaks into lines of like length', (tester) async {
      late BuildContext context;
      await tester.pumpWidget(
        wrap(
          Builder(
            builder: (c) {
              context = c;
              return const SizedBox();
            },
          ),
        ),
      );
      // In the test font every letter is as wide as the text's size: at 300 px the last word
      // would sit alone on its line.
      final width = balancedWidth(context, headline, style, 300);
      expect(width, lessThan(260));
      expect(linesAt(width), 2);
      expect(linesAt(width), linesAt(300));
      // Nothing to balance on one line, or with no edge to break at.
      expect(balancedWidth(context, 'Short', style, 300), 300);
      expect(balancedWidth(context, headline, style, double.infinity), double.infinity);
    });

    testWidgets('balanced lettering takes only the width it was balanced to', (tester) async {
      await tester.pumpWidget(
        wrap(
          const Align(
            alignment: Alignment.topLeft,
            child: SizedBox(
              width: 300,
              child: Align(
                alignment: Alignment.topLeft,
                child: GradientText(headline, style: style, balanced: true),
              ),
            ),
          ),
        ),
      );
      final words = tester.renderObject<RenderParagraph>(find.text(headline));
      expect(words.size.width, lessThan(260));
      expect(words.size.height, moreOrLessEquals(2 * 20 * 1.2, epsilon: 1));
      expect(tester.takeException(), isNull);
    });
  });

  group('Glass', () {
    testWidgets('blurs what lies behind it, and not where nothing does', (tester) async {
      await tester.pumpWidget(wrap(const Center(child: Glass(child: Text('Tabs')))));
      expect(find.byType(BackdropFilter), findsOneWidget);
      await tester.pumpWidget(wrap(const Center(child: Glass(blur: 0, child: Text('Box')))));
      expect(find.byType(BackdropFilter), findsNothing);
      expect(find.text('Box'), findsOneWidget);
    });

    testWidgets('its edge takes another color, as the action box does with focus', (tester) async {
      const gold = Color(0xFFE8C36A);
      await tester.pumpWidget(
        wrap(
          const Center(
            child: Glass(borderColor: gold, glow: gold, child: Text('Box')),
          ),
        ),
      );
      final box = tester.widget<DecoratedBox>(
        find.ancestor(of: find.text('Box'), matching: find.byType(DecoratedBox)).first,
      );
      expect(((box.decoration as BoxDecoration).border! as Border).top.color, gold);
    });

    group('GlassTopBar', () {
      Widget bar({Brightness brightness = Brightness.dark, double textScale = 1}) => wrap(
        Align(
          alignment: Alignment.topCenter,
          child: SizedBox(
            height: GlassTopBar.extent,
            child: GlassTopBar(
              leading: const BackButton(),
              title: const Text(
                'The Last Outer Disciple of the Ninth Peak',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
              actions: [IconButton(onPressed: () {}, icon: const Icon(Icons.tune_rounded))],
            ),
          ),
        ),
        brightness: brightness,
        textScale: textScale,
      );

      testWidgets('keeps its height at twice the text size', (tester) async {
        usePhone(tester);
        await tester.pumpWidget(bar(textScale: 2));
        expect(tester.takeException(), isNull);
        expect(tester.getSize(find.byType(GlassTopBar)).height, GlassTopBar.extent);
        // Its words grow only as far as they fit.
        final title = tester.element(find.textContaining('Outer Disciple'));
        expect(MediaQuery.textScalerOf(title).scale(10), moreOrLessEquals(13));
        // And nothing else on the page is held back.
        expect(MediaQuery.textScalerOf(tester.element(find.byType(GlassTopBar))).scale(10), 20);
      });

      testWidgets('sets the status bar\'s icons to read on the page', (tester) async {
        for (final (brightness, style) in [
          (Brightness.dark, SystemUiOverlayStyle.light),
          (Brightness.light, SystemUiOverlayStyle.dark),
        ]) {
          await tester.pumpWidget(bar(brightness: brightness));
          // The theme glides from one to the other.
          await tester.pump(const Duration(milliseconds: 400));
          final region = tester.widget<AnnotatedRegion<SystemUiOverlayStyle>>(
            find.descendant(
              of: find.byType(GlassTopBar),
              matching: find.byType(AnnotatedRegion<SystemUiOverlayStyle>),
            ),
          );
          expect(region.value, style);
        }
      });

      testWidgets('the page under its fade still takes taps beside the bar', (tester) async {
        usePhone(tester);
        var taps = 0;
        await tester.pumpWidget(
          wrap(
            Stack(
              children: [
                Positioned.fill(child: GestureDetector(onTap: () => taps++)),
                const Positioned(
                  top: 0,
                  left: 0,
                  right: 0,
                  height: GlassTopBar.extent,
                  child: GlassTopBar(title: Text('Story')),
                ),
              ],
            ),
          ),
        );
        // The bar's own gap, above the glass: the fade there is only paint.
        await tester.tapAt(const Offset(195, 1));
        expect(taps, 1);
      });
    });
  });

  group('Ambient', () {
    testWidgets('drifts, and holds still with reduced motion', (tester) async {
      await tester.pumpWidget(wrap(const SizedBox.expand(child: Ambient())));
      await tester.pump(const Duration(milliseconds: 100));
      expect(tester.binding.transientCallbackCount, greaterThan(0));

      await tester.pumpWidget(wrap(const SizedBox.expand(child: Ambient()), reduceMotion: true));
      await tester.pump(const Duration(milliseconds: 100));
      expect(tester.binding.transientCallbackCount, 0);
      expect(tester.takeException(), isNull);
    });

    testWidgets('takes no taps and says nothing to a screen reader', (tester) async {
      var taps = 0;
      await tester.pumpWidget(
        wrap(
          Stack(
            children: [
              Center(
                child: FilledButton(onPressed: () => taps++, child: const Text('Begin')),
              ),
              const Positioned.fill(child: Ambient(motes: Ambient.forest, glow: null)),
            ],
          ),
        ),
      );
      await tester.tap(find.text('Begin'));
      expect(taps, 1);
      expect(
        find.descendant(of: find.byType(Ambient), matching: find.byType(ExcludeSemantics)),
        findsOneWidget,
      );
    });

    testWidgets('paints in both themes without a picture behind it', (tester) async {
      for (final brightness in Brightness.values) {
        await tester.pumpWidget(
          wrap(const SizedBox.expand(child: Ambient(strength: 0.5)), brightness: brightness),
        );
        await tester.pump(const Duration(seconds: 1));
        expect(tester.takeException(), isNull);
      }
    });
  });

  group('RiseIn', () {
    double opacityOf(WidgetTester tester, String text) => tester
        .widget<FadeTransition>(
          find.ancestor(of: find.text(text), matching: find.byType(FadeTransition)).first,
        )
        .opacity
        .value;

    testWidgets('fades a part of the page in, from the top down', (tester) async {
      await tester.pumpWidget(
        wrap(
          const Column(
            children: [
              RiseIn(child: Text('First')),
              RiseIn(order: 4, child: Text('Later')),
            ],
          ),
        ),
      );
      expect(opacityOf(tester, 'First'), 0);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 120));
      // The first is on its way while the later one still waits its turn.
      expect(opacityOf(tester, 'First'), greaterThan(0));
      expect(opacityOf(tester, 'Later'), 0);
      await tester.pump(Motion.rise + Motion.riseStagger * 4);
      expect(opacityOf(tester, 'First'), 1);
      expect(opacityOf(tester, 'Later'), 1);
    });

    testWidgets('with reduced motion everything is simply there', (tester) async {
      await tester.pumpWidget(
        wrap(const RiseIn(order: 3, child: Text('Here')), reduceMotion: true),
      );
      expect(opacityOf(tester, 'Here'), 1);
      expect(tester.binding.transientCallbackCount, 0);
    });
  });

  group('DropCapParagraph', () {
    const opening =
        'Above the sea of clouds the ninth peak wakes, and the bells of the outer court answer '
        'it one by one, as they have every dawn since the mountain was raised.';
    const body = TextStyle(fontSize: 16, height: 1.5);

    Widget paragraph(String text, {double width = 360, double textScale = 1}) => wrap(
      Align(
        alignment: Alignment.topLeft,
        child: SizedBox(
          width: width,
          child: DefaultTextStyle(
            style: body,
            child: DropCapParagraph(
              spans: [TextSpan(text: text)],
              style: body,
            ),
          ),
        ),
      ),
      textScale: textScale,
      scroll: true,
    );

    /// The paragraph's own lines of text, without the capital.
    List<RenderParagraph> words(WidgetTester tester) => [
      for (final element
          in find
              .descendant(of: find.byType(DropCapParagraph), matching: find.byType(RichText))
              .evaluate())
        if (find
            .ancestor(of: find.byWidget(element.widget), matching: find.byType(GradientText))
            .evaluate()
            .isEmpty)
          element.renderObject! as RenderParagraph,
    ];

    testWidgets('sets the first letter beside two lines, and the rest under it', (tester) async {
      await tester.pumpWidget(paragraph(opening));
      expect(tester.takeException(), isNull);
      final capital = tester.widget<GradientText>(find.byType(GradientText));
      expect(capital.text, 'A');
      // Tall enough to stand beside two lines of the words.
      expect(capital.style.fontSize, greaterThan(16 * 2.5));

      final [beside, under] = words(tester);
      expect(beside.text.toPlainText() + under.text.toPlainText(), opening.substring(1));
      expect(beside.size.height, moreOrLessEquals(2 * 16 * 1.5, epsilon: 1));
      // The words under the capital run the full width of the column again.
      final left = tester.getTopLeft(find.byType(DropCapParagraph)).dx;
      expect(under.localToGlobal(Offset.zero).dx, left);
      expect(beside.localToGlobal(Offset.zero).dx, greaterThan(left + 40));
      expect(
        under.localToGlobal(Offset.zero).dy,
        moreOrLessEquals(beside.localToGlobal(Offset.zero).dy + beside.size.height, epsilon: 1),
      );
      // No word is split between the two.
      expect(beside.text.toPlainText(), endsWith(' '));
    });

    testWidgets('a screen reader hears the paragraph whole', (tester) async {
      final handle = tester.ensureSemantics();
      await tester.pumpWidget(paragraph(opening));
      expect(find.bySemanticsLabel(opening), findsOneWidget);
      expect(find.bySemanticsLabel('A'), findsNothing);
      handle.dispose();
    });

    testWidgets('a short paragraph ends beside its capital', (tester) async {
      await tester.pumpWidget(paragraph('Dawn, at last.'));
      expect(tester.widget<GradientText>(find.byType(GradientText)).text, 'D');
      final [beside] = words(tester);
      expect(beside.text.toPlainText(), 'awn, at last.');
      // The capital still has its two lines of room, so what follows doesn't run into it.
      expect(
        tester.getSize(find.byType(DropCapParagraph)).height,
        moreOrLessEquals(2 * 16 * 1.5, epsilon: 1),
      );
    });

    testWidgets('a paragraph that opens with speech keeps its mark and stays plain', (
      tester,
    ) async {
      const speech = '“Run,” she says, and the lamps go out along the whole street.';
      await tester.pumpWidget(paragraph(speech));
      expect(find.byType(GradientText), findsNothing);
      expect(words(tester).single.text.toPlainText(), speech);
    });

    test('only a letter or a digit is set as a capital, in any alphabet', () {
      expect(DropCapParagraph.fits('Above the clouds'), isTrue);
      expect(DropCapParagraph.fits('Élan'), isTrue);
      expect(DropCapParagraph.fits('Ñu'), isTrue);
      expect(DropCapParagraph.fits('7 days later'), isTrue);
      expect(DropCapParagraph.fits('“Run”'), isFalse);
      expect(DropCapParagraph.fits('¿Quién?'), isFalse);
      expect(DropCapParagraph.fits('— Corre.'), isFalse);
      expect(DropCapParagraph.fits(' A'), isFalse);
      expect(DropCapParagraph.fits(''), isFalse);
    });

    testWidgets('a column too narrow for words beside it leaves the paragraph plain', (
      tester,
    ) async {
      await tester.pumpWidget(paragraph(opening, width: 190));
      expect(find.byType(GradientText), findsNothing);
      expect(words(tester).single.text.toPlainText(), opening);
      expect(tester.takeException(), isNull);
    });

    testWidgets('fits at twice the text size', (tester) async {
      usePhone(tester);
      await tester.pumpWidget(paragraph(opening, textScale: 2));
      expect(tester.takeException(), isNull);
      // Whether or not the capital fits there, every word is still on the page.
      final shown = words(tester).map((p) => p.text.toPlainText()).join();
      expect(opening, endsWith(shown));
      expect(opening.length - shown.length, lessThanOrEqualTo(1));
    });

    testWidgets('NarrationText opens only its first paragraph with a capital', (tester) async {
      const text = 'The gate *opens* on a road of moonlight.\n\nNobody is waiting.';
      await tester.pumpWidget(
        wrap(const SizedBox(width: 360, child: NarrationText(text, dropCap: true)), scroll: true),
      );
      expect(find.byType(DropCapParagraph), findsOneWidget);
      expect(tester.widget<GradientText>(find.byType(GradientText)).text, 'T');
      final first = tester.widget<DropCapParagraph>(find.byType(DropCapParagraph));
      expect(
        TextSpan(children: first.spans).toPlainText(),
        'The gate opens on a road of moonlight.',
      );
      expect(find.textContaining('Nobody is waiting.', findRichText: true), findsOneWidget);

      // Any other scene reads as it always has.
      await tester.pumpWidget(
        wrap(const SizedBox(width: 360, child: NarrationText(text)), scroll: true),
      );
      expect(find.byType(DropCapParagraph), findsNothing);
      expect(find.textContaining('The gate opens', findRichText: true), findsOneWidget);
    });

    testWidgets('an opening still being written has its capital from its first words', (
      tester,
    ) async {
      Widget at(String text, {bool streaming = true}) => wrap(
        SizedBox(
          width: 360,
          child: StreamingNarration(text: text, streaming: streaming, dropCap: true),
        ),
        scroll: true,
      );
      await tester.pumpWidget(at('The gate'));
      expect(tester.widget<GradientText>(find.byType(GradientText)).text, 'T');
      await tester.pumpWidget(at('The gate opens on a road of moonlight.\n\nNobody'));
      await tester.pump(Motion.reveal * 2);
      expect(find.byType(DropCapParagraph), findsOneWidget);
      expect(find.textContaining('Nobody', findRichText: true), findsOneWidget);
      await tester.pumpWidget(
        at('The gate opens on a road of moonlight.\n\nNobody is waiting.', streaming: false),
      );
      await tester.pump(Motion.reveal * 2);
      expect(tester.takeException(), isNull);
      expect(find.textContaining('Nobody is waiting.', findRichText: true), findsOneWidget);
    });
  });

  group('page furniture', () {
    testWidgets('a page ends clear of whatever floats over its foot', (tester) async {
      await tester.pumpWidget(
        wrap(
          const MediaQuery(
            data: MediaQueryData(padding: EdgeInsets.only(bottom: 90)),
            child: Align(alignment: Alignment.topCenter, child: PageEnd()),
          ),
        ),
      );
      expect(tester.getSize(find.byType(PageEnd)).height, Space.xl + 90);
    });

    testWidgets('a headline in two lines is one heading, under the app\'s mark', (tester) async {
      final handle = tester.ensureSemantics();
      await tester.pumpWidget(
        wrap(
          const PageHeader(
            brand: true,
            title: 'Pick a world, or',
            accentTitle: 'dream up your own.',
          ),
          scroll: true,
        ),
      );
      final l10n = await english();
      expect(find.byType(BrandMark), findsOneWidget);
      expect(find.text(l10n.appTitle), findsOneWidget);
      expect(find.byType(GradientText), findsOneWidget);
      expect(
        tester.getSemantics(find.bySemanticsLabel('Pick a world, or dream up your own.')),
        isSemantics(isHeader: true),
      );
      handle.dispose();
    });

    testWidgets('a headline grows with the text size only as far as a line holds a word', (
      tester,
    ) async {
      usePhone(tester);
      await tester.pumpWidget(
        wrap(
          const PageHeader(title: 'Account', subtitle: 'Everything about you'),
          textScale: 2,
          scroll: true,
        ),
      );
      double scaleOf(String text) =>
          MediaQuery.textScalerOf(tester.element(find.text(text))).scale(10) / 10;
      expect(scaleOf('Account'), moreOrLessEquals(HeadlineScaling.maxScale));
      // The words under it are read at the size the player asked for.
      expect(scaleOf('Everything about you'), 2);
      expect(tester.takeException(), isNull);
    });

    testWidgets('a face\'s initials keep to their circle at any text size', (tester) async {
      await tester.pumpWidget(
        wrap(const Center(child: PortraitAvatar(name: 'Demo Player', size: 56)), textScale: 2),
      );
      final initials = tester.renderObject<RenderParagraph>(find.text('DP'));
      expect(initials.size.width, lessThan(56));
      expect(initials.size.height, lessThan(56));
    });

    testWidgets('on a wide screen the rail has the mark, so the headline stands alone', (
      tester,
    ) async {
      usePhone(tester, size: const Size(1280, 800));
      await tester.pumpWidget(wrap(const PageHeader(brand: true, title: 'Account'), scroll: true));
      expect(find.byType(BrandMark), findsNothing);
      expect(find.text('Account'), findsOneWidget);
    });

    testWidgets('the mark stands alone where the name has no room', (tester) async {
      await tester.pumpWidget(wrap(const Center(child: BrandMark(size: 36, showName: false))));
      final l10n = await english();
      expect(find.text(l10n.appTitle), findsNothing);
      expect(tester.getSize(find.byType(BrandMark)), const Size.square(36));
    });

    testWidgets('a ghost pill is a full touch target, and quiet when it has nothing to do', (
      tester,
    ) async {
      var taps = 0;
      Widget pill(VoidCallback? onPressed) => wrap(
        Center(
          child: GhostPill(label: 'Wait', icon: Icons.hourglass_empty, onPressed: onPressed),
        ),
      );
      await tester.pumpWidget(pill(() => taps++));
      expect(tester.getSize(find.byType(GhostPill)).height, greaterThanOrEqualTo(48));
      await tester.tap(find.text('Wait'));
      expect(taps, 1);

      await tester.pumpWidget(pill(null));
      await tester.tap(find.text('Wait'));
      expect(taps, 1);
      final colors = AppTheme.dark().extension<LucidColors>()!;
      expect(tester.widget<Text>(find.text('Wait')).style!.color, colors.textMuted);
    });

    testWidgets('a lit bead is a button with a name, or an ornament without one', (tester) async {
      final handle = tester.ensureSemantics();
      var sent = 0;
      await tester.pumpWidget(
        wrap(
          Center(
            child: AccentOrb(
              icon: Icons.arrow_upward_rounded,
              size: 42,
              tooltip: 'Send',
              onPressed: () => sent++,
            ),
          ),
        ),
      );
      expect(
        tester.getSemantics(find.bySemanticsLabel('Send')),
        isSemantics(isButton: true, isEnabled: true, hasTapAction: true),
      );
      // Smaller than a touch target, it is still tapped as one.
      expect(tester.getSize(find.byType(InkResponse)), const Size.square(48));
      await tester.tap(find.byTooltip('Send'));
      expect(sent, 1);

      // Unlit, it is there with nothing to do.
      await tester.pumpWidget(
        wrap(
          const Center(
            child: AccentOrb(icon: Icons.arrow_upward_rounded, tooltip: 'Send', lit: false),
          ),
        ),
      );
      await tester.pump(Motion.base);
      expect(
        tester.getSemantics(find.bySemanticsLabel('Send')),
        isSemantics(isButton: true, isEnabled: false),
      );

      // On something that is itself the button, it is only paint.
      await tester.pumpWidget(
        wrap(const Center(child: AccentOrb(icon: Icons.arrow_forward_rounded))),
      );
      expect(find.byType(InkResponse), findsNothing);
      expect(
        find.ancestor(of: find.byType(Icon), matching: find.byType(ExcludeSemantics)),
        findsWidgets,
      );
      handle.dispose();
    });

    testWidgets('a story\'s tile is a painting on night ink in both themes', (tester) async {
      for (final brightness in Brightness.values) {
        var opened = 0;
        await tester.pumpWidget(
          wrap(
            StoryTile(
              title: 'The Last Outer Disciple',
              genre: 'Cultivation',
              meta: 'Turn 12 · Day 3, dusk',
              onTap: () => opened++,
            ),
            brightness: brightness,
            scroll: true,
          ),
        );
        expect(
          tester.widget<Text>(find.text('The Last Outer Disciple')).style!.color,
          Palette.inkTextPrimary,
        );
        expect(
          tester.widget<Text>(find.text('CULTIVATION')).style!.color,
          accentFor(GenreAccent.jade, Brightness.dark),
        );
        // The way in is lit in the story's own color.
        expect(find.byType(AccentOrb), findsOneWidget);
        await tester.tap(find.text('The Last Outer Disciple'));
        expect(opened, 1);
        expect(tester.takeException(), isNull);
      }
    });

    testWidgets('a tile fills the height it is given, to match the one beside it', (tester) async {
      await tester.pumpWidget(
        wrap(
          const IntrinsicHeight(
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Expanded(
                  child: Align(
                    alignment: Alignment.topCenter,
                    child: StoryTile(title: 'Short', genre: 'Mystery', meta: 'Turn 1'),
                  ),
                ),
                Expanded(
                  child: StoryTile(
                    title: 'A story with a name long enough to take two lines of the tile',
                    genre: 'Mystery',
                    meta: 'Turn 2',
                  ),
                ),
              ],
            ),
          ),
          scroll: true,
        ),
      );
      final short = tester.getSize(find.widgetWithText(StoryTile, 'Short'));
      final long = tester.getSize(find.widgetWithText(StoryTile, 'Turn 2'));
      expect(short.height, long.height);
    });
  });
}

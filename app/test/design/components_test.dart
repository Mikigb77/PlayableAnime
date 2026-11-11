import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:playable_anime/core/api/api_error.dart';
import 'package:playable_anime/design/design.dart';
import 'package:playable_anime/design/gallery/gallery_screen.dart';

import '../helpers.dart';

void main() {
  group('SceneCard', () {
    testWidgets('shows the action, time, event, narration and footer', (tester) async {
      var details = 0;
      await tester.pumpWidget(
        wrap(
          SceneCard(
            playerAction: 'I answer the voice',
            spokenAction: true,
            time: const TimeChip(duration: '+2 min', label: 'Day 1, dawn'),
            event: const EventBadge(size: EventSize.local, title: 'Fire in the market'),
            narration: const NarrationText('The lamps *flicker*.'),
            portraits: const PortraitStack(portraits: [PortraitRef(name: 'Elder Wen')]),
            onDetails: () => details++,
          ),
          scroll: true,
        ),
      );
      final l10n = await english();
      expect(find.textContaining('I answer the voice'), findsOneWidget);
      expect(find.byIcon(Icons.mic_none_rounded), findsOneWidget);
      expect(find.textContaining('Day 1, dawn', findRichText: true), findsOneWidget);
      expect(find.textContaining('Fire in the market', findRichText: true), findsOneWidget);
      expect(find.textContaining('The lamps flicker.', findRichText: true), findsOneWidget);
      expect(find.text('EW'), findsOneWidget);
      await tester.tap(find.text(l10n.sceneDetails));
      expect(details, 1);
    });

    testWidgets('leaves out what a scene does not have', (tester) async {
      await tester.pumpWidget(wrap(const SceneCard(narration: Text('Only words.'))));
      expect(find.byType(TimeChip), findsNothing);
      expect(find.byType(EventBadge), findsNothing);
      expect(find.byType(PassageHeading), findsNothing);
      expect(find.byType(SceneOrnament), findsOneWidget);
    });

    testWidgets('a scene that days passed in opens under its heading (W10)', (tester) async {
      await tester.pumpWidget(
        wrap(
          const SceneCard(
            playerAction: 'I train with the sword for a week',
            passage: 'Three days later',
            time: TimeChip(duration: '+3 d', label: 'Day 4, dawn'),
            narration: Text('On the third morning the bell rings.'),
          ),
          scroll: true,
        ),
      );
      // Under what the player did and over the time and the story, as a heading.
      final heading = tester.getRect(find.text('Three days later'));
      expect(heading.top, greaterThan(tester.getRect(find.textContaining('I train')).bottom));
      expect(heading.bottom, lessThan(tester.getRect(find.byType(TimeChip)).top));
      expect(
        tester.getSemantics(find.byType(PassageHeading)),
        matchesSemantics(label: 'Three days later', isHeader: true),
      );
    });

    testWidgets('a long heading in large text wraps between its lines', (tester) async {
      await tester.pumpWidget(
        wrap(
          const MediaQuery(
            data: MediaQueryData(textScaler: TextScaler.linear(2)),
            child: SizedBox(width: 260, child: PassageHeading('Diecisiete meses después')),
          ),
        ),
      );
      expect(tester.takeException(), isNull);
      expect(tester.getSize(find.text('Diecisiete meses después')).height, greaterThan(60));
    });
  });

  group('StoryChoices', () {
    const choices = [
      StoryChoice(id: 'c1', label: 'Climb down'),
      StoryChoice(id: 'c2', label: 'Find Sister Lan', kind: ChoiceKind.personal),
    ];

    testWidgets('sends the tapped choice and standing action', (tester) async {
      StoryChoice? picked;
      StandingAction? stood;
      await tester.pumpWidget(
        wrap(
          StoryChoices(choices: choices, onChoice: (c) => picked = c, onStanding: (a) => stood = a),
        ),
      );
      await tester.pump(const Duration(seconds: 1)); // The entrance.
      final l10n = await english();
      await tester.tap(find.text('Find Sister Lan'));
      expect(picked?.id, 'c2');
      await tester.tap(find.text(l10n.standingObserve));
      expect(stood, StandingAction.observe);
      expect(find.byIcon(ChoiceKind.personal.icon), findsOneWidget);
    });

    testWidgets('does nothing while disabled', (tester) async {
      StoryChoice? picked;
      await tester.pumpWidget(
        wrap(StoryChoices(choices: choices, onChoice: (c) => picked = c, enabled: false)),
      );
      await tester.pump(const Duration(seconds: 1));
      await tester.tap(find.text('Climb down'), warnIfMissed: false);
      expect(picked, isNull);
    });

    testWidgets('shows at once with reduced motion', (tester) async {
      await tester.pumpWidget(
        wrap(StoryChoices(choices: choices, onChoice: (_) {}), reduceMotion: true),
      );
      await tester.pump();
      final fade = tester.widget<FadeTransition>(
        find.ancestor(of: find.text('Climb down'), matching: find.byType(FadeTransition)).first,
      );
      expect(fade.opacity.value, 1);
    });
  });

  group('Composer', () {
    late TextEditingController controller;
    setUp(() => controller = TextEditingController());
    tearDown(() => controller.dispose());

    Widget composer({
      required ValueChanged<String> onSubmit,
      bool busy = false,
      int max = 2000,
      ValueNotifier<bool>? dictating,
      Future<bool> Function()? onFinishDictation,
    }) => wrap(
      Align(
        alignment: Alignment.bottomCenter,
        child: Composer(
          controller: controller,
          onSubmit: onSubmit,
          busy: busy,
          maxLength: max,
          dictating: dictating,
          onFinishDictation: onFinishDictation,
          commands: const [
            SlashCommand('status', 'Your sheet'),
            SlashCommand('recap', 'The story so far'),
          ],
        ),
      ),
    );

    testWidgets('sends the trimmed text, and not when empty or busy', (tester) async {
      final sent = <String>[];
      await tester.pumpWidget(composer(onSubmit: sent.add));
      final l10n = await english();
      await tester.tap(find.byTooltip(l10n.composerSend));
      expect(sent, isEmpty);

      await tester.enterText(find.byType(TextField), '  I wait.  ');
      await tester.pump();
      await tester.tap(find.byTooltip(l10n.composerSend));
      expect(sent, ['I wait.']);

      // While a turn runs, the send button is a spinner and the keyboard's send waits too.
      await tester.pumpWidget(composer(onSubmit: sent.add, busy: true));
      await tester.enterText(find.byType(TextField), 'Again');
      await tester.pump();
      expect(find.byTooltip(l10n.composerSend), findsNothing);
      await tester.testTextInput.receiveAction(TextInputAction.send);
      expect(sent, ['I wait.']);
    });

    testWidgets('with the mic on, send waits for the words and sends the whole box (V2)', (
      tester,
    ) async {
      final dictating = ValueNotifier(true);
      addTearDown(dictating.dispose);
      final sent = <String>[];
      var finishes = 0;
      final landing = Completer<bool>();
      await tester.pumpWidget(
        composer(
          onSubmit: sent.add,
          dictating: dictating,
          onFinishDictation: () {
            finishes++;
            return landing.future;
          },
        ),
      );
      final l10n = await english();

      // Nothing in the box yet, but the words are on their way: send is open.
      await tester.tap(find.byTooltip(l10n.composerSend));
      await tester.pump();
      expect(finishes, 1);
      expect(sent, isEmpty, reason: 'nothing goes until the words are in');
      expect(find.byTooltip(l10n.composerSend), findsNothing);
      expect(find.byType(CircularProgressIndicator), findsOneWidget);

      // Typing on meanwhile, or the keyboard's send, doesn't send half of it.
      await tester.enterText(find.byType(TextField), 'Quietly,');
      await tester.testTextInput.receiveAction(TextInputAction.send);
      await tester.pump();
      expect(finishes, 1);
      expect(sent, isEmpty);

      controller.text = 'Quietly, I bow.';
      dictating.value = false;
      landing.complete(true);
      await tester.pump();
      expect(sent, ['Quietly, I bow.']);
      expect(find.byTooltip(l10n.composerSend), findsOneWidget);
    });

    testWidgets('with the mic on, words that could not be written down are not sent', (
      tester,
    ) async {
      final dictating = ValueNotifier(true);
      addTearDown(dictating.dispose);
      final sent = <String>[];
      await tester.pumpWidget(
        composer(
          onSubmit: sent.add,
          dictating: dictating,
          onFinishDictation: () async {
            dictating.value = false;
            return false;
          },
        ),
      );
      await tester.enterText(find.byType(TextField), 'I run');
      await tester.testTextInput.receiveAction(TextInputAction.send);
      await tester.pump();
      expect(sent, isEmpty);
      expect(
        controller.text,
        'I run',
        reason: 'the box stays, to send once the player has seen it',
      );

      // Sent again, with the mic off, it goes at once.
      await tester.tap(find.byTooltip((await english()).composerSend));
      await tester.pump();
      expect(sent, ['I run']);
    });

    testWidgets('with the mic on, a box past the limit still cannot be sent', (tester) async {
      final dictating = ValueNotifier(true);
      addTearDown(dictating.dispose);
      var finishes = 0;
      await tester.pumpWidget(
        composer(
          onSubmit: (_) {},
          max: 20,
          dictating: dictating,
          onFinishDictation: () async {
            finishes++;
            return true;
          },
        ),
      );
      await tester.enterText(find.byType(TextField), 'x' * 21);
      await tester.pump();
      await tester.tap(find.byTooltip((await english()).composerSend));
      await tester.pump();
      expect(finishes, 0);
    });

    testWidgets('shows slash hints for a leading slash and fills the tapped one', (tester) async {
      await tester.pumpWidget(composer(onSubmit: (_) {}));
      await tester.enterText(find.byType(TextField), '/re');
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400)); // The hints grow in.
      expect(find.text('/recap'), findsOneWidget);
      expect(find.text('/status'), findsNothing);
      await tester.tap(find.text('/recap'));
      await tester.pump();
      expect(controller.text, '/recap ');
      expect(find.text('/recap'), findsNothing); // Hints close once there is a space.
    });

    testWidgets('counts characters near the limit', (tester) async {
      await tester.pumpWidget(composer(onSubmit: (_) {}, max: 20));
      await tester.enterText(find.byType(TextField), 'x' * 10);
      await tester.pump();
      expect(find.textContaining('/ 20'), findsNothing);
      await tester.enterText(find.byType(TextField), 'x' * 19);
      await tester.pump();
      expect(find.textContaining('19'), findsOneWidget);
    });
  });

  group('PictureSlot', () {
    testWidgets('pending shows a shimmer at the final size', (tester) async {
      await tester.pumpWidget(
        wrap(const SizedBox(width: 320, child: PictureSlot(status: PictureStatus.pending))),
      );
      expect(find.byType(Shimmer), findsOneWidget);
      expect(tester.getSize(find.byType(PictureSlot)).height, closeTo(180, 0.5));
      final l10n = await english();
      expect(find.bySemanticsLabel(l10n.picturePending), findsOneWidget);
    });

    testWidgets('skipped collapses quietly to nothing', (tester) async {
      await tester.pumpWidget(
        wrap(const SizedBox(width: 320, child: PictureSlot(status: PictureStatus.skipped))),
      );
      await tester.pump(const Duration(seconds: 1));
      expect(tester.getSize(find.byType(PictureSlot)).height, 0);
    });

    testWidgets('ready draws the picture', (tester) async {
      await tester.pumpWidget(
        wrap(
          const SizedBox(
            width: 320,
            child: PictureSlot(
              status: PictureStatus.ready,
              url: 'asset:assets/fake/scene-peaks.jpg',
              semanticLabel: 'Misty peaks',
            ),
          ),
        ),
      );
      await tester.pump(const Duration(seconds: 1));
      expect(find.byType(Image), findsOneWidget);
      expect(find.bySemanticsLabel('Misty peaks'), findsOneWidget);
    });

    testWidgets('the shimmer stops once the picture has faded in', (tester) async {
      await tester.pumpWidget(
        wrap(
          const SizedBox(
            width: 320,
            child: PictureSlot(
              status: PictureStatus.ready,
              url: 'asset:assets/fake/scene-peaks.jpg',
            ),
          ),
        ),
      );
      expect(find.byType(Shimmer), findsOneWidget);
      // Let the real image load and decode, then run the fade.
      for (var i = 0; i < 5 && find.byType(Shimmer).evaluate().isNotEmpty; i++) {
        await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 200)));
        await tester.pump(const Duration(seconds: 1));
        await tester.pump();
      }
      expect(find.byType(Shimmer), findsNothing);
      expect(find.byType(Image), findsOneWidget);
    });
  });

  group('CoverImage', () {
    const glow = ColoredBox(key: Key('glow'), color: Colors.purple);

    testWidgets('keeps a tall cover\'s upper part in a wide slot', (tester) async {
      await tester.pumpWidget(
        wrap(
          const SizedBox(
            width: 320,
            height: 180,
            child: CoverImage(url: 'asset:assets/fake/portrait-1.jpg', fallback: glow),
          ),
        ),
      );
      final image = tester.widget<Image>(find.byType(Image));
      expect((image.fit, image.alignment), (BoxFit.cover, coverFocus));
    });

    testWidgets('a cover that fails to load leaves the glow', (tester) async {
      await tester.pumpWidget(
        wrap(
          const SizedBox(
            width: 320,
            height: 180,
            child: CoverImage(url: 'asset:assets/fake/no-such-cover.jpg', fallback: glow),
          ),
        ),
      );
      // Let the missing asset fail, then the error frame build.
      for (var i = 0; i < 5; i++) {
        await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 100)));
        await tester.pump();
      }
      expect(find.byKey(const Key('glow')), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  });

  group('portraits', () {
    test('initials skip "the" and use the first and last words', () {
      expect(PortraitAvatar.initials('Elder Wen'), 'EW');
      expect(PortraitAvatar.initials('the Masked Disciple of Ash'), 'MA');
      expect(PortraitAvatar.initials('Lan'), 'L');
      expect(PortraitAvatar.initials('  '), '?');
    });

    testWidgets('a stack shows the first few and counts the rest', (tester) async {
      await tester.pumpWidget(
        wrap(
          const PortraitStack(
            portraits: [
              PortraitRef(name: 'Ann Bell'),
              PortraitRef(name: 'Cy Dorn'),
              PortraitRef(name: 'Eve Fay'),
              PortraitRef(name: 'Gus Hale'),
              PortraitRef(name: 'Ida Jun'),
            ],
          ),
        ),
      );
      expect(find.byType(PortraitAvatar), findsNWidgets(3));
      expect(find.text('+2'), findsOneWidget);
    });
  });

  group('chips', () {
    testWidgets('a time chip shows the duration and the time of day', (tester) async {
      await tester.pumpWidget(wrap(const TimeChip(duration: '+8 h', label: 'Day 3, dusk')));
      expect(find.textContaining('+8 h', findRichText: true), findsOneWidget);
      expect(find.textContaining('Day 3, dusk', findRichText: true), findsOneWidget);
    });

    testWidgets('an opening has only the time of day', (tester) async {
      await tester.pumpWidget(wrap(const TimeChip(label: 'Day 1, dawn')));
      final text = tester.widget<Text>(find.byType(Text)).textSpan!.toPlainText();
      expect(text, 'Day 1, dawn');
    });

    testWidgets('a split clock shows the personal label in the accent', (tester) async {
      await tester.pumpWidget(
        wrap(const TimeChip(duration: '+0 s', personalLabel: 'World: +0 s. You: +40 s.')),
      );
      expect(find.textContaining('You: +40 s.', findRichText: true), findsOneWidget);
      expect(find.byIcon(Icons.hourglass_top_rounded), findsOneWidget);
    });

    testWidgets('event badges read their size and title', (tester) async {
      final l10n = await english();
      for (final size in EventSize.values) {
        await tester.pumpWidget(wrap(EventBadge(size: size, title: 'The bell')));
        final kind = switch (size) {
          EventSize.personal => l10n.eventPersonal,
          EventSize.local => l10n.eventLocal,
          EventSize.world => l10n.eventWorld,
        };
        expect(find.bySemanticsLabel('$kind: The bell'), findsOneWidget);
      }
      expect(EventSize.fromWire('world'), EventSize.world);
      expect(EventSize.fromWire('nonsense'), EventSize.personal);
    });
  });

  group('states', () {
    testWidgets('an error state explains the code and retries', (tester) async {
      var retries = 0;
      final l10n = await english();
      await tester.pumpWidget(
        wrap(
          ErrorState(
            error: const ApiException(ApiErrorCode.network, message: 'offline'),
            onRetry: () => retries++,
          ),
        ),
      );
      expect(find.text(l10n.errorNetworkTitle), findsOneWidget);
      await tester.tap(find.text(l10n.retry));
      expect(retries, 1);
    });

    testWidgets('an error that retrying will not fix has no retry button', (tester) async {
      final l10n = await english();
      await tester.pumpWidget(
        wrap(
          ErrorState(
            error: const ApiException(ApiErrorCode.notFound, message: 'gone'),
            onRetry: () {},
          ),
        ),
      );
      expect(find.text(l10n.retry), findsNothing);
    });

    testWidgets('an empty state offers its action', (tester) async {
      var tapped = 0;
      await tester.pumpWidget(
        wrap(
          EmptyState(
            icon: Icons.auto_stories_outlined,
            title: 'Nothing yet',
            message: 'Start a story.',
            actionLabel: 'Discover',
            onAction: () => tapped++,
          ),
        ),
      );
      await tester.tap(find.text('Discover'));
      expect(tapped, 1);
    });

    testWidgets('a sheet opens with its title and closes', (tester) async {
      await tester.pumpWidget(
        wrap(
          Builder(
            builder: (context) => TextButton(
              onPressed: () => showAppSheet<void>(
                context: context,
                title: 'Scene details',
                builder: (_) => const Text('How it played out'),
              ),
              child: const Text('Open'),
            ),
          ),
        ),
      );
      await tester.tap(find.text('Open'));
      await tester.pumpAndSettle();
      expect(find.text('Scene details'), findsOneWidget);
      expect(find.text('How it played out'), findsOneWidget);
      await tester.tapAt(const Offset(10, 10));
      await tester.pumpAndSettle();
      expect(find.text('How it played out'), findsNothing);
    });
  });

  group('the widget gallery lays out without overflow', () {
    for (final (brightness, scale) in [
      (Brightness.dark, 1.0),
      (Brightness.light, 1.0),
      (Brightness.dark, 2.0),
    ]) {
      testWidgets('${brightness.name} at ${scale}x text', (tester) async {
        // Tall enough that every section is built at once.
        usePhone(tester, size: Size(390, 9000 * scale));
        await tester.pumpWidget(wrap(GalleryScreen(brightness: brightness, textScale: scale)));
        await tester.pump(const Duration(seconds: 1));
        expect(tester.takeException(), isNull);
        expect(find.text('Pictures'.toUpperCase()), findsOneWidget);
      });
    }
  });
}

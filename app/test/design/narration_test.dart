import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:playable_anime/design/design.dart';

import '../helpers.dart';

void main() {
  group('parseNarration', () {
    test('plain text is one run', () {
      expect(parseNarration('The bell tolls.'), [const NarrationRun('The bell tolls.')]);
    });

    test('reads *italic* and **bold**', () {
      expect(parseNarration('A *voice* and a **name**.'), const [
        NarrationRun('A '),
        NarrationRun('voice', italic: true),
        NarrationRun(' and a '),
        NarrationRun('name', bold: true),
        NarrationRun('.'),
      ]);
    });

    test('a blank line is a paragraph break, a single line end is not', () {
      expect(parseNarration('One.\n\nTwo.\nThree.'), const [
        NarrationRun('One.'),
        NarrationRun('\n', paragraphBreak: true),
        NarrationRun('Two.'),
        NarrationRun('\n'),
        NarrationRun('Three.'),
      ]);
    });

    test('blank lines with spaces and Windows line ends still break once', () {
      expect(parseNarration('One.\r\n \r\n\r\nTwo.'), const [
        NarrationRun('One.'),
        NarrationRun('\n', paragraphBreak: true),
        NarrationRun('Two.'),
      ]);
    });

    test('an emphasis left open mid-stream runs to the end of its paragraph', () {
      expect(parseNarration('It says *you were'), const [
        NarrationRun('It says '),
        NarrationRun('you were', italic: true),
      ]);
      expect(parseNarration('*open\n\nclosed'), const [
        NarrationRun('open', italic: true),
        NarrationRun('\n', paragraphBreak: true),
        NarrationRun('closed'),
      ]);
    });

    test('marks never show as text', () {
      final text = parseNarration('***both*** and **').map((r) => r.text).join();
      expect(text, isNot(contains('*')));
    });
  });

  testWidgets('NarrationText shows the words without the marks', (tester) async {
    await tester.pumpWidget(wrap(const NarrationText('A *quiet* voice.\n\nThen silence.')));
    final text = tester.widget<Text>(find.byType(Text)).textSpan!.toPlainText();
    expect(text, contains('A quiet voice.'));
    expect(text, contains('Then silence.'));
    expect(text, isNot(contains('*')));
  });

  group('StreamingNarration', () {
    String shown(WidgetTester tester) => tester
        .widget<RichText>(find.byType(RichText).first)
        .text
        .toPlainText(includePlaceholders: false);

    bool hasCaret(WidgetTester tester) {
      var found = false;
      tester.widget<RichText>(find.byType(RichText).first).text.visitChildren((span) {
        found = found || span is WidgetSpan;
        return true;
      });
      return found;
    }

    testWidgets('shows skeleton lines before the first words', (tester) async {
      await tester.pumpWidget(wrap(const StreamingNarration(text: '', streaming: true)));
      expect(find.byType(SkeletonText), findsOneWidget);
      await tester.pump(const Duration(seconds: 2));
    });

    testWidgets('adds words as they arrive and fades them in', (tester) async {
      Widget at(String text, {bool streaming = true}) =>
          wrap(StreamingNarration(text: text, streaming: streaming));
      await tester.pumpWidget(at('The scroll'));
      expect(shown(tester), 'The scroll');
      expect(hasCaret(tester), isTrue);

      await tester.pumpWidget(at('The scroll is warm'));
      expect(shown(tester), 'The scroll is warm');
      // Mid-fade, the new words are drawn partly transparent.
      await tester.pump(const Duration(milliseconds: 60));
      final spans = <TextSpan>[];
      tester.widget<RichText>(find.byType(RichText).first).text.visitChildren((span) {
        if (span is TextSpan && span.text != null) spans.add(span);
        return true;
      });
      final fading = spans.where((s) => s.text!.contains('warm')).single;
      expect(fading.style!.color!.a, lessThan(1));

      // Once the reveal is over, everything is opaque and the caret is gone when done.
      await tester.pump(Motion.reveal * 2);
      await tester.pumpWidget(at('The scroll is warm.', streaming: false));
      await tester.pump(Motion.reveal * 2);
      expect(shown(tester), 'The scroll is warm.');
      expect(hasCaret(tester), isFalse);
    });

    testWidgets('a reset starts over without animating', (tester) async {
      await tester.pumpWidget(wrap(const StreamingNarration(text: 'Words that', streaming: true)));
      await tester.pumpWidget(wrap(const StreamingNarration(text: 'Elsewhere', streaming: true)));
      expect(shown(tester), 'Elsewhere');
      await tester.pump(const Duration(seconds: 1));
    });

    testWidgets('with reduced motion, words simply appear', (tester) async {
      Widget at(String text) =>
          wrap(StreamingNarration(text: text, streaming: true), reduceMotion: true);
      await tester.pumpWidget(at('One'));
      await tester.pumpWidget(at('One two'));
      final spans = <TextSpan>[];
      tester.widget<RichText>(find.byType(RichText).first).text.visitChildren((span) {
        if (span is TextSpan && span.text != null) spans.add(span);
        return true;
      });
      expect(spans.every((s) => s.style?.color == null || s.style!.color!.a == 1), isTrue);
    });
  });
}

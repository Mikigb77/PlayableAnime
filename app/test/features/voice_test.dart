import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:playable_anime/design/design.dart';
import 'package:playable_anime/features/voice/dictation_button.dart';
import 'package:playable_anime/features/voice/dictation_controller.dart';
import 'package:playable_anime/features/voice/input_mode.dart';
import 'package:playable_anime/features/voice/speech_engine.dart';

import '../helpers.dart';

void main() {
  group('InputModeTracker (V7)', () {
    late TextEditingController controller;
    late InputModeTracker tracker;
    setUp(() {
      controller = TextEditingController();
      tracker = InputModeTracker(controller);
    });
    tearDown(() {
      tracker.dispose();
      controller.dispose();
    });

    test('typing is typed', () {
      controller.text = 'I wait';
      expect(tracker.mode, InputMode.typed);
    });

    test('dictation alone is voice, and editing it makes it voice_edited', () {
      tracker.applyDictation('I draw my blade');
      expect(tracker.mode, InputMode.voice);
      expect(controller.selection.baseOffset, 'I draw my blade'.length);
      controller.selection = const TextSelection.collapsed(offset: 2); // A cursor move.
      expect(tracker.mode, InputMode.voice);
      controller.text = 'I draw my sword';
      expect(tracker.mode, InputMode.voiceEdited);
      expect(InputMode.voiceEdited.wire, 'voice_edited');
    });

    test('clearing the box starts over', () {
      tracker.applyDictation('Hello');
      controller.text = 'Hello there';
      controller.clear();
      expect(tracker.mode, InputMode.typed);
      tracker.applyDictation('Again');
      expect(tracker.mode, InputMode.voice);
    });
  });

  group('DictationController', () {
    late TextEditingController text;
    late InputModeTracker tracker;
    late FakeSpeechEngine engine;
    late DictationController dictation;

    setUp(() {
      text = TextEditingController();
      tracker = InputModeTracker(text);
      engine = FakeSpeechEngine();
      dictation = DictationController(engine: engine, tracker: tracker, localeId: 'en_US');
    });
    tearDown(() {
      dictation.dispose();
      tracker.dispose();
      text.dispose();
    });

    test('writes words live into the box and stops on the final result', () async {
      await dictation.start();
      expect(dictation.phase, DictationPhase.listening);
      expect(engine.listens.single, (localeId: 'en_US', onDevice: true));
      engine.hear('I draw');
      expect(text.text, 'I draw');
      engine.hear('I draw my blade', isFinal: true);
      expect(text.text, 'I draw my blade');
      expect(dictation.phase, DictationPhase.idle);
      expect(tracker.mode, InputMode.voice);
    });

    test('adds to what is already in the box, with a space', () async {
      text.text = 'I look up.';
      await dictation.start();
      engine.hear('Then I run');
      expect(text.text, 'I look up. Then I run');
      expect(tracker.mode, InputMode.voiceEdited);
    });

    test('asks for permission once, and only on the first tap', () async {
      await dictation.start();
      await dictation.stop();
      await dictation.start();
      expect(engine.initializations, 1);
      expect(engine.stops, 1);
    });

    test('a refused permission shows as denied and stays there', () async {
      engine
        ..grants = false
        ..permission = false;
      await dictation.start();
      expect(dictation.phase, DictationPhase.denied);
      await dictation.start();
      expect(engine.listens, isEmpty);
    });

    test('after a refusal, the mic works once the player allows it in settings', () async {
      engine
        ..grants = false
        ..permission = false;
      await dictation.start();
      expect(await dictation.retryPermission(), isFalse);
      expect(dictation.phase, DictationPhase.denied);

      engine
        ..grants = true
        ..permission = true;
      expect(await dictation.retryPermission(), isTrue);
      expect(dictation.phase, DictationPhase.listening);
      expect(engine.listens, hasLength(1));
    });

    test('a device without a recognizer is unavailable', () async {
      engine
        ..grants = false
        ..permission = true;
      await dictation.start();
      expect(dictation.phase, DictationPhase.unavailable);
    });

    test('falls back from on-device recognition once', () async {
      await dictation.start();
      engine.fail('error_language_unavailable');
      expect(engine.listens.map((l) => l.onDevice), [true, false]);
      await Future<void>.delayed(Duration.zero);
      expect(dictation.phase, DictationPhase.listening);
      engine.fail('error_network');
      expect(dictation.phase, DictationPhase.idle);
      expect(dictation.failure?.code, 'error_network');
    });

    test('silence is not an error worth telling', () async {
      await dictation.start();
      engine.fail('error_no_match');
      expect(dictation.phase, DictationPhase.idle);
      expect(dictation.failure, isNull);
    });

    test('a permission error while listening is denied', () async {
      await dictation.start();
      engine.fail('error_permission');
      expect(dictation.phase, DictationPhase.denied);
    });

    test('stopping in the middle of a dictation leaves the words to edit', () async {
      await dictation.start();
      engine.hear('Half a');
      await dictation.toggle();
      expect(dictation.phase, DictationPhase.idle);
      expect(text.text, 'Half a');
    });
  });

  group('DictationButton', () {
    late FakeSpeechEngine engine;
    late TextEditingController text;
    late InputModeTracker tracker;

    setUp(() {
      engine = FakeSpeechEngine();
      text = TextEditingController();
      tracker = InputModeTracker(text);
    });
    tearDown(() {
      tracker.dispose();
      text.dispose();
    });

    Widget app() => ProviderScope(
      overrides: [speechEngineProvider.overrideWithValue(engine)],
      child: wrap(
        Center(
          child: Row(
            children: [
              Expanded(child: TextField(controller: text)),
              DictationButton(tracker: tracker),
            ],
          ),
        ),
      ),
    );

    testWidgets('hides where speech is not supported', (tester) async {
      engine.supported = false;
      await tester.pumpWidget(app());
      await tester.pump();
      expect(find.byType(MicButton), findsNothing);
    });

    testWidgets('listens on tap and shows the words as they come', (tester) async {
      await tester.pumpWidget(app());
      await tester.pump();
      final l10n = await english();
      await tester.tap(find.byType(MicButton));
      await tester.pump();
      expect(tester.widget<MicButton>(find.byType(MicButton)).visual, MicVisual.listening);
      engine.hear('Open the door');
      await tester.pump();
      expect(find.text('Open the door'), findsOneWidget);
      await tester.tap(find.byTooltip(l10n.micStop));
      await tester.pump();
      expect(tester.widget<MicButton>(find.byType(MicButton)).visual, MicVisual.idle);
      expect(engine.stops, 1);
    });

    testWidgets('explains how to allow the mic after a refusal', (tester) async {
      engine
        ..grants = false
        ..permission = false;
      await tester.pumpWidget(app());
      await tester.pump();
      await tester.tap(find.byType(MicButton));
      await tester.pump();
      expect(tester.widget<MicButton>(find.byType(MicButton)).visual, MicVisual.denied);
      await tester.tap(find.byType(MicButton));
      await tester.pumpAndSettle();
      final l10n = await english();
      expect(find.text(l10n.micDeniedTitle), findsOneWidget);
    });

    testWidgets('a failure is a short message, and typing still works', (tester) async {
      await tester.pumpWidget(app());
      await tester.pump();
      await tester.tap(find.byType(MicButton));
      await tester.pump();
      engine.hear('Something');
      engine.fail('error_network');
      await tester.pump();
      final l10n = await english();
      expect(find.text(l10n.micError), findsOneWidget);
      await tester.enterText(find.byType(TextField), 'Typed instead');
      expect(tracker.mode, InputMode.voiceEdited);
    });
  });
}

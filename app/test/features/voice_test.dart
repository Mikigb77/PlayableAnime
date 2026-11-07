import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:playable_anime/core/l10n.dart';
import 'package:playable_anime/design/design.dart';
import 'package:playable_anime/features/voice/dictation_button.dart';
import 'package:playable_anime/features/voice/dictation_controller.dart';
import 'package:playable_anime/features/voice/dictation_mode.dart';
import 'package:playable_anime/features/voice/input_mode.dart';
import 'package:playable_anime/features/voice/speech_engine.dart';
import 'package:shared_preferences/shared_preferences.dart';

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
      expect(engine.listens.single.localeId, 'en_US');
      expect(engine.listens.single.onDevice, isTrue);
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

  group('online DictationController (V6)', () {
    late TextEditingController text;
    late InputModeTracker tracker;
    late FakeSpeechEngine engine;
    late DictationController dictation;

    setUp(() {
      text = TextEditingController();
      tracker = InputModeTracker(text);
      engine = FakeSpeechEngine(onPhone: false);
      dictation = DictationController(
        engine: engine,
        tracker: tracker,
        context: const SpeechContext(storyId: 'story_1'),
      );
    });
    tearDown(() {
      dictation.dispose();
      tracker.dispose();
      text.dispose();
    });

    test('listens in the story language, for the story', () async {
      await dictation.start();
      final listen = engine.listens.single;
      expect(listen.localeId, storyLanguage);
      expect(listen.context, const SpeechContext(storyId: 'story_1'));
    });

    test('the tap ends the recording and waits for the words', () async {
      await dictation.start();
      await dictation.toggle();
      expect(engine.stops, 1);
      expect(dictation.phase, DictationPhase.transcribing);
      await dictation.toggle(); // the mic can't be tapped while the words are on their way
      expect(engine.listens, hasLength(1));

      engine
        ..hear('I bow.', isFinal: true)
        ..stopped();
      expect(text.text, 'I bow.');
      expect(dictation.phase, DictationPhase.idle);
    });

    test('a long dictation lands in parts, after anything typed meanwhile', () async {
      text.text = 'Quietly,';
      await dictation.start();

      engine.hear('I bow.'); // the first part, while the player goes on
      expect(text.text, 'Quietly, I bow.');
      expect(dictation.phase, DictationPhase.listening);
      text.text = 'Quietly, I bow. Then';

      await dictation.stop();
      expect(dictation.phase, DictationPhase.transcribing);
      engine
        ..hear('I wait.')
        ..stopped();

      expect(text.text, 'Quietly, I bow. Then I wait.');
      expect(dictation.phase, DictationPhase.idle);
      expect(tracker.mode, InputMode.voiceEdited);
    });

    test('a failure is told once, with no on-device fallback', () async {
      await dictation.start();
      engine
        ..transcribing()
        ..fail(SpeechFailure.outOfCredits);
      expect(dictation.phase, DictationPhase.idle);
      expect(dictation.failure?.code, SpeechFailure.outOfCredits);
      expect(engine.listens, hasLength(1));
    });

    test('a stop while the mic is starting writes nothing down', () async {
      await dictation.start();
      await dictation.stop();
      await dictation.start();
      await dictation.stop();
      expect(dictation.phase, isNot(DictationPhase.listening));
    });
  });

  group('finishing a dictation before sending (V2)', () {
    late TextEditingController text;
    late InputModeTracker tracker;

    setUp(() {
      text = TextEditingController();
      tracker = InputModeTracker(text);
    });
    tearDown(() {
      tracker.dispose();
      text.dispose();
    });

    DictationController mic(FakeSpeechEngine engine, {Duration? lastWords}) {
      final dictation = DictationController(
        engine: engine,
        tracker: tracker,
        lastWords: lastWords ?? const Duration(seconds: 2),
      );
      addTearDown(dictation.dispose);
      return dictation;
    }

    test('a box with no mic, or with the mic off, sends at once', () async {
      expect(tracker.dictating.value, isFalse);
      expect(await tracker.finishDictation(), isTrue);

      final engine = FakeSpeechEngine(onPhone: false);
      final dictation = DictationController(engine: engine, tracker: tracker);
      expect(await tracker.finishDictation(), isTrue);
      expect(engine.stops, 0);

      await dictation.start();
      expect(tracker.dictating.value, isTrue);
      dictation.dispose(); // the box's mic is gone
      expect(tracker.dictating.value, isFalse);
      expect(await tracker.finishDictation(), isTrue);
    });

    test('online, it turns the mic off and waits for the words after the typed ones', () async {
      final engine = FakeSpeechEngine(onPhone: false);
      final dictation = mic(engine);
      await dictation.start();
      expect(tracker.dictating.value, isTrue);
      text.text = 'Quietly,';

      var landed = false;
      final finishing = tracker.finishDictation().then((ok) => landed = ok);
      await pumpEventQueue();
      expect(engine.stops, 1);
      expect(dictation.phase, DictationPhase.transcribing);
      expect(landed, isFalse, reason: 'the words are still on their way');
      expect(tracker.dictating.value, isTrue);

      // The mic can't come back on while the box waits to be sent.
      await dictation.start();
      expect(engine.listens, hasLength(1));

      engine
        ..hear('I bow.')
        ..stopped();
      await finishing;
      expect(landed, isTrue);
      expect(text.text, 'Quietly, I bow.');
      expect(tracker.dictating.value, isFalse);
      expect(tracker.mode, InputMode.voiceEdited);
    });

    test('online, it waits for words already being written down', () async {
      final engine = FakeSpeechEngine(onPhone: false);
      final dictation = mic(engine);
      await dictation.start();
      await dictation.stop();
      expect(dictation.phase, DictationPhase.transcribing);

      final finishing = tracker.finishDictation();
      engine
        ..hear('I wait.')
        ..stopped();
      expect(await finishing, isTrue);
      expect(engine.stops, 1, reason: 'the mic was already off');
      expect(text.text, 'I wait.');
    });

    test('online, words that cannot be written down are not sent', () async {
      final engine = FakeSpeechEngine(onPhone: false);
      final dictation = mic(engine);
      await dictation.start();
      text.text = 'I run';
      final finishing = tracker.finishDictation();
      await pumpEventQueue();
      engine.fail(SpeechFailure.offline);
      expect(await finishing, isFalse);
      expect(dictation.failure?.code, SpeechFailure.offline);
      expect(text.text, 'I run', reason: 'what was there stays to send');
      expect(tracker.dictating.value, isFalse);
    });

    test('online, silence sends what was typed', () async {
      final engine = FakeSpeechEngine(onPhone: false);
      final dictation = mic(engine);
      await dictation.start();
      final finishing = tracker.finishDictation();
      await pumpEventQueue();
      engine.fail('error_speech_timeout');
      expect(await finishing, isTrue);
      expect(dictation.phase, DictationPhase.idle);
    });

    test('a mic still starting just stops: nothing was heard', () async {
      final engine = FakeSpeechEngine(onPhone: false);
      final dictation = mic(engine);
      final starting = dictation.start();
      expect(dictation.phase, DictationPhase.starting);
      expect(await tracker.finishDictation(), isTrue);
      await starting;
      expect(dictation.phase, DictationPhase.idle);
      expect(tracker.dictating.value, isFalse);
    });

    test('on the phone, it waits for the last words, and later ones never land', () async {
      final engine = FakeSpeechEngine();
      final dictation = mic(engine);
      await dictation.start();
      engine.hear('I draw my');

      var done = false;
      final finishing = tracker.finishDictation().then((ok) => done = ok);
      await pumpEventQueue();
      expect(engine.stops, 1);
      expect(dictation.phase, DictationPhase.idle);
      expect(done, isFalse, reason: 'the last words are still to come');
      expect(tracker.dictating.value, isTrue);

      engine.hear('I draw my blade', isFinal: true);
      await finishing;
      expect(done, isTrue);
      expect(text.text, 'I draw my blade');
      expect(tracker.dictating.value, isFalse);

      text.clear(); // sent
      engine.hear('I draw my blade', isFinal: true);
      expect(text.text, isEmpty);
    });

    test('on the phone, it sends what is there if the last words never come', () async {
      final engine = FakeSpeechEngine();
      final dictation = mic(engine, lastWords: const Duration(milliseconds: 20));
      await dictation.start();
      engine.hear('I draw my');
      expect(await tracker.finishDictation(), isTrue);
      expect(text.text, 'I draw my');
      expect(tracker.dictating.value, isFalse);
    });

    test('on the phone, a recognizer that stopped by itself still gives its last words', () async {
      final engine = FakeSpeechEngine();
      final dictation = mic(engine);
      await dictation.start();
      engine
        ..hear('I wait')
        ..stopped(); // a pause long enough for the phone to stop
      expect(dictation.phase, DictationPhase.idle);
      expect(tracker.dictating.value, isTrue, reason: 'its last words are still to come');

      final finishing = tracker.finishDictation();
      engine.hear('I wait here', isFinal: true);
      expect(await finishing, isTrue);
      expect(text.text, 'I wait here');
      expect(tracker.dictating.value, isFalse);
      expect(engine.stops, 0, reason: 'it was already off');
    });

    test('on the phone, a new dictation never gets the last one\'s late words', () async {
      final engine = FakeSpeechEngine();
      final dictation = mic(engine);
      await dictation.start();
      engine.hear('I wait');
      await dictation.stop();
      await dictation.start(); // before the first one's last words came
      engine.hearLate(0, 'I wait here');
      expect(text.text, 'I wait');
      engine.hear('then I run');
      expect(text.text, 'I wait then I run');
    });

    test('on the phone, an error once the mic is off never turns it on again', () async {
      final engine = FakeSpeechEngine();
      final dictation = mic(engine);
      await dictation.start();
      final finishing = tracker.finishDictation();
      await pumpEventQueue();
      engine.fail('error_language_unavailable');
      expect(await finishing, isFalse);
      expect(engine.listens, hasLength(1));
      expect(dictation.phase, DictationPhase.idle);
    });
  });

  group('DictationModeController', () {
    test('is online until the player picks this device, which is remembered', () async {
      SharedPreferences.setMockInitialValues({});
      final first = ProviderContainer();
      addTearDown(first.dispose);
      expect(first.read(dictationModeProvider), DictationMode.online);
      await first.read(dictationModeProvider.notifier).set(DictationMode.device);

      final next = ProviderContainer();
      addTearDown(next.dispose);
      next.read(dictationModeProvider);
      await pumpEventQueue();
      expect(next.read(dictationModeProvider), DictationMode.device);
    });

    test('a stored value it does not know is online', () async {
      SharedPreferences.setMockInitialValues({'dictation.mode': 'telepathy'});
      final container = ProviderContainer();
      addTearDown(container.dispose);
      container.read(dictationModeProvider);
      await pumpEventQueue();
      expect(container.read(dictationModeProvider), DictationMode.online);
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

    Widget app({FakeSpeechEngine? using, String? storyId}) => ProviderScope(
      overrides: [speechEngineProvider.overrideWithValue(using ?? engine)],
      child: wrap(
        Center(
          child: Row(
            children: [
              Expanded(child: TextField(controller: text)),
              DictationButton(tracker: tracker, storyId: storyId),
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

    testWidgets('online, it spins while the words are written down', (tester) async {
      final online = FakeSpeechEngine(onPhone: false);
      await tester.pumpWidget(app(using: online, storyId: 'story_1'));
      await tester.pump();
      final l10n = await english();
      await tester.tap(find.byType(MicButton));
      await tester.pump();
      expect(online.listens.single.context, const SpeechContext(storyId: 'story_1'));

      await tester.tap(find.byTooltip(l10n.micStop));
      await tester.pump();
      final mic = tester.widget<MicButton>(find.byType(MicButton));
      expect(mic.visual, MicVisual.transcribing);
      expect(find.byTooltip(l10n.micTranscribing), findsOneWidget);

      online
        ..hear('Open the door', isFinal: true)
        ..stopped();
      await tester.pump();
      expect(find.text('Open the door'), findsOneWidget);
      expect(tester.widget<MicButton>(find.byType(MicButton)).visual, MicVisual.idle);
    });

    testWidgets('leaving the app turns the mic off', (tester) async {
      final online = FakeSpeechEngine(onPhone: false);
      await tester.pumpWidget(app(using: online));
      await tester.pump();
      await tester.tap(find.byType(MicButton));
      await tester.pump();

      tester.binding
        ..handleAppLifecycleStateChanged(AppLifecycleState.inactive)
        ..handleAppLifecycleStateChanged(AppLifecycleState.hidden);
      await tester.pump();
      expect(online.stops, 1);
      expect(tester.widget<MicButton>(find.byType(MicButton)).visual, MicVisual.transcribing);

      tester.binding
        ..handleAppLifecycleStateChanged(AppLifecycleState.inactive)
        ..handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await tester.pump();
      expect(online.stops, 1, reason: 'coming back starts nothing');
    });

    for (final (code, message) in [
      (SpeechFailure.outOfCredits, (AppLocalizations l) => l.micOutOfCredits),
      (SpeechFailure.limited, (AppLocalizations l) => l.micLimited),
      (SpeechFailure.offline, (AppLocalizations l) => l.micOffline),
    ]) {
      testWidgets('online, $code says what to do', (tester) async {
        final online = FakeSpeechEngine(onPhone: false);
        await tester.pumpWidget(app(using: online));
        await tester.pump();
        await tester.tap(find.byType(MicButton));
        await tester.pump();
        online
          ..transcribing()
          ..fail(code);
        await tester.pump();
        expect(find.text(message(await english())), findsOneWidget);
      });
    }

    testWidgets('switching dictation in Account switches the mic at once', (tester) async {
      SharedPreferences.setMockInitialValues({});
      final online = FakeSpeechEngine(onPhone: false);
      final phone = FakeSpeechEngine();
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            speechEngineProvider.overrideWith(
              (ref) => switch (ref.watch(dictationModeProvider)) {
                DictationMode.online => online,
                DictationMode.device => phone,
              },
            ),
          ],
          child: wrap(DictationButton(tracker: tracker)),
        ),
      );
      await tester.pump();
      await tester.tap(find.byType(MicButton));
      await tester.pump();
      expect((online.listens.length, phone.listens.length), (1, 0));

      final container = ProviderScope.containerOf(tester.element(find.byType(DictationButton)));
      await container.read(dictationModeProvider.notifier).set(DictationMode.device);
      await tester.pump();
      await tester.pump();
      expect(online.cancels, 1, reason: 'the old recognizer stops listening');
      expect(tester.widget<MicButton>(find.byType(MicButton)).visual, MicVisual.idle);

      await tester.tap(find.byType(MicButton));
      await tester.pump();
      expect((online.listens.length, phone.listens.length), (1, 1));
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

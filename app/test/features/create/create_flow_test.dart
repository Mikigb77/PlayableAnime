import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:playable_anime/core/api/api_client.dart';
import 'package:playable_anime/core/api/api_error.dart';
import 'package:playable_anime/core/fake/fake_auth.dart';
import 'package:playable_anime/core/fake/fake_backend.dart';
import 'package:playable_anime/core/json.dart';
import 'package:playable_anime/features/create/create_flow.dart';
import 'package:playable_anime/features/create/draft.dart';
import 'package:playable_anime/features/create/draft_repository.dart';
import 'package:playable_anime/features/library/library.dart';
import 'package:playable_anime/features/story/memory.dart';

import '../../helpers.dart';

/// The create flow on the fake backend: drafting, changes with their costs, stale copies and the
/// start (G1, G2, K2, T10).
void main() {
  late ApiClient api;
  late FakeBackend backend;
  late CreateFlow flow;

  Future<num> balance() async =>
      (await api.get('/v1/me/credits') as JsonMap)['balance_cents'] as num;

  setUp(() async {
    final fake = fakeApi();
    api = fake.api;
    backend = fake.backend;
    final session =
        await api.post('/v1/auth/login', {
              'email': FakeAuthState.demoEmail,
              'password': FakeAuthState.demoPassword,
            }, authenticated: false)
            as JsonMap;
    fake.tokens.accessToken = session['access_token'] as String;
    flow = CreateFlow(DraftRepository(api));
    addTearDown(flow.dispose);
  });

  Future<Draft> drafted({
    String premiseId = 'outer-disciple',
    Rating rating = Rating.mature,
  }) async {
    await flow.create(premiseId: premiseId, rating: rating);
    expect(flow.error, isNull);
    return flow.draft!;
  }

  test('a starter is drafted by id, word for word, for one draft call', () async {
    final before = await balance();
    final stages = <CreateStage>[];
    flow.addListener(() => stages.add(flow.stage));
    final draft = await drafted();
    expect(stages, [CreateStage.drafting, CreateStage.review]);
    expect(draft.premiseId, 'outer-disciple');
    expect(draft.title, 'The Last Outer Disciple');
    expect(draft.worldParts, isNotEmpty);
    expect(draft.characterParts.first, const DraftLine(LineKind.who, 'Lin Feng, 16.'));
    expect(draft.character.name, 'Lin Feng');
    expect(draft.character.age, 16);
    expect(draft.ladder!.rungs.first, 'Qi Condensation');
    expect(flow.hasUnsavedDraft, isTrue);
    expect(await balance(), before - 3);
    final sent = backend.requests.lastWhere((r) => r.uri.path == '/v1/drafts').json;
    expect(sent, {'premise_id': 'outer-disciple', 'rating': 'mature', 'language': 'en'});
  });

  test('the player\'s own premise and early choices go with the first draft', () async {
    await flow.create(
      premise: 'A lighthouse keeper finds a door in the sea.',
      rating: Rating.teen,
      choices: const DraftChoices(physics: Physics.strict, difficulty: Difficulty.brutal),
    );
    final draft = flow.draft!;
    expect(draft.premise, 'A lighthouse keeper finds a door in the sea.');
    expect(draft.rating, Rating.teen);
    expect(draft.advanced.physics, Physics.strict);
    expect(draft.advanced.difficulty, Difficulty.brutal);
  });

  test('every change costs what the app said it would', () async {
    final draft = await drafted();
    final rules = draft.advanced.rules;
    final edits = [
      const DraftEdit(physics: Physics.strict),
      DraftEdit(rules: [for (final rule in rules) rule.copyWith(fixed: !rule.fixed)]),
      const DraftEdit(difficulty: Difficulty.brutal, eventFrequency: EventFrequency.calm),
      const DraftEdit(title: 'The Ninth Peak', tone: 'Cold and patient'),
      const DraftEdit(name: 'Shen Yu', age: 17),
      const DraftEdit(looks: 'Tall, with a scar through one brow.', manner: 'Says little.'),
      DraftEdit(
        rules: [
          ...rules,
          const DraftRule(text: 'Jade remembers who held it.'),
        ],
      ),
      const DraftEdit(giftStrength: GiftStrength.rare),
      const DraftEdit(giftStrength: GiftStrength.none),
      const DraftEdit(rating: Rating.teen),
      const DraftEdit(rating: Rating.mature),
    ];
    for (final edit in edits) {
      final cost = redraftFor(flow.draft!, edit);
      final before = await balance();
      final version = flow.draft!.version;
      expect(await flow.edit(edit), isNull);
      expect(
        await balance(),
        before - 3 * cost.calls,
        reason: '${edit.toJson(expectedVersion: 0)}',
      );
      expect(flow.draft!.version, version + 1);
      final sent = backend.requests.lastWhere((r) => r.method == 'PATCH').json;
      expect(sent['expected_version'], version);
    }
    expect(flow.draft!.advanced.physics, Physics.strict);
    expect(flow.draft!.rating, Rating.mature);
  });

  test('each paid request says so, for the balance to be read again (K2)', () async {
    var charged = 0;
    final paid = CreateFlow(DraftRepository(api), onCharged: () => charged++);
    addTearDown(paid.dispose);
    await paid.create(premiseId: 'outer-disciple', rating: Rating.mature);
    expect(charged, 1);
    // A free change spends nothing; a redraft and a revision do, and so does a failed one.
    expect(await paid.edit(const DraftEdit(physics: Physics.strict)), isNull);
    expect(charged, 1);
    expect(await paid.edit(const DraftEdit(rating: Rating.teen)), isNull);
    expect(charged, 2);
    expect(await paid.revise(DraftPart.world, 'More rain [fail:llm_unavailable]'), isNotNull);
    expect(charged, 3);
  });

  test('the redrafting parts show while a change is in flight', () async {
    await drafted();
    final seen = <Redraft>[];
    flow.addListener(() => seen.add(flow.redrafting));
    expect(await flow.revise(DraftPart.character, 'Make me older, with a scar'), isNull);
    expect(seen.first, const Redraft(character: true));
    expect(flow.redrafting, Redraft.none);
    expect(
      flow.draft!.linesOf(DraftPart.character, LineKind.nature).last,
      'Me older, with a scar.',
    );
  });

  test('the plain fields change at once, with no model call (G1, G2)', () async {
    final draft = await drafted(premiseId: 'ashen-squire');
    final before = await balance();
    final seen = <Redraft>[];
    flow.addListener(() => seen.add(flow.redrafting));

    expect(await flow.edit(const DraftEdit(name: 'Mara Quill', age: 23)), isNull);
    expect(await flow.edit(const DraftEdit(title: 'Ash and Oath')), isNull);
    expect(await flow.edit(const DraftEdit(looks: 'Tall, with a burn across one hand.')), isNull);
    expect(await balance(), before);
    // Nothing is redrafted, so no part shows as being rewritten.
    expect(seen, everyElement(Redraft.none));

    final now = flow.draft!;
    expect(now.version, draft.version + 3);
    expect(now.title, 'Ash and Oath');
    expect(now.character.name, 'Mara Quill');
    expect(now.character.age, 23);
    expect(now.character.looks, 'Tall, with a burn across one hand.');
    expect(now.characterParts.first, const DraftLine(LineKind.who, 'Mara Quill, 23.'));
    final sent = backend.requests.where((r) => r.method == 'PATCH').first.json;
    expect(sent, {
      'character': {'name': 'Mara Quill', 'age': 23},
      'expected_version': draft.version,
    });
  });

  test(
    'a blank or overlong plain field is refused at its own field, and nothing changes',
    () async {
      final draft = await drafted();
      final blank = await flow.edit(const DraftEdit(name: '   '));
      expect(
        (blank! as ApiException).fields.single,
        allOf(containsPair('field', 'character.name'), containsPair('type', 'empty')),
      );
      final long = await flow.edit(DraftEdit(title: 'x' * (DraftLimits.title + 1)));
      expect((long! as ApiException).fields.single, containsPair('field', 'title'));
      final old = await flow.edit(const DraftEdit(age: DraftLimits.ageMax + 1));
      expect((old! as ApiException).fields.single, containsPair('field', 'character.age'));
      expect(flow.draft!.version, draft.version);
      expect(flow.draft!.character.name, 'Lin Feng');
    },
  );

  test('a change asked at one line of the summary says which, and lands there', () async {
    final draft = await drafted();
    final skills = draft.linesOf(DraftPart.character, LineKind.skills).single;
    expect(await flow.revise(DraftPart.character, 'Add archery', about: LineKind.skills), isNull);
    final sent = backend.requests.lastWhere((r) => r.uri.path.endsWith('/revise')).json;
    expect(sent, {
      'target': 'character',
      'instruction': 'Add archery',
      'about': 'skills',
      'expected_version': draft.version,
    });
    expect(flow.draft!.linesOf(DraftPart.character, LineKind.skills), ['$skills Archery.']);
    // Asked of the whole part, nothing names a line.
    expect(await flow.revise(DraftPart.world, 'Add a hidden demonic cult'), isNull);
    final whole = backend.requests.lastWhere((r) => r.uri.path.endsWith('/revise')).json;
    expect(whole.containsKey('about'), isFalse);
  });

  test('how the story starts shows only when the player\'s own words name it (G1)', () async {
    // The starter's own words name the trial and the dead master, so both show. Nothing in them
    // names Ser Garrick: he is counted among the people kept back, never told.
    final draft = await drafted(premiseId: 'ashen-squire');
    List<LineKind> shown(Draft draft) => [for (final (_, line) in draft.openers) line.kind];
    expect(shown(draft), [LineKind.deadline, LineKind.question]);
    expect(draft.kept.people, 5);
    expect(draft.kept.events, 2);
    expect(draft.kept.questions, 1);
    expect([
      for (final part in DraftPart.values)
        for (final line in draft.partsOf(part)) line.text,
    ], everyElement(isNot(contains('Garrick'))));

    // Named in a change, he shows from then on, and one person fewer is kept back.
    expect(await flow.revise(DraftPart.world, 'Make Garrick my oldest friend'), isNull);
    final now = flow.draft!;
    expect(shown(now), [LineKind.deadline, LineKind.question, LineKind.person]);
    expect(now.kept.people, 4);
    expect(now.kept.events, 2);
  });

  test('a stale copy is refused before any charge, and the latest draft is loaded', () async {
    final draft = await drafted();
    // The same draft changes somewhere else.
    await api.patch('/v1/drafts/${draft.id}', {
      'advanced': {'difficulty': 'story'},
      'expected_version': draft.version,
    });
    final before = await balance();
    final failure = await flow.revise(DraftPart.world, 'Add a hidden demonic cult');
    expect(
      failure,
      isA<ApiException>().having((e) => e.code, 'code', ApiErrorCode.versionConflict),
    );
    expect(await balance(), before);
    expect(flow.draft!.version, draft.version + 1);
    expect(flow.draft!.advanced.difficulty, Difficulty.story);
    // Made again on the latest copy, it goes through.
    expect(await flow.revise(DraftPart.world, 'Add a hidden demonic cult'), isNull);
  });

  test('out of credits, nothing is drafted and the premise stays', () async {
    final balanceNow = await balance();
    backend.data.account.charge(
      FakeAuthState.demoUserId,
      kind: 'turn',
      cents: balanceNow - 1,
      now: DateTime.now(),
    );
    await flow.create(premise: 'A lighthouse keeper finds a door in the sea.', rating: Rating.teen);
    expect(flow.stage, CreateStage.premise);
    expect(flow.draft, isNull);
    expect(
      flow.error,
      isA<ApiException>().having((e) => e.code, 'code', ApiErrorCode.outOfCredits),
    );
    expect(flow.hasUnsavedDraft, isFalse);
  });

  test('a free change still saves when credits run out', () async {
    await drafted();
    final balanceNow = await balance();
    backend.data.account.charge(
      FakeAuthState.demoUserId,
      kind: 'turn',
      cents: balanceNow,
      now: DateTime.now(),
    );
    expect(await flow.edit(const DraftEdit(physics: Physics.strict)), isNull);
    final failure = await flow.revise(DraftPart.world, 'Add hidden vampires');
    expect(failure, isA<ApiException>().having((e) => e.code, 'code', ApiErrorCode.outOfCredits));
  });

  test('a teen account cannot draft Mature (F8)', () async {
    final teen = fakeApi();
    // A fresh backend whose demo account is under 17.
    final now = teen.backend.now();
    teen.backend.data.auth.users[FakeAuthState.demoUserId]!['birth_date'] = DateTime.utc(
      now.year - 14,
      now.month,
      now.day,
    ).toIso8601String().substring(0, 10);
    final session =
        await teen.api.post('/v1/auth/login', {
              'email': FakeAuthState.demoEmail,
              'password': FakeAuthState.demoPassword,
            }, authenticated: false)
            as JsonMap;
    teen.tokens.accessToken = session['access_token'] as String;
    final teenFlow = CreateFlow(DraftRepository(teen.api));
    addTearDown(teenFlow.dispose);
    await teenFlow.create(premiseId: 'outer-disciple', rating: Rating.mature);
    expect(
      teenFlow.error,
      isA<ApiException>().having((e) => e.code, 'code', ApiErrorCode.forbidden),
    );
    await teenFlow.create(premiseId: 'outer-disciple', rating: Rating.teen);
    expect(teenFlow.stage, CreateStage.review);
  });

  test('starting makes a story at turn 0 that remembers the drafted character', () async {
    final draft = await drafted();
    final storyId = await flow.start();
    expect(storyId, isNotNull);
    expect(flow.hasUnsavedDraft, isFalse);
    final sent = backend.requests.lastWhere((r) => r.uri.path.endsWith('/start')).json;
    expect(sent['expected_version'], draft.version);

    // Starting again opens the same story, without asking the server.
    expect(await flow.start(), storyId);

    final summary = (await LibraryRepository(api).stories()).firstWhere((s) => s.id == storyId);
    expect(summary.title, draft.title);
    expect(summary.turn, 0);
    expect(summary.coverUrl, isNotNull);
    final memory = MemoryView.fromJson(await api.get('/v1/stories/$storyId/memory') as JsonMap);
    expect(memory.character!.name, 'Lin Feng');
    expect(memory.character!.lines, [for (final line in draft.characterParts) line.text]);
    expect(memory.sections, isEmpty);
  });

  test('a stale copy starts nothing, and the latest draft is loaded to start from (T10)', () async {
    final draft = await drafted();
    final stories = (await LibraryRepository(api).stories()).length;
    await api.patch('/v1/drafts/${draft.id}', {
      'advanced': {'difficulty': 'story'},
      'expected_version': draft.version,
    });

    expect(await flow.start(), isNull);
    expect(
      flow.error,
      isA<ApiException>().having((e) => e.code, 'code', ApiErrorCode.versionConflict),
    );
    expect(await LibraryRepository(api).stories(), hasLength(stories));
    expect(flow.draft!.version, draft.version + 1);

    expect(await flow.start(), isNotNull);
  });

  test('nothing can change while the story starts', () async {
    await drafted();
    final starting = flow.start();
    expect(flow.busy, isTrue);
    expect(await flow.edit(const DraftEdit(physics: Physics.strict)), isA<StateError>());
    expect(await starting, isNotNull);
    expect(backend.requests.where((r) => r.method == 'PATCH'), isEmpty);
  });

  test('a draft started elsewhere answers with its story', () async {
    final draft = await drafted();
    final started = await api.post('/v1/drafts/${draft.id}/start', {}) as JsonMap;
    final failure = await flow.edit(const DraftEdit(physics: Physics.strict));
    expect(failure, isA<ApiException>().having((e) => e.code, 'code', ApiErrorCode.forbidden));
    expect(flow.draft!.storyId, started['story_id']);
    expect(await flow.start(), started['story_id']);
  });

  test('a real person is refused at the field that names them, free of charge (G12)', () async {
    final draft = await drafted();
    final before = await balance();
    final failure = await flow.revise(DraftPart.world, 'Add [fail:real_person] as the sect master');
    expect(
      failure,
      isA<ApiException>()
          .having((e) => e.code, 'code', ApiErrorCode.validationError)
          .having((e) => (e.fields.single as Map)['field'], 'field', 'instruction')
          .having((e) => (e.fields.single as Map)['type'], 'type', 'real_person'),
    );
    final edit = await flow.edit(const DraftEdit(name: '[fail:real_person]'));
    expect((edit! as ApiException).fields.single, containsPair('field', 'character.name'));
    final rules = [...draft.advanced.rules, const DraftRule(text: '[fail:real_person] is a god.')];
    final rule = await flow.edit(DraftEdit(rules: rules));
    expect(
      (rule! as ApiException).fields.single,
      containsPair('field', 'advanced.rules.${rules.length - 1}.text'),
    );
    expect(await balance(), before);
    expect(flow.draft!.version, draft.version);
  });

  group('a change whose reply was lost', () {
    // The server finishes a change whatever becomes of the connection. On 2026-11-11 a change
    // to one row took the model 111 s, the phone had dropped the request by then, and asking
    // again failed against the draft the first one had changed.
    CreateFlow lossy(
      Future<Draft> Function(Future<Draft> Function() save) reply, {
      Duration wait = const Duration(milliseconds: 200),
    }) {
      final lossy = CreateFlow(
        _Lossy(api, reply),
        landingPoll: const Duration(milliseconds: 5),
        landingWait: wait,
      );
      addTearDown(lossy.dispose);
      return lossy;
    }

    Never dropped() => throw const ApiException(ApiErrorCode.network);

    test('is found saved, and nothing is asked twice', () async {
      final flow = lossy((save) async {
        await save();
        dropped();
      });
      await flow.create(premiseId: 'outer-disciple', rating: Rating.mature);
      final draft = flow.draft!;

      expect(await flow.revise(DraftPart.character, 'Add alchemy', about: LineKind.skills), isNull);

      expect(flow.draft!.version, draft.version + 1);
      expect(flow.draft!.linesOf(DraftPart.character, LineKind.skills).single, contains('Alchemy'));
      expect(backend.requests.where((r) => r.uri.path.endsWith('/revise')), hasLength(1));
      expect(flow.busy, isFalse);
    });

    test('is waited for while the server still works on it', () async {
      final flow = lossy((save) async {
        // The reply is lost at once; the change itself lands a little later.
        unawaited(Future<void>.delayed(const Duration(milliseconds: 30), save));
        dropped();
      });
      await flow.create(premiseId: 'outer-disciple', rating: Rating.mature);
      final draft = flow.draft!;

      final changing = flow.revise(DraftPart.world, 'Add hidden vampires');
      expect(flow.busy, isTrue);
      // Nothing else is sent under a change that may still land.
      expect(await flow.edit(const DraftEdit(physics: Physics.strict)), isA<StateError>());

      expect(await changing, isNull);
      expect(flow.draft!.version, draft.version + 1);
    });

    test('shows its failure once the server has had its time, when nothing landed', () async {
      final flow = lossy((save) async => dropped(), wait: const Duration(milliseconds: 20));
      await flow.create(premiseId: 'outer-disciple', rating: Rating.mature);
      final draft = flow.draft!;
      final reads = backend.requests.where((r) => r.method == 'GET').length;

      final failure = await flow.revise(DraftPart.world, 'Add hidden vampires');

      expect(failure, isA<ApiException>().having((e) => e.code, 'code', ApiErrorCode.network));
      expect(flow.draft!.version, draft.version);
      expect(backend.requests.where((r) => r.method == 'GET').length, greaterThan(reads + 1));
      expect(flow.busy, isFalse);
    });

    test('is looked for once after a free change, which the server saves at once', () async {
      final flow = lossy((save) async => dropped());
      await flow.create(premiseId: 'outer-disciple', rating: Rating.mature);
      final reads = backend.requests.where((r) => r.method == 'GET').length;

      final failure = await flow.edit(const DraftEdit(name: 'Mara Quill'));

      expect(failure, isA<ApiException>());
      expect(backend.requests.where((r) => r.method == 'GET').length, reads + 1);
    });

    test('is looked for once when a proxy answered in the server\'s place', () async {
      // A 502 page says nothing of the change either way, and the server isn't known to be
      // working on it: one look, with no wait.
      final flow = lossy(
        (save) async => throw const ApiException(ApiErrorCode.server, status: 502),
        wait: const Duration(seconds: 30),
      );
      await flow.create(premiseId: 'outer-disciple', rating: Rating.mature);
      final reads = backend.requests.where((r) => r.method == 'GET').length;

      final failure = await flow.revise(DraftPart.world, 'Add hidden vampires');

      expect(failure, isA<ApiException>().having((e) => e.code, 'code', ApiErrorCode.server));
      expect(backend.requests.where((r) => r.method == 'GET').length, reads + 1);
    });

    test('is no reason to look when the server itself refused the change', () async {
      final flow = lossy((save) => save());
      await flow.create(premiseId: 'outer-disciple', rating: Rating.mature);
      final reads = backend.requests.where((r) => r.method == 'GET').length;

      final failure = await flow.revise(DraftPart.world, 'Add [fail:llm_unavailable]');

      expect(
        failure,
        isA<ApiException>().having((e) => e.code, 'code', ApiErrorCode.llmUnavailable),
      );
      expect(backend.requests.where((r) => r.method == 'GET').length, reads);
    });
  });

  test('a failed draft says why, and a trigger names the failure', () async {
    await flow.create(premise: 'A quiet village [fail:llm_unavailable]', rating: Rating.teen);
    expect(flow.stage, CreateStage.premise);
    expect(
      flow.error,
      isA<ApiException>().having((e) => e.code, 'code', ApiErrorCode.llmUnavailable),
    );
    flow.clearError();
    expect(flow.error, isNull);
  });
}

/// The drafts of a phone on a bad connection: each change is sent as [_reply] decides, which is
/// handed the real request and may lose its answer.
class _Lossy extends DraftRepository {
  _Lossy(super.api, this._reply);

  final Future<Draft> Function(Future<Draft> Function() save) _reply;

  @override
  Future<Draft> edit(Draft draft, DraftEdit edit) => _reply(() => super.edit(draft, edit));

  @override
  Future<Draft> revise(Draft draft, DraftPart part, String instruction, {LineKind? about}) =>
      _reply(() => super.revise(draft, part, instruction, about: about));
}

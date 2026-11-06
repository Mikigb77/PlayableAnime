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
    expect(draft.worldLines, isNotEmpty);
    expect(draft.characterLines, isNotEmpty);
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
      DraftEdit.lines(DraftPart.world, [...draft.worldLines.skip(1)]),
      DraftEdit.lines(DraftPart.character, [
        ...draft.characterLines,
        'Hates the smell of incense.',
      ]),
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
    expect(flow.draft!.characterLines.last, 'Me older, with a scar.');
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
    expect(memory.character!.lines, draft.characterLines);
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
    final lines = [...draft.worldLines]..[2] = 'Ruled by [fail:real_person].';
    final edit = await flow.edit(DraftEdit.lines(DraftPart.world, lines));
    expect((edit! as ApiException).fields.single, containsPair('field', 'world_lines.2'));
    final rules = [...draft.advanced.rules, const DraftRule(text: '[fail:real_person] is a god.')];
    final rule = await flow.edit(DraftEdit(rules: rules));
    expect(
      (rule! as ApiException).fields.single,
      containsPair('field', 'advanced.rules.${rules.length - 1}.text'),
    );
    expect(await balance(), before);
    expect(flow.draft!.version, draft.version);
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

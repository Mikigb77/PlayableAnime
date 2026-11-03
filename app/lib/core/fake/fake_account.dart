import '../json.dart';
import 'fake_auth.dart';
import 'fake_backend.dart';

/// Fake account and credits (K1, K2, T12). Owned by the accounts work (WS13).
class FakeAccountState {
  /// The starter credit every new account gets (K1).
  static const starterCents = 50;

  final _ledger = <String, List<JsonMap>>{};

  List<JsonMap> ledgerOf(String userId) => _ledger.putIfAbsent(
    userId,
    () => [
      {
        'id': 'ledger_starter_$userId',
        'kind': 'starter',
        'amount_cents': starterCents,
        'balance_after_cents': starterCents,
        'created_at': '2026-11-01T09:00:00Z',
      },
    ],
  );

  num balanceOf(String userId) => ledgerOf(userId).last['balance_after_cents'] as num;

  /// Debits [cents]; a picture never takes the balance below zero (M7), so callers check first.
  void charge(
    String userId, {
    required String kind,
    required num cents,
    required DateTime now,
    String? storyId,
    int? turn,
  }) {
    final ledger = ledgerOf(userId);
    final after = balanceOf(userId) - cents;
    ledger.add({
      'id': 'ledger_${ledger.length}_$userId',
      'kind': kind,
      'amount_cents': -cents,
      'balance_after_cents': after,
      'story_id': ?storyId,
      'turn': ?turn,
      'created_at': now.toUtc().toIso8601String(),
    });
  }
}

void registerAccountRoutes(FakeBackend b) {
  final users = b.data.auth.users;

  b.route('GET', '/v1/me', (r) => FakeResponse.json(fakeUserJson(b, r.userId!)));

  b.route('PATCH', '/v1/me', (r) {
    final user = users[r.userId!]!;
    if (r.json['display_name'] case final String name) user['display_name'] = name;
    if (r.json['content_prefs'] case final JsonMap prefs) {
      user['content_prefs'] = {...user['content_prefs'] as JsonMap, ...prefs};
    }
    return FakeResponse.json(fakeUserJson(b, r.userId!));
  });

  b.route('DELETE', '/v1/me', (r) {
    b.data.stories.deleteAllOf(r.userId!);
    if (r.userId != FakeAuthState.demoUserId) users.remove(r.userId);
    return FakeResponse.noContent;
  });

  b.route(
    'GET',
    '/v1/me/export',
    (r) => FakeResponse.json({
      'user': fakeUserJson(b, r.userId!),
      'stories': [
        for (final story in b.data.stories.ownedBy(r.userId!)) story.toJson(allScenes: true),
      ],
    }),
  );

  b.route('GET', '/v1/me/credits', (r) {
    final limit = int.tryParse(r.query('limit') ?? '') ?? 50;
    final ledger = b.data.account.ledgerOf(r.userId!);
    return FakeResponse.json({
      'balance_cents': b.data.account.balanceOf(r.userId!),
      'unlimited': false,
      'entries': ledger.reversed.take(limit).toList(),
    });
  });
}

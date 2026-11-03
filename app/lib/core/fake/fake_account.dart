import '../json.dart';
import 'fake_auth.dart';
import 'fake_backend.dart';

/// Fake account and credits (K1, K2, K7, T12), matching the backend's billing app. Owned by the
/// accounts work (WS13).
///
/// The demo and owner accounts start with the starter credit. The owner plays free: their costs
/// are recorded at zero charge, so their ledger still shows what they used (K7).
class FakeAccountState {
  FakeAccountState() {
    final seeded = DateTime.utc(2026, 11, 1, 9);
    grantStarter(FakeAuthState.demoUserId, seeded);
    grantStarter(FakeAuthState.ownerUserId, seeded);
    unlimited.add(FakeAuthState.ownerUserId);
  }

  /// The starter credit a verified account gets once (K1).
  static const starterCents = 50;

  final _ledger = <String, List<JsonMap>>{};

  /// Accounts whose costs are recorded at zero charge (the owner, K7).
  final unlimited = <String>{};

  /// Oldest first.
  List<JsonMap> ledgerOf(String userId) => _ledger.putIfAbsent(userId, () => []);

  num balanceOf(String userId) => ledgerOf(userId).lastOrNull?['balance_after_cents'] as num? ?? 0;

  void grantStarter(String userId, DateTime now) {
    final ledger = ledgerOf(userId);
    if (ledger.any((e) => e['kind'] == 'starter')) return;
    ledger.add({
      'id': 'ledger_starter_$userId',
      'kind': 'starter',
      'amount_cents': starterCents,
      'balance_after_cents': balanceOf(userId) + starterCents,
      'created_at': now.toUtc().toIso8601String(),
    });
  }

  /// Debits [cents]. A charge larger than what is left takes the balance to zero, never below
  /// (K2); callers that must not overdraw, such as pictures (M7), check first.
  void charge(
    String userId, {
    required String kind,
    required num cents,
    required DateTime now,
    String? storyId,
    int? turn,
  }) {
    final ledger = ledgerOf(userId);
    final balance = balanceOf(userId);
    final amount = unlimited.contains(userId) ? 0 : (cents > balance ? balance : cents);
    ledger.add({
      'id': 'ledger_${ledger.length}_$userId',
      'kind': kind,
      'amount_cents': amount == 0 ? 0 : -amount,
      'balance_after_cents': balance - amount,
      'story_id': ?storyId,
      'turn': ?turn,
      'created_at': now.toUtc().toIso8601String(),
    });
  }

  void delete(String userId) => _ledger.remove(userId);
}

void registerAccountRoutes(FakeBackend b) {
  final users = b.data.auth.users;

  b.route('GET', '/v1/me', (r) => FakeResponse.json(fakeUserJson(b, r.userId!)));

  b.route('PATCH', '/v1/me', (r) {
    final user = users[r.userId!]!;
    final body = r.json;
    if (body['display_name'] case final String raw) {
      final name = raw.split(RegExp(r'\s+')).where((w) => w.isNotEmpty).join(' ');
      if (name.isEmpty || raw.length > 80) {
        throw const FakeError(400, 'validation_error', 'Enter a name.', {
          'fields': [
            {
              'field': 'display_name',
              'source': 'body',
              'message': 'Enter a name.',
              'type': 'missing',
            },
          ],
        });
      }
      user['display_name'] = name;
    }
    if (body['content_prefs'] case final JsonMap prefs) {
      final gore = prefs['gore'];
      if (gore != null && !const {'low', 'medium', 'high'}.contains(gore)) {
        throw const FakeError.validation("gore must be 'low', 'medium' or 'high'");
      }
      user['content_prefs'] = {
        ...user['content_prefs'] as JsonMap,
        for (final e in prefs.entries)
          if (e.value != null) e.key: e.value,
      };
    }
    return FakeResponse.json(fakeUserJson(b, r.userId!));
  });

  b.route('DELETE', '/v1/me', (r) {
    final userId = r.userId!;
    final storyIds = {for (final story in b.data.stories.ownedBy(userId)) story.id};
    b.data.reports.removeWhere((report) => storyIds.contains(report['story_id']));
    b.data.pictures.charged.removeWhere((key) => storyIds.any((id) => key.startsWith('$id-')));
    b.data.stories.deleteAllOf(userId);
    b.data.account.delete(userId);
    b.data.auth.delete(userId);
    if (userId == FakeAuthState.demoUserId) {
      // The demo account comes back fresh, with its starter credit and its story.
      b.data.account.grantStarter(userId, b.now());
      b.data.stories.seed(ownerId: userId);
    }
    return FakeResponse.noContent;
  });

  b.route('GET', '/v1/me/export', (r) {
    final stories = b.data.stories.ownedBy(r.userId!).toList();
    final expires = b.now().toUtc().add(const Duration(hours: 1)).toIso8601String();
    return FakeResponse.json({
      'user': fakeUserJson(b, r.userId!),
      'stories': [for (final story in stories) story.toJson(allScenes: true)],
      'images': [
        for (final story in stories)
          for (final scene in story.scenes)
            if (scene['image']
                case final JsonMap image && {'status': 'ready', 'image_id': final String id})
              {
                'id': id,
                'story_id': story.id,
                'kind': image['kind'],
                'subject': scene['turn'].toString(),
                'version': 1,
                'turns': [scene['turn']],
                'url': image['url'],
                'expires_at': expires,
                'created_at': scene['created_at'],
              },
      ],
      'reports': [
        for (final report in b.data.reports)
          if (stories.any((story) => story.id == report['story_id']))
            {
              'story_id': report['story_id'],
              'turn': int.tryParse('${report['turn']}') ?? report['turn'],
              'category': report['category'],
              'note': report['note'],
              'block': report['block'] ?? false,
              'status': 'open',
              'created_at': report['created_at'] ?? b.now().toUtc().toIso8601String(),
            },
      ],
    });
  });

  b.route('GET', '/v1/me/credits', (r) {
    final limit = int.tryParse(r.query('limit') ?? '50');
    if (limit == null || limit < 1 || limit > 200) {
      throw const FakeError(400, 'validation_error', 'limit must be 1 to 200', {
        'fields': [
          {
            'field': 'limit',
            'source': 'query',
            'message': 'Input should be between 1 and 200',
            'type': 'less_than_equal',
          },
        ],
      });
    }
    final userId = r.userId!;
    final ledger = b.data.account.ledgerOf(userId);
    return FakeResponse.json({
      'balance_cents': b.data.account.balanceOf(userId),
      'unlimited': b.data.account.unlimited.contains(userId),
      'entries': ledger.reversed.take(limit).toList(),
    });
  });
}

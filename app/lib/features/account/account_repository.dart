import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/api_client.dart';
import '../../core/api/api_error.dart';
import '../../core/api/api_providers.dart';
import '../../core/json.dart';
import '../../core/session/session_controller.dart';
import 'account_models.dart';

/// The account endpoints in docs/API.md (T12, K1, K2, F7).
class AccountRepository {
  const AccountRepository(this._api);

  final ApiClient _api;

  Future<AccountUser> me() async => AccountUser.fromJson(await _api.get('/v1/me') as JsonMap);

  /// Changes only what is passed; inside the preferences, only the keys passed (API.md).
  Future<AccountUser> update({String? displayName, JsonMap? contentPrefs}) async =>
      AccountUser.fromJson(
        await _api.patch('/v1/me', {'display_name': ?displayName, 'content_prefs': ?contentPrefs})
            as JsonMap,
      );

  /// How many ledger entries the credits page reads (the API allows up to 200).
  static const creditsPage = 100;

  Future<CreditsHistory> credits({int limit = creditsPage}) async => CreditsHistory.fromJson(
    await _api.get('/v1/me/credits', query: {'limit': '$limit'}) as JsonMap,
  );

  /// Everything the account holds, as the indented JSON file the player downloads (T12, M4).
  Future<Uint8List> export() async {
    final data = await _api.get('/v1/me/export');
    if (data is! JsonMap) throw const ApiException(ApiErrorCode.server);
    return utf8.encode(const JsonEncoder.withIndent('  ').convert(data));
  }

  /// Deletes the account and everything it owns, at once and for good (T12).
  Future<void> deleteAccount() => _api.delete('/v1/me');

  /// The titles of the player's stories by id, for naming ledger entries. Best effort: an empty
  /// map when the list can't be read.
  Future<Map<String, String>> storyTitles() async {
    try {
      final list = await _api.get('/v1/stories');
      return {
        for (final story in list as List<Object?>)
          if (story case {'id': final String id, 'title': final String title}) id: title,
      };
    } on Object {
      return const {};
    }
  }
}

final accountRepositoryProvider = Provider<AccountRepository>(
  (ref) => AccountRepository(ref.watch(apiClientProvider)),
);

/// The signed-in account, fresh from `GET /v1/me`. Screens show the session's copy of the user
/// while it loads, so nothing flashes.
class MeController extends AsyncNotifier<AccountUser> {
  @override
  Future<AccountUser> build() async {
    // A different account (or none) starts over.
    final userId = ref.watch(sessionProvider.select((s) => s.session?.user['id']));
    if (userId == null) throw const ApiException(ApiErrorCode.unauthenticated);
    return ref.read(accountRepositoryProvider).me();
  }

  /// The account as last seen: the latest answer, or the session's copy before the first one.
  AccountUser? get current =>
      state.value ??
      switch (ref.read(sessionProvider).session?.user) {
        final JsonMap user when user.isNotEmpty => AccountUser.fromJson(user),
        _ => null,
      };

  /// Changes started since this controller was built. A reload that overlaps one is dropped, since
  /// it may carry the values from before the change.
  var _writes = 0;

  /// Reads the account again while the screen keeps showing what it has.
  Future<void> reload() async {
    final writes = _writes;
    final user = await ref.read(accountRepositoryProvider).me();
    if (ref.mounted && writes == _writes) state = AsyncData(user);
  }

  /// Reads the account again in the background, as when the Account tab comes back. A first load
  /// still on its way is enough, and a failure leaves what is shown.
  void refreshQuietly() {
    if (state.isLoading) return;
    reload().ignore();
  }

  /// Starts a change: a first load still on its way would land on top of it, so it lands first.
  Future<void> _beginWrite() async {
    _writes++;
    if (state.isLoading) await future.then<void>((_) {}, onError: (Object _) {});
  }

  Future<void> rename(String displayName) async {
    await _beginWrite();
    final user = await ref.read(accountRepositoryProvider).update(displayName: displayName);
    if (ref.mounted) state = AsyncData(user);
  }

  /// Saves one content preference (F7) at once and puts it back if the server refuses it.
  Future<void> updatePrefs(ContentPrefs prefs) async {
    await _beginWrite();
    if (!ref.mounted) return;
    final before = current;
    if (before == null) return;
    final changed = {
      for (final e in prefs.toJson().entries)
        if (before.prefs.toJson()[e.key] != e.value) e.key: e.value,
    };
    if (changed.isEmpty) return;
    state = AsyncData(before.copyWith(prefs: prefs));
    try {
      final user = await ref.read(accountRepositoryProvider).update(contentPrefs: changed);
      if (ref.mounted) state = AsyncData(user);
    } on Object {
      if (ref.mounted) state = AsyncData(before);
      rethrow;
    }
  }
}

final meProvider = AsyncNotifierProvider<MeController, AccountUser>(MeController.new);

/// The balance and ledger for the credits page, read again each time it opens.
final creditsHistoryProvider = FutureProvider.autoDispose<CreditsHistory>((ref) {
  ref.watch(sessionProvider.select((s) => s.session?.user['id']));
  return ref.watch(accountRepositoryProvider).credits();
});

/// Story titles for the ledger, keyed by story id.
final ledgerStoryTitlesProvider = FutureProvider.autoDispose<Map<String, String>>((ref) {
  ref.watch(sessionProvider.select((s) => s.session?.user['id']));
  return ref.watch(accountRepositoryProvider).storyTitles();
});

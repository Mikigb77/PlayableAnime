import 'package:flutter/foundation.dart';

import '../../core/json.dart';

/// How much gore the world shows in a Mature story (F7). Teen stories never show gore.
enum GoreLevel {
  low,
  medium,
  high;

  static GoreLevel fromWire(Object? value) =>
      values.where((g) => g.name == value).firstOrNull ?? GoreLevel.medium;
}

/// The player's content preferences (F7): which themes the world and its people may start.
@immutable
class ContentPrefs {
  const ContentPrefs({this.gore = GoreLevel.medium, this.romance = true, this.darkThemes = true});

  factory ContentPrefs.fromJson(JsonMap? json) => ContentPrefs(
    gore: GoreLevel.fromWire(json?['gore']),
    romance: json?['romance'] as bool? ?? true,
    darkThemes: json?['dark_themes'] as bool? ?? true,
  );

  final GoreLevel gore;
  final bool romance;
  final bool darkThemes;

  ContentPrefs copyWith({GoreLevel? gore, bool? romance, bool? darkThemes}) => ContentPrefs(
    gore: gore ?? this.gore,
    romance: romance ?? this.romance,
    darkThemes: darkThemes ?? this.darkThemes,
  );

  JsonMap toJson() => {'gore': gore.name, 'romance': romance, 'dark_themes': darkThemes};

  @override
  bool operator ==(Object other) =>
      other is ContentPrefs &&
      other.gore == gore &&
      other.romance == romance &&
      other.darkThemes == darkThemes;

  @override
  int get hashCode => Object.hash(gore, romance, darkThemes);
}

/// The `User` object from docs/API.md.
@immutable
class AccountUser {
  const AccountUser({
    required this.id,
    required this.email,
    required this.displayName,
    this.isOwner = false,
    this.matureAllowed = false,
    this.prefs = const ContentPrefs(),
    this.balanceCents = 0,
    this.unlimited = false,
  });

  factory AccountUser.fromJson(JsonMap json) {
    final credits = json['credits'] as JsonMap? ?? const {};
    return AccountUser(
      id: json['id'] as String? ?? '',
      email: json['email'] as String? ?? '',
      displayName: json['display_name'] as String? ?? '',
      isOwner: json['role'] == 'owner',
      matureAllowed: json['max_rating'] == 'mature',
      prefs: ContentPrefs.fromJson(json['content_prefs'] as JsonMap?),
      balanceCents: credits['balance_cents'] as num? ?? 0,
      unlimited: credits['unlimited'] as bool? ?? false,
    );
  }

  final String id;
  final String email;
  final String displayName;

  /// The owner role (K7): unlimited credits and every feature.
  final bool isOwner;

  /// Whether the account may play Mature stories: from the 17th birthday (F8).
  final bool matureAllowed;

  final ContentPrefs prefs;

  /// Fractional: a turn costs about 2 cents (K2).
  final num balanceCents;
  final bool unlimited;

  /// The name to show: the display name, or the email when there is none.
  String get label => displayName.isNotEmpty ? displayName : email;

  AccountUser copyWith({String? displayName, ContentPrefs? prefs}) => AccountUser(
    id: id,
    email: email,
    displayName: displayName ?? this.displayName,
    isOwner: isOwner,
    matureAllowed: matureAllowed,
    prefs: prefs ?? this.prefs,
    balanceCents: balanceCents,
    unlimited: unlimited,
  );
}

/// What a ledger entry was for (K2).
enum LedgerKind {
  starter,
  turn,
  draft,
  image,

  /// A dictation written down online (V6).
  speech,
  topup,
  adjustment;

  static LedgerKind fromWire(Object? value) =>
      values.where((k) => k.name == value).firstOrNull ?? LedgerKind.adjustment;
}

/// One line of the credit ledger: `LedgerEntry` in docs/API.md.
@immutable
class LedgerEntry {
  const LedgerEntry({
    required this.id,
    required this.kind,
    required this.amountCents,
    required this.balanceAfterCents,
    required this.createdAt,
    this.storyId,
    this.turn,
  });

  factory LedgerEntry.fromJson(JsonMap json) => LedgerEntry(
    id: json['id'].toString(),
    kind: LedgerKind.fromWire(json['kind']),
    amountCents: json['amount_cents'] as num? ?? 0,
    balanceAfterCents: json['balance_after_cents'] as num? ?? 0,
    createdAt: DateTime.tryParse(json['created_at'] as String? ?? '')?.toLocal() ?? DateTime(2000),
    storyId: json['story_id'] as String?,
    turn: (json['turn'] as num?)?.toInt(),
  );

  final String id;
  final LedgerKind kind;

  /// Positive when credits are added, negative when spent, zero for the owner's recorded costs.
  final num amountCents;
  final num balanceAfterCents;
  final DateTime createdAt;
  final String? storyId;
  final int? turn;
}

/// `GET /v1/me/credits`: the balance and the newest ledger entries first.
@immutable
class CreditsHistory {
  const CreditsHistory({
    required this.balanceCents,
    required this.unlimited,
    required this.entries,
  });

  factory CreditsHistory.fromJson(JsonMap json) => CreditsHistory(
    balanceCents: json['balance_cents'] as num? ?? 0,
    unlimited: json['unlimited'] as bool? ?? false,
    entries: [
      for (final entry in json['entries'] as List<Object?>? ?? const [])
        if (entry is JsonMap) LedgerEntry.fromJson(entry),
    ],
  );

  final num balanceCents;
  final bool unlimited;
  final List<LedgerEntry> entries;
}

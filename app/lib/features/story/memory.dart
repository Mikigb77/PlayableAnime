/// What the player character knows (docs/API.md `MemoryView`, C6, G16): the people, places and
/// factions they have met, their goals and leads, the rumors they heard and their own deeds, all in
/// the world's words. The server leaves out everything the character doesn't know, so the app shows
/// what it gets and never guesses at the rest.
library;

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/api_providers.dart';
import '../../core/json.dart';

List<String> _lines(Object? json) => [
  for (final line in json as List? ?? const [])
    if (line is String && line.trim().isNotEmpty) line,
];

List<T> _list<T>(Object? json, T Function(JsonMap) fromJson) => [
  for (final item in json as List? ?? const [])
    if (item is JsonMap) fromJson(item),
];

class MemoryCharacter {
  const MemoryCharacter({required this.name, this.lines = const [], this.portraitUrl});

  factory MemoryCharacter.fromJson(JsonMap json) => MemoryCharacter(
    name: json['name'] as String? ?? '',
    lines: _lines(json['lines']),
    portraitUrl: json['portrait_url'] as String?,
  );

  final String name;
  final List<String> lines;
  final String? portraitUrl;
}

/// Whether someone is alive, as far as the character knows (C1, C6).
enum Fate { alive, dead, presumedDead, other }

class MemoryPerson {
  const MemoryPerson({
    required this.id,
    required this.name,
    this.lines = const [],
    this.attitudeLabel,
    this.portraitUrl,
    this.statusLabel = '',
  });

  factory MemoryPerson.fromJson(JsonMap json) => MemoryPerson(
    id: json['id'] as String? ?? '',
    name: json['name'] as String? ?? '',
    lines: _lines(json['lines']),
    attitudeLabel: json['attitude_label'] as String?,
    portraitUrl: json['portrait_url'] as String?,
    statusLabel: json['status_label'] as String? ?? '',
  );

  final String id;
  final String name;
  final List<String> lines;

  /// How they feel about the character, such as "Friendly". Only for people the character met.
  final String? attitudeLabel;
  final String? portraitUrl;

  /// "Alive", "Dead", "Presumed dead", "Missing" and so on, as the character believes.
  final String statusLabel;

  /// The engine words a status in English (`engine.visibility`), so these labels are stable.
  Fate get fate => switch (statusLabel.trim().toLowerCase()) {
    '' || 'alive' => Fate.alive,
    'dead' => Fate.dead,
    'presumed dead' => Fate.presumedDead,
    _ => Fate.other,
  };
}

class MemoryPlace {
  const MemoryPlace({required this.id, required this.name, this.lines = const [], this.imageUrl});

  factory MemoryPlace.fromJson(JsonMap json) => MemoryPlace(
    id: json['id'] as String? ?? '',
    name: json['name'] as String? ?? '',
    lines: _lines(json['lines']),
    imageUrl: json['image_url'] as String?,
  );

  final String id;
  final String name;
  final List<String> lines;
  final String? imageUrl;
}

class MemoryFaction {
  const MemoryFaction({
    required this.id,
    required this.name,
    this.lines = const [],
    this.standingLabel = '',
  });

  factory MemoryFaction.fromJson(JsonMap json) => MemoryFaction(
    id: json['id'] as String? ?? '',
    name: json['name'] as String? ?? '',
    lines: _lines(json['lines']),
    standingLabel: json['standing_label'] as String? ?? '',
  );

  final String id;
  final String name;
  final List<String> lines;

  /// Esteem and fear in words, such as "Respected, and a little feared" (W3).
  final String standingLabel;
}

/// A goal, lead, rumor or deed: one line of text and what the character knows about it.
class MemoryNote {
  const MemoryNote({required this.id, required this.text, this.labels = const []});

  final String id;
  final String text;

  /// When it was heard or done, who saw it, when it expires.
  final List<String> labels;

  static MemoryNote goal(JsonMap json) =>
      MemoryNote(id: json['id'] as String? ?? '', text: json['text'] as String? ?? '');

  static MemoryNote lead(JsonMap json) => MemoryNote(
    id: json['id'] as String? ?? '',
    text: json['text'] as String? ?? '',
    labels: [?json['expires_label'] as String?],
  );

  static MemoryNote rumor(JsonMap json) => MemoryNote(
    id: json['id'] as String? ?? '',
    text: json['text'] as String? ?? '',
    labels: [?json['heard_label'] as String?],
  );

  static MemoryNote deed(JsonMap json) => MemoryNote(
    id: json['id'] as String? ?? '',
    text: json['text'] as String? ?? '',
    labels: [?json['when_label'] as String?, ?json['known_label'] as String?],
  );
}

/// A plot line's state (N1).
enum ThreadStatus {
  open('open'),
  dormant('dormant'),
  resolved('resolved'),
  failed('failed'),
  abandoned('abandoned'),
  resolvedWithoutPlayer('resolved_without_player');

  const ThreadStatus(this.wire);

  final String wire;

  bool get isClosed => this != open && this != dormant;

  static ThreadStatus fromWire(Object? value) =>
      values.where((s) => s.wire == value).firstOrNull ?? open;
}

class MemoryThread {
  const MemoryThread({required this.id, required this.title, this.status = ThreadStatus.open});

  factory MemoryThread.fromJson(JsonMap json) => MemoryThread(
    id: json['id'] as String? ?? '',
    title: json['title'] as String? ?? '',
    status: ThreadStatus.fromWire(json['status']),
  );

  final String id;
  final String title;
  final ThreadStatus status;
}

/// The groups of the memory screen, in the order it shows them.
enum MemorySection { people, places, factions, goals, rumors, deeds, threads }

class MemoryView {
  const MemoryView({
    this.character,
    this.people = const [],
    this.places = const [],
    this.factions = const [],
    this.goals = const [],
    this.leads = const [],
    this.rumors = const [],
    this.deeds = const [],
    this.threads = const [],
  });

  factory MemoryView.fromJson(JsonMap json) => MemoryView(
    character: switch (json['character']) {
      final JsonMap character when (character['name'] as String? ?? '').isNotEmpty =>
        MemoryCharacter.fromJson(character),
      _ => null,
    },
    people: _list(json['people'], MemoryPerson.fromJson),
    places: _list(json['places'], MemoryPlace.fromJson),
    factions: _list(json['factions'], MemoryFaction.fromJson),
    goals: _list(json['goals'], MemoryNote.goal),
    leads: _list(json['leads'], MemoryNote.lead),
    rumors: _list(json['rumors'], MemoryNote.rumor),
    deeds: _list(json['deeds'], MemoryNote.deed),
    threads: _list(json['threads'], MemoryThread.fromJson),
  );

  final MemoryCharacter? character;
  final List<MemoryPerson> people;
  final List<MemoryPlace> places;
  final List<MemoryFaction> factions;
  final List<MemoryNote> goals;
  final List<MemoryNote> leads;

  /// Always unconfirmed: the character heard them and can't tell if they are true (W13, C6).
  final List<MemoryNote> rumors;
  final List<MemoryNote> deeds;
  final List<MemoryThread> threads;

  /// How many entries a group holds. Goals and leads share one.
  int count(MemorySection section) => switch (section) {
    MemorySection.people => people.length,
    MemorySection.places => places.length,
    MemorySection.factions => factions.length,
    MemorySection.goals => goals.length + leads.length,
    MemorySection.rumors => rumors.length,
    MemorySection.deeds => deeds.length,
    MemorySection.threads => threads.length,
  };

  /// The groups with something in them.
  List<MemorySection> get sections => [
    for (final section in MemorySection.values)
      if (count(section) > 0) section,
  ];
}

/// `GET /v1/stories/{id}/memory`.
final memoryProvider = FutureProvider.autoDispose.family<MemoryView, String>((ref, storyId) async {
  final json = await ref
      .watch(apiClientProvider)
      .get('/v1/stories/${Uri.encodeComponent(storyId)}/memory');
  return MemoryView.fromJson(json as JsonMap);
});

/// What the player character knows (docs/API.md `MemoryView`, C6, G16): the people, places and
/// factions they have met, their goals and leads, the rumors they heard and their own deeds, all in
/// the world's words. The server leaves out everything the character doesn't know, so the app shows
/// what it gets and never guesses at the rest.
library;

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/api_providers.dart';
import '../../core/json.dart';

List<String> _lines(Object? json) => [
  for (final line in json is List ? json : const [])
    if (line is String && line.trim().isNotEmpty) line,
];

List<T> _list<T>(Object? json, T Function(JsonMap) fromJson) => [
  for (final item in json is List ? json : const [])
    if (item is JsonMap) fromJson(item),
];

String _text(Object? json) => json is String ? json : '';

String? _label(Object? json) => json is String && json.trim().isNotEmpty ? json : null;

class MemoryCharacter {
  const MemoryCharacter({required this.name, this.lines = const [], this.portraitUrl});

  factory MemoryCharacter.fromJson(JsonMap json) => MemoryCharacter(
    name: _text(json['name']),
    lines: _lines(json['lines']),
    portraitUrl: _label(json['portrait_url']),
  );

  final String name;
  final List<String> lines;
  final String? portraitUrl;
}

/// Whether someone is alive, as far as the character knows (C1, C6).
enum Fate { alive, dead, presumedDead, other }

/// How someone comes across toward the character (W4): what they show, warmest first.
enum Attitude {
  warm,
  friendly,
  neutral,
  cold,
  hostile;

  static Attitude? parse(Object? json) => values.where((a) => a.name == json).firstOrNull;
}

class MemoryPerson {
  const MemoryPerson({
    required this.id,
    required this.name,
    this.lines = const [],
    this.attitude,
    this.attitudeLabel,
    this.portraitUrl,
    this.status,
    this.presumed = false,
    this.statusLabel = '',
  });

  factory MemoryPerson.fromJson(JsonMap json) => MemoryPerson(
    id: _text(json['id']),
    name: _text(json['name']),
    lines: _lines(json['lines']),
    attitude: Attitude.parse(json['attitude']),
    attitudeLabel: _label(json['attitude_label']),
    portraitUrl: _label(json['portrait_url']),
    status: _label(json['status']),
    presumed: json['presumed'] == true,
    statusLabel: _text(json['status_label']),
  );

  final String id;
  final String name;
  final List<String> lines;

  /// What [attitudeLabel] says, for picking its color. Null for someone they never met, and
  /// from a server older than it.
  final Attitude? attitude;

  /// How they feel about the character, such as "Friendly". Only for people the character met.
  final String? attitudeLabel;
  final String? portraitUrl;

  /// What [statusLabel] says: "alive", "missing", "dead". Null from a server older than it.
  final String? status;

  /// A death the character only believes in (C1).
  final bool presumed;

  /// "Alive", "Dead", "Presumed dead", "Missing" and so on, as the character believes, in the
  /// story's language.
  final String statusLabel;

  /// Read from [status], which says the same in every language. A server from before it sent
  /// only the label, which it worded in English.
  Fate get fate => switch (status ?? statusLabel.trim().toLowerCase()) {
    '' || 'alive' => Fate.alive,
    'dead' => presumed ? Fate.presumedDead : Fate.dead,
    'presumed dead' => Fate.presumedDead,
    _ => Fate.other,
  };
}

class MemoryPlace {
  const MemoryPlace({required this.id, required this.name, this.lines = const [], this.imageUrl});

  factory MemoryPlace.fromJson(JsonMap json) => MemoryPlace(
    id: _text(json['id']),
    name: _text(json['name']),
    lines: _lines(json['lines']),
    imageUrl: _label(json['image_url']),
  );

  final String id;
  final String name;
  final List<String> lines;
  final String? imageUrl;
}

/// How well a faction thinks of the character (W3), best first.
enum Esteem {
  admired,
  respected,
  neutral,
  disliked,
  despised;

  static Esteem parse(Object? json) =>
      values.firstWhere((e) => e.name == json, orElse: () => neutral);

  bool get good => index < neutral.index;
  bool get bad => index > neutral.index;
}

class MemoryFaction {
  const MemoryFaction({
    required this.id,
    required this.name,
    this.lines = const [],
    this.esteem = Esteem.neutral,
    this.feared = false,
    this.standingLabel = '',
  });

  factory MemoryFaction.fromJson(JsonMap json) => MemoryFaction(
    id: _text(json['id']),
    name: _text(json['name']),
    lines: _lines(json['lines']),
    esteem: Esteem.parse(json['esteem']),
    feared: json['dread'] == 'wary' || json['dread'] == 'feared',
    standingLabel: _text(json['standing_label']),
  );

  final String id;
  final String name;
  final List<String> lines;

  /// What [standingLabel] says of their regard, for picking its color.
  final Esteem esteem;

  /// Whether they are wary of the character, or fear them.
  final bool feared;

  /// Esteem and fear in words, such as "Respected and feared" (W3).
  final String standingLabel;
}

/// What the character knows of a rumor they heard (C6): only that people say it, that it is so,
/// or that it isn't. The server says it is so or isn't only where the character knows for
/// themselves: they did or saw what it tells, or were there when it happened.
enum RumorCertainty {
  unconfirmed('unconfirmed'),
  confirmed('confirmed'),
  wrong('false');

  const RumorCertainty(this.wire);

  final String wire;

  /// A server older than `certainty` sends only `unconfirmed`, always true.
  static RumorCertainty fromJson(JsonMap json) =>
      values.where((c) => c.wire == json['certainty']).firstOrNull ?? unconfirmed;
}

/// Something the character means to do (N2).
class MemoryGoal {
  const MemoryGoal({required this.id, required this.text});

  factory MemoryGoal.fromJson(JsonMap json) =>
      MemoryGoal(id: _text(json['id']), text: _text(json['text']));

  final String id;
  final String text;
}

/// Something on offer that the character could take up, and until when (W13).
class MemoryLead {
  const MemoryLead({required this.id, required this.text, this.expiresLabel});

  factory MemoryLead.fromJson(JsonMap json) => MemoryLead(
    id: _text(json['id']),
    text: _text(json['text']),
    expiresLabel: _label(json['expires_label']),
  );

  final String id;
  final String text;

  /// "Ends in 3 hours", for one that runs out.
  final String? expiresLabel;
}

/// What people say that reached the character (W2), and what they know of it.
class MemoryRumor {
  const MemoryRumor({
    required this.id,
    required this.text,
    this.heardLabel,
    this.certainty = RumorCertainty.unconfirmed,
  });

  factory MemoryRumor.fromJson(JsonMap json) => MemoryRumor(
    id: _text(json['id']),
    text: _text(json['text']),
    heardLabel: _label(json['heard_label']),
    certainty: RumorCertainty.fromJson(json),
  );

  final String id;
  final String text;

  /// "Heard 2 hours ago".
  final String? heardLabel;
  final RumorCertainty certainty;
}

/// Who saw a deed, as far as the character knows (W2, C6).
enum DeedSeen {
  /// Someone else's deed, which the character saw.
  watched('watched'),

  /// Someone else's deed, which the character heard of.
  heardOf('heard_of'),

  /// Their own, with someone they noticed watching.
  seen('seen'),

  /// Their own, done where anyone could see.
  public('public'),

  /// Their own, with nobody watching as far as they know.
  unseen('unseen');

  const DeedSeen(this.wire);

  final String wire;

  static DeedSeen? parse(Object? json) => values.where((s) => s.wire == json).firstOrNull;
}

/// Something done, by the character or by someone else they know of (W1).
class MemoryDeed {
  const MemoryDeed({
    required this.id,
    required this.text,
    this.whenLabel,
    this.knownLabel,
    this.seen,
  });

  factory MemoryDeed.fromJson(JsonMap json) => MemoryDeed(
    id: _text(json['id']),
    text: _text(json['text']),
    whenLabel: _label(json['when_label']),
    knownLabel: _label(json['known_label']),
    seen: DeedSeen.parse(json['seen']),
  );

  final String id;
  final String text;

  /// When it was done, as the world dates it.
  final String? whenLabel;

  /// Who saw it, in words: "Seen by Carmine Russo and 1 other".
  final String? knownLabel;

  /// What [knownLabel] says, for picking its mark. Null from a server older than it.
  final DeedSeen? seen;
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
    id: _text(json['id']),
    title: _text(json['title']),
    status: ThreadStatus.fromWire(json['status']),
  );

  final String id;
  final String title;
  final ThreadStatus status;
}

/// The groups of the memory screen, in the order it shows them: what the character is after,
/// who they know and how they stand with the world's powers, where they have been, then what
/// they have heard and what was done.
enum MemorySection { objectives, people, factions, places, rumors, deeds }

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
      final JsonMap character when _text(character['name']).isNotEmpty => MemoryCharacter.fromJson(
        character,
      ),
      _ => null,
    },
    people: _list(json['people'], MemoryPerson.fromJson),
    places: _list(json['places'], MemoryPlace.fromJson),
    factions: _list(json['factions'], MemoryFaction.fromJson),
    goals: _list(json['goals'], MemoryGoal.fromJson),
    leads: _list(json['leads'], MemoryLead.fromJson),
    rumors: _list(json['rumors'], MemoryRumor.fromJson),
    deeds: _list(json['deeds'], MemoryDeed.fromJson),
    threads: _list(json['threads'], MemoryThread.fromJson),
  );

  final MemoryCharacter? character;
  final List<MemoryPerson> people;
  final List<MemoryPlace> places;
  final List<MemoryFaction> factions;
  final List<MemoryGoal> goals;
  final List<MemoryLead> leads;

  /// What people say that reached the character, each said once: unconfirmed unless they know
  /// for themselves (W2, W13, C6).
  final List<MemoryRumor> rumors;
  final List<MemoryDeed> deeds;
  final List<MemoryThread> threads;

  /// The story's threads still running (N1), and the ones that ended.
  Iterable<MemoryThread> get openThreads => threads.where((thread) => !thread.status.isClosed);
  Iterable<MemoryThread> get closedThreads => threads.where((thread) => thread.status.isClosed);

  /// How many entries a group holds. Goals, leads and the story's threads share one: what the
  /// character is after.
  int count(MemorySection section) => switch (section) {
    MemorySection.objectives => goals.length + leads.length + threads.length,
    MemorySection.people => people.length,
    MemorySection.factions => factions.length,
    MemorySection.places => places.length,
    MemorySection.rumors => rumors.length,
    MemorySection.deeds => deeds.length,
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

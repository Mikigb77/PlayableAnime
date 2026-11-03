/// Client models for stories. They read the v1 contract (docs/API.md) and, until the backend moves
/// over (WS1, WS3), the legacy payloads of today's FastAPI backend, so the app works against both.
/// The play screen work (WS14) and the library work (WS15) replace these with full v1 models.
library;

import '../../core/json.dart';

typedef Json = JsonMap;

List<T> _list<T>(Object? json, T Function(Json) fromJson) => [
  for (final item in json as List? ?? const []) fromJson(item as Json),
];

List<String> _strings(Object? json) => [
  for (final item in json as List? ?? const [])
    if (item is String) item else if (item is Json) (item['text'] ?? item['title'] ?? '') as String,
];

class Premise {
  const Premise({
    required this.id,
    required this.title,
    required this.genre,
    required this.premise,
    this.tagline,
    this.flagship = false,
    this.coverUrl,
  });

  factory Premise.fromJson(Json json) => Premise(
    id: json['id'] as String,
    title: json['title'] as String,
    genre: json['genre'] as String? ?? '',
    premise: json['premise'] as String,
    tagline: json['tagline'] as String?,
    flagship: json['flagship'] as bool? ?? false,
    coverUrl: json['cover_url'] as String?,
  );

  final String id;
  final String title;
  final String genre;
  final String premise;
  final String? tagline;
  final bool flagship;
  final String? coverUrl;
}

class StorySummary {
  const StorySummary({
    required this.id,
    required this.title,
    required this.turn,
    this.genre = '',
    this.premise,
    this.worldTimeLabel,
    this.coverUrl,
  });

  factory StorySummary.fromJson(Json json) => StorySummary(
    id: json['id'] as String,
    title: json['title'] as String,
    turn: (json['turn'] as num? ?? 0).toInt(),
    genre: json['genre'] as String? ?? '',
    premise: json['premise'] as String?,
    worldTimeLabel: json['world_time_label'] as String?,
    coverUrl: json['cover_url'] as String?,
  );

  final String id;
  final String title;
  final int turn;
  final String genre;
  final String? premise;
  final String? worldTimeLabel;
  final String? coverUrl;
}

class Choice {
  const Choice({required this.id, required this.label, this.kind = 'thread'});

  factory Choice.fromJson(Json json) => Choice(
    id: json['id'] as String,
    label: json['label'] as String,
    kind: json['kind'] as String? ?? 'thread',
  );

  final String id;
  final String label;

  /// thread, personal, side or wild (S2).
  final String kind;
}

/// A scene's picture (docs/API.md `SceneImage` and `Picture`).
class SceneImage {
  const SceneImage({required this.status, this.url, this.kind = 'scene', this.imageId});

  factory SceneImage.fromJson(Json json) => SceneImage(
    status: json['status'] as String? ?? 'planned',
    url: json['url'] as String?,
    kind: json['kind'] as String? ?? 'scene',
    imageId: json['image_id'] as String?,
  );

  /// planned, ready or skipped.
  final String status;
  final String? url;

  /// portrait, place, scene or cover: it sets the slot's shape before the picture arrives.
  final String kind;

  /// The picture's id, the same wherever it is reused (M4). Cache by it, not by the signed URL.
  final String? imageId;

  bool get isReady => status == 'ready' && url != null;

  /// Portraits and covers are 3:4, places and scenes 16:9 (docs/API.md).
  double get aspectRatio => kind == 'portrait' || kind == 'cover' ? 3 / 4 : 16 / 9;
}

class ScenePortrait {
  const ScenePortrait({required this.name, this.url});

  factory ScenePortrait.fromJson(Json json) =>
      ScenePortrait(name: json['name'] as String? ?? '?', url: json['url'] as String?);

  final String name;
  final String? url;
}

class Scene {
  const Scene({
    required this.turn,
    required this.narration,
    required this.choices,
    this.playerAction,
    this.inputMode,
    this.standingActions = const [],
    this.image,
    this.durationLabel,
    this.timeLabel,
    this.personalTimeLabel,
    this.eventSize,
    this.eventTitle,
    this.portraits = const [],
  });

  factory Scene.fromJson(Json json) {
    final time = json['time'] as Json?;
    final event = json['event'] as Json?;
    final image = switch (json) {
      {'image': final Json image} => SceneImage.fromJson(image),
      {'image_url': final String url} => SceneImage(status: 'ready', url: url), // legacy
      _ => null,
    };
    return Scene(
      turn: (json['turn'] as num).toInt(),
      narration: json['narration'] as String,
      choices: _list(json['choices'], Choice.fromJson),
      playerAction: json['player_action'] as String?,
      inputMode: json['input_mode'] as String?,
      standingActions: [for (final a in json['standing_actions'] as List? ?? const []) a as String],
      image: image,
      durationLabel: time?['duration_label'] as String?,
      timeLabel: time?['label'] as String?,
      personalTimeLabel: time?['personal_label'] as String?,
      eventSize: event?['size'] as String?,
      eventTitle: event?['title'] as String?,
      portraits: _list(json['portraits'], ScenePortrait.fromJson),
    );
  }

  final int turn;
  final String narration;
  final List<Choice> choices;
  final String? playerAction;

  /// typed, voice, voice_edited or choice (V7).
  final String? inputMode;

  /// wait and observe, when the scene offers them (S2).
  final List<String> standingActions;
  final SceneImage? image;
  final String? durationLabel;
  final String? timeLabel;
  final String? personalTimeLabel;
  final String? eventSize;
  final String? eventTitle;
  final List<ScenePortrait> portraits;

  bool get spoken => inputMode == 'voice' || inputMode == 'voice_edited';

  Scene withImage(SceneImage image) => Scene(
    turn: turn,
    narration: narration,
    choices: choices,
    playerAction: playerAction,
    inputMode: inputMode,
    standingActions: standingActions,
    image: image,
    durationLabel: durationLabel,
    timeLabel: timeLabel,
    personalTimeLabel: personalTimeLabel,
    eventSize: eventSize,
    eventTitle: eventTitle,
    portraits: portraits,
  );
}

class Story {
  const Story({
    required this.id,
    required this.title,
    required this.scenes,
    this.genre = '',
    this.premise,
    this.version = 0,
    this.clockLabel,
    this.coverUrl,
  });

  factory Story.fromJson(Json json) => Story(
    id: json['id'] as String,
    title: json['title'] as String,
    scenes: _list(json['scenes'], Scene.fromJson),
    genre: json['genre'] as String? ?? '',
    premise: json['premise'] as String?,
    version: (json['version'] as num? ?? 0).toInt(),
    clockLabel: (json['clock'] as Json?)?['label'] as String?,
    coverUrl: json['cover_url'] as String?,
  );

  final String id;
  final String title;
  final List<Scene> scenes;
  final String genre;
  final String? premise;

  /// The version the next turn sends as `expected_version` (T10).
  final int version;
  final String? clockLabel;
  final String? coverUrl;

  Story copyWith({List<Scene>? scenes, int? version, String? clockLabel}) => Story(
    id: id,
    title: title,
    scenes: scenes ?? this.scenes,
    genre: genre,
    premise: premise,
    version: version ?? this.version,
    clockLabel: clockLabel ?? this.clockLabel,
    coverUrl: coverUrl,
  );

  Story withScene(Scene scene, {required int version, String? clockLabel}) =>
      copyWith(scenes: [...scenes, scene], version: version, clockLabel: clockLabel);
}

/// One entry on the memory screen.
class MemoryItem {
  const MemoryItem({
    required this.title,
    this.lines = const [],
    this.trailing,
    this.imageUrl,
    this.muted = false,
  });

  final String title;
  final List<String> lines;
  final String? trailing;
  final String? imageUrl;

  /// Struck through: a dead character or a destroyed faction.
  final bool muted;
}

enum MemorySectionKind {
  you,
  people,
  places,
  factions,
  goals,
  leads,
  rumors,
  deeds,
  threads,
  summary,
  facts,
}

class MemorySection {
  const MemorySection(this.kind, this.items);

  final MemorySectionKind kind;
  final List<MemoryItem> items;
}

/// What the character knows (C6): the v1 `MemoryView`, or today's backend's world state.
class MemoryData {
  const MemoryData(this.sections);

  factory MemoryData.fromJson(Json json) =>
      json.containsKey('people') || json.containsKey('character')
      ? _fromView(json)
      : _fromLegacy(json);

  static MemoryData _fromView(Json json) {
    MemoryItem entity(Json e, {String? trailingKey, String? imageKey}) => MemoryItem(
      title: e['name'] as String? ?? e['text'] as String? ?? e['title'] as String? ?? '',
      lines: _strings(e['lines']),
      trailing: trailingKey == null ? null : e[trailingKey] as String?,
      imageUrl: imageKey == null ? null : e[imageKey] as String?,
      muted: (e['status_label'] as String? ?? '').toLowerCase() == 'dead',
    );
    final character = json['character'] as Json?;
    return MemoryData([
      if (character != null)
        MemorySection(MemorySectionKind.you, [entity(character, imageKey: 'portrait_url')]),
      MemorySection(MemorySectionKind.goals, [
        for (final g in json['goals'] as List? ?? const [])
          MemoryItem(title: (g as Json)['text'] as String),
      ]),
      MemorySection(MemorySectionKind.people, [
        for (final p in json['people'] as List? ?? const [])
          entity(p as Json, trailingKey: 'attitude_label', imageKey: 'portrait_url'),
      ]),
      MemorySection(MemorySectionKind.places, [
        for (final p in json['places'] as List? ?? const [])
          entity(p as Json, imageKey: 'image_url'),
      ]),
      MemorySection(MemorySectionKind.factions, [
        for (final f in json['factions'] as List? ?? const [])
          entity(f as Json, trailingKey: 'standing_label'),
      ]),
      MemorySection(MemorySectionKind.leads, [
        for (final l in json['leads'] as List? ?? const [])
          MemoryItem(title: (l as Json)['text'] as String, trailing: l['expires_label'] as String?),
      ]),
      MemorySection(MemorySectionKind.rumors, [
        for (final r in json['rumors'] as List? ?? const [])
          MemoryItem(title: (r as Json)['text'] as String, lines: [?r['heard_label'] as String?]),
      ]),
      MemorySection(MemorySectionKind.deeds, [
        for (final d in json['deeds'] as List? ?? const [])
          MemoryItem(
            title: (d as Json)['text'] as String,
            lines: [?d['when_label'] as String?, ?d['known_label'] as String?],
          ),
      ]),
      MemorySection(MemorySectionKind.threads, [
        for (final t in json['threads'] as List? ?? const [])
          MemoryItem(title: (t as Json)['title'] as String, trailing: t['status'] as String?),
      ]),
    ]);
  }

  static MemoryData _fromLegacy(Json json) => MemoryData([
    MemorySection(MemorySectionKind.summary, [
      if ((json['summary'] as String? ?? '').isNotEmpty)
        MemoryItem(title: json['summary'] as String),
    ]),
    MemorySection(MemorySectionKind.goals, [
      for (final g in _strings(json['goals'])) MemoryItem(title: g),
    ]),
    MemorySection(MemorySectionKind.people, [
      for (final c in json['characters'] as List? ?? const [])
        MemoryItem(
          title: (c as Json)['name'] as String,
          lines: [if ((c['description'] as String? ?? '').isNotEmpty) c['description'] as String],
          muted: c['status'] == 'dead',
        ),
    ]),
    MemorySection(MemorySectionKind.factions, [
      for (final f in json['factions'] as List? ?? const [])
        MemoryItem(
          title: (f as Json)['name'] as String,
          lines: [if ((f['description'] as String? ?? '').isNotEmpty) f['description'] as String],
          trailing: f['stance'] as String?,
          muted: f['stance'] == 'destroyed',
        ),
    ]),
    MemorySection(MemorySectionKind.facts, [
      for (final f in (json['facts'] as List? ?? const []).reversed)
        MemoryItem(title: (f as Json)['text'] as String),
    ]),
  ]);

  final List<MemorySection> sections;
}

/// The `/status` page (S5): the sheet, reputation and the date (docs/API.md `StatusView`).
class StatusData {
  const StatusData({
    required this.name,
    required this.lines,
    required this.reputation,
    required this.since,
    this.clockLabel,
  });

  factory StatusData.fromJson(Json json) {
    final character = json['character'] as Json? ?? const {};
    return StatusData(
      name: character['name'] as String? ?? '',
      lines: _strings(character['lines']),
      reputation: [
        for (final r in json['reputation'] as List? ?? const [])
          ((r as Json)['name'] as String, r['label'] as String),
      ],
      since: [
        for (final s in json['since'] as List? ?? const [])
          ((s as Json)['text'] as String, s['ago_label'] as String),
      ],
      clockLabel: (json['clock'] as Json?)?['label'] as String?,
    );
  }

  final String name;
  final List<String> lines;
  final List<(String name, String label)> reputation;
  final List<(String text, String ago)> since;
  final String? clockLabel;
}

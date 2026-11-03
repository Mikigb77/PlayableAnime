/// Client models for stories. They read the v1 contract (docs/API.md) and, until the backend moves
/// over (WS1, WS3), the legacy payloads of today's FastAPI backend, so the app works against both.
/// The play screen work (WS14) replaces these with full v1 models. Premises, the library's
/// summaries and memory have their own models in `discover/`, `library/` and `story/memory.dart`.
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

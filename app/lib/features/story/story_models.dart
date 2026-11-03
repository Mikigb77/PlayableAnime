/// Client-side mirrors of the backend's story models (backend/app/domain.py).
library;

typedef Json = Map<String, dynamic>;

List<T> _list<T>(Object? json, T Function(Json) fromJson) => [
  for (final item in json as List? ?? const []) fromJson(item as Json),
];

class Premise {
  const Premise({
    required this.id,
    required this.title,
    required this.genre,
    required this.premise,
  });

  factory Premise.fromJson(Json json) => Premise(
    id: json['id'] as String,
    title: json['title'] as String,
    genre: json['genre'] as String,
    premise: json['premise'] as String,
  );

  final String id;
  final String title;
  final String genre;
  final String premise;
}

class StorySummary {
  const StorySummary({
    required this.id,
    required this.title,
    required this.premise,
    required this.turn,
  });

  factory StorySummary.fromJson(Json json) => StorySummary(
    id: json['id'] as String,
    title: json['title'] as String,
    premise: json['premise'] as String,
    turn: json['turn'] as int,
  );

  final String id;
  final String title;
  final String premise;
  final int turn;
}

class Choice {
  const Choice({required this.id, required this.label});

  factory Choice.fromJson(Json json) =>
      Choice(id: json['id'] as String, label: json['label'] as String);

  final String id;
  final String label;
}

class Scene {
  const Scene({
    required this.turn,
    required this.narration,
    required this.choices,
    this.playerAction,
    this.imageUrl,
  });

  factory Scene.fromJson(Json json) => Scene(
    turn: json['turn'] as int,
    narration: json['narration'] as String,
    choices: _list(json['choices'], Choice.fromJson),
    playerAction: json['player_action'] as String?,
    imageUrl: json['image_url'] as String?,
  );

  final int turn;
  final String narration;
  final List<Choice> choices;
  final String? playerAction;
  final String? imageUrl;
}

class Character {
  const Character({
    required this.id,
    required this.name,
    required this.description,
    required this.status,
    required this.affinity,
  });

  factory Character.fromJson(Json json) => Character(
    id: json['id'] as String,
    name: json['name'] as String,
    description: json['description'] as String? ?? '',
    status: json['status'] as String,
    affinity: json['affinity'] as int,
  );

  final String id;
  final String name;
  final String description;

  /// alive, dead or missing.
  final String status;

  /// -100 (hatred) to 100 (devotion) toward the player.
  final int affinity;

  bool get isDead => status == 'dead';
}

class Faction {
  const Faction({
    required this.id,
    required this.name,
    required this.description,
    required this.stance,
  });

  factory Faction.fromJson(Json json) => Faction(
    id: json['id'] as String,
    name: json['name'] as String,
    description: json['description'] as String? ?? '',
    stance: json['stance'] as String,
  );

  final String id;
  final String name;
  final String description;

  /// allied, neutral, hostile or destroyed.
  final String stance;
}

class Fact {
  const Fact({required this.text, required this.turn, required this.importance});

  factory Fact.fromJson(Json json) => Fact(
    text: json['text'] as String,
    turn: json['turn'] as int,
    importance: json['importance'] as int,
  );

  final String text;
  final int turn;
  final int importance;
}

class WorldState {
  const WorldState({
    required this.turn,
    required this.summary,
    required this.goals,
    required this.characters,
    required this.factions,
    required this.facts,
  });

  factory WorldState.fromJson(Json json) => WorldState(
    turn: json['turn'] as int,
    summary: json['summary'] as String? ?? '',
    goals: [for (final goal in json['goals'] as List? ?? const []) goal as String],
    characters: _list(json['characters'], Character.fromJson),
    factions: _list(json['factions'], Faction.fromJson),
    facts: _list(json['facts'], Fact.fromJson),
  );

  final int turn;
  final String summary;
  final List<String> goals;
  final List<Character> characters;
  final List<Faction> factions;
  final List<Fact> facts;
}

class Story {
  const Story({
    required this.id,
    required this.title,
    required this.premise,
    required this.scenes,
    required this.state,
  });

  factory Story.fromJson(Json json) => Story(
    id: json['id'] as String,
    title: json['title'] as String,
    premise: json['premise'] as String,
    scenes: _list(json['scenes'], Scene.fromJson),
    state: WorldState.fromJson(json['state'] as Json),
  );

  final String id;
  final String title;
  final String premise;
  final List<Scene> scenes;
  final WorldState state;

  Story withTurn(TurnResult turn) => Story(
    id: id,
    title: title,
    premise: premise,
    scenes: [...scenes, turn.scene],
    state: turn.state,
  );
}

class TurnResult {
  const TurnResult({required this.scene, required this.state});

  factory TurnResult.fromJson(Json json) => TurnResult(
    scene: Scene.fromJson(json['scene'] as Json),
    state: WorldState.fromJson(json['state'] as Json),
  );

  final Scene scene;
  final WorldState state;
}

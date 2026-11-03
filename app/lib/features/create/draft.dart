/// The draft of a world and a character (docs/API.md, "Drafting a world and a character", G1, G2),
/// what a change to it costs, and the choices the player makes about it.
library;

import 'package:flutter/foundation.dart';

import '../../core/json.dart';

/// A story's rating (F2). Accounts under 17 get Teen only (F8).
enum Rating {
  teen('teen'),
  mature('mature');

  const Rating(this.wire);

  final String wire;

  static Rating fromWire(Object? value) => value == 'mature' ? mature : teen;
}

/// How strict physics is (A9): fun first by default, or strict for a rougher, more coherent world.
enum Physics {
  funFirst('fun_first'),
  strict('strict');

  const Physics(this.wire);

  final String wire;

  static Physics fromWire(Object? value) => value == 'strict' ? strict : funFirst;
}

/// The strongest gift the character holds (G22).
enum GiftStrength {
  none('none'),
  small('small'),
  rare('rare'),
  overpowered('overpowered');

  const GiftStrength(this.wire);

  final String wire;

  static GiftStrength fromWire(Object? value) =>
      values.where((g) => g.wire == value).firstOrNull ?? none;
}

/// How often rolled steps go the character's way (A5).
enum Difficulty {
  story('story'),
  balanced('balanced'),
  brutal('brutal');

  const Difficulty(this.wire);

  final String wire;

  static Difficulty fromWire(Object? value) =>
      values.where((d) => d.wire == value).firstOrNull ?? balanced;
}

/// How often the world brings events of its own (W16).
enum EventFrequency {
  calm('calm'),
  normal('normal'),
  dramatic('dramatic');

  const EventFrequency(this.wire);

  final String wire;

  static EventFrequency fromWire(Object? value) =>
      values.where((e) => e.wire == value).firstOrNull ?? normal;
}

/// A rule of the world (G6), fixed for the whole story or open to discovery (G7). A rule without
/// an [id] is one the player is adding.
@immutable
class DraftRule {
  const DraftRule({this.id, required this.text, this.fixed = true});

  factory DraftRule.fromJson(JsonMap json) => DraftRule(
    id: json['id'] as String?,
    text: json['text'] as String? ?? '',
    fixed: json['fixed'] as bool? ?? true,
  );

  final String? id;
  final String text;
  final bool fixed;

  DraftRule copyWith({String? text, bool? fixed}) =>
      DraftRule(id: id, text: text ?? this.text, fixed: fixed ?? this.fixed);

  JsonMap toJson() => {'id': ?id, 'text': text, 'fixed': fixed};

  @override
  bool operator ==(Object other) =>
      other is DraftRule && other.id == id && other.text == text && other.fixed == fixed;

  @override
  int get hashCode => Object.hash(id, text, fixed);
}

/// The fields hidden behind "Advanced" (G1).
@immutable
class DraftAdvanced {
  const DraftAdvanced({
    this.physics = Physics.funFirst,
    this.rules = const [],
    this.giftStrength = GiftStrength.none,
    this.difficulty = Difficulty.balanced,
    this.eventFrequency = EventFrequency.normal,
  });

  factory DraftAdvanced.fromJson(JsonMap json) => DraftAdvanced(
    physics: Physics.fromWire(json['physics']),
    rules: [
      for (final rule in json['rules'] as List? ?? const []) DraftRule.fromJson(rule as JsonMap),
    ],
    giftStrength: GiftStrength.fromWire(json['gift_strength']),
    difficulty: Difficulty.fromWire(json['difficulty']),
    eventFrequency: EventFrequency.fromWire(json['event_frequency']),
  );

  final Physics physics;
  final List<DraftRule> rules;
  final GiftStrength giftStrength;
  final Difficulty difficulty;
  final EventFrequency eventFrequency;
}

@immutable
class Draft {
  const Draft({
    required this.id,
    required this.premise,
    required this.rating,
    required this.title,
    required this.genre,
    required this.version,
    this.premiseId,
    this.tone = '',
    this.worldLines = const [],
    this.characterLines = const [],
    this.advanced = const DraftAdvanced(),
    this.storyId,
  });

  factory Draft.fromJson(JsonMap json) => Draft(
    id: json['id'] as String,
    premise: json['premise'] as String? ?? '',
    premiseId: json['premise_id'] as String?,
    rating: Rating.fromWire(json['rating']),
    title: json['title'] as String? ?? '',
    genre: json['genre'] as String? ?? '',
    tone: json['tone'] as String? ?? '',
    worldLines: [for (final line in json['world_lines'] as List? ?? const []) line as String],
    characterLines: [
      for (final line in json['character_lines'] as List? ?? const []) line as String,
    ],
    advanced: DraftAdvanced.fromJson(json['advanced'] as JsonMap? ?? const {}),
    version: (json['version'] as num? ?? 1).toInt(),
    storyId: json['story_id'] as String?,
  );

  final String id;
  final String premise;
  final String? premiseId;
  final Rating rating;
  final String title;
  final String genre;
  final String tone;

  /// The one-screen summary of the world, in plain words (G1). Code writes it from the world's
  /// public parts, so it always matches the draft.
  final List<String> worldLines;

  /// The character in the world's words (G2, G16).
  final List<String> characterLines;
  final DraftAdvanced advanced;

  /// Sent back as `expected_version` with every change (T10).
  final int version;

  /// Set once the draft has started a story.
  final String? storyId;

  List<String> linesOf(DraftPart part) => switch (part) {
    DraftPart.world => worldLines,
    DraftPart.character => characterLines,
  };
}

/// The two halves of a draft that the player reviews and can ask to change.
enum DraftPart {
  world('world'),
  character('character');

  const DraftPart(this.wire);

  /// The `target` of a revision.
  final String wire;
}

/// Choices sent with a new draft, so the first draft already follows them and nothing needs
/// redrafting later. Fields left null take the server's defaults.
@immutable
class DraftChoices {
  const DraftChoices({this.physics, this.giftStrength, this.difficulty, this.eventFrequency});

  final Physics? physics;
  final GiftStrength? giftStrength;
  final Difficulty? difficulty;
  final EventFrequency? eventFrequency;

  bool get isEmpty =>
      physics == null && giftStrength == null && difficulty == null && eventFrequency == null;

  JsonMap toJson() => {
    'physics': ?physics?.wire,
    'gift_strength': ?giftStrength?.wire,
    'difficulty': ?difficulty?.wire,
    'event_frequency': ?eventFrequency?.wire,
  };
}

/// A direct edit (`PATCH /v1/drafts/{id}`). Fields left null stay as they are.
@immutable
class DraftEdit {
  const DraftEdit({
    this.worldLines,
    this.characterLines,
    this.rating,
    this.physics,
    this.rules,
    this.giftStrength,
    this.difficulty,
    this.eventFrequency,
  });

  /// Lines of one part replaced.
  factory DraftEdit.lines(DraftPart part, List<String> lines) => switch (part) {
    DraftPart.world => DraftEdit(worldLines: lines),
    DraftPart.character => DraftEdit(characterLines: lines),
  };

  final List<String>? worldLines;
  final List<String>? characterLines;
  final Rating? rating;
  final Physics? physics;

  /// The whole list the player sees, word for word.
  final List<DraftRule>? rules;
  final GiftStrength? giftStrength;
  final Difficulty? difficulty;
  final EventFrequency? eventFrequency;

  JsonMap toJson({required int expectedVersion}) {
    final advanced = <String, Object?>{
      'physics': ?physics?.wire,
      if (rules case final rules?) 'rules': [for (final rule in rules) rule.toJson()],
      'gift_strength': ?giftStrength?.wire,
      'difficulty': ?difficulty?.wire,
      'event_frequency': ?eventFrequency?.wire,
    };
    return {
      'world_lines': ?worldLines,
      'character_lines': ?characterLines,
      'rating': ?rating?.wire,
      if (advanced.isNotEmpty) 'advanced': advanced,
      'expected_version': expectedVersion,
    };
  }
}

/// What a change costs: the parts the server redrafts with the model to match it, one call each
/// (docs/API.md, "Direct edits"). A change that redrafts nothing is free.
@immutable
class Redraft {
  const Redraft({this.world = false, this.character = false});

  static const none = Redraft();

  final bool world;
  final bool character;

  bool get isFree => !world && !character;

  /// Model calls, each charged as a draft (K2).
  int get calls => (world ? 1 : 0) + (character ? 1 : 0);

  @override
  bool operator ==(Object other) =>
      other is Redraft && other.world == world && other.character == character;

  @override
  int get hashCode => Object.hash(world, character);

  @override
  String toString() => 'Redraft(world: $world, character: $character)';
}

/// What [edit] would cost on [draft], by the server's own rules: physics, a rule's fixed flag, no
/// gift, difficulty, event frequency and raising the rating are free. Rewritten lines, rewritten,
/// added or removed rules and a new gift strength redraft the world or the character, and lowering
/// the rating to Teen redrafts both (F2).
Redraft redraftFor(Draft draft, DraftEdit edit) {
  var world = false;
  var character = false;
  if (edit.rating == Rating.teen && draft.rating == Rating.mature) {
    world = true;
    character = true;
  }
  if (edit.rules case final rules?) {
    // As the server compares: the player's words normalized, the drafted ones as they are.
    final after = [
      for (final rule in rules)
        if (normalizeLine(rule.text).isNotEmpty) '${rule.id}\u0000${normalizeLine(rule.text)}',
    ];
    final before = [for (final rule in draft.advanced.rules) '${rule.id}\u0000${rule.text}'];
    if (!listEquals(after, before)) world = true;
  }
  if (edit.worldLines case final lines? when !listEquals(cleanLines(lines), draft.worldLines)) {
    world = true;
  }
  if (edit.characterLines case final lines?
      when !listEquals(cleanLines(lines), draft.characterLines)) {
    character = true;
  }
  if (edit.giftStrength case final gift?
      when gift != GiftStrength.none && gift != draft.advanced.giftStrength) {
    character = true;
  }
  return Redraft(world: world, character: character);
}

/// A line as the server keeps it: single spaces, no ends.
String normalizeLine(String line) =>
    line.split(RegExp(r'\s+')).where((w) => w.isNotEmpty).join(' ');

/// Lines as the server keeps them: normalized, blanks dropped.
List<String> cleanLines(Iterable<String> lines) => [
  for (final line in lines)
    if (normalizeLine(line).isNotEmpty) normalizeLine(line),
];

/// Limits from docs/API.md.
abstract final class DraftLimits {
  static const premiseMin = 10;
  static const premiseMax = 4000;
  static const line = 300;
  static const instruction = 1000;
  static const rules = 12;
}

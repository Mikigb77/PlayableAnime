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

/// What a line of the summary tells of (docs/API.md, `DraftPartKind`). The app labels and groups
/// the lines by it, and points a change in plain words at it.
enum LineKind {
  // The world.
  rule,
  era,
  ladder,
  peoples,
  faction,
  // How the story starts, shown only when the player's own words name it (G1).
  deadline,
  question,
  person,
  connections,
  goal,
  // The character.
  who,
  manner,
  standing,
  rank,
  skills,
  talents,
  traits,
  nature,
  power,
  belongings;

  /// The kind as the API names it, and the `about` of a revision.
  String get wire => name;

  /// Null for a kind this app doesn't know, whose line is then left out.
  static LineKind? fromWire(Object? value) => values.where((k) => k.name == value).firstOrNull;

  /// Whether it tells of how the story starts.
  bool get isOpener => switch (this) {
    deadline || question || person || connections || goal => true,
    _ => false,
  };
}

/// One line of a draft's summary, with what it tells of.
@immutable
class DraftLine {
  const DraftLine(this.kind, this.text);

  final LineKind kind;
  final String text;

  static List<DraftLine> listFromJson(Object? json) => [
    for (final part in json as List? ?? const [])
      if (LineKind.fromWire((part as JsonMap)['kind']) case final kind?)
        DraftLine(kind, part['text'] as String? ?? ''),
  ];

  @override
  bool operator ==(Object other) => other is DraftLine && other.kind == kind && other.text == text;

  @override
  int get hashCode => Object.hash(kind, text);

  @override
  String toString() => 'DraftLine(${kind.name}: $text)';
}

/// The character's plain fields, which the player changes themselves (G2), with their people
/// and their standing to tell them by.
@immutable
class DraftCharacter {
  const DraftCharacter({
    this.name = '',
    this.age,
    this.people = '',
    this.standing = '',
    this.looks = '',
    this.manner = '',
  });

  factory DraftCharacter.fromJson(JsonMap json) => DraftCharacter(
    name: json['name'] as String? ?? '',
    age: (json['age'] as num?)?.toInt(),
    people: json['people'] as String? ?? '',
    standing: json['standing'] as String? ?? '',
    looks: json['looks'] as String? ?? '',
    manner: json['manner'] as String? ?? '',
  );

  final String name;
  final int? age;
  final String people;
  final String standing;

  /// Face, build, hair and usual clothes, which every picture of them is drawn from (M5).
  final String looks;

  /// How they come across.
  final String manner;
}

/// The world's first ladder as the summary tells it (G18, G19): the rungs everyone has heard of,
/// and where the character stands when that is one of them.
@immutable
class DraftLadder {
  const DraftLadder({
    required this.name,
    this.rungs = const [],
    this.more = false,
    this.at,
    this.stage = '',
  });

  factory DraftLadder.fromJson(JsonMap json) => DraftLadder(
    name: json['name'] as String? ?? '',
    rungs: [for (final rung in json['rungs'] as List? ?? const []) rung as String],
    more: json['more'] as bool? ?? false,
    at: (json['at'] as num?)?.toInt(),
    stage: json['stage'] as String? ?? '',
  );

  final String name;
  final List<String> rungs;

  /// Whether the ladder goes on above the rungs named.
  final bool more;

  /// The character's rung, an index into [rungs], or null when they stand above them.
  final int? at;

  /// Their stage of that rung, in words, or "".
  final String stage;
}

/// How much of the story's start the summary keeps out of sight (G1), as counts and nothing more.
@immutable
class DraftKept {
  const DraftKept({this.people = 0, this.events = 0, this.questions = 0});

  factory DraftKept.fromJson(JsonMap json) => DraftKept(
    people: (json['people'] as num? ?? 0).toInt(),
    events: (json['events'] as num? ?? 0).toInt(),
    questions: (json['questions'] as num? ?? 0).toInt(),
  );

  final int people;
  final int events;
  final int questions;

  bool get isEmpty => people == 0 && events == 0 && questions == 0;
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
    this.language = 'en',
    this.tone = '',
    this.worldParts = const [],
    this.characterParts = const [],
    this.character = const DraftCharacter(),
    this.ladder,
    this.kept = const DraftKept(),
    this.advanced = const DraftAdvanced(),
    this.storyId,
  });

  factory Draft.fromJson(JsonMap json) => Draft(
    id: json['id'] as String,
    premise: json['premise'] as String? ?? '',
    premiseId: json['premise_id'] as String?,
    rating: Rating.fromWire(json['rating']),
    language: json['language'] as String? ?? 'en',
    title: json['title'] as String? ?? '',
    genre: json['genre'] as String? ?? '',
    tone: json['tone'] as String? ?? '',
    worldParts: DraftLine.listFromJson(json['world_parts']),
    characterParts: DraftLine.listFromJson(json['character_parts']),
    character: DraftCharacter.fromJson(json['character'] as JsonMap? ?? const {}),
    ladder: switch (json['ladder']) {
      final JsonMap ladder => DraftLadder.fromJson(ladder),
      _ => null,
    },
    kept: DraftKept.fromJson(json['kept'] as JsonMap? ?? const {}),
    advanced: DraftAdvanced.fromJson(json['advanced'] as JsonMap? ?? const {}),
    version: (json['version'] as num? ?? 1).toInt(),
    storyId: json['story_id'] as String?,
  );

  final String id;
  final String premise;
  final String? premiseId;
  final Rating rating;

  /// The language the draft is written in and its story starts and stays in, `en`, `es` or `ca`
  /// (S10).
  final String language;
  final String title;
  final String genre;
  final String tone;

  /// The summary of the world, line by line, each with what it tells of (G1). Code writes it
  /// from the world's public parts, so it always matches the draft.
  final List<DraftLine> worldParts;

  /// The character in the world's words (G2, G16).
  final List<DraftLine> characterParts;

  /// The character's plain fields, which the player changes themselves (G2).
  final DraftCharacter character;

  /// The world's first ladder, or null in a world with none.
  final DraftLadder? ladder;

  /// What the story keeps back of its start, as counts (G1).
  final DraftKept kept;
  final DraftAdvanced advanced;

  /// Sent back as `expected_version` with every change (T10).
  final int version;

  /// Set once the draft has started a story.
  final String? storyId;

  List<DraftLine> partsOf(DraftPart part) => switch (part) {
    DraftPart.world => worldParts,
    DraftPart.character => characterParts,
  };

  /// The lines of [part] that tell of [kind], in order.
  List<String> linesOf(DraftPart part, LineKind kind) => [
    for (final line in partsOf(part))
      if (line.kind == kind) line.text,
  ];

  /// What the player's own words named of how the story starts (G1), in the order the summary
  /// tells it, each with the half of the draft it belongs to.
  List<(DraftPart, DraftLine)> get openers => [
    for (final part in DraftPart.values)
      for (final line in partsOf(part))
        if (line.kind.isOpener) (part, line),
  ];

  /// This draft once it has started [storyId].
  Draft started(String storyId) => Draft(
    id: id,
    premise: premise,
    premiseId: premiseId,
    rating: rating,
    language: language,
    title: title,
    genre: genre,
    tone: tone,
    worldParts: worldParts,
    characterParts: characterParts,
    character: character,
    ladder: ladder,
    kept: kept,
    advanced: advanced,
    version: version,
    storyId: storyId,
  );
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
    this.title,
    this.tone,
    this.name,
    this.age,
    this.looks,
    this.manner,
    this.rating,
    this.physics,
    this.rules,
    this.giftStrength,
    this.difficulty,
    this.eventFrequency,
  });

  /// The plain fields (G1, G2): the server writes them in at once, with no model call.
  final String? title;
  final String? tone;
  final String? name;
  final int? age;
  final String? looks;
  final String? manner;
  final Rating? rating;
  final Physics? physics;

  /// The whole list the player sees, word for word.
  final List<DraftRule>? rules;
  final GiftStrength? giftStrength;
  final Difficulty? difficulty;
  final EventFrequency? eventFrequency;

  JsonMap toJson({required int expectedVersion}) {
    final character = <String, Object?>{
      'name': ?name,
      'age': ?age,
      'looks': ?looks,
      'manner': ?manner,
    };
    final advanced = <String, Object?>{
      'physics': ?physics?.wire,
      if (rules case final rules?) 'rules': [for (final rule in rules) rule.toJson()],
      'gift_strength': ?giftStrength?.wire,
      'difficulty': ?difficulty?.wire,
      'event_frequency': ?eventFrequency?.wire,
    };
    return {
      'title': ?title,
      'tone': ?tone,
      if (character.isNotEmpty) 'character': character,
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

/// What [edit] would cost on [draft], by the server's own rules: the plain fields (a title, a
/// tone, a name, an age, a look, a manner), physics, a rule's fixed flag, no gift, difficulty,
/// event frequency and raising the rating are free. Rewritten, added or removed rules redraft
/// the world, a new gift strength redrafts the character, and lowering the rating to Teen
/// redrafts both (F2).
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
  if (edit.giftStrength case final gift?
      when gift != GiftStrength.none && gift != draft.advanced.giftStrength) {
    character = true;
  }
  return Redraft(world: world, character: character);
}

/// A line as the server keeps it: single spaces, no ends.
String normalizeLine(String line) =>
    line.split(RegExp(r'\s+')).where((w) => w.isNotEmpty).join(' ');

/// Limits from docs/API.md.
abstract final class DraftLimits {
  static const premiseMin = 10;
  static const premiseMax = 4000;
  static const line = 300;
  static const instruction = 1000;

  /// The most rules the player may write. A draft may hold more, and those are still theirs to
  /// change or remove.
  static const rules = 12;

  /// The plain fields, each as long as the drafter may write it (the backend's
  /// `graph.drafting.assemble`): a field always takes back the text it shows.
  static const title = 120;
  static const tone = 200;
  static const name = 120;

  /// A look or a manner.
  static const long = 600;
  static const ageMax = 100000;
}

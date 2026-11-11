/// Client models for stories, read from the v1 contract (docs/API.md): scenes, pictures, details
/// and settings. Premises, the library's summaries and memory have their own models in
/// `discover/`, `library/` and `story/memory.dart`.
library;

import '../../core/json.dart';
import 'sheet.dart';

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
  const SceneImage({
    required this.status,
    this.url,
    this.kind = 'scene',
    this.imageId,
    this.expiresAt,
    this.planned = true,
  });

  factory SceneImage.fromJson(Json json) => SceneImage(
    status: json['status'] as String? ?? 'planned',
    url: json['url'] as String?,
    kind: json['kind'] as String? ?? 'scene',
    imageId: json['image_id'] as String?,
    expiresAt: switch (json['expires_at']) {
      final String at => DateTime.tryParse(at),
      _ => null,
    },
    planned: json['planned'] as bool? ?? true,
  );

  /// planned, ready or skipped. A `Picture` that is `pending` reads as planned.
  final String status;
  final String? url;

  /// portrait, place, scene or cover: it sets the slot's shape before the picture arrives.
  final String kind;

  /// The picture's id, the same wherever it is reused (M4). Cache by it, not by the signed URL.
  final String? imageId;

  /// When [url] stops working, about an hour after it was signed. A fresh one comes from
  /// `GET /v1/stories/{id}/images/{image_id}`.
  final DateTime? expiresAt;

  /// Code planned it (M1); false for a picture the player asked for (Illustrate, M2).
  final bool planned;

  bool get isReady => status == 'ready' && url != null;
  bool get isPending => status == 'planned';
  bool get isSkipped => status == 'skipped';

  /// Portraits and covers are 3:4, places and scenes 16:9 (docs/API.md).
  double get aspectRatio => kind == 'portrait' || kind == 'cover' ? 3 / 4 : 16 / 9;

  SceneImage copyWith({String? status, String? url, String? kind, String? imageId}) => SceneImage(
    status: status ?? this.status,
    url: url ?? this.url,
    kind: kind ?? this.kind,
    imageId: imageId ?? this.imageId,
    expiresAt: expiresAt,
    planned: planned,
  );
}

class ScenePortrait {
  const ScenePortrait({required this.name, this.url, this.characterId});

  factory ScenePortrait.fromJson(Json json) => ScenePortrait(
    name: json['name'] as String? ?? '?',
    url: json['url'] as String?,
    characterId: json['character_id'] as String?,
  );

  final String name;
  final String? url;
  final String? characterId;
}

/// How a step stood before anything was rolled (A2): the facts settle a certain or ruled-out
/// step, and only contested steps and long shots are rolled.
enum OutcomeClass {
  certain,
  contested,
  longShot,
  ruledOut;

  static OutcomeClass fromWire(String? value) => switch (value) {
    'certain' => certain,
    'long_shot' => longShot,
    'ruled_out' => ruledOut,
    _ => contested,
  };
}

/// What a roll gave (A3).
enum RollResult {
  success,
  partial,
  failure;

  static RollResult fromWire(String? value) => switch (value) {
    'success' => success,
    'partial' => partial,
    _ => failure,
  };
}

/// What a die of a throw is (A3): plain for the hand, green for an advantage, violet or gold for
/// the move's own die, and grey for the world's.
enum DieKind {
  plain,
  green,
  violet,
  gold,
  grey;

  static DieKind fromWire(String? value) => switch (value) {
    'green' => green,
    'violet' => violet,
    'gold' => gold,
    'grey' => grey,
    _ => plain,
  };
}

/// One die as it fell (A3).
class ThrownDie {
  const ThrownDie({required this.kind, required this.face, this.sprung = false});

  factory ThrownDie.fromJson(Json json) => ThrownDie(
    kind: DieKind.fromWire(json['kind'] as String?),
    face: ((json['face'] as num?)?.toInt() ?? 1).clamp(1, 20),
    sprung: json['sprung'] as bool? ?? false,
  );

  /// What a gold die counts for at least, whatever it shows.
  static const goldFloor = 10;

  final DieKind kind;

  /// The number it shows, 1 to 20.
  final int face;

  /// Thrown because the die before it showed a 20.
  final bool sprung;

  /// What it adds to the total: its face, and never under 10 for a gold die.
  int get value => kind == DieKind.gold && face < goldFloor ? goldFloor : face;
}

/// How a throw fell against its number (A3).
enum ThrowMark {
  overTheTop,
  passed,
  soClose,
  missed;

  static ThrowMark fromWire(String? value) => switch (value) {
    'over_the_top' => overTheTop,
    'passed' => passed,
    'so_close' => soClose,
    _ => missed,
  };

  /// The total reached the number.
  bool get reached => this == overTheTop || this == passed;
}

/// One thing a throw's number is made of: the level first, then each thing that moved it.
typedef NumberPart = ({String text, int points});

/// The dice that decided a step (docs/API.md `Throw`, A3): every die as it fell, the hand and
/// why, the number and what it is made of, and how the total fell against it. The app shows
/// these dice and never rolls any.
class SceneThrow {
  const SceneThrow({
    required this.dice,
    required this.number,
    required this.total,
    required this.most,
    required this.mark,
    this.hand = 1,
    this.handWhy = '',
    this.greens = const [],
    this.madeOf = const [],
    this.against = '',
    this.deadly = false,
    this.missCosts = '',
    this.insight = false,
    this.insightAt = 18,
  });

  factory SceneThrow.fromJson(Json json) {
    final dice = _list(json['dice'], ThrownDie.fromJson);
    final hand = (json['hand'] as num?)?.toInt() ?? dice.where((d) => !d.sprung).length;
    return SceneThrow(
      dice: dice,
      hand: hand,
      handWhy: json['hand_why'] as String? ?? '',
      greens: [
        for (final green in json['greens'] as List? ?? const [])
          if (green is String) green,
      ],
      number: (json['number'] as num?)?.toInt() ?? 0,
      madeOf: [
        for (final part in json['made_of'] as List? ?? const [])
          if (part is Json)
            (text: part['text'] as String? ?? '', points: (part['points'] as num?)?.toInt() ?? 0),
      ],
      total: (json['total'] as num?)?.toInt() ?? dice.fold<int>(0, (sum, d) => sum + d.value),
      most: (json['most'] as num?)?.toInt() ?? 20 * hand,
      mark: ThrowMark.fromWire(json['mark'] as String?),
      against: json['against'] as String? ?? '',
      deadly: json['deadly'] as bool? ?? false,
      missCosts: json['miss_costs'] as String? ?? '',
      insight: json['insight'] as bool? ?? false,
      insightAt: (json['insight_at'] as num?)?.toInt() ?? 18,
    );
  }

  /// The throw in [json], or none when there are no dice to show.
  static SceneThrow? maybe(Object? json) {
    if (json is! Json) return null;
    final thrown = SceneThrow.fromJson(json);
    return thrown.dice.isEmpty ? null : thrown;
  }

  /// Every die in the order thrown.
  final List<ThrownDie> dice;

  /// The dice in the hand, before any a 20 threw, and why: "Aura blade (skilled), 3 dice".
  final int hand;
  final String handWhy;

  /// Each green die's reason, in the order thrown.
  final List<String> greens;

  /// What the total had to reach, and what it is made of.
  final int number;
  final List<NumberPart> madeOf;

  /// The dice added up, and the most the hand could make with no 20.
  final int total;
  final int most;
  final ThrowMark mark;

  /// What it was up against, in a sentence.
  final String against;

  /// A miss could kill, and what it costs (N6).
  final bool deadly;
  final String missCosts;

  /// The violet die showed an insight (A4), and the face that shows one.
  final bool insight;
  final int insightAt;

  /// The world's one grey die, for what is nobody's doing.
  bool get ofTheWorld => dice.first.kind == DieKind.grey;
}

class SceneRoll {
  const SceneRoll({required this.oddsLabel, required this.result, this.seed, this.thrown});

  factory SceneRoll.fromJson(Json json) => SceneRoll(
    oddsLabel: json['odds_label'] as String? ?? '',
    result: RollResult.fromWire(json['result'] as String?),
    seed: json['seed'] as String?,
    thrown: SceneThrow.maybe(json['throw']),
  );

  /// The roll in one line: "31 against 27", or the odds in words on a scene saved before the dice.
  final String oddsLabel;
  final RollResult result;

  /// The roll's seed, so the same roll can be checked again.
  final String? seed;

  /// The dice (A3). None on a scene saved before they travelled.
  final SceneThrow? thrown;
}

SceneRoll? _roll(Object? json) => json is Json ? SceneRoll.fromJson(json) : null;

/// A beat of a step whose check is worth explaining (R2): it made something part of the world, or
/// came up empty and stopped the step there.
class SceneBeat {
  const SceneBeat({
    required this.beat,
    required this.thing,
    required this.madeCanon,
    this.reason = '',
    this.roll,
  });

  factory SceneBeat.fromJson(Json json) => SceneBeat(
    beat: json['beat'] as String? ?? '',
    thing: json['thing'] as String? ?? '',
    madeCanon: json['verdict'] == 'made_canon',
    reason: json['reason'] as String? ?? '',
    roll: _roll(json['roll']),
  );

  /// The beat in plain words, such as "grab the rope".
  final String beat;

  /// What it relied on, such as "a rope on the balcony".
  final String thing;

  /// True when the thing became part of the world (`made_canon`), false when it wasn't there.
  final bool madeCanon;
  final String reason;
  final SceneRoll? roll;
}

/// What struck back at the character right after a step (N6): the foes still fighting them, or a
/// danger the step met, such as a long drop, settled like a step, by the facts or by a roll.
class SceneStruck {
  const SceneStruck({
    required this.by,
    required this.outcomeClass,
    this.harm = 'none',
    this.reason = '',
    this.roll,
  });

  factory SceneStruck.fromJson(Json json) => SceneStruck(
    by: json['by'] as String? ?? '',
    outcomeClass: OutcomeClass.fromWire(json['class'] as String?),
    harm: json['harm'] as String? ?? 'none',
    reason: json['reason'] as String? ?? '',
    roll: _roll(json['roll']),
  );

  /// Who or what struck, such as "the grey mage" or "the long drop to the river".
  final String by;
  final OutcomeClass outcomeClass;

  /// What it did: `none`, `hurt`, `wounded`, `subdued`, `badly_wounded`, `maimed`, `dying` or
  /// `dead`.
  final String harm;
  final String reason;
  final SceneRoll? roll;

  bool get harmed => harm != 'none';

  /// A wound that puts the character's life or body at stake.
  bool get grave => const {'badly_wounded', 'maimed', 'dying', 'dead'}.contains(harm);
}

/// One step of the player's action, as the engine settled it (A2, A8).
class SceneStep {
  const SceneStep({
    required this.text,
    required this.outcomeClass,
    this.reason = '',
    this.roll,
    this.beats = const [],
    this.struck = const [],
  });

  factory SceneStep.fromJson(Json json) => SceneStep(
    text: json['text'] as String? ?? '',
    outcomeClass: OutcomeClass.fromWire(json['class'] as String?),
    reason: json['reason'] as String? ?? '',
    roll: _roll(json['roll']),
    beats: _list(json['beats'], SceneBeat.fromJson),
    struck: _list(json['struck'], SceneStruck.fromJson),
  );

  final String text;
  final OutcomeClass outcomeClass;

  /// Why, in the world's words (A8, G14).
  final String reason;
  final SceneRoll? roll;

  /// The beats worth explaining (R2), when the engine sent any.
  final List<SceneBeat> beats;

  /// What struck back at the character after it (N6), in order.
  final List<SceneStruck> struck;
}

/// One link of a cause-and-effect chain (A9).
class ChainLink {
  const ChainLink({required this.text, required this.outcomeClass, this.reason = ''});

  factory ChainLink.fromJson(Json json) => ChainLink(
    text: json['link'] as String? ?? '',
    outcomeClass: OutcomeClass.fromWire(json['class'] as String?),
    reason: json['reason'] as String? ?? '',
  );

  final String text;
  final OutcomeClass outcomeClass;
  final String reason;
}

/// Why the scene went the way it did (docs/API.md `SceneDetails`, A8, A9, R6).
class SceneDetails {
  const SceneDetails({this.steps = const [], this.chain = const [], this.stoppedAtStep});

  factory SceneDetails.fromJson(Json? json) => json == null
      ? const SceneDetails()
      : SceneDetails(
          steps: _list(json['steps'], SceneStep.fromJson),
          chain: _list(json['chain'], ChainLink.fromJson),
          stoppedAtStep: (json['stopped_at_step'] as num?)?.toInt(),
        );

  final List<SceneStep> steps;
  final List<ChainLink> chain;

  /// A chained plan stopped at this step (0-based, R6); the steps after it never happened.
  final int? stoppedAtStep;

  bool get isEmpty => steps.isEmpty && chain.isEmpty;

  /// Dice decided something here (A3), so the scene has a throw to watch.
  bool get hasThrows => steps.any(
    (step) =>
        step.roll?.thrown != null ||
        step.beats.any((beat) => beat.roll?.thrown != null) ||
        step.struck.any((struck) => struck.roll?.thrown != null),
  );
}

class Scene {
  const Scene({
    required this.turn,
    required this.narration,
    required this.choices,
    this.kind = 'action',
    this.playerAction,
    this.inputMode,
    this.standingActions = const [],
    this.image,
    this.durationLabel,
    this.timeLabel,
    this.personalTimeLabel,
    this.passageLabel,
    this.worldStartS,
    this.worldEndS,
    this.eventSize,
    this.eventTitle,
    this.portraits = const [],
    this.details = const SceneDetails(),
    this.blocked = false,
  });

  factory Scene.fromJson(Json json) {
    final time = json['time'] as Json?;
    final event = json['event'] as Json?;
    final image = switch (json) {
      {'image': final Json image} => SceneImage.fromJson(image),
      {'image_url': final String url} => SceneImage(status: 'ready', url: url), // legacy
      _ => null,
    };
    final playerAction = json['player_action'] as String?;
    return Scene(
      turn: (json['turn'] as num).toInt(),
      narration: json['narration'] as String,
      choices: _list(json['choices'], Choice.fromJson),
      kind: json['kind'] as String? ?? (playerAction == null ? 'opening' : 'action'),
      playerAction: playerAction,
      inputMode: json['input_mode'] as String?,
      standingActions: [for (final a in json['standing_actions'] as List? ?? const []) a as String],
      image: image,
      durationLabel: _text(time?['duration_label']),
      timeLabel: _text(time?['label']),
      personalTimeLabel: _text(time?['personal_label']),
      passageLabel: _text(time?['passage_label']),
      worldStartS: (time?['world_start_s'] as num?)?.toInt(),
      worldEndS: (time?['world_end_s'] as num?)?.toInt(),
      eventSize: event?['size'] as String?,
      eventTitle: event?['title'] as String?,
      portraits: _list(json['portraits'], ScenePortrait.fromJson),
      details: SceneDetails.fromJson(json['details'] as Json?),
      blocked: json['blocked'] as bool? ?? false,
    );
  }

  /// A label, or null when the server sent none or an empty one.
  static String? _text(Object? value) => value is String && value.trim().isNotEmpty ? value : null;

  final int turn;
  final String narration;
  final List<Choice> choices;

  /// opening, action, choice or standing.
  final String kind;
  final String? playerAction;

  /// typed, voice, voice_edited or choice (V7).
  final String? inputMode;

  /// wait and observe, when the scene offers them (S2).
  final List<String> standingActions;
  final SceneImage? image;

  /// How long the scene took in the world, such as "+8 h" (W10). An opening has none.
  final String? durationLabel;

  /// When the scene ended, in the world's calendar, such as "Day 3, dusk".
  final String? timeLabel;

  /// Both clocks when the player's ran apart from the world's, such as "World: +0 s. You: +40 s."
  /// (W10a).
  final String? personalTimeLabel;

  /// The heading of a scene that hours or days passed in, such as "Three days later" (W10), in
  /// the story's language. A short scene has none.
  final String? passageLabel;
  final int? worldStartS;
  final int? worldEndS;
  final String? eventSize;
  final String? eventTitle;
  final List<ScenePortrait> portraits;
  final SceneDetails details;

  /// The player blocked this scene (F6): the app shows a placeholder instead of its text.
  final bool blocked;

  bool get spoken => inputMode == 'voice' || inputMode == 'voice_edited';

  bool get hasTime => durationLabel != null || timeLabel != null || personalTimeLabel != null;

  Scene withImage(SceneImage? image) => Scene(
    turn: turn,
    narration: narration,
    choices: choices,
    kind: kind,
    playerAction: playerAction,
    inputMode: inputMode,
    standingActions: standingActions,
    image: image,
    durationLabel: durationLabel,
    timeLabel: timeLabel,
    personalTimeLabel: personalTimeLabel,
    passageLabel: passageLabel,
    worldStartS: worldStartS,
    worldEndS: worldEndS,
    eventSize: eventSize,
    eventTitle: eventTitle,
    portraits: portraits,
    details: details,
    blocked: blocked,
  );
}

/// A story's settings (S6, M2, S2, S13), changed with `PATCH /v1/stories/{id}`.
class StorySettings {
  const StorySettings({
    this.narrationLength = 'medium',
    this.tone,
    this.difficulty = 'balanced',
    this.eventFrequency = 'normal',
    this.images = 'key_moments',
    this.suggestions = true,
    this.language = 'en',
    this.accent,
  });

  factory StorySettings.fromJson(Json? json) => json == null
      ? const StorySettings()
      : StorySettings(
          narrationLength: json['narration_length'] as String? ?? 'medium',
          tone: switch (json['tone']) {
            final String tone when tone.trim().isNotEmpty => tone,
            _ => null,
          },
          difficulty: json['difficulty'] as String? ?? 'balanced',
          eventFrequency: json['event_frequency'] as String? ?? 'normal',
          images: json['images'] as String? ?? 'key_moments',
          suggestions: json['suggestions'] as bool? ?? true,
          language: json['language'] as String? ?? 'en',
          accent: json['accent'] as String?,
        );

  /// short, medium or long.
  final String narrationLength;

  /// The player's own words for the tone, such as "grim and quiet".
  final String? tone;

  /// story, balanced or brutal (A5).
  final String difficulty;

  /// calm, normal or dramatic (W16).
  final String eventFrequency;

  /// off, key_moments or more (M2).
  final String images;

  /// Whether scenes suggest choices (S2).
  final bool suggestions;

  /// The language the story is written in, `en`, `es` or `ca` (S10): the one it started in. It
  /// never changes, so the settings don't offer it and a PATCH never sends it.
  final String language;

  /// The color the player chose for the story, an accent's name such as `jade` (S13), or null
  /// for its genre's.
  final String? accent;

  Json toJson() => {
    'narration_length': narrationLength,
    // Null clears the tone.
    'tone': tone,
    'difficulty': difficulty,
    'event_frequency': eventFrequency,
    'images': images,
    'suggestions': suggestions,
    // Null goes back to the genre's color.
    'accent': accent,
  };

  /// Only the fields that differ from [base], for a PATCH that leaves the rest as they are on the
  /// server, even if another device changed them meanwhile (S6).
  Json changesFrom(StorySettings base) {
    final mine = toJson();
    final theirs = base.toJson();
    return {
      for (final MapEntry(:key, :value) in mine.entries)
        if (theirs[key] != value) key: value,
    };
  }

  /// The settings with these changed. [accent] is a getter so that it can go back to null, the
  /// genre's color (S13).
  StorySettings copyWith({
    String? narrationLength,
    String? tone,
    String? difficulty,
    String? eventFrequency,
    String? images,
    bool? suggestions,
    String? Function()? accent,
  }) => StorySettings(
    narrationLength: narrationLength ?? this.narrationLength,
    tone: tone == null ? this.tone : (tone.trim().isEmpty ? null : tone.trim()),
    difficulty: difficulty ?? this.difficulty,
    eventFrequency: eventFrequency ?? this.eventFrequency,
    images: images ?? this.images,
    suggestions: suggestions ?? this.suggestions,
    language: language,
    accent: accent == null ? this.accent : accent(),
  );

  @override
  bool operator ==(Object other) =>
      other is StorySettings &&
      other.narrationLength == narrationLength &&
      other.tone == tone &&
      other.difficulty == difficulty &&
      other.eventFrequency == eventFrequency &&
      other.images == images &&
      other.suggestions == suggestions &&
      other.language == language &&
      other.accent == accent;

  @override
  int get hashCode => Object.hash(
    narrationLength,
    tone,
    difficulty,
    eventFrequency,
    images,
    suggestions,
    language,
    accent,
  );
}

/// How the player character's story ended (N6, docs/API.md `Ending`). A story at its ending takes
/// no more turns: the player closes it or starts again from its premise.
class StoryEnding {
  const StoryEnding({
    required this.kind,
    this.characterId = '',
    this.character = '',
    this.selfInflicted = false,
    this.turn,
    this.closed = false,
    this.rewind = 0,
  });

  factory StoryEnding.fromJson(Json json) => StoryEnding(
    kind: json['kind'] as String? ?? 'death',
    characterId: json['character_id'] as String? ?? '',
    character: json['character'] as String? ?? '',
    selfInflicted: json['self_inflicted'] as bool? ?? false,
    turn: (json['turn'] as num?)?.toInt(),
    closed: json['closed'] as bool? ?? false,
    rewind: (json['rewind'] as num?)?.toInt() ?? 0,
  );

  static StoryEnding? maybe(Object? json) => json is Json ? StoryEnding.fromJson(json) : null;

  /// `death` (the character died) or `chosen` (the player ended it with /end).
  final String kind;
  final String characterId;

  /// Who fell or retired, by the name the story last knew them by.
  final String character;

  /// Harm they aimed at their own body killed them (F1).
  final bool selfInflicted;

  /// The scene the ending came in.
  final int? turn;

  /// The player closed the story; it stays in the Library to read.
  final bool closed;

  /// How many scenes back the player can rewind (C8): a death not by the character's own hand,
  /// up to 5 scenes on Story, 1 on Balanced and none on Brutal. 0 once closed.
  final int rewind;

  bool get isDeath => kind == 'death';

  /// The ending can be taken back a few scenes (C8).
  bool get canRewind => !closed && rewind > 0;

  @override
  bool operator ==(Object other) =>
      other is StoryEnding &&
      other.kind == kind &&
      other.characterId == characterId &&
      other.character == character &&
      other.selfInflicted == selfInflicted &&
      other.turn == turn &&
      other.closed == closed &&
      other.rewind == rewind;

  @override
  int get hashCode =>
      Object.hash(kind, characterId, character, selfInflicted, turn, closed, rewind);
}

/// Someone of the player character's family who can carry the story on after its ending (N6):
/// a child or grandchild, or a child not born yet.
class Heir {
  const Heir({
    required this.id,
    required this.name,
    this.relation = 'child',
    this.age,
    this.unborn = false,
    this.years = 0,
  });

  factory Heir.fromJson(Json json) => Heir(
    id: json['id'] as String,
    name: json['name'] as String? ?? '',
    relation: json['relation'] as String? ?? 'child',
    age: (json['age'] as num?)?.toInt(),
    unborn: json['unborn'] as bool? ?? false,
    years: (json['years'] as num? ?? 0).toInt(),
  );

  static Heir? maybe(Object? json) => json is Json ? Heir.fromJson(json) : null;

  final String id;
  final String name;

  /// child, grandchild or great-grandchild of the player character whose story ended.
  final String relation;

  /// Their age now; null for a child not born yet.
  final int? age;
  final bool unborn;

  /// The years the story skips before they can act: until they are 16, or born and 16.
  final int years;
}

/// Someone drawn to carry a story on after its ending (N6, docs/API.md `Successor`): a random
/// person of the world, by its population odds, or one of the player character's heirs. The
/// player starts as them or chooses someone else.
class Successor {
  const Successor({
    required this.name,
    this.age,
    this.station = 'common',
    this.oneIn = 1,
    this.master = false,
    this.place,
    this.people,
    this.lines = const [],
    this.situation = '',
    this.draws = 1,
    this.heir,
  });

  factory Successor.fromJson(Json json) => Successor(
    name: json['name'] as String? ?? '',
    age: (json['age'] as num?)?.toInt(),
    station: json['station'] as String? ?? 'common',
    oneIn: (json['one_in'] as num? ?? 1).toInt(),
    master: json['master'] as bool? ?? false,
    place: json['place'] as String?,
    people: json['people'] as String?,
    lines: _strings(json['lines']),
    situation: json['situation'] as String? ?? '',
    draws: (json['draws'] as num? ?? 1).toInt(),
    heir: Heir.maybe(json['heir']),
  );

  static Successor? maybe(Object? json) => json is Json ? Successor.fromJson(json) : null;

  final String name;
  final int? age;

  /// common, skilled, notable, noble or royal: where they stand among the world's people.
  final String station;

  /// How rare a person like this is: one in this many. 1 for the commonest.
  final int oneIn;

  /// A hidden master: the player knows, and the world doesn't.
  final bool master;

  /// Where they live, and the people they belong to, by name.
  final String? place;
  final String? people;

  /// Who they are, in the world's own words (G2, G16).
  final List<String> lines;

  /// The moment their first scene opens on.
  final String situation;

  /// How many people have been drawn for this ending so far.
  final int draws;

  /// The player character's heir, rather than someone drawn at random.
  final Heir? heir;
}

/// A turn the story still owes (docs/API.md `Story.unfinished_turn`, A3): its steps were decided
/// and shown, and its scene isn't saved yet. Whatever is sent next plays it out.
class UnfinishedTurn {
  const UnfinishedTurn({required this.turn, required this.kind, this.action});

  static UnfinishedTurn? maybe(Object? json) => json is Json
      ? UnfinishedTurn(
          turn: (json['turn'] as num?)?.toInt() ?? 0,
          kind: json['kind'] as String? ?? 'action',
          action: json['action'] as String?,
        )
      : null;

  final int turn;

  /// action, choice, standing or end.
  final String kind;

  /// The words that were sent, a choice's label, `wait` or `observe`, or an end turn's note.
  final String? action;
}

class Story {
  const Story({
    required this.id,
    required this.title,
    required this.scenes,
    this.genre = '',
    this.premise,
    this.rating,
    this.version = 0,
    this.clockLabel,
    this.coverUrl,
    this.settings = const StorySettings(),
    this.ending,
    this.successor,
    this.heirs = const [],
    this.openingDue = false,
    this.unfinishedTurn,
  });

  factory Story.fromJson(Json json) => Story(
    id: json['id'] as String,
    title: json['title'] as String,
    scenes: _list(json['scenes'], Scene.fromJson)..sort((a, b) => a.turn.compareTo(b.turn)),
    genre: json['genre'] as String? ?? '',
    premise: json['premise'] as String?,
    rating: json['rating'] as String?,
    version: (json['version'] as num? ?? 0).toInt(),
    clockLabel: (json['clock'] as Json?)?['label'] as String?,
    coverUrl: json['cover_url'] as String?,
    settings: StorySettings.fromJson(json['settings'] as Json?),
    ending: StoryEnding.maybe(json['ending']),
    successor: Successor.maybe(json['successor']),
    heirs: _list(json['heirs'], Heir.fromJson),
    openingDue: json['opening_due'] as bool? ?? false,
    unfinishedTurn: UnfinishedTurn.maybe(json['unfinished_turn']),
  );

  final String id;
  final String title;

  /// The scenes the app has, oldest first. A long story arrives with only its latest scenes; older
  /// ones load as the player scrolls back.
  final List<Scene> scenes;
  final String genre;
  final String? premise;

  /// teen or mature.
  final String? rating;

  /// The version the next turn sends as `expected_version` (T10).
  final int version;

  /// The world's date and time now, such as "Day 3, dusk" (W10).
  final String? clockLabel;
  final String? coverUrl;
  final StorySettings settings;

  /// Set once the story has reached its ending (N6). Then it takes no more turns.
  final StoryEnding? ending;

  /// Who was drawn to carry the story on after its ending, until the player starts as them (N6).
  final Successor? successor;

  /// Who of the player character's family can carry the story on from its ending (N6).
  final List<Heir> heirs;

  /// Someone new carries the story on, and their first scene is still to be told: the next turn
  /// is their opening (N6).
  final bool openingDue;

  /// The turn the story still owes (A3), which the next request plays out.
  final UnfinishedTurn? unfinishedTurn;

  /// [unfinishedTurn] is a function so it can be set to none.
  Story copyWith({
    List<Scene>? scenes,
    int? version,
    String? clockLabel,
    String? title,
    StorySettings? settings,
    StoryEnding? ending,
    bool? openingDue,
    UnfinishedTurn? Function()? unfinishedTurn,
  }) => Story(
    id: id,
    title: title ?? this.title,
    scenes: scenes ?? this.scenes,
    genre: genre,
    premise: premise,
    rating: rating,
    version: version ?? this.version,
    clockLabel: clockLabel ?? this.clockLabel,
    coverUrl: coverUrl,
    settings: settings ?? this.settings,
    ending: ending ?? this.ending,
    successor: successor,
    heirs: heirs,
    openingDue: openingDue ?? this.openingDue,
    unfinishedTurn: unfinishedTurn == null ? this.unfinishedTurn : unfinishedTurn(),
  );

  /// The story with a saved scene. Once any scene is saved, no opening is due and no turn is
  /// owed.
  Story withScene(Scene scene, {required int version, String? clockLabel, StoryEnding? ending}) =>
      copyWith(
        scenes: [...scenes.where((s) => s.turn != scene.turn), scene],
        version: version,
        clockLabel: clockLabel,
        ending: ending,
        openingDue: false,
        unfinishedTurn: () => null,
      );
}

/// The `/status` page (S5): the sheet, reputation and the date (docs/API.md `StatusView`).
class StatusData {
  const StatusData({
    required this.name,
    required this.lines,
    required this.reputation,
    required this.since,
    this.sheet,
    this.clockLabel,
    this.portraitUrl,
  });

  factory StatusData.fromJson(Json json) {
    final character = json['character'] as Json? ?? const {};
    return StatusData(
      name: character['name'] as String? ?? '',
      portraitUrl: character['portrait_url'] as String?,
      lines: _strings(character['lines']),
      sheet: json['sheet'] is Json ? Sheet.fromJson(json['sheet'] as Json) : null,
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

  /// The sheet in sections (G13). A server from before it sends only [lines].
  final Sheet? sheet;

  /// The sheet as plain lines, shown only when there is no [sheet].
  final List<String> lines;
  final List<(String name, String label)> reputation;
  final List<(String text, String ago)> since;
  final String? clockLabel;

  /// The player character's portrait, once it is drawn (M4).
  final String? portraitUrl;
}

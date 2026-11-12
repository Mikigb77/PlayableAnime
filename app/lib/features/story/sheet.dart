/// The player character's sheet in sections (docs/API.md `Sheet`; G13, G16): who they are, how
/// they are, where they stand on the world's ladders, what they hold, what they can do and what
/// they are like. The server words everything in the story's language and sends, next to each
/// word, the value it says, so the screen draws a meter or picks a color without reading words.
library;

import '../../core/json.dart';

List<String> _lines(Object? json) => [
  for (final line in json is List ? json : const [])
    if (line is String && line.trim().isNotEmpty) line.trim(),
];

List<T> _list<T>(Object? json, T Function(JsonMap) fromJson) => [
  for (final item in json is List ? json : const [])
    if (item is JsonMap) fromJson(item),
];

String _text(Object? json) => json is String ? json.trim() : '';

String? _label(Object? json) => _text(json).isEmpty ? null : _text(json);

int _count(Object? json, {int or = 0}) => json is num ? json.toInt() : or;

/// A share from 0 to 1, or nothing where the server sent none.
double? _share(Object? json) => json is num ? json.toDouble().clamp(0, 1).toDouble() : null;

/// How hurt they are, from fine to dying. A health the app doesn't know reads as hurt.
enum Health {
  unhurt,
  hurt,
  wounded,
  badlyWounded,
  dying;

  static Health parse(Object? json) => switch (json) {
    null || 'unhurt' => unhurt,
    'wounded' => wounded,
    'badly_wounded' => badlyWounded,
    'dying' => dying,
    _ => hurt,
  };
}

class SheetWound {
  const SheetWound({required this.text, this.lasting = false});

  factory SheetWound.fromJson(JsonMap json) =>
      SheetWound(text: _text(json['text']), lasting: json['lasting'] == true);

  final String text;

  /// An injury that stays, such as a lost eye.
  final bool lasting;
}

/// A passing state such as drunk or drained by a power, with what it does and when it passes.
class SheetState {
  const SheetState({required this.name, this.effect = '', this.endsLabel});

  factory SheetState.fromJson(JsonMap json) => SheetState(
    name: _text(json['name']),
    effect: _text(json['effect']),
    endsLabel: _label(json['ends_label']),
  );

  final String name;
  final String effect;
  final String? endsLabel;
}

/// What is left of one of the world's energies (qi, aura, mana), in percent.
class SheetReserve {
  const SheetReserve({required this.name, required this.level});

  factory SheetReserve.fromJson(JsonMap json) =>
      SheetReserve(name: _text(json['name']), level: _count(json['level']).clamp(0, 100));

  final String name;
  final int level;
}

class SheetCondition {
  const SheetCondition({
    this.health = Health.unhurt,
    this.healthLabel = '',
    this.wounds = const [],
    this.states = const [],
    this.reserves = const [],
    this.expectingLabel,
  });

  factory SheetCondition.fromJson(JsonMap json) => SheetCondition(
    health: Health.parse(json['health']),
    healthLabel: _text(json['health_label']),
    wounds: [
      for (final wound in _list(json['wounds'], SheetWound.fromJson))
        if (wound.text.isNotEmpty) wound,
    ],
    states: [
      for (final state in _list(json['states'], SheetState.fromJson))
        if (state.name.isNotEmpty) state,
    ],
    reserves: [
      for (final reserve in _list(json['reserves'], SheetReserve.fromJson))
        if (reserve.name.isNotEmpty) reserve,
    ],
    expectingLabel: _label(json['expecting_label']),
  );

  final Health health;
  final String healthLabel;
  final List<SheetWound> wounds;
  final List<SheetState> states;
  final List<SheetReserve> reserves;

  /// A child on the way, and when it is due (N6).
  final String? expectingLabel;
}

class SheetRung {
  const SheetRung({
    required this.name,
    this.stage = '',
    this.filled,
    this.description = '',
    this.note = '',
  });

  factory SheetRung.fromJson(JsonMap json) => SheetRung(
    name: _text(json['name']),
    stage: _text(json['stage']),
    filled: _share(json['filled']),
    description: _text(json['description']),
    note: _text(json['note']),
  );

  final String name;

  /// How full their rank is, in words (G19): "Late stage", or that a breakthrough can be
  /// tried once it is at its peak.
  final String stage;

  /// How full their rank is, from 0 to 1. Nothing for a rung they left behind, on a ladder's
  /// last rung, and from a server that doesn't send it.
  final double? filled;
  final String description;

  /// When, where the record holds it: "Reached, day 9" or "Left behind, day 9".
  final String note;
}

/// A rung above their own, as far as they know of it (C6): solid once the story confirmed it,
/// only heard of until then.
class SheetRungAbove {
  const SheetRungAbove({
    required this.name,
    this.known = false,
    this.note = '',
    this.said = const [],
    this.gapBelow = false,
  });

  factory SheetRungAbove.fromJson(JsonMap json) => SheetRungAbove(
    name: _text(json['name']),
    known: json['known'] == true,
    note: _text(json['note']),
    said: _lines(json['said']),
    gapBelow: json['gap_below'] == true,
  );

  final String name;

  /// Whether the story confirmed it. Until then they have only heard its name.
  final bool known;

  /// How they know of it: "Heard of, day 14", "Confirmed before Elder Han, day 15".
  final String note;

  /// What they have learned or heard about it, in the record's own words.
  final List<String> said;

  /// Whether rungs lie under it that nobody has named to them.
  final bool gapBelow;
}

/// One of the world's ladders (G18). [rungs] runs from its first rung up to where they stand,
/// lowest first, so the last one is theirs; it is empty for a ladder they don't stand on.
/// [above] holds the rungs over their own that they have heard of, lowest first, and the
/// server sends nothing else of what lies higher (C6), except [higher]: who they have seen
/// stand above all of those, in the server's words, with no rung named.
class SheetPath {
  const SheetPath({
    required this.name,
    this.rungs = const [],
    this.above = const [],
    this.higher = '',
  });

  factory SheetPath.fromJson(JsonMap json) => SheetPath(
    name: _text(json['name']),
    higher: _text(json['higher']),
    rungs: [
      for (final rung in _list(json['rungs'], SheetRung.fromJson))
        if (rung.name.isNotEmpty) rung,
    ],
    above: [
      for (final rung in _list(json['above'], SheetRungAbove.fromJson))
        if (rung.name.isNotEmpty) rung,
    ],
  );

  final String name;
  final List<SheetRung> rungs;
  final List<SheetRungAbove> above;
  final String higher;

  /// A ladder they neither stand on nor have heard a rung of is no path of theirs.
  bool get isEmpty => rungs.isEmpty && above.isEmpty;
}

/// What kind of thing a belonging is. One the app doesn't know is just a thing.
enum ItemKind {
  weapon,
  armour,
  gear,
  treasure,
  consumable,
  vehicle,
  property,
  document,
  other;

  static ItemKind parse(Object? json) =>
      values.firstWhere((kind) => kind.name == json, orElse: () => other);
}

class SheetItem {
  const SheetItem({
    required this.name,
    this.kind = ItemKind.other,
    this.kindLabel = '',
    this.description = '',
    this.history = '',
    this.quantity = 1,
    this.carried = true,
  });

  factory SheetItem.fromJson(JsonMap json) => SheetItem(
    name: _text(json['name']),
    kind: ItemKind.parse(json['kind']),
    kindLabel: _text(json['kind_label']),
    description: _text(json['description']),
    history: _text(json['history']),
    quantity: _count(json['quantity'], or: 1),
    carried: json['carried'] != false,
  );

  final String name;
  final ItemKind kind;
  final String kindLabel;
  final String description;

  /// Where a thing with a past comes from.
  final String history;
  final int quantity;

  /// On them now, or kept somewhere else.
  final bool carried;
}

class SheetSkill {
  const SheetSkill({required this.name, this.levelLabel = '', this.dice = 1, this.notes = ''});

  factory SheetSkill.fromJson(JsonMap json) => SheetSkill(
    name: _text(json['name']),
    levelLabel: _text(json['level_label']),
    dice: _count(json['dice'], or: 1),
    notes: _text(json['notes']),
  );

  final String name;
  final String levelLabel;

  /// The dice a step throws on this skill alone (A3), one to five.
  final int dice;
  final String notes;
}

class SheetPower {
  const SheetPower({
    required this.name,
    this.description = '',
    this.limits = const [],
    this.cost = '',
    this.ready = true,
    this.readyLabel = '',
    this.secret = false,
  });

  factory SheetPower.fromJson(JsonMap json) => SheetPower(
    name: _text(json['name']),
    description: _text(json['description']),
    limits: _lines(json['limits']),
    cost: _text(json['cost']),
    ready: json['ready'] != false,
    readyLabel: _text(json['ready_label']),
    secret: json['secret'] == true,
  );

  final String name;
  final String description;
  final List<String> limits;

  /// What using it costs, as the sheet says (G13), or nothing where the world charges nothing.
  final String cost;
  final bool ready;

  /// "Ready", or "Ready in 3 hours" while it recovers.
  final String readyLabel;

  /// Nobody in the world knows of it.
  final bool secret;
}

class SheetTechnique {
  const SheetTechnique({
    required this.name,
    this.style = '',
    this.effect = '',
    this.cost = '',
    this.sourceLabel = '',
    this.masteryLabel = '',
    this.dice = 1,
    this.uses = 0,
    this.need,
  });

  factory SheetTechnique.fromJson(JsonMap json) => SheetTechnique(
    name: _text(json['name']),
    style: _text(json['style']),
    effect: _text(json['effect']),
    cost: _text(json['cost']),
    sourceLabel: _text(json['source_label']),
    masteryLabel: _text(json['mastery_label']),
    dice: _count(json['dice'], or: 1),
    uses: _count(json['uses']),
    need: json['need'] is num && (json['need'] as num) > 0 ? (json['need'] as num).toInt() : null,
  );

  final String name;
  final String style;
  final String effect;
  final String cost;

  /// Where they have it from, when the story recorded it: "Your own", "Learned from Zhao Kun".
  final String sourceLabel;

  /// How well they have it: "Learning", "Second nature".
  final String masteryLabel;

  /// The dice it throws by its mastery (A3), one to five.
  final int dice;

  /// Uses counted toward the next mastery, and how many reach it at their own pace (A4). No
  /// [need] where use alone takes it no further.
  final int uses;
  final int? need;
}

enum TraitKind {
  gift,
  flaw,
  quirk;

  static TraitKind parse(Object? json) =>
      values.firstWhere((kind) => kind.name == json, orElse: () => quirk);
}

class SheetTrait {
  const SheetTrait({
    required this.name,
    this.kind = TraitKind.quirk,
    this.kindLabel = '',
    this.description = '',
  });

  factory SheetTrait.fromJson(JsonMap json) => SheetTrait(
    name: _text(json['name']),
    kind: TraitKind.parse(json['kind']),
    kindLabel: _text(json['kind_label']),
    description: _text(json['description']),
  );

  final String name;
  final TraitKind kind;
  final String kindLabel;
  final String description;
}

class SheetTalent {
  const SheetTalent({
    required this.name,
    this.weakness = false,
    this.strengthLabel = '',
    this.paceLabel = '',
    this.covers = '',
  });

  factory SheetTalent.fromJson(JsonMap json) => SheetTalent(
    name: _text(json['name']),
    weakness: json['strength'] == 'slow',
    strengthLabel: _text(json['strength_label']),
    paceLabel: _text(json['pace_label']),
    covers: _text(json['covers']),
  );

  final String name;

  /// A talent that slows them down: what it covers is learned at half the pace.
  final bool weakness;

  /// "Genius", "A knack", "Weakness".
  final String strengthLabel;

  /// "Four times as fast".
  final String paceLabel;

  /// What it reaches, in plain words.
  final String covers;
}

/// One thing they gained (A4, G17), as the sheet tells how they grew: what, on which day in the
/// world's calendar, and how it was made where the record says.
class SheetGain {
  const SheetGain({required this.text, this.when = '', this.how = '', this.kind = ''});

  factory SheetGain.fromJson(JsonMap json) => SheetGain(
    text: _text(json['text']),
    when: _text(json['when']),
    how: _text(json['how']),
    kind: _text(json['kind']),
  );

  /// "Broke through to Qi Condensation", "Swordsmanship: Skilled".
  final String text;

  /// "Day 9".
  final String when;

  /// "With a master", "By doing it". Empty where the record doesn't say.
  final String how;

  /// What kind of gain it was: `breakthrough`, `stage`, `skill`, `learned`, `mastery` or
  /// `new_use`.
  final String kind;

  /// A rung of one of the world's ladders, which the timeline lights.
  bool get isBreakthrough => kind == 'breakthrough';
}

class Sheet {
  const Sheet({
    this.about = const [],
    this.description = '',
    this.condition = const SheetCondition(),
    this.paths = const [],
    this.moneyLabel,
    this.items = const [],
    this.skills = const [],
    this.powers = const [],
    this.techniques = const [],
    this.traits = const [],
    this.temperament = const [],
    this.talents = const [],
    this.talentNotes = const [],
    this.grew = const [],
  });

  factory Sheet.fromJson(JsonMap json) => Sheet(
    about: _lines(json['about']),
    description: _text(json['description']),
    condition: switch (json['condition']) {
      final JsonMap condition => SheetCondition.fromJson(condition),
      _ => const SheetCondition(),
    },
    paths: [
      for (final path in _list(json['paths'], SheetPath.fromJson))
        if (!path.isEmpty) path,
    ],
    moneyLabel: _label(json['money_label']),
    items: _named(_list(json['items'], SheetItem.fromJson), (item) => item.name),
    skills: _named(_list(json['skills'], SheetSkill.fromJson), (skill) => skill.name),
    powers: _named(_list(json['powers'], SheetPower.fromJson), (power) => power.name),
    techniques: _named(_list(json['techniques'], SheetTechnique.fromJson), (t) => t.name),
    traits: _named(_list(json['traits'], SheetTrait.fromJson), (trait) => trait.name),
    temperament: _lines(json['temperament']),
    talents: _named(_list(json['talents'], SheetTalent.fromJson), (talent) => talent.name),
    talentNotes: _lines(json['talent_notes']),
    grew: _named(_list(json['grew'], SheetGain.fromJson), (gain) => gain.text),
  );

  /// Who they are in a few words: their place in a faction, a title, their age.
  final List<String> about;

  /// How they come across to anyone who meets them.
  final String description;
  final SheetCondition condition;
  final List<SheetPath> paths;

  /// The purse, in the world's currency: "12 silver taels". Null where they have none to speak of.
  final String? moneyLabel;
  final List<SheetItem> items;
  final List<SheetSkill> skills;
  final List<SheetPower> powers;
  final List<SheetTechnique> techniques;
  final List<SheetTrait> traits;
  final List<String> temperament;
  final List<SheetTalent> talents;

  /// What the story ruled about each thing a talent reaches, a line each (A4).
  final List<String> talentNotes;

  /// How they grew, latest first. Empty from a server that doesn't send it.
  final List<SheetGain> grew;

  Iterable<SheetItem> get carried => items.where((item) => item.carried);
  Iterable<SheetItem> get elsewhere => items.where((item) => !item.carried);

  bool get hasMoves => powers.isNotEmpty || techniques.isNotEmpty;
  bool get hasNature => traits.isNotEmpty || temperament.isNotEmpty || talents.isNotEmpty;
}

List<T> _named<T>(List<T> entries, String Function(T) name) => [
  for (final entry in entries)
    if (name(entry).isNotEmpty) entry,
];

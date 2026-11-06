import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:playable_anime/design/design.dart';

void main() {
  test('each flagship genre gets its own accent', () {
    expect(GenreAccent.forGenre('Cultivation'), GenreAccent.jade);
    expect(GenreAccent.forGenre('Knights and aura'), GenreAccent.azure);
    expect(GenreAccent.forGenre('Many races and monsters'), GenreAccent.ember);
    expect(GenreAccent.forGenre('Reincarnation'), GenreAccent.violet);
    expect(GenreAccent.forGenre('Grounded modern'), GenreAccent.crimson);
    expect(GenreAccent.forGenre('Science fiction'), GenreAccent.cyan);
    expect(GenreAccent.forGenre('Supernatural in a hidden world'), GenreAccent.orchid);
  });

  test('every starter genre beyond the flagship gets an accent', () {
    expect(GenreAccent.forGenre('Grounded mystery'), GenreAccent.crimson);
    expect(GenreAccent.forGenre('Mecha'), GenreAccent.cyan);
    expect(GenreAccent.forGenre('Cyberpunk'), GenreAccent.cyan);
    expect(GenreAccent.forGenre('Gothic horror'), GenreAccent.orchid);
    expect(GenreAccent.forGenre('Pirate fantasy'), GenreAccent.ember);
    expect(GenreAccent.forGenre('Cozy fantasy'), GenreAccent.ember);
    expect(GenreAccent.forGenre('Post-apocalyptic'), GenreAccent.ember);
    expect(GenreAccent.forGenre('Superpowers'), GenreAccent.azure);
  });

  test('a starter genre in Spanish gets the same accent as in English (S10)', () {
    // The genres of the starters as Discover shows them in Spanish (`catalog_es.py`).
    const pairs = {
      'Cultivation': 'Cultivo',
      'Knights and aura': 'Caballeros y aura',
      'Races and monsters': 'Razas y monstruos',
      'Reincarnation': 'Reencarnación',
      'Grounded crime': 'Crimen realista',
      'Science fiction': 'Ciencia ficción',
      'Hidden supernatural': 'Lo sobrenatural oculto',
      'Academy fantasy': 'Fantasía de academia',
      'Neon urban fantasy': 'Fantasía urbana de neón',
      'Grounded mystery': 'Misterio realista',
      'Mecha': 'Mecha',
      'Gothic horror': 'Terror gótico',
      'Pirate fantasy': 'Fantasía pirata',
      'Cyberpunk': 'Cyberpunk',
      'Cozy fantasy': 'Fantasía acogedora',
      'Post-apocalyptic': 'Postapocalíptico',
      'Superpowers': 'Superpoderes',
      // No accent of its own in either language.
      'Samurai drama': 'Drama de samuráis',
    };
    for (final MapEntry(key: english, value: spanish) in pairs.entries) {
      expect(GenreAccent.forGenre(spanish), GenreAccent.forGenre(english), reason: spanish);
      if (english != 'Samurai drama') {
        expect(GenreAccent.forGenre(english), isNot(GenreAccent.lucid), reason: english);
      }
    }
  });

  test('a more specific genre wins over a broad one', () {
    expect(GenreAccent.forGenre('Urban fantasy'), GenreAccent.orchid);
    expect(GenreAccent.forGenre('Isekai fantasy'), GenreAccent.violet);
  });

  test('an unknown or missing genre keeps the app accent', () {
    expect(GenreAccent.forGenre(null), GenreAccent.lucid);
    expect(GenreAccent.forGenre(''), GenreAccent.lucid);
    expect(GenreAccent.forGenre('Your own'), GenreAccent.lucid);
  });

  test('a story theme takes its genre accent', () {
    final jade = AppTheme.build(Brightness.dark, GenreAccent.jade);
    final lucid = AppTheme.build(Brightness.dark, GenreAccent.lucid);
    expect(jade.extension<LucidColors>()!.accent, isNot(lucid.extension<LucidColors>()!.accent));
    expect(jade.colorScheme.primary, jade.extension<LucidColors>()!.accent);
    // Themes are cached: the same pair builds once.
    expect(identical(AppTheme.build(Brightness.dark, GenreAccent.jade), jade), isTrue);
  });
}

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

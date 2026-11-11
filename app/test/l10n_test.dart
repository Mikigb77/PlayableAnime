import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// The app's fixed text in English, Spanish and Catalan (S10): every string the app shows exists
/// in each, with the same placeholders, so a string added in English without its translations
/// fails here.
void main() {
  Map<String, dynamic> arb(String locale) =>
      jsonDecode(File('lib/l10n/app_$locale.arb').readAsStringSync()) as Map<String, dynamic>;

  Map<String, String> messages(Map<String, dynamic> json) => {
    for (final MapEntry(:key, :value) in json.entries)
      if (!key.startsWith('@')) key: value as String,
  };

  final template = arb('en');
  final english = messages(template);
  // Each translation, by its locale and the language's name in English.
  final translations = {
    'es': ('Spanish', messages(arb('es'))),
    'ca': ('Catalan', messages(arb('ca'))),
  };

  test('the app ships exactly these languages', () {
    final shipped = [
      for (final file in Directory('lib/l10n').listSync())
        if (RegExp(r'app_(\w+)\.arb$').firstMatch(file.path) case final match?) match[1]!,
    ]..sort();
    expect(shipped, ['ca', 'en', 'es']);
    for (final locale in translations.keys) {
      expect(arb(locale)['@@locale'], locale);
    }
  });

  // The placeholders the English template declares for a string, such as `name` or `count`.
  Set<String> declared(String key) {
    final meta = template['@$key'] as Map<String, dynamic>?;
    return (meta?['placeholders'] as Map<String, dynamic>? ?? {}).keys.toSet();
  }

  for (final MapEntry(key: locale, value: (name, translated)) in translations.entries) {
    test('every English string has its $name, and nothing else', () {
      expect(translated.keys.toSet().difference(english.keys.toSet()), isEmpty);
      expect(
        english.keys.toSet().difference(translated.keys.toSet()),
        isEmpty,
        reason: 'Add the $name to lib/l10n/app_$locale.arb',
      );
    });

    test('each $name string keeps the placeholders of its English one', () {
      for (final key in english.keys) {
        for (final placeholder in declared(key)) {
          // `{name}`, or a plural or select on it: `{count, plural, ...}`.
          expect(
            translated[key],
            matches(RegExp('\\{$placeholder[},]')),
            reason: '$key: {$placeholder}',
          );
        }
      }
    });
  }

  test('no Spanish string is left in English', () {
    // Words both languages share, and names that stay as they are.
    const same = {
      'appTitle',
      'authEmailLabel',
      'accountApi',
      'accountGore',
      'accountRomance',
      'choiceKindPersonal',
      'colorJade',
      'composerCount',
      'difficultyBrutal',
      'eventsNormal',
      'languageEnglish',
      'languageSpanish',
      'languageCatalan',
      'settingsBrutal',
      'settingsColor',
      'settingsNormal',
    };
    final spanish = translations['es']!.$2;
    final untranslated = [
      for (final MapEntry(:key, value: text) in english.entries)
        if (spanish[key] == text && !same.contains(key)) key,
    ];
    expect(untranslated, isEmpty, reason: 'Translate these in lib/l10n/app_es.arb');
  });

  test('no Catalan string is left in English or Spanish', () {
    // Words Catalan shares with English, and names that stay as they are.
    const same = {
      'appTitle',
      'accountApi',
      'accountGore',
      'choiceKindPersonal',
      'colorJade',
      'composerCount',
      'difficultyBrutal',
      'eventsNormal',
      'languageEnglish',
      'languageSpanish',
      'languageCatalan',
      'memoryRumors',
      'settingsBrutal',
      'settingsColor',
      'settingsNormal',
      'sheetCost',
    };
    final catalan = translations['ca']!.$2;
    final untranslated = [
      for (final MapEntry(:key, value: text) in english.entries)
        if (catalan[key] == text && !same.contains(key)) key,
    ];
    expect(untranslated, isEmpty, reason: 'Translate these in lib/l10n/app_ca.arb');
    // Catalan shares many words with Spanish, but never these letters, so Spanish left behind
    // shows.
    final spanish = [
      for (final MapEntry(:key, value: text) in catalan.entries)
        if (key != 'languageSpanish' && text.contains(RegExp('[ñÑ¿¡áÁ]'))) key,
    ];
    expect(spanish, isEmpty, reason: 'Translate these from Spanish in lib/l10n/app_ca.arb');
  });

  test('the language options name each language in itself', () {
    for (final locale in [english, for (final (_, messages) in translations.values) messages]) {
      expect(locale['languageEnglish'], 'English');
      expect(locale['languageSpanish'], 'Español');
      expect(locale['languageCatalan'], 'Català');
    }
  });
}

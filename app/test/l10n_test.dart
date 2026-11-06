import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// The app's fixed text in English and Spanish (S10): every string the app shows exists in both,
/// with the same placeholders, so a string added in English without its Spanish fails here.
void main() {
  Map<String, dynamic> arb(String locale) =>
      jsonDecode(File('lib/l10n/app_$locale.arb').readAsStringSync()) as Map<String, dynamic>;

  Map<String, String> messages(Map<String, dynamic> json) => {
    for (final MapEntry(:key, :value) in json.entries)
      if (!key.startsWith('@')) key: value as String,
  };

  final template = arb('en');
  final english = messages(template);
  final spanish = messages(arb('es'));

  // The placeholders the English template declares for a string, such as `name` or `count`.
  Set<String> declared(String key) {
    final meta = template['@$key'] as Map<String, dynamic>?;
    return (meta?['placeholders'] as Map<String, dynamic>? ?? {}).keys.toSet();
  }

  test('every English string has its Spanish, and nothing else', () {
    expect(spanish.keys.toSet().difference(english.keys.toSet()), isEmpty);
    expect(
      english.keys.toSet().difference(spanish.keys.toSet()),
      isEmpty,
      reason: 'Add the Spanish to lib/l10n/app_es.arb',
    );
  });

  test('each Spanish string keeps the placeholders of its English one', () {
    for (final key in english.keys) {
      for (final name in declared(key)) {
        // `{name}`, or a plural or select on it: `{count, plural, ...}`.
        expect(spanish[key], matches(RegExp('\\{$name[},]')), reason: '$key: {$name}');
      }
    }
  });

  test('no Spanish string is left in English', () {
    // Words both languages share, and names that stay as they are.
    const same = {
      'appTitle',
      'authEmailLabel',
      'accountApi',
      'accountGore',
      'accountRomance',
      'choiceKindPersonal',
      'composerCount',
      'difficultyBrutal',
      'eventsNormal',
      'languageEnglish',
      'languageSpanish',
      'settingsBrutal',
      'settingsNormal',
    };
    final untranslated = [
      for (final MapEntry(:key, value: text) in english.entries)
        if (spanish[key] == text && !same.contains(key)) key,
    ];
    expect(untranslated, isEmpty, reason: 'Translate these in lib/l10n/app_es.arb');
  });

  test('the language options name each language in itself', () {
    for (final locale in [english, spanish]) {
      expect(locale['languageEnglish'], 'English');
      expect(locale['languageSpanish'], 'Español');
    }
  });
}

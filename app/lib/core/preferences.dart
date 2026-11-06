import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'l10n.dart';

/// The player's appearance choice. Dark by default: the app is designed dark first.
class ThemeModeController extends Notifier<ThemeMode> {
  static const _key = 'appearance.theme_mode';

  @override
  ThemeMode build() {
    _load();
    return ThemeMode.dark;
  }

  Future<void> _load() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final saved = ThemeMode.values.where((m) => m.name == prefs.getString(_key)).firstOrNull;
      if (saved != null) state = saved;
    } on Object {
      // No stored choice (or no storage, as in tests): stay dark.
    }
  }

  Future<void> set(ThemeMode mode) async {
    state = mode;
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_key, mode.name);
    } on Object {
      // The choice still applies for this run.
    }
  }
}

final themeModeProvider = NotifierProvider<ThemeModeController, ThemeMode>(ThemeModeController.new);

/// The app's language (S10): the device's own, or one the player picked. Only the app's fixed
/// text follows it. What a story has already told stays in the language it was written in.
enum AppLanguage {
  system(null),
  english('en'),
  spanish('es');

  const AppLanguage(this.code);

  /// The language code, or null to follow the device.
  final String? code;

  Locale? get locale => code == null ? null : Locale(code!);
}

/// The player's language choice, kept on this device. The device's language by default, and
/// English when the device's isn't one the app has.
class LanguageController extends Notifier<AppLanguage> {
  static const _key = 'appearance.language';

  @override
  AppLanguage build() {
    _load();
    return AppLanguage.system;
  }

  Future<void> _load() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final saved = AppLanguage.values.where((l) => l.name == prefs.getString(_key)).firstOrNull;
      if (saved != null) state = saved;
    } on Object {
      // No stored choice (or no storage, as in tests): follow the device.
    }
  }

  Future<void> set(AppLanguage language) async {
    state = language;
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_key, language.name);
    } on Object {
      // The choice still applies for this run.
    }
  }
}

final languageProvider = NotifierProvider<LanguageController, AppLanguage>(LanguageController.new);

/// The language the app shows now, as a code such as `es`: the player's choice, or the device's
/// languages resolved the way the app resolves them. For what the server writes in the app's
/// language, such as the starter premises (S10).
final appLanguageCodeProvider = Provider<String>((ref) {
  if (ref.watch(languageProvider).code case final chosen?) return chosen;
  final device = WidgetsBinding.instance.platformDispatcher.locales;
  return basicLocaleListResolution(device, AppLocalizations.supportedLocales).languageCode;
});

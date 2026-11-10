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

/// The app's language (S10): the device's own, or one the player picked. The app's fixed text
/// follows it, and a new story starts in it. Each story then stays in the language it started in.
enum AppLanguage {
  system(null),
  english('en'),
  spanish('es'),
  catalan('ca');

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

/// Gamer mode (S15): each turn's dice play before its scene is read. Off by default, and kept on
/// this device like the other preferences.
class GamerModeController extends Notifier<bool> {
  static const _key = 'play.gamer_mode';

  /// The stored choice being read, so a turn played the moment a story opens still gets it.
  Future<void> _loaded = Future.value();

  /// The player flipped the switch before the stored choice was read: theirs wins.
  var _changed = false;

  @override
  bool build() {
    _changed = false;
    _loaded = _load();
    return false;
  }

  /// The player's choice, once the stored one is read.
  Future<bool> loaded() async {
    await _loaded;
    return state;
  }

  Future<void> _load() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final saved = prefs.getBool(_key);
      if (saved != null && !_changed) state = saved;
    } on Object {
      // No stored choice (or no storage, as in tests): off.
    }
  }

  Future<void> set(bool on) async {
    _changed = true;
    state = on;
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setBool(_key, on);
    } on Object {
      // The choice still applies for this run.
    }
  }
}

final gamerModeProvider = NotifierProvider<GamerModeController, bool>(GamerModeController.new);

/// The language the app shows now, as a code such as `es`: the player's choice, or the device's
/// languages resolved the way the app resolves them. For what the server writes in the app's
/// language, such as the starter premises (S10).
final appLanguageCodeProvider = Provider<String>((ref) {
  if (ref.watch(languageProvider).code case final chosen?) return chosen;
  final device = WidgetsBinding.instance.platformDispatcher.locales;
  return basicLocaleListResolution(device, AppLocalizations.supportedLocales).languageCode;
});

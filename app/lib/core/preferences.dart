import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

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

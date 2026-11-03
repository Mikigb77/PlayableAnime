import 'package:flutter/material.dart';

abstract final class AppTheme {
  static const _seed = Color(0xFF8B5CF6);

  static final dark = ThemeData(
    colorScheme: ColorScheme.fromSeed(seedColor: _seed, brightness: Brightness.dark),
  );

  static final light = ThemeData(colorScheme: ColorScheme.fromSeed(seedColor: _seed));
}

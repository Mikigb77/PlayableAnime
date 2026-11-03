import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'app.dart';
import 'core/api/api_providers.dart';

void main() {
  runApp(const ProviderScope(retry: retryTransient, child: App()));
}

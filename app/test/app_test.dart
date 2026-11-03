import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:playable_anime/app.dart';
import 'package:playable_anime/features/story/story_models.dart';
import 'package:playable_anime/features/story/story_repository.dart';

void main() {
  testWidgets('Discover lists premises inside the tab shell', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          premisesProvider.overrideWith(
            (ref) async => const [
              Premise(id: 'p1', title: 'Test Premise', genre: 'Test', premise: 'A premise.'),
            ],
          ),
        ],
        child: const App(),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Test Premise'), findsOneWidget);
    expect(find.text('Create your own'), findsOneWidget);
    expect(find.text('Library'), findsOneWidget);
    expect(find.text('Settings'), findsOneWidget);
  });
}

import 'fake_backend.dart';

/// Fake scene reports (F6). Owned by the play screen work (WS14).
void registerReportRoutes(FakeBackend b) {
  b.route('POST', '/v1/stories/:id/scenes/:turn/report', (r) {
    b.data.stories.get(r.param('id'), r.userId!);
    const categories = {'sexual', 'minor', 'hate', 'real_person', 'self_harm', 'other'};
    if (!categories.contains(r.json['category'])) {
      throw const FakeError.validation('Pick a category.');
    }
    b.data.reports.add({'story_id': r.param('id'), 'turn': r.param('turn'), ...r.json});
    return FakeResponse.noContent;
  });
}

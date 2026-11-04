import 'fake_backend.dart';

/// Fake scene reports (F6), as docs/API.md "Reports" describes them. Owned by the play screen work
/// (WS14). A report with `block` hides the scene for good: it comes back with `blocked: true` from
/// then on.
void registerReportRoutes(FakeBackend b) {
  b.route('POST', '/v1/stories/:id/scenes/:turn/report', (r) {
    final story = b.data.stories.get(r.param('id'), r.userId!);
    final turn = int.tryParse(r.param('turn'));
    final scene = story.scenes.where((s) => s['turn'] == turn).firstOrNull;
    if (scene == null) throw const FakeError.notFound('No such scene');
    const categories = {'sexual', 'minor', 'hate', 'real_person', 'self_harm', 'other'};
    if (!categories.contains(r.json['category'])) {
      throw const FakeError.validation('Pick a category.');
    }
    final note = r.json['note'];
    if (note != null && (note is! String || note.length > 1000)) {
      throw const FakeError.validation('A note is up to 1000 characters.');
    }
    final block = r.json['block'] == true;
    // One report per scene and player: reporting again updates it, and a block is never undone.
    final reports = b.data.reports;
    final earlier = reports.where((e) => e['story_id'] == story.id && e['turn'] == turn);
    final report = earlier.firstOrNull ?? (<String, dynamic>{'story_id': story.id, 'turn': turn});
    if (earlier.isEmpty) reports.add(report);
    report
      ..['category'] = r.json['category']
      ..['block'] = block || report['block'] == true;
    if (note != null) report['note'] = note;
    if (block) scene['blocked'] = true;
    return FakeResponse.noContent;
  });
}

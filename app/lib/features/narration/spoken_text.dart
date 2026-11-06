/// A scene's narration as it is read aloud (V9), the same way the server reads it
/// (`speech.reading.spoken_text`): no emphasis marks, one space between words and a blank line
/// between paragraphs. The app finds the server's parts in it, to read the rest of a scene in the
/// phone's voice when the studio voice can't.
String spokenText(String narration) => narration
    .replaceAll(_emphasis, '')
    .split(_paragraph)
    .map((p) => p.replaceAll(_spaces, ' ').trim())
    .where((p) => p.isNotEmpty)
    .join('\n\n');

/// [text] in pieces the phone's voice takes one at a time: paragraphs, and a paragraph longer
/// than [limit] between sentences, then between words. Android's engines refuse text over 4,000
/// characters.
List<String> phoneChunks(String text, {int limit = 2000}) {
  final chunks = <String>[];
  for (final paragraph in text.split('\n\n')) {
    if (paragraph.trim().isEmpty) continue;
    if (paragraph.length <= limit) {
      chunks.add(paragraph);
      continue;
    }
    var current = '';
    for (final piece in _sentences(paragraph).expand((s) => _words(s, limit))) {
      if (current.isNotEmpty && current.length + 1 + piece.length > limit) {
        chunks.add(current);
        current = '';
      }
      current = current.isEmpty ? piece : '$current $piece';
    }
    if (current.isNotEmpty) chunks.add(current);
  }
  return chunks;
}

final _emphasis = RegExp(r'\*+');
final _paragraph = RegExp(r'\n\s*\n');
final _spaces = RegExp(r'\s+');
final _sentenceEnd = RegExp('[.!?…]["\'”’»)\\]]*(?=\\s)');

List<String> _sentences(String paragraph) {
  final sentences = <String>[];
  var start = 0;
  for (final end in _sentenceEnd.allMatches(paragraph)) {
    sentences.add(paragraph.substring(start, end.end).trim());
    start = end.end;
  }
  sentences.add(paragraph.substring(start).trim());
  return [
    for (final s in sentences)
      if (s.isNotEmpty) s,
  ];
}

List<String> _words(String sentence, int limit) {
  if (sentence.length <= limit) return [sentence];
  final runs = <String>[];
  var current = '';
  for (final word in sentence.split(' ')) {
    if (current.isNotEmpty && current.length + 1 + word.length > limit) {
      runs.add(current);
      current = word;
    } else {
      current = current.isEmpty ? word : '$current $word';
    }
  }
  if (current.isNotEmpty) runs.add(current);
  return runs;
}

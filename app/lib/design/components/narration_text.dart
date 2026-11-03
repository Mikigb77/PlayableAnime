import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';

import '../../core/l10n.dart';
import '../motion.dart';
import '../theme.dart';
import 'skeleton.dart';

/// One run of narration with the same emphasis.
@immutable
class NarrationRun {
  const NarrationRun(
    this.text, {
    this.italic = false,
    this.bold = false,
    this.paragraphBreak = false,
  });

  final String text;
  final bool italic;
  final bool bold;

  /// A gap between paragraphs (a blank line in the source), drawn shorter than a full line.
  final bool paragraphBreak;

  @override
  bool operator ==(Object other) =>
      other is NarrationRun &&
      other.text == text &&
      other.italic == italic &&
      other.bold == bold &&
      other.paragraphBreak == paragraphBreak;

  @override
  int get hashCode => Object.hash(text, italic, bold, paragraphBreak);

  @override
  String toString() => 'NarrationRun(${italic ? 'i' : ''}${bold ? 'b' : ''}"$text")';
}

/// Parses narration into runs: `*italic*` and `**bold**`, blank lines as paragraph breaks. An
/// emphasis left open (as it is mid-stream) runs to the end of its paragraph, so streamed text
/// is already italic before the closing mark arrives.
List<NarrationRun> parseNarration(String source) {
  final runs = <NarrationRun>[];
  final buffer = StringBuffer();
  var italic = false;
  var bold = false;

  void flush() {
    if (buffer.isEmpty) return;
    runs.add(NarrationRun(buffer.toString(), italic: italic, bold: bold));
    buffer.clear();
  }

  final text = source.replaceAll('\r\n', '\n');
  for (var i = 0; i < text.length; i++) {
    final c = text[i];
    if (c == '*') {
      flush();
      if (i + 1 < text.length && text[i + 1] == '*') {
        bold = !bold;
        i++;
      } else {
        italic = !italic;
      }
      continue;
    }
    if (c == '\n') {
      // A blank line (two or more line ends, spaces between them allowed) starts a paragraph.
      var j = i;
      var newlines = 1;
      while (j + 1 < text.length && (text[j + 1] == '\n' || text[j + 1] == ' ')) {
        j++;
        if (text[j] == '\n') newlines++;
      }
      flush();
      italic = false;
      bold = false;
      runs.add(NarrationRun('\n', paragraphBreak: newlines >= 2));
      i = j;
      continue;
    }
    buffer.write(c);
  }
  flush();
  return runs;
}

int _displayLength(List<NarrationRun> runs) => runs.fold(0, (n, r) => n + r.text.length);

List<InlineSpan> _spans(
  List<NarrationRun> runs,
  TextStyle base, {
  int settled = 1 << 30,
  List<(int start, double opacity)> fades = const [],
}) {
  final spans = <InlineSpan>[];
  var offset = 0;
  final color = base.color ?? const Color(0xFF000000);

  // The opacity of the character at [index].
  double opacityAt(int index) {
    if (index < settled) return 1;
    var opacity = 1.0;
    for (final (start, value) in fades) {
      if (index >= start) opacity = value;
    }
    return opacity;
  }

  // Cut points: where a fade starts.
  final cuts = {settled, for (final (start, _) in fades) start};

  for (final run in runs) {
    if (run.paragraphBreak) {
      // End the line, then a short empty line as the paragraph gap.
      spans
        ..add(TextSpan(text: '\n', style: base))
        ..add(TextSpan(text: '​\n', style: base.copyWith(fontSize: 9, height: 1)));
      offset += run.text.length;
      continue;
    }
    final style = base.copyWith(
      fontStyle: run.italic ? FontStyle.italic : null,
      fontWeight: run.bold ? FontWeight.w600 : null,
    );
    var start = 0;
    final points = [
      for (final cut in cuts)
        if (cut > offset && cut < offset + run.text.length) cut - offset,
    ]..sort();
    for (final point in [...points, run.text.length]) {
      final piece = run.text.substring(start, point);
      if (piece.isNotEmpty) {
        final opacity = opacityAt(offset + start);
        spans.add(
          TextSpan(
            text: piece,
            style: opacity >= 1
                ? style
                : style.copyWith(color: color.withValues(alpha: color.a * opacity)),
          ),
        );
      }
      start = point;
    }
    offset += run.text.length;
  }
  return spans;
}

/// Finished narration in the reading serif.
class NarrationText extends StatelessWidget {
  const NarrationText(this.text, {super.key, this.style});

  final String text;
  final TextStyle? style;

  @override
  Widget build(BuildContext context) {
    final base = style ?? context.lucidText.narration;
    return Text.rich(TextSpan(children: _spans(parseNarration(text), base)));
  }
}

/// Narration as it streams in (S3): new words fade in calmly, a soft caret breathes at the end
/// while the turn is being written, and before the first words arrive a few skeleton lines show
/// that the story is being written. With reduce-motion on, words simply appear.
class StreamingNarration extends StatefulWidget {
  const StreamingNarration({super.key, required this.text, required this.streaming, this.style});

  /// Everything received so far. When it gets shorter or changes (a `narration.reset`), the
  /// reveal starts over without animation.
  final String text;
  final bool streaming;
  final TextStyle? style;

  @override
  State<StreamingNarration> createState() => _StreamingNarrationState();
}

class _StreamingNarrationState extends State<StreamingNarration>
    with SingleTickerProviderStateMixin {
  // Made on the first arrival, so a narration that never grows (or a skeleton) never builds one,
  // and dispose never has to create it from a deactivated context.
  Ticker? _ticker;
  late List<NarrationRun> _runs = parseNarration(widget.text);
  late int _length = _displayLength(_runs);
  late int _settled = _length;
  final _arrivals = <(int start, Duration at)>[];
  Duration _now = Duration.zero;

  @override
  void didUpdateWidget(StreamingNarration old) {
    super.didUpdateWidget(old);
    if (old.text == widget.text) return;
    final runs = parseNarration(widget.text);
    final length = _displayLength(runs);
    final grew = widget.text.startsWith(old.text) && length > _length;
    if (!grew || Motion.reduced(context)) {
      _arrivals.clear();
      _settled = length;
    } else {
      final ticker = _ticker ??= createTicker(_tick);
      if (!ticker.isActive) {
        _now = Duration.zero;
        ticker.start();
      }
      _arrivals.add((_length, _now));
    }
    _runs = runs;
    _length = length;
  }

  void _tick(Duration elapsed) {
    _now = elapsed;
    while (_arrivals.isNotEmpty && elapsed - _arrivals.first.$2 >= Motion.reveal) {
      _arrivals.removeAt(0);
      _settled = _arrivals.isEmpty ? _length : _arrivals.first.$1;
    }
    if (_arrivals.isEmpty) {
      _settled = _length;
      _ticker?.stop();
    }
    setState(() {});
  }

  @override
  void dispose() {
    _ticker?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final base = widget.style ?? context.lucidText.narration;
    if (widget.text.isEmpty && widget.streaming) {
      return Semantics(
        label: context.l10n.narrationWriting,
        child: const SkeletonText(lines: 3, lineHeight: 14, spacing: 14),
      );
    }
    final reveal = Motion.reveal.inMicroseconds;
    final fades = [
      for (final (start, at) in _arrivals)
        (start, Curves.easeOut.transform(((_now - at).inMicroseconds / reveal).clamp(0.0, 1.0))),
    ];
    return Text.rich(
      TextSpan(
        children: [
          ..._spans(_runs, base, settled: _settled, fades: fades),
          if (widget.streaming)
            WidgetSpan(
              alignment: PlaceholderAlignment.middle,
              child: Padding(
                padding: const EdgeInsets.only(left: 4),
                child: _Caret(color: context.lucid.accent),
              ),
            ),
        ],
      ),
    );
  }
}

/// A small breathing dot after the newest words.
class _Caret extends StatefulWidget {
  const _Caret({required this.color});

  final Color color;

  @override
  State<_Caret> createState() => _CaretState();
}

class _CaretState extends State<_Caret> with SingleTickerProviderStateMixin {
  late final _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 900),
  );

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (Motion.reduced(context)) {
      _controller
        ..stop()
        ..value = 1;
    } else if (!_controller.isAnimating) {
      _controller.repeat(reverse: true);
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return ExcludeSemantics(
      child: FadeTransition(
        opacity: Tween(begin: 0.25, end: 1.0).animate(_controller),
        child: Container(
          width: 7,
          height: 7,
          decoration: BoxDecoration(color: widget.color, shape: BoxShape.circle),
        ),
      ),
    );
  }
}

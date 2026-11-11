import 'package:flutter/material.dart';

import '../../core/api/api_error.dart';
import '../design.dart';

/// Every component in its states, for development (`/gallery`, debug builds and the fake API).
/// Switch the theme, the genre accent and the text size at the top. Labels here are developer-facing
/// and not translated. The query `?theme=light&accent=jade&scale=2` sets the controls up front, for
/// screenshots.
class GalleryScreen extends StatefulWidget {
  const GalleryScreen({super.key, this.brightness, this.accent, this.textScale});

  /// Reads the starting controls from a route's query, ignoring values it does not know.
  factory GalleryScreen.fromQuery(Map<String, String> query) => GalleryScreen(
    brightness: switch (query['theme']) {
      'light' => Brightness.light,
      'dark' => Brightness.dark,
      _ => null,
    },
    accent: GenreAccent.values.where((a) => a.name == query['accent']).firstOrNull,
    textScale: const [
      1.0,
      1.3,
      2.0,
    ].where((v) => v == double.tryParse(query['scale'] ?? '')).firstOrNull,
  );

  final Brightness? brightness;
  final GenreAccent? accent;
  final double? textScale;

  @override
  State<GalleryScreen> createState() => _GalleryScreenState();
}

class _GalleryScreenState extends State<GalleryScreen> {
  late Brightness _brightness = widget.brightness ?? Theme.of(context).brightness;
  late GenreAccent _accent = widget.accent ?? GenreAccent.lucid;
  late double _textScale = widget.textScale ?? 1;
  bool _streaming = false;
  int _tab = 0;
  String _streamed = _sampleNarration;
  final _composer = TextEditingController();

  @override
  void dispose() {
    _composer.dispose();
    super.dispose();
  }

  Future<void> _replayStream() async {
    setState(() {
      _streaming = true;
      _streamed = '';
    });
    final words = RegExp(r'\S+\s*').allMatches(_sampleNarration).map((m) => m.group(0)!).toList();
    for (final word in words) {
      await Future<void>.delayed(const Duration(milliseconds: 45));
      if (!mounted) return;
      setState(() => _streamed += word);
    }
    if (mounted) setState(() => _streaming = false);
  }

  @override
  Widget build(BuildContext context) {
    return Theme(
      data: AppTheme.build(_brightness, _accent),
      child: MediaQuery(
        data: MediaQuery.of(context).copyWith(textScaler: TextScaler.linear(_textScale)),
        child: Builder(builder: _page),
      ),
    );
  }

  Widget _page(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('Widget gallery')),
      body: ListView(
        padding: const EdgeInsets.only(bottom: Space.xxxl),
        children: [
          ContentColumn(child: _controls(context)),
          _section(context, 'Colors and type', _swatches(context)),
          _section(context, 'Gold, glass and night air', _look(context)),
          _section(
            context,
            'Scene card',
            SceneCard(
              playerAction: 'I answer the voice, quietly. Who are you?',
              spokenAction: true,
              time: const TimeChip(duration: '+2 min', label: 'Day 1, dawn'),
              event: const EventBadge(
                size: EventSize.local,
                title: 'The library alarm wakes the sect',
              ),
              picture: const PictureSlot(
                status: PictureStatus.ready,
                url: 'asset:assets/fake/scene-peaks.jpg',
                borderRadius: BorderRadius.zero,
              ),
              narration: const NarrationText(_sampleNarration),
              portraits: const PortraitStack(
                portraits: [
                  PortraitRef(name: 'The voice', url: 'asset:assets/fake/portrait-2.jpg'),
                  PortraitRef(name: 'Old Gu', url: 'asset:assets/fake/portrait-3.jpg'),
                  PortraitRef(name: 'Senior Sister Lan'),
                  PortraitRef(name: 'Elder Wen'),
                ],
              ),
              onDetails: () {},
              onMore: () {},
              ornament: false,
            ),
            padded: false,
          ),
          _section(
            context,
            'Streaming narration',
            Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                StreamingNarration(text: _streamed, streaming: _streaming),
                const SizedBox(height: Space.lg),
                Align(
                  alignment: Alignment.centerLeft,
                  child: OutlinedButton.icon(
                    onPressed: _streaming ? null : _replayStream,
                    icon: const Icon(Icons.replay_rounded),
                    label: const Text('Replay the stream'),
                  ),
                ),
                const SizedBox(height: Space.lg),
                Text('Before the first words:', style: theme.textTheme.bodySmall),
                const SizedBox(height: Space.sm),
                const StreamingNarration(text: '', streaming: true),
              ],
            ),
          ),
          _section(
            context,
            'Choices and standing actions',
            StoryChoices(
              choices: const [
                StoryChoice(id: '1', label: 'Take the scroll and run for the window'),
                StoryChoice(id: '2', label: 'Greet Old Gu and lie', kind: ChoiceKind.personal),
                StoryChoice(
                  id: '3',
                  label: 'Visit the herbalist in the lower town',
                  kind: ChoiceKind.side,
                ),
                StoryChoice(
                  id: '4',
                  label: 'Ask the voice to prove it, right now',
                  kind: ChoiceKind.wild,
                ),
              ],
              onChoice: (_) {},
              onStanding: (_) {},
            ),
          ),
          _section(
            context,
            'Composer, mic and slash hints',
            Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: Space.gutter),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Wrap(
                        spacing: Space.lg,
                        children: [
                          MicButton(visual: MicVisual.idle, onPressed: _noop),
                          MicButton(visual: MicVisual.starting, onPressed: _noop),
                          MicButton(visual: MicVisual.listening, onPressed: _noop, level: 0.7),
                          MicButton(visual: MicVisual.denied, onPressed: _noop),
                          MicButton(visual: MicVisual.transcribing, onPressed: _noop),
                        ],
                      ),
                      const SizedBox(height: Space.lg),
                      Text(
                        'Idle, starting, listening and denied. Type / in the composer for the hints.',
                        style: theme.textTheme.bodySmall,
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: Space.sm),
                Composer(
                  controller: _composer,
                  onSubmit: (_) => _composer.clear(),
                  mic: const MicButton(visual: MicVisual.idle, onPressed: _noop),
                  commands: const [
                    SlashCommand('status', 'Your sheet, reputation and the date'),
                    SlashCommand('ooc', 'Talk to the narrator'),
                    SlashCommand('recap', 'The story so far'),
                    SlashCommand(
                      'thoughts',
                      'What a character lets show',
                      argumentHint: '<character>',
                    ),
                  ],
                ),
              ],
            ),
            padded: false,
          ),
          _section(
            context,
            'Pictures',
            const Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                PictureSlot(status: PictureStatus.pending),
                SizedBox(height: Space.lg),
                PictureSlot(status: PictureStatus.ready, url: 'asset:assets/fake/scene-castle.jpg'),
                SizedBox(height: Space.sm),
                Text('A skipped picture collapses quietly to nothing:'),
                PictureSlot(status: PictureStatus.skipped),
              ],
            ),
          ),
          _section(
            context,
            'Portraits, time and events',
            const Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Wrap(
                  spacing: Space.md,
                  runSpacing: Space.md,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    PortraitAvatar(
                      name: 'Shen Yu',
                      url: 'asset:assets/fake/portrait-3.jpg',
                      size: 56,
                      ring: true,
                    ),
                    PortraitAvatar(name: 'Senior Sister Lan', size: 56),
                    PortraitAvatar(
                      name: 'The voice',
                      url: 'asset:assets/fake/portrait-2.jpg',
                      size: 40,
                    ),
                  ],
                ),
                SizedBox(height: Space.lg),
                Wrap(
                  spacing: Space.sm,
                  runSpacing: Space.sm,
                  children: [
                    TimeChip(duration: '+8 h', label: 'Day 3, dusk'),
                    TimeChip(duration: '+40 s', personalLabel: 'World: +0 s. You: +40 s.'),
                  ],
                ),
                SizedBox(height: Space.xl),
                PassageHeading('Three days later'),
                SizedBox(height: Space.xl),
                EventBadge(size: EventSize.personal, title: 'A letter with your mother\'s seal'),
                SizedBox(height: Space.sm),
                EventBadge(size: EventSize.local, title: 'Fire in the lower market'),
                SizedBox(height: Space.sm),
                EventBadge(size: EventSize.world, title: 'The Emperor is dead'),
              ],
            ),
          ),
          _section(
            context,
            'Cards',
            Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                CoverCard(
                  title: 'The Ninth Peak',
                  genre: 'Cultivation',
                  subtitle:
                      'Crippled meridians. A forbidden library. A voice that knows your name.',
                  imageUrl: 'asset:assets/fake/scene-peaks.jpg',
                  badge: 'Signature',
                  onTap: () {},
                ),
                const SizedBox(height: Space.lg),
                CoverCard(
                  title: 'Ninefold Drift',
                  genre: 'Science fiction',
                  subtitle: 'No cover yet.',
                  onTap: () {},
                ),
                const SizedBox(height: Space.lg),
                StoryTile(
                  title: 'Naples, 1974',
                  genre: 'Grounded modern',
                  meta: 'Turn 12 · Day 3, dusk',
                  imageUrl: 'asset:assets/fake/scene-city.jpg',
                  onTap: () {},
                ),
              ],
            ),
          ),
          _section(
            context,
            'Sheets',
            Align(
              alignment: Alignment.centerLeft,
              child: FilledButton.tonal(
                onPressed: () => showAppSheet<void>(
                  context: context,
                  title: 'How it played out',
                  builder: (context) => const Text(
                    'Reach the window before the wards wake: contested. The wards answer anyone who '
                    'carries a sealed text past the threshold. Rolled about even: failure.',
                  ),
                ),
                child: const Text('Open a sheet'),
              ),
            ),
          ),
          _section(
            context,
            'Loading, empty and error states',
            Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const SkeletonCard(),
                const SizedBox(height: Space.xl),
                const SkeletonText(),
                SizedBox(
                  height: 300,
                  child: EmptyState(
                    icon: Icons.auto_stories_outlined,
                    title: 'No stories yet',
                    message: 'Pick a world in Discover, or start from your own idea.',
                    actionLabel: 'Discover worlds',
                    onAction: () {},
                  ),
                ),
                SizedBox(
                  height: 300,
                  child: ErrorState(
                    error: const ApiException(ApiErrorCode.network),
                    onRetry: () {},
                  ),
                ),
                SizedBox(
                  height: 300,
                  child: ErrorState(
                    error: const ApiException(ApiErrorCode.llmUnavailable),
                    onRetry: () {},
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _controls(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(Space.gutter),
      child: Wrap(
        spacing: Space.md,
        runSpacing: Space.md,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          SegmentedButton<Brightness>(
            segments: const [
              ButtonSegment(value: Brightness.dark, label: Text('Dark')),
              ButtonSegment(value: Brightness.light, label: Text('Light')),
            ],
            selected: {_brightness},
            showSelectedIcon: false,
            onSelectionChanged: (s) => setState(() => _brightness = s.single),
          ),
          DropdownMenu<GenreAccent>(
            initialSelection: _accent,
            label: const Text('Accent'),
            dropdownMenuEntries: [
              for (final a in GenreAccent.values) DropdownMenuEntry(value: a, label: a.name),
            ],
            onSelected: (a) => setState(() => _accent = a ?? GenreAccent.lucid),
          ),
          SegmentedButton<double>(
            segments: const [
              ButtonSegment(value: 1, label: Text('1×')),
              ButtonSegment(value: 1.3, label: Text('1.3×')),
              ButtonSegment(value: 2, label: Text('2×')),
            ],
            selected: {_textScale},
            showSelectedIcon: false,
            onSelectionChanged: (s) => setState(() => _textScale = s.single),
          ),
        ],
      ),
    );
  }

  Widget _swatches(BuildContext context) {
    final theme = Theme.of(context);
    final colors = context.lucid;
    final swatches = [
      ('Background', colors.background),
      ('Surface', theme.colorScheme.surface),
      ('Container', theme.colorScheme.surfaceContainer),
      ('Highest', theme.colorScheme.surfaceContainerHighest),
      ('Accent', colors.accent),
      ('Accent soft', colors.accentSoft),
      ('Success', colors.success),
      ('Caution', colors.caution),
      ('Danger', colors.danger),
    ];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Wrap(
          spacing: Space.sm,
          runSpacing: Space.sm,
          children: [
            for (final (name, color) in swatches)
              Container(
                constraints: const BoxConstraints(minWidth: 96, minHeight: 56),
                padding: const EdgeInsets.all(Space.sm),
                decoration: BoxDecoration(
                  color: color,
                  borderRadius: BorderRadius.circular(Radii.sm),
                  border: Border.all(color: theme.colorScheme.outlineVariant),
                ),
                // Grows with large text, and otherwise stays a small tile.
                child: Align(
                  alignment: Alignment.bottomLeft,
                  widthFactor: 1,
                  heightFactor: 1,
                  child: Text(
                    name,
                    style: theme.textTheme.labelSmall!.copyWith(color: onColor(color)),
                  ),
                ),
              ),
          ],
        ),
        const SizedBox(height: Space.xl),
        Text('Display serif', style: theme.textTheme.displaySmall),
        Text('Headline in the display serif', style: theme.textTheme.headlineSmall),
        Text('Title in Inter', style: theme.textTheme.titleLarge),
        Text('Body text in Inter, for the interface.', style: theme.textTheme.bodyLarge),
        Text('CULTIVATION', style: context.lucidText.overline),
        const SizedBox(height: Space.sm),
        const NarrationText('Narration in Literata, *with emphasis*.'),
        Text('+8 h · Day 3, dusk', style: context.lucidText.meta),
      ],
    );
  }

  /// The pieces the look is made of: gradient lettering, the app's mark, glass over the night
  /// air, the tab bar, the pills and the bead, and a paragraph with its drop capital.
  Widget _look(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const BrandMark(),
        const SizedBox(height: Space.lg),
        Text('Pick a world, or', style: theme.textTheme.displaySmall),
        GradientText('dream up your own.', style: theme.textTheme.displaySmall!, balanced: true),
        const SizedBox(height: Space.lg),
        const Eyebrow('An eyebrow'),
        const SizedBox(height: Space.lg),
        ClipRRect(
          borderRadius: Radii.card,
          child: SizedBox(
            height: 200,
            child: Stack(
              children: [
                const Positioned.fill(child: Ambient()),
                Align(
                  alignment: Alignment.bottomCenter,
                  child: LucidTabBar(
                    tabs: const [
                      LucidTab(
                        icon: Icons.explore_outlined,
                        selectedIcon: Icons.explore,
                        label: 'Discover',
                      ),
                      LucidTab(
                        icon: Icons.auto_stories_outlined,
                        selectedIcon: Icons.auto_stories,
                        label: 'Library',
                      ),
                      LucidTab(
                        icon: Icons.person_outline_rounded,
                        selectedIcon: Icons.person_rounded,
                        label: 'Account',
                      ),
                    ],
                    selected: _tab,
                    onSelected: (i) => setState(() => _tab = i),
                  ),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: Space.lg),
        Wrap(
          spacing: Space.md,
          runSpacing: Space.sm,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            GhostPill(icon: Icons.insights_rounded, label: 'How it played out', onPressed: () {}),
            GhostPill(
              large: true,
              icon: Icons.visibility_outlined,
              label: 'Observe',
              onPressed: () {},
            ),
            AccentOrb(icon: Icons.arrow_upward_rounded, tooltip: 'Send', onPressed: () {}),
            const AccentOrb(icon: Icons.arrow_upward_rounded, tooltip: 'Send', lit: false),
          ],
        ),
        const SizedBox(height: Space.lg),
        const StarRule(),
        const SizedBox(height: Space.lg),
        const NarrationText(_sampleNarration, dropCap: true),
      ],
    );
  }

  Widget _section(BuildContext context, String title, Widget child, {bool padded = true}) {
    return ContentColumn.reading(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SectionLabel(
            title,
            padding: const EdgeInsets.fromLTRB(Space.gutter, Space.xxl, Space.gutter, Space.lg),
          ),
          if (padded)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: Space.gutter),
              child: child,
            )
          else
            child,
        ],
      ),
    );
  }
}

void _noop() {}

const _sampleNarration =
    'Your own voice sounds small in the stacks. For a long moment nothing answers but the lamps.\n\n'
    'Then the scroll unrolls itself a hand\'s width, and the voice comes again, closer, dry as old '
    'paper. *Someone who also had a door closed on them,* it says. *Your meridians are not '
    'shattered, child. They were cut. Carefully.*';

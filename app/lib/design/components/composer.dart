import 'package:flutter/material.dart';

import '../../core/l10n.dart';
import '../motion.dart';
import '../theme.dart';
import '../tokens.dart';

/// A slash command the composer can hint at, such as `/status` (S5).
@immutable
class SlashCommand {
  const SlashCommand(this.name, this.description, {this.argumentHint});

  /// Without the slash: `status`.
  final String name;
  final String description;

  /// Shown after the name, such as `<character>` for `/thoughts`.
  final String? argumentHint;

  String get command => '/$name';
}

/// Where the player writes what they do: a growing text box, a slot for the dictation button
/// (V1), and send. Typing `/` lists the slash commands that match.
///
/// The composer never sends on its own: dictated words land in [controller] and wait for the
/// player (V2).
class Composer extends StatefulWidget {
  const Composer({
    super.key,
    required this.controller,
    required this.onSubmit,
    this.focusNode,
    this.enabled = true,
    this.busy = false,
    this.hintText,
    this.commands = const [],
    this.mic,
    this.maxLength = 2000,
  });

  final TextEditingController controller;

  /// Called with the trimmed text when the player sends.
  final ValueChanged<String> onSubmit;
  final FocusNode? focusNode;
  final bool enabled;

  /// A turn is running: sending waits.
  final bool busy;
  final String? hintText;
  final List<SlashCommand> commands;

  /// The dictation button, from features/voice.
  final Widget? mic;

  /// The API's limit on an action (docs/API.md: 1 to 2000 characters).
  final int maxLength;

  @override
  State<Composer> createState() => _ComposerState();
}

class _ComposerState extends State<Composer> {
  @override
  void initState() {
    super.initState();
    widget.controller.addListener(_changed);
  }

  @override
  void didUpdateWidget(Composer old) {
    super.didUpdateWidget(old);
    if (old.controller != widget.controller) {
      old.controller.removeListener(_changed);
      widget.controller.addListener(_changed);
    }
  }

  @override
  void dispose() {
    widget.controller.removeListener(_changed);
    super.dispose();
  }

  void _changed() => setState(() {});

  String get _text => widget.controller.text.trim();

  bool get _canSend =>
      widget.enabled && !widget.busy && _text.isNotEmpty && _text.length <= widget.maxLength;

  List<SlashCommand> get _matches {
    final text = widget.controller.text;
    if (!text.startsWith('/') || text.contains(RegExp(r'\s'))) return const [];
    final typed = text.substring(1).toLowerCase();
    return [
      for (final c in widget.commands)
        if (c.name.startsWith(typed)) c,
    ];
  }

  void _submit() {
    if (!_canSend) return;
    widget.onSubmit(_text);
  }

  void _pick(SlashCommand command) {
    // The trailing space closes the hints; sending trims it.
    final text = '${command.command} ';
    widget.controller.value = TextEditingValue(
      text: text,
      selection: TextSelection.collapsed(offset: text.length),
    );
    widget.focusNode?.requestFocus();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = context.lucid;
    final l10n = context.l10n;
    final matches = _matches;
    final length = widget.controller.text.length;
    final nearLimit = length > widget.maxLength * 0.9;
    const none = InputBorder.none;

    return Material(
      color: theme.colorScheme.surface,
      child: DecoratedBox(
        decoration: BoxDecoration(
          border: Border(top: BorderSide(color: theme.colorScheme.outlineVariant)),
        ),
        child: SafeArea(
          top: false,
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: Layout.readingWidth + 2 * Space.md),
              child: Padding(
                padding: const EdgeInsets.fromLTRB(Space.md, Space.sm, Space.md, Space.sm),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    AnimatedSize(
                      duration: Motion.of(context, Motion.fast),
                      curve: Motion.standard,
                      alignment: Alignment.bottomCenter,
                      child: matches.isEmpty
                          ? const SizedBox(width: double.infinity)
                          : _SlashHints(commands: matches, onPick: _pick),
                    ),
                    Container(
                      decoration: BoxDecoration(
                        color: theme.colorScheme.surfaceContainer,
                        borderRadius: BorderRadius.circular(Radii.xl),
                        border: Border.all(color: theme.colorScheme.outlineVariant),
                      ),
                      padding: const EdgeInsets.only(left: Space.lg, right: Space.xs),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.end,
                        children: [
                          Expanded(
                            child: Padding(
                              padding: const EdgeInsets.symmetric(vertical: 2),
                              child: TextField(
                                controller: widget.controller,
                                focusNode: widget.focusNode,
                                enabled: widget.enabled,
                                minLines: 1,
                                maxLines: 5,
                                textCapitalization: TextCapitalization.sentences,
                                textInputAction: TextInputAction.send,
                                onSubmitted: (_) => _submit(),
                                style: theme.textTheme.bodyLarge,
                                decoration: InputDecoration(
                                  hintText: widget.hintText ?? l10n.composerHint,
                                  filled: false,
                                  isDense: true,
                                  border: none,
                                  enabledBorder: none,
                                  focusedBorder: none,
                                  disabledBorder: none,
                                  contentPadding: const EdgeInsets.symmetric(vertical: 12),
                                ),
                              ),
                            ),
                          ),
                          ?widget.mic,
                          Padding(
                            padding: const EdgeInsets.only(bottom: 4, top: 4),
                            child: _SendButton(
                              enabled: _canSend,
                              busy: widget.busy,
                              onPressed: _submit,
                            ),
                          ),
                        ],
                      ),
                    ),
                    if (nearLimit)
                      Padding(
                        padding: const EdgeInsets.only(top: Space.xs, right: Space.sm),
                        child: Text(
                          l10n.composerCount(length, widget.maxLength),
                          textAlign: TextAlign.end,
                          style: context.lucidText.meta.copyWith(
                            color: length > widget.maxLength
                                ? theme.colorScheme.error
                                : colors.textMuted,
                          ),
                        ),
                      ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _SendButton extends StatelessWidget {
  const _SendButton({required this.enabled, required this.busy, required this.onPressed});

  final bool enabled;
  final bool busy;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final colors = context.lucid;
    final l10n = context.l10n;
    if (busy) {
      return SizedBox.square(
        dimension: 40,
        child: Padding(
          padding: const EdgeInsets.all(11),
          child: CircularProgressIndicator(strokeWidth: 2, color: colors.accent),
        ),
      );
    }
    return IconButton.filled(
      tooltip: l10n.composerSend,
      onPressed: enabled ? onPressed : null,
      style: IconButton.styleFrom(
        backgroundColor: colors.accent,
        foregroundColor: colors.onAccent,
        disabledBackgroundColor: Theme.of(context).colorScheme.surfaceContainerHighest,
        disabledForegroundColor: colors.textMuted,
        minimumSize: const Size.square(40),
        fixedSize: const Size.square(40),
      ),
      icon: const Icon(Icons.arrow_upward_rounded, size: 22),
    );
  }
}

class _SlashHints extends StatelessWidget {
  const _SlashHints({required this.commands, required this.onPick});

  final List<SlashCommand> commands;
  final ValueChanged<SlashCommand> onPick;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = context.lucid;
    return Padding(
      padding: const EdgeInsets.only(bottom: Space.sm),
      child: Material(
        color: theme.colorScheme.surfaceContainerHigh,
        borderRadius: BorderRadius.circular(Radii.lg),
        clipBehavior: Clip.antiAlias,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(Space.lg, Space.md, Space.lg, Space.xs),
              child: Text(
                context.l10n.composerCommands.toUpperCase(),
                style: context.lucidText.overline.copyWith(color: colors.textMuted),
              ),
            ),
            for (final command in commands)
              InkWell(
                onTap: () => onPick(command),
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: Space.lg, vertical: 10),
                  child: Row(
                    children: [
                      Text.rich(
                        TextSpan(
                          children: [
                            TextSpan(
                              text: command.command,
                              style: TextStyle(color: colors.accent),
                            ),
                            if (command.argumentHint case final hint?)
                              TextSpan(
                                text: ' $hint',
                                style: TextStyle(color: colors.textMuted),
                              ),
                          ],
                        ),
                        style: theme.textTheme.labelLarge,
                      ),
                      const SizedBox(width: Space.md),
                      Expanded(
                        child: Text(
                          command.description,
                          style: theme.textTheme.bodyMedium!.copyWith(color: colors.textSecondary),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            const SizedBox(height: Space.xs),
          ],
        ),
      ),
    );
  }
}

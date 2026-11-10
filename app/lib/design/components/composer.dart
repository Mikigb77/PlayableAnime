import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../../core/l10n.dart';
import '../motion.dart';
import '../theme.dart';
import '../tokens.dart';
import 'glass.dart';
import 'pills.dart';

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

/// Where the player writes what they do: a pill of glass that holds a growing text box, a slot
/// for the dictation button (V1), and send, a bead that lights up in the accent once there is
/// something to send. The pill's edge takes the accent while the player writes. Typing `/` lists
/// the slash commands that match.
///
/// The composer never sends on its own: dictated words land in [controller] and wait for the
/// player (V2). Nor does it send while the mic is on or its words are on their way ([dictating]):
/// send then turns the mic off, waits for the words to land after what was typed, and sends the
/// whole box, as Claude's app does (Miki, 2026-11-07).
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
    this.dictating,
    this.onFinishDictation,
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

  /// Whether [mic] is on, or what it heard is still on its way to the box. Send stays open then,
  /// even with nothing in the box yet.
  final ValueListenable<bool>? dictating;

  /// Turns [mic] off and waits until what it heard is in the box. Sending while [dictating] calls
  /// it first, then sends the box as it is by then, even if the owner showed [busy] while it
  /// waited; false (the words couldn't be written down, or the owner won't send now) sends
  /// nothing, leaving the box to the player.
  final Future<bool> Function()? onFinishDictation;

  /// The API's limit on an action (docs/API.md: 1 to 2000 characters).
  final int maxLength;

  @override
  State<Composer> createState() => _ComposerState();
}

class _ComposerState extends State<Composer> {
  /// Send was tapped while the mic was on: the words are on their way, and then the box goes.
  bool _finishing = false;

  /// The box's focus when the owner passes none, so the pill can light its edge.
  FocusNode? _ownFocus;

  FocusNode get _focus => widget.focusNode ?? (_ownFocus ??= FocusNode());

  @override
  void initState() {
    super.initState();
    widget.controller.addListener(_changed);
    widget.dictating?.addListener(_changed);
    _focus.addListener(_changed);
  }

  @override
  void didUpdateWidget(Composer old) {
    super.didUpdateWidget(old);
    if (old.controller != widget.controller) {
      old.controller.removeListener(_changed);
      widget.controller.addListener(_changed);
    }
    if (old.dictating != widget.dictating) {
      old.dictating?.removeListener(_changed);
      widget.dictating?.addListener(_changed);
    }
    if (old.focusNode != widget.focusNode) {
      (old.focusNode ?? _ownFocus)?.removeListener(_changed);
      _focus.addListener(_changed);
    }
  }

  @override
  void dispose() {
    widget.controller.removeListener(_changed);
    widget.dictating?.removeListener(_changed);
    _focus.removeListener(_changed);
    _ownFocus?.dispose();
    super.dispose();
  }

  void _changed() => setState(() {});

  String get _text => widget.controller.text.trim();

  bool get _dictating => widget.dictating?.value ?? false;

  bool get _open => widget.enabled && !widget.busy && !_finishing;

  bool get _fits => _text.length <= widget.maxLength;

  bool get _sendable => _text.isNotEmpty && _fits;

  /// With the mic on, send is open even with an empty box: the words are on their way.
  bool get _canSend => _open && (_sendable || (_dictating && _fits));

  List<SlashCommand> get _matches {
    final text = widget.controller.text;
    if (!text.startsWith('/') || text.contains(RegExp(r'\s'))) return const [];
    final typed = text.substring(1).toLowerCase();
    return [
      for (final c in widget.commands)
        if (c.name.startsWith(typed)) c,
    ];
  }

  Future<void> _submit() async {
    if (!_canSend) return;
    if (_dictating) {
      setState(() => _finishing = true);
      var landed = false;
      try {
        landed = await (widget.onFinishDictation?.call() ?? Future.value(true));
      } finally {
        if (mounted) setState(() => _finishing = false);
      }
      if (!mounted || !landed || !widget.enabled || !_sendable) return;
    }
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
    final focused = _focus.hasFocus && widget.enabled;
    const none = InputBorder.none;

    return Material(
      color: theme.scaffoldBackgroundColor,
      child: SafeArea(
        top: false,
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: Layout.readingWidth + 2 * Layout.barInset),
            child: Padding(
              padding: const EdgeInsets.fromLTRB(
                Layout.barInset,
                Space.xs,
                Layout.barInset,
                Space.md,
              ),
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
                  Glass(
                    // Nothing lies behind the pill to see through it.
                    blur: 0,
                    borderRadius: const BorderRadius.all(Radius.circular(30)),
                    borderColor: focused ? colors.accent.withValues(alpha: 0.5) : null,
                    glow: focused ? colors.accent.withValues(alpha: 0.14) : null,
                    padding: const EdgeInsetsDirectional.only(start: 22, end: 5),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.end,
                      children: [
                        Expanded(
                          child: Padding(
                            padding: const EdgeInsets.symmetric(vertical: 5),
                            child: TextField(
                              controller: widget.controller,
                              focusNode: _focus,
                              enabled: widget.enabled,
                              minLines: 1,
                              maxLines: 5,
                              textCapitalization: TextCapitalization.sentences,
                              textInputAction: TextInputAction.send,
                              onSubmitted: (_) => unawaited(_submit()),
                              style: theme.textTheme.bodyLarge,
                              cursorColor: colors.accent,
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
                          padding: const EdgeInsets.symmetric(vertical: 5),
                          child: _SendButton(
                            enabled: _canSend,
                            busy: widget.busy || _finishing,
                            onPressed: () => unawaited(_submit()),
                          ),
                        ),
                      ],
                    ),
                  ),
                  if (nearLimit)
                    Padding(
                      padding: const EdgeInsets.only(top: Space.xs, right: Space.lg),
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
    );
  }
}

/// Send: a bead that lights up in the accent once there is something to send, and a quiet
/// spinner while a turn runs.
class _SendButton extends StatelessWidget {
  const _SendButton({required this.enabled, required this.busy, required this.onPressed});

  final bool enabled;
  final bool busy;
  final VoidCallback onPressed;

  static const _size = 42.0;

  @override
  Widget build(BuildContext context) {
    if (busy) {
      return SizedBox.square(
        dimension: Layout.minTouch,
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: CircularProgressIndicator(strokeWidth: 2, color: context.lucid.accent),
        ),
      );
    }
    return AccentOrb(
      icon: Icons.arrow_upward_rounded,
      size: _size,
      lit: enabled,
      tooltip: context.l10n.composerSend,
      onPressed: enabled ? onPressed : null,
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
        shape: RoundedRectangleBorder(
          borderRadius: Radii.card,
          side: BorderSide(color: colors.hairline),
        ),
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

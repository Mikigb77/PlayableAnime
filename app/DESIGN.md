# Lucid Saga design

The look and feel of the app, and the rules every screen follows. The code lives in `lib/design/`
and every component is on show in the widget gallery (`/gallery`). Requirements are cited by id
from [`docs/REQUIREMENTS.md`](../docs/REQUIREMENTS.md).

![Welcome, Discover, a story's title page and a scene with its choices](docs/screenshots/overview.jpg)

## Direction: a reading room at night

The story is the interface. A scene should feel like a page from a well-set novel with one
painting beside it, not like a chat log or a game HUD.

- **Dark first.** The default theme is *ink*: deep blue-black layers and warm parchment text, so a
  long session at night is easy on the eyes and pictures glow. *Paper* is the light theme, a warm
  off-white with ink text. The player picks dark, light or system in Account.
- **Words in a serif, the interface in a sans.** Narration is set in Literata at reading size;
  buttons, chips and lists are in Inter. Headlines use Literata's display cut.
- **One accent at a time.** Outside a story the accent is *lucid gold*. Inside a story the accent
  follows its genre (see below), so each world has its own tint without any genre-specific layout
  (G5), unless the player picked another color for the story (S13).
- **The same look as the website** (S14; Miki, 2026-11-10: the app should feel as finished as
  the site). Four things carry it, each one component: **gold lettering**, the accent as a gradient
  from bright to deep, for the line of a headline that matters, a story's title and the capital
  that opens it (`GradientText`); **glass**, for whatever floats over the page, the tabs and a
  story's bar (`Glass`); **night air**, a glow that breathes and a few fireflies behind the top of
  a page (`Ambient`); and **the forest gate** from the icon, as the welcome screen's picture and
  the small round mark beside the app's name (`BrandMark`).
- **Chrome recedes.** Hairlines instead of borders, soft layers instead of shadows, generous space,
  and one bright thing on a screen: the filled button, the send button once there are words to
  send, the way into the story to continue.
- **Pictures are events.** They arrive at key moments (M1), edge to edge on a phone, faded into the
  page with a vignette. They never block the text (M3).

## Color

Widgets read colors from the theme (`Theme.of(context).colorScheme` and `context.lucid`), never from
`Palette` directly, so both themes and every accent work.

| Token | Ink (dark) | Paper (light) | Use |
| --- | --- | --- | --- |
| background | `#0B0D12` | `#F6F3ED` | Page behind everything |
| surface | `#11141B` | `#FBF9F5` | Bars, sheets |
| container low to highest | `#151922` to `#29303D` | `#F1EDE5` to `#DED7CA` | Cards, fields, chips, in rising layers |
| textPrimary | `#EDE8DF` | `#1B1D23` | Narration, titles |
| textSecondary | `#B4B8C3` | `#474B56` | Supporting lines |
| textMuted | `#9399A6` | `#545965` | Meta, hints |
| error | `#F4878A` | `#B3261E` | Errors only |

**Contrast is tested, not hoped for.** Every text color, the accent and the error color reach WCAG
AA (4.5:1) on every surface in both themes and for every accent (`test/design/contrast_test.dart`).
Accents pass through `ensureContrast`, which moves lightness and keeps the hue.

The look adds a few tokens to `context.lucid`, each made from the ones above so both themes and
every accent have them:

| Token | What it is |
| --- | --- |
| `accentHi`, `accentLo` | The bright and the deep end of the accent's gradient (`accentEnds`), with the accent between them (`accentGradient()`). Both read as text on the page and on a card, and `onAccent` reads on both: tested |
| `glass`, `glassBorder`, `glassShadow` | A floating bar's see-through fill, its hairline edge and the shadow it casts |
| `hairline` | The quietest edge: around a chip, a tile or a card that sits on the page |
| `veil` | A faint wash of the text color, for a chip's fill |

### Genre accents

`GenreAccent.forGenre` maps the story's genre label to an accent family. The table is the only place
genre touches the interface.

| Accent | Seed | Genres |
| --- | --- | --- |
| lucid | `#E3B66B` | The app outside stories, and any genre not listed |
| jade | `#5CC9A7` | Cultivation, xianxia, wuxia, martial |
| azure | `#84A9F5` | Knights and aura, chivalry, superpowers |
| ember | `#F08A5D` | Many races and monsters, fantasy, dungeons, post-apocalyptic |
| violet | `#B08CFA` | Reincarnation, isekai, regression |
| crimson | `#EF7A82` | Grounded modern, crime, mafia, noir |
| cyan | `#4FCFE0` | Science fiction, space, cyberpunk, mecha |
| orchid | `#DD8BE8` | Supernatural, urban fantasy, horror |
| lime | `#A8D46F` | None: only when the player picks it |
| rose | `#F390B8` | None: only when the player picks it |
| silver | `#B7BFCC` | None: only when the player picks it, for a quiet, nearly colorless story |

**The player can pick a story's color** (S13). The story's settings offer Automatic, the genre's
accent, then every accent in `GenreAccent.palette`, around the color wheel from red to pink, then
silver. Each swatch is 48 dp across, with its name in a tooltip and for screen readers, and a ring on
the one picked. The sheet wears the color being picked, so the player sees it before saving. The
choice is `StorySettings.accent` on the server, so the Library's tiles (`StoryTile(accent: …)`) and
every device show it. `GenreAccent.of(genre:, chosen:)` resolves a story's accent: the chosen one,
or its genre's when there is none or the name is one this app doesn't know.

Wrap a story's screens in `StoryTheme(genre: …, chosen: …)`, or `StoryTheme.accent(accent: …)` for
an accent already resolved, such as the one the play screen hands Memory and Status. It animates
the accent when the story loads and when the player changes it.

## Type

Fonts are bundled (`assets/fonts/`, SIL Open Font License), so nothing loads at runtime and text
looks the same offline.

| Style | Font | Size / line | Use |
| --- | --- | --- | --- |
| display S to L | Literata Display 500 | 30 to 44 | Page headlines (`PageHeader`, 33 in two lines), a story's title on its title page (40), the welcome headline (44) |
| headline S to L | Literata Display 500 | 21 to 28 | Sheet titles |
| cover titles | Literata 600 | 18 to 23 / 1.17 | A title over a painting (`coverTitleStyle`), heavier so it holds on a picture |
| title S to L | Inter 600 | 14 to 19 | List titles, buttons (15.5) |
| body S to L | Inter 400 | 12.5 to 16 | Interface text |
| `narration` | Literata 400 | 18 / 1.62 | The story itself |
| `playerAction` | Literata italic | 16.5 / 1.45 | What the player did, above a scene |
| `overline` | Inter 600, tracked | 11 | Section labels, genre lines (uppercase) |
| `meta` | Inter, tabular figures | 12.5 | Time, turn counts |

The reading column is at most 680 px wide, about 70 characters a line. Narration supports `*italic*`
and `**bold**`; a blank line starts a paragraph with a short gap.

A headline in two lines sets its second in gold and breaks it into lines of like length
(`GradientText(balanced: true)`), so no line is left with one word. Large headlines grow with the
system's text size only to 1.4 times (`HeadlineScaling`): they are already several times the size
of body text, and at twice that one word no longer fits a phone's line. Everything else scales in
full.

## Space, shape and layout

- **Spacing** is on a 4 pt grid: 2, 4, 8, 12, 16, 24, 32, 48. Screen gutters are 20.
- **Radii:** 8 (small), 12 (pictures), 16 (fields), 20 (cards), 24 (covers and painted tiles), 28
  (sheets), and pills for buttons, chips, the composer and the glass bars.
- **Layout:** phones get the tabs as a pill of glass that floats over the page's foot
  (`LucidTabBar`), so the page runs on behind it and ends with a `PageEnd`, the room that lets its
  last thing scroll clear of the bar. From 840 px wide the tabs move into a side rail under the
  app's mark. Lists and forms stay within 920 px, and reading within 680 px. A row of its own
  never stretches across a wide screen: Library's stories go two across from 640 px inside the
  gutters, and Account's settings keep to 680 px under the page title.
- **A tab's page** opens with the app's mark and name (on a phone; the rail has the mark on a wide
  screen), then its headline, over the night air: "Pick a world, or" then, in gold, "dream up your
  own."
- **The tabs** show every name where there is room, in English, Spanish and Catalan on a phone
  from 360 px wide (`test/design/tab_bar_test.dart` measures it in the app's own font). On a
  narrower phone or at a large text size they draw closer in two steps, and then only the tab the
  player is on keeps its name. Every tab keeps its name for screen readers and on a long press.
- **Discover** opens on starting from your own idea, then the latest story the player can still
  play on (Continue your story, S8), then the signature worlds and the shelf of more worlds. On a
  phone the signature worlds are a row to swipe, one large card at a time with the next peeking
  in, and a swipe settles on a card; from 600 px inside the gutters they are two across, and the
  story to continue is as wide as one of them. The section heading names them, so the cards carry
  no badge. The first load waits for the player's stories as well as the worlds, so the story to
  continue never pushes the worlds down once they show.
- **Touch targets** are at least 48 px, whatever the drawn size: a ghost pill is 36 px high and a
  send button 42 px across inside their 48.

## Motion

Short and calm: 150 ms for small changes, 200 to 250 ms for entrances, eased out. New narration
fades in word by word as it streams (S3), choices rise in one after another, and pictures fade in
over their shimmer. A page arrives from the top down: each part fades in and rises 14 px over
320 ms, 50 ms after the one above it (`RiseIn(order: …)`). The night air moves on one slow loop of
16 s: the glow breathes and each firefly wanders a few pixels and twinkles. With the platform's
reduce-motion setting on, everything appears at once, and shimmers, the glow and the fireflies
stand still (`Motion.of(context, …)`, `Motion.reduced`). The dice are the one place where motion
is the point, and they have their own rules ([The dice](#the-dice)).

## Components

All in `lib/design/components/`, exported from `design/design.dart`.

| Component | What it is |
| --- | --- |
| `GradientText` | Lettering in the accent's gradient. `balanced` breaks a headline into lines of like length |
| `Glass`, `GlassTopBar` | A panel of smoked glass with a hairline edge and a soft shadow, blurring what lies behind it; and a story's bar made of it, for a scaffold's `appBar` with `extendBodyBehindAppBar`. The page keeps its first words below `GlassTopBar.extent` |
| `LucidTabBar` | The glass tabs at the foot of a phone, with the tab the player is on lit in the accent |
| `Ambient` | The night air behind a page: the glow and the fireflies (`Ambient.corner` on a tab, `Ambient.forest` around the gate). It takes no taps and says nothing to a screen reader |
| `RiseIn` | Lets a part of a page fade in and rise when it first shows, in the order given |
| `BrandMark` | The forest gate in a small round frame, with or without the app's name |
| `GhostPill`, `AccentOrb` | A quiet pill with a hairline edge, for an action beside the story (How it played out, Wait, Observe); and a round bead of the accent's gradient, lit from behind: send, or the way into a story |
| `SceneCard` | One scene: the player's action under a thin line of the accent (with a mic mark when spoken, V7), time chip, event badge, picture, narration, portraits and a footer for scene details and the scene menu, which goes under the portraits when the two don't fit on a line. In the feed the picture comes after the narration (`pictureAfterNarration`), so a picture that lands late never pushes the words being read |
| `NarrationText`, `StreamingNarration` | Finished narration, and narration as it streams in with a breathing caret and skeleton lines before the first words. With `dropCap` the first paragraph opens with a capital |
| `DropCapParagraph` | A paragraph that opens with a large capital in gold, set into its first two lines. Only a letter or a digit is set this way, so a paragraph that opens with speech keeps its mark and stays plain, as does one in a column too narrow for words beside the capital. A screen reader hears the paragraph whole |
| `StoryChoices` | Suggested choices as full-width tiles with their kind over them (main thread, personal, side path, wild card), the first one ringed in the accent, then **Wait** and **Observe** as ghost pills (S2) |
| `Composer` | The action box, a pill of glass that lights its edge when it has focus: grows to five lines, mic slot, a send bead that lights up once there are words to send and spins while busy, slash-command hints (S5) and a counter near the 2000-character limit |
| `MicButton` | The mic in four states: idle, starting, listening (with a level halo) and denied |
| `PictureSlot` | A picture's place: shimmer while pending, fade-in when ready, quiet collapse when skipped or broken (M3). With `onError`, a picture that fails to load is reported once, so the play screen can fetch a fresh URL by its image id, and the shimmer stays meanwhile |
| `PortraitAvatar`, `PortraitStack` | A character's portrait, or initials until one exists; a stack shows three, each in a thin ring of the accent, and counts the rest |
| `TimeChip` | How long a scene took and when it ended (W10); the accent tint when the player's clock ran apart from the world's (W10a) |
| `EventBadge` | An event, louder from personal (an outline) to local (a tint and a lit dot) to world (the gradient) (W16) |
| `CoverCard`, `StoryTile` | A premise or story as a painting with its genre, title and line on a scrim at its foot, inside a thin ring of its accent; and a story's row, a card of night ink in both themes with the cover coming out of the ink on its far side: in the Library with its menu, and as Discover's story to continue with a lit bead. Tiles side by side match the taller one |
| `showAppSheet` | A bottom sheet with a handle, a serif title and a width limit on large screens |
| `SkeletonText`, `SkeletonList`, `Shimmer` | Loading placeholders in the shape of what is coming |
| `EmptyState`, `ErrorState` | Nothing here yet, or a load that failed, in plain words with one action; errors use the typed API codes (T7) |
| `AsyncValueView` | Loading, error and data for a Riverpod `AsyncValue` |
| `ContentColumn`, `PageHeader`, `SectionLabel`, `Eyebrow`, `PageEnd` | Width limits; a tab's header; a small uppercase label led in by a short line, as a group's heading or over a title; and the room at the end of a page under the glass tabs |
| `StarRule`, `SceneOrnament` | A thin rule with a star at its heart, under a story's title; and the small mark between two scenes |

Features add their own widgets on top of these; when one is useful to more than one screen, move it
here and add it to the gallery.

## Pictures

The app frames pictures and the pictures backend (`backend/media/`, WS8) makes them. Its house style
(`HOUSE_STYLE` and `FRAMING` in `backend/media/prompts.py`) follows this section; change the two
together.

- **Shapes come from the kind** (docs/API.md): places and scenes are 16:9, portraits and covers 3:4.
  The slot takes its shape from the scene's `image.kind` before the picture arrives, so nothing
  jumps when it lands.
- **Scenes and places** run edge to edge on a phone and get 12 px corners in a wider column. The app
  adds its own vignette and fades the bottom edge into the page, so the image keeps its focal point
  in the upper two thirds, leaves the bottom calm and dark, and has no vignette or border of its
  own.
- **Portraits** are head and shoulders with the face in the upper half, on a dark, simple
  background, so they still read cropped to a 30 px circle in a stack; in the feed a portrait is
  shown at most 280 px wide.
- **Covers** leave calm, darker space in the lower third, where `CoverCard` sets the genre and title
  over a scrim. In the Library a cover fills the far two thirds of its story's tile and fades into
  the tile's ink where the words are; on Discover's shelf of more worlds covers show whole, in
  their own 3:4 shape. A wider slot (Discover's signature cards, the create flow's banner, a
  story's title page) keeps the cover's upper part (`coverFocus`), where its focal point is. A
  cover not drawn yet, or still loading, shows a glow in the genre's accent, and the cover fades
  in over it (`CoverImage`). The starter premises' covers are drawn once for everyone by the
  backend's `draw_premise_covers` command, with the same framing.
- **The house style (S7, M5)** suits the dark page and the app's readers, teens and adults: a
  grown-up look, like a frame from an anime film or a graphic novel made for adults (Miki,
  2026-11-08: the pictures looked like a fairy tale for children). Semi-realistic proportions,
  faces that show each person's true age and character, high detail (intricate textures, fine
  highlights and crisp small details, with the focal point kept clear), a serious, grounded
  mood, dramatic painterly light true to the moment's time of day with strong contrast and deep
  shadows, atmospheric depth and a muted, naturalistic palette with one strong accent, in the
  world's own era and look. Nothing cute or childish: no chibi or cartoon proportions, no
  oversized eyes or baby faces on grown-ups, no candy or pastel colors, no storybook look.
  Everyone is drawn at the age the story gives them. A scene is lit for the hour on the story's
  clock, while its bottom edge stays calm and darker for the fade. One uninterrupted image with no
  border or vignette of its own and no writing in it: no text, logos or panels. Mild in what it
  shows in every rating, never in its mood (M6). A change of style moves `HOUSE_STYLE_VERSION` on,
  so the next deploy draws the starter covers and every story's pictures again (M4).
- The placeholder art in `assets/fake/` is procedural and only stands in for the fake API.

## App icon

![The icon on iPhone, as an Android round icon and as an Android 13 themed
icon](docs/screenshots/app-icon.jpg)

**The forest gate** (Miki's pick, 2026-11-04): a cloaked traveller walks through a glowing golden
doorway in a dark forest, the moment a story begins. It is the app's night and lucid gold in the
painterly anime look of its pictures, and at home-screen size it reads as a bright arch with a
dark figure.

- **The painting:** `tool/app_icon/forest-gate.jpg`, painted by Gemini on Vertex AI
  (`gemini-3.1-flash-lite-image`, 1:1, 1K) from this prompt: "A glowing doorway of golden light
  standing alone in a dark misty forest, a small cloaked traveller about to step through. Square
  mobile app icon artwork for an anime interactive story game. One bold, centered subject that
  stays readable at 48 pixels, kept inside the middle 60% of the frame, on a full-bleed background
  that fills the whole square edge to edge. Painterly anime key-art style, cinematic low-key
  lighting, deep ink-blue night tones with one strong warm gold accent. No text, no letters, no
  logos, no watermark, no border, no frame, no rounded corners, no user interface." That came
  as 1024 px with the scene on a 584 px inner panel. On 2026-11-10 the panel was upscaled 4x with
  Real-ESRGAN and repainted by Gemini at 4096 px: the same design painted afresh in a darker,
  denser forest, with the traveller from a repaint that draws them with more care (robe folds, a
  buckled satchel, cuffed boots), mostly by `gemini-nano-banana-2.1`. Miki picked it from three
  rounds of pictures, and it is the same picture as the website's hero. The scripts and the
  exact prompts are in the website's repo, Mikigb77/LucidSaga_Web (`scripts/upscale.py`,
  `scripts/repaint.py`). The file holds that scene at 1680 px, enough for the App Store's 1024 px
  icon, inside a 400 px margin of the scene mirrored at its edges for the blurred rim of
  Android's adaptive layer. It keeps the IPTC mark for AI-made media.
- **One source:** `tool/app_icon/icon.svg`, on Android's 108-unit adaptive-icon grid in three
  layers: `#bg`, the painting, opaque; `#fg`, empty, since the painting is one layer; and `#mono`,
  the doorway with the traveller cut out, for Android 13 themed icons.
- **Every size from it:** `tool/app_icon/render.mjs` draws Android's adaptive layers and the icon
  for Android before 8, each size in the iOS asset catalog (opaque, as the App Store requires) and
  the web's favicon, manifest icons (maskable ones full bleed) and home-screen icon. To change the
  icon, edit the SVG, run the script (how is at its top) and commit the PNGs it writes.
  `test/app_icon_test.dart` checks that no size is missing.
- **Store-safe:** like the screenshots, the icon stays 4+ in the stores (REQUIREMENTS.md, Apple
  2.3.8).

## The play screen

The story reads as one page of scenes, like a book that writes itself.

![Opening at the newest scene, the title page, a turn streaming in, the scene once saved, its
picture and choices, a failed turn](docs/screenshots/play-screen.jpg)

![How it played out (with what struck back), story settings, /status and
Memory](docs/screenshots/play-sheets.jpg)

- **The page runs on behind the bar.** The bar at the top is a pill of glass (`GlassTopBar`) that
  floats over the page, so a cover or a picture passes under it, and the page dims a little under
  the status bar so nothing is read through the clock. The page's last lines fade out towards the
  action box.
- **The title page** sits above the opening scene: the story's cover, when it has one, fading into
  the page at its foot and behind the bar at its top, with the genre, the title in gold and a rule
  with a star standing on it. The title is the page's heading for a screen reader.
- **The opening scene starts with a drop capital**, as a story opens in a book
  (`DropCapParagraph`), while it streams in and once it is saved. No other scene has one.
- **Where it opens:** at the top of the newest scene, a little below the bar, so the player picks
  up where they left off and its first line never sits under the bar. A story whose newest scene
  is its opening opens on the title page, which stays whole while the opening streams in. Older
  scenes load above as the player scrolls back, and the page never moves under them. **Latest**
  appears when they are far back.
- **A turn:** the player's action appears at once, then the words stream in under it (S3). The page
  follows the scene as it grows but stops at its top, so it is read from the first word at the
  player's own pace. When it is saved, the time chip and event badge join it without moving the
  words, and the choices rise in below; a scene written faster than the page could follow is
  still brought up to its top, or to its choices when all of it fits. A standing action reads as
  **Wait** or **Observe**, in the app's words.
- **Pictures** take their place under the words they belong to, as a shimmer in the right shape,
  and fade in when painted (M3). A picture that never comes leaves no trace.
- **Why it went that way** (A8): every scene opens "How it played out" as a replay of its steps
  ([The dice](#the-dice), S15), with the dice of each step that threw any and a tick on each one
  the facts settled. A standing action's one step reads in the app's words there.
- **When a turn fails** (T7), a calm card takes the scene's place and says what happened in plain
  words, with the way on: retry (counting down after a rate limit), say it another way, or open
  Account. Nothing was saved, and the words the player wrote are never lost. Running out of
  credits opens a sheet instead. A content limit shows the server's own words.
- **A turn the story owes** (A3). Once a turn's steps have been shown, the story plays that turn
  before any other. It starts by itself as the story opens, and the page goes to it. If it fails
  and the player dismisses the card, it stays on the page under its own words as "This turn is
  already decided", with **Play it out**; the action box and the choices wait behind it. Words
  sent for another turn come back to the box, with a line that says another turn was already
  decided.
- **The scene menu** illustrates a scene (M2) or reports it (F6). A blocked scene collapses to one
  quiet line in its place.
- **The bar** keeps the title and the world's date and time in sight (W10), with `/status`,
  Memory and the story's settings (S6) a tap away. It keeps its height at any text size, so its
  words grow only as far as they fit (1.3 times), as an app bar's do. `/status` and Memory show
  the player character's portrait once it is drawn (M4), and the initials until then.
- **Names from the world** start with a capital where they stand as a heading or a card's title
  (`"the inner court".asHeading` is "The inner court"), and keep the world's own spelling
  everywhere else.

## The dice

"How it played out" is a replay for every scene (S15): the turn's steps one at a time, each with
the throw that decided it or the tick of a step the facts settled, and then the whole turn as a
list.

![A throw resting on what it is against, the dice in the air, a deadly throw where the gold die
holds at ten, a 20 that throws one more and goes over the top, and a step opened again in the
list](docs/screenshots/replay.jpg)

- **A dark table, in the dice's own colors.** The replay looks the same in both themes and under
  every accent (`ReplayInk`): bone for the hand, jade for a green die, violet for the insight
  die, gold for mastery, grey for the world's die and white for a die a 20 threw. A story's color
  never tints it, so a green die always reads as a green die. A result is jade when it went well,
  gold when it was so close or over the top, and red when it went badly; a throw that can kill
  wears red from the start and ends in jade if the character came through.
- **One step at a time.** A step appears only when its turn comes, so nothing says what is coming.
  While it plays it is the one thing to look at, large in the middle over the list, which dims.
  When it is done it goes down into the list as a row, and the row lights once as it lands.
- **Read first, then the dice.** A throw says what it is up against before any die moves, with
  the hand in small pills under it, and rests there long enough to read: longer for more words,
  and longer still when a miss can kill, where the tray's edge beats like a heart. A line under
  the words runs out as the throw comes nearer. The card is laid out whole from the start, with
  the room its result will need, so it never changes size while it is watched.
- **The count is shown, not told.** Each die is read into a bar that runs to the most the hand
  could make, in its own color, with a line at the number and the stretch that is so close
  hatched just short of it; then into a sum; then the total against the number; then the stamp.
  The words under it say only what the throw meant.
- **No die where none was thrown.** A step the facts settled draws a ring that closes on a tick,
  or on a bar when the world ruled it out, with why under it. A roll saved before the dice
  travelled plays the same way, with the odds it kept in a line beside how it fell.
- **A tap anywhere moves on**: it throws dice that are waiting, shows a result still being
  counted, and goes on from a result being read. The card says so in small words where it
  applies ("Tap to see the result", "Tap to go on"). **Skip** gives the list at once.
- **The list** is the turn at a glance: each row with its total in a bead, or a tick where
  nothing was thrown, what it was, and its result. A row opens in place as it ended, with **Watch the throw again** and the roll's seed,
  and the list scrolls to show it. Under the rows are the scene's time, its chain of cause and
  effect and where a plan stopped.
- **Gamer mode** (a switch in the story's settings, off by default, kept on the device) opens the
  replay by itself when a turn's steps are decided and one of them threw dice, while the story is
  written behind it. Then it is headed "How it plays out", offers nothing at its end and gives
  way to the story by itself, and Skip goes straight to the story.
- **Reduced motion:** the dice appear where they came to rest, the card and the row neither fly
  nor flash, there is no celebration, and the time to read stays the same.
- **How it is built:** the dice are drawn and moved by the app's own code (`features/story/dice`),
  ported from the prototype line by line and held to its numbers by tests, with saved pictures
  for their look. To change how they look, run
  `flutter test --update-goldens test/features/dice` and look at the pictures before committing
  them.

## Voice

The mic sits wherever the player types (V1): in the composer's mic slot and as a field's suffix.
Use `DictationButton(tracker: InputModeTracker(controller))`, with the box's `storyId` or `draftId`.
Words are never sent on their own (V2). Online dictation (the default, V6) records until the player
taps again (a pause to think never ends it; a long dictation lands in parts meanwhile, and leaving
the app turns the mic off), then the mic spins (`MicVisual.transcribing`, "Writing down what you said")
until the words land in the box; with the phone's recognizer they appear live. A failure is a short
snackbar that says what to do: out of credits, too many dictations, or the server out of reach. The first tap asks for permission with a reason (V5); if the player
refuses, the mic shows a struck-through icon and explains how to allow it, and typing still works.
Where the platform has no recognizer, the mic hides. The tracker reports `typed`, `voice`,
`voice_edited` or `choice` with each turn (V7).

## Sign-in and account

- **The welcome screen is the gate.** The painting from the app's icon stands at the top of the
  page and fades out at its foot, where the headline stands on it: "Step through." and, in gold,
  "The story never ends." Fireflies drift in the forest around it. Under the headline are the
  tagline and the ways in, on the first screen of a phone. On a page wider than the painting its
  sides fade out too, and the words keep to a column under it. The pictures are in
  `assets/brand/` (`gate.jpg`, and `mark.jpg` for `BrandMark`), cut from
  `tool/app_icon/forest-gate.jpg`, and keep its mark for AI-made media.
- **Google's button** follows Google's branding rules: the four-color G, "Continue with Google", and
  Google's dark or light fill and stroke, never the app accent. On the web the page shows the button
  Google draws itself, since Google allows no other sign-in button on the web.
- **The birth-date step is neutral** (F8): the date starts empty and in typed entry, the copy says
  why we ask, and a refusal never names the minimum age, so nobody learns which date to type.
- **Credits** read as cents below a dollar (`44.6¢`) and as dollars from one (`$1.20`), with a real
  minus sign; the owner sees "Unlimited" and still sees each cost in the history. Each line of the
  history keeps its amount and the balance after it beside the entry, wrapping within their share
  of the row at large text sizes rather than overflowing. On the balance card, History sits at the
  far side of the balance, or under it when the two don't fit on a line.
- **The Developer section** (which server the app talks to, and the gallery) shows only in
  development builds and to the owner, never to players.
- **Destructive steps** say exactly what goes, offer the export first, and ask the player to type a
  word before the red button works.
- Problems the server finds on a form show under their field once the player has tried to submit,
  and clear as soon as that field changes.

## Words

- Every string the player sees is in `lib/l10n/app_en.arb`, with its Spanish in `app_es.arb` and
  its Catalan in `app_ca.arb` (S10). Read them with `context.l10n`. A new or changed string goes in
  all three files in the same change (Spanish from Spain with "tú", Catalan with "tu"), and
  `test/l10n_test.dart` fails when one is missing, loses a placeholder or is left in English (or,
  in Catalan, in Spanish). Spanish runs about a fifth longer than English, so check a new
  screen in Spanish at twice the text size too (`test/features/large_text_test.dart`). Only the
  developer gallery uses literal English.
- The player picks the language in Account (S10), from a pop-up list that scrolls: the device's own
  by default, English when the device's isn't one the app has, each language named in itself. A new
  language is a value of `AppLanguage`, an `app_xx.arb` and a `privacy_xx.md`. Only the app's fixed
  text follows it, and the language a new story starts in: a story then keeps its own. What the
  server writes in the app's language, such as the starter premises, is asked for with
  `appLanguageCodeProvider`.
- Sentence case, plain words, full sentences. Say what happened and what to do next: "You're
  offline. Check your connection and try again."
- Errors never show a status code or a stack trace (T7).
- **A change says what it costs before the player makes it**, next to its button: "Free: nothing
  needs redrafting", or which parts get redrafted with credits (K2). The create review does this
  with `CostNote`, from the same rules the server uses.

## Accessibility

- Contrast at 4.5:1 or better everywhere, tested: every text color on every surface, both ends of
  the gold gradient on the page and on a card, what is written on the gradient, and the lit tab
  on its own light over the glass.
- Text scales to 200% without clipping or overflow; the gallery is tested at 2× text. Three things
  that keep a fixed size hold their words back instead of clipping them: large headlines (1.4
  times), a story's glass bar (1.3 times) and the initials in an avatar's circle.
- Every icon-only button has a tooltip and a semantics label; pictures carry a label when the scene
  gives one, and a pending picture says so. A component that names itself for a screen reader in
  place of its children gives its tap again (`Semantics(onTap: …)`), as the tabs and the send
  button do.
- What is only for the eye is hidden from a screen reader: the night air, the gate, the app's
  mark, the line beside an eyebrow. A headline in two colors is one heading, and a paragraph with
  a drop capital is read whole.
- Reduce motion is respected throughout.
- The replay of a throw is read as its dice and its result: the tray says the numbers that fell
  once they are counted, and the stamp is announced when it comes down.

## Working on the design

- Run the app on the fake API to see every state without a backend:
  `flutter run -d chrome --dart-define=API_MODE=fake`.
- Open `/gallery` (debug builds and the fake API) to see every component. The query
  `?theme=light&accent=jade&scale=2` sets the controls up front, for screenshots.
- Change a token in `lib/design/tokens.dart` or a component, then check the gallery in both themes
  and at 2× text, and run `flutter test test/design/`. The gallery's "Gold, glass and night air"
  section shows the pieces of the look together.

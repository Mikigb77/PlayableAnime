# Feature list (draft v0)

An AI interactive-fiction app for phones: start from a premise, play through choices or free-text
actions, and an LLM keeps the story going forever while a memory engine keeps it consistent.

> **Naming.** "OOC: The Playable Anime" is Wrtn Technologies' product. We are building our own app
> in the same genre, so before launch we need our own name, branding, premises, characters and art.
> "PlayableAnime" is just the repo's working title.

## What the reference app does

Notes from public coverage of OOC (launched in North America in April 2026):

- **Story-first, not character-chat.** You pick a story, enter a pre-built world and play the lead.
- **Choices or free text** at every branch; the AI generates the next scene live.
- **Four memory layers:** long-term events, short-term context, relationships, current goals.
- **Stats:** HP, affinity and unlock progress; thresholds unlock endings, side stories, images.
- **Images** appear when characters or key moments show up (one story reportedly has ~150).
- **AI RPG mode:** race and class, buffs and debuffs, dice rolls, "observe" or "intervene" turns.
- **Saved Memories tab** that lets players curate what the AI remembers. Also slash commands (e.g. a
  character's inner thoughts) and an output-length setting.
- **Credits, no subscription:** $1.99 for 2,000 credits, up to $99.99 for 100,000. Better models
  cost more. Free credits come from daily check-ins.
- **Top complaints:** credits run out before a story ends, continuity breaks, and the creator tools
  have too many fields.

## Where we can do better

1. **Continuity the engine enforces.** The model *proposes* world changes and the backend decides
   what sticks: the dead stay dead and destroyed factions stay destroyed, no matter what the model
   writes. This is already in the scaffold (`backend/app/engine/memory.py`).
2. **Memory you can see and fix.** A Memory screen with characters, factions, facts and goals. Later
   you can pin, edit or forget entries.
3. **Cheaper play.** Bring-your-own-key, a fast default model, and images generated once per
   character and reused, so a story doesn't run dry halfway through.
4. **Truly endless.** A rolling summary plus chapter summaries and retrieval, so long stories never
   hit the context limit.
5. **One-box creation.** Type a premise; the AI expands it into a world bible. Advanced fields stay
   hidden until you ask for them.

## Features

### P0: MVP

- [x] Discover feed of starter premises *(scaffold)*
- [x] Create a story from your own premise *(scaffold)*
- [x] Play screen: narration, 3 suggested choices, free-text action *(scaffold)*
- [x] Memory engine: characters (alive/dead/missing, affinity), factions (stance), facts with
      importance, goals, rolling summary, enforced invariants *(scaffold)*
- [x] Memory screen, read-only *(scaffold)*
- [x] Library of your stories *(scaffold, in-memory only)*
- [x] Bring your own Gemini key, stored on the device *(scaffold)*
- [ ] Persistence on Neon Postgres
- [ ] Accounts and sign-in (needed before any public deploy)
- [ ] Premise → world bible expansion (setting, rules, factions, key NPCs, tone)
- [ ] Streaming narration (SSE) so text appears as it's written
- [ ] Basic safety: content rating per story, model safety settings, report button
- [ ] Deploy the API to Cloud Run

### P1

- [ ] Character portraits and scene images: one per character, cached and reused
- [ ] Edit, pin or forget memories; undo the last turn; branch a save
- [ ] Optional RPG layer per story: HP, inventory, skills, dice checks
- [ ] Relationship meters, endings and achievements
- [ ] Slash commands: `/thoughts <character>`, `/recap`, `/ooc` (talk to the narrator directly)
- [ ] Settings for narration length and tone
- [ ] More BYOK providers (OpenAI, Anthropic, OpenRouter)
- [ ] Spanish and English localisation

### P2: later

- [ ] Publish, share and remix stories; likes and follows
- [ ] Creator tools: world-bible editor, NPC sheets, lorebook
- [ ] Voice narration (TTS)
- [ ] Monetisation for players without their own key (credits or subscription)
- [ ] Shared multiplayer worlds

## Open questions

- **Player agency.** Do actions always succeed, or can the world push back? In a test against
  Gemini, a "kill this character" action failed in-story: the target survived, hanging off a ledge.
- **Content rating and age gating.**
- **Brand name** (see the naming note above).
- **Monetisation model** and how it coexists with BYOK.
- **Image generator.** Options and costs are in [ARCHITECTURE.md](ARCHITECTURE.md#images).

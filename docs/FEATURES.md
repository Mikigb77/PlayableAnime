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
   writes. The engine does this (`backend/engine/apply.py` and `invariants.py`).
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

The first version's state, checked against the code in WS18.

- [x] Discover feed of starter premises, the signature worlds first (S1), under the latest story
      to continue
- [x] Create a story from your own premise: a drafted world and character to review and change (G1, G2)
- [x] Play screen: streamed narration, suggested choices, Wait and Observe, free-text action (S2, S3)
- [x] Memory engine: characters (alive, dead, missing, attitudes), factions, places, goals, leads,
      rumors and deeds, with the invariants enforced in code (C1, W1 to W16)
- [x] Memory screen, read-only, showing only what the character knows (C6)
- [x] Library of your stories, saved on the server
- [x] Bring your own Gemini key, stored on the device (K6, S9)
- [x] Persistence on Neon Postgres *(stories as JSONB)*
- [x] Accounts and sign-in: Google and email (T8)
- [x] Premise → world bible expansion: setting, rules, factions, key characters, tone (G1)
- [x] Streaming narration (SSE) so text appears as it's written (S3)
- [x] Narration that plays out the player's action step by step, from where the last scene ended,
      before its outcome (R1 to R7)
- [x] Outcomes worked out from the facts: logic first, rolls only for real doubt, and clever
      workarounds reasoned through by cause and effect (A2, A9)
- [x] Voice dictation of actions and premises, with a transcript the player edits before sending
      (V1 to V7)
- [x] Basic safety: content rating per story, model safety settings, report and block (F6 to F8)
- [ ] Deploy the API to Cloud Run *(the pipeline is ready; the first deploy waits on Miki)*

### P1

- [x] Character portraits and scene pictures at key moments: one per character, cached and reused,
      drawn again when a face or place changes for good (M1 to M8)
- [x] Online dictation with Gemini 3.5 Transcribe that knows the story's names, the default, with
      the phone's own recognizer as an option in Account (V6)
- [x] Reading scenes aloud: Gemini's studio voice by default, each part kept and paid once, with
      the device's own voice as a free option in Account (V8 to V10)
- [ ] Edit, pin or forget memories; undo the last turn; branch a save
- [ ] Optional RPG layer per story: HP, inventory, skills, dice checks
- [ ] Relationship meters, endings and achievements
- [ ] Slash commands: `/status` works; `/thoughts <character>`, `/recap` and `/ooc` are still to come
- [x] Settings for narration length and tone (S6)
- [ ] More BYOK providers (OpenAI, Anthropic, OpenRouter)
- [x] English, Spanish and Catalan (S10): the app's text, the starters, the privacy policy and stories, each story in the language it started in

### P2: later

- [ ] Publish, share and remix stories; likes and follows
- [ ] Creator tools: world-bible editor, NPC sheets, lorebook
- [ ] Hands-free voice mode that sends after a pause (V2)
- [ ] Monetisation for players without their own key *(credits, quotas and the starter credit
      are built (K1 to K8); top-ups are not)*
- [ ] Shared multiplayer worlds

## Open questions

- **Player agency.** Do actions always succeed, or can the world push back? In a test against
  Gemini, a "kill this character" action failed in-story: the target survived, hanging off a ledge.
- **Content rating and age gating.**
- **Brand name** (see the naming note above).
- **Monetisation model** and how it coexists with BYOK.
- **Image generator.** Options and costs are in [ARCHITECTURE.md](ARCHITECTURE.md#images).

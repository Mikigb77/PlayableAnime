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
- [x] The draft keeps how the story starts a surprise: its first deadline, people and goal, and what your character wants, show only when your own words name them (G1, G2)
- [x] A deadline your premise gives a time comes at exactly that time: "the exam is in 3 days" is three days (G1, E2)
- [x] A goal is yours to give: it shows when your words say it as an aim ("I must pass the exam", "I came to find my sister"), and a deadline alone gives none (G1, G2)
- [x] Memory keeps the same surprise once the story starts: the people your character already knows, their goal and what is coming show there when a scene first names them (G1, C6)
- [x] The server changes a draft's plain fields at once, with no AI call and at no cost: the title, the tone, and the character's name, age, looks and manner (G1, G2)
- [x] The draft's screen leads with your character and marks every row with how it changes: typed by you at once and free (name, age, looks, title, rules), or told to the storyteller at that row, with the cost said first; how it plays is on the same screen (G1, G2)
- [x] The first step shows what a premise can decide (who you are, what makes you special, what is coming, who is in your life, what you are after), with an example of each, and that the rest stays a surprise (G1)
- [x] Play screen: streamed narration, suggested choices, Wait and Observe, free-text action (S2, S3)
- [x] Memory engine: characters (alive, dead, missing, attitudes), factions, places, goals, leads,
      rumors, deeds and romances, with the invariants enforced in code (C1, W1 to W17)
- [x] Memory screen, read-only, showing only what the character knows (C6)
- [x] Library of your stories, saved on the server
- [x] Bring your own Gemini key, stored on the device (K6, S9)
- [x] Persistence on Neon Postgres *(stories as JSONB)*
- [x] Accounts and sign-in: Google and email (T8)
- [x] Premise → world bible expansion: setting, rules, factions, key characters, tone (G1)
- [x] Streaming narration (SSE) so text appears as it's written (S3)
- [x] Narration that plays out the player's action step by step, from where the last scene ended,
      before its outcome (R1 to R7)
- [x] Scenes sized to what happened: a passing moment is told short and a turning point gets
      room, within the length the player set (R3, S6)
- [x] Looks and stock phrases that don't keep coming back: the character's appearance, and how
      they come across, are told when a scene has reason to show them, and code hands the
      narrator the wording the last scenes repeated, to say another way (R9)
- [x] Whereabouts that stay clear: every scene records the place it ends in, places know whether
      they are outdoors, indoors, underground or underwater, and a way out is told, never guessed (R8)
- [x] Outcomes worked out from the facts: logic first, rolls only for real doubt, and clever
      workarounds reasoned through by cause and effect (A2, A9)
- [x] Odds from who the character is: their attributes, skills, gifts and flaws weighed against
      how hard the task is, and a run of misses that makes the next try likelier (A3, G14)
- [x] Proven abilities stay reliable: a move made with the character's own power is that power at
      work, the first clean success makes it a technique of theirs (listed in Status), and a miss
      is told as what stood in the way, never the ability fizzling (A3, A4, G14, G25)
- [x] Injuries only from what happened: the engine makes every wound the player character carries,
      and no scene or odds lean on a wound they never had (N6, G13)
- [x] Romance the world keeps on record: a bond between two people that moves in stages
      (interest, courting, together, promised, married, over), and a heart of their own for the
      other person, which moves at their own pace. An ask is answered by their heart, nobody
      throws to kiss their own partner, and no scene can make a couple the record doesn't hold.
      Memory tells where the two stand under a heart on that person's entry, as far as the
      character knows (W17, C6).
- [x] A romance that wrongs someone: courting or bedding someone else is a deed on record that
      wrongs the partner of either of the two, and no crime. They learn of it by seeing it or
      from someone who saw it, lose liking, trust and heart by how far it went, and come to
      have it out. A partner whose heart is gone ends it, and a rival comes for revenge only
      over a night together (W17, W1, W2, W4).
- [x] Couples among the cast: a new world records who among its key people is married,
      promised or together, so courting someone's wife wrongs a husband who is on record, and
      whether having several partners is the custom there (W17).
- [x] They have to be there: a move in a romance reaches someone in the scene or at the place.
      Toward someone a short walk away the character goes to them first and the scene plays
      where they are, and toward someone far off it reaches nobody, so nobody says yes from
      another town (W17, W10).
- [x] Whoever the world sends somewhere comes back: an important person's outing, a witness
      who rode off to report and someone who came to have it out all go home again after a
      while, and the way takes its time. The scene can say that a neighbour is away and about
      when they are back (W6, W4, W11).
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
      the device's own voice as a free option in Account, both in the story's own accent: Spanish
      from Spain, never Latin American, and English in a native English voice (V8 to V10)
- [ ] Edit, pin or forget memories; undo the last turn; branch a save
- [ ] Optional RPG layer per story: HP, inventory, skills, dice checks
- [ ] Relationship meters, endings and achievements
- [ ] Slash commands: `/status` works; `/thoughts <character>`, `/recap` and `/ooc` are still to come
- [x] Settings for narration length and tone (S6)
- [x] A color of the player's own for each story, instead of its genre's (S13)
- [x] The dice shown as a replay of each turn, step by step, with gamer mode to play them before
      the scene (S15)
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

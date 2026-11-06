# Privacy policy (draft)

> **Draft for Miki's review. Not published, and not legal advice.** Written by WS6 on 2026-11-03 from
> how the first version is built (T12, V5). Before it goes live, Miki should settle the open
> questions below and have it checked by someone who knows EU data protection law.
>
> The app shows this policy from "Who we are" on, from a copy in `app/assets/legal/privacy_en.md`.
> An app test fails when the two differ, so after a change run
> `awk '/^## Who we are/{p=1} p' docs/PRIVACY.md > app/assets/legal/privacy_en.md`.
> The app also ships the policy in Spanish, `app/assets/legal/privacy_es.md`, and in Catalan,
> `app/assets/legal/privacy_ca.md` (S10), for players whose app is in those languages. Change them in
> the same PR: a test fails when their sections, tables and lists stop matching the English ones.
>
> **Open questions for Miki**
>
> 1. **Who the controller is** and the contact address for privacy requests (placeholders below).
> 2. **Minimum age.** Sign-up is set to 13 and over (`MIN_SIGNUP_AGE`), with Teen stories only
>    under 17 (F8). EU countries set the age of digital consent between 13 and 16 (Spain 14,
>    Germany and the Netherlands 16). If we rely on consent anywhere, younger players in those
>    countries need a parent's consent, so 16 is the cautious choice and 13 the widest audience.
> 3. **Where Gemini runs.** Turns call Vertex AI on the `global` endpoint, which may process
>    prompts outside the EU. An EU regional endpoint (for example `europe-west1`) keeps them in the
>    EU, if the models we use are offered there. The policy must name whichever we choose. Online
   dictation's model, Gemini 3.5 Transcribe, is offered only on the `global` endpoint today.
> 4. **Backup window.** Neon's point-in-time restore keeps deleted data in its history for the
>    plan's restore window. Fill in the real number of days.
> 5. **Log retention.** Cloud Logging's default bucket keeps logs 30 days. Confirm, or set a
>    shorter retention.

## Who we are

Lucid Saga is an AI story game made by [controller name], [address]. For anything about your data,
write to [privacy contact email]. We answer within one month.

## What we collect and why

| What | Why | Legal basis |
| --- | --- | --- |
| **Account:** email, display name, birth date, and either a password (stored only as a salted hash) or your Google account's ID | To sign you in, keep your stories yours, and apply the age rules: Teen stories only under 17 | Contract |
| **Story settings and content preferences:** gore level, romance and dark themes on or off | To shape the stories you get | Contract |
| **Your stories:** the premise, the actions you type or dictate, the choices you pick, and what the narrator writes back | This is the game: each turn sends the story so far to the AI model to write what happens next | Contract |
| **Pictures** made for your stories | Shown in your stories, made at key moments | Contract |
| **Credits:** your balance and what each turn, picture or dictation cost | To charge fairly and show you your spending | Contract |
| **Signed-in devices:** when each one signed in and was last used | To keep you signed in and let you sign a device out | Contract |
| **Technical logs:** request ids, your account id, the story id, errors, timings, costs per turn, and when a scene was blocked by our safety rules and under which category (never the story's text) | To keep the service running, fix bugs and control costs | Legitimate interest |
| **Reports:** the scene you reported, the reason you picked, any note you wrote, whether you blocked the scene, and what our staff decided | To review scenes that may break our content rules, fix the narrator, and keep a scene you blocked hidden | Legitimate interest |
| **Sign-in protection:** short-lived counts of failed sign-ins per email and per network address, stored only as one-way keys, never the email or address itself | To stop password guessing and fake sign-ups | Legitimate interest |

We never sell your data, show you ads, or use your stories to train AI models.

## Speech

When you tap the microphone, what you say becomes text in the box, for you to check before you
send it (V5). In Account, under Dictation, you choose what writes it down:

- **Online (the default).** The app records while the mic is on and sends the recording to our
  server, which has Gemini on Google Cloud's Vertex AI write it down, listening for the names your
  character knows in that story. The recording is used for that request only: we never store it or
  log it, and Google doesn't use it to train its models. We keep only its length and its cost, as
  an entry in your credit history.
- **This device.** Your phone's own speech recognizer writes it down, and the audio never reaches
  our servers. Android uses Google's speech recognition service on your phone; recent phones
  recognize speech on the device itself. iOS uses Apple's speech recognition: where your iPhone
  supports on-device recognition for your language, the audio stays on the phone; otherwise Apple
  processes it on its servers.

The text is part of your story like anything you type. The app asks for microphone permission the
first time you tap the mic, the mic is on only while it shows it is listening, and typing always
works.

## Who processes your data for us

| Service | What it does | Where |
| --- | --- | --- |
| Google Cloud: Cloud Run, Cloud Storage, Cloud Logging, Secret Manager | Runs the game server, stores pictures and logs | EU: Frankfurt |
| Google Cloud: Vertex AI (Gemini) | Writes the story, draws the pictures and writes down online dictation. Google doesn't use this data to train its models. The part of a story's prompts that stays the same from turn to turn (its style, content settings and world) is kept in a Vertex AI cache until 15 minutes after your last turn, so it costs less | [Global endpoint, possibly outside the EU, or an EU region: see open question 3] |
| Neon | Hosts the database | Frankfurt (AWS eu-central-1) |
| Google Sign-In | Confirms who you are when you sign in with Google | Google |

Where data leaves the EU, it does so under the European Commission's standard contractual clauses
or the EU-US Data Privacy Framework.

**Your own API key.** If you add your own Gemini API key, your turns go to Google's Gemini API
under your own account and Google's terms for it. Online dictation still runs on our account. On Gemini's free tier, Google may use what you
send to improve its products. The app keeps the key on your device and sends it with each request;
our server uses it for that request only and never stores or logs it.

## How long we keep it

- **Your account, stories and pictures:** until you delete them.
- **Reports:** until you delete the story or your account.
- **Deleting your account** (Account, Delete account) removes your account, every story, every
  picture and every signed-in device from the live database and storage at once. Copies in the
  database's restore history disappear when they age out of it, within [N] days.
- **Logs:** [30] days.

## Your rights

You can, at any time:

- **Download everything** we hold about you as a file (Account, Export my data).
- **Delete your account** and everything in it (Account, Delete account).
- **Correct** your display name and preferences in Account, or ask us to correct anything else.
- **Object** to processing based on legitimate interest, or ask us to restrict it.
- **Complain** to a data protection authority, such as [the authority for the controller's
  country, for example Spain's AEPD].

## Children

You must be at least [13] to sign up, and we ask your birth date when you do. Players under 17 only
get Teen stories, whatever the store age rating says. If we learn that someone under the minimum
age signed up, we delete the account.

## Security

All traffic is encrypted. Passwords are stored only as salted hashes, sign-in tokens as one-way
hashes, and our own keys and passwords live in Google Secret Manager. Signing out on a device ends
its sign-in at once, and repeated wrong passwords are slowed down.

In our admin tools, only the owner and the staff who handle reports can read story text, and they
read it to review reports. Other staff, who help with accounts and credits, see a story's title,
rating and numbers, never what is written in it.

## Changes

If this policy changes in a way that matters, we'll tell you in the app before it takes effect.

*Last updated: [date].*

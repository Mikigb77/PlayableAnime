# Privacy policy

> **Not legal advice.** Miki settled the operator and the sign-up age on 2026-11-08. Have the words
> checked by someone who knows EU data protection law before the Play listing. It says what the
> first version does (T12, V5).
>
> **One policy, two places.** These are the words of the website's Privacy Policy
> (Mikigb77/LucidSaga_Web, `src/content/legal/{en,es,ca}.ts`, published at
> `https://lucid-saga-web-528988811295.europe-west1.run.app/{en,es,ca}/privacy`), so the app and the
> website never say different things. Where the app shows them, "this website" reads "our website",
> the operator's details are a list, links are written out, and the last lines point to the website.
> A change to one changes the other on the same day, and a change that matters is announced in the
> app before it takes effect. Where each fact comes from is in the website's `docs/LEGAL.md`.
>
> **What it rests on.** GARBAR, IN-TEC, S.L. is the controller, with `lucidsaga@garbar.tech` for
> general enquiries and `lucidsaga.support@garbar.tech` for support, privacy and deletion (both must
> exist as aliases of the company mailbox before the Play listing). Sign-up is
> 16 and over (`MIN_SIGNUP_AGE`), with Teen stories only under 17 (F8): at 16 no EU country asks for
> a parent's consent, which the app doesn't collect. Turns, pictures, online dictation and the
> studio voice run on Vertex AI's `global` endpoint (`VERTEX_LOCATION`), so Google may process them
> outside the EU. Logs are kept 30 days, Cloud Logging's default. Backups are Neon's restore window,
> not stated as a number.
>
> The app shows this policy from "At a glance" on, from a copy in `app/assets/legal/privacy_en.md`.
> An app test fails when the two differ, so after a change run
> `awk '/^## At a glance/{p=1} p' docs/PRIVACY.md > app/assets/legal/privacy_en.md`.
> The app also ships the policy in Spanish, `app/assets/legal/privacy_es.md`, and in Catalan,
> `app/assets/legal/privacy_ca.md` (S10), for players whose app is in those languages. Change them in
> the same PR: a test fails when their sections and lists stop matching the English ones, or when
> the age they state isn't the app's.

## At a glance

- We don’t sell your data, show you ads or use your stories to train AI.
- Your story goes to Google’s AI to write what happens next, draw its pictures and read it aloud.
  Your voice goes there only when you dictate online.
- You can download everything or delete your account in the app, whenever you want.

## 1. Who is responsible

- **Operator:** GARBAR, IN-TEC, S.L.
- **Tax number (NIF):** B56760374
- **Registered address:** Carrer Sant Antoni Mª Claret, 24, 3ª planta, 08037 Barcelona, España
- **Mercantile Registry:** Registered in the Barcelona Mercantile Registry, volume 49105, folio 130,
  sheet 607875, entry 1
- **General enquiries:** lucidsaga@garbar.tech
- **Support, privacy and deletion:** lucidsaga.support@garbar.tech

GARBAR, IN-TEC, S.L. operates Lucid Saga and is the controller of the personal data described here.
Lucid Saga is the product’s name, not a separate company. This policy covers the Lucid Saga app, its
account and game servers, and our website.

This policy explains how we use data; it doesn’t ask for blanket consent. Where a feature needs a
permission or your consent, the app asks at the time.

Write to lucidsaga@garbar.tech for general enquiries, and to lucidsaga.support@garbar.tech for
support, privacy requests and account deletion. Both reach our company mailbox. You don’t need a
particular form or subject to exercise your rights.

## 2. What we collect

- Account: your email address, a display name, your birth date, and either a password, stored only
  as a salted hash that can’t be read back, or your Google account’s identifier when you sign in
  with Google. We never receive your Google password.
- Story settings: the content preferences you choose (gore level, romance and dark themes on or
  off), your dictation and reading-aloud choices, and the language of each story.
- Your stories: the world or premise you start from, the actions you type or dictate, the choices
  you pick and what the narrator writes back, with the story’s state: its characters, places and the
  facts its world remembers.
- Pictures and audio: the pictures drawn for your stories, and the audio of scenes read aloud in the
  studio voice, kept so a scene you hear again plays at once and costs nothing.
- Credits: your balance, and what each turn, picture, dictation or scene read aloud cost.
- Signed-in devices: when each one signed in and was last used, so you stay signed in and can sign a
  device out.
- Reports: a scene you report, the reason you pick, any note you write, whether you blocked it, and
  what our staff decided.
- Technical records: request identifiers, your account and story identifiers, errors, timings,
  costs, your network address and app version, and, when our safety rules block a scene, its
  category, never the story’s text. Short-lived counts of failed sign-ins per email and per network
  address are kept only as one-way keys.
- Messages you send us, and what we need to answer them.

## 3. Why we use it, and our legal bases

- To provide the game you ask for (GDPR Article 6(1)(b), contract): your account, writing your
  story, drawing its pictures, reading it aloud, dictation, credits, export, deletion and support.
  Your birth date is needed to apply the age rules.
- Our legitimate interests (Article 6(1)(f)): keeping the service secure, stopping password
  guessing, fake sign-ups and abuse, controlling costs, fixing faults, and reviewing reported scenes
  so the narrator keeps to our content rules. You can object where this is the basis.
- Legal obligations (Article 6(1)(c)): accounting and tax records once there are purchases,
  answering lawful requests from authorities, and handling your data-protection rights.
- Consent (Article 6(1)(a)), only where the app asks for it separately, such as the microphone
  permission. You can withdraw it at any time, without affecting what was done before.

We don’t sell personal data, show ads, use advertising trackers or train AI models on your stories.
The AI writes fiction for your story; it doesn’t make decisions about you with legal or similarly
significant effects.

## 4. The AI, your voice and reading aloud

Lucid Saga is written by AI. On each turn, our server sends Google’s Gemini models, on Google
Cloud’s Vertex AI, what the story needs to go on: the story so far, its world and characters, your
action and your content settings. The same service draws the pictures for key moments. The part of a
story’s instructions that stays the same from turn to turn may be kept in a Vertex AI cache until 15
minutes after your last turn, so it costs less.

Dictation: by default, the app records while the mic is on and sends the recording to our server,
which has Gemini write it down, listening for the names your character knows in that story. The
recording is used for that request only: we don’t store it or log it, and keep only its length and
cost in your credit history. If you choose This device in Account, under Dictation, your phone’s own
speech recognition writes it down and the audio never reaches our servers, though Android’s and
Apple’s recognizers may use their makers’ servers when the phone can’t do it alone.

Reading aloud: by default, the studio voice sends the scene’s text to Gemini, which reads it aloud,
and we keep the audio with your story. If you choose your device’s voice, your phone reads it and
nothing reaches our servers.

Under Google Cloud’s terms, Google doesn’t use what we send to Vertex AI to train its models without
our permission. Google may keep some data for a limited time for caching, safety and abuse
monitoring, and may process it outside the EU. We don’t promise zero retention or EU-only
processing.

Your own API key: if you add your own Gemini API key in the app, your turns go to Google’s Gemini
API under your own account and Google’s terms for it, and on its free tier Google may use what you
send to improve its products. The key stays on your device and is sent only with the requests that
need it; our server never stores or logs it. Dictation and the studio voice still run on our
account.

Stories are fiction. Don’t put real people’s private details, health records, passwords or other
sensitive information into a story.

- Google Cloud service terms, including Vertex AI: https://cloud.google.com/terms/service-terms
- Google Cloud data processing terms: https://cloud.google.com/terms/data-processing-addendum

## 5. Who sees your data

Your stories are private to your account: Lucid Saga has no public sharing. In our team, only the
owner and the staff who handle reports can read a story’s text, and they read it to review reports.
Staff who help with accounts and credits see a story’s title, rating and numbers, never what is
written in it.

Our providers receive what they need for their job, as processors under our instructions, or, for
their own legal, security or payment duties, as independent controllers under their own notices.

- Google Cloud (Cloud Run, Cloud Storage, Cloud Logging, Secret Manager): runs the game server and
  our website, stores pictures and audio, and keeps logs. The game server and its storage are in
  Frankfurt, Germany, and our website in Belgium.
- Google Cloud Vertex AI (Gemini): writes the stories, draws the pictures, writes down online
  dictation and reads scenes in the studio voice.
- Neon: hosts the database of accounts and stories, in Frankfurt, Germany.
- Google Sign-In: confirms who you are when you sign in with Google.
- Google Workspace (Gmail): receives and answers your emails to us, with whatever you choose to
  send.
- Google Play: distributes the app and, once purchases are offered, takes payments. We never receive
  your full card details.
- Professional advisers or authorities, only where a legal obligation or a legal claim requires it.

- Neon privacy notice: https://neon.com/privacy-policy
- Google privacy notice: https://policies.google.com/privacy

## 6. Processing outside the EU

Our database and servers are in the EU, but some processing can happen elsewhere: Vertex AI runs on
Google’s global endpoint, and our providers’ support and security teams may work from outside the
European Economic Area.

Such transfers follow Chapter V of the GDPR: a European Commission adequacy decision, such as the
EU–US Data Privacy Framework for certified recipients, or the Commission’s Standard Contractual
Clauses with any measures needed. Write to lucidsaga.support@garbar.tech for the mechanism that
applies to your data and a copy of the safeguards.

## 7. How long we keep it

- Your account, stories, pictures, audio and credits: as long as you keep them. Deleting a story
  deletes its scenes, pictures and audio. Deleting your account deletes everything in it, at once.
- Reports: until you delete the reported story or your account.
- Dictation recordings: not kept. Each is used for its one request.
- Logs: 30 days. Sign-in protection counts expire on their own after a short time.
- Your emails to us: while we handle your request and, where needed, for as long as a complaint or
  legal claim about it could be brought.
- Purchases, once offered: the records the law requires, such as six years for Spanish commercial
  records and generally four for tax, with restricted access.

Our database’s restore history keeps deleted data for our provider’s restore window, and then it’s
gone; backups aren’t edited when you delete something. Copies you exported yourself are yours to
remove. You can ask us which periods apply to your data.

## 8. Our website and cookies

Our website has no accounts, analytics, advertising or tracking. It opens in your browser’s language
when that is English, Spanish or Catalan, and in English otherwise; it never uses your location for
this.

If you pick a language in the language switch, a cookie named lang remembers it for up to a year, so
the site opens in that language next time. It’s a preference you asked for, used for nothing else.
You can delete it in your browser at any time.

Our hosting keeps request logs, with the time, the page, your browser and your network address, for
30 days, to keep the site running and secure.

## 9. Permissions and security

The app asks for the microphone the first time you tap the mic, and listens only while it shows it
is listening; typing always works. You can change permissions in your phone’s settings.

All traffic is encrypted. Passwords are stored only as salted hashes and sign-in tokens as one-way
hashes, our own keys live in Google Secret Manager, signing out ends a device’s sign-in at once, and
repeated wrong passwords are slowed down. Lucid Saga isn’t end-to-end encrypted: our servers and
providers process your stories in order to write them.

## 10. Your rights

In the app you can download everything we hold about you (Account → Privacy and data → Export my
data), delete your account and everything in it (Account → Privacy and data → Delete account), and
correct your name and preferences in Account.

You can also ask us for access, correction, erasure, restriction or portability of your data, and
object to processing based on our legitimate interests. Where we rely on your consent, you can
withdraw it.

Write to lucidsaga.support@garbar.tech saying which account and which right. We check that the
account is yours in a proportionate way, and never ask for your password or card number. We answer
within one month; for complex or numerous requests we may take up to two more months, and we’ll tell
you why within the first. Requests are free.

You can complain to the Spanish Data Protection Agency (AEPD), or the authority where you live,
without contacting us first.

- Delete your account: https://lucid-saga-web-528988811295.europe-west1.run.app/en/delete-account
- AEPD: your rights and how to complain: https://www.aepd.es/derechos-y-deberes/conoce-tus-derechos

## 11. Age and changes

You must be 16 or older to sign up, and the app asks your birth date. Players under 17 get only Teen
stories. If we learn that someone under 16 has signed up, we delete the account. If you think a
younger person has one, write to us.

We’ll update this policy when the game or its use of data changes, show the date each version takes
effect, and tell you in the app before a change that matters takes effect.

You can also read this policy on our website:
https://lucid-saga-web-528988811295.europe-west1.run.app/en/privacy

*In force since 8 November 2026.*

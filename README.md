# Flight Narrator

A small **World of Warcraft Classic** addon that **reads a line out loud while you fly**.

The long-term goal is a commentary track for flight paths — the Tour de France idea, in Azeroth. What is in this repository right now is the **narrator, rebuilt from scratch and working**: the speech call is the client's own, the voice is a shipped neural-voice library, and it speaks by itself when a flight starts. The writing it reads is still a demo of two lines. See [Current status](#current-status).

## Quick start (WoW Classic)

Four steps. Everything else in this file is background.

1. **Install the folder** here, keeping the folder name exactly `FlightNarrator`:

   ```
   World of Warcraft\_classic_era_\Interface\AddOns\FlightNarrator\
   ```

   `_classic_era_` is the Classic Era folder; each other flavour (Anniversary/BCC, Titan Reforged, Cata, Mists) installs into its own `_classic_*` folder — see [Compatibility](#compatibility).

2. **Turn Text to Speech on, if you want the client's voice too.** The shipped narration is an ordinary sound file and plays without it; the client's speech is what `/fn <text>`, `/fn voices` and any line with no clip use. Go to **Options → Accessibility → Text to Speech** and enable voice output. That master switch is the `textToSpeech` CVar — account-wide, and off by default — which makes it the number one reason a narrator stays silent.

   > **Important:** the switch is account-wide, but the settings behind it are not. Classic keeps voice, rate, volume and the chat-type toggles **per character** (`TTSUseCharacterSettings`, default on), so an alt can stay silent with speech enabled — volume 0, or a voice that is not installed. `/fn diag` prints what the client reports for the character you are actually on.

3. **`/reload`** (or log in), and check the AddOns list: Flight Narrator must be ticked, and must **not** be marked "out of date" — an out-of-date addon does not load at all, and then nothing you type will do anything. If it is flagged, tick *Load out of date AddOns*, or see [Compatibility](#compatibility).

4. **Run `/fn`.** You should hear the test sentence, and see this in chat:

   ```
   Flight Narrator: playing the shipped clip voice\frFR\test.mp3 (no Text to Speech involved).
   ```

   Then run **`/fn flight`**: that is the call a real flight makes, so you hear a flight line without leaving the ground.

If you hear nothing, run **`/fn diag`** and follow [Troubleshooting](#troubleshooting-i-dont-hear-anything). The addon never fails quietly: when speech is impossible it prints the text in chat instead, so a problem always looks like something.

## Usage

| Command | What it does |
| --- | --- |
| `/fn` or `/fn test` | Speaks the fixed test sentence out loud. |
| `/fn <text>` | Speaks `<text>` out loud — e.g. `/fn Above you, the spires of Dalaran.` |
| `/fn voices` | Lists every voice the client can speak with, marking the one the narrator uses. |
| `/fn voice <number>` | Switches the narrator to that voice and speaks a sample — see [Choosing a voice](#choosing-a-voice). |
| `/fn clip <key>` | Plays a narration clip shipped with the addon, if one has been rendered. |
| `/fn flight [destination]` | Pulls the flight trigger by hand — the same call a real flight makes, so you can hear the flight line without flying. |
| `/fn trace` | Turns the flight watch on or off: every signal and every taxi-state check is printed, which is how a flight that does not announce itself is diagnosed. |
| `/fn diag` | Prints a full diagnosis — see [Troubleshooting](#troubleshooting-i-dont-hear-anything) for how to read it. |

`/flyn` and `/flightnarrator` are the same command.

Every command reports back in chat, prefixed with `Flight Narrator:`. A successful call prints which call was used (the client's own helper first, then the modern `SpeakText`, then the legacy one), and then either `the client started reading it aloud.` or the reason it did not.

Nothing is saved in this build: the manifest still declares `FlightNarratorDB`, but no code writes to it yet, so every command is self-contained and stateless. One exception, and it is deliberate: `/fn voice <number>` writes the voice slot you name, through the client's own voice API — see [Choosing a voice](#choosing-a-voice). Everything else in your client settings is only ever read — see [Other addons and the client's own Text to Speech](#other-addons-and-the-clients-own-text-to-speech). Flight detection keeps no state between sessions either: it holds the destination of the taxi that was clicked and one flag for *this flight has been announced*, and both are gone on landing.

## Choosing a voice

Two commands. Everything else is the operating system's business.

| Command | What it does |
| --- | --- |
| `/fn voices` | Lists every voice this client can speak with, marking the one the narrator uses. |
| `/fn voice <number>` | Switches the narrator to that voice and speaks a sample, so you hear the change immediately. |
| `/fn voice <number> alternate` | Fills the client's *alternate* slot instead — the slot it uses for system messages. |
| `/fn voice <name>` | The same, for voices whose names you would rather type than count. |

These go through `C_TTSSettings.SetVoiceOption`, the call the client's own voice dropdown makes, in the same slot. The Options panel, `/fn diag` and the narrator therefore cannot disagree about which voice is selected, and the choice is saved with your character settings — the client's own `tts-cache-character.txt` — like every other Text to Speech setting. `/fn voice` is the only setting this addon ever writes.

**Where the voices come from.** Not from the game, and not from this addon: they are the Text to Speech voices installed in your operating system, and the client lists whatever it finds. `/fn voices` is authoritative on your machine and this file is not, because that list is different everywhere. It is also why the client's own panel puts a **More voices** link (`TEXT_TO_SPEECH_MORE_VOICES`) next to its dropdown: adding a voice is an operating system job. On Windows that is **Settings → Time & Language → Speech → Voices**. A machine carrying only the stock SAPI 5 voices sounds like 2010 for the simple reason that those voices date from it.

**Natural voices, and what no addon can do.** The neural "Natural" voices Windows 11 offers are built for Narrator and for other speech APIs, and in practice do not appear in the list this client receives. Nothing inside the game can change that either: an addon is Lua and data files, so it cannot install a voice, ship a speech engine, call a service while you play, or add an entry to that list. What an addon *can* do is ship the audio.

### Packaging a voice with the addon

If the voice should be part of the addon — natural, identical on every machine, and independent of the client's language — pre-render the narration and ship the clips:

```lua
PlaySoundFile("Interface\\AddOns\\FlightNarrator\\voice\\frFR\\ratchet.mp3", "Dialog")
```

`PlaySoundFile` plays `.ogg` and `.mp3` files from an addon's own folder (the file has to exist before you log in or reload). Shipping sound is allowed and normal: the big voice addons, `VoiceOver` and `DialogueUI` among them, are built exactly this way. `tools/Render-VoiceClips.ps1` renders the lines in `tools/lines.txt` with a neural voice into `voice/<locale>/`, one clip per line key, and the narrator plays a clip when one exists and falls back to the game's Text to Speech when it does not. Which voice says the words stops being the same question as what the words are. The shipped library is rendered with **`fr-FR-HenriNeural`** into `voice/frFR/`, and the folder read at play time is the client's own locale first, then `NARRATION_LANGUAGE` in `FlightNarrator.lua` — set to `frFR`, the language the library is written in. A French client therefore hears French, a client set to any other language still hears the narration instead of silence, and that one line plus a rendered folder moves the whole library to another language.

The clips are rendered a little slower than the voice's own pace: `-Rate`, **-15%** by default, because narration that plays over a flight has to leave room for the flight. That pace is baked into the audio, so it is a property of the voice — change `-Rate` and re-render with `-Force`, and the same line comes back at a different speed. The client's own voice, which speaks only for a key with no clip, keeps its own rate setting: the addon reads `GetSpeechRate` and never writes it, so the client's own **`/tts rate <n>`** is what changes that one, and `/fn diag` prints the value and the scale it belongs to.

The trade-offs, plainly:

- **Only rendered lines are spoken in that voice.** Free text (`/fn <text>`) still goes through the client's own voice. For this addon that is a small limit: flight narration is a fixed library of lines, which is the next thing to write anyway.
- **Size.** A few seconds of mono speech is tens of kilobytes, so a full zone library is a few megabytes in the addon folder. The clips are generated, so they are ignored by git and rebuilt with one command; commit them only if you intend to hand the folder to somebody else.
- **The narration language becomes your choice**, which is the one thing the operating system cannot give you: a French library with a French neural voice works on an English client, and the reverse.
- **No clip, no voice: it falls back.** A missing clip is never silence — the line is read by the client's voice instead.

## Troubleshooting: "I don't hear anything"

The addon prints every outcome and retries once by itself, so each row below has a distinct, visible symptom.

| What you see | What it means | What to do |
| --- | --- | --- |
| Nothing at all — no `loaded` line in chat after logging in, and `/fn` does nothing | The addon is not running | AddOns list: is it ticked? Is it "out of date"? Is the folder named `FlightNarrator`, with the `.toc` and `.lua` inside it? |
| `no Text to Speech voice available` (then the text, printed) | No voice is installed, or this character's settings give the speech system nothing to use | **Options → Accessibility → Text to Speech** and check the voice, then `/reload`. On Windows also check that a voice is installed in the OS speech settings. |
| `playback failed (<StatusCode>), retrying with modern:` | The client rejected the first call | Nothing yet — this is the addon recovering by itself. If the next lines are `speaking with modern: …` and `started reading it aloud`, the narrator works. |
| `playback failed (<StatusCode>). Showing the text instead:` | Every call form this addon can use was rejected | Copy the status name (`InvalidArgument`, `VoiceUnavailable`, …) and the `/fn diag` output into a bug report. |
| `this client has no speech API` | `C_VoiceChat.SpeakText` does not exist on this build | Wrong client family, or an interface number that does not match your flavour — see [Compatibility](#compatibility). |
| `the client started reading it aloud.` but you hear nothing | The client believes it spoke | Check game and system volume and the output device: the client plays Text to Speech through its own audio. There is also a receipt: the client writes every utterance it generates to `Speech\VoiceSpeak_Utterance_<voice>_<volume>_<rate>_*.wav` in its own folder, so a file whose name says volume `0` containing nothing but zero samples is how the argument-order bug behind version 0.3.0 was found in the first place. |
| `speaking with modern:` where you expected the helper | `TextToSpeech_Speak` was not loaded, so the addon used the fallback form, and the client accepted it | The narrator works. Nothing to fix. |
| A clip plays but the narrator sounds rushed | The pace of a shipped clip is whatever it was rendered at | Re-render slower, for example `tools\Render-VoiceClips.ps1 -Voice fr-FR-HenriNeural -Rate -25% -LinesFile tools\lines.fr.txt -Force`, then `/reload`. |
| The voice you hear is the *client's*, not the shipped one (`speaking with …` instead of `playing the shipped clip …`) | There is no clip for that key, or the client did not see the folder | That fallback is by design. If you expected a clip, check the folder `/fn diag` prints, and remember the client only sees files that existed when it loaded. |
| The fallback voice is too fast (you see `speaking with …`) | Text to Speech speed is the character's own setting, and this addon never writes it | `/tts rate -20`, or the slider in **Options → Accessibility → Text to Speech**. `/fn diag` prints the current rate and its range. |
| No `a flight begins` line when you take a flight | The trigger is the taxi state itself (`UnitOnTaxi`), asked on the taxi click and after every signal that could mean a flight is starting, and the addon has to be loaded before the flight starts | Run `/fn trace`, then take the flight: the `[watch]` lines say which signals arrived and what the taxi state was at each one. `/fn diag` reports the `taxi hook` and `on a flight right now`. `/fn flight` proves the rest of the path: if that speaks, detection is the only thing missing. |
| `a flight begins.` with no destination, on a client that names its taxi nodes | `TaxiNodeName` did not answer for that slot | Harmless: the line is spoken either way. Worth a `/fn diag` note in a bug report. |

`/fn diag` is the tool for all of this. It prints the client build and interface number, which speech APIs the client actually has, the `textToSpeech` setting (with a hint about per-character settings when it reads as off), the voice in each slot, the rate and volume it will use, how many voices the client reports (`/fn voices` lists them), the events it is watching, what the flight detection is built on — the taxi state, the taxi hook, every signal and whether this client answered it, and whether the player is on a flight right now — and the rate in the client's own scale.

## The idea

Think of the Tour de France: the peloton rolls through a village, and the commentators fill the dead air with everything worth knowing about it — its history, its landmarks, the people who lived there. Flight Narrator wants to do the same for World of Warcraft. When you hop on a flight path, it should tell you something about the land you are passing over or flying into.

Flight paths in WoW are long, quiet, and full of story that nobody reads. Whole zones drift by under your gryphon — a ruined keep, a bridge named after a dead king, a swamp where something terrible once happened — and the game never says a word about any of it. This addon is meant to be that missing commentary track:

> *"You are leaving Stormwind behind now, heading north toward Elwynn Forest — the old heartland of the Alliance, where the Defias Brotherhood once cut a bloody path through the king's own woods..."*

The narration should match **where you are going**, not just that you are flying. Board a flight to a new zone and you get its story; cross into another region mid-flight and the commentary follows along.

## Current status

The vision above is the destination; this repository is at the second waypoint. **Version 0.3.3 narrates flights: a voice of its own, and speech that starts when a flight does.** The writing it reads is still a demo of two lines.

What it does today:

- **Speaks on its own when a flight starts**, once per flight: the taxi click names the destination, and the client's own taxi state is the trigger — see [Flight detection](#flight-detection). `/fn flight` pulls the same trigger by hand, and `/fn trace` shows the watch working.
- **Has its own voice.** The narration is rendered with `fr-FR-HenriNeural` into `voice/frFR/` and played with `PlaySoundFile`, so it sounds the same on every machine, needs nothing installed, and works on any client language. `/fn clip <key>` plays one directly.
- Speaks out loud through the game's own Text to Speech when a line has no clip, or on demand: `/fn` says a fixed test sentence, `/fn <text>` says whatever you type.
- Speaks through the client's **own** speech helper, `TextToSpeech_Speak`, which is the path its Play Sample button takes; a real voice table, the character's rate and a non-zero volume are handed over, which is what an earlier build got wrong. The raw `SpeakText` calls are kept as fallbacks, in the client's own order, for a client where that helper is not loaded.
- Reports what the client actually did: whether playback started, and if it failed, with which status code, retrying with the next call form before giving up.
- Prints the text in chat whenever it cannot speak, so a silent client is always visible, never mysterious.
- Self-checks on request with `/fn diag`.
- Lists the voices this client can speak with (`/fn voices`) and switches between them (`/fn voice <number>`), through the same call the client's own voice dropdown makes — see [Choosing a voice](#choosing-a-voice).

What it does **not** do yet:

- It does not know zones yet: every flight speaks the one destination line there is, keyed `ratchet`, whatever the taxi click reported. Chat says which destination it detected, so the gap is visible rather than silent.
- It has no lore database: `tools/lines.fr.txt` carries two lines, one of them the test sentence.
- It does not queue announcements during a long flight, and does not speak for the zones it crosses on the way.

In short: the narrator works, it is observable, and it now speaks by itself at the right moment. The interesting work — actually writing the lore, keyed to zones and destinations — is what comes next.

## Flight detection

A flight is announced once, when it starts. Classic Era has no event that says "a taxi lifted off", so the trigger asks the client the one question that has a real answer — `UnitOnTaxi("player")` — and keeps asking it for a short while after anything that could mean a flight is starting.

| Signal | What it contributes |
| --- | --- |
| `TakeTaxiNode`, hooked rather than replaced | Names the destination. It is the click on the flight master's map, and the slot it is called with is the same index the client's own taxi buttons use, so `TaxiNodeName(slot)` answers with "Stormwind City". A click opens the watch below: it is a question, not an answer. |
| `UnitOnTaxi("player")` | The answer. Era's own interface asks it the same way (`VehicleLeaveButton`, `PaperDollFrame`, `UIParent`), and it is what separates a flight from a cinematic, a summon or a fear — those take control away too, and stay silent. |
| `TAXIMAP_CLOSED`, `UNIT_FLAGS`, `PLAYER_ENTERING_WORLD`, `PLAYER_CONTROL_LOST`, `PLAYER_CONTROL_GAINED` | Each one opens the same watch and asks the same question: the map closing as the taxi is taken, a unit flag, the loading screen a long flight crosses (which is also how a `/reload` in mid-air is noticed), and the loss-of-control pair on clients that fire it. |
| The watch | For 20 seconds after a click or a signal, the taxi state is asked every 0.5 seconds. A flight turns it on within a tick or two of the click; a refused taxi never does, and a destination that never became a flight is dropped when the watch runs out. |

**Why not wait for `PLAYER_CONTROL_LOST`?** Because that was the 0.3.2 trigger, and on Classic Era it is never fired for a taxi: era's interface does not register it at all (the later flavours do), while the registration still succeeds, since this client is a modern engine wearing a Classic skin. The addon armed a wait for an event that never came and no flight was ever announced. A registration is not a promise — which is why `/fn diag` prints what each signal answered.

**Why not announce on the click alone?** Because a taxi the client refuses — no money, no route — costs no flight, and a narrator that announces flights you never took is worse than one that stays quiet for a second. The watch is what makes the click safe to trust.

**Why `TAXIMAP_CLOSED` and not `TAXIMAP_OPENED`?** Because opening the map is not flying: it is a window, closed again with Escape. The *closing* is the moment the taxi is taken, which is why that one is a signal and the other is not.

**Why once, at the start, and not mid-flight?** Because a multi-leg route stops between legs without ever handing control back, so the flight really is one continuous thing, and one line per flight is what the commentary wants for now. The zone-by-zone version is on the [Roadmap](#roadmap).

That is all the state the addon keeps: the destination of the taxi that was clicked, whether the flight it is in has already been announced, and when the watch runs out. None of it survives a session, and none of it is written to `FlightNarratorDB`.

**Trying it without flying:** `/fn flight` makes the same call the event makes, and `/fn flight <destination>` makes it with a name. When a flight does not announce itself, **`/fn trace`** prints the watch as it happens: which signal arrived, what the taxi state said, and what the addon did about it.

## How it works

Text to Speech in WoW lives in `C_VoiceChat`, and this one call has changed shape mid-life, which makes it easy to get wrong. Until **patch 12.0.0**, whose note reads *"Removed `destination`, added `overlap` arguments"*, the call was:

```lua
C_VoiceChat.SpeakText(voiceID, text, destination, rate, volume)   -- pre-12.0.0, and Classic Era before 1.15.9
```

From **12.0.0** onwards it is:

```lua
C_VoiceChat.SpeakText(voiceID, text, rate, volume, overlap)       -- 12.0.0+, and Classic Era 1.15.9+
```

The two forms are dangerously similar, and the failure mode of mixing them is silence: hand the classic argument list to a client built from the Modern UI — which Classic Era is, from 1.15.9 — and `1` lands in `rate` while `volume` becomes `0`. The client accepts the call, reports that playback started, and synthesises nothing at all. That was this addon's bug, and the file the client wrote for it measures a peak of 0 across 75440 samples: a receipt, not a theory.

So the addon does not guess and hope. `Speak()` tries, in order:

1. **the client's own helper**, `TextToSpeech_Speak(text, voice, neverQueue)` — the path its Play Sample button takes, which cannot disagree with that client about argument order, and which applies the character's own voice, rate and volume;
2. **the modern `SpeakText`**, `(voiceID, text, rate, volume, false)`;
3. **the legacy `SpeakText`**, `(voiceID, text, destination, rate, volume)`.

A form is only tried when the previous one is missing or was rejected — the failure is remembered by name, not by a boolean — and `VOICE_CHAT_TTS_PLAYBACK_FAILED` walks the same chain before the text is finally printed in chat.

The rest of the correctness work:

- **Voice.** `0` is not a valid voice. The helper path hands the client the voice *table* that `TextToSpeech_GetSelectedVoice(Enum.TtsVoiceType.Standard)` returns — Blizzard's own helper, which already falls back to the first installed voice when the saved setting is stale. The raw `SpeakText` path resolves an ID through `C_TTSSettings.GetVoiceOptionID` and then through the first entry of `C_VoiceChat.GetTtsVoices()`, and refuses to guess: if nothing resolves, it says so and prints the text rather than calling the client with an unusable ID.
- **Rate and volume.** Volume is the player's own `C_TTSSettings` value (`GetSpeechVolume`, a 0–100 scale on which 0 is mute), falling back to `100` so it can never be silently zero. Rate comes from `GetSpeechRate`, or the client's normal speed if that cannot be read.
- **Destination, and why it is the trap.** `Enum.VoiceTtsDestination` runs `0 = RemoteTransmission`, `1 = LocalPlayback`, and so on, so `1` is the value that reads the text to you and nobody else — *in the legacy form only*. Era 1.15.9 has no `destination` argument at all: there the third argument is `rate` and the fourth is `volume`, which is how a `1` and a `0` became a mute button.
- **Events.** `VOICE_CHAT_TTS_PLAYBACK_STARTED`, `_FINISHED` and `_FAILED` are watched on a hidden frame so the addon can report the outcome of a call instead of firing and forgetting. Each event is registered defensively, since not every client version knows all of them.

## Compatibility

This build targets **Classic Era from 1.15.9**, which is built from the Modern 12.0.0 UI and therefore takes the modern `C_VoiceChat.SpeakText(voiceID, text, rate, volume)` form — the form supplied by the client's own helper wherever that helper is loaded. Older clients (Era before 1.15.9, and anything before 12.0.0) are covered by the legacy fallback, and the addon reports in chat which call it used, so the answer is never a guess.

The manifest declares the interface of the client this build targets, on one line:

```
## Interface: 11509
```

For another flavour, that number is the only thing to change:

| Client | Interface number to declare | Latest, per the wiki at the time of writing |
| --- | --- | --- |
| Classic Era (Vanilla) | 11509 | 11509 (1.15.9) |
| Burning Crusade / Anniversary | 20505 | 20506 |
| Wrath / Titan Reforged | 30403 | 30405 (Wrath), 38002 (Titan) |
| Cataclysm | 40402 | 40402 |
| Mists | 50500 | 50504 |
| Retail | not declared | 120100 |

> **Important:** an addon whose interface number is **older** than the client's build is flagged "out of date" in the AddOns list, and is **not loaded at all** unless *Load out of date AddOns* is ticked. If the addon appears to do nothing — not even a `loaded` message in chat after logging in — this is the first thing to check. `/fn diag` prints the interface number of the client you are actually running, to compare against the first column.

The addon is plain Lua with no libraries and no Blizzard UI dependencies, which is why it travels across flavours; the only version-sensitive parts are the speech call branch and the voice list, both described in [How it works](#how-it-works). Version 0.3.0 also drops the invented `## Interface-Classic:` / `-BCC:` / `-Wrath:` / `-Cata:` / `-Mists:` lines the manifest used to carry: the client ignores directives it does not know, so they did nothing except mislead anyone reading them.

## Other addons and the client's own Text to Speech

Everything that speaks in this game goes through the same call, so the overlap worth worrying about is duplicated **speech**, not conflicting code. Two things are worth knowing.

**The client already covers the settings.** Options → Accessibility → Text to Speech is where voice output is switched on and where the voice, rate and volume are chosen — `C_TTSSettings` underneath, via `SetVoiceOption`, `SetSpeechRate`, `SetSpeechVolume`, and the per-channel and per-chat-type toggles the client uses to decide what it reads by itself (`GetChannelEnabled`, `SetChatTypeEnabled`). Those settings are saved per character (`GetCharacterSettingsSaved`), so an alt can stay silent even though the account-wide switch is on. Blizzard also ships **Speak for Me** (`C_VoiceChat.IsSpeakForMeActive`), which voices text on your behalf rather than only to your own speakers.

> **This addon writes exactly one of those, and only when asked.** `/fn voice <number>` fills the voice slot you name through `SetVoiceOption`, the same call your client's own voice dropdown makes — see [Choosing a voice](#choosing-a-voice). Everything else is read-only: rate and volume come from `GetSpeechRate` and `GetSpeechVolume`, and the addon never calls `SetSpeechRate`, `SetSpeechVolume`, `SetCVar` or `StopSpeakingText`. It cannot mute anyone or cancel another addon's line — and it declares `FlightNarratorDB` without ever writing to it.

**Anything that reads chat, whispers or events out loud is doing what this addon does** — one line at a time, through the same `C_VoiceChat.SpeakText`. So a clash looks like two voices talking over each other, never like an error message.

| Situation | What to do |
| --- | --- |
| Another addon already narrates zone changes, flight paths or chat | Run one narrator, not two. Silence the other from its own settings — this addon has no switch that reaches it. |
| The client itself reads every chat line | That is the Accessibility chat toggles, not an addon. Narrow them to the channels or chat types you actually want spoken. |
| Two lines start at once and one is cut off | Speech is handled by the client, not the caller. The modern `SpeakText` form takes an `overlap` flag, and the client's own helper takes two (`neverQueue` and `allowOverlappedSpeech`); this addon passes `neverQueue = true` so a flight line is spoken when it happens instead of queueing behind chat, and leaves overlap alone. `C_VoiceChat.StopSpeakingText()` is how a caller cancels speech; another addon may call it and truncate this addon's line, and this build does not call it back. |
| The narrator speaks during a flight and you wanted quiet | Flight detection is on in 0.3.3 and there is no switch for it yet | `/fn` and `/fn flight` are the manual paths; the real one fires when a taxi starts. Note that silencing the client's Text to Speech leaves the shipped clips audible, because they are not speech. A settings switch is on the [Roadmap](#roadmap). |

One more consequence of the shared call: the `VOICE_CHAT_TTS_PLAYBACK_*` events are client-wide, so `STARTED` fires for speech this addon never requested — the client reading chat, another addon, or Speak for Me. The addon therefore never claims those events as its own: it reports only on the call it just made, inside a short window, and ignores everything else.

## Roadmap

Roughly in the order it makes sense to build:

1. ~~**Bring back flight detection.**~~ Done in 0.3.2, fixed in 0.3.3: `TakeTaxiNode` names the destination, and the taxi state (`UnitOnTaxi`), asked on every signal that could mean a flight is starting, is the trigger — see [Flight detection](#flight-detection).
2. **Zone-aware narration.** Turn the destination the taxi hook already resolves into a library key, so a flight to Stormwind speaks for Elwynn instead of the demo line.
3. **A lore library.** Ship community-written texts keyed by zone and destination, in the spirit of the Tour de France commentator: a couple of sentences per place, read once as you leave or arrive.
4. **Mid-flight updates.** Longer flights cross borders. Announce again when the character enters a new zone mid-flight, instead of going silent for three minutes.
5. **Variation.** Several lines per zone, so a route you fly every day does not become a catchphrase.
6. **Localisation.** All of the above in languages other than English — with the shipped-clip route in [Choosing a voice](#choosing-a-voice) this becomes a rendering job rather than a coding one.
7. **A voice of its own.** Render the lore library with a neural voice and ship the clips, so the narrator sounds the same on every machine and in any client language.
8. **Optional extras.** Interrupting the narration, per-character settings, and maybe a voice chosen per faction or per zone.

Contributions to the lore library — especially short, evocative, accurate writing — are the most valuable thing anyone can bring to this project, well before any code.

## Repository layout

```
FlightNarrator.toc   Addon manifest: metadata, supported client versions, saved variables.
FlightNarrator.lua   The whole addon: the speech call, flight detection, TTS diagnostics, slash commands.
voice/frFR/          The shipped narration clips, one per line key (generated, and ignored by git).
tools/lines.fr.txt   The narration lines, key|text, in French: the library itself.
tools/lines.txt      The same keys in English, for rendering an English library.
tools/Render-VoiceClips.ps1   Renders the lines into clips with edge-tts.
tools/text_to_mp3.py   Turns one piece of text into one MP3 clip (edge-tts, OpenAI, or ElevenLabs).
tools/SmokeTest.py   Loads the addon into embedded Lua and drives the commands and the flight events.
```

## Generating narration audio (tools/text_to_mp3.py)

`tools/text_to_mp3.py` turns one piece of text into one MP3 narration clip, in a
deep, slow storyteller voice. It is the single-text companion to
`tools/Render-VoiceClips.ps1`, and can use three engines with `--backend`:

| Backend | Needs | Default voice (deep male) | Notes |
| --- | --- | --- | --- |
| `elevenlabs` | `ELEVENLABS_API_KEY` | `Antoni` (or any voice ID) | Most natural French intonation; a `[Lentement]` tag works on `eleven_v4`. |
| `openai` | `OPENAI_API_KEY` | `onyx` | Steer intonation with a natural-language `--instructions` prompt. |
| `edge` | none (free) | `fr-FR-HenriNeural` | Works out of the box; lower quality. |

API keys are read from a `.env` file at the repo root (git-ignored) or from the
environment. `--backend auto` (the default) uses ElevenLabs/OpenAI when a key is
present and falls back to `edge`, so the tool always works:

    OPENAI_API_KEY=sk-...
    ELEVENLABS_API_KEY=sk-...

    python -m pip install edge-tts          # only needed for the edge backend

    # Free, no key:
    python tools\text_to_mp3.py "Test du narrateur." -o voice\frFR\test.mp3

    # OpenAI, deep storyteller voice:
    python tools\text_to_mp3.py --backend openai --voice onyx --text-file narration.txt -o voice\frFR\ratchet.mp3

    # ElevenLabs, "Martin Dupont" voice, reading slowly (tag in the text):
    python tools\text_to_mp3.py --backend elevenlabs --voice a5n9pJUnAhX4fn7lx3uo --model eleven_v4 --text-file narration.txt -o voice\frFR\ratchet.mp3

The text is read from the argument, `--text-file <path>`, or stdin, and is read
whole, so for a draft file like `Ratchet.txt` (which also holds a title and
metadata) pass just the narration paragraph. To make ElevenLabs read slowly,
prefix the text with a square-bracket tag on the v3/v4 models, for example
`[Lentement]` or `[Lentement, voix grave et posee de narrateur]`. List your
ElevenLabs voices and their IDs with `GET https://api.elevenlabs.io/v1/voices`
(header `xi-api-key: <key>`); a library voice like "Martin Dupont" needs a paid
plan to be used through the API.

## Development notes

- **Language and style:** plain Lua, no frameworks. Locals for internal state, `DEFAULT_CHAT_FRAME:AddMessage` for user-facing output, `|cff33ff99Flight Narrator:|r` as the chat prefix.
- **No build step, no dependencies.** Edit the `.lua` and `/reload` in game.
- **Testing:** drop the folder in `World of Warcraft\_classic_era_\Interface\AddOns\`, enable it in the AddOns list, tick **Options → Accessibility → Text to Speech**, log in, and run `/fn`. Follow up with `/fn diag` if you hear nothing.
- **Tooling, all optional:** `tools/Render-VoiceClips.ps1` renders narration clips (needs Python and `edge-tts`); `tools/SmokeTest.py` loads the addon into an embedded Lua runtime with mocked WoW APIs and drives every slash command and every flight event (needs Python and `lupa`). The second one is worth the dependency: it catches the class of mistake that otherwise only appears in game, such as calling a function that is not in scope yet.
- **What "working" looks like:** chat shows `playing the shipped clip voice\frFR\ratchet.mp3 (no Text to Speech involved).` and you hear it. For a key with no clip it shows `speaking with the client's own helper: TextToSpeech_Speak(text, voice) ->` and then `the client started reading it aloud.` — and you hear the sentence. Anything else (a status code, or the text printed back) is the diagnosis, not a mystery.

## License

This repository does not currently include a license file, so no license is granted by default. If you intend to reuse or redistribute the addon, ask the author first.

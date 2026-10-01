# Flight Narrator — Lore Library Design

This file records the design conclusion for turning Flight Narrator from a
destination-announcer into a **rotating lore library**: deep, curated Warcraft
lore that plays during a flight, with a new piece each time you repeat a route.

## The vision

- Not "you are flying to Stormwind" — that is not interesting.
- Deep lore the player does not already have, served while they are otherwise
  just flying and listening.
- The same travel done ten times should surface ten different pieces of lore.

## The core decision: pre-rendered audio, not a live voice reader

There is no way to ship a "voice reader" (a speech engine) inside a WoW addon.
The addon sandbox blocks it on three independent levels:

1. **No native code.** An addon cannot load a `.dll`/`.exe`, spawn a process, or
   use FFI — so a compiled TTS engine has no entry point.
2. **No network/service.** It cannot call an online TTS API at play time.
3. **No raw-audio output.** Even a pure-Lua synthesizer would have nowhere to
   send its samples. The client only offers `PlaySoundFile` (a file that already
   exists when the client loads) and the client's own OS Text-to-Speech.

The client's own TTS is rejected for this goal: the base Windows voices are not
good enough for lore narration.

Therefore the only path to a consistent, high-quality in-game voice is **shipped
audio**.

The reframe that makes this acceptable: a live reader is only needed for
*dynamic* text (a destination name, a chat line, a player name). This project's
content is *static, pre-written lore*, so pre-rendered audio is not a compromise —
it is the correct tool. The only cost is disk.

## Size budget

Speech is extremely compressible. `edge-tts` already encodes at roughly
**40 kbps mono**; the proof is in the repo: `voice/frFR/elwynn.mp3` is **74 KB**
for a full ~15-second lore sentence.

| Bitrate (mono) | Per minute of speech |
|----------------|----------------------|
| ~40 kbps (edge-tts default) | ~300 KB |
| 48 kbps OGG Vorbis | ~360 KB |
| 32 kbps (aggressive, still clear) | ~240 KB |

| Lore clips | Average length | Approx. total |
|-----------|----------------|---------------|
| 100 | 1 min | ~30 MB |
| 200 | 1 min | ~60 MB |
| 300 | 1 min | ~90 MB |
| 500 | 1 min | ~150 MB |

A 60–150 MB library is normal for a voice addon (the big voice addons ship
gigabytes) and buys a large amount of "something new each time".

Variety does **not** multiply storage: the lore is a **rotating pool** filtered
by zone/region, not one unique clip per route. The same pool serves every
flight, so variety compounds instead of scaling with routes.

## The work

1. **Writing (the real effort).** Short, evocative, accurate lore lines. This is
   the irreplaceable human part.
2. **Rendering.** Render the lines offline with a neural voice. The existing
   `tools/Render-VoiceClips.ps1` already does this; an optional ffmpeg pass can
   re-encode MP3 -> OGG Vorbis mono at ~40–48 kbps to shrink further.
3. **Selection + rotation logic (the only new code).** Pick clips by
   zone/region, rotate, and remember what has been heard.

## Selection logic plan (against the current code)

Today every flight speaks the same demo key:

- `FlightNarrator.lua` line 569: `local FLIGHT_DEMO_KEY = "elwynn"`
- `FlightNarrator.lua` line 608: `Narrate(FLIGHT_DEMO_KEY, FlightLine(destination))`

To implement the rotating library:

- Replace the single demo key with a **pool** of lore keys, filtered by the
  player's current zone/region (the destination name is already captured in
  `taxiDestination` via `TaxiNodeName`).
- **Rotate** through the pool so a route repeats only after the pool is
  exhausted.
- **Persist** what has been heard in `FlightNarratorDB` — already declared in
  `FlightNarrator.toc` line 7 (`## SavedVariables: FlightNarratorDB`) but not
  yet written by any code.
- Add a **zone-change trigger** mid-flight so long routes switch clips as the
  player crosses a border (already on the README roadmap).

## Files involved

| File | Role |
|------|------|
| `tools/lines.fr.txt` / `tools/lines.txt` | The lore text (`key|text`), the library itself |
| `tools/Render-VoiceClips.ps1` | Renders the text into `voice/<locale>/<key>.mp3` clips |
| `voice/<locale>/` | The shipped clips (generated) |
| `FlightNarrator.lua` | Speech calls, clip playback, flight detection, rotation logic (to be added) |
| `FlightNarrator.toc` | Manifest; declares `FlightNarratorDB` for persistence |

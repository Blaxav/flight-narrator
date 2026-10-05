# Flight Narrator

A **World of Warcraft Classic** addon that narrates a flight (taxi) with the zone
clips matching the route. The flight duration is cut into ~55 s slots; each slot
picks one random clip from the zones overflown during that slot, and the clips
play one after the other, each starting at the beginning of its own slot.

## Install

Copy the `FlightNarrator` folder into the addons directory, keeping the folder
name exactly `FlightNarrator`:

    World of Warcraft\_classic_era_\Interface\AddOns\FlightNarrator\

`_classic_era_` is the Classic Era folder; each other flavour (Anniversary/BCC,
Titan Reforged, Cata, Mists) installs into its own `_classic_*` folder.

Then `/reload` and make sure the addon is ticked in the AddOns list.

## Rendering the audio

The clip is rendered offline and travels with the addon as an ordinary sound
file — the only way a voice can ship inside a WoW addon.

- `tools/text_to_mp3.py` renders a single piece of text with ElevenLabs (deep
  French storyteller voice "Martin Dupont"). See its header for details.

- `tools/render_zone_audio.py` renders every narration in a `zones\<region>`
  folder to an MP3 **next to each text** with ElevenLabs (resumable; skips clips
  that already exist unless `--force`):

      python tools/render_zone_audio.py "Les Tarides"

After rendering, `/reload`: the client only sees sound files that existed when it
loaded.

## Texts

- `Ratchet.txt` — the Ratchet narration (French).
- `La-Croisee.txt` — the Crossroads narration (French).

## Travel data

The route timelines ship as `TravelData.lua`: flight durations from
`travels/**/duration.txt`, every MP3 under `zones/`, and the per-route zone
timelines rebuilt from `travels/**/steps.txt`. Each route folder lists its
unitary stops in `steps.txt` (intermediate nodes plus the destination; a direct
route has a single line); the generator concatenates the `zones.txt` of each
leg of that chain into the route's zone timeline. WoW cannot list files or read
`.txt` files at runtime, so regenerate this file after adding clips or zone
timelines:

    python tools/generate_travel_data.py

Routes with no usable leg `zones.txt` fall back to a single random clip.

## Notes

- Plain Lua, no dependencies, no build step.
- Flight detection polls the client's own `UnitOnTaxi` rather than waiting for an
  event, because Classic Era has no event that fires when a taxi lifts off.

## License

No license file is included, so no license is granted by default. Ask the author
before reusing or redistributing.

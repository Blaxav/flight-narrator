# Flight Narrator

A small **World of Warcraft Classic** addon that plays the **Ratchet** narration
clip when a flight (taxi) launches. One clip, one trigger, nothing else.

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

- `tools/Render-VoiceClips.ps1` renders the lines in a `key|text` file into
  `voice\<locale>\<key>.mp3` with a Microsoft Edge neural voice (free, no key):

      python -m pip install edge-tts
      powershell -ExecutionPolicy Bypass -File tools\Render-VoiceClips.ps1 -Voice fr-FR-HenriNeural -LinesFile tools\lines.fr.txt

- `tools/text_to_mp3.py` renders a single piece of text with a choice of backends
  (OpenAI, ElevenLabs, or Edge). See its header for details.

After rendering, `/reload`: the client only sees sound files that existed when it
loaded.

## Texts

- `Ratchet.txt` — the Ratchet narration (French).
- `La-Croisee.txt` — the Crossroads narration (French).

`tools/lines.fr.txt` holds the same lines in the `key|text` form the renderer
reads; `tools/lines.txt` is the English counterpart.

## Notes

- Plain Lua, no dependencies, no build step.
- Flight detection polls the client's own `UnitOnTaxi` rather than waiting for an
  event, because Classic Era has no event that fires when a taxi lifts off.

## License

No license file is included, so no license is granted by default. Ask the author
before reusing or redistributing.

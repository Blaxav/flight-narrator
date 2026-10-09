#!/usr/bin/env python3
"""Validate the travel <-> audio association and the generated TravelData.lua.

Runs tools/generate_travel_data.py, then checks the association algorithm
against the one shipped example route:

    travels/horde/Thunder Bluff, Mulgore/Orgrimmar, Durotar/

Expected, from the spec:
- slot maths: 224 s -> 2 slots of 112 s (standalone check of the spec example).
- duration 207 -> 2 equal slots of 103.5 s: [0,103.5), [103.5,207).
- the generated timeline covers Mulgore -> Les Tarides -> Durotar.
- every slot of that route has at least one shipped clip to choose from.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import generate_travel_data as gend

CLIP_SECONDS = 75


def compute_slots(duration):
    count = max(1, int(duration // CLIP_SECONDS))
    length = duration / count
    return [(i * length, (i + 1) * length) for i in range(count)]


def overlapping(slot, zones):
    return [z for z in zones if z["start"] < slot[1] and z["stop"] > slot[0]]


def candidates(slot, zones, audio):
    files = []
    for z in overlapping(slot, zones):
        files.extend(audio.get(z["region"], {}).get(z["subzone"], []))
    return files


def main():
    gend.main()

    out = os.path.join(ROOT, "TravelData.lua")
    assert os.path.isfile(out), "TravelData.lua was not generated"
    with open(out, encoding="utf-8") as f:
        content = f.read()

    for token in (
        "FlightNarratorData.Audio",
        "FlightNarratorData.Travels",
        "Orgrimmar, Durotar",
        "Thunder Bluff, Mulgore",
        "centaures.mp3",
        "carrefour.mp3",
        "durotan.mp3",
    ):
        assert token in content, token

    assert '["Crossroads, The Barrens"] = "La Croisée, Tarides"' in content

    audio = gend.collect_audio()
    travels, _ = gend.collect_travels()

    # Standalone spec check: 224 s -> 2 slots of 112 s.
    assert compute_slots(224) == [(0, 112), (112, 224)]

    route = travels["horde"]["Thunder Bluff, Mulgore"]["Orgrimmar, Durotar"]
    duration = route["duration"]
    zones = route["zones"]
    assert duration == 207, duration

    slots = compute_slots(duration)
    assert slots == [(0, 103.5), (103.5, 207)], slots

    regions = [z["region"] for z in zones]
    assert regions[0] == "Mulgore", regions
    assert "Les Tarides" in regions, regions
    assert regions[-1] == "Durotar", regions

    for slot in slots:
        files = candidates(slot, zones, audio)
        assert files, f"no candidate clip for slot {slot}"
        print(f"slot {slot}: {files}")

    print("TravelData.lua generated and the association spec validates.")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())

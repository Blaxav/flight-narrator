#!/usr/bin/env python3
"""Generate TravelData.lua from the travels/ and zones/ trees.

WoW cannot list files or read the .txt files at runtime, so everything the
addon needs is baked into one Lua data file:

- FlightNarratorData.Audio   : every shipped MP3, keyed by region then sub-zone,
                               each entry a path relative to the addon root
                               (e.g. "zones\\Les Tarides\\Général\\centaures.mp3").
- FlightNarratorData.Travels : every route (faction -> source -> destination)
                               with its duration and zone timeline as
                               { start, stop, region, subzone } entries. A route
                               folder carries a steps.txt (intermediate stops
                               plus the destination); its timeline is rebuilt by
                               concatenating each leg's zones.txt.

Run:
    python tools/generate_travel_data.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import generate_travels as gt  # noqa: E402  (Lua tokenizer + parser for the data files)

TRAVELS_DIR = os.path.join(ROOT, "travels")
ZONES_DIR = os.path.join(ROOT, "zones")
OUT_PATH = os.path.join(ROOT, "TravelData.lua")
DATA_EN = os.path.join(ROOT, "DataFlights.lua")
DATA_FR = os.path.join(ROOT, "DataFlights-frFR.lua")

FACTIONS = ("alliance", "horde")


def lua_string(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def rel_parts(path):
    return os.path.relpath(path, ROOT).split(os.sep)


def collect_audio():
    """Return {region: {subzone: [relative clip path, ...]}} for every MP3."""
    audio = {}
    for dirpath, dirnames, filenames in os.walk(ZONES_DIR):
        dirnames.sort()
        for name in sorted(filenames):
            if not name.lower().endswith(".mp3"):
                continue
            parts = rel_parts(os.path.join(dirpath, name))
            if len(parts) != 4:
                # Expected layout: zones/<region>/<subzone>/<file>.mp3
                continue
            region, subzone = parts[1], parts[2]
            audio.setdefault(region, {}).setdefault(subzone, []).append(
                "\\".join(parts)
            )
    return audio

def parse_zones(path):
    """Parse a zones.txt timeline into {start, stop, region, subzone} entries."""
    zones = []
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            fields = [p.strip() for p in line.split(";")]
            if len(fields) < 4:
                continue
            try:
                start = int(fields[0])
                stop = int(fields[1])
            except ValueError:
                continue
            if not fields[2] or not fields[3]:
                continue
            zones.append({
                "start": start,
                "stop": stop,
                "region": fields[2],
                "subzone": fields[3],
            })
    return zones


def read_duration(path):
    with open(path, encoding="utf-8-sig") as f:
        return int(f.read().strip())


def read_steps(path):
    """Return the non-empty lines of a steps.txt (escales + destination)."""
    with open(path, encoding="utf-8-sig") as f:
        return [ln.strip() for ln in f.read().splitlines() if ln.strip()]


def collect_travels():
    """Return ({faction: {source: {destination: {duration, zones?}}}}, stats).

    A route folder now ships a ``steps.txt`` listing the route's unitary stops
    (intermediate nodes plus the destination; a direct route has a single line)
    instead of a per-route ``zones.txt``. The zone timeline is rebuilt on the
    fly by concatenating the ``zones.txt`` of every leg of the chain
    ``[source] + steps``, each leg's intervals shifted by the sum of the
    preceding legs' durations. The concatenated timeline is then normalised to
    the route's own ``duration.txt`` so it always spans the full flight.
    """
    travels = {}
    stats = {"multi_leg": 0, "normalized": 0}
    for faction in FACTIONS:
        faction_dir = os.path.join(TRAVELS_DIR, faction)
        if not os.path.isdir(faction_dir):
            continue
        faction_table = {}
        for source in sorted(os.listdir(faction_dir)):
            source_dir = os.path.join(faction_dir, source)
            if not os.path.isdir(source_dir):
                continue
            source_table = {}
            for dest in sorted(os.listdir(source_dir)):
                dest_dir = os.path.join(source_dir, dest)
                dur_path = os.path.join(dest_dir, "duration.txt")
                if not os.path.isfile(dur_path):
                    continue
                duration = read_duration(dur_path)
                entry = {"duration": duration}

                steps_path = os.path.join(dest_dir, "steps.txt")
                steps = read_steps(steps_path) if os.path.isfile(steps_path) else []
                if not steps:
                    # No steps.txt yet: treat the route as a single direct leg.
                    steps = [dest]

                chain = [source] + steps
                if len(chain) > 2:
                    stats["multi_leg"] += 1

                raw_zones = []
                offset = 0
                total_leg = 0
                for a, b in zip(chain, chain[1:]):
                    leg_dir = os.path.join(faction_dir, a, b)
                    leg_dur_path = os.path.join(leg_dir, "duration.txt")
                    leg_dur = read_duration(leg_dur_path) if os.path.isfile(leg_dur_path) else 0
                    leg_zones_path = os.path.join(leg_dir, "zones.txt")
                    if os.path.isfile(leg_zones_path):
                        for z in parse_zones(leg_zones_path):
                            raw_zones.append({
                                "start": offset + z["start"],
                                "stop": offset + z["stop"],
                                "region": z["region"],
                                "subzone": z["subzone"],
                            })
                    offset += leg_dur
                    total_leg += leg_dur

                if raw_zones:
                    # Keep the legs' relative proportions but span the route's
                    # reported duration. A no-op when the legs already sum to it.
                    if total_leg > 0 and total_leg != duration:
                        stats["normalized"] += 1
                        scale = duration / total_leg
                        raw_zones = [
                            {
                                "start": round(z["start"] * scale),
                                "stop": round(z["stop"] * scale),
                                "region": z["region"],
                                "subzone": z["subzone"],
                            }
                            for z in raw_zones
                        ]
                    # Drop zero-length intervals (rounding can collapse a very
                    # short crossing to start == stop).
                    zones = [z for z in raw_zones if z["start"] < z["stop"]]
                    if zones:
                        entry["zones"] = zones

                source_table[dest] = entry
            if source_table:
                faction_table[source] = source_table
        if faction_table:
            travels[faction] = faction_table
    return travels, stats


def parse_flight_db(path):
    """Parse the CLASSIC section of a DataFlights*.lua file into
    {faction: {source: {destination: duration}}}."""
    with open(path, encoding="utf-8") as f:
        content = f.read()
    block = gt.extract_classic_block(content)
    return gt.Parser(gt.tokenize(block)).parse_table()


def build_node_names():
    """Return a {english_name: french_name} map built from the two data files.

    The English and French files describe the same graph with locale-only
    differences, but their durations are locale-independent. We pair nodes by
    matching their outgoing duration multisets, then pair each route's
    destinations by their duration values.
    """
    eng = parse_flight_db(DATA_EN)
    fr = parse_flight_db(DATA_FR)

    mapping = {}
    ambiguous = 0
    for faction in sorted(eng):
        if faction not in fr:
            continue
        eng_sources = eng[faction]
        fr_sources = fr[faction]

        fr_by_sig = {}
        for fr_src, fr_dests in fr_sources.items():
            sig = tuple(sorted(fr_dests.values()))
            fr_by_sig.setdefault(sig, []).append(fr_src)

        for eng_src, eng_dests in eng_sources.items():
            sig = tuple(sorted(eng_dests.values()))
            cands = fr_by_sig.get(sig, [])
            if len(cands) != 1:
                ambiguous += 1
                continue
            fr_src = cands[0]
            mapping[eng_src] = fr_src

            fr_dest_by_dur = {}
            for fr_d, dur in fr_sources[fr_src].items():
                fr_dest_by_dur.setdefault(dur, []).append(fr_d)
            for eng_d, dur in eng_dests.items():
                fr_cands = fr_dest_by_dur.get(dur, [])
                if len(fr_cands) == 1:
                    mapping.setdefault(eng_d, fr_cands[0])

    return mapping, ambiguous


def _zone_line(z):
    return (
        "                    { start = " + str(z["start"])
        + ", stop = " + str(z["stop"])
        + ", region = " + lua_string(z["region"])
        + ", subzone = " + lua_string(z["subzone"]) + " },"
    )


def emit(audio, travels, node_names):
    lines = []
    lines.append("-- Generated by tools/generate_travel_data.py - do not edit by hand.")
    lines.append("--")
    lines.append("-- Shipped clip paths and per-route zone timelines, in Lua so the client")
    lines.append("-- can read them (WoW cannot list files or read .txt files at runtime).")
    lines.append("")
    lines.append("FlightNarratorData = FlightNarratorData or {}")
    lines.append("")
    lines.append("FlightNarratorData.Audio = {")
    for region in sorted(audio):
        lines.append("    [" + lua_string(region) + "] = {")
        for subzone in sorted(audio[region]):
            lines.append("        [" + lua_string(subzone) + "] = {")
            for clip in audio[region][subzone]:
                lines.append("            " + lua_string(clip) + ",")
            lines.append("        },")
        lines.append("    },")
    lines.append("}")
    lines.append("")
    lines.append("FlightNarratorData.NodeNames = {")
    for eng in sorted(node_names):
        lines.append("    [" + lua_string(eng) + "] = " + lua_string(node_names[eng]) + ",")
    lines.append("}")
    lines.append("")
    lines.append("FlightNarratorData.Travels = {")
    for faction in sorted(travels):
        lines.append("    [" + lua_string(faction) + "] = {")
        for source in sorted(travels[faction]):
            lines.append("        [" + lua_string(source) + "] = {")
            for dest in sorted(travels[faction][source]):
                entry = travels[faction][source][dest]
                lines.append("            [" + lua_string(dest) + "] = {")
                lines.append("                duration = " + str(entry["duration"]) + ",")
                if "zones" in entry:
                    lines.append("                zones = {")
                    for z in entry["zones"]:
                        lines.append(_zone_line(z))
                    lines.append("                },")
                lines.append("            },")
            lines.append("        },")
        lines.append("    },")
    lines.append("}")
    lines.append("")

    with open(OUT_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))


def main():
    audio = collect_audio()
    travels, stats = collect_travels()
    node_names, ambiguous = build_node_names()
    emit(audio, travels, node_names)

    n_clips = sum(len(files) for subs in audio.values() for files in subs.values())
    n_routes = sum(
        len(srcs) for faction in travels.values() for srcs in faction.values()
    )
    n_zones = sum(
        1 for faction in travels.values() for srcs in faction.values()
        for entry in srcs.values() if "zones" in entry
    )
    print(f"Audio: {n_clips} clip(s) across {len(audio)} region(s)")
    print(f"Travels: {n_routes} route(s), {n_zones} with a zone timeline "
          f"({stats['multi_leg']} rebuilt from steps, "
          f"{stats['normalized']} rescaled to duration)")
    print(f"Node names: {len(node_names)} English->French mapping(s) ({ambiguous} ambiguous)")
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()


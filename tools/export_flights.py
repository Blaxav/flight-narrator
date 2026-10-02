#!/usr/bin/env python3
"""
Export WoW Classic (Vanilla) taxi flight durations from Sogoten/FlyTravelTimes.

Usage:
  python export_wow_classic_flight_times.py FlightData.lua wow_classic_flight_times.csv

Download FlightData.lua from:
  https://raw.githubusercontent.com/Sogoten/FlyTravelTimes/main/FlightData.lua

The script extracts the CLASSIC section only and writes one row per directed
origin -> destination route. Durations are stored in seconds in the source.
"""
import csv
import re
import sys
from pathlib import Path

if len(sys.argv) != 3:
    raise SystemExit("Usage: python export_wow_classic_flight_times.py FlightData.lua output.csv")

source = Path(sys.argv[1]).read_text(encoding="utf-8")
out_path = Path(sys.argv[2])

start_marker = 'FlyTravelTimes.FlightDB["CLASSIC"] = {'
end_marker = '-- TBC'
start = source.find(start_marker)
if start < 0:
    raise SystemExit("Could not find CLASSIC section in source file.")
end = source.find(end_marker, start)
if end < 0:
    raise SystemExit("Could not find end of CLASSIC section.")
classic = source[start:end]

# Parse faction -> origin -> destination = seconds, preserving quoted names.
faction = None
origin = None
routes = []
for line in classic.splitlines():
    faction_match = re.match(r'\s*\["(Horde|Alliance)"\]\s*=\s*\{', line)
    if faction_match:
        faction = faction_match.group(1)
        origin = None
        continue
    node_match = re.match(r'\s*\["((?:\\.|[^"])*)"\]\s*=\s*\{', line)
    if node_match:
        origin = node_match.group(1)
        continue
    dest_match = re.match(r'\s*\["((?:\\.|[^"])*)"\]\s*=\s*(\d+)\s*,?\s*$', line)
    if dest_match and faction and origin:
        destination = dest_match.group(1)
        seconds = int(dest_match.group(2))
        routes.append((faction, origin, destination, seconds))

# Remove duplicate identical rows, if present, but keep opposite-direction timings.
routes = list(dict.fromkeys(routes))
with out_path.open("w", newline="", encoding="utf-8-sig") as f:
    writer = csv.writer(f)
    writer.writerow(["expansion", "faction", "origin", "destination",
                     "duration_seconds", "duration_mm_ss"])
    for faction, origin, destination, seconds in routes:
        writer.writerow(["Classic Vanilla", faction, origin, destination,
                         seconds, f"{seconds // 60:02d}:{seconds % 60:02d}"])

print(f"Wrote {len(routes)} directed routes to {out_path}")

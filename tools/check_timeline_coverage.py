#!/usr/bin/env python3
"""Report coverage problems in the generated per-route zone timelines.

For every route in the travels/ tree (as rebuilt by generate_travel_data.py):
  - "gap"   : a span of the flight with no zone interval at all (no clip can play).
  - "start0": a foreign region whose interval wrongly starts at t=0 (the flight
              is reported over a region from the very first second).

Both are symptoms of the geometry used by generate_travel_zones.py (straight
segments crossing overlapping, non-tiling zone rectangles), not of the
concatenation in generate_travel_data.py. This script distinguishes direct vs
multi-leg routes to make that visible.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import generate_travel_data as gend

TRAVELS_DIR = os.path.join(os.path.dirname(HERE), "travels")


def merge(intervals):
    ivs = sorted((z["start"], z["stop"]) for z in intervals)
    merged = []
    for s, e in ivs:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


def gaps_of(zones, duration):
    merged = merge(zones)
    gaps = []
    cur = 0
    for s, e in merged:
        if s > cur:
            gaps.append((cur, min(s, duration)))
        cur = max(cur, e)
    if cur < duration:
        gaps.append((cur, duration))
    return [g for g in gaps if g[0] < g[1]]


def is_multi_leg(faction, source, destination):
    steps_path = os.path.join(
        TRAVELS_DIR, faction, source, destination, "steps.txt")
    steps = gend.read_steps(steps_path) if os.path.isfile(steps_path) else []
    return len(steps) > 1


def main():
    travels, _ = gend.collect_travels()

    gap_rows = []
    start0_rows = []
    n_with_zones = 0

    for faction in sorted(travels):
        for src in sorted(travels[faction]):
            for dst in sorted(travels[faction][src]):
                entry = travels[faction][src][dst]
                dur = entry["duration"]
                zones = entry.get("zones", [])
                if not zones:
                    continue
                n_with_zones += 1
                gaps = gaps_of(zones, dur)
                if gaps:
                    gap_rows.append((
                        sum(e - s for s, e in gaps), is_multi_leg(faction, src, dst),
                        faction, src, dst, dur, gaps))

                start0 = {}
                for z in zones:
                    if z["start"] == 0:
                        start0.setdefault((z["region"], z["subzone"]), []).append(z["stop"])
                if len({r for (r, _s) in start0}) > 1:
                    start0_rows.append((faction, src, dst, dur, sorted(start0.items())))

    print(f"routes avec une timeline zones : {n_with_zones}")
    print()
    print("=== 1. GAPS (temps sans aucune zone) ===")
    print(f"routes concernees : {len(gap_rows)}")
    direct = sum(1 for r in gap_rows if not r[1])
    multi = sum(1 for r in gap_rows if r[1])
    print(f"  dont routes directes  : {direct}")
    print(f"  dont routes multi-leg : {multi}")
    print(f"  somme des gaps        : {sum(r[0] for r in gap_rows)} s")
    gap_rows.sort(key=lambda r: r[0], reverse=True)
    print("Top 15 des routes (gap total decroissant) :")
    for total, multi_, f, s, d, dur, gaps in gap_rows[:15]:
        kind = "multi" if multi_ else "direct"
        print(f"  [{kind}] {f}/{s} -> {d} (dur={dur}) gap={total}s {gaps}")

    print()
    print("=== 2. REGION ETRANGERE QUI DEMARRE A t=0 ===")
    print(f"routes concernees : {len(start0_rows)}")
    for f, s, d, dur, items in start0_rows[:20]:
        print(f"  [{f}] {s} -> {d} (dur={dur})")
        for (region, sub), stops in items:
            print(f"      start=0 region={region!r} sub={sub!r} stops={stops}")


if __name__ == "__main__":
    main()

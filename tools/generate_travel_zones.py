#!/usr/bin/env python3
"""Génère travels/<faction>/<source>/<dest>/zones.txt pour chaque trajet direct.

La timeline de zones est reconstruite en échantillonnant le segment de vol :
noeuds en coordonnées carte (tools/map_transform.py), régions et sous-zones en
polygones (zones/**/geometry.txt). À chaque seconde, on détermine quels
polygones contiennent la position et on émet un intervalle par zone couverte.
Seuls les trajets directs reçoivent un zones.txt (concaténation au runtime).
"""
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import geometry as geo
import map_transform as mt
import generate_travel_data as gend

TRAVELS_DIR = os.path.join(ROOT, "travels")
ZONES_DIR = os.path.join(ROOT, "zones")
GENERAL = "Général"

# English zone -> (French region, continent)
ZONE_META = {
    "Arathi": ("Arathi", "EK"),
    "Ashenvale": ("Ashenvale", "Kalimdor"),
    "Azshara": ("Azshara", "Kalimdor"),
    "Badlands": ("Terres ingrates", "EK"),
    "Blasted Lands": ("Terres foudroyées", "EK"),
    "Burning Steppes": ("Steppes ardentes", "EK"),
    "Darkshore": ("Sombrivage", "Kalimdor"),
    "Desolace": ("Désolace", "Kalimdor"),
    "Dun Morogh": ("Dun Morogh", "EK"),
    "Durotar": ("Durotar", "Kalimdor"),
    "Duskwood": ("Bois de la Pénombre", "EK"),
    "Dustwallow Marsh": ("Marécage d'Âprefange", "Kalimdor"),
    "Eastern Plaguelands": ("Maleterres de l'est", "EK"),
    "Elwynn": ("Elwynn", "EK"),
    "Felwood": ("Gangrebois", "Kalimdor"),
    "Feralas": ("Feralas", "Kalimdor"),
    "Hillsbrad": ("Hillsbrad", "EK"),
    "Loch Modan": ("Loch Modan", "EK"),
    "Moonglade": ("Reflet-de-Lune", "Kalimdor"),
    "Mulgore": ("Mulgore", "Kalimdor"),
    "Redridge": ("Les Carmines", "EK"),
    "Searing Gorge": ("Gorge des Vents brûlants", "EK"),
    "Silithus": ("Silithus", "Kalimdor"),
    "Silverpine Forest": ("Forêt des Pins argentés", "EK"),
    "Stonetalon Mountains": ("Serres-Rocheuses", "Kalimdor"),
    "Stranglethorn": ("Strangleronce", "EK"),
    "Swamp of Sorrows": ("Marais des Chagrins", "EK"),
    "Tanaris": ("Tanaris", "Kalimdor"),
    "Teldrassil": ("Teldrassil", "Kalimdor"),
    "The Barrens": ("Les Tarides", "Kalimdor"),
    "The Hinterlands": ("Les Hinterlands", "EK"),
    "Thousand Needles": ("Mille Pointes", "Kalimdor"),
    "Tirisfal": ("Tirisfal", "EK"),
    "Un'Goro Crater": ("Cratère d'Un'Goro", "Kalimdor"),
    "Western Plaguelands": ("Maleterres de l'ouest", "EK"),
    "Westfall": ("Marche de l'Ouest", "EK"),
    "Wetlands": ("Les Paluns", "EK"),
    "Winterspring": ("Berceau-de-l'Hiver", "Kalimdor"),
}

REGION_CONTINENT = {fr: c for _, (fr, c) in ZONE_META.items()}
REGION_CONTINENT["Défilé de Deuillevent"] = "EK"
REGION_CONTINENT["Montagnes d'Alterac"] = "EK"


def split_city_zone(name):
    if ", " in name:
        city, zone = name.split(", ", 1)
    elif "," in name:
        city, zone = name.split(",", 1)
    else:
        return name, name
    return city.strip(), zone.strip()


def node_region_continent(node):
    _, zone = split_city_zone(node)
    return ZONE_META[zone]
def load_polygons():
    """Renvoie {region: poly} et {(region, sous-zone): poly} depuis zones/."""
    regions = {}
    subzones = {}
    for region in sorted(os.listdir(ZONES_DIR)):
        rd = os.path.join(ZONES_DIR, region)
        if not os.path.isdir(rd):
            continue
        for sub in sorted(os.listdir(rd)):
            gp = os.path.join(rd, sub, "geometry.txt")
            if not os.path.isfile(gp):
                continue
            poly = geo.parse_geometry(gp)
            if len(poly) < 3:
                continue
            poly = geo.normalize_clockwise(poly)
            if sub == GENERAL:
                regions[region] = poly
            else:
                subzones[(region, sub)] = poly
    return regions, subzones


def route_timeline(src, dst, duration, regions, subzones,
                   region_bbox, subzone_bbox):
    """Intervalles (start, stop, region, subzone) pour un segment direct."""
    active = defaultdict(list)
    for t in range(int(duration) + 1):
        frac = t / duration if duration else 0.0
        x = src[0] + (dst[0] - src[0]) * frac
        y = src[1] + (dst[1] - src[1]) * frac
        for region, (x0, y0, x1, y1) in region_bbox.items():
            if x0 <= x <= x1 and y0 <= y <= y1 and \
                    geo.point_in_polygon((x, y), regions[region]):
                active[(region, GENERAL)].append(t)
        for (region, sub), (x0, y0, x1, y1) in subzone_bbox.items():
            if x0 <= x <= x1 and y0 <= y <= y1 and \
                    geo.point_in_polygon((x, y), subzones[(region, sub)]):
                active[(region, sub)].append(t)

    out = []
    for key, ts in active.items():
        ts = sorted(set(ts))
        a = b = ts[0]
        for t in ts[1:]:
            if t == b + 1:
                b = t
            else:
                out.append((a, min(b + 1, duration), key[0], key[1]))
                a = b = t
        out.append((a, min(b + 1, duration), key[0], key[1]))
    return sorted(e for e in out if e[0] < e[1])


def write_zones(path, timeline):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for s, e, region, sub in timeline:
            f.write(f"{int(round(s))};{int(round(e))};{region};{sub};\n")


def main():
    fr_en, _ = gend.build_node_names()       # {anglais: francais}
    en_fr = {v: k for k, v in fr_en.items()}   # {francais: anglais}
    positions = mt.node_map_positions()       # {anglais: (map_id, x, y)}
    regions, subzones = load_polygons()

    by_cont = {}
    for cont in ("EK", "Kalimdor"):
        r = {reg: poly for reg, poly in regions.items()
             if REGION_CONTINENT.get(reg) == cont}
        s = {(reg, sub): poly for (reg, sub), poly in subzones.items()
             if REGION_CONTINENT.get(reg) == cont}
        by_cont[cont] = (r, {k: geo.bbox(p) for k, p in r.items()},
                         s, {k: geo.bbox(p) for k, p in s.items()})

    written = removed = skipped = 0
    for faction in ("alliance", "horde"):
        faction_dir = os.path.join(TRAVELS_DIR, faction)
        if not os.path.isdir(faction_dir):
            continue
        for src in sorted(os.listdir(faction_dir)):
            src_dir = os.path.join(faction_dir, src)
            if not os.path.isdir(src_dir):
                continue
            for dst in sorted(os.listdir(src_dir)):
                dst_dir = os.path.join(src_dir, dst)
                dur_path = os.path.join(dst_dir, "duration.txt")
                if not os.path.isfile(dur_path):
                    continue
                steps_path = os.path.join(dst_dir, "steps.txt")
                steps = [ln.strip() for ln in
                         open(steps_path, encoding="utf-8-sig") if ln.strip()] \
                    if os.path.isfile(steps_path) else []
                zones_path = os.path.join(dst_dir, "zones.txt")

                if len(steps) != 1:
                    if os.path.isfile(zones_path):
                        os.remove(zones_path)
                        removed += 1
                    continue

                en_src = en_fr.get(src, src)
                en_dst = en_fr.get(dst, dst)
                if en_src not in positions or en_dst not in positions:
                    skipped += 1
                    continue
                mid, sx, sy = positions[en_src]
                mid2, dx, dy = positions[en_dst]
                if mid != mid2:
                    skipped += 1
                    continue

                cont = "Kalimdor" if mid == 1 else "EK"
                r, rb, s, sb = by_cont[cont]
                duration = int(open(dur_path, encoding="utf-8-sig").read().strip())
                timeline = route_timeline((sx, sy), (dx, dy), duration,
                                          r, s, rb, sb)
                if timeline:
                    write_zones(zones_path, timeline)
                    written += 1

    print(f"Wrote zones.txt for {written} direct route(s), removed {removed} multi-hop, "
          f"{skipped} skipped")


if __name__ == "__main__":
    main()

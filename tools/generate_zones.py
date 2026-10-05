#!/usr/bin/env python3
"""Generate zones/<région>/<sous-zone>/ folders for WoW Classic.

Every Classic region becomes a folder. Inside it, one folder per city, dungeon,
raid, or sub-region, plus a "Général" folder that holds the audio applying to
the whole region.

City folders are derived automatically from DataFlights-frFR.lua (the official
frFR flight-node names), so every flight destination already maps to a zone.
Dungeons, raids and sub-regions are curated below in EXTRA_SUBZONES.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import generate_travels as gt  # noqa: E402  (tokenize, Parser, extract_classic_block)

LUA_PATH = os.path.join(ROOT, "DataFlights-frFR.lua")
OUT_DIR = os.path.join(ROOT, "zones")

GENERAL = "Général"


def canonical_zone(zone: str) -> str:
    """Normalize a flight-node zone string to its canonical folder name.

    The flight DB spells some zone names inconsistently ("Tarides" and
    "les Tarides" both appear for the Barrens) and leaves article-initial
    names lowercase. We title-case them so the folder tree is uniform.
    """
    if zone in ("Tarides", "les Tarides"):
        return "Les Tarides"
    return zone[:1].upper() + zone[1:]


def split_name_zone(name: str):
    if ", " in name:
        city, zone = name.split(", ", 1)
    elif "," in name:
        city, zone = name.split(",", 1)
    else:
        city, zone = name, ""
    return city.strip(), zone.strip()


# frFR flight-node names we prefer to display under the narration/lore name.
# text/ and prompts/ call the town "Ratchet" while the flight DB calls it
# "Ratchet" (both are official; "Ratchet" is the one used in the audio).
CITY_RENAME = {
    "Ratchet": "Ratchet",
}

# Curated sub-folders: dungeons, raids, sub-regions, and cities that are not
# flight nodes. Cities present in DataFlights-frFR.lua are added automatically.
#
# A few French translations are best-effort and marked TODO for review.
EXTRA_SUBZONES = {
    # --- Kalimdor ---
    "Teldrassil": ["Darnassus", "Dolanaar", "Aldrassil"],
    "Sombrivage": ["Bashal'Aran", "Ameth'Aran"],
    "Ashenvale": ["Profondeurs de Brassenoire"],
    "Azshara": [],
    "Durotar": ["Gouffre de Ragefeu", "Sen'jin", "Colline de Lame-Rasoir"],  # TODO: vérifier "Razor Hill"
    "Mulgore": ["Camp Narache", "Village des Sabot-Sanglant"],  # TODO: vérifier "Bloodhoof Village"
    "Les Tarides": ["Ouest", "Nord", "Sud", "Est", "Cavernes des lamentations"],
    "Serres-Rocheuses": [],
    "Désolace": ["Maraudon"],
    "Mille Pointes": [
        "Souilles de Tranchebauge (Kraul)",   # TODO: vérifier le nom frFR exact
        "Souilles de Tranchebauge (Downs)",   # TODO: vérifier le nom frFR exact
    ],
    "Marécage d'Âprefange": ["Repaire d'Onyxia"],
    "Feralas": ["Hache-Tripes"],
    "Gangrebois": [],
    "Berceau-de-l'Hiver": [],
    "Reflet-de-Lune": [],
    "Tanaris": ["Zul'Farrak"],
    "Cratère d'Un'Goro": [],
    "Silithus": ["Ruines d'Ahn'Qiraj", "Temple d'Ahn'Qiraj"],
    # --- Royaumes de l'Est ---
    "Elwynn": ["La Prison", "Comté-de-l'Or"],  # TODO: vérifier "Goldshire"
    "Dun Morogh": ["Gnomeregan", "Kharanos"],
    "Loch Modan": [],
    "Marche de l'Ouest": ["Les Mortemines"],
    "Les Carmines": [],
    "Bois de la Pénombre": [],
    "Défilé de Deuillevent": ["Karazhan"],
    "Les Paluns": [],
    "Hillsbrad": [],
    "Montagnes d'Alterac": ["Ruines d'Alterac"],
    "Arathi": ["Stromgarde"],
    "Strangleronce": ["Zul'Gurub"],
    "Terres ingrates": ["Uldaman"],
    "Marais des Chagrins": ["Temple englouti"],
    "Maleterres de l'ouest": ["Scholomance", "Andorhal"],
    "Maleterres de l'est": ["Stratholme", "Naxxramas"],
    "Steppes ardentes": [
        "Pic Rochenoire",
        "Profondeurs de Rochenoire",
        "Bas du Pic Rochenoire",
        "Sommet du Pic Rochenoire",
        "Cœur du Magma",
        "Repaire de l'Aile noire",
    ],
    "Gorge des Vents brûlants": [],
    "Les Hinterlands": ["Jintha'Alor"],
    "Terres foudroyées": ["La Porte des Ténèbres"],
    "Tirisfal": ["Monastère Écarlate", "Brill"],
    "Forêt des Pins argentés": ["Donjon d'Ombrecroc"],
}


def main() -> None:
    with open(LUA_PATH, encoding="utf-8") as f:
        content = f.read()

    classic_block = gt.extract_classic_block(content)
    db = gt.Parser(gt.tokenize(classic_block)).parse_table()

    # db: faction -> source -> destination -> duration. Sources and destinations
    # are "Ville, Zone" strings (or a bare name such as "Reflet-de-Lune").
    cities_by_zone = {}
    for sources in db.values():
        for node in sources:
            for key in (node, *sources[node].keys()):
                city, zone = split_name_zone(key)
                canon = canonical_zone(zone) if zone else city
                city = CITY_RENAME.get(city, city)
                if city == canon:
                    continue  # the node names the whole zone (Moonglade)
                cities_by_zone.setdefault(canon, set()).add(city)

    zones = sorted(set(EXTRA_SUBZONES) | set(cities_by_zone))

    os.makedirs(OUT_DIR, exist_ok=True)

    total_folders = 0
    for zone in zones:
        subzones = sorted(set(EXTRA_SUBZONES.get(zone, [])) | cities_by_zone.get(zone, set()))
        for sub in [GENERAL] + subzones:
            sub_path = os.path.join(OUT_DIR, zone, sub)
            os.makedirs(sub_path, exist_ok=True)
            # Git does not track empty directories; drop a .gitkeep so the whole
            # tree is committable until audio lands in it.
            with open(os.path.join(sub_path, ".gitkeep"), "w", encoding="utf-8"):
                pass
            total_folders += 1

    print(f"Wrote folder structure to {OUT_DIR}")
    print(f"{len(zones)} regions, {total_folders} sub-folders")
    for zone in zones:
        subs = [GENERAL] + sorted(set(EXTRA_SUBZONES.get(zone, [])) | cities_by_zone.get(zone, set()))
        print(f"  {zone}: {len(subs)} ({', '.join(subs)})")


if __name__ == "__main__":
    main()

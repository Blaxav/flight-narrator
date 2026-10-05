#!/usr/bin/env python3
"""Generate DataFlights-frFR.lua (CLASSIC only, French node names).

Reads the CLASSIC section of DataFlights.lua (English, name-based) and emits the
same flight durations keyed by the official frFR flight-node names.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import generate_travels as gt  # noqa: E402  (tokenize, Parser, extract_classic_block)

SRC_PATH = os.path.join(ROOT, "DataFlights.lua")
OUT_PATH = os.path.join(ROOT, "DataFlights-frFR.lua")

# English "Name, Zone" -> French "Name, Zone" (official frFR client names).
MAPPING = {
    # --- Horde / Kalimdor ---
    "Thunder Bluff, Mulgore": "Thunder Bluff, Mulgore",
    "Orgrimmar, Durotar": "Orgrimmar, Durotar",
    "Crossroads, The Barrens": "La Croisée, Tarides",
    "Sun Rock Retreat, Stonetalon Mountains": "Retraite de Roche-Soleil, Serres-Rocheuses",
    "Freewind Post, Thousand Needles": "Poste de Librevent, Mille Pointes",
    "Shadowprey Village, Desolace": "Proie-de-l'Ombre, Désolace",
    "Gadgetzan, Tanaris": "Gadgetzan, Tanaris",
    "Camp Mojache, Feralas": "Camp Mojache, Feralas",
    "Valormok, Azshara": "Valormok, Azshara",
    "Bloodvenom Post, Felwood": "Poste de la Vénéneuse, Gangrebois",
    "Everlook, Winterspring": "Long-guet, Berceau-de-l'Hiver",
    "Brackenwall Village, Dustwallow Marsh": "Mur-de-Fougères, marécage d'Âprefange",
    "Zoram'gar Outpost, Ashenvale": "Avant-poste de Zoram'gar, Ashenvale",
    "Splintertree Post, Ashenvale": "Poste de Bois-brisé, Ashenvale",
    "Nighthaven, Moonglade": "Havrenuit, Reflet-de-Lune",
    "Cenarion Hold, Silithus": "Fort cénarien, Silithus",
    "Camp Taurajo, The Barrens": "Camp Taurajo, les Tarides",
    "Marshal's Refuge, Un'Goro Crater": "Refuge des Marshal, cratère d'Un'Goro",
    "Ratchet, The Barrens": "Ratchet, les Tarides",
    # --- Eastern Kingdoms ---
    "The Sepulcher, Silverpine Forest": "Le Sépulcre, forêt des Pins argentés",
    "Undercity, Tirisfal": "Undercity, Tirisfal",
    "Tarren Mill, Hillsbrad": "Moulin-de-Tarren, Hillsbrad",
    "Hammerfall, Arathi": "Trépas-d'Orgrim, Arathi",
    "Booty Bay, Stranglethorn": "Baie-du-Butin, Strangleronce",
    "Grom'gol, Stranglethorn": "Grom'gol, Strangleronce",
    "Kargath, Badlands": "Kargath, Terres ingrates",
    "Stonard, Swamp of Sorrows": "Stonard, marais des Chagrins",
    "Light's Hope Chapel, Eastern Plaguelands": "Chapelle de l'Espoir de Lumière, Maleterres de l'est",
    "Flame Crest, Burning Steppes": "Corniches des flammes, Steppes ardentes",
    "Thorium Point, Searing Gorge": "Halte du Thorium, Gorge des Vents brûlants",
    "Revantusk Village, The Hinterlands": "Village des Revantusk, les Hinterlands",
    # --- Alliance / remaining Classic nodes ---
    "Aerie Peak, The Hinterlands": "Nid-de-l'Aigle, Les Hinterlands",
    "Astranaar, Ashenvale": "Astranaar, Ashenvale",
    "Auberdine, Darkshore": "Auberdine, Sombrivage",
    "Chillwind Camp, Western Plaguelands": "Camp du Noroît, Maleterres de l'ouest",
    "Darkshire, Duskwood": "Darkshire, bois de la Pénombre",
    "Feathermoon, Feralas": "Feathermoon, Feralas",
    "Ironforge, Dun Morogh": "Ironforge, Dun Morogh",
    "Lakeshire, Redridge": "Lakeshire, les Carmines",
    "Menethil Harbor, Wetlands": "Port de Menethil, les Paluns",
    "Morgan's Vigil, Burning Steppes": "Veille de Morgan, Steppes ardentes",
    "Nethergarde Keep, Blasted Lands": "Rempart-du-Néant, Terres foudroyées",
    "Nijel's Point, Desolace": "Combe de Nijel, Désolace",
    "Refuge Pointe, Arathi": "Refuge de l'Ornière, Arathi",
    "Rut'theran Village, Teldrassil": "Rut'theran, Teldrassil",
    "Sentinel Hill, Westfall": "Colline des sentinelles, marche de l'Ouest",
    "Southshore, Hillsbrad": "Southshore, Hillsbrad",
    "Stonetalon Peak, Stonetalon Mountains": "Pic des Serres-Rocheuses, Serres-Rocheuses",
    "Stormwind, Elwynn": "Stormwind, Elwynn",
    "Talonbranch Glade, Felwood": "Clairière de Griffebranche, Gangrebois",
    "Talrendis Point, Azshara": "Halte de Talrendis, Azshara",
    "Thalanaar, Feralas": "Thalanaar, Feralas",
    "Thelsamar, Loch Modan": "Thelsamar, Loch Modan",
    "Theramore, Dustwallow Marsh": "Theramore, marécage d'Âprefange",
}


def _quote(name: str) -> str:
    # Names contain apostrophes but never double quotes.
    return '"' + name + '"'


def main() -> None:
    with open(SRC_PATH, encoding="utf-8") as f:
        content = f.read()

    classic_block = gt.extract_classic_block(content)
    db = gt.Parser(gt.tokenize(classic_block)).parse_table()

    # Verify every location key has a mapping and that the mapping is 1:1.
    keys = set()
    for sources in db.values():
        for src in sources:
            keys.add(src)
            keys.update(sources[src])

    missing = {k for k in keys if k and k not in MAPPING}
    if missing:
        print("ERROR: these names have no French mapping:")
        for k in sorted(missing):
            print("  -", k)
        sys.exit(1)

    fr_values = list(MAPPING.values())
    if len(set(fr_values)) != len(fr_values):
        dupes = {v for v in fr_values if fr_values.count(v) > 1}
        print("ERROR: duplicate French names:", sorted(dupes))
        sys.exit(1)

    # Build the translated db.
    tdb = {}
    total_edges = 0
    for faction, sources in sorted(db.items()):
        tdb[faction] = {}
        for src, dests in sources.items():
            tdb[faction][MAPPING[src]] = {
                MAPPING[d]: dur for d, dur in dests.items()
            }
            total_edges += len(dests)

    lines = []
    lines.append("-- FlyTravelTimes Flight Data (NAME-BASED) — French (frFR)")
    lines.append("-- CLASSIC only. Translated from DataFlights.lua using the official frFR")
    lines.append("-- flight-node names.")
    lines.append("")
    lines.append("FlyTravelTimes = FlyTravelTimes or {}")
    lines.append("FlyTravelTimes.FlightDB = FlyTravelTimes.FlightDB or {}")
    lines.append("")
    lines.append('FlyTravelTimes.FlightDB["CLASSIC"] = {')

    for faction in sorted(tdb):
        lines.append(f'    [{_quote(faction)}] = {{')
        for src in sorted(tdb[faction]):
            lines.append(f'        [{_quote(src)}] = {{')
            for dest in sorted(tdb[faction][src]):
                lines.append(
                    f'            [{_quote(dest)}] = {tdb[faction][src][dest]},'
                )
            lines.append("        },")
        lines.append("    },")

    lines.append("}")

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"Wrote {OUT_PATH}")
    for faction in sorted(tdb):
        n_src = len(tdb[faction])
        n_edges = sum(len(d) for d in tdb[faction].values())
        print(f"  {faction}: {n_src} sources, {n_edges} edges")
    print(f"  Total: {total_edges} directed edges")


if __name__ == "__main__":
    main()



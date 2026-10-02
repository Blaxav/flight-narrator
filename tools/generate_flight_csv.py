#!/usr/bin/env python3
"""Generate a CSV of all direct (non-stop) flight paths in WoW Classic (vanilla).

Each row is one directed connection. Durations are approximate in-game flight
times (seconds), sourced from Classic-era community flight-timer data.
"""
import csv
import os

# (continent, node_a, node_b, duration_seconds)
# Each entry is one undirected direct connection; both directions are emitted.
EDGES = [
    # ---- Eastern Kingdoms - Alliance & neutral ----
    ("Eastern Kingdoms", "Stormwind", "Sentinel Hill", 80),
    ("Eastern Kingdoms", "Stormwind", "Lakeshire", 113),
    ("Eastern Kingdoms", "Stormwind", "Darkshire", 100),
    ("Eastern Kingdoms", "Stormwind", "Booty Bay", 230),
    ("Eastern Kingdoms", "Stormwind", "Ironforge", 259),
    ("Eastern Kingdoms", "Stormwind", "Nethergarde Keep", 240),
    ("Eastern Kingdoms", "Stormwind", "Morgan's Vigil", 151),
    ("Eastern Kingdoms", "Ironforge", "Menethil Harbor", 128),
    ("Eastern Kingdoms", "Ironforge", "Thelsamar", 105),
    ("Eastern Kingdoms", "Ironforge", "Southshore", 265),
    ("Eastern Kingdoms", "Ironforge", "Refuge Pointe", 253),
    ("Eastern Kingdoms", "Ironforge", "Aerie Peak", 120),
    ("Eastern Kingdoms", "Ironforge", "Chillwind Camp", 294),
    ("Eastern Kingdoms", "Ironforge", "Light's Hope Chapel", 369),
    ("Eastern Kingdoms", "Ironforge", "Thorium Point", 94),
    ("Eastern Kingdoms", "Sentinel Hill", "Lakeshire", 130),
    ("Eastern Kingdoms", "Sentinel Hill", "Darkshire", 95),
    ("Eastern Kingdoms", "Lakeshire", "Darkshire", 60),
    ("Eastern Kingdoms", "Lakeshire", "Morgan's Vigil", 64),
    ("Eastern Kingdoms", "Darkshire", "Booty Bay", 173),
    ("Eastern Kingdoms", "Darkshire", "Nethergarde Keep", 150),
    ("Eastern Kingdoms", "Booty Bay", "Nethergarde Keep", 266),
    ("Eastern Kingdoms", "Nethergarde Keep", "Morgan's Vigil", 207),
    ("Eastern Kingdoms", "Morgan's Vigil", "Thorium Point", 100),
    ("Eastern Kingdoms", "Menethil Harbor", "Thelsamar", 158),
    ("Eastern Kingdoms", "Menethil Harbor", "Refuge Pointe", 120),
    ("Eastern Kingdoms", "Menethil Harbor", "Southshore", 108),
    ("Eastern Kingdoms", "Thelsamar", "Refuge Pointe", 167),
    ("Eastern Kingdoms", "Southshore", "Refuge Pointe", 80),
    ("Eastern Kingdoms", "Southshore", "Aerie Peak", 68),
    ("Eastern Kingdoms", "Refuge Pointe", "Aerie Peak", 74),
    ("Eastern Kingdoms", "Aerie Peak", "Chillwind Camp", 60),
    ("Eastern Kingdoms", "Aerie Peak", "Light's Hope Chapel", 180),
    ("Eastern Kingdoms", "Light's Hope Chapel", "Revantusk Village", 60),
    ("Eastern Kingdoms", "Thorium Point", "Kargath", 63),
    ("Eastern Kingdoms", "Thorium Point", "Stonard", 286),
    ("Eastern Kingdoms", "Thorium Point", "Light's Hope Chapel", 559),
    # ---- Eastern Kingdoms - Horde ----
    ("Eastern Kingdoms", "Undercity", "The Sepulcher", 109),
    ("Eastern Kingdoms", "Undercity", "Tarren Mill", 140),
    ("Eastern Kingdoms", "Undercity", "Hammerfall", 280),
    ("Eastern Kingdoms", "Undercity", "Revantusk Village", 284),
    ("Eastern Kingdoms", "Undercity", "Light's Hope Chapel", 261),
    ("Eastern Kingdoms", "The Sepulcher", "Tarren Mill", 97),
    ("Eastern Kingdoms", "Tarren Mill", "Hammerfall", 117),
    ("Eastern Kingdoms", "Tarren Mill", "Revantusk Village", 177),
    ("Eastern Kingdoms", "Hammerfall", "Revantusk Village", 92),
    ("Eastern Kingdoms", "Hammerfall", "Kargath", 259),
    ("Eastern Kingdoms", "Kargath", "Booty Bay", 412),
    ("Eastern Kingdoms", "Kargath", "Stonard", 283),
    ("Eastern Kingdoms", "Kargath", "Flame Crest", 93),
    ("Eastern Kingdoms", "Kargath", "Grom'gol Base Camp", 320),
    ("Eastern Kingdoms", "Stonard", "Booty Bay", 264),
    ("Eastern Kingdoms", "Stonard", "Grom'gol Base Camp", 197),
    ("Eastern Kingdoms", "Stonard", "Flame Crest", 205),
    ("Eastern Kingdoms", "Grom'gol Base Camp", "Booty Bay", 92),
    ("Eastern Kingdoms", "Grom'gol Base Camp", "Flame Crest", 401),
    # ---- Kalimdor - Alliance & neutral ----
    ("Kalimdor", "Rut'theran Village", "Auberdine", 85),
    ("Kalimdor", "Rut'theran Village", "Astranaar", 261),
    ("Kalimdor", "Auberdine", "Astranaar", 162),
    ("Kalimdor", "Auberdine", "Stonetalon Peak", 179),
    ("Kalimdor", "Auberdine", "Moonglade", 147),
    ("Kalimdor", "Auberdine", "Theramore", 648),
    ("Kalimdor", "Auberdine", "Feathermoon Stronghold", 150),
    ("Kalimdor", "Auberdine", "Talrendis Post", 132),
    ("Kalimdor", "Auberdine", "Talonbranch Glade", 150),
    ("Kalimdor", "Astranaar", "Stonetalon Peak", 154),
    ("Kalimdor", "Astranaar", "Nijel's Point", 273),
    ("Kalimdor", "Stonetalon Peak", "Nijel's Point", 120),
    ("Kalimdor", "Moonglade", "Everlook", 138),
    ("Kalimdor", "Moonglade", "Rut'theran Village", 152),
    ("Kalimdor", "Theramore", "Gadgetzan", 156),
    ("Kalimdor", "Theramore", "Nijel's Point", 321),
    ("Kalimdor", "Theramore", "Thalanaar", 160),
    ("Kalimdor", "Theramore", "Ratchet", 111),
    ("Kalimdor", "Theramore", "Talrendis Post", 150),
    ("Kalimdor", "Gadgetzan", "Thalanaar", 174),
    ("Kalimdor", "Gadgetzan", "Ratchet", 262),
    ("Kalimdor", "Gadgetzan", "Marshal's Refuge", 110),
    ("Kalimdor", "Thalanaar", "Feathermoon Stronghold", 167),
    ("Kalimdor", "Feathermoon Stronghold", "Nijel's Point", 230),
    ("Kalimdor", "Feathermoon Stronghold", "Cenarion Hold", 175),
    ("Kalimdor", "Talrendis Post", "Ratchet", 133),
    ("Kalimdor", "Talonbranch Glade", "Everlook", 121),
    ("Kalimdor", "Everlook", "Bloodvenom Post", 193),
    ("Kalimdor", "Everlook", "Orgrimmar", 312),
    ("Kalimdor", "Everlook", "Ratchet", 357),
    # ---- Kalimdor - Horde & neutral ----
    ("Kalimdor", "Orgrimmar", "Crossroads", 110),
    ("Kalimdor", "Orgrimmar", "Ratchet", 161),
    ("Kalimdor", "Orgrimmar", "Splintertree Post", 93),
    ("Kalimdor", "Orgrimmar", "Valormok", 99),
    ("Kalimdor", "Orgrimmar", "Thunder Bluff", 216),
    ("Kalimdor", "Orgrimmar", "Sun Rock Retreat", 260),
    ("Kalimdor", "Orgrimmar", "Brackenwall Village", 226),
    ("Kalimdor", "Orgrimmar", "Moonglade", 372),
    ("Kalimdor", "Thunder Bluff", "Camp Taurajo", 100),
    ("Kalimdor", "Thunder Bluff", "Crossroads", 171),
    ("Kalimdor", "Thunder Bluff", "Sun Rock Retreat", 182),
    ("Kalimdor", "Thunder Bluff", "Freewind Post", 215),
    ("Kalimdor", "Thunder Bluff", "Shadowprey Village", 168),
    ("Kalimdor", "Thunder Bluff", "Brackenwall Village", 232),
    ("Kalimdor", "Thunder Bluff", "Valormok", 263),
    ("Kalimdor", "Thunder Bluff", "Splintertree Post", 309),
    ("Kalimdor", "Thunder Bluff", "Zoram'gar Outpost", 400),
    ("Kalimdor", "Thunder Bluff", "Ratchet", 230),
    ("Kalimdor", "Crossroads", "Ratchet", 61),
    ("Kalimdor", "Crossroads", "Camp Taurajo", 85),
    ("Kalimdor", "Crossroads", "Sun Rock Retreat", 150),
    ("Kalimdor", "Crossroads", "Splintertree Post", 161),
    ("Kalimdor", "Crossroads", "Brackenwall Village", 162),
    ("Kalimdor", "Crossroads", "Valormok", 170),
    ("Kalimdor", "Crossroads", "Freewind Post", 184),
    ("Kalimdor", "Crossroads", "Zoram'gar Outpost", 230),
    ("Kalimdor", "Crossroads", "Bloodvenom Post", 247),
    ("Kalimdor", "Camp Taurajo", "Freewind Post", 131),
    ("Kalimdor", "Camp Taurajo", "Ratchet", 144),
    ("Kalimdor", "Ratchet", "Brackenwall Village", 223),
    ("Kalimdor", "Ratchet", "Sun Rock Retreat", 218),
    ("Kalimdor", "Ratchet", "Zoram'gar Outpost", 299),
    ("Kalimdor", "Ratchet", "Shadowprey Village", 374),
    ("Kalimdor", "Ratchet", "Camp Mojache", 318),
    ("Kalimdor", "Splintertree Post", "Valormok", 95),
    ("Kalimdor", "Splintertree Post", "Zoram'gar Outpost", 166),
    ("Kalimdor", "Valormok", "Bloodvenom Post", 236),
    ("Kalimdor", "Freewind Post", "Gadgetzan", 87),
    ("Kalimdor", "Freewind Post", "Shadowprey Village", 323),
    ("Kalimdor", "Brackenwall Village", "Gadgetzan", 222),
    ("Kalimdor", "Brackenwall Village", "Marshal's Refuge", 329),
    ("Kalimdor", "Shadowprey Village", "Gadgetzan", 466),
    ("Kalimdor", "Camp Mojache", "Gadgetzan", 200),
    ("Kalimdor", "Camp Mojache", "Marshal's Refuge", 307),
    ("Kalimdor", "Camp Mojache", "Shadowprey Village", 201),
]


def mmss(seconds: int) -> str:
    return f"{seconds // 60}:{seconds % 60:02d}"


def main() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    out_path = os.path.join(os.path.dirname(here), "flight-paths-classic.csv")

    rows = []
    for continent, a, b, secs in EDGES:
        rows.append([a, b, continent, secs, mmss(secs)])
        rows.append([b, a, continent, secs, mmss(secs)])

    rows.sort(key=lambda r: (r[2], r[0], r[1]))

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["source", "destination", "continent", "duration_seconds", "duration_mmss"])
        writer.writerows(rows)

    print(f"Wrote {len(rows)} directed rows ({len(EDGES)} undirected connections) to {out_path}")


if __name__ == "__main__":
    main()

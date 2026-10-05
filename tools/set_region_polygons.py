#!/usr/bin/env python3
"""Écrit les polygones de région (Général) dans zones/<region>/Général/geometry.txt.

Premier pavage approximatif des deux continents, en coordonnées carte (0-100,
X est, Y sud), calé sur les noeuds de vol (tools/map_transform.py) et sur le
polygone des Tarides fourni. Les polygones sont normalisés en sens horaire.

Lance aussi un auto-contrôle : chaque noeud de vol doit tomber dans le polygone
de SA région (et pas dans celui d'une autre).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import geometry as geo
import map_transform as mt
import generate_travel_zones as gtz

ZONES = os.path.join(ROOT, "zones")
GENERAL = "Général"

# region -> liste de sommets (x, y). Sens horaire non requis (normalisé après).
REGION_POLYGONS = {
    # --- Kalimdor ---
    "Teldrassil": [(42, 15), (47, 15), (47, 20), (42, 20)],
    "Sombrivage": [(42, 21), (47, 21), (47, 34), (42, 34)],
    "Berceau-de-l'Hiver": [(54, 20), (62, 20), (62, 28), (54, 28)],
    "Reflet-de-Lune": [(49, 19), (54, 19), (54, 25), (49, 25)],
    "Gangrebois": [(47, 25), (54, 25), (54, 34), (47, 34)],
    "Ashenvale": [(42, 34), (54, 34), (54, 44), (46, 44), (46, 40), (42, 40)],
    "Azshara": [(54, 34), (62, 34), (62, 42), (54, 42)],
    "Serres-Rocheuses": [(41, 40), (46, 40), (46, 49), (41, 49)],
    "Durotar": [(57.5, 42), (62, 42), (62, 50), (57.5, 50)],
    "Les Tarides": [(49, 46.4), (49, 68.6), (54.5, 72.7), (53.6, 61.9),
                    (57.3, 61.4), (56.4, 44.6)],
    "Mulgore": [(44.5, 49), (47, 49), (47, 60), (44.5, 60)],
    "Désolace": [(36, 49), (44.5, 49), (44.5, 62), (36, 62)],
    "Feralas": [(36, 62), (49, 62), (49, 72), (36, 72)],
    "Marécage d'Âprefange": [(57.3, 61.4), (60, 62), (60, 72), (54.5, 72.7), (53.6, 61.9)],
    "Mille Pointes": [(49, 73), (56, 73), (56, 76), (49, 76)],
    "Cratère d'Un'Goro": [(46, 76), (52, 76), (52, 80), (46, 80)],
    "Tanaris": [(52, 78), (60, 78), (60, 84), (52, 84)],
    "Silithus": [(40, 76), (46, 76), (46, 84), (40, 84)],

    # --- Royaumes de l'Est ---
    "Tirisfal": [(43, 22), (46, 22), (46, 28), (43, 28)],
    "Forêt des Pins argentés": [(38, 26), (43, 26), (43, 34), (38, 34)],
    "Maleterres de l'ouest": [(46, 24), (50, 24), (50, 30), (46, 30)],
    "Maleterres de l'est": [(50, 20), (62, 20), (62, 26), (50, 26)],
    "Les Hinterlands": [(50, 26), (62, 26), (62, 36), (50, 36)],
    "Hillsbrad": [(44, 30), (50, 30), (50, 38), (44, 38)],
    "Montagnes d'Alterac": [(44, 28), (46, 28), (46, 30), (44, 30)],
    "Arathi": [(50, 36), (56, 36), (56, 42), (50, 42)],
    "Les Paluns": [(46, 42), (52, 42), (52, 48.5), (46, 48.5)],
    "Dun Morogh": [(46, 48.5), (52, 48.5), (52, 56), (46, 56)],
    "Loch Modan": [(52, 50), (56, 50), (56, 56), (52, 56)],
    "Gorge des Vents brûlants": [(46, 58), (50, 58), (50, 62), (46, 62)],
    "Terres ingrates": [(50, 56), (56, 56), (56, 62), (50, 62)],
    "Steppes ardentes": [(48, 62), (55, 62), (55, 68), (48, 68)],
    "Elwynn": [(42, 64), (46, 64), (46, 72), (42, 72)],
    "Marche de l'Ouest": [(40, 72), (44, 72), (44, 80), (40, 80)],
    "Bois de la Pénombre": [(46, 70), (51, 70), (51, 80), (46, 80)],
    "Les Carmines": [(51, 68), (54, 68), (54, 74), (51, 74)],
    "Défilé de Deuillevent": [(51, 74), (54, 74), (54, 78), (51, 78)],
    "Marais des Chagrins": [(54, 74), (58, 74), (58, 79), (54, 79)],
    "Terres foudroyées": [(54, 79), (58, 79), (58, 88), (54, 88)],
    "Strangleronce": [(42, 82), (48, 82), (48, 96), (42, 96)],
}


def write_geometry(region, poly):
    path = os.path.join(ZONES, region, GENERAL, "geometry.txt")
    poly = geo.normalize_clockwise(list(poly))
    header = (
        f"# {region} / {GENERAL} — polygone (coordonnées carte continent 0-100)\n"
        "# X = est, Y = sud. Sommets en SENS HORAIRE, un par ligne : X;Y\n"
    )
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(header)
        for x, y in poly:
            f.write(f"{x};{y}\n")


def main():
    missing = [r for r in REGION_POLYGONS if not os.path.isdir(os.path.join(ZONES, r))]
    for region, poly in REGION_POLYGONS.items():
        write_geometry(region, poly)
    print(f"Écrit {len(REGION_POLYGONS)} polygones de région."
          + (f"  INCONNUS (ignorés) : {missing}" if missing else ""))

    # --- auto-contrôle : chaque noeud dans SA région (même continent) ---
    positions = mt.node_map_positions()  # {eng: (map_id, x, y)}
    cont_of = {r: gtz.REGION_CONTINENT.get(r, "?") for r in REGION_POLYGONS}
    problems = []
    for eng, (_mid, x, y) in positions.items():
        try:
            region, _cont = gtz.node_region_continent(eng)
        except KeyError:
            continue
        poly = REGION_POLYGONS.get(region)
        if poly is None:
            continue
        if not geo.point_in_polygon((x, y), poly):
            problems.append((region, eng, round(x, 1), round(y, 1)))
        # noeud dans une AUTRE région du MÊME continent ?
        for other, opoly in REGION_POLYGONS.items():
            if other == region or cont_of[other] != cont_of[region]:
                continue
            if geo.point_in_polygon((x, y), opoly):
                problems.append((f"{region}->{other}", eng, round(x, 1), round(y, 1)))

    if problems:
        print(f"\n{len(problems)} problème(s) de nœud hors région :")
        for region, eng, x, y in problems:
            print(f"  {eng:32s} ({x},{y})  —  {region}")
    else:
        print("\nAuto-contrôle OK : chaque nœud est dans sa région.")


if __name__ == "__main__":
    main()

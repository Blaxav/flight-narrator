#!/usr/bin/env python3
"""Remplit les geometry.txt vides des sous-zones (donjons, sous-régions).

Chaque entrée est un petit polygone placé à sa position approximative sur la
carte continent (0-100). Les quartiers des Tarides (Nord/Sud/Est/Ouest)
reçoivent des rectangles couvrant une partie de la région. Idempotent sur les
fichiers déjà remplis (on n'écrase que les fichiers vides).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import geometry as geo

ZONES = os.path.join(ROOT, "zones")


def box(cx, cy, half=1.5):
    """Carré (sens horaire) centré sur (cx, cy)."""
    return [(cx - half, cy - half), (cx + half, cy - half),
            (cx + half, cy + half), (cx - half, cy + half)]


# "region/sous-zone" -> liste de sommets (x, y)
SUBZONES = {
    # --- Kalimdor ---
    "Ashenvale/Profondeurs de Brassenoire": box(43.5, 37.5),
    "Durotar/Colline de Lame-Rasoir": box(55.5, 47.5),
    "Durotar/Gouffre de Ragefeu": box(58, 45.5),
    "Durotar/Sen'jin": box(56.5, 50),
    "Défilé de Deuillevent/Karazhan": box(52.5, 75.5),
    "Désolace/Maraudon": box(39, 60),
    "Feralas/Hache-Tripes": box(43, 67.5),
    "Les Hinterlands/Jintha'Alor": box(58, 33.5),
    "Les Tarides/Cavernes des lamentations": box(50, 63.5),
    "Les Tarides/Nord": [(49, 46.4), (56, 46.4), (56, 56), (49, 56)],
    "Les Tarides/Sud": [(49, 56), (54, 56), (54, 68), (49, 68)],
    "Les Tarides/Ouest": [(49, 46.4), (53, 46.4), (53, 68), (49, 68)],
    "Les Tarides/Est": [(53, 46.4), (56, 46.4), (56, 61), (53, 61)],
    "Marécage d'Âprefange/Repaire d'Onyxia": box(56, 70),
    "Mille Pointes/Souilles de Tranchebauge (Downs)": box(51, 74.5),
    "Mille Pointes/Souilles de Tranchebauge (Kraul)": box(50, 73.5),
    "Mulgore/Camp Narache": box(45, 58.5),
    "Mulgore/Village des Sabot-Sanglant": box(46.5, 55.5),
    "Silithus/Ruines d'Ahn'Qiraj": box(42, 82),
    "Silithus/Temple d'Ahn'Qiraj": box(43.5, 80),
    "Sombrivage/Ameth'Aran": box(43.5, 28),
    "Sombrivage/Bashal'Aran": box(44.5, 25),
    "Tanaris/Zul'Farrak": box(54, 79.5),
    "Teldrassil/Aldrassil": box(43, 17),
    "Teldrassil/Darnassus": box(45, 16, 2.0),
    "Teldrassil/Dolanaar": box(44, 18),

    # --- Royaumes de l'Est ---
    "Arathi/Stromgarde": box(53.5, 37.5),
    "Dun Morogh/Gnomeregan": box(47, 52),
    "Dun Morogh/Kharanos": box(49, 50.5),
    "Elwynn/Comté-de-l'Or": box(44, 67.5),
    "Elwynn/La Prison": box(44, 69.5),
    "Forêt des Pins argentés/Donjon d'Ombrecroc": box(41, 31.5),
    "Maleterres de l'est/Naxxramas": box(56, 24),
    "Maleterres de l'est/Stratholme": box(57.5, 24),
    "Maleterres de l'ouest/Andorhal": box(48, 28),
    "Maleterres de l'ouest/Scholomance": box(49, 27),
    "Marais des Chagrins/Temple englouti": box(55.5, 76.5),
    "Marche de l'Ouest/Les Mortemines": box(41, 76.5),
    "Montagnes d'Alterac/Ruines d'Alterac": box(45, 29),
    "Steppes ardentes/Bas du Pic Rochenoire": box(50.5, 62.5),
    "Steppes ardentes/Cœur du Magma": box(49.5, 63),
    "Steppes ardentes/Pic Rochenoire": box(50, 63),
    "Steppes ardentes/Profondeurs de Rochenoire": box(50.5, 63.5),
    "Steppes ardentes/Repaire de l'Aile noire": box(49.5, 62.5),
    "Steppes ardentes/Sommet du Pic Rochenoire": box(50, 62),
    "Strangleronce/Zul'Gurub": box(44, 87),
    "Terres foudroyées/La Porte des Ténèbres": box(55.5, 86),
    "Terres ingrates/Uldaman": box(51.5, 59.5),
    "Tirisfal/Brill": box(45, 25.5),
    "Tirisfal/Monastère Écarlate": box(45.5, 23),
}


def main():
    written = 0
    for key, poly in SUBZONES.items():
        region, sub = key.split("/", 1)
        path = os.path.join(ZONES, region, sub, "geometry.txt")
        if not os.path.isdir(os.path.dirname(path)):
            continue
        poly = geo.normalize_clockwise(poly)
        header = (f"# {region} / {sub} — polygone (coordonnées carte continent 0-100)\n"
                  "# X = est, Y = sud. Sommets en SENS HORAIRE, un par ligne : X;Y\n")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(header)
            for x, y in poly:
                f.write(f"{x};{y}\n")
        written += 1

    # vérification : reste-t-il des geometry.txt vides ?
    empty = []
    for region in sorted(os.listdir(ZONES)):
        rd = os.path.join(ZONES, region)
        if not os.path.isdir(rd):
            continue
        for sub in sorted(os.listdir(rd)):
            gp = os.path.join(rd, sub, "geometry.txt")
            if os.path.isfile(gp) and not geo.parse_geometry(gp):
                empty.append(f"{region}/{sub}")

    print(f"Écrit {written} polygones de sous-zone.")
    if empty:
        print(f"{len(empty)} sous-zone(s) encore vide(s) : {empty}")
    else:
        print("Aucune sous-zone vide : tout est rempli.")


if __name__ == "__main__":
    main()

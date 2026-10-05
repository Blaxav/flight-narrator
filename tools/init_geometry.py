#!/usr/bin/env python3
"""Crée un geometry.txt de départ pour chaque zones/<region>/<sous-zone>/.

- Général : rectangle = boîte englobante (paddée) des noeuds de vol de la
  région, exprimée en coordonnées carte continent (via tools/map_transform.py).
- Villes (sous-dossiers qui correspondent à un point de vol) : petit carré
  autour du noeud, assez grand pour que le trajet le traverse.
- Autres sous-dossiers (donjons, sous-régions) : gabarit vide à remplir.

Idempotent : ne touche pas aux geometry.txt déjà existants.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import map_transform as mt            # noqa: E402
import generate_travel_zones as gtz   # noqa: E402  (node_region_continent)
import generate_travel_data as gend   # noqa: E402  (build_node_names)

ZONES = os.path.join(ROOT, "zones")
GENERAL = "Général"

# taille (demi-côté) du carré de départ autour d'un noeud de ville, en unités carte
CITY_HALF = 2.0
# padding de la boîte englobante des régions : fraction de sa plus grande dimension
REGION_PAD_FRAC = 0.15
REGION_PAD_MIN = 2.0


def _header(region, sub):
    return (
        f"# {region} / {sub} — polygone (coordonnées carte continent 0-100)\n"
        "# X = est, Y = sud. Sommets en SENS HORAIRE, un par ligne : X;Y\n"
    )


def _write(path, region, sub, verts):
    lines = [_header(region, sub)]
    if verts:
        for x, y in verts:
            lines.append(f"{x:.2f};{y:.2f}")
    else:
        lines.append("# (à remplir — exemple commenté ci-dessous)")
        lines.append("# 46.2;22.4")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


def _rect(x0, y0, x1, y1):
    """Rectangle en sens horaire (Y vers le bas)."""
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def _clamp(v):
    return max(0.0, min(100.0, v))


def main():
    positions = mt.node_map_positions()   # {nom_anglais: (map_id, x, y)}
    fr_names, _ = gend.build_node_names()  # {nom_anglais: nom_francais}

    def _city_of(fr_name):
        # "La Croisée, Tarides" -> "La Croisée" ; nom nu -> lui-même
        for sep in (", ", ","):
            if sep in fr_name:
                return fr_name.split(sep, 1)[0].strip()
        return fr_name.strip()

    # nom français de ville -> nom anglais du noeud (pour les sous-dossiers villes)
    fr_city_to_eng = {}
    for eng, fr in fr_names.items():
        fr_city_to_eng.setdefault(_city_of(fr), eng)

    # région -> liste de (x, y) carte pour ses noeuds de vol
    region_nodes = {}
    for eng, (_mid, x, y) in positions.items():
        try:
            region, _cont = gtz.node_region_continent(eng)
        except KeyError:
            # noeud sans zone dans ZONE_META (ex. "Northshire Abbey")
            continue
        region_nodes.setdefault(region, []).append((x, y))

    created = 0
    skipped = 0
    for region in sorted(os.listdir(ZONES)):
        rd = os.path.join(ZONES, region)
        if not os.path.isdir(rd):
            continue
        for sub in sorted(os.listdir(rd)):
            gp = os.path.join(rd, sub, "geometry.txt")
            if os.path.isfile(gp):
                skipped += 1
                continue

            verts = []
            if sub == GENERAL:
                pts = region_nodes.get(region)
                if pts:
                    xs = [p[0] for p in pts]
                    ys = [p[1] for p in pts]
                    pad = max(REGION_PAD_MIN, REGION_PAD_FRAC * max(max(xs) - min(xs), max(ys) - min(ys)))
                    verts = _rect(_clamp(min(xs) - pad), _clamp(min(ys) - pad),
                                  _clamp(max(xs) + pad), _clamp(max(ys) + pad))
            else:
                eng = fr_city_to_eng.get(sub)
                if eng and eng in positions:
                    _mid, x, y = positions[eng]
                    verts = _rect(x - CITY_HALF, y - CITY_HALF, x + CITY_HALF, y + CITY_HALF)

            _write(gp, region, sub, verts)
            created += 1

    print(f"geometry.txt créés : {created}")
    print(f"existants (ignorés) : {skipped}")


if __name__ == "__main__":
    main()

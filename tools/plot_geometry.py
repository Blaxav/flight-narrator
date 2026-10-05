#!/usr/bin/env python3
"""Génère une image SVG des polygones : régions (colorées) + villes (contour)
+ noeuds de vol (points), un panneau par continent (deux repères 0-100 distincts).

Sortie : geometry_map.svg à la racine du projet.
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
OUT = os.path.join(ROOT, "geometry_map.svg")

PALETTE = [
    "#e6194b", "#3cb44b", "#ffe119", "#4363d8", "#f58231", "#911eb4",
    "#46f0f0", "#f032e6", "#bcf60c", "#fabebe", "#008080", "#e6beff",
    "#9a6324", "#aaffc3", "#800000", "#ffd8b1", "#808000", "#7d5fa8",
    "#000075", "#5f9ea0", "#8b4513", "#c71585", "#2e8b57", "#ff69b4",
]


def collect():
    tree = {}
    for region in sorted(os.listdir(ZONES)):
        rd = os.path.join(ZONES, region)
        if not os.path.isdir(rd):
            continue
        for sub in sorted(os.listdir(rd)):
            gp = os.path.join(rd, sub, "geometry.txt")
            if os.path.isfile(gp):
                poly = geo.parse_geometry(gp)
                if poly:
                    tree.setdefault(region, {})[sub] = geo.normalize_clockwise(poly)
    return tree


def centroid(poly):
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def build_panel(tree, cont, nodes):
    """Renvoie le SVG d'un panneau continent."""
    regions = {r: s for r, s in tree.items()
               if gtz.REGION_CONTINENT.get(r) == cont and GENERAL in s}
    subzones = []
    for r, s in tree.items():
        if gtz.REGION_CONTINENT.get(r) != cont:
            continue
        for sub, poly in s.items():
            if sub != GENERAL:
                subzones.append((r, sub, poly))

    # bbox du continent (régions + noeuds)
    all_pts = [p for s in regions.values() for p in s[GENERAL]] + \
              [n["xy"] for n in nodes]
    minx = min(p[0] for p in all_pts) - 1
    maxx = max(p[0] for p in all_pts) + 1
    miny = min(p[1] for p in all_pts) - 1
    maxy = max(p[1] for p in all_pts) + 1

    W = 520
    M = 46
    TITLE = 34
    H = TITLE + (W - 2 * M) * (maxy - miny) / (maxx - minx) + 2 * M
    H = max(H, 500)

    def px(x):
        return M + (x - minx) / (maxx - minx) * (W - 2 * M)

    def py(y):
        return TITLE + (y - miny) / (maxy - miny) * (H - TITLE - 2 * M)

    parts = [f'<g transform="translate(0,0)">']
    parts.append(f'<text x="{W/2}" y="20" font-size="16" text-anchor="middle" '
                 f'font-family="sans-serif" font-weight="bold">{cont}</text>')

    # régions
    names = sorted(regions)
    for i, r in enumerate(names):
        color = PALETTE[i % len(PALETTE)]
        pts = " ".join(f"{px(x):.1f},{py(y):.1f}" for x, y in regions[r][GENERAL])
        parts.append(f'<polygon points="{pts}" fill="{color}" fill-opacity="0.55" '
                     f'stroke="#333" stroke-width="1"/>')
        cx, cy = centroid(regions[r][GENERAL])
        parts.append(f'<text x="{px(cx):.1f}" y="{py(cy):.1f}" font-size="11" '
                     f'text-anchor="middle" font-family="sans-serif" '
                     f'stroke="#fff" stroke-width="2.5" paint-order="stroke">{r}</text>')

    # villes / sous-zones
    for r, sub, poly in subzones:
        pts = " ".join(f"{px(x):.1f},{py(y):.1f}" for x, y in poly)
        parts.append(f'<polygon points="{pts}" fill="none" stroke="#666" '
                     f'stroke-width="1" stroke-dasharray="2,2"/>')

    # noeuds
    for n in nodes:
        parts.append(f'<circle cx="{px(n["xy"][0]):.1f}" cy="{py(n["xy"][1]):.1f}" '
                     f'r="2.4" fill="#000" stroke="#fff" stroke-width="0.6"/>')
    parts.append("</g>")
    return W, H, "".join(parts)


def main():
    tree = collect()
    positions = mt.node_map_positions()

    # noeuds par continent
    nodes = {0: [], 1: []}
    for eng, (mid, x, y) in positions.items():
        nodes[mid].append({"name": eng, "xy": (x, y)})

    panel_w = 520
    gap = 30
    k_w, k_h, k_svg = build_panel(tree, "Kalimdor", nodes[1])
    e_w, e_h, e_svg = build_panel(tree, "EK", nodes[0])

    total_w = k_w + gap + e_w
    total_h = max(k_h, e_h)

    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_w}" height="{total_h}" '
           f'viewBox="0 0 {total_w} {total_h}">']
    svg.append('<rect width="100%" height="100%" fill="#f7f7f7"/>')
    svg.append(f'<g transform="translate(0,0)">{k_svg}</g>')
    svg.append(f'<g transform="translate({k_w + gap},0)">{e_svg}</g>')
    svg.append("</svg>")

    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(svg))
    print(f"Écrit {OUT}  (régions={len([r for r in tree if GENERAL in tree[r]])})")


if __name__ == "__main__":
    main()

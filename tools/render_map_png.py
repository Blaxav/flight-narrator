#!/usr/bin/env python3
"""Rasterise les polygones de région + noeuds en geometry_map.png (sans dépendance).

Un panneau par continent, côte à côte. Remplissage via point-dans-polygone,
écriture PNG via zlib (bibliothèque standard).
"""
import os
import struct
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import geometry as geo
import map_transform as mt
import generate_travel_zones as gtz

ZONES = os.path.join(ROOT, "zones")
GENERAL = "Général"
OUT = os.path.join(ROOT, "geometry_map.png")

PALETTE = [
    "#e6194b", "#3cb44b", "#ffe119", "#4363d8", "#f58231", "#911eb4",
    "#46f0f0", "#f032e6", "#bcf60c", "#fabebe", "#008080", "#e6beff",
    "#9a6324", "#aaffc3", "#800000", "#ffd8b1", "#808000", "#7d5fa8",
    "#000075", "#5f9ea0", "#8b4513", "#c71585", "#2e8b57", "#ff69b4",
]


def hex_rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


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


def rasterize_continent(regions, nodes, scale):
    pts = [p for poly in regions.values() for p in poly] + nodes
    minx = min(p[0] for p in pts) - 1
    maxx = max(p[0] for p in pts) + 1
    miny = min(p[1] for p in pts) - 1
    maxy = max(p[1] for p in pts) + 1

    w = int((maxx - minx) * scale)
    h = int((maxy - miny) * scale)
    buf = bytearray([255]) * (w * h * 3)

    for i, r in enumerate(sorted(regions)):
        poly = regions[r]
        color = hex_rgb(PALETTE[i % len(PALETTE)])
        x0 = max(0, int((min(p[0] for p in poly) - minx) * scale))
        x1 = min(w, int((max(p[0] for p in poly) - minx) * scale) + 1)
        y0 = max(0, int((min(p[1] for p in poly) - miny) * scale))
        y1 = min(h, int((max(p[1] for p in poly) - miny) * scale) + 1)
        for py in range(y0, y1):
            my = miny + (py + 0.5) / scale
            for px in range(x0, x1):
                mx = minx + (px + 0.5) / scale
                if geo.point_in_polygon((mx, my), poly):
                    idx = (py * w + px) * 3
                    buf[idx] = color[0]
                    buf[idx + 1] = color[1]
                    buf[idx + 2] = color[2]

    for x, y in nodes:
        cx = int((x - minx) * scale)
        cy = int((y - miny) * scale)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                ix, iy = cx + dx, cy + dy
                if 0 <= ix < w and 0 <= iy < h:
                    idx = (iy * w + ix) * 3
                    buf[idx] = buf[idx + 1] = buf[idx + 2] = 0
    return w, h, buf


def write_png(path, w, h, buf):
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        raw.extend(buf[y * w * 3:(y + 1) * w * 3])
    comp = zlib.compress(bytes(raw), 9)

    def chunk(typ, data):
        out = struct.pack(">I", len(data)) + typ + data
        out += struct.pack(">I", zlib.crc32(typ + data) & 0xffffffff)
        return out

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", ihdr))
        f.write(chunk(b"IDAT", comp))
        f.write(chunk(b"IEND", b""))


def main():
    tree = collect()
    positions = mt.node_map_positions()
    nodes = {0: [], 1: []}
    for eng, (mid, x, y) in positions.items():
        nodes[mid].append((x, y))

    scale = 9
    panels = []
    for cont, node_list in (("Kalimdor", nodes[1]), ("EK", nodes[0])):
        regions = {r: s[GENERAL] for r, s in tree.items()
                   if gtz.REGION_CONTINENT.get(r) == cont and GENERAL in s}
        panels.append(rasterize_continent(regions, node_list, scale))

    gap = 14
    total_w = panels[0][0] + gap + panels[1][0]
    total_h = max(panels[0][1], panels[1][1])
    out = bytearray([255]) * (total_w * total_h * 3)
    for (w, h, buf), ox in ((panels[0], 0), (panels[1], panels[0][0] + gap)):
        for y in range(h):
            src = y * w * 3
            dst = (y * total_w + ox) * 3
            out[dst:dst + w * 3] = buf[src:src + w * 3]

    write_png(OUT, total_w, total_h, out)
    print(f"Écrit {OUT}  ({total_w}x{total_h}px)")


if __name__ == "__main__":
    main()

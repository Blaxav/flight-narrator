#!/usr/bin/env python3
"""Calibrer la transformation monde -> carte (continent) depuis quelques ancres
relevées en jeu, puis émettre les coordonnées carte de tous les noeuds de vol.

Les ancres sont des paires (noeud, coord_monde_x, coord_monde_y, map_x, map_y).
On ajuste une transformation affine (rotation + échelle + translation, avec
éventuelle réflexion) par moindres carrés, par continent (map=0 EK, map=1 Kalimdor).
"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FLIGHTDATA = os.path.join(ROOT, "FlightData.lua")

# (nom anglais du noeud, x_monde, y_monde, X_carte, Y_carte)
ANCHORS = {
    1: [  # Kalimdor
        ("Everlook, Winterspring", 6806.15, -4676.78, 59.0, 24.9),          # Long-guet
        ("Shadowprey Village, Desolace", -1767.64, 3263.89, 38.1, 59.1),    # Proie-de-l'Ombre
        ("Gadgetzan, Tanaris", -7136.43, -3757.48, 56.5, 81.6),
        ("Camp Mojache, Feralas", -4419.86, 199.31, 45.7, 70.4),
    ],
    0: [  # Royaumes de l'Est
        ("Undercity, Tirisfal", 1568.62, 267.97, 44.6, 24.4),
        ("Grom'gol, Stranglethorn", -12414.18, 146.29, 44.8, 84.9),
        ("Hammerfall, Arathi", -916.29, -3496.89, 55.5, 36.3),              # Trépas d'Orgrim
        ("Stonard, Swamp of Sorrows", -10456.97, -3279.25, 54.7, 76.7),
    ],
}


def solve3(a, b):
    """Résout un système 3x3 (élimination de Gauss avec pivot partiel)."""
    m = [list(row) + [b[i]] for i, row in enumerate(a)]  # augmentée 3x4
    n = 3
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[piv][col]) < 1e-12:
            raise ValueError("matrice singulière")
        m[col], m[piv] = m[piv], m[col]
        for r in range(col + 1, n):
            f = m[r][col] / m[col][col]
            for c in range(col, n + 1):
                m[r][c] -= f * m[col][c]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        s = m[i][n] - sum(m[i][j] * x[j] for j in range(i + 1, n))
        x[i] = s / m[i][i]
    return x


def fit_affine(pairs):
    """pairs: liste (wx, wy, mx, my). Retourne (m11,m12,tx, m21,m22,ty)."""
    def normal(rows):
        A = [[0.0] * 3 for _ in range(3)]
        b = [0.0] * 3
        for wx, wy, val in rows:
            row = [wx, wy, 1.0]
            for i in range(3):
                for j in range(3):
                    A[i][j] += row[i] * row[j]
                b[i] += row[i] * val
        return A, b

    A, bx = normal([(wx, wy, mx) for wx, wy, mx, my in pairs])
    A, by = normal([(wx, wy, my) for wx, wy, mx, my in pairs])
    cx = solve3(A, bx)  # [m11, m12, tx]
    cy = solve3(A, by)  # [m21, m22, ty]
    return cx[0], cx[1], cx[2], cy[0], cy[1], cy[2]


def parse_nodes(path):
    nodes = []
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            m = re.search(
                r'\[\d+\]\s*=\s*\{\s*name\s*=\s*"((?:[^"\\]|\\.)*)"\s*,\s*map\s*=\s*(\d+).*?'
                r'x\s*=\s*(-?[\d.]+)\s*,\s*y\s*=\s*(-?[\d.]+)\s*\}',
                line,
            )
            if m:
                name = m.group(1)
                map_id = int(m.group(2))
                x = float(m.group(3))
                y = float(m.group(4))
                nodes.append((name, map_id, x, y))
    return nodes


def main():
    nodes = parse_nodes(FLIGHTDATA)
    print(f"noeuds lus : {len(nodes)}\n")

    for map_id, anchors in sorted(ANCHORS.items()):
        label = "Kalimdor" if map_id == 1 else "Royaumes de l'Est"
        pairs = [(wx, wy, mx, my) for _n, wx, wy, mx, my in anchors]
        m11, m12, tx, m21, m22, ty = fit_affine(pairs)

        # décomposition : détection rotation vs réflexion, échelle, angle
        det = m11 * m22 - m12 * m21
        print(f"=== {label} (map={map_id}) ===")
        print(f"  matrice linéaire : [[{m11:+.6f}, {m12:+.6f}], [{m21:+.6f}, {m22:+.6f}]]  det={det:+.6f}")
        print(f"  translation      : ({tx:+.3f}, {ty:+.3f})")

        # échelle et angle (en supposant une similitude)
        s = (abs(det)) ** 0.5
        # rotation vs réflexion
        if det >= 0:
            # rotation pure : m11 = s cos, m21 = s sin
            import math
            theta = math.degrees(math.atan2(m21, m11))
            kind = "rotation"
        else:
            # réflexion : m11 = s cos, m21 = s sin (avec un axe)
            import math
            theta = math.degrees(math.atan2(m21, m11))
            kind = "réflexion"
        print(f"  échelle          : {s:.6f} yards -> 1 unité carte (1/{s:.4f} carte/yard)")
        print(f"  angle            : {theta:+.2f}° ({kind})")

        # résidus
        print("  résidus (prédit vs relevé) :")
        rms = 0.0
        for name, wx, wy, mx, my in anchors:
            px = m11 * wx + m12 * wy + tx
            py = m21 * wx + m22 * wy + ty
            ex = px - mx
            ey = py - my
            dist = (ex * ex + ey * ey) ** 0.5
            rms += dist * dist
            print(f"    {name:30s} -> carte=({px:6.2f},{py:6.2f})  relevé=({mx},{my})  "
                  f"écart={dist:.2f}")
        rms = (rms / len(anchors)) ** 0.5
        print(f"  RMS des écarts   : {rms:.3f} unités carte")

        # émettre les coordonnées carte de tous les noeuds de ce continent
        print("  coordonnées carte des noeuds :")
        cont_nodes = [n for n in nodes if n[1] == map_id]
        for name, _, wx, wy in sorted(cont_nodes, key=lambda n: n[0]):
            px = m11 * wx + m12 * wy + tx
            py = m21 * wx + m22 * wy + ty
            print(f"    {name:32s} ({px:6.2f}, {py:6.2f})")
        print()


if __name__ == "__main__":
    main()

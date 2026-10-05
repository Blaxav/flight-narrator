#!/usr/bin/env python3
"""Transformation monde -> carte continent, calibrée sur des ancres relevées en jeu.

FlightData.lua stocke les positions des nœuds de vol en yards (repère monde,
tourné ~90° + réfléchi par rapport à la carte). L'addon travaille en coordonnées
de carte continent (0-100, X est, Y sud). Ce module ajuste une transformation
affine par continent à partir de quelques ancres et expose les positions carte
de tous les nœuds.

Les ancres sont des paires (noeud_anglais, x_monde, y_monde, X_carte, Y_carte)
relevées dans la carte en jeu. On ajuste par moindres carrés (4 paramètres par
axe, donc 8 au total par continent).
"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FLIGHTDATA = os.path.join(ROOT, "FlightData.lua")

CONTINENTS = {0: "Eastern Kingdoms", 1: "Kalimdor"}

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


def _solve3(a, b):
    """Résout un système 3x3 (élimination de Gauss avec pivot partiel)."""
    m = [list(row) + [b[i]] for i, row in enumerate(a)]
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


def _fit_affine(pairs):
    """pairs: liste (wx, wy, mx, my). Retourne (m11, m12, tx, m21, m22, ty)."""
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
    cx = _solve3(A, bx)  # [m11, m12, tx]
    cy = _solve3(A, by)  # [m21, m22, ty]
    return cx[0], cx[1], cx[2], cy[0], cy[1], cy[2]


def _parse_nodes(path):
    """Renvoie la liste (nom, map_id, x_monde, y_monde) des nœuds de FlightData.lua."""
    nodes = []
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            m = re.search(
                r'\[\d+\]\s*=\s*\{\s*name\s*=\s*"((?:[^"\\]|\\.)*)"\s*,\s*map\s*=\s*(\d+).*?'
                r'x\s*=\s*(-?[\d.]+)\s*,\s*y\s*=\s*(-?[\d.]+)\s*\}',
                line,
            )
            if m:
                nodes.append((m.group(1), int(m.group(2)),
                              float(m.group(3)), float(m.group(4))))
    return nodes


def transforms():
    """Renvoie {map_id: (m11, m12, tx, m21, m22, ty)}."""
    out = {}
    for map_id, anchors in ANCHORS.items():
        pairs = [(wx, wy, mx, my) for _n, wx, wy, mx, my in anchors]
        out[map_id] = _fit_affine(pairs)
    return out


def map_coord(map_id, wx, wy):
    """Convertit (x_monde, y_monde) -> (X_carte, Y_carte) pour un continent."""
    m11, m12, tx, m21, m22, ty = transforms()[map_id]
    return m11 * wx + m12 * wy + tx, m21 * wx + m22 * wy + ty


def node_map_positions():
    """Renvoie {nom_anglais: (map_id, X_carte, Y_carte)} pour tous les nœuds."""
    tfs = transforms()
    out = {}
    for name, map_id, wx, wy in _parse_nodes(FLIGHTDATA):
        m11, m12, tx, m21, m22, ty = tfs[map_id]
        out[name] = (map_id, m11 * wx + m12 * wy + tx, m21 * wx + m22 * wy + ty)
    return out

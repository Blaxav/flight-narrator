#!/usr/bin/env python3
"""Utilitaires de géométrie pour le système geometry.txt.

Repère : la carte continent en jeu (0-100), X vers l'est, Y vers le sud.

Un polygone est une liste de tuples (x, y). Le sens canonique est le sens
HORAIRE ; dans ce repère (Y vers le bas), le sens horaire correspond à une
aire signée (formule du shoelace) POSITIVE.
"""


def parse_geometry(path):
    """Lit un geometry.txt en une liste de sommets (x, y).

    Format : un sommet par ligne, deux nombres séparés par ';', ',' ou espaces.
    Les lignes vides et celles commençant par '#' sont ignorées, ainsi que tout
    ce qui suit un '#' en fin de ligne.
    """
    verts = []
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            nums = _split_numbers(line)
            if len(nums) != 2:
                raise ValueError(f"{path}: ligne invalide : {line!r}")
            verts.append((float(nums[0]), float(nums[1])))
    return verts


def _split_numbers(line):
    for sep in (";", ",", "\t"):
        line = line.replace(sep, " ")
    return line.split()


def shoelace(poly):
    """Aire signée (2x). Positive = sens horaire dans ce repère (Y vers le bas)."""
    s = 0.0
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        s += x0 * y1 - x1 * y0
    return s


def area(poly):
    """Aire absolue du polygone."""
    return abs(shoelace(poly)) / 2.0


def is_clockwise(poly):
    """Vrai si le polygone est orienté dans le sens horaire."""
    return shoelace(poly) > 0


def normalize_clockwise(poly):
    """Renvoie le polygone en sens horaire (inverse si nécessaire)."""
    if shoelace(poly) < 0:
        return list(reversed(poly))
    return list(poly)


def bbox(poly):
    """Renvoie (min_x, min_y, max_x, max_y)."""
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


def _cross(o, a, b):
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _on_segment(p, q, r):
    """q est-il sur le segment p-r ?"""
    return (min(p[0], r[0]) <= q[0] <= max(p[0], r[0])
            and min(p[1], r[1]) <= q[1] <= max(p[1], r[1]))


def segments_intersect(p1, p2, p3, p4):
    """Les segments p1-p2 et p3-p4 se croisent-ils (y compris en se touchant) ?"""
    d1 = _cross(p3, p4, p1)
    d2 = _cross(p3, p4, p2)
    d3 = _cross(p1, p2, p3)
    d4 = _cross(p1, p2, p4)

    if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and \
       ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)):
        return True
    if d1 == 0 and _on_segment(p3, p1, p4):
        return True
    if d2 == 0 and _on_segment(p3, p2, p4):
        return True
    if d3 == 0 and _on_segment(p1, p3, p2):
        return True
    if d4 == 0 and _on_segment(p1, p4, p2):
        return True
    return False


def segments_properly_intersect(p1, p2, p3, p4):
    """Vrai si les segments se CROISENT proprement (intérieurs, pas juste en se touchant)."""
    d1 = _cross(p3, p4, p1)
    d2 = _cross(p3, p4, p2)
    d3 = _cross(p1, p2, p3)
    d4 = _cross(p1, p2, p4)
    return ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and \
           ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0))


def is_simple(poly):
    """Vrai si le polygone est simple (pas d'auto-intersection), >= 3 sommets."""
    n = len(poly)
    if n < 3:
        return False
    for i in range(n):
        a1, a2 = poly[i], poly[(i + 1) % n]
        for j in range(i + 1, n):
            # les arêtes adjacentes (qui partagent un sommet) sont ignorées
            if j == i + 1 or (i == 0 and j == n - 1):
                continue
            b1, b2 = poly[j], poly[(j + 1) % n]
            if segments_intersect(a1, a2, b1, b2):
                return False
    return True


def point_in_polygon(pt, poly):
    """Ray casting : vrai si pt est à l'intérieur du polygone (ou sur sa frontière)."""
    x, y = pt
    n = len(poly)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def on_boundary(pt, poly):
    """Vrai si pt est exactement sur un sommet ou une arête du polygone."""
    x, y = pt
    n = len(poly)
    for i in range(n):
        ax, ay = poly[i]
        bx, by = poly[(i + 1) % n]
        cross = (bx - ax) * (y - ay) - (by - ay) * (x - ax)
        if abs(cross) < 1e-9 and min(ax, bx) <= x <= max(ax, bx) \
                and min(ay, by) <= y <= max(ay, by):
            return True
    return False


def point_strictly_inside(pt, poly):
    """Vrai si pt est à l'intérieur strict (pas sur la frontière)."""
    return point_in_polygon(pt, poly) and not on_boundary(pt, poly)


def polygons_overlap(a, b):
    """Vrai si a et b partagent une surface (intérieurs qui se recoupent).

    Deux polygones qui ne font que se toucher (arête ou sommet partagé) ne
    sont PAS considérés comme se chevauchant : c'est le cas du pavage.
    """
    for p in a:
        if point_strictly_inside(p, b):
            return True
    for p in b:
        if point_strictly_inside(p, a):
            return True
    n, m = len(a), len(b)
    for i in range(n):
        a1, a2 = a[i], a[(i + 1) % n]
        for j in range(m):
            b1, b2 = b[j], b[(j + 1) % m]
            if segments_properly_intersect(a1, a2, b1, b2):
                return True
    return False


def polygon_contains(outer, inner):
    """Vrai si inner est entièrement inclus dans outer (frontière partagée tolérée)."""
    for p in inner:
        if not point_in_polygon(p, outer):
            return False
    n, m = len(outer), len(inner)
    for i in range(n):
        a1, a2 = outer[i], outer[(i + 1) % n]
        for j in range(m):
            b1, b2 = inner[j], inner[(j + 1) % m]
            if segments_properly_intersect(a1, a2, b1, b2):
                return False
    return True


def coverage_fraction(polygons, step=1.0):
    """Fraction (approximative) d'une boîte englobante couverte par les polygones.

    Échantillonne une grille régulière sur la boîte englobante de l'union des
    polygones et compte les points tombant dans au moins un polygone. Métrique
    indicative uniquement (océan et zones vides comptent comme non couverts).
    """
    if not polygons:
        return 0.0, None
    boxes = [bbox(p) for p in polygons]
    minx = min(b[0] for b in boxes)
    miny = min(b[1] for b in boxes)
    maxx = max(b[2] for b in boxes)
    maxy = max(b[3] for b in boxes)
    w = maxx - minx
    h = maxy - miny
    if w <= 0 or h <= 0:
        return 0.0, (minx, miny, maxx, maxy)

    xs = [minx + step / 2 + i * step for i in range(int(w / step) + 1)]
    ys = [miny + step / 2 + i * step for i in range(int(h / step) + 1)]
    total = 0
    covered = 0
    for x in xs:
        for y in ys:
            total += 1
            if any(point_in_polygon((x, y), p) for p in polygons):
                covered += 1
    return covered / total, (minx, miny, maxx, maxy)

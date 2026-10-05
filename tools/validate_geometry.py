#!/usr/bin/env python3
"""Valide les polygones geometry.txt sous zones/.

Vérifie, par fichier :
  - le polygone se parse, a >= 3 sommets, est simple (pas d'auto-intersection) ;
  - l'orientation est signalée (horaire attendu).
Puis, au niveau régions (Général) :
  - deux régions d'un même continent ne se chevauchent pas ;
  - chaque sous-zone est incluse dans le polygone Général de sa région ;
  - une couverture (approximative) par continent est affichée.

Sortie : liste des problèmes, puis code de sortie non nul si une erreur
(chevauchenrent ou polygone invalide) est détectée.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import geometry as geo          # noqa: E402
import generate_travel_zones as gtz  # noqa: E402  (REGION_CONTINENT)

ZONES = os.path.join(ROOT, "zones")
GENERAL = "Général"


def collect():
    """Renvoie {region: {subzone: [ (x,y), ... ]}} pour chaque geometry.txt."""
    tree = {}
    for region in sorted(os.listdir(ZONES)):
        rd = os.path.join(ZONES, region)
        if not os.path.isdir(rd):
            continue
        for sub in sorted(os.listdir(rd)):
            gp = os.path.join(rd, sub, "geometry.txt")
            if os.path.isfile(gp):
                tree.setdefault(region, {})[sub] = geo.parse_geometry(gp)
    return tree


def main():
    tree = collect()
    errors = []
    warnings = []

    print("=== Validité des polygones ===")
    n_poly = 0
    n_empty = 0
    for region in sorted(tree):
        for sub in sorted(tree[region]):
            poly = tree[region][sub]
            label = f"{region}/{sub}"
            if not poly:
                n_empty += 1
                print(f"  .   {label:42s} (vide — à remplir)")
                continue
            n_poly += 1
            if len(poly) < 3:
                errors.append((label, f"moins de 3 sommets ({len(poly)})"))
                continue
            if not geo.is_simple(poly):
                errors.append((label, "auto-intersection"))
                continue
            wind = "horaire" if geo.is_clockwise(poly) else "ANTI-horaire"
            flag = "" if geo.is_clockwise(poly) else "  <-- inverser"
            print(f"  OK  {label:42s} {len(poly):2d} sommets  aire={geo.area(poly):6.1f}  {wind}{flag}")

    # --- chevauchement des régions (Général), par continent ---
    print("\n=== Chevauchement des régions (Général) ===")
    regions_by_cont = {}
    for region, subs in tree.items():
        if GENERAL not in subs or not subs[GENERAL]:
            continue
        cont = gtz.REGION_CONTINENT.get(region, "?")
        regions_by_cont.setdefault(cont, []).append(region)

    n_overlap = 0
    for cont in sorted(regions_by_cont):
        regs = regions_by_cont[cont]
        for i in range(len(regs)):
            for j in range(i + 1, len(regs)):
                a, b = regs[i], regs[j]
                if geo.polygons_overlap(tree[a][GENERAL], tree[b][GENERAL]):
                    n_overlap += 1
                    errors.append((f"{a} <-> {b}", f"chevauchement de régions ({cont})"))
    if n_overlap == 0:
        print("  OK  aucun chevauchement entre régions.")

    # --- inclusion des sous-zones dans leur région (toléré) ---
    print("\n=== Sous-zones hors de leur région (toléré) ===")
    n_contain_viol = 0
    for region, subs in tree.items():
        outer = subs.get(GENERAL)
        if not outer:
            continue
        for sub in sorted(subs):
            if sub == GENERAL or not subs[sub]:
                continue
            if not geo.polygon_contains(outer, subs[sub]):
                n_contain_viol += 1
    if n_contain_viol == 0:
        print("  OK  toutes les sous-zones sont dans leur région.")
    else:
        print(f"  info : {n_contain_viol} sous-zone(s) débordent (toléré — villes/donjons frontaliers).")

    # --- couverture par continent ---
    print("\n=== Couverture (indicative) ===")
    for cont in sorted(regions_by_cont):
        polys = [tree[r][GENERAL] for r in regions_by_cont[cont] if tree[r][GENERAL]]
        frac, bb = geo.coverage_fraction(polys)
        bb_s = f" bbox=({bb[0]:.1f},{bb[1]:.1f})..({bb[2]:.1f},{bb[3]:.1f})" if bb else ""
        print(f"  {cont:18s} régions={len(polys):2d}  couverture ~{frac*100:4.0f}%{bb_s}")

    print()
    print(f"Polygones : {n_poly} définis, {n_empty} vides.")
    print(f"Erreurs   : {len(errors)}")
    print(f"Warnings  : {len(warnings)}")
    for label, why in errors:
        print(f"  ERROR {label} : {why}")

    if errors:
        raise SystemExit(1)
    print("OK : géométrie valide.")


if __name__ == "__main__":
    main()

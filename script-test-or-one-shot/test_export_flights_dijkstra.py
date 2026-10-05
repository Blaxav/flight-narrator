#!/usr/bin/env python3
"""
gen_flightdata.py - Génère FlightData.lua (routes de vol Classic Era) à partir
des tables du jeu TaxiNodes / TaxiPath / TaxiPathNode.

Pipeline locale (--wow-dir) :
  1. Lit .build.info de votre installation et repère la build wow_classic_era
  2. Extrait les 3 fichiers .db2 du CASC local avec TACTTool (par FileDataID)
  3. Met à jour les définitions WoWDBDefs et convertit les .db2 en CSV avec DBC2CSV
  4. Construit le graphe de vol, un par faction (Horde / Alliance)
  5. Dijkstra depuis chaque point de vol -> étapes réelles vers chaque destination
  6. Écrit FlightData.lua

Sources alternatives : --csv-dir (CSV déjà prêts) ou, sans --wow-dir, téléchargement
des CSV depuis wago.tools.

Prérequis pour --wow-dir : le runtime .NET et deux outils à télécharger une fois :
  - TACTTool  (https://github.com/wowdev/TACTSharp)
  - DBC2CSV   (https://github.com/Marlamin/DBC2CSV)

Exemples :
  python gen_flightdata.py --wow-dir "C:/Program Files (x86)/World of Warcraft" \\
         --tacttool C:/outils/TACTTool.exe --dbc2csv C:/outils/DBC2CSV/DBC2CSV.exe
  python gen_flightdata.py --route "Orgrimmar" "Sun Rock"   (vérification rapide)
  python gen_flightdata.py --list-nodes                      (revue des points de vol)
"""
import argparse
import csv
import heapq
import json
import math
import re
import shlex
import subprocess
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

WAGO = "https://wago.tools"
USER_AGENT = "Mozilla/5.0 (compatible; FlightDataGenerator/1.0)"
FLAG_ALLIANCE = 0x1  # bits de faction dans TaxiNodes.Flags (à valider via --list-nodes)
FLAG_HORDE = 0x2
DBD_RAW = "https://raw.githubusercontent.com/wowdev/WoWDBDefs/master"
TABLES = ["TaxiNodes", "TaxiPath", "TaxiPathNode"]
# FileDataID des .db2 (tirés de manifest.json de WoWDBDefs ; surchargeables avec --fdid)
DEFAULT_FDIDS = {"TaxiNodes": 1068100, "TaxiPath": 1067802, "TaxiPathNode": 1000437}
JUNK_NAME = re.compile(
    r"\b(test|deprecated|unused|dnt|transport|generic|programmer|quest|"
    r"zepp(elin|lin)s?|ferry|tower|naxxramas)\b",
    re.I,
)


# --------------------------------------------------------------------------
# 1. Résolution de la build + téléchargement
# --------------------------------------------------------------------------
def http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def version_key(v):
    return tuple(int(p) for p in re.findall(r"\d+", v))


def find_latest_era_build():
    """Cherche la dernière build 'wow_classic_era' dans l'API de builds de wago."""
    raw = json.loads(http_get(f"{WAGO}/api/builds"))
    found = []

    def walk(o):
        if isinstance(o, dict):
            if o.get("product") == "wow_classic_era" and "version" in o:
                found.append(o["version"])
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(raw)
    if not found:
        raise RuntimeError("Aucune build wow_classic_era trouvée dans la réponse de wago.")
    return max(found, key=version_key)


def fetch_table(table, build, cache_dir):
    path = cache_dir / f"{table}.csv"
    if path.exists():
        return path
    url = f"{WAGO}/db2/{table}/csv?build={build}"
    print(f"  téléchargement {url}")
    try:
        data = http_get(url)
    except urllib.error.HTTPError as e:
        raise RuntimeError(
            f"HTTP {e.code} sur {url}.\n"
            "wago.tools est protégé contre les bots et peut refuser certaines connexions.\n"
            f"Solution : ouvrez l'URL dans votre navigateur, enregistrez le CSV sous\n  {path}\n"
            "puis relancez (ou utilisez --csv-dir)."
        )
    if data.lstrip()[:15].lower().startswith((b"<!doctype", b"<html")):
        raise RuntimeError(f"wago a renvoyé une page HTML au lieu d'un CSV pour {table} (protection anti-bot).")
    cache_dir.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def load_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def get(row, *names, default=None):
    """Lit la première colonne existante parmi plusieurs noms possibles."""
    for n in names:
        if n in row and row[n] != "":
            return row[n]
    return default


# --------------------------------------------------------------------------
# 1bis. Extraction depuis l'installation locale (CASC -> .db2 -> .csv)
# --------------------------------------------------------------------------
def run(cmd, cwd=None):
    print("  $ " + " ".join(str(c) for c in cmd))
    try:
        subprocess.run([str(c) for c in cmd], cwd=cwd, check=True)
    except FileNotFoundError:
        raise RuntimeError(f"Programme introuvable : {cmd[0]} (vérifiez le chemin ou le runtime .NET).")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"La commande a échoué (code {e.returncode}) : {cmd[0]}")


def read_era_version(wow_dir):
    """Lit .build.info et retourne la version du produit wow_classic_era."""
    info = wow_dir / ".build.info"
    if not info.exists():
        raise RuntimeError(f"{info} introuvable : --wow-dir doit pointer sur le dossier racine de WoW.")
    lines = info.read_text(encoding="utf-8", errors="replace").splitlines()
    cols = [c.split("!")[0] for c in lines[0].split("|")]
    products = []
    for line in lines[1:]:
        row = dict(zip(cols, line.split("|")))
        products.append(row.get("Product"))
        if row.get("Product") == "wow_classic_era":
            return row.get("Version")
    raise RuntimeError(f"Pas de produit wow_classic_era dans .build.info (trouvé : {products}).")


def update_definitions(dbc2csv):
    """Met à jour les .dbd de DBC2CSV (ceux livrés sont souvent trop anciens pour 1.15.x)."""
    d = Path(dbc2csv).resolve().parent / "definitions"
    d.mkdir(exist_ok=True)
    for t in TABLES:
        (d / f"{t}.dbd").write_bytes(http_get(f"{DBD_RAW}/definitions/{t}.dbd"))
    print(f"  définitions WoWDBDefs mises à jour dans {d}")


def extract_local(args):
    wow_dir = Path(args.wow_dir)
    version = read_era_version(wow_dir)
    print(f"Installation : {wow_dir}  |  Classic Era {version}")
    out = (Path(args.cache_dir) / f"era-{version}").resolve()
    out.mkdir(parents=True, exist_ok=True)

    fdids = dict(DEFAULT_FDIDS)
    for item in filter(None, args.fdid.split(",")):
        name, val = item.split("=")
        fdids[name.strip()] = int(val)

    tables = [t for t in TABLES if not (t == "TaxiPathNode" and args.weight == "cost")]
    extra = shlex.split(args.tacttool_args)
    for t in tables:
        db2 = out / f"{t}.db2"
        if not db2.exists() or db2.stat().st_size == 0:
            run([args.tacttool, "-p", "wow_classic_era", "-m", "fdid", "-i", fdids[t],
                 "-o", db2, "-d", wow_dir] + extra)
        if not db2.exists() or db2.stat().st_size == 0:
            raise RuntimeError(f"Extraction de {t}.db2 échouée (FileDataID {fdids[t]}). "
                               "Essayez --fdid ou consultez TACTTool --help.")

    if not args.no_update_defs:
        try:
            update_definitions(args.dbc2csv)
        except (urllib.error.URLError, OSError) as e:
            print(f"  (avertissement) définitions non mises à jour : {e}")
    for t in tables:  # DBC2CSV doit tourner sur un dossier ne contenant que ce qu'on veut
        (out / f"{t}.csv").unlink(missing_ok=True)
    run([args.dbc2csv, out], cwd=Path(args.dbc2csv).resolve().parent)
    for t in tables:
        if not (out / f"{t}.csv").exists():
            raise RuntimeError(f"DBC2CSV n'a pas produit {t}.csv (définition manquante pour cette build ?).")
    return out, version


# --------------------------------------------------------------------------
# 2. Modèle de données
# --------------------------------------------------------------------------
def parse_nodes(rows, continents):
    nodes = {}
    for r in rows:
        nid = int(get(r, "ID"))
        name = (get(r, "Name_lang", "Name", default="") or "").strip()
        cont = int(get(r, "ContinentID", "Map", default=-1))
        flags = int(get(r, "Flags", default=0))
        if not name or JUNK_NAME.search(name) or cont not in continents:
            continue
        # La faction est encodée dans TaxiNodes.Flags (0x1 = Alliance, 0x2 = Horde).
        # MountCreatureID_* n'est pas fiable par faction (ex. Northshire Abbey ->
        # monture 308 lue comme "Horde" alors que c'est un nœud Alliance).
        a, h = bool(flags & FLAG_ALLIANCE), bool(flags & FLAG_HORDE)
        if a and not h:
            faction = "A"
        elif h and not a:
            faction = "H"
        else:
            faction = "N"  # neutre (les deux, ou aucun indice)
        nodes[nid] = {
            "name": name,
            "map": cont,
            "faction": faction,
            "x": float(get(r, "Pos_0", "PosX", default=0)),
            "y": float(get(r, "Pos_1", "PosY", default=0)),
            "z": float(get(r, "Pos_2", "PosZ", default=0)),
        }
    return nodes


def merge_duplicate_nodes(nodes):
    """Fusionne les nœuds portant le même nom (villes neutres dupliquées par
    faction dans le DBC : Booty Bay, Gadgetzan, Everlook, ...) en un seul nœud
    neutre. Renvoie (nœuds fusionnés, {ancien_id: id_canonique})."""
    by_name = defaultdict(list)
    for nid, n in nodes.items():
        by_name[n["name"]].append(nid)
    merged, canonical = {}, {}
    for name, ids in by_name.items():
        if len(ids) == 1:
            merged[ids[0]] = nodes[ids[0]]
            canonical[ids[0]] = ids[0]
            continue
        keep = min(ids)
        xs = [nodes[i]["x"] for i in ids]
        ys = [nodes[i]["y"] for i in ids]
        zs = [nodes[i]["z"] for i in ids]
        merged[keep] = {
            "name": name,
            "map": nodes[keep]["map"],
            "faction": "N",  # ville desservie par les deux factions
            "x": sum(xs) / len(xs),
            "y": sum(ys) / len(ys),
            "z": sum(zs) / len(zs),
        }
        for i in ids:
            canonical[i] = keep
    return merged, canonical


def path_lengths(rows):
    """Longueur 3D de chaque TaxiPath (somme des segments de TaxiPathNode)."""
    by_path = defaultdict(list)
    for r in rows:
        by_path[int(get(r, "PathID"))].append((
            int(get(r, "NodeIndex", default=0)),
            float(get(r, "Loc_0", "LocX", default=0)),
            float(get(r, "Loc_1", "LocY", default=0)),
            float(get(r, "Loc_2", "LocZ", default=0)),
        ))
    out = {}
    for pid, pts in by_path.items():
        pts.sort()
        out[pid] = sum(math.dist(a[1:], b[1:]) for a, b in zip(pts, pts[1:]))
    return out


def build_edges(path_rows, nodes, lengths, weight, canonical=None):
    """Retourne {(src, dst): poids}, en gardant la liaison la moins chère."""
    canonical = canonical or {}
    edges = {}
    for r in path_rows:
        a, b = int(get(r, "FromTaxiNode")), int(get(r, "ToTaxiNode"))
        a, b = canonical.get(a, a), canonical.get(b, b)
        if a not in nodes or b not in nodes or a == b:
            continue
        if weight == "cost":
            w = int(get(r, "Cost", default=0))
        else:
            w = lengths.get(int(get(r, "ID")), 0.0)
        if (a, b) not in edges or w < edges[(a, b)]:
            edges[(a, b)] = w
    return edges


# --------------------------------------------------------------------------
# 3. Dijkstra
# --------------------------------------------------------------------------
def allowed(node, side):
    return node["faction"] in ("N", side)


def routes_for(side, nodes, edges):
    ids = {n for n, v in nodes.items() if allowed(v, side)}
    adj = defaultdict(list)
    for (a, b), w in sorted(edges.items()):
        if a in ids and b in ids:
            adj[a].append((b, w))

    result = {}
    for src in sorted(ids):
        best = {src: (0, 0)}  # (poids, nombre de tronçons)
        prev = {}
        pq = [(0, 0, src)]
        while pq:
            w, hops, u = heapq.heappop(pq)
            if (w, hops) > best[u]:
                continue
            for v, ew in adj[u]:
                cand = (w + ew, hops + 1)
                if v not in best or cand < best[v]:
                    best[v] = cand
                    prev[v] = u
                    heapq.heappush(pq, (cand[0], cand[1], v))
        table = {}
        for dst in best:
            if dst == src:
                continue
            steps, cur = [dst], dst
            while prev[cur] != src:
                cur = prev[cur]
                steps.append(cur)
            table[dst] = steps[::-1]  # escales puis destination finale
        result[src] = table
    return result


# --------------------------------------------------------------------------
# 4. Export Lua
# --------------------------------------------------------------------------
def lua_str(s):
    return json.dumps(s, ensure_ascii=False)


def write_lua(path, build, weight, nodes, routes_by_side):
    with open(path, "w", encoding="utf-8", newline="\n") as o:
        o.write("-- Fichier généré par gen_flightdata.py - ne pas éditer à la main\n")
        o.write("FlightData = {\n")
        o.write(f"  build = {lua_str(build)},\n  weight = {lua_str(weight)},\n")
        o.write("  -- [id] = { name, map, faction (H/A/N), x, y }\n  nodes = {\n")
        used = set()
        for side in routes_by_side.values():
            for src, t in side.items():
                used.add(src)
                used.update(t)
        for nid in sorted(used):
            n = nodes[nid]
            o.write(f"    [{nid}] = {{ name = {lua_str(n['name'])}, map = {n['map']}, "
                    f"faction = \"{n['faction']}\", x = {n['x']:.2f}, y = {n['y']:.2f} }},\n")
        o.write("  },\n  -- routes[faction][depart][arrivee] = { escale1, escale2, ..., arrivee }\n  routes = {\n")
        for side_name, side in routes_by_side.items():
            o.write(f"    {side_name} = {{\n")
            for src in sorted(side):
                o.write(f"      [{src}] = {{\n")
                for dst in sorted(side[src]):
                    o.write(f"        [{dst}] = {{{', '.join(map(str, side[src][dst]))}}},\n")
                o.write("      },\n")
            o.write("    },\n")
        o.write("  },\n}\n")


def dump_routes(path, nodes, routes):
    """Écrit toutes les routes (noms lisibles) dans un fichier texte, une ligne
    par liaison orientée, groupées par faction et triées par nom."""
    lines, total = [], 0
    for side in ("Horde", "Alliance"):
        table = routes[side]
        entries = []
        for src in table:
            for dst in table[src]:
                chain = [nodes[src]["name"]] + [nodes[i]["name"] for i in table[src][dst]]
                entries.append((nodes[src]["name"], nodes[dst]["name"], chain))
        entries.sort()
        lines.append(f"{side} ({len(entries)} routes) :")
        for _, _, chain in entries:
            lines.append("  " + " -> ".join(chain))
        lines.append("")
        total += len(entries)
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{total} routes écrites dans {path}")


# --------------------------------------------------------------------------
# 5. Programme principal
# --------------------------------------------------------------------------
def find_node(nodes, text):
    t = text.lower()
    hits = [i for i, n in nodes.items() if t in n["name"].lower()]
    if not hits:
        sys.exit(f"Aucun point de vol ne contient '{text}'.")
    return hits


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wow-dir", help="dossier racine de WoW (contient .build.info) : lecture locale du CASC")
    ap.add_argument("--tacttool", default="TACTTool", help="chemin de TACTTool (défaut : dans le PATH)")
    ap.add_argument("--dbc2csv", default="DBC2CSV", help="chemin de DBC2CSV (défaut : dans le PATH)")
    ap.add_argument("--tacttool-args", default="", help="arguments supplémentaires passés à TACTTool")
    ap.add_argument("--fdid", default="", help="surcharge des FileDataID, ex. TaxiNodes=123,TaxiPath=456")
    ap.add_argument("--no-update-defs", action="store_true", help="ne pas mettre à jour les .dbd de DBC2CSV")
    ap.add_argument("--build", help="(mode wago) build Classic Era, ex. 1.15.9.70003. Défaut : la dernière.")
    ap.add_argument("--csv-dir", help="dossier contenant déjà TaxiNodes.csv, TaxiPath.csv (et TaxiPathNode.csv)")
    ap.add_argument("--cache-dir", default="cache", help="dossier de cache des téléchargements")
    ap.add_argument("--weight", choices=["cost", "distance"], default="distance",
                    help="critère du plus court chemin (défaut : distance). "
                         "'cost' est le tarif (Price) et ne reflète pas la route réelle.")
    ap.add_argument("--continents", default="0,1", help="IDs de continents gardés (défaut : 0,1)")
    ap.add_argument("--exclude", default="", help="IDs de points de vol à exclure, séparés par des virgules")
    ap.add_argument("--out", default="FlightData.lua")
    ap.add_argument("--list-nodes", action="store_true", help="affiche les points de vol retenus et quitte")
    ap.add_argument("--route", nargs=2, metavar=("DEPART", "ARRIVEE"),
                    help="affiche une route (recherche par nom anglais) et quitte")
    ap.add_argument("--dump-routes", nargs="?", const="routes.txt", metavar="FICHIER",
                    help="écrit toutes les routes (noms lisibles) dans FICHIER "
                         "(défaut : routes.txt) et quitte")
    args = ap.parse_args()

    # --- sources
    if args.csv_dir:
        src_dir, build = Path(args.csv_dir), args.build or "local"
    elif args.wow_dir:
        src_dir, build = extract_local(args)
    else:
        build = args.build or find_latest_era_build()
        print(f"Build : {build}")
        src_dir = Path(args.cache_dir) / build
        wanted = ["TaxiNodes", "TaxiPath"] + (["TaxiPathNode"] if args.weight == "distance" else [])
        for t in wanted:
            fetch_table(t, build, src_dir)

    # --- chargement
    continents = {int(c) for c in args.continents.split(",")}
    nodes = parse_nodes(load_csv(src_dir / "TaxiNodes.csv"), continents)
    for bad in filter(None, args.exclude.split(",")):
        nodes.pop(int(bad), None)
    nodes, canonical = merge_duplicate_nodes(nodes)
    lengths = {}
    if args.weight == "distance":
        lengths = path_lengths(load_csv(src_dir / "TaxiPathNode.csv"))
    edges = build_edges(load_csv(src_dir / "TaxiPath.csv"), nodes, lengths, args.weight, canonical)

    # --- calcul
    routes = {"Horde": routes_for("H", nodes, edges), "Alliance": routes_for("A", nodes, edges)}

    if args.list_nodes:
        for nid in sorted(nodes, key=lambda i: (nodes[i]["faction"], nodes[i]["name"])):
            n = nodes[nid]
            print(f"{n['faction']}  {nid:5d}  map {n['map']}  {n['name']}")
        return

    if args.route:
        a_ids, b_ids = find_node(nodes, args.route[0]), find_node(nodes, args.route[1])
        for side, table in routes.items():
            for a in a_ids:
                for b in b_ids:
                    if b in table.get(a, {}):
                        chain = [a] + table[a][b]
                        print(f"{side:8s}: " + " -> ".join(nodes[i]["name"] for i in chain))
        return

    if args.dump_routes:
        dump_routes(args.dump_routes, nodes, routes)
        return

    # --- export
    write_lua(args.out, build, args.weight, nodes, routes)
    counts = {s: sum(1 for v in nodes.values() if v["faction"] in ("N", s[0])) for s in routes}
    print(f"{len(nodes)} points de vol retenus ({counts['Horde']} Horde, {counts['Alliance']} Alliance, incluant les neutres)")
    print(f"{len(edges)} liaisons directes. Fichier écrit : {args.out}")
    print("Pensez à vérifier : --list-nodes (factions, points propres à la Saison des Découvertes) "
          "et --route \"Orgrimmar\" \"Sun Rock\" (doit passer par Crossroads).")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        sys.exit(f"Erreur : {e}")
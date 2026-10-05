#!/usr/bin/env python3
"""Serve the zone polygon calibrator web app.

Run:
    python tools/zone_calibrator/server.py

Then open http://127.0.0.1:8000 in a browser.

Single view:
- The continent map image is shown and calibrated by dragging the flight-route
  nodes (pastilles) onto their real town locations. A least-squares
  axis-aligned anisotropic scale + translation fit (no rotation, no shear)
  maps image pixels -> 0-100 coordinates.
- Overlay the zones/**/geometry.txt polygons and drag vertices / split edges.
  "Sauvegarder" writes the polygons back to their original geometry.txt files.

Only the Python standard library is required.
"""
import json
import os
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import geometry as geo
import map_transform as mt
import generate_travel_zones as gtz
import generate_travel_data as gend

ZONES = os.path.join(ROOT, "zones")
GENERAL = "Général"
INDEX = os.path.join(HERE, "index.html")
APPJS = os.path.join(HERE, "app.js")

# Continent -> candidate map images (first existing file wins). The Kalimdor
# image is optional: the user can load one from the browser instead.
MAP_IMAGES = {
    "Kalimdor": [
        os.path.join(ROOT, "kalimdor_map.webp"),
        os.path.join(ROOT, "kalimdor_map.jpg"),
        os.path.join(ROOT, "kalimdor_map.png"),
        os.path.join(ROOT, "kalimdor_map.jpeg"),
    ],
    "EK": [os.path.join(ROOT, "eastern_map.jpg")],
}

MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
}

_config_cache = None


def collect_zones():
    """Return every polygon as {region, subzone, continent, vertices}."""
    out = []
    for region in sorted(os.listdir(ZONES)):
        rd = os.path.join(ZONES, region)
        if not os.path.isdir(rd):
            continue
        cont = gtz.REGION_CONTINENT.get(region, "unknown")
        for sub in sorted(os.listdir(rd)):
            gp = os.path.join(rd, sub, "geometry.txt")
            if not os.path.isfile(gp):
                continue
            try:
                verts = geo.parse_geometry(gp)
            except (OSError, ValueError):
                verts = []
            out.append({
                "region": region,
                "subzone": sub,
                "continent": cont,
                "vertices": [[round(x, 4), round(y, 4)] for x, y in verts],
            })
    return out


_node_data = None


def _nodes():
    """Return ({eng: (map_id, x, y)}, {eng: french}) computed once."""
    global _node_data
    if _node_data is None:
        _node_data = (mt.node_map_positions(), gend.build_node_names()[0])
    return _node_data


def calibration_towns():
    """Return {continent: [{name, eng, x, y}]} for every flight node."""
    positions, fr_en = _nodes()
    towns = {"EK": [], "Kalimdor": []}
    for eng, (mid, x, y) in positions.items():
        cont = "Kalimdor" if mid == 1 else "EK"
        towns[cont].append({
            "name": fr_en.get(eng, eng),
            "eng": eng,
            "x": round(x, 3),
            "y": round(y, 3),
        })
    for cont in towns:
        towns[cont].sort(key=lambda t: t["name"].lower())
    return towns


TRAVELS_DIR = os.path.join(ROOT, "travels")


def collect_routes():
    """Return {faction: [{src, dst, continent, segments}]} for every flight.

    ``segments`` is a list of [x1, y1, x2, y2] in 0-100 continent coordinates.
    """
    positions, fr_en = _nodes()
    fr_to_pos = {fr: positions[eng] for eng, fr in fr_en.items()
                 if eng in positions}
    routes = {"alliance": [], "horde": []}
    for faction in ("alliance", "horde"):
        fdir = os.path.join(TRAVELS_DIR, faction)
        if not os.path.isdir(fdir):
            continue
        for src in sorted(os.listdir(fdir)):
            sdir = os.path.join(fdir, src)
            if not os.path.isdir(sdir):
                continue
            for dst in sorted(os.listdir(sdir)):
                ddir = os.path.join(sdir, dst)
                if not os.path.isdir(ddir):
                    continue
                steps_path = os.path.join(ddir, "steps.txt")
                if os.path.isfile(steps_path):
                    with open(steps_path, encoding="utf-8-sig") as f:
                        steps = [ln.strip() for ln in f.read().splitlines()
                                 if ln.strip()]
                else:
                    steps = [dst]
                chain = [src] + steps
                segments, cont = [], None
                for a, b in zip(chain, chain[1:]):
                    pa, pb = fr_to_pos.get(a), fr_to_pos.get(b)
                    if not pa or not pb or pa[0] != pb[0]:
                        continue
                    segments.append([round(pa[1], 3), round(pa[2], 3),
                                     round(pb[1], 3), round(pb[2], 3)])
                    cont = "Kalimdor" if pa[0] == 1 else "EK"
                if segments:
                    routes[faction].append({
                        "src": src, "dst": dst, "continent": cont,
                        "segments": segments,
                    })
    return routes

def get_config():
    global _config_cache
    if _config_cache is None:
        maps = {c: any(os.path.isfile(p) for p in paths)
                for c, paths in MAP_IMAGES.items()}
        _config_cache = {
            "continents": ["Kalimdor", "EK"],
            "general": GENERAL,
            "zones": collect_zones(),
            "towns": calibration_towns(),
            "routes": collect_routes(),
            "maps": maps,
        }
    return _config_cache


def _fmt(v):
    v = round(float(v), 3)
    s = f"{v:.3f}".rstrip("0").rstrip(".")
    return s if s not in ("", "-") else "0"


def save_polygons(payload):
    global _config_cache
    items = payload if isinstance(payload, list) else [payload]
    saved, errors = [], []
    for it in items:
        region = it.get("region")
        subzone = it.get("subzone")
        verts = it.get("vertices")
        try:
            if not region or not subzone:
                raise ValueError("region/subzone manquants")
            poly = [(float(x), float(y)) for x, y in verts]
            if len(poly) < 3:
                raise ValueError("un polygone doit avoir au moins 3 sommets")
            poly = geo.normalize_clockwise(poly)
            path = os.path.join(ZONES, region, subzone, "geometry.txt")
            os.makedirs(os.path.dirname(path), exist_ok=True)

            header = []
            if os.path.isfile(path):
                with open(path, encoding="utf-8-sig") as f:
                    for line in f:
                        s = line.rstrip("\n")
                        if s.strip() == "" or s.lstrip().startswith("#"):
                            header.append(s)
                        else:
                            break
            if not header:
                header = [
                    f"# {region} / {subzone} — polygone (coordonnées carte continent 0-100)",
                    "# X = est, Y = sud. Sommets en SENS HORAIRE, un par ligne : X;Y",
                    "",
                ]

            lines = list(header) + [f"{_fmt(x)};{_fmt(y)}" for x, y in poly]
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write("\n".join(lines) + "\n")
            saved.append({"region": region, "subzone": subzone, "n": len(poly)})
        except Exception as exc:  # noqa: BLE001
            errors.append({"region": region, "subzone": subzone,
                           "error": str(exc)})
    if saved:
        # Invalidate the cached /api/config so a later "Recharger" re-reads
        # the freshly written geometry.txt files instead of stale data.
        _config_cache = None
    return {"saved": saved, "errors": errors}


class Handler(BaseHTTPRequestHandler):
    server_version = "ZoneCalibrator/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._send(code, body, "application/json; charset=utf-8")

    def _file(self, path, ctype):
        try:
            with open(path, "rb") as f:
                self._send(200, f.read(), ctype)
        except OSError:
            self._json({"error": "fichier introuvable"}, 500)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._file(INDEX, "text/html; charset=utf-8")
        elif path == "/app.js":
            self._file(APPJS, "text/javascript; charset=utf-8")
        elif path == "/api/config":
            self._json(get_config())
        elif path.startswith("/api/map/"):
            self._serve_map(urllib.parse.unquote(path[len("/api/map/"):]))
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/save":
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            try:
                payload = json.loads(body.decode("utf-8"))
            except Exception as exc:  # noqa: BLE001
                self._json({"error": f"JSON invalide: {exc}"}, 400)
                return
            self._json(save_polygons(payload))
        else:
            self._json({"error": "not found"}, 404)

    def _serve_map(self, cont):
        for path in MAP_IMAGES.get(cont, []):
            if os.path.isfile(path):
                ext = os.path.splitext(path)[1].lower()
                with open(path, "rb") as f:
                    body = f.read()
                self._send(200, body, MIME.get(ext, "application/octet-stream"))
                return
        self._json({"error": f"aucune image de carte pour {cont}"}, 404)


def main():
    port = int(os.environ.get("PORT", "8000"))
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print("Zone calibrator: http://127.0.0.1:%d/" % port)
    print("  Images de carte par continent :")
    for c in ("Kalimdor", "EK"):
        avail = [p for p in MAP_IMAGES[c] if os.path.isfile(p)]
        print("    %s: %s" % (c, avail[0] if avail else
                             "(aucune — chargez une image depuis le navigateur)"))
    print("  Ctrl+C pour arrêter.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt.")


if __name__ == "__main__":
    main()


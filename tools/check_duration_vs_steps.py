#!/usr/bin/env python3
"""Compare every travel's duration.txt against the sum of its legs' durations.

For each route ``travels/<faction>/<source>/<destination>/``:
  - ``duration.txt`` : total flight duration reported by the community (seconds).
  - ``steps.txt``    : the known stops of the route, one node name per line,
    ``escale1, escale2, ..., destination`` (the source is *not* repeated).

The full node chain is therefore ``[source] + steps``, and the route is the
concatenation of its consecutive legs (source -> escale1, escale1 -> escale2,
..., last escale -> destination).  Each leg is itself a route in the same
faction tree, so it has its own ``duration.txt``.

This script reports, for every route in the tree, the difference between the
reported total duration and the sum of the durations of its individual legs.
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRAVELS_DIR = os.path.join(ROOT, "travels")


def read_int(path):
    with open(path, encoding="utf-8-sig") as fh:
        return int(fh.read().strip())


def collect_routes():
    """Return {(faction, source, destination): (duration, [steps])}."""
    routes = {}
    for faction in ("alliance", "horde"):
        faction_dir = os.path.join(TRAVELS_DIR, faction)
        if not os.path.isdir(faction_dir):
            continue
        for source in sorted(os.listdir(faction_dir)):
            source_dir = os.path.join(faction_dir, source)
            if not os.path.isdir(source_dir):
                continue
            for destination in sorted(os.listdir(source_dir)):
                dest_dir = os.path.join(source_dir, destination)
                duration_path = os.path.join(dest_dir, "duration.txt")
                if not os.path.isfile(duration_path):
                    continue
                duration = read_int(duration_path)
                steps_path = os.path.join(dest_dir, "steps.txt")
                steps = []
                if os.path.isfile(steps_path):
                    with open(steps_path, encoding="utf-8-sig") as fh:
                        steps = [ln.strip() for ln in fh.read().splitlines()
                                 if ln.strip()]
                routes[(faction, source, destination)] = (duration, steps)
    return routes


def main():
    routes = collect_routes()

    # Quick lookup of every leg duration.
    leg_durations = {}
    for (faction, source, destination), (duration, _) in routes.items():
        leg_durations.setdefault(faction, {}).setdefault(source, {})[
            destination] = duration

    rows = []          # routes that do NOT match (or have a missing leg)
    n_routes = 0
    n_direct = 0       # routes with no intermediate stop (single leg)
    n_multi = 0        # routes with at least one intermediate stop
    n_matched = 0
    n_mismatched = 0
    n_missing_leg = 0
    n_multi_matched = 0
    n_multi_mismatched = 0

    for (faction, source, destination), (reported, steps) in sorted(
            routes.items()):
        n_routes += 1
        chain = [source] + steps
        legs = list(zip(chain, chain[1:]))

        is_multi = len(steps) > 1
        if is_multi:
            n_multi += 1
        else:
            n_direct += 1

        leg_sum = 0
        missing = []
        for a, b in legs:
            if (faction in leg_durations and a in leg_durations[faction]
                    and b in leg_durations[faction][a]):
                leg_sum += leg_durations[faction][a][b]
            else:
                missing.append((a, b))

        if missing:
            n_missing_leg += 1
            rows.append({
                "faction": faction,
                "source": source,
                "destination": destination,
                "reported": reported,
                "leg_sum": leg_sum,
                "diff": reported - leg_sum,
                "n_legs": len(legs),
                "steps": steps,
                "missing": missing,
            })
            continue

        if leg_sum == reported:
            n_matched += 1
            if is_multi:
                n_multi_matched += 1
        else:
            n_mismatched += 1
            if is_multi:
                n_multi_mismatched += 1
            rows.append({
                "faction": faction,
                "source": source,
                "destination": destination,
                "reported": reported,
                "leg_sum": leg_sum,
                "diff": reported - leg_sum,
                "n_legs": len(legs),
                "steps": steps,
                "missing": [],
            })

    # Summary.
    print("=== duration.txt vs sum(duration.txt des etapes) ===")
    print(f"Routes au total                                : {n_routes}")
    print(f"  dont routes directes (1 troncon)             : {n_direct}")
    print(f"  dont routes multi-troncons (>= 1 escale)     : {n_multi}")
    print(f"Somme des troncons == duration.txt             : {n_matched}")
    print(f"  dont multi-troncons concordants              : {n_multi_matched}")
    print(f"Somme des troncons != duration.txt             : {n_mismatched}")
    print(f"  dont multi-troncons discordants              : {n_multi_mismatched}")
    print(f"Troncon(s) introuvable(s) dans le graphe       : {n_missing_leg}")
    print()

    diffs = [r for r in rows if not r["missing"]]
    if diffs:
        abs_diffs = [abs(r["diff"]) for r in diffs]
        print(f"Ecarts observes (hors troncons manquants)      : {len(diffs)}")
        print(f"  ecart absolu moyen                           : "
              f"{sum(abs_diffs) / len(abs_diffs):.2f} s")
        print(f"  ecart absolu max                             : "
              f"{max(abs_diffs)} s")
        print(f"  ecart absolu min                             : "
              f"{min(abs_diffs)} s")
        print(f"  somme des ecarts absolus                     : "
              f"{sum(abs_diffs)} s")
        print("Repartition des ecarts absolus                :")
        buckets = [
            ("1 s (exact)", lambda d: d == 1),
            ("2-5 s", lambda d: 2 <= d <= 5),
            ("6-10 s", lambda d: 6 <= d <= 10),
            ("11-30 s", lambda d: 11 <= d <= 30),
            ("31-60 s", lambda d: 31 <= d <= 60),
            ("61-120 s", lambda d: 61 <= d <= 120),
            ("> 120 s", lambda d: d > 120),
        ]
        for label, pred in buckets:
            n = sum(1 for d in abs_diffs if pred(d))
            print(f"    {label:<14}: {n}")
    else:
        print("Aucun ecart (hors troncons manquants).")
    print()

    # Detail, sorted by |diff| descending.
    rows.sort(key=lambda r: abs(r["diff"]), reverse=True)
    print("=== Detail des ecarts (tri par |diff| decroissant) ===")
    if not rows:
        print("Aucun ecart a afficher.")
    for r in rows:
        tag = "MANQUANT" if r["missing"] else "ECART"
        print(f"[{tag}] {r['faction']}/{r['source']} -> {r['destination']}")
        print(f"  reporte={r['reported']} s  somme_etapes={r['leg_sum']} s  "
              f"diff={r['diff']:+d} s  (troncons={r['n_legs']})")
        print(f"  etapes: {' -> '.join(r['steps'])}")
        for a, b in r["missing"]:
            print(f"    manquant: {a} -> {b}")

    # UTF-8 CSV of the discrepancies for easy reading/versioning.
    import csv
    report_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "duration_vs_steps_report.csv",
    )
    with open(report_path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(["faction", "source", "destination", "reported_s",
                         "sum_legs_s", "diff_s", "n_legs", "steps", "missing"])
        for r in rows:
            writer.writerow([
                r["faction"], r["source"], r["destination"], r["reported"],
                r["leg_sum"], r["diff"], r["n_legs"],
                " -> ".join(r["steps"]),
                " | ".join(f"{a} -> {b}" for a, b in r["missing"]),
            ])
    print(f"Rapport CSV ecrit : {report_path}")


if __name__ == "__main__":
    main()


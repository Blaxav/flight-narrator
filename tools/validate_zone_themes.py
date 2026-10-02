#!/usr/bin/env python3
"""Validate the themed zone-lore source (tools/zones-fr) before generation.

Checks that every leaf folder under zones/ is covered, that no entry points at
an unknown folder (typo), and reports theme counts and word counts.
"""
import glob
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC_DIR = os.path.join(HERE, "zones-fr")
ZONES = os.path.join(ROOT, "zones")


def leaf_folders():
    result = []
    for dirpath, dirnames, filenames in os.walk(ZONES):
        if not dirnames:
            result.append(os.path.relpath(dirpath, ZONES).replace(os.sep, "/"))
    return sorted(result)


def parse_src():
    entries = {}
    bad = []
    for src in sorted(glob.glob(os.path.join(SRC_DIR, "*.txt"))):
        for i, line in enumerate(open(src, encoding="utf-8"), 1):
            line = line.rstrip("\r\n")
            if not line or line.startswith("#"):
                continue
            if line.count("|") != 2:
                bad.append((os.path.basename(src), i, "pipe count"))
                continue
            path, title, text = line.split("|", 2)
            parts = path.split("/")
            if len(parts) != 3:
                bad.append((os.path.basename(src), i, "path segments"))
                continue
            region, subzone, slug = parts
            entries.setdefault((region, subzone), []).append((slug, title, text))
    return entries, bad


def main():
    entries, bad = parse_src()
    real = leaf_folders()  # list of "region/subzone" strings
    real_set = set(real)
    have = {f"{r}/{s}": items for (r, s), items in entries.items()}

    missing = sorted(f for f in real if f not in have)
    unknown = sorted(f for f in have if f not in real_set)
    short = [f for f in real if len(have.get(f, [])) < 4]

    all_items = [item for items in have.values() for item in items]
    words = [len(t.split()) for _, _, t in all_items]

    print(f"real leaf folders : {len(real)}")
    print(f"covered folders   : {len(have)}")
    print(f"total entries     : {len(all_items)}")
    print(f"bad source lines  : {len(bad)}")
    print(f"missing (0 theme) : {missing}")
    print(f"unknown (typo)    : {unknown}")
    print(f"folders <4 themes : {short}")
    if words:
        print(f"word count        : min={min(words)} max={max(words)} avg={sum(words)/len(words):.0f}")

    for b in bad[:20]:
        print("  bad line:", b)

    if missing or unknown or short or bad:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

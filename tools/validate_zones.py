#!/usr/bin/env python3
"""Validate that every travels/**/zones.txt only references folders that exist
under zones/ (the strict choice list), so the audio association always resolves.
"""
import glob
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ZONES = os.path.join(ROOT, "zones")


def main():
    valid = set()
    for region in os.listdir(ZONES):
        rd = os.path.join(ZONES, region)
        if not os.path.isdir(rd):
            continue
        for sub in os.listdir(rd):
            if os.path.isdir(os.path.join(rd, sub)):
                valid.add((region, sub))

    entries = 0
    bad = []
    files = 0
    for path in glob.glob(os.path.join(ROOT, "travels", "**", "zones.txt"), recursive=True):
        files += 1
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            f = line.split(";")
            region, sub = f[2], f[3]
            entries += 1
            if (region, sub) not in valid:
                bad.append((os.path.relpath(path, ROOT), region, sub))

    print(f"zones.txt files : {files}")
    print(f"timeline entries: {entries}")
    print(f"invalid refs     : {len(bad)}")
    for b in bad[:40]:
        print("  INVALID", b)

    if bad:
        raise SystemExit("FAIL: some zones.txt reference missing folders.")
    print("OK: every reference resolves to a zones/ folder.")


if __name__ == "__main__":
    main()

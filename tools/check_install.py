#!/usr/bin/env python3
"""Verify an installed FlightNarrator addon folder is complete and consistent.

Cross-checks the clip paths written into TravelData.lua against the MP3 files
actually present in the installed "zones" tree, and reports any missing or
orphaned files plus a couple of data sanity checks.

Usage:
    python tools/check_install.py [addon_dir]

Defaults to the standard Classic Era addons path.
"""
import io
import os
import re
import sys

DEFAULT_DIR = (
    r"C:\Program Files (x86)\World of Warcraft\_classic_era_\Interface\AddOns\FlightNarrator"
)


def main():
    addon_dir = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DIR

    lua_path = os.path.join(addon_dir, "TravelData.lua")
    if not os.path.isfile(lua_path):
        raise SystemExit(f"no TravelData.lua at {lua_path}")

    content = io.open(lua_path, encoding="utf-8").read()

    # 1. Clip paths referenced by the generated data (Lua "\\" -> one backslash).
    refs = sorted({
        p.replace("\\\\", "\\")
        for p in re.findall(r'"([^"]+\.mp3)"', content)
    })

    # 2. MP3 files actually present under the installed zones/ folder.
    zones_dir = os.path.join(addon_dir, "zones")
    present = sorted({
        os.path.relpath(os.path.join(dirpath, name), addon_dir).replace(os.sep, "\\")
        for dirpath, _dirnames, filenames in os.walk(zones_dir)
        for name in filenames
        if name.lower().endswith(".mp3")
    })

    missing = [p for p in refs if p not in present]
    orphan = [p for p in present if p not in refs]

    print(f"clips referenced in TravelData.lua : {len(refs)}")
    print(f"mp3 present in installed zones/    : {len(present)}")
    print(f"missing (referenced but absent)    : {len(missing)}")
    print(f"orphan  (present but not referenced): {len(orphan)}")
    for p in missing:
        print("  MISSING", p)
    for p in orphan:
        print("  ORPHAN ", p)

    print(f"routes with 'duration ='           : {content.count('duration =')}")
    print("faction keys alliance/horde        :",
          '"alliance"' in content, "/", '"horde"' in content)
    print("example zone timeline present      :",
          'region = "Les Tarides"' in content)

    if missing:
        raise SystemExit("FAIL: some referenced clips are missing.")
    print("OK: every referenced clip is present.")


if __name__ == "__main__":
    main()

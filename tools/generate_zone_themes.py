#!/usr/bin/env python3
"""Write zones/<region>/<subzone>/<theme>.txt from tools/zones-fr/*.txt.

Every non-empty, non-comment line of any source file is:

    <region>/<subzone>/<slug>|<Title>|<paragraph>

The paragraph is a ~50 s narration in French. The generator writes one file per
theme in the same format as text/frFR/*.txt (title, underline, paragraph,
duration, lore key), named after the slug.

Usage:

    python tools/generate_zone_themes.py
"""
import glob
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC_DIR = os.path.join(HERE, "zones-fr")
ZONES = os.path.join(ROOT, "zones")


def write_file(path, title, text):
    underline = "=" * len(title)
    key = os.path.splitext(os.path.basename(path))[0]
    content = (
        f"{title}\n"
        f"{underline}\n\n"
        f"{text}\n\n"
        "---\n\n"
        "Durée estimée : ~50 s en narration.\n"
        f"Clé (lore library) : {key}\n"
    )
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)


def iter_entries():
    sources = sorted(glob.glob(os.path.join(SRC_DIR, "*.txt")))
    if not sources:
        raise SystemExit(f"no source files in {SRC_DIR}")
    for src in sources:
        with open(src, encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\r\n")
                if not line or line.startswith("#"):
                    continue
                path_part, title, text = line.split("|", 2)
                parts = path_part.split("/")
                if len(parts) != 3:
                    raise SystemExit(
                        f"bad path (expected region/subzone/slug): {path_part!r}"
                    )
                yield parts, title, text


def main():
    count = 0
    for parts, title, text in iter_entries():
        region, subzone, slug = parts
        target = os.path.join(ZONES, region, subzone, slug + ".txt")
        write_file(target, title, text)
        count += 1

    print(f"Wrote {count} themed narration files under {ZONES}")


if __name__ == "__main__":
    main()

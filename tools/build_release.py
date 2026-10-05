#!/usr/bin/env python3
"""Build the distributable FlightNarrator addon archive.

The archive must contain a single top-level folder named exactly
``FlightNarrator`` so that extracting it straight into
``World of Warcraft\\_classic_era_\\Interface\\AddOns\\`` installs the addon.

Only the files the client needs at runtime are shipped:

    FlightNarrator.toc     manifest (loads the two Lua files below)
    FlightNarrator.lua     the game logic
    TravelData.lua         clip paths + per-route zone timelines
    zones/**/*.mp3         the narration clips referenced by TravelData.lua

The pipeline sources (DataFlights*.lua, FlightData.lua, tools/, travels/, the
narration .txt and geometry.txt files...) stay out of the release.

Usage:
    python tools/build_release.py [--out dist] [--with-sources] [--keep-staging]

    --with-sources   also ship zones/**/*.txt (human-readable narrations)
    --keep-staging   leave the assembled staging folder in place
"""
import argparse
import io
import os
import re
import shutil
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDON_NAME = "FlightNarrator"

# The manifest plus the two Lua files it loads.
RUNTIME_FILES = ("FlightNarrator.toc", "FlightNarrator.lua", "TravelData.lua")

# Extensions copied out of zones/. The MP3 clips are mandatory; the source
# .txt narrations only travel with --with-sources.
CLIP_EXTENSION = ".mp3"
SOURCE_EXTENSIONS = (".txt",)


def read_version(toc_path):
    with io.open(toc_path, encoding="utf-8") as handle:
        for line in handle:
            match = re.match(r"##\s*Version:\s*(\S+)", line)
            if match:
                return match.group(1)
    raise SystemExit("no '## Version' line in " + toc_path)


def collect_zones(zones_dir, extensions):
    """Yield (absolute_path, relative_path) for every wanted file in zones/."""
    for dirpath, _dirnames, filenames in os.walk(zones_dir):
        for name in sorted(filenames):
            if os.path.splitext(name)[1].lower() in extensions:
                full = os.path.join(dirpath, name)
                yield full, os.path.relpath(full, zones_dir)


def build_staging(staging_dir, with_sources):
    if os.path.isdir(staging_dir):
        shutil.rmtree(staging_dir)
    os.makedirs(os.path.join(staging_dir, "zones"))

    for name in RUNTIME_FILES:
        src = os.path.join(ROOT, name)
        if not os.path.isfile(src):
            raise SystemExit("missing runtime file: " + src)
        shutil.copy2(src, os.path.join(staging_dir, name))

    extensions = {CLIP_EXTENSION}
    if with_sources:
        extensions.update(SOURCE_EXTENSIONS)

    count = 0
    for full, rel in collect_zones(os.path.join(ROOT, "zones"), extensions):
        dest = os.path.join(staging_dir, "zones", rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(full, dest)
        count += 1
    return count


def zip_staging(staging_dir, zip_path):
    parent = os.path.dirname(zip_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    if os.path.exists(zip_path):
        os.remove(zip_path)

    total = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for dirpath, _dirnames, filenames in os.walk(staging_dir):
            for name in sorted(filenames):
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, staging_dir).replace(os.sep, "/")
                arcname = ADDON_NAME + "/" + rel
                # MP3 are already compressed: store them as-is for speed.
                method = (zipfile.ZIP_STORED
                          if name.lower().endswith(CLIP_EXTENSION)
                          else zipfile.ZIP_DEFLATED)
                archive.write(full, arcname, compress_type=method)
                total += 1
    return total


def verify_zip(zip_path):
    """Check the archive is self-consistent and installs as FlightNarrator/.

    Confirms every clip path written into TravelData.lua is present in the
    archive, and that the archive has a single top-level FlightNarrator folder.
    """
    toc_name = ADDON_NAME + "/FlightNarrator.toc"
    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
        bad_root = [n for n in names if not n.startswith(ADDON_NAME + "/")]
        if bad_root:
            raise SystemExit("archive has entries outside %s/: %s"
                             % (ADDON_NAME, bad_root[:5]))
        if toc_name not in names:
            raise SystemExit("archive is missing " + toc_name)

        data = archive.read(ADDON_NAME + "/TravelData.lua").decode("utf-8")
        refs = sorted({m.replace("\\\\", "/")
                       for m in re.findall(r'"([^"]+\.mp3)"', data)})
        missing = [r for r in refs if ADDON_NAME + "/" + r not in names]

    print("clips referenced in data :", len(refs))
    print("missing from archive     :", len(missing))
    for name in missing:
        print("  MISSING", name)
    if missing:
        raise SystemExit("FAIL: the archive is missing referenced clips.")
    print("OK: every referenced clip ships in the archive.")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--out", default=os.path.join(ROOT, "dist"),
                        help="output directory (default: dist/)")
    parser.add_argument("--with-sources", action="store_true",
                        help="also ship zones/**/*.txt narrations")
    parser.add_argument("--keep-staging", action="store_true",
                        help="keep the assembled staging folder")
    args = parser.parse_args()

    version = read_version(os.path.join(ROOT, "FlightNarrator.toc"))
    staging_root = os.path.join(args.out, "staging")
    staging_dir = os.path.join(staging_root, ADDON_NAME)
    zip_path = os.path.join(args.out, "FlightNarrator-v%s.zip" % version)

    print("FlightNarrator version   :", version)
    copied = build_staging(staging_dir, args.with_sources)
    print("zones files staged       :", copied)
    entries = zip_staging(staging_dir, zip_path)
    print("zip entries              :", entries)
    print("size                     : %.1f MB"
          % (os.path.getsize(zip_path) / (1024 * 1024)))
    print("archive                  :", zip_path)
    verify_zip(zip_path)

    if not args.keep_staging:
        shutil.rmtree(staging_root, ignore_errors=True)


if __name__ == "__main__":
    main()

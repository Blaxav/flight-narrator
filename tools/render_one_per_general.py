#!/usr/bin/env python3
"""Render one narration MP3 per zone, from each zone's "Général" subfolder.

For every ``zones/<ZONE>/Général`` folder, pick the first ``<slug>.txt``
(alphabetical) and render it to ``<slug>.mp3`` next to the text, so each zone
ships with at least one clip. Existing MP3s are kept (resumable) unless
``--force``.

Uses the same ElevenLabs voice/settings as ``render_zone_audio.py``.

Usage:

    python tools/render_one_per_general.py            # one clip per zone
    python tools/render_one_per_general.py --workers 3 --force
"""

import argparse
import concurrent.futures
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import text_to_mp3 as ttm  # noqa: E402
import render_zone_audio as rz  # noqa: E402

# Same voice/settings as render_zone_audio.py
VOICE = "a5n9pJUnAhX4fn7lx3uo"  # Martin Dupont, deep French storyteller
MODEL = "eleven_v4"
STABILITY = 0.15
SIMILARITY = 0.09
STYLE = 0.2
OUTPUT_FORMAT = "mp3_22050_32"  # small mono MP3 (see text_to_mp3.py)

GENERAL_NAMES = ("général", "general")


def pick_first_txt(folder):
    """Return the path of the first .txt (alphabetical) in a folder, or None."""
    names = sorted(n for n in os.listdir(folder) if n.lower().endswith(".txt"))
    return os.path.join(folder, names[0]) if names else None


def collect(zones_dir):
    """Yield (zone, txt_path, mp3_path) for one text per zone's Général folder."""
    items = []
    for zone in sorted(os.listdir(zones_dir)):
        zone_dir = os.path.join(zones_dir, zone)
        if not os.path.isdir(zone_dir):
            continue
        general = None
        for candidate in os.listdir(zone_dir):
            if candidate.lower() in GENERAL_NAMES:
                general = os.path.join(zone_dir, candidate)
                break
        if not general or not os.path.isdir(general):
            continue
        txt = pick_first_txt(general)
        if not txt:
            continue
        items.append((zone, txt, os.path.splitext(txt)[0] + ".mp3"))
    return items


def render_one(item, api_key, force):
    zone, txt, out = item
    rel = os.path.relpath(out, ROOT)
    if not force and os.path.isfile(out) and os.path.getsize(out) > 0:
        return ("kept", zone, rel)
    text = rz.extract_paragraph(txt)
    if not text:
        return ("empty", zone, rel)
    last = None
    for attempt in range(4):
        try:
            ttm.render_elevenlabs(text, VOICE, MODEL, STABILITY, SIMILARITY,
                                  STYLE, out, api_key, OUTPUT_FORMAT)
            return ("rendered", zone, rel)
        except SystemExit as exc:
            last = exc
            if "429" in str(exc) and attempt < 3:
                time.sleep(2 ** attempt)
                continue
            break
    return ("failed", zone, f"{rel}: {last}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=3,
                        help="parallel ElevenLabs requests (default 3)")
    parser.add_argument("--force", action="store_true",
                        help="re-render clips that already exist")
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    ttm.load_dotenv()
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise SystemExit("ELEVENLABS_API_KEY is missing (set it in .env or env).")

    items = collect(os.path.join(ROOT, "zones"))
    if not items:
        raise SystemExit("no zone with a Général folder found.")

    print(f"{len(items)} zones, one clip each (voice={VOICE}, model={MODEL}, "
          f"workers={args.workers}).")

    counts = {"rendered": 0, "kept": 0, "empty": 0, "failed": 0}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(render_one, item, api_key, args.force)
                   for item in items]
        done = 0
        for future in concurrent.futures.as_completed(futures):
            status, zone, rel = future.result()
            counts[status] += 1
            done += 1
            print(f"[{done}/{len(items)}] {status:8s} {zone}: {rel}", flush=True)

    print(f"\nDone: {counts['rendered']} rendered, {counts['kept']} kept, "
          f"{counts['empty']} empty, {counts['failed']} failed.")
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

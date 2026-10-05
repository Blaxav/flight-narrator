#!/usr/bin/env python3
"""Render narration MP3s in priority order, deepening coverage on every run.

Reads every narration ``zones/<zone>/<subfolder>/*.txt`` (the files that carry a
``---`` footer separator; ``geometry.txt`` polygon files are ignored) and renders
each one to ``<slug>.mp3`` next to the text with ElevenLabs (same voice/settings
as ``render_zone_audio.py``).

The queue is ordered so the most valuable clips come first, alternating a level
of the ``Général`` subfolder with the same level of every other subfolder:

1. first  narration per ``Général`` subfolder     (wave 1),
2. first  narration per non-``Général`` subfolder (wave 2),
3. second narration per ``Général`` subfolder     (wave 3),
4. second narration per non-``Général`` subfolder (wave 4),
5. third  narration per ``Général`` subfolder     (wave 5),
   ... and so on.

Each wave only runs if the ones above finished without hitting the credit wall,
so the whole set of narrations is covered over successive runs. Existing MP3s
are kept (resumable) unless ``--force``. Rate limits (429) are retried with
backoff; an exhausted account (HTTP 402) stops the run cleanly.

Usage:

    python tools/render_waves.py --dry-run     # list the plan, no API calls
    python tools/render_waves.py               # render, stop at the credit wall
    python tools/render_waves.py --workers 3 --force
    python tools/render_waves.py --limit 10    # render only the first 10 pending
"""

import argparse
import concurrent.futures
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import text_to_mp3 as ttm  # noqa: E402
import render_zone_audio as rz  # noqa: E402

# Same voice/settings as render_zone_audio.py and render_one_per_general.py.
VOICE = "a5n9pJUnAhX4fn7lx3uo"  # Martin Dupont, deep French storyteller
MODEL = "eleven_v4"
STABILITY = 0.15
SIMILARITY = 0.09
STYLE = 0.2
OUTPUT_FORMAT = "mp3_22050_32"  # small mono MP3 (see text_to_mp3.py)

GENERAL_NAMES = ("général", "general")
MAX_ATTEMPTS = 4


def narration_txts(folder):
    """Return the narration ``.txt`` paths in *folder*, sorted alphabetically.

    Skips ``geometry.txt`` (polygon data, not speech) and any ``.txt`` without a
    ``---`` footer separator, so only real narrations are rendered.
    """
    out = []
    for name in sorted(os.listdir(folder)):
        if not name.lower().endswith(".txt"):
            continue
        if name.lower() == "geometry.txt":
            continue
        path = os.path.join(folder, name)
        with open(path, "r", encoding="utf-8-sig") as handle:
            if "\n---" not in handle.read():
                continue
        out.append(path)
    return out


def wave_title(wave):
    """Human description of a wave number (see ``collect_targets``)."""
    level = (wave + 1) // 2  # 1 for waves 1-2, 2 for waves 3-4, ...
    ordinal = {1: "first", 2: "second", 3: "third", 4: "fourth"}.get(
        level, f"{level}th")
    where = "Général" if wave % 2 else "non-Général"
    return f"{ordinal} narration per {where} subfolder"


def collect_targets(zones_dir):
    """Return the render queue as ``(wave, zone, subfolder, txt, mp3)`` tuples.

    Wave numbers alternate a level of the ``Général`` subfolder with the same
    level of every other subfolder, so coverage deepens on every run::

        wave 1 = first  narration per Général subfolder
        wave 2 = first  narration per non-Général subfolder
        wave 3 = second narration per Général subfolder
        wave 4 = second narration per non-Général subfolder
        ...

    i.e. ``wave = 1 + 2 * level`` for ``Général`` and ``2 + 2 * level`` for the
    others (``level`` being the 0-based narration index inside the folder).
    """
    by_wave = {}  # wave -> [(zone, sub, txt), ...] in collection order

    def add(wave, zone, sub, txt):
        by_wave.setdefault(wave, []).append((zone, sub, txt))

    for zone in sorted(os.listdir(zones_dir)):
        zone_dir = os.path.join(zones_dir, zone)
        if not os.path.isdir(zone_dir):
            continue
        general = None
        others = []
        for sub in sorted(os.listdir(zone_dir)):
            sub_dir = os.path.join(zone_dir, sub)
            if not os.path.isdir(sub_dir):
                continue
            if sub.lower() in GENERAL_NAMES:
                general = sub
            else:
                others.append(sub)

        if general:
            for level, txt in enumerate(narration_txts(os.path.join(zone_dir, general))):
                add(1 + 2 * level, zone, general, txt)
        for sub in others:
            for level, txt in enumerate(narration_txts(os.path.join(zone_dir, sub))):
                add(2 + 2 * level, zone, sub, txt)

    targets = []
    for wave in sorted(by_wave):
        for zone, sub, txt in by_wave[wave]:
            targets.append((wave, zone, sub, txt,
                            os.path.splitext(txt)[0] + ".mp3"))
    return targets


def render_one(target, api_key, force, stop):
    """Render a single target; returns ``(status, wave, zone, subfolder, rel)``."""
    wave, zone, sub, txt, out = target
    rel = os.path.relpath(out, ROOT)
    if not force and os.path.isfile(out) and os.path.getsize(out) > 0:
        return ("kept", wave, zone, sub, rel)
    text = rz.extract_paragraph(txt)
    if not text:
        return ("empty", wave, zone, sub, rel)
    last = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            ttm.render_elevenlabs(text, VOICE, MODEL, STABILITY, SIMILARITY,
                                  STYLE, out, api_key, OUTPUT_FORMAT)
            return ("rendered", wave, zone, sub, rel)
        except SystemExit as exc:
            # HTTP errors surface as SystemExit("request failed (CODE): ...").
            last = exc
            msg = str(exc)
            if "429" in msg and attempt < MAX_ATTEMPTS - 1:
                time.sleep(min(2 ** attempt, 30))
                continue
            if "402" in msg:
                stop.set()
                return ("no_credits", wave, zone, sub, rel)
            break
        except Exception as exc:  # noqa: BLE001 - network timeouts, resets, ...
            last = exc
            if attempt < MAX_ATTEMPTS - 1:
                time.sleep(min(2 ** attempt, 30))
                continue
            break
    return ("failed", wave, zone, sub, f"{rel}: {last}")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--workers", type=int, default=3,
                        help="parallel ElevenLabs requests (default 3)")
    parser.add_argument("--force", action="store_true",
                        help="re-render clips that already exist")
    parser.add_argument("--limit", type=int, default=0,
                        help="render only the first N pending items (0 = all)")
    parser.add_argument("--dry-run", action="store_true",
                        help="list the plan without calling the API")
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    targets = collect_targets(os.path.join(ROOT, "zones"))
    if not targets:
        raise SystemExit("no narration found under zones/.")

    def exists(out):
        return os.path.isfile(out) and os.path.getsize(out) > 0

    pending = [t for t in targets if args.force or not exists(t[4])]

    if args.dry_run:
        by_wave = {}
        for t in targets:
            by_wave.setdefault(t[0], []).append(t)
        total_chars = 0
        total_words = 0
        for wave in sorted(by_wave):
            items = by_wave[wave]
            print(f"\n--- wave {wave}: {wave_title(wave)} ({len(items)}) ---")
            for w, zone, sub, txt, out in items:
                text = rz.extract_paragraph(txt)
                words = len(text.split())
                chars = len(text)
                marker = "exists" if exists(out) else "RENDER"
                if not exists(out):
                    total_chars += chars
                    total_words += words
                print(f"  {marker:6s} {zone}/{sub} : "
                      f"{os.path.basename(out)}  ({words} words, {chars} chars)")
        print(f"\nTotal: {len(targets)} targets, {len(pending)} to render, "
              f"~{total_words} words, ~{total_chars} chars.")
        return 0

    ttm.load_dotenv()
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise SystemExit("ELEVENLABS_API_KEY is missing (set it in .env or env).")

    if args.limit:
        pending = pending[:args.limit]

    print(f"{len(targets)} targets total, {len(pending)} to render "
          f"(voice={VOICE}, model={MODEL}, workers={args.workers}).")

    counts = {"rendered": 0, "kept": 0, "empty": 0, "failed": 0, "no_credits": 0}
    done = 0
    stop = threading.Event()

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {}
        idx = 0

        def submit_more():
            nonlocal idx
            while idx < len(pending) and len(futures) < args.workers:
                target = pending[idx]
                futures[pool.submit(render_one, target, api_key, args.force,
                                    stop)] = target
                idx += 1

        submit_more()
        while futures:
            finished, _ = concurrent.futures.wait(
                futures, return_when=concurrent.futures.FIRST_COMPLETED)
            for fut in finished:
                target = futures.pop(fut)
                status, wave, zone, sub, rel = fut.result()
                counts[status] += 1
                done += 1
                print(f"[{done}/{len(pending)}] wave{wave} {status:9s} "
                      f"{zone}/{sub}: {rel}", flush=True)
            if stop.is_set():
                break
            submit_more()

    print(f"\nDone: {counts['rendered']} rendered, {counts['kept']} kept, "
          f"{counts['empty']} empty, {counts['failed']} failed, "
          f"{counts['no_credits']} no-credits stop.")
    if counts["no_credits"]:
        print("Stopped early: ElevenLabs credits exhausted. Re-run later to "
              "continue where it left off.")
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Render every narration in a zone folder to MP3 with ElevenLabs.

Walks ``zones/<ZONE>/...`` and, for each ``<slug>.txt``, renders the narration
paragraph to ``<slug>.mp3`` **in the same folder**. Existing MP3s are kept
unless ``FORCE`` is True.

Edit the settings below, then run:

    python tools/render_zone_audio.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import text_to_mp3 as ttm  # noqa: E402

# --- Settings ---
ZONE = "Les Tarides"
VOICE = "a5n9pJUnAhX4fn7lx3uo"  # Martin Dupont, deep French storyteller
MODEL = "eleven_v4"
STABILITY = 0.15
SIMILARITY = 0.09
STYLE = 0.2
OUTPUT_FORMAT = "mp3_22050_32"  # small mono MP3 (see text_to_mp3.py)
FORCE = False  # True = re-render clips that already exist


def extract_paragraph(path: str) -> str:
    """Return the narration body of a zones/*.txt file.

    The file is: title, underline, blank, paragraph, blank, ``---``, footer.
    We keep everything between the underline and the ``---`` separator.
    """
    with open(path, "r", encoding="utf-8-sig") as handle:
        content = handle.read()

    head = content.split("\n---", 1)[0]
    lines = head.splitlines()
    body = lines[2:] if len(lines) >= 2 else lines
    while body and not body[0].strip():
        body.pop(0)
    while body and not body[-1].strip():
        body.pop()
    return "\n".join(body).strip()


def iter_zone_txt(zone_dir: str):
    """Yield (text_path, mp3_path) for every .txt narration in a zone folder."""
    for dirpath, dirnames, filenames in os.walk(zone_dir):
        dirnames.sort()
        for name in sorted(filenames):
            if not name.lower().endswith(".txt"):
                continue
            path = os.path.join(dirpath, name)
            out = os.path.splitext(path)[0] + ".mp3"
            yield path, out


def main() -> int:
    ttm.load_dotenv()
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise SystemExit("ELEVENLABS_API_KEY is missing (set it in .env or the environment).")

    zone_dir = os.path.join(ROOT, "zones", ZONE)
    if not os.path.isdir(zone_dir):
        raise SystemExit(f"no zone folder at {zone_dir}")

    items = list(iter_zone_txt(zone_dir))
    total = len(items)
    rendered = skipped = failed = 0
    print(f"{ZONE}: {total} text(s) to render (voice={VOICE}, model={MODEL}).")

    for index, (txt_path, out_path) in enumerate(items, 1):
        rel = os.path.relpath(out_path, ROOT)
        if os.path.isfile(out_path) and os.path.getsize(out_path) > 0 and not FORCE:
            print(f"[{index}/{total}] kept     {rel}")
            skipped += 1
            continue

        text = extract_paragraph(txt_path)
        if not text:
            print(f"[{index}/{total}] SKIP empty {rel}")
            skipped += 1
            continue

        print(f"[{index}/{total}] rendering {rel} ({len(text.split())} words)")
        try:
            ttm.render_elevenlabs(text, VOICE, MODEL, STABILITY, SIMILARITY, STYLE,
                                  out_path, api_key, OUTPUT_FORMAT)
            rendered += 1
        except SystemExit as exc:
            print(f"            FAILED {rel}: {exc}")
            failed += 1

    print(f"\n{ZONE}: {rendered} rendered, {skipped} kept/skipped, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

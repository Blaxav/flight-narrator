#!/usr/bin/env python3
"""Generate one French narration per Horde flight route using the OpenAI API.

Walks ``travels/horde/<source>/<destination>/duration.txt`` and, for each route,
fills the ``prompts/narration.md`` template's « Entrées » section, calibrates the
requested length to the flight duration, asks the LLM for the narration, and
writes the resulting paragraph to ``narration.txt`` next to ``duration.txt``.

Length calibration: the reference text ``Ratchet.txt`` is ~175 words for a 66 s
flight, i.e. ~2.6 words/second at a slow storyteller pace. We round to
``duration_seconds * 2.5`` words (minimum 120).

Usage:

    python tools/generate_narrations.py --limit 3      # quick sample
    python tools/generate_narrations.py                # everything (resumable)
    python tools/generate_narrations.py --force --model gpt-4o
"""

import argparse
import concurrent.futures
import os
import re
import sys
import threading
import time

from openai import OpenAI

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PROMPT_PATH = os.path.join(ROOT, "prompts", "narration.md")
HORDE_DIR = os.path.join(ROOT, "travels", "horde")
ENV_PATH = os.path.join(ROOT, ".env")

WORDS_PER_SECOND = 2.5   # storyteller French pace (Ratchet ~175 words / 66 s)
MIN_WORDS = 120
MAX_WORDS = 600          # gpt-4o refuses single responses much above ~1000 words
DEFAULT_MODEL = "gpt-4o"

SYSTEM_PROMPT = (
    "Tu es un assistant d'écriture pour un addon de World of Warcraft Classic. "
    "Tu appliques exactement les instructions du message utilisateur et tu ne "
    "produis rien d'autre que la narration demandée."
)

# Matches the template's bullet list under "## Entrées" (header + one or more
# "- **Label** : ..." lines) so we can inject the concrete values regardless of
# the exact wording of each bullet.
ENTREES_RE = re.compile(
    r"## Entrées \(à remplir pour chaque voyage\)\s*\n(?:- \*\*[^*]+\*\*[^\n]*\n)+"
)
# Matches the fixed word-count hint in the expected-output block, e.g.
# "environ 180 à 220 mots, à lire en ~1 min 30".
WORDCOUNT_RE = re.compile(r"environ \d+ à \d+ mots, à lire en ~[^>]*")


def load_env(path):
    """Minimal .env loader (no external dependency)."""
    env = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                env[key.strip()] = value.strip()
    except FileNotFoundError:
        pass
    return env


def mmss(seconds):
    m, s = divmod(int(seconds), 60)
    if m == 0:
        return f"{s} s"
    return f"{m} min {s:02d}"


def target_words(duration_s, max_words=MAX_WORDS):
    return min(max(MIN_WORDS, round(duration_s * WORDS_PER_SECOND)), max_words)


def split_name_zone(folder_name):
    if ", " in folder_name:
        name, zone = folder_name.split(", ", 1)
    elif "," in folder_name:
        name, zone = folder_name.split(",", 1)
    else:
        name, zone = folder_name, ""
    return name.strip(), zone.strip()


def fill_prompt(template, destination, zone, faction, duration_s, max_words=MAX_WORDS):
    """Return the template with the Entrées filled and the length calibrated."""
    words = target_words(duration_s, max_words)
    lo = max(80, round(words * 0.85))
    hi = round(words * 1.15)

    entrees = (
        "## Entrées (remplies pour ce voyage)\n\n"
        f"- **Destination** : {destination}\n"
        f"- **Région / zone** : {zone}\n"
        f"- **Faction du vol** : {faction}\n"
        f"- **Durée du vol** : {duration_s} secondes (~{mmss(duration_s)}).\n"
    )

    template = ENTREES_RE.sub(entrees, template, count=1)
    # Firm length requirement in the expected-output block.
    template = WORDCOUNT_RE.sub(
        f"de {lo} à {hi} mots (exigence stricte), à lire en ~{mmss(duration_s)}",
        template,
        count=1,
    )
    # Reinforce the length constraint right before the final instruction.
    length_note = (
        "## Contrainte de longueur (stricte)\n\n"
        f"Le texte doit faire entre {lo} et {hi} mots. "
        "Ne sois pas plus court : développe l'histoire, les lieux, les personnages "
        "et l'enjeu jusqu'à atteindre la longueur demandée, en restant fidèle au "
        "lore. Ne réponds rien d'autre que la narration demandée.\n\n"
    )
    template = template.replace(
        "## Instruction finale", length_note + "## Instruction finale", 1
    )
    return template


def extract_paragraph(raw):
    """Keep only the narration paragraph from the LLM's formatted output."""
    if not raw:
        return ""
    text = raw.strip()

    # Strip markdown code fences the model may add around the whole output.
    text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
    text = re.sub(r"\s*```$", "", text).strip()

    # Drop everything from a horizontal rule ("---") onward.
    text = re.split(r"\n\s*-{3,}\s*\n", text)[0]
    # Drop a trailing "Durée estimée : ..." / "Clé ..." line if present.
    text = re.split(r"\n\s*(?:Durée estimée|Duree estimee|Clé)\s*[:：]", text)[0]

    lines = [ln.rstrip() for ln in text.split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    # Drop a "<Destination> ===========" header on a single line.
    if lines and re.search(r"=+\s*$", lines[0]):
        lines.pop(0)
    # Drop a "<Destination>\n=========" header on two lines.
    elif len(lines) >= 2 and re.fullmatch(r"=+\s*", lines[1].strip()):
        lines = lines[2:]
    while lines and not lines[-1].strip():
        lines.pop()

    paragraph = " ".join(ln.strip() for ln in lines if ln.strip()).strip()
    return paragraph


def collect_routes(horde_dir):
    routes = []
    for source in sorted(os.listdir(horde_dir)):
        src_path = os.path.join(horde_dir, source)
        if not os.path.isdir(src_path):
            continue
        for dest in sorted(os.listdir(src_path)):
            dest_path = os.path.join(src_path, dest)
            dur_path = os.path.join(dest_path, "duration.txt")
            if not os.path.isdir(dest_path) or not os.path.isfile(dur_path):
                continue
            with open(dur_path, encoding="utf-8") as f:
                duration = int(f.read().strip())
            routes.append((source, dest, dest_path, duration))
    return routes


MAX_ATTEMPTS = 6


def generate_one(client, model, template, source, dest, dest_path, duration_s, max_words=MAX_WORDS):
    dest_name, dest_zone = split_name_zone(dest)
    prompt = fill_prompt(template, dest_name, dest_zone, "Horde", duration_s, max_words)

    last_error = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.8,
            )
            paragraph = extract_paragraph(resp.choices[0].message.content)
            if not paragraph:
                raise ValueError("empty narration after extraction")
            out_path = os.path.join(dest_path, "narration.txt")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(paragraph + "\n")
            return ("ok", source, dest, len(paragraph.split()))
        except Exception as exc:  # noqa: BLE001 - report and retry with backoff
            last_error = exc
            msg = str(exc)
            is_rate_limit = ("429" in msg) or ("rate_limit" in msg) or ("rate limit" in msg.lower())
            if is_rate_limit:
                m = re.search(r"try again in ([\d.]+)s", msg)
                delay = (float(m.group(1)) + 0.5) if m else min(2 ** attempt, 30)
            else:
                delay = 2.0
            if attempt < MAX_ATTEMPTS - 1:
                time.sleep(min(delay, 30))
    return ("error", source, dest, str(last_error))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0,
                        help="generate only the first N routes (0 = all)")
    parser.add_argument("--force", action="store_true",
                        help="regenerate existing narration.txt files")
    parser.add_argument("--model",
                        default=os.environ.get("NARRATION_MODEL", DEFAULT_MODEL))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-words", type=int, default=MAX_WORDS,
                        help="cap the narration length in words (default 600)")
    args = parser.parse_args()

    env = load_env(ENV_PATH)
    for key in ("OPENAI_API_KEY",):
        if env.get(key) and not os.environ.get(key):
            os.environ[key] = env[key]

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY is missing (set it in .env or the environment).")
        sys.exit(1)

    with open(PROMPT_PATH, encoding="utf-8") as f:
        template = f.read()

    routes = collect_routes(HORDE_DIR)
    todo = []
    skipped = 0
    for source, dest, dest_path, duration in routes:
        out_path = os.path.join(dest_path, "narration.txt")
        if not args.force and os.path.isfile(out_path) and os.path.getsize(out_path) > 0:
            skipped += 1
            continue
        todo.append((source, dest, dest_path, duration))
        if args.limit and len(todo) >= args.limit:
            break

    print(f"{len(routes)} routes found, {len(todo)} to generate, "
          f"{skipped} already present (model={args.model}).")

    client = OpenAI(api_key=api_key)
    counter = {"ok": 0, "error": 0, "done": 0}
    lock = threading.Lock()

    def work(item):
        source, dest, dest_path, duration = item
        result = generate_one(client, args.model, template, source, dest, dest_path,
                              duration, args.max_words)
        with lock:
            counter["done"] += 1
            counter[result[0]] += 1
            status = "OK " if result[0] == "ok" else "ERR"
            detail = f" ({result[3]} words)" if result[0] == "ok" else f" ({result[3]})"
            print(f"[{counter['done']}/{len(todo)}] {status} {source} -> {dest}{detail}",
                  flush=True)
        return result

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(work, todo))

    print(f"\nDone: {counter['ok']} ok, {counter['error']} errors.")


if __name__ == "__main__":
    main()


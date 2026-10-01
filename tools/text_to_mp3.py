#!/usr/bin/env python3
"""Turn text into an MP3 narration clip with a state-of-the-art, natural voice.

Three backends, chosen with --backend (or auto-detected):

    openai      gpt-4o-mini-tts (or tts-1-hd for quality). The voice is steered with a natural
                language "instructions" prompt, which is exactly what you want for
                "voix grave, lecture lente, narrateur de conte". Deep male voice:
                onyx. Needs OPENAI_API_KEY.
    elevenlabs  Eleven v4 / Multilingual v2. Widely considered the most natural
                intonation for French; deep storyteller voice "Antoni" (or Daniel,
                George). Needs ELEVENLABS_API_KEY.
    edge        Microsoft Edge neural TTS (free, no account, no key) - the
                previous default, kept as a zero-setup fallback.

Without any API key, --backend auto falls back to edge so the tool always works.
Set OPENAI_API_KEY or ELEVENLABS_API_KEY (or pass --api-key) to unlock the
state-of-the-art backends.

Examples:

    python tools/text_to_mp3.py "Vous quittez Hurlevent derriere vous, cap au nord vers la foret d'Elwynn."
    python tools/text_to_mp3.py --backend openai -o elwynn.mp3 "Votre texte ici..."
    python tools/text_to_mp3.py --backend elevenlabs --model eleven_v4 -o elwynn.mp3 --text-file lore.txt

    setx OPENAI_API_KEY "sk-..."      # then re-open the terminal
    setx ELEVENLABS_API_KEY "..."     # then re-open the terminal

Notes:
  * OpenAI  "instructions" steer intonation, pacing and emotion (the default is a
            deep, slow, storyteller prompt in French).
  * ElevenLabs stability/similarity/style control the delivery; for a solemn
    storyteller keep stability ~0.5 and style low.
"""

import argparse
import asyncio
import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.request

import edge_tts

# Deep storyteller voice for each backend (the closest to the WoW narrator).
DEFAULT_VOICE = {
    "openai": "onyx",          # deep, calm male; echo/ash/verse are the other males
    "elevenlabs": "Antoni",    # deep, warm storyteller; Daniel/George also work
    "edge": "fr-FR-HenriNeural",
}

DEFAULT_MODEL = {
    "openai": "gpt-4o-mini-tts",            # alternatives: tts-1 (fast), tts-1-hd (quality)
    "elevenlabs": "eleven_multilingual_v2",  # eleven_v4 = latest, most emotive
    "edge": None,
}

OPENAI_DEFAULT_INSTRUCTIONS = (
    "Parle d'une voix grave, posee et lente, comme un narrateur de conte qui "
    "raconte une legende au coin du feu. Articule bien, laisse des pauses "
    "naturelles, et donne de l'emotion a l'histoire."
)

ELEVENLABS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice}"
OPENAI_URL = "https://api.openai.com/v1/audio/speech"


def slugify(text: str) -> str:
    """Turn arbitrary text into a safe file-name stem (ASCII only)."""
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    stem = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_text).strip("-").lower()
    return stem[:60] or "narration"


def read_text(args: argparse.Namespace) -> str:
    """Resolve the text to speak from --text-file, positional args, or stdin."""
    if args.text_file:
        with open(args.text_file, "r", encoding="utf-8-sig") as handle:
            return handle.read().strip()
    if args.text:
        return " ".join(args.text).strip()
    if not sys.stdin.isatty():
        return sys.stdin.read().strip()
    raise SystemExit("no text given: pass it as an argument, with --text-file, or on stdin")


def resolve_backend(requested: str) -> str:
    if requested != "auto":
        return requested
    if os.environ.get("ELEVENLABS_API_KEY"):
        return "elevenlabs"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    return "edge"


def load_dotenv() -> None:
    """Load TTS API keys from a .env file, without overriding the real environment.

    Looks for .env next to this script (the repo root) and in the current
    working directory. A variable already present in the environment always wins.
    """
    candidates = [os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")]
    cwd_env = os.path.join(os.getcwd(), ".env")
    if cwd_env not in candidates:
        candidates.append(cwd_env)
    for path in candidates:
        if not os.path.isfile(path):
            continue
        with open(path, "r", encoding="utf-8") as handle:
            for raw in handle:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and value and key not in os.environ:
                    os.environ[key] = value


def _post_json(url: str, payload: dict, headers: dict) -> bytes:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")
        raise SystemExit(f"request failed ({error.code}): {detail}") from None


async def render_edge(text, voice, rate, pitch, volume, output) -> None:
    kwargs = {"rate": rate}
    if pitch:
        kwargs["pitch"] = pitch
    if volume:
        kwargs["volume"] = volume
    communicate = edge_tts.Communicate(text, voice, **kwargs)
    await communicate.save(output)


def render_openai(text, voice, model, instructions, output, api_key) -> None:
    if not api_key:
        raise SystemExit("--backend openai needs OPENAI_API_KEY (or --api-key).")
    payload = {
        "model": model,
        "voice": voice,
        "input": text,
        "instructions": instructions,
        "response_format": "mp3",
    }
    audio = _post_json(OPENAI_URL, payload, {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    })
    _write(audio, output)


def render_elevenlabs(text, voice, model, stability, similarity, style, output, api_key) -> None:
    if not api_key:
        raise SystemExit("--backend elevenlabs needs ELEVENLABS_API_KEY (or --api-key).")
    payload = {
        "text": text,
        "model_id": model,
        "voice_settings": {
            "stability": stability,
            "similarity_boost": similarity,
            "style": style,
            "use_speaker_boost": True,
        },
    }
    audio = _post_json(ELEVENLABS_URL.format(voice=voice), payload, {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
    })
    _write(audio, output)


def _write(audio: bytes, output: str) -> None:
    with open(output, "wb") as handle:
        handle.write(audio)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Turn text into an MP3 narration clip with a deep, slow storyteller voice.",
        epilog="Backends: openai (steerable intonation), elevenlabs (most natural French), edge (free, no key).",
    )
    parser.add_argument("text", nargs="*", help="The text to speak (joined with spaces).")
    parser.add_argument("-o", "--output", help="Output MP3 path. Defaults to <slug>.mp3 in the current folder.")
    parser.add_argument("--text-file", metavar="PATH", help="Read the text from this UTF-8 file instead of the command line.")

    parser.add_argument("--backend", choices=["auto", "openai", "elevenlabs", "edge"], default="auto",
                        help="Which engine to use (default: auto = elevenlabs/openai if a key is set, else edge).")
    parser.add_argument("--voice", default=None,
                        help="Voice name/id. Defaults per backend: openai=onyx, elevenlabs=Antoni, edge=fr-FR-HenriNeural.")
    parser.add_argument("--model", default=None,
                        help="Model id. Defaults per backend: openai=gpt-4o-mini-tts, elevenlabs=eleven_multilingual_v2.")
    parser.add_argument("--api-key", default=None,
                        help="API key. Defaults to $OPENAI_API_KEY or $ELEVENLABS_API_KEY.")

    parser.add_argument("--instructions", default=None,
                        help="(openai) Natural-language style prompt steering intonation, pacing, emotion.")

    parser.add_argument("--rate", default="-15%", help="(edge) Speed, e.g. -15%% or -20%%.")
    parser.add_argument("--pitch", default=None, help="(edge) Pitch shift, e.g. -8Hz for a deeper voice.")
    parser.add_argument("--volume", default=None, help="(edge) Volume, e.g. -5%%.")

    parser.add_argument("--stability", type=float, default=0.5, help="(elevenlabs) 0-1, higher = more consistent/less expressive.")
    parser.add_argument("--similarity", type=float, default=0.75, help="(elevenlabs) 0-1, closeness to the reference voice.")
    parser.add_argument("--style", type=float, default=0.2, help="(elevenlabs) 0-1, higher = more expressive performance.")
    args = parser.parse_args()

    load_dotenv()

    text = read_text(args)
    if not text:
        raise SystemExit("the text is empty")

    backend = resolve_backend(args.backend)
    voice = args.voice or DEFAULT_VOICE[backend]
    output = args.output or (slugify(text) + ".mp3")

    if backend == "edge":
        asyncio.run(render_edge(text, voice, args.rate, args.pitch, args.volume, output))
        print(f"[edge] rendered {output} with {voice} at {args.rate}")
        print("tip: set OPENAI_API_KEY or ELEVENLABS_API_KEY for state-of-the-art intonation")
    elif backend == "openai":
        model = args.model or DEFAULT_MODEL["openai"]
        instructions = args.instructions or OPENAI_DEFAULT_INSTRUCTIONS
        api_key = args.api_key or os.environ.get("OPENAI_API_KEY")
        render_openai(text, voice, model, instructions, output, api_key)
        print(f"[openai] rendered {output} with {voice} ({model})")
    else:  # elevenlabs
        model = args.model or DEFAULT_MODEL["elevenlabs"]
        api_key = args.api_key or os.environ.get("ELEVENLABS_API_KEY")
        render_elevenlabs(text, voice, model, args.stability, args.similarity, args.style, output, api_key)
        print(f"[elevenlabs] rendered {output} with {voice} ({model})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

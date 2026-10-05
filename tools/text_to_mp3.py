#!/usr/bin/env python3
"""Turn text into an MP3 narration clip with ElevenLabs.

Single backend: ElevenLabs, the most natural intonation for French. The deep
storyteller voice is "Martin Dupont" (a5n9pJUnAhX4fn7lx3uo), with model
eleven_v4 (the latest, most emotive model). Needs
ELEVENLABS_API_KEY.

Every text is prefixed with "[lentement]" (slow) before it is sent, and the
delivery is steered by the voice settings below (stability/similarity/style).

Examples:

    python tools/text_to_mp3.py "Vous quittez Stormwind derriere vous, cap au nord vers la foret d'Elwynn."
    python tools/text_to_mp3.py --model eleven_v4 -o elwynn.mp3 --text-file lore.txt

    setx ELEVENLABS_API_KEY "..."     # then re-open the terminal
"""

import argparse
import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.request

# Deep French storyteller voice (the closest to the WoW narrator).
DEFAULT_VOICE = "a5n9pJUnAhX4fn7lx3uo"  # Martin Dupont, deep warm French storyteller
DEFAULT_MODEL = "eleven_v4"  # latest, most emotive

# Smallest MP3 ElevenLabs offers: 22.05 kHz, 32 kbps, mono. Voice-only narration
# stays perfectly intelligible at this bitrate and files are ~4x smaller than the
# default mp3_44100_128 (stereo). See --output-format for other values, e.g.
# mp3_44100_64 (mono, a touch fuller) or opus_48000_32 (Opus in an OGG container).
DEFAULT_OUTPUT_FORMAT = "mp3_22050_32"

ELEVENLABS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format={output_format}"

# Prepended to every text before it is sent to ElevenLabs.
PREFIX = "[lentement] "

# Allowed ElevenLabs output formats (codec_sample_rate_bitrate).
OUTPUT_FORMATS = (
    "alaw_8000",
    "mp3_22050_32",
    "mp3_24000_48",
    "mp3_44100_32",
    "mp3_44100_64",
    "mp3_44100_96",
    "mp3_44100_128",
    "mp3_44100_192",
    "opus_48000_32",
    "opus_48000_64",
    "opus_48000_96",
    "opus_48000_128",
    "opus_48000_192",
    "pcm_8000",
    "pcm_16000",
    "pcm_22050",
    "pcm_24000",
    "pcm_32000",
    "pcm_44100",
    "pcm_48000",
    "ulaw_8000",
    "wav_8000",
    "wav_16000",
    "wav_22050",
    "wav_24000",
    "wav_32000",
    "wav_44100",
    "wav_48000",
)


def default_extension(output_format: str) -> str:
    """Return the file extension matching an ElevenLabs output format."""
    if output_format.startswith("opus"):
        return ".ogg"
    if output_format.startswith(("wav", "pcm")):
        return ".wav"
    if output_format.startswith(("ulaw", "alaw")):
        return ".raw"
    return ".mp3"


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


def render_elevenlabs(text, voice, model, stability, similarity, style, output, api_key, output_format=DEFAULT_OUTPUT_FORMAT) -> None:
    if not api_key:
        raise SystemExit("ELEVENLABS_API_KEY is missing (or pass --api-key).")
    payload = {
        "text": PREFIX + text,
        "model_id": model,
        "voice_settings": {
            "stability": stability,
            "similarity_boost": similarity,
            "style": style,
            "use_speaker_boost": True,
        },
    }
    audio = _post_json(ELEVENLABS_URL.format(voice=voice, output_format=output_format), payload, {
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
        epilog="Backend: ElevenLabs (Martin Dupont, deep French storyteller).",
    )
    parser.add_argument("text", nargs="*", help="The text to speak (joined with spaces).")
    parser.add_argument("-o", "--output", help="Output MP3 path. Defaults to <slug>.mp3 in the current folder.")
    parser.add_argument("--text-file", metavar="PATH", help="Read the text from this UTF-8 file instead of the command line.")

    parser.add_argument("--voice", default=None,
                        help="ElevenLabs voice name/id (default: Martin Dupont).")
    parser.add_argument("--model", default=None,
                        help="ElevenLabs model id (default: eleven_v4).")
    parser.add_argument("--api-key", default=None,
                        help="API key. Defaults to $ELEVENLABS_API_KEY.")

    parser.add_argument("--stability", type=float, default=0.15, help="(elevenlabs) 0-1, higher = more consistent/less expressive.")
    parser.add_argument("--similarity", type=float, default=0.09, help="(elevenlabs) 0-1, closeness to the reference voice.")
    parser.add_argument("--style", type=float, default=0.2, help="(elevenlabs) 0-1, higher = more expressive performance.")
    parser.add_argument("--output-format", choices=OUTPUT_FORMATS, default=None,
                        help=f"output codec/bitrate (default: {DEFAULT_OUTPUT_FORMAT}, a small mono MP3).")
    args = parser.parse_args()

    load_dotenv()

    text = read_text(args)
    if not text:
        raise SystemExit("the text is empty")

    voice = args.voice or DEFAULT_VOICE
    model = args.model or DEFAULT_MODEL
    api_key = args.api_key or os.environ.get("ELEVENLABS_API_KEY")
    output_format = args.output_format or DEFAULT_OUTPUT_FORMAT
    output = args.output or (slugify(text) + default_extension(output_format))

    render_elevenlabs(text, voice, model, args.stability, args.similarity, args.style, output, api_key, output_format)
    print(f"[elevenlabs] rendered {output} with {voice} ({model}, {output_format})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

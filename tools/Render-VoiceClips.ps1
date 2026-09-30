<#
.SYNOPSIS
Renders the narration lines in tools\lines.txt into voice\<locale>\ clips.

.DESCRIPTION
The clips are ordinary MP3 files that the addon plays with PlaySoundFile, which
is the only way a voice can really travel with an addon: an addon cannot install
a Text to Speech voice or ship a speech engine, but it can ship the audio. One
file per line key, named <key>.mp3, in the folder for the locale it speaks.

Rendering needs the edge-tts package (free, no account, no API key) and an
internet connection while it runs. Nothing extra is needed in game.

    python -m pip install edge-tts
    powershell -ExecutionPolicy Bypass -File tools\Render-VoiceClips.ps1 -Voice fr-FR-HenriNeural -LinesFile tools\lines.fr.txt

Clips are rendered at -Rate, -15% by default, which is deliberately below the
voice's own pace: narration that plays over a flight has to leave room for the
flight, and a neural voice at full speed reads a lore line like a headline. The
rate is baked into the audio, so it belongs to the voice: change -Rate and
re-render with -Force, because an existing clip is otherwise kept. The client's
Text to Speech, which speaks only for keys that have no clip, has its own speed
setting and this addon never writes it: the client's own /tts rate <n> is what
changes that one.

Voices that read well and are worth trying: en-US-AriaNeural, en-US-GuyNeural,
en-GB-SoniaNeural, fr-FR-DeniseNeural, fr-FR-HenriNeural. List them all with
python -m edge_tts --list-voices

After rendering, /reload in game: the client only sees sound files that existed
when it loaded, then test with  /fn clip test  (or /fn).

.PARAMETER Voice
An edge-tts voice name, for example fr-FR-DeniseNeural.

.PARAMETER Locale
The folder under voice\ to write into, for example frFR. Defaults to the
language of the voice: fr-FR-DeniseNeural writes to voice\frFR\.

.PARAMETER LinesFile
The key|text file to render. Defaults to tools\lines.txt.

.PARAMETER Rate
The speed edge-tts renders at, as a percentage of the voice's own pace, for
example -15% (the default, a little slower) or +10%. Existing clips are kept
unless -Force is given, so changing the rate means re-rendering with -Force.

.PARAMETER Force
Re-render clips that are already there.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Voice,
    [string]$Locale = "",
    [string]$LinesFile = "",
    [string]$Rate = "-15%",
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$toolsDir = $PSScriptRoot
$addonDir = Split-Path -Parent $toolsDir

if (-not $LinesFile) { $LinesFile = Join-Path $toolsDir "lines.txt" }
if (-not (Test-Path $LinesFile)) { throw "no line file at $LinesFile" }

# "fr-FR-DeniseNeural" -> "frFR", which is what GetLocale returns in game.
if (-not $Locale) {
    $parts = $Voice -split "-"
    if ($parts.Count -lt 2) {
        throw "-Locale is required: cannot read a language out of the voice name '$Voice'"
    }
    $Locale = $parts[0] + $parts[1]
}

$localeDir = Join-Path (Join-Path $addonDir "voice") $Locale
if (-not (Test-Path $localeDir)) { New-Item -ItemType Directory -Path $localeDir | Out-Null }

$previousPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& python -c "import edge_tts" 2>&1 | Out-Null
$edgeTtsMissing = ($LASTEXITCODE -ne 0)
$ErrorActionPreference = $previousPreference

if ($edgeTtsMissing) {
    throw "edge-tts is not installed for this python. Run:  python -m pip install edge-tts"
}

$rendered = 0
$skipped = 0
$failed = 0

# edge-tts writes progress to stderr, which must not be read as a failure here.
$ErrorActionPreference = "Continue"

foreach ($rawLine in Get-Content $LinesFile) {
    $line = $rawLine.Trim()
    if ($line -eq "" -or $line.StartsWith("#")) { continue }

    $separator = $line.IndexOf("|")
    if ($separator -lt 1) {
        Write-Warning "skipping a line with no key|text separator: $line"
        continue
    }

    $key = $line.Substring(0, $separator).Trim()
    $text = $line.Substring($separator + 1).Trim()
    if ($key -eq "" -or $text -eq "") {
        Write-Warning "skipping an incomplete line: $line"
        continue
    }

    $outPath = Join-Path $localeDir ($key + ".mp3")
    if ((Test-Path $outPath) -and -not $Force) {
        Write-Host ("kept     {0}" -f $outPath)
        $skipped++
        continue
    }

    Write-Host ("rendering {0} with {1} at {2}" -f $key, $Voice, $Rate)
    # --rate= as one token: a bare -15% would be read as another option.
    & python -m edge_tts --voice $Voice "--rate=$Rate" --text $text --write-media $outPath
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "edge-tts failed for '$key'"
        $failed++
        continue
    }
    $rendered++
}

Write-Host ""
Write-Host ("voice\{0}: {1} rendered at {2}, {3} already there, {4} failed" -f $Locale, $rendered, $Rate, $skipped, $failed)
Write-Host "now /reload in game, then:  /fn clip test"

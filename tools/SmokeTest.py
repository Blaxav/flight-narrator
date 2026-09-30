"""Smoke test for FlightNarrator.lua: loads the addon into an embedded Lua
runtime with mocked WoW APIs and drives the slash commands. Not part of the
addon (which stays plain Lua, no dependencies) - it checks what is otherwise
only testable in game.

    python tools/SmokeTest.py
"""
import os
import sys

from lupa import LuaRuntime

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUA_FILE = os.path.join(REPO, "FlightNarrator.lua")
CLIP_FS_ROOT = os.path.join(REPO, "voice") + os.sep

MOCK = r'''
CHAT = {}
CALLS = {}

function strtrim(s) return (tostring(s):gsub("^%s*(.-)%s*$", "%1")) end
function strlower(s) return string.lower(tostring(s)) end
DEFAULT_CHAT_FRAME = { AddMessage = function(self, m) table.insert(CHAT, m) end }

function GetBuildInfo() return "1.15.9", "61234", "2026-01-01", 11509 end
function GetCVar(name) return "1" end
function GetTime() return 100 end
function GetLocale() return LOCALE end

function CreateFrame(kind)
  return {
    registered = {},
    RegisterEvent = function(self, event) table.insert(self.registered, event); return true end,
    SetScript = function(self, script, fn) self.script = fn; return true end,
  }
end

Enum = {
  TtsVoiceType = { Standard = 0, Alternate = 1 },
  TtsBoolSetting = { AlternateSystemVoice = 3 },
  VoiceTtsDestination = { LocalPlayback = 1 },
  VoiceTtsStatusCode = { InvalidArgument = 1, VoiceUnavailable = 2 },
}

local VOICES = {
  { voiceID = 10, name = "Microsoft Hortense Desktop - French" },
  { voiceID = 11, name = "Microsoft Zira Desktop - English (United States)" },
  { voiceID = 12, name = "Microsoft Julie - French (France)" },
}
selectedStandard = 10
selectedAlternate = 11

C_VoiceChat = {
  GetTtsVoices = function()
    local out = {}
    for i, v in ipairs(VOICES) do out[i] = { voiceID = v.voiceID, name = v.name } end
    return out
  end,
  SpeakText = function(...)
    local args = { ... }
    table.insert(CALLS, { call = "SpeakText", args = args })
    return true
  end,
}

C_TTSSettings = {
  GetVoiceOptionID = function(voiceType)
    if voiceType == 1 then return selectedAlternate end
    return selectedStandard
  end,
  SetVoiceOption = function(voiceType, voiceID)
    table.insert(CALLS, { call = "SetVoiceOption", slot = voiceType, voiceID = voiceID })
    if voiceType == 1 then selectedAlternate = voiceID else selectedStandard = voiceID end
    return true
  end,
  GetSpeechRate = function() return 0 end,
  GetSpeechVolume = function() return 100 end,
  GetSetting = function(setting) return true end,
}

function TextToSpeech_GetSelectedVoice(voiceType)
  local wanted = selectedStandard
  if voiceType == 1 then wanted = selectedAlternate end
  for _, v in ipairs(VOICES) do if v.voiceID == wanted then return v end end
  return nil
end

function TextToSpeech_Speak(text, voice, neverQueue, overlap)
  table.insert(CALLS, {
    call = "helper", text = text, voice = voice and voice.name or "nil", neverQueue = neverQueue,
  })
  return true
end

function PlaySoundFile(path, channel)
  table.insert(CALLS, { call = "PlaySoundFile", path = path, channel = channel })
  if not CLIPS_EXIST then return false end
  local relative = path:gsub("^Interface\\AddOns\\FlightNarrator\\voice\\", "")
  local f = io.open(CLIP_FS_ROOT .. relative, "rb")
  if f then f:close() return true end
  return false
end

SlashCmdList = {}
'''

PASS, FAIL = [], []


def check(label, condition, detail=""):
    (PASS if condition else FAIL).append(label)
    print(("  PASS  " if condition else "  FAIL  ") + label + ("" if condition else "   <- " + detail))


def build(clips_exist=True, locale="frFR"):
    runtime = LuaRuntime(unpack_returned_tuples=True)
    runtime.execute("LOCALE = %r\nCLIPS_EXIST = %s\nCLIP_FS_ROOT = %r\n"
                    % (locale, "true" if clips_exist else "false", CLIP_FS_ROOT))
    runtime.execute(MOCK)
    with open(LUA_FILE, encoding="utf-8") as handle:
        runtime.execute(handle.read())
    return runtime


def read(runtime, name):
    table = runtime.globals()[name]
    return [table[i] for i in range(1, len(table) + 1)]


def chat(runtime):
    return [str(line) for line in read(runtime, "CHAT")]


def run(runtime, command):
    runtime.execute("CHAT = {}\nCALLS = {}")
    runtime.globals().SlashCmdList["FLIGHTNARRATOR"](command)
    return chat(runtime), read(runtime, "CALLS")


def show(lines):
    for line in lines:
        print("        " + line)


print("Loading %s into embedded Lua..." % os.path.basename(LUA_FILE))
lua = build(clips_exist=True, locale="frFR")

print("\n/fn voices")
lines, recorded = run(lua, "voices")
show(lines)
check("lists all three voices", any("Microsoft Julie" in l for l in lines), str(lines))
check("marks the voice in use", any("* 1." in l for l in lines), str(lines))
check("marks the alternate voice", any("~ 2." in l for l in lines), str(lines))

print("\n/fn voice 3")
lines, recorded = run(lua, "voice 3")
show(lines)
sets = [c for c in recorded if c["call"] == "SetVoiceOption"]
check("calls SetVoiceOption once", len(sets) == 1, str(recorded))
check("writes the standard slot (voiceType 0)", bool(sets) and sets[0]["slot"] == 0, str(sets))
check("writes voice id 12 (Julie)", bool(sets) and sets[0]["voiceID"] == 12, str(sets))
check("speaks a sample through the client helper",
      any(c["call"] == "helper" for c in recorded), str(recorded))

print("\n/fn voices (after the change)")
lines, recorded = run(lua, "voices")
check("the marker moved to Julie", any("* 3." in l for l in lines), str(lines))

print("\n/fn voice 3 alternate")
lines, recorded = run(lua, "voice 3 alternate")
show(lines)
sets = [c for c in recorded if c["call"] == "SetVoiceOption"]
check("writes the alternate slot (voiceType 1)", bool(sets) and sets[0]["slot"] == 1, str(sets))
check("stays quiet when filling the alternate slot",
      not any(c["call"] == "helper" for c in recorded), str(recorded))

print("\n/fn voice Microsoft Hortense Desktop - French   (by name)")
lines, recorded = run(lua, "voice Microsoft Hortense Desktop - French")
show(lines)
sets = [c for c in recorded if c["call"] == "SetVoiceOption"]
check("resolves a voice by name", bool(sets) and sets[0]["voiceID"] == 10, str(sets))

print("\n/fn voice 99   (out of range)")
lines, recorded = run(lua, "voice 99")
show(lines)
check("refuses an impossible index", any("no voice number 99" in l for l in lines), str(lines))
check("does not touch the client", not recorded, str(recorded))

print("\n/fn clip test   (voice/frFR/test.mp3 exists)")
lines, recorded = run(lua, "clip test")
show(lines)
plays = [c for c in recorded if c["call"] == "PlaySoundFile"]
check("plays voice\\frFR\\test.mp3",
      any("voice\\frFR\\test.mp3" in c["path"] for c in plays), str(plays))
check("uses the Dialog channel", bool(plays) and plays[0]["channel"] == "Dialog", str(plays))
check("does not also synthesise", not any(c["call"] == "helper" for c in recorded), str(recorded))

print("\n/fn clip nope   (no such clip)")
lines, recorded = run(lua, "clip nope")
show(lines)
check("says so instead of failing quietly", any("no clip called nope" in l for l in lines), str(lines))

print("\n/fn   (the clip is preferred for the test line)")
lines, recorded = run(lua, "")
show(lines)
check("plays the shipped clip", any("playing the shipped clip" in l for l in lines), str(lines))

print("\n/fn above you, the spires of Dalaran.   (free text)")
lines, recorded = run(lua, "above you, the spires of Dalaran.")
show(lines)
check("free text goes through Text to Speech",
      any(c["call"] == "helper" and c["text"] == "above you, the spires of Dalaran."
          for c in recorded), str(recorded))
check("passes neverQueue = true", any(c["neverQueue"] is True for c in recorded), str(recorded))

print("\n/fn diag")
lines, recorded = run(lua, "diag")
show(lines)
check("reports the client build and interface",
      any("1.15.9" in l and "11509" in l for l in lines), str(lines))
check("reports the voice in the standard slot",
      any("narrator voice (standard slot): Microsoft Hortense" in l for l in lines), str(lines))
check("reports the locale clips are read from",
      any("locale: frFR" in l and "voice\\frFR\\" in l for l in lines), str(lines))

print("\nA client with no clips rendered at all")
bare = build(clips_exist=False, locale="frFR")
lines, recorded = run(bare, "")
show(lines)
check("falls back to the client's own speech",
      any(c["call"] == "helper" for c in recorded), str(recorded))
check("says so in chat",
      any("speaking with the client's own helper" in l for l in lines), str(lines))

print("\nA client in another language (deDE): the library language is the fallback")
other = build(clips_exist=True, locale="deDE")
lines, recorded = run(other, "")
show(lines)
check("probes the client's own folder first",
      any("voice\\deDE\\test" in (c["path"] or "") for c in recorded), str(recorded))
check("falls through to the language the library is written in",
      any("voice\\frFR\\test.mp3" in (c["path"] or "") for c in recorded), str(recorded))
check("does not synthesise when the fallback clip exists",
      not any(c["call"] == "helper" for c in recorded), str(recorded))
lines, recorded = run(other, "diag")
check("diag reports both folders, in the order it will read them",
      any("voice\\deDE\\ or voice\\frFR\\" in l for l in lines), str(lines))

print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
for label in FAIL:
    print("  failed: " + label)
sys.exit(1 if FAIL else 0)


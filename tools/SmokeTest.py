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
function GetLocale() return LOCALE end

-- The test's clock, and the timers the addon's takeoff watch polls with:
-- advance() in Python moves NOW and runs whatever came due, which is how a
-- flight that takes a moment to start is exercised.
NOW = 100
function GetTime() return NOW end
TIMERS = {}
C_Timer = {}
function C_Timer.After(seconds, fn) table.insert(TIMERS, { due = NOW + seconds, fn = fn }) end
function RunDueTimers()
  local ran = 0
  local i = 1
  while i <= #TIMERS do
    local timer = TIMERS[i]
    if timer.due <= NOW then
      table.remove(TIMERS, i)
      ran = ran + 1
      timer.fn()
    else
      i = i + 1
    end
  end
  return ran
end

-- Flight detection: the taxi APIs and the taxi state. ON_TAXI is what the test
-- moves around; UnitOnTaxi is what separates a flight from a cinematic.
ON_TAXI = false
function UnitOnTaxi(unit) return ON_TAXI end

TAXI_NODES = { "Stormwind City", "Ironforge", "Menethil Harbor" }
function TaxiNodeName(slot) return TAXI_NODES[slot] end
function TakeTaxiNode(slot) end

-- hooksecurefunc, without passing the return values through: the one hooked call
-- in the test returns nothing. A client is allowed to refuse a hook, which is
-- how the addon's error handling is exercised: HOOK_REFUSED plays that client.
function hooksecurefunc(name, fn)
  if HOOK_REFUSED then error("Hook is not permitted") end
  local original = _G[name]
  if type(original) ~= "function" then return end
  _G[name] = function(...)
    original(...)
    fn(...)
  end
end

FRAMES = {}

function CreateFrame(kind)
  local frame = {
    registered = {},
    RegisterEvent = function(self, event) table.insert(self.registered, event); return true end,
    SetScript = function(self, script, fn) self.script = fn; self[script] = fn; return true end,
  }
  table.insert(FRAMES, frame)
  return frame
end

-- The client fires an event on the frame that registered it. The test drives the
-- same path, which is also the only way to reach the addon's local event frame
-- from out here.
function FireEvent(event, ...)
  for _, frame in ipairs(FRAMES) do
    if frame.OnEvent then frame.OnEvent(frame, event, ...) end
  end
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


def build(clips_exist=True, locale="frFR", hook_refused=False):
    runtime = LuaRuntime(unpack_returned_tuples=True)
    runtime.execute("LOCALE = %r\nCLIPS_EXIST = %s\nCLIP_FS_ROOT = %r\nHOOK_REFUSED = %s\n"
                    % (locale, "true" if clips_exist else "false", CLIP_FS_ROOT,
                       "true" if hook_refused else "false"))
    runtime.execute(MOCK)
    with open(LUA_FILE, encoding="utf-8") as handle:
        runtime.execute(handle.read())
    return runtime


def read(runtime, name):
    table = runtime.globals()[name]
    return [table[i] for i in range(1, len(table) + 1)]


def chat(runtime):
    return [str(line) for line in read(runtime, "CHAT")]


def reset(runtime):
    runtime.execute("CHAT = {}\nCALLS = {}\nNOW = 100\nTIMERS = {}")


def run(runtime, command):
    reset(runtime)
    runtime.globals().SlashCmdList["FLIGHTNARRATOR"](command)
    return chat(runtime), read(runtime, "CALLS")


def fire(runtime, event, *args):
    reset(runtime)
    runtime.globals().FireEvent(event, *args)
    return chat(runtime), read(runtime, "CALLS")


def advance(runtime, seconds, step=0.5):
    """Move the mock clock on, running the addon's poll callbacks as they come
    due: half a second is one poll of the takeoff watch, so a flight that takes
    a moment to start is a second or two of this."""
    globals_ = runtime.globals()
    moved = 0.0
    while moved < seconds - 1e-9:
        globals_.NOW = float(globals_.NOW) + step
        moved += step
        globals_.RunDueTimers()


def pending_timers(runtime):
    return int(runtime.execute("return #TIMERS"))


def stand_on_the_ground(runtime):
    """End whatever flight the addon thinks is happening: back on the ground,
    with a signal that asks the taxi state. Scenarios that each start a flight
    begin with this, the way a player lands before flying again."""
    runtime.globals().ON_TAXI = False
    runtime.globals().FireEvent("TAXIMAP_CLOSED")


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
check("reports the rate as the character's own, read and never written",
      any("rate 0" in l for l in lines), str(lines))
check("points at the client's own /tts rate for the fallback voice",
      any("/tts rate" in l for l in lines), str(lines))
check("reports that it watches the flight events",
      any("PLAYER_CONTROL_LOST" in l and "PLAYER_CONTROL_GAINED" in l for l in lines), str(lines))

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

print("\nPLAYER_LOGIN   (where the taxi hook is installed)")
lines, recorded = fire(lua, "PLAYER_LOGIN")
show(lines)
check("says flights are narrated from now on",
      any("flights are narrated from now on" in l for l in lines), str(lines))
check("points at /fn flight, the only help text this addon has",
      any("/fn flight" in l for l in lines), str(lines))

print("\n/fn flight   (the trigger, without the taxi)")
lines, recorded = run(lua, "flight")
show(lines)
check("announces a flight", any("a flight begins." in l for l in lines), str(lines))
check("plays the ratchet clip once, after probing for an ogg",
      len([c for c in recorded if (c["path"] or "").endswith("ratchet.mp3")]) == 1, str(recorded))
check("does not also synthesise", not any(c["call"] == "helper" for c in recorded), str(recorded))

print("\n/fn flight Stormwind City   (a named destination)")
lines, recorded = run(lua, "flight Stormwind City")
show(lines)
check("names the destination in chat",
      any("a flight begins, to Stormwind City." in l for l in lines), str(lines))

print("\nA real taxi on era: the click, then the taxi state a moment later")
print("  (0.3.2 waited for PLAYER_CONTROL_LOST here, which era never fires)")
reset(lua)
lua.globals().ON_TAXI = False
lua.globals().TakeTaxiNode(1)
show(chat(lua))
check("does not announce on the click alone, with the player still on the ground",
      not any("a flight begins" in l for l in chat(lua)), str(chat(lua)))
lua.globals().ON_TAXI = True
advance(lua, 1.0)
lines, recorded = chat(lua), read(lua, "CALLS")
show(lines)
check("announces the flight the click named, once the taxi state arrives",
      any("a flight begins, to Stormwind City." in l for l in lines), str(lines))
check("plays the clip once",
      len([c for c in recorded if (c["path"] or "").endswith("ratchet.mp3")]) == 1, str(recorded))

print("\nThe same flight, a few seconds later   (the watch stops asking)")
before = len(chat(lua))
advance(lua, 2.0)
lines = chat(lua)[before:]
check("stays quiet inside the same flight",
      not any("a flight begins" in l for l in lines), str(lines))

print("\nLanding, on a client that fires nothing at the end of a flight")
lua.globals().ON_TAXI = False
lines, recorded = fire(lua, "TAXIMAP_CLOSED")
show(lines)
check("says nothing about the flight that is over",
      not any("a flight begins" in l for l in lines), str(lines))

print("\nA taxi that is refused: the click, and no flight")
reset(lua)
lua.globals().ON_TAXI = False
lua.globals().TakeTaxiNode(2)
advance(lua, 25.0)
lines = chat(lua)
show(lines)
check("never announces", not any("a flight begins" in l for l in lines), str(lines))
check("stops asking once the watch is over", pending_timers(lua) == 0, str(pending_timers(lua)))

print("\nThe taxi map closing, with no click seen   (a client without the hook)")
reset(lua)
stand_on_the_ground(lua)
lua.globals().ON_TAXI = True
lines, recorded = fire(lua, "TAXIMAP_CLOSED")
show(lines)
check("announces the flight anyway",
      any("a flight begins." in l for l in lines), str(lines))

print("\nUNIT_FLAGS for the player is a signal; for anyone else it is not")
reset(lua)
stand_on_the_ground(lua)
lua.globals().ON_TAXI = True
lines, recorded = fire(lua, "UNIT_FLAGS", "party1")
show(lines)
check("ignores another unit's flags",
      not any("a flight begins" in l for l in lines), str(lines))
lines, recorded = fire(lua, "UNIT_FLAGS", "player")
show(lines)
check("announces on the player's flags",
      any("a flight begins." in l for l in lines), str(lines))

print("\nA /reload in mid-air   (PLAYER_ENTERING_WORLD on a taxi)")
reset(lua)
stand_on_the_ground(lua)
lua.globals().ON_TAXI = True
lines, recorded = fire(lua, "PLAYER_ENTERING_WORLD")
show(lines)
check("notices the flight it is already in",
      any("a flight begins." in l for l in lines), str(lines))

print("\nA cinematic: control lost, nobody on a taxi")
reset(lua)
lua.globals().ON_TAXI = False
lines, recorded = fire(lua, "PLAYER_CONTROL_LOST")
show(lines)
check("stays quiet when it is not a flight",
      not any("a flight begins" in l for l in lines), str(lines))
advance(lua, 25.0)
check("keeps quiet for as long as the watch lasts",
      not any("a flight begins" in l for l in chat(lua)), str(chat(lua)))
check("and then stops asking", pending_timers(lua) == 0, str(pending_timers(lua)))

print("\nA client that does fire PLAYER_CONTROL_LOST for a taxi")
reset(lua)
lua.globals().ON_TAXI = True
lines, recorded = fire(lua, "PLAYER_CONTROL_LOST")
show(lines)
check("announces the flight", any("a flight begins." in l for l in lines), str(lines))

print("\n/fn trace   (what a flight looks like when it does not announce itself)")
lines, recorded = run(lua, "trace")
show(lines)
check("says the watch is on", any("flight trace on" in l for l in lines), str(lines))
lua.globals().ON_TAXI = False
lua.globals().TakeTaxiNode(1)
lines = chat(lua)
show(lines)
check("prints the click and the taxi state it found",
      any("[watch]" in l and "off the taxi" in l for l in lines), str(lines))
check("and the destination the click named",
      any("Stormwind City" in l for l in lines), str(lines))

print("\nA client that refuses the taxi hook")
refusing = build(clips_exist=True, locale="frFR", hook_refused=True)
reset(refusing)
refusing.globals().FireEvent("PLAYER_LOGIN")
lines = chat(refusing)
show(lines)
check("still logs in and says so", any("loaded (classic narrator)" in l for l in lines), str(lines))
lines, recorded = run(refusing, "diag")
check("admits the hook is not installed", any("taxi hook no" in l for l in lines), str(lines))
reset(refusing)
refusing.globals().ON_TAXI = True
refusing.globals().FireEvent("TAXIMAP_CLOSED")
lines = chat(refusing)
show(lines)
check("announces the flight anyway, from the taxi state",
      any("a flight begins" in l for l in lines), str(lines))

print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
for label in FAIL:
    print("  failed: " + label)
sys.exit(1 if FAIL else 0)


-- Flight Narrator -- narrator (Text to Speech) smoke test.
--
-- Target client: WoW Classic. The speech entry point changed shape in the
-- Modern 12.0.0 patch, and the Classic clients inherit that change with the UI
-- they are built from:
--     legacy: C_VoiceChat.SpeakText(voiceID, text, destination, rate, volume)
--     modern: C_VoiceChat.SpeakText(voiceID, text, rate, volume, overlap)
-- Classic Era 1.15.9 (interface 11509) is built from the Modern 12.0.0 UI, so
-- it takes the *modern* form. That is not a guess: the client's own
-- Blizzard_ChatFrame/Shared/TextToSpeechFrame.lua calls
--     C_VoiceChat.SpeakText(voice.voiceID, text,
--         C_TTSSettings.GetSpeechRate(), C_TTSSettings.GetSpeechVolume(),
--         allowOverlappedSpeech)
-- and sending it the legacy form makes it read our rate as the volume, so it
-- synthesises silence. The client writes every utterance it generates to
-- Speech\VoiceSpeak_Utterance_<voice>_<volume>_<rate>_*.wav, which is how the
-- wrong form was caught: the legacy call produced a file filed under volume 0
-- containing nothing but zero samples.
--
-- So: use the client's own TextToSpeech_Speak helper when it is loaded (it
-- always matches that client's signature), otherwise pick the form from the
-- interface version, and if the client reports playback failure, retry once
-- with the next form and report in chat exactly what happened.
--
-- Voices come from the operating system, not from the game, so an addon cannot
-- ship one: it can only pick between the voices the client already sees. /fn
-- voices lists them, and /fn voice <number> selects one through
-- C_TTSSettings.SetVoiceOption, the same call the client's own voice dropdown
-- makes, so the two can never disagree about which voice is selected.
--
-- Flight detection is back, and deliberately narrow: a flight is announced when
-- it starts, from the taxi click (which names the destination) and from losing
-- control while on a taxi (which catches flights that start any other way). See
-- the flight block further down. The library has no destination lines yet, so
-- every flight speaks the one demo line there is.
--
-- The pace is a property of the voice, and the voice is the shipped clip, so it
-- is set when the clips are rendered (tools\Render-VoiceClips.ps1 -Rate, -15% by
-- default) rather than at play time. The client's own Text to Speech, which
-- speaks only for keys with no clip, has its own rate setting that this addon
-- reads and never writes.

local TEST_TEXT = "Flight Narrator test. If you can hear this, the narrator works."

local PREFIX = "|cff33ff99Flight Narrator:|r "

-- The interface number at which a client switched to the signature without
-- `destination`. Era 1.15.9 is the first Classic build built from the Modern
-- 12.0.0 UI; retail crossed over at 120000.
local MODERN_SIGNATURE_INTERFACE = 11509

local NO_VOICE_MESSAGE = "no Text to Speech voice available. Turn on Options > Accessibility > Text to Speech"
	.. " (the switch is account-wide; voice, rate and volume are per character), then /reload."

local function Print(message)
	DEFAULT_CHAT_FRAME:AddMessage(PREFIX .. message)
end

local function GetInterfaceVersion()
	local interfaceVersion = select(4, GetBuildInfo())
	if type(interfaceVersion) == "number" then
		return interfaceVersion
	end
	return tonumber(interfaceVersion) or 0
end

-- Interface 11509 (Era 1.15.9) is the oldest client known to ship the modern
-- form; every higher number does too.
local function UsesModernSignature()
	return GetInterfaceVersion() >= MODERN_SIGNATURE_INTERFACE
end

-- How the addon is about to speak, named so that chat says exactly which call
-- was made.
local function DescribeCall(method)
	if method == "helper" then
		return "the client's own helper: TextToSpeech_Speak(text, voice)"
	elseif method == "legacy" then
		return "legacy: SpeakText(voiceID, text, destination, rate, volume)"
	end
	return "modern: SpeakText(voiceID, text, rate, volume)"
end

-- The client's own voice table for the current character's settings.
-- TextToSpeech_Speak wants that table, not a bare ID, and Blizzard's own code
-- resolves a "default" setting to the first installed voice for us. Returns nil
-- when the helper is not loaded (it lives in Blizzard_ChatFrame, which is
-- load-on-demand).
local function GetSelectedVoice()
	if not TextToSpeech_GetSelectedVoice then
		return nil
	end
	local voiceType = Enum and Enum.TtsVoiceType and Enum.TtsVoiceType.Standard
	local ok, voice = pcall(TextToSpeech_GetSelectedVoice, voiceType)
	if ok and type(voice) == "table" and type(voice.voiceID) == "number" then
		return voice
	end
	return nil
end

-- Voice IDs have to come from the client. 0 is not a usable voice, which is one
-- of the reasons the original build stayed silent.
local function ResolveVoiceID()
	if C_TTSSettings and C_TTSSettings.GetVoiceOptionID and Enum and Enum.TtsVoiceType then
		local ok, voiceID = pcall(C_TTSSettings.GetVoiceOptionID, Enum.TtsVoiceType.Standard)
		if ok and type(voiceID) == "number" and voiceID > 0 then
			return voiceID
		end
	end

	if C_VoiceChat and C_VoiceChat.GetTtsVoices then
		local ok, voices = pcall(C_VoiceChat.GetTtsVoices)
		if ok and type(voices) == "table" then
			for _, voice in ipairs(voices) do
				if type(voice) == "table" and type(voice.voiceID) == "number" and voice.voiceID > 0 then
					return voice.voiceID
				end
			end
		end
	end

	return nil
end

local function GetSpeechRate()
	if C_TTSSettings and C_TTSSettings.GetSpeechRate then
		local ok, rate = pcall(C_TTSSettings.GetSpeechRate)
		if ok and type(rate) == "number" then
			return rate
		end
	end
	return 0 -- 0 is the normal speaking speed
end

local function GetSpeechVolume()
	if C_TTSSettings and C_TTSSettings.GetSpeechVolume then
		local ok, volume = pcall(C_TTSSettings.GetSpeechVolume)
		if ok and type(volume) == "number" and volume > 0 then
			return volume
		end
	end
	return 100 -- 0 is silent, which is the second reason the original build stayed silent
end

-- Forward declaration: SelectVoice() speaks a sample, and Speak() is defined
-- further down with the speech calls. Without this, the name inside SelectVoice
-- would resolve to a global and the call would be nil.
local Speak

-- Voices. The client's own Options panel offers exactly two slots per system:
-- the standard voice, which chat and this addon speak with, and an alternate
-- voice, which the client itself uses for system messages when the matching
-- checkbox is ticked. Both slots are filled from the same list, and that list
-- is the operating system's installed Text to Speech voices. No addon can add
-- to it: an addon is Lua, and voices are installed by the operating system.
local VOICE_SLOT_STANDARD = "standard"
local VOICE_SLOT_ALTERNATE = "alternate"

-- The enum member when this client has one, its documented value otherwise
-- (0 = Standard, 1 = Alternate).
local function GetVoiceType(slot)
	if Enum and Enum.TtsVoiceType then
		if slot == VOICE_SLOT_ALTERNATE and Enum.TtsVoiceType.Alternate then
			return Enum.TtsVoiceType.Alternate
		end
		if Enum.TtsVoiceType.Standard then
			return Enum.TtsVoiceType.Standard
		end
	end
	return slot == VOICE_SLOT_ALTERNATE and 1 or 0
end

local function GetInstalledVoices()
	if not (C_VoiceChat and C_VoiceChat.GetTtsVoices) then
		return nil
	end
	local ok, voices = pcall(C_VoiceChat.GetTtsVoices)
	if ok and type(voices) == "table" then
		return voices
	end
	return nil
end

local function GetSelectedVoiceID(slot)
	if C_TTSSettings and C_TTSSettings.GetVoiceOptionID then
		local ok, voiceID = pcall(C_TTSSettings.GetVoiceOptionID, GetVoiceType(slot))
		if ok and type(voiceID) == "number" then
			return voiceID
		end
	end
	return nil
end

local function DescribeVoice(slot)
	local voiceID = GetSelectedVoiceID(slot)
	local voices = GetInstalledVoices()
	if voices then
		for _, voice in ipairs(voices) do
			if type(voice) == "table" and voice.voiceID == voiceID then
				return tostring(voice.name) .. " (id " .. tostring(voiceID) .. ")"
			end
		end
	end
	return "nothing selected"
end

local function DescribeFlag(value)
	if value == nil then
		return "unknown on this client"
	end
	if value then
		return "yes"
	end
	return "no"
end

local function GetAlternateSystemVoiceFlag()
	local setting = Enum and Enum.TtsBoolSetting and Enum.TtsBoolSetting.AlternateSystemVoice
	if setting and C_TTSSettings and C_TTSSettings.GetSetting then
		local ok, value = pcall(C_TTSSettings.GetSetting, setting)
		if ok then
			return value and true or false
		end
	end
	return nil
end

local function ListVoices()
	local voices = GetInstalledVoices()
	if not voices then
		Print("this client does not report a voice list, so there is nothing to list here.")
		return
	end

	local standardID = GetSelectedVoiceID(VOICE_SLOT_STANDARD)
	local alternateID = GetSelectedVoiceID(VOICE_SLOT_ALTERNATE)

	Print("voices this client can use (" .. #voices .. "):")
	for index, voice in ipairs(voices) do
		if type(voice) == "table" then
			local mark = "  "
			if voice.voiceID == standardID then
				mark = "* "
			elseif voice.voiceID == alternateID then
				mark = "~ "
			end
			Print("  " .. mark .. index .. ". " .. tostring(voice.name) .. " (id " .. tostring(voice.voiceID) .. ")")
		end
	end
	Print("  * is the voice the narrator speaks with, ~ the alternate system voice")
	Print("  /fn voice <number> switches the narrator to that voice and speaks a sample")
end

-- The one client setting this addon writes, and only when asked: /fn voice.
-- It fills the same slot, from the same list, through the same call that the
-- client's own voice dropdown uses, so the panel and the narrator cannot
-- disagree about which voice is selected.
local function SelectVoice(argument)
	argument = strtrim(argument or "")

	if argument == "" then
		Print("the narrator speaks with: " .. DescribeVoice(VOICE_SLOT_STANDARD))
		Print("  /fn voices lists what this client can use, /fn voice <number> picks one")
		return
	end

	local slot = VOICE_SLOT_STANDARD
	local suffix = VOICE_SLOT_ALTERNATE
	if strlower(argument):sub(-#suffix) == suffix then
		slot = VOICE_SLOT_ALTERNATE
		argument = strtrim(argument:sub(1, #argument - #suffix))
		if argument == "" then
			Print("which voice? /fn voices lists them, and /fn voice <number> " .. suffix .. " fills that slot")
			return
		end
	end

	local voices = GetInstalledVoices()
	if not voices or #voices == 0 then
		Print("this client reports no voices at all, so there is nothing to choose here:")
		Print("  install a voice in the operating system's speech settings first, then /reload.")
		return
	end

	local voice
	local index = tonumber(argument)
	if index then
		voice = voices[index]
		if type(voice) ~= "table" then
			Print("there is no voice number " .. tostring(index) .. ": /fn voices lists them, 1 to " .. #voices .. ".")
			return
		end
	else
		local wanted = strlower(argument)
		for _, candidate in ipairs(voices) do
			if type(candidate) == "table" and type(candidate.name) == "string" and strlower(candidate.name) == wanted then
				voice = candidate
				break
			end
		end
		if not voice then
			Print("no voice on this client is called \"" .. argument .. "\": /fn voices lists them.")
			return
		end
	end

	if not (C_TTSSettings and C_TTSSettings.SetVoiceOption) then
		Print("this client has no C_TTSSettings.SetVoiceOption, so the voice cannot be changed from here:")
		Print("  Options > Accessibility > Text to Speech.")
		return
	end

	local ok, err = pcall(C_TTSSettings.SetVoiceOption, GetVoiceType(slot), voice.voiceID)
	if not ok then
		Print("the client refused that voice: " .. tostring(err))
		return
	end

	Print("voice \"" .. tostring(voice.name) .. "\" is now in the " .. slot .. " slot (id " .. tostring(voice.voiceID) .. ")")
	Print("  saved with your character settings, exactly like the client's own voice dropdown")

	if slot == VOICE_SLOT_STANDARD then
		Speak()
	end
end

-- Which call to try, in order, and what to try next when one is rejected.
local METHOD_ORDER = { "helper", "modern", "legacy" }

-- Reasons that are not errors: that path simply does not exist on this client,
-- so the next one is tried without bothering the player about it.
local FAILURE_CODES = {
	helper = true, -- TextToSpeech_Speak is not loaded on this client
	api = true, -- C_VoiceChat.SpeakText does not exist on this client
	voice = true, -- the client reports no usable voice
}

local pendingAttempt

local function NextMethod(method)
	for index, name in ipairs(METHOD_ORDER) do
		if name == method then
			return METHOD_ORDER[index + 1]
		end
	end
	return nil
end

-- The client's own path, the one its Play Sample button uses: it cannot
-- disagree with the client about argument order, and it applies the
-- character's own voice, rate and volume settings.
local function SpeakWithHelper(text)
	if not TextToSpeech_Speak then
		return false, "helper"
	end
	local voice = GetSelectedVoice()
	if not voice then
		return false, "voice"
	end
	-- neverQueue = true: a flight line should be heard now, not after the client
	-- has finished reading a chat line.
	return pcall(TextToSpeech_Speak, text, voice, true)
end

local function SpeakWithVoiceChat(text, useModernSignature)
	if not (C_VoiceChat and C_VoiceChat.SpeakText) then
		return false, "api"
	end

	local voiceID = ResolveVoiceID()
	if not voiceID then
		return false, "voice"
	end

	local rate, volume = GetSpeechRate(), GetSpeechVolume()
	if useModernSignature then
		-- rate, then volume, no destination: the order the client's own UI uses.
		return pcall(C_VoiceChat.SpeakText, voiceID, text, rate, volume, false)
	end

	local destination = 1 -- Enum.VoiceTtsDestination.LocalPlayback
	if Enum and Enum.VoiceTtsDestination and Enum.VoiceTtsDestination.LocalPlayback then
		destination = Enum.VoiceTtsDestination.LocalPlayback
	end
	return pcall(C_VoiceChat.SpeakText, voiceID, text, destination, rate, volume)
end

local function SpeakThroughClient(text, method)
	if method == "helper" then
		return SpeakWithHelper(text)
	end
	return SpeakWithVoiceChat(text, method ~= "legacy")
end

Speak = function(text, method)
	text = text or TEST_TEXT
	method = method or "helper"
	pendingAttempt = nil

	local ok, reason = SpeakThroughClient(text, method)

	if ok then
		Print("speaking with " .. DescribeCall(method) .. " -> " .. text)
		pendingAttempt = {
			text = text,
			method = method,
			startedAt = GetTime(),
			started = false,
		}
		return true
	end

	if FAILURE_CODES[reason] then
		local nextMethod = NextMethod(method)
		if not nextMethod then
			if reason == "voice" then
				Print(NO_VOICE_MESSAGE)
			else
				Print("this client has no usable speech API, so here is the text instead:")
			end
			Print(text)
			return false
		end
		return Speak(text, nextMethod)
	end

	Print(DescribeCall(method) .. " raised an error: " .. tostring(reason))
	Print(text)
	return false
end

-- Shipped voice clips. If this addon carries rendered narration (see the
-- README), the clip is used in preference to the client's Text to Speech: the
-- same words, in a voice that does not depend on the player's operating system,
-- and with no synthesis at all. A missing clip is never silence: it falls back.
local CLIP_ROOT = "Interface\\AddOns\\FlightNarrator\\voice\\"
local CLIP_EXTENSIONS = { "ogg", "mp3" }
local CLIP_CHANNEL = "Dialog"
local clipState = {}

-- The language the shipped library is written in. The client's own locale is
-- tried first, so a French client hears the French clips; a client in any other
-- language falls through to this rather than to silence, because the narration
-- language is a decision of the addon rather than of the player's client.
-- Render another language into its own folder and point this at it to move.
local NARRATION_LANGUAGE = "frFR"

local function GetClipFolders()
	local folders = {}
	local locale = GetLocale and GetLocale() or nil
	if type(locale) == "string" and locale ~= "" then
		folders[#folders + 1] = locale
	end
	if NARRATION_LANGUAGE ~= "" and NARRATION_LANGUAGE ~= locale then
		folders[#folders + 1] = NARRATION_LANGUAGE
	end
	return folders
end

local function DescribeClipFolders()
	local folders = {}
	for _, folder in ipairs(GetClipFolders()) do
		folders[#folders + 1] = "voice\\" .. folder .. "\\"
	end
	return table.concat(folders, " or ")
end

-- "Interface\AddOns\FlightNarrator\voice\frFR\test.mp3" -> "voice\frFR\test.mp3"
local function ShortClipPath(path)
	return (path:gsub("^Interface\\AddOns\\FlightNarrator\\", ""))
end

-- Looking for a clip and playing it are the same call: PlaySoundFile reports
-- whether it will play, so the first folder and extension that exist are also
-- the ones that sound. The answer is cached, so each key is looked for once per
-- session. Returns the path it played, or false when there is no clip at all.
local function PlayShippedClip(key)
	if type(key) ~= "string" or key == "" then
		return false
	end

	local cached = clipState[key]
	if cached == false then
		return false
	end
	if type(cached) == "string" then
		pcall(PlaySoundFile, cached, CLIP_CHANNEL)
		return cached
	end

	for _, folder in ipairs(GetClipFolders()) do
		for _, extension in ipairs(CLIP_EXTENSIONS) do
			local candidate = CLIP_ROOT .. folder .. "\\" .. key .. "." .. extension
			local ok, willPlay = pcall(PlaySoundFile, candidate, CLIP_CHANNEL)
			if ok and willPlay then
				clipState[key] = candidate
				return candidate
			end
		end
	end

	clipState[key] = false
	return false
end

-- The narrator's single entry point: the shipped clip when there is one, the
-- client's own Text to Speech when there is not.
local function Narrate(key, text)
	local played = PlayShippedClip(key)
	if played then
		Print("playing the shipped clip " .. ShortClipPath(played) .. " (no Text to Speech involved).")
		return true
	end
	return Speak(text or key)
end

local function PlayClipCommand(key)
	key = strtrim(key or "")
	if key == "" then
		Print("usage: /fn clip <key>, for example /fn clip test")
		Print("  clips live in " .. DescribeClipFolders() .. ", as <key>.ogg or <key>.mp3")
		return
	end
	local played = PlayShippedClip(key)
	if played then
		Print("playing the shipped clip " .. ShortClipPath(played) .. ".")
		return
	end
	Print("there is no clip called " .. key .. " in " .. DescribeClipFolders() .. ".")
	Print("  render one with tools\\Render-VoiceClips.ps1, then /reload: the client only sees files that existed when it loaded.")
end

-- Flight detection. The one question worth asking is "is the player on a flight
-- path?", and the client's own answer to it is UnitOnTaxi, which era's interface
-- uses the same way (VehicleLeaveButton, PaperDollFrame, UIParent). Asking for
-- the state instead of waiting for an event is not a preference: era has no
-- event that a taxi lifts off on. PLAYER_CONTROL_LOST looks like one and is not
-- - the era interface never registers it, only the later flavours do - so a
-- flight that waited for it would never be announced. That is how 0.3.2 failed
-- in game, having registered the event successfully and then waited forever.
--
-- So every moment that could mean a flight is starting opens a short watch, and
-- the watch keeps asking the taxi state until it has an answer:
--
--   * TakeTaxiNode, hooked with hooksecurefunc so the vanilla call is left
--     alone, is the click on the flight master's map and the only one of these
--     that can name where the player is going. A click is a question, not an
--     answer - a taxi that is refused costs no flight - so it opens a watch
--     rather than announcing on the spot.
--   * TAXIMAP_CLOSED is the map closing as the taxi is taken. UNIT_FLAGS is
--     there because the taxi state is a unit flag on some clients, and
--     PLAYER_ENTERING_WORLD for the loading screen a long flight crosses (which
--     is also how a /reload mid-flight is noticed). PLAYER_CONTROL_LOST is
--     watched too, for the sake of a client that does fire it, and is never
--     required.
--   * The watch polls for TAKEOFF_WATCH_SECONDS, every TAKEOFF_POLL_SECONDS: a
--     flight turns the flag on within a tick or two of the click, and a refused
--     taxi leaves the player off the taxi and announces nothing.
--
-- The state also separates a flight from a cinematic, a summon or a fear, all of
-- which take control away and must stay silent. Being off the taxi is where the
-- flight ends (PLAYER_CONTROL_GAINED asks the same question), and a route that
-- spans several legs is announced once, at the start, because the taxi never
-- lets go between legs.
--
-- Destination lines are the library's next job. Until they exist every flight
-- speaks the one demo key there is, and chat says where the flight is going, so
-- that the detection can be seen working before the writing catches up.
local FLIGHT_DEMO_KEY = "elwynn"
local TAKEOFF_WATCH_SECONDS = 20
local TAKEOFF_POLL_SECONDS = 0.5

local flightAnnounced = false
local taxiDestination
local taxiHookInstalled = false
local watchUntil = 0
local tracing = false

-- Events that can mean a flight is starting, and the event that ends one, with
-- the client's answer to the registration kept alongside. PLAYER_CONTROL_LOST is
-- in the list for the sake of any client that fires it, and a client that
-- refuses the registration says so in /fn diag instead of the absence being
-- silent, which is what 0.3.2 got wrong.
local FLIGHT_START_EVENTS = { "TAXIMAP_CLOSED", "UNIT_FLAGS", "PLAYER_ENTERING_WORLD", "PLAYER_CONTROL_LOST" }
local FLIGHT_END_EVENT = "PLAYER_CONTROL_GAINED"
local flightSignals = {}

-- A line for the client's Text to Speech to read when the key has no clip: the
-- fallback, not the narration. Written in the library's language, like every
-- other line in it.
local function FlightLine(destination)
	if destination then
		return "Le voyage commence, destination " .. destination .. "."
	end
	return "Le voyage commence."
end

local function AnnounceFlight(destination)
	if flightAnnounced then
		return false
	end
	flightAnnounced = true
	if destination then
		Print("a flight begins, to " .. destination .. ".")
	else
		Print("a flight begins.")
	end
	Narrate(FLIGHT_DEMO_KEY, FlightLine(destination))
	return true
end

-- "Stormwind City" for the slot TakeTaxiNode was called with, which is the same
-- index the client's own taxi buttons use. A client without TaxiNodeName still
-- gets its flights announced, just without a name.
local function NameTaxiNode(slot)
	if type(slot) ~= "number" or not TaxiNodeName then
		return nil
	end
	local ok, name = pcall(TaxiNodeName, slot)
	if ok and type(name) == "string" and name ~= "" then
		return name
	end
	return nil
end

-- Whether the player is on a flight path right now. The call is vanilla, so it
-- is asked without ceremony; a client that does not answer (none known) falls
-- back to "a taxi was just clicked", which is the best evidence there is then.
local function OnFlightNow()
	if UnitOnTaxi then
		local ok, onTaxi = pcall(UnitOnTaxi, "player")
		if ok then
			return onTaxi and true or false
		end
	end
	return taxiDestination ~= nil
end

-- /fn trace prints the flight watch as it happens, which is how a flight that
-- does not announce itself gets diagnosed in game.
local function Trace(what)
	if not tracing then
		return
	end
	Print("  [watch] " .. what .. ": " .. (OnFlightNow() and "on a taxi" or "off the taxi")
		.. ", destination " .. (taxiDestination or "none")
		.. ", announced " .. (flightAnnounced and "yes" or "no"))
end

local function HasPolling()
	return type(C_Timer) == "table" and type(C_Timer.After) == "function"
end

-- The single point that decides whether a flight is happening, and the only
-- caller of AnnounceFlight for a real flight. Returns true when the player is on
-- a taxi, whether or not this flight was announced before.
local function CheckFlight(why)
	if OnFlightNow() then
		if not flightAnnounced then
			Trace(why .. " found the player on a taxi")
			AnnounceFlight(taxiDestination)
		end
		return true
	end
	if flightAnnounced then
		-- Off the taxi: the flight that was announced is over, and the next one
		-- is announced when it starts.
		Trace(why .. " found the flight over")
		flightAnnounced = false
		taxiDestination = nil
	end
	return false
end

-- Keeps asking while the watch is open. A poll that finds the player still on
-- the ground costs nothing: only a flight that ended clears the destination.
local function WatchForTakeoff(why)
	if CheckFlight(why) then
		return true
	end
	if flightAnnounced or GetTime() >= watchUntil then
		if why == "poll" then
			-- The watch is over. A destination that never turned into a flight
			-- goes with it: a later taxi that this addon did not see clicked must
			-- not be announced under a name that belongs to another one.
			Trace("the watch closed with no flight")
			taxiDestination = nil
		end
		return false
	end
	if not HasPolling() then
		-- No timers on this client: the next signal brings the next look, and a
		-- click with no signal behind it announces directly.
		return false
	end
	return pcall(C_Timer.After, TAKEOFF_POLL_SECONDS, function()
		WatchForTakeoff("poll")
	end)
end

-- A moment that may mean a flight is starting. None of these is trusted on its
-- own: each one opens the watch, and the taxi state is what answers - in either
-- direction, because a signal that finds the player back on the ground is how a
-- flight that ended is noticed on a client that fires nothing at the end of one.
local function NoteFlightSignal(why)
	Trace(why .. " arrived")
	watchUntil = GetTime() + TAKEOFF_WATCH_SECONDS
	WatchForTakeoff(why)
end

local function AnyFlightSignalWatched()
	for _, answered in pairs(flightSignals) do
		if answered then
			return true
		end
	end
	return false
end

-- The click on the flight master's map: the only signal that can name where the
-- player is going, and a question rather than an answer, because a taxi can be
-- refused.
local function OnTaxiClicked(slot)
	flightAnnounced = false
	taxiDestination = NameTaxiNode(slot)
	Trace("the taxi map was clicked")
	watchUntil = GetTime() + TAKEOFF_WATCH_SECONDS
	if not HasPolling() and not AnyFlightSignalWatched() then
		-- Nothing on this client can answer later, so the click is all there is
		-- to go on.
		AnnounceFlight(taxiDestination)
		return
	end
	WatchForTakeoff("taxi click")
end

-- Hooked rather than replaced: hooksecurefunc leaves TakeTaxiNode itself alone.
-- The pcall is not decoration. A client can refuse a hook, and without it the
-- error would escape from the login handler and the flag would claim a hook that
-- is not there. What is lost when the hook is refused is the click and the
-- destination's name, never the announcement: the taxi state is asked for
-- anyway, and the other signals open the same watch.
local function InstallTaxiHook()
	if taxiHookInstalled or not hooksecurefunc or type(TakeTaxiNode) ~= "function" then
		return false
	end
	taxiHookInstalled = pcall(hooksecurefunc, "TakeTaxiNode", OnTaxiClicked) and true or false
	return taxiHookInstalled
end

-- A flight cannot be staged on demand in game, so this is the trigger without
-- the taxi: the same call the event makes, so what it prints is what a real
-- flight prints.
local function PretendFlight(destination)
	destination = strtrim(destination or "")
	if destination == "" then
		destination = nil
	end
	local named = ""
	if destination then
		named = " to " .. destination
	end
	Print("pretending a flight starts" .. named .. ":")
	flightAnnounced = false
	AnnounceFlight(destination)
end

local watchedEvents = {}
local watchedCount = 0

local eventFrame = CreateFrame("Frame")

local function WatchEvent(event)
	-- Not every client knows every TTS event, and registering an unknown event
	-- raises an error, so it is attempted defensively.
	if pcall(eventFrame.RegisterEvent, eventFrame, event) then
		watchedCount = watchedCount + 1
		watchedEvents[watchedCount] = event
		return true
	end
	return false
end

local function StatusName(status)
	if Enum and Enum.VoiceTtsStatusCode then
		for name, value in pairs(Enum.VoiceTtsStatusCode) do
			if value == status then
				return name
			end
		end
	end
	return tostring(status)
end

local function IsCurrentAttempt()
	return pendingAttempt and (GetTime() - pendingAttempt.startedAt) < 5
end

WatchEvent("PLAYER_LOGIN")
WatchEvent("VOICE_CHAT_TTS_PLAYBACK_STARTED")
WatchEvent("VOICE_CHAT_TTS_PLAYBACK_FINISHED")
WatchEvent("VOICE_CHAT_TTS_PLAYBACK_FAILED")
for _, signal in ipairs(FLIGHT_START_EVENTS) do
	flightSignals[signal] = WatchEvent(signal)
end
flightSignals[FLIGHT_END_EVENT] = WatchEvent(FLIGHT_END_EVENT)

eventFrame:SetScript("OnEvent", function(_, event, ...)
	if event == "PLAYER_LOGIN" then
		InstallTaxiHook()
		Print("loaded (classic narrator). /fn to hear it, /fn flight for the flight trigger, /fn trace to watch for the next one, /fn voices to pick a voice, /fn diag for details.")
		Print("flights are narrated from now on: /fn flight tries the trigger without leaving the ground.")
		return
	end

	if flightSignals[event] and event ~= FLIGHT_END_EVENT then
		-- A flight may be starting: the taxi map closing as the taxi is taken, a
		-- unit flag, the loading screen a long flight crosses, or a loss of
		-- control on a client that announces one. The taxi state is what
		-- answers; UNIT_FLAGS is filtered to the player because it fires for
		-- every unit.
		local unit = ...
		if event ~= "UNIT_FLAGS" or unit == "player" then
			NoteFlightSignal(event)
		end
		return
	end

	if event == FLIGHT_END_EVENT then
		-- Control is back. Off the taxi, the flight is over and the next one can
		-- be announced; a flight that is still going is not touched.
		CheckFlight(event)
		return
	end

	if event == "VOICE_CHAT_TTS_PLAYBACK_STARTED" then
		if IsCurrentAttempt() then
			pendingAttempt.started = true
			Print("the client started reading it aloud.")
		end
		return
	end

	if event == "VOICE_CHAT_TTS_PLAYBACK_FINISHED" then
		if pendingAttempt and pendingAttempt.started then
			pendingAttempt = nil
		end
		return
	end

	if event == "VOICE_CHAT_TTS_PLAYBACK_FAILED" and IsCurrentAttempt() then
		local status = select(2, ...)
		local attempt = pendingAttempt
		local nextMethod = NextMethod(attempt.method)
		if nextMethod then
			Print("playback failed (" .. StatusName(status) .. "), retrying with " .. DescribeCall(nextMethod) .. ":")
			Speak(attempt.text, nextMethod)
			return
		end
		Print("playback failed (" .. StatusName(status) .. "). Showing the text instead:")
		Print(attempt.text)
		pendingAttempt = nil
	end
end)

local function FormatFlag(value)
	if value then
		return "yes"
	end
	return "no"
end

-- The client's own rate range (TEXTTOSPEECH_RATE_MIN/MAX, 0 being its normal
-- speed), when it exports one: the scale the fallback voice answers to.
local function DescribeRateRange()
	if type(TEXTTOSPEECH_RATE_MIN) == "number" and type(TEXTTOSPEECH_RATE_MAX) == "number" then
		return tostring(TEXTTOSPEECH_RATE_MIN) .. " to " .. tostring(TEXTTOSPEECH_RATE_MAX)
	end
	return "its own range"
end

-- The flight events this client answered, for /fn diag. A refused registration is
-- worth showing rather than hiding: 0.3.2 rested the whole trigger on
-- PLAYER_CONTROL_LOST, and a client that never fires it is exactly how a flight
-- went unannounced.
local function DescribeFlightSignals()
	local parts = {}
	for _, name in ipairs(FLIGHT_START_EVENTS) do
		parts[#parts + 1] = name .. " " .. FormatFlag(flightSignals[name])
	end
	parts[#parts + 1] = FLIGHT_END_EVENT .. " " .. FormatFlag(flightSignals[FLIGHT_END_EVENT])
	return table.concat(parts, ", ")
end

local function PrintDiagnostics()
	local version, build, _, interfaceVersion = GetBuildInfo()
	local cvarValue = GetCVar and GetCVar("textToSpeech")

	Print("diagnostics")
	Print("  client: " .. tostring(version) .. ", build " .. tostring(build) .. ", interface " .. tostring(interfaceVersion))
	Print("  the .toc must declare that same interface number or the addon counts as out of date")
	Print("  first choice: " .. DescribeCall("helper") .. " (" .. FormatFlag(TextToSpeech_Speak) .. ")")
	Print("  C_VoiceChat.SpeakText: " .. FormatFlag(C_VoiceChat and C_VoiceChat.SpeakText)
		.. " (fallback form: " .. DescribeCall(UsesModernSignature() and "modern" or "legacy") .. ")")
	Print("  C_VoiceChat.GetTtsVoices: " .. FormatFlag(C_VoiceChat and C_VoiceChat.GetTtsVoices))
	Print("  C_TTSSettings.GetVoiceOptionID: " .. FormatFlag(C_TTSSettings and C_TTSSettings.GetVoiceOptionID))
	Print("  TextToSpeech_GetSelectedVoice helper: " .. FormatFlag(TextToSpeech_GetSelectedVoice))
	Print("  Text to Speech setting (textToSpeech CVar): " .. tostring(cvarValue))
	if cvarValue == "0" then
		Print("  ^ that setting is off. It is account-wide: turn on")
		Print("    Options > Accessibility > Text to Speech, then /reload.")
	end

	Print("  selected voice ID: " .. tostring(ResolveVoiceID()))
	Print("  narrator voice (standard slot): " .. DescribeVoice(VOICE_SLOT_STANDARD))
	Print("  alternate slot: " .. DescribeVoice(VOICE_SLOT_ALTERNATE)
		.. " (used by the client for system messages: " .. DescribeFlag(GetAlternateSystemVoiceFlag()) .. ")")
	Print("  rate " .. tostring(GetSpeechRate()) .. " of " .. DescribeRateRange() .. ", volume " .. tostring(GetSpeechVolume()))
	Print("  ^ the character's own Text to Speech settings, read and never written:")
	Print("    /tts rate <n> is the client's own way to slow the fallback voice; shipped clips carry their own pace")
	Print("  flight detection: the taxi state itself (UnitOnTaxi " .. FormatFlag(UnitOnTaxi) .. "), asked on the taxi click")
	Print("    (TakeTaxiNode hooked: " .. FormatFlag(taxiHookInstalled) .. ") and on any of these events:")
	Print("    " .. DescribeFlightSignals())
	Print("    a watch then asks the taxi state every " .. tostring(TAKEOFF_POLL_SECONDS) .. "s for "
		.. tostring(TAKEOFF_WATCH_SECONDS) .. "s, because no event says that a taxi lifted off")
	Print("  taxi hook " .. FormatFlag(taxiHookInstalled) .. " (TakeTaxiNode is a function here: "
		.. FormatFlag(type(TakeTaxiNode) == "function") .. ")")
	Print("  on a flight right now: " .. FormatFlag(OnFlightNow()))
	Print("  /fn trace " .. (tracing and "is on: it prints the flight watch as it happens" or "prints the flight watch as a flight happens"))
	Print("  every flight speaks the demo key '" .. FLIGHT_DEMO_KEY .. "' until the library names destinations")
	Print("  /fn voices lists every voice this client can use")
	Print("  locale: " .. tostring(GetLocale and GetLocale() or "unknown") .. ", clips are read from " .. DescribeClipFolders())

	local voices = GetInstalledVoices()
	if voices then
		Print("  installed voices: " .. #voices .. " (/fn voices lists them)")
	else
		Print("  installed voices: this client does not report a list")
	end

	local watchedText = "none available on this client"
	if watchedCount > 0 then
		watchedText = table.concat(watchedEvents, ", ")
	end
	Print("  watching: " .. watchedText)
end

SLASH_FLIGHTNARRATOR1 = "/flightnarrator"
SLASH_FLIGHTNARRATOR2 = "/fn"
SLASH_FLIGHTNARRATOR3 = "/flyn"

SlashCmdList.FLIGHTNARRATOR = function(message)
	message = strtrim(message or "")

	if message == "" or strlower(message) == "test" then
		Narrate("test", TEST_TEXT)
		return
	end

	local command = strlower(message)

	if command == "diag" then
		PrintDiagnostics()
		return
	end

	if command == "trace" then
		tracing = not tracing
		Print("flight trace " .. (tracing and "on" or "off")
			.. (tracing and ": take a flight and every [watch] line says what the client did." or "."))
		return
	end

	if command == "voices" then
		ListVoices()
		return
	end

	if command == "clip" or command:sub(1, 5) == "clip " then
		PlayClipCommand(strtrim(message:sub(5)))
		return
	end

	if command == "flight" or command:sub(1, 7) == "flight " then
		PretendFlight(message:sub(8))
		return
	end

	if command == "voice" or command:sub(1, 6) == "voice " then
		SelectVoice(strtrim(message:sub(6)))
		return
	end

	Speak(message)
end

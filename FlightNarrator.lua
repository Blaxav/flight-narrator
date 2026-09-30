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
-- Flight detection is deliberately not in this build: the goal right now is to
-- prove that the narrator can speak at all. Use /fn to test it.

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

local function Speak(text, method)
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

eventFrame:SetScript("OnEvent", function(_, event, ...)
	if event == "PLAYER_LOGIN" then
		Print("loaded (classic narrator test). /fn to hear it, /fn diag for details.")
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
	Print("  rate " .. tostring(GetSpeechRate()) .. ", volume " .. tostring(GetSpeechVolume()))

	if C_VoiceChat and C_VoiceChat.GetTtsVoices then
		local ok, voices = pcall(C_VoiceChat.GetTtsVoices)
		if ok and type(voices) == "table" then
			local sample = {}
			for index, voice in ipairs(voices) do
				if index > 3 then
					break
				end
				if type(voice) == "table" then
					sample[#sample + 1] = tostring(voice.voiceID) .. " = " .. tostring(voice.name)
				end
			end
			local sampleText = "none listed"
			if #sample > 0 then
				sampleText = table.concat(sample, ", ")
			end
			Print("  installed voices (" .. #voices .. "): " .. sampleText)
		else
			Print("  installed voices: could not be read")
		end
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
		Speak(TEST_TEXT)
		return
	end

	if strlower(message) == "diag" then
		PrintDiagnostics()
		return
	end

	Speak(message)
end

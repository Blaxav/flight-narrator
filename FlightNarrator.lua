local TAXI_BOARD_WINDOW_SECONDS = 1
local DEFAULT_FLIGHT_TEXT = "You are now in flight. Enjoy the view."
local CHAT_COMMAND = "flightnarrator"

local taxiNodeTakenAt = 0
local isOnFlightPath = false

local function GetSavedText()
	if FlightNarratorDB and type(FlightNarratorDB.flightText) == "string" and FlightNarratorDB.flightText ~= "" then
		return FlightNarratorDB.flightText
	end
	return DEFAULT_FLIGHT_TEXT
end

local function Speak(text)
	if TextToSpeech_Speak then
		local voice
		if TextToSpeech_GetSelectedVoice then
			voice = TextToSpeech_GetSelectedVoice("standard")
		end
		TextToSpeech_Speak(text, voice)
		return
	end

	if C_VoiceChat and C_VoiceChat.SpeakText then
		local destination = 1
		if Enum and Enum.VoiceTtsDestination and Enum.VoiceTtsDestination.LocalPlayback then
			destination = Enum.VoiceTtsDestination.LocalPlayback
		end
		C_VoiceChat.SpeakText(0, text, destination, 0, 100)
		return
	end

	DEFAULT_CHAT_FRAME:AddMessage("|cff33ff99Flight Narrator:|r enable Text to Speech in Accessibility, then /reload.")
	DEFAULT_CHAT_FRAME:AddMessage("|cff33ff99Flight Narrator:|r " .. text)
end

local function OnFlightStarted()
	isOnFlightPath = true
	Speak(GetSavedText())
end

local function OnFlightEnded()
	isOnFlightPath = false
end

hooksecurefunc("TakeTaxiNode", function()
	taxiNodeTakenAt = GetTime()
end)

local eventFrame = CreateFrame("Frame")
eventFrame:RegisterEvent("PLAYER_LOGIN")
eventFrame:RegisterEvent("PLAYER_CONTROL_LOST")
eventFrame:RegisterEvent("PLAYER_CONTROL_GAINED")

eventFrame:SetScript("OnEvent", function(_, event)
	if event == "PLAYER_LOGIN" then
		if type(FlightNarratorDB) ~= "table" then
			FlightNarratorDB = {}
		end
		if type(FlightNarratorDB.flightText) ~= "string" or FlightNarratorDB.flightText == "" then
			FlightNarratorDB.flightText = DEFAULT_FLIGHT_TEXT
		end
		return
	end

	if event == "PLAYER_CONTROL_LOST" then
		if not isOnFlightPath and (GetTime() - taxiNodeTakenAt) < TAXI_BOARD_WINDOW_SECONDS then
			OnFlightStarted()
		end
		return
	end

	if event == "PLAYER_CONTROL_GAINED" and isOnFlightPath then
		OnFlightEnded()
	end
end)

SLASH_FLIGHTNARRATOR1 = "/" .. CHAT_COMMAND
SLASH_FLIGHTNARRATOR2 = "/fn"

SlashCmdList.FLIGHTNARRATOR = function(message)
	message = strtrim(message or "")
	if message == "" then
		DEFAULT_CHAT_FRAME:AddMessage("|cff33ff99Flight Narrator:|r current line: " .. GetSavedText())
		DEFAULT_CHAT_FRAME:AddMessage("|cff33ff99Flight Narrator:|r /fn <text> to change it. /fn test to hear it.")
		return
	end
	if strlower(message) == "test" then
		Speak(GetSavedText())
		return
	end
	FlightNarratorDB.flightText = message
	DEFAULT_CHAT_FRAME:AddMessage("|cff33ff99Flight Narrator:|r saved. /fn test to hear it.")
end

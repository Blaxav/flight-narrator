-- Flight Narrator
--
-- WoW Classic addon: when a flight (taxi) launches, plays the shipped Ratchet
-- narration clip. One clip, one trigger, nothing else.
--
-- The clip travels with the addon as an ordinary sound file and is played with
-- PlaySoundFile, the only way a voice can ship inside a WoW addon. The file must
-- exist when the client loads, so after rendering a clip: /reload.
--
-- Flight detection asks the client's own UnitOnTaxi instead of waiting for an
-- event, because Classic Era has no event that fires when a taxi lifts off
-- (PLAYER_CONTROL_LOST looks like one, but Era never registers it). So every
-- moment that could mean a flight is starting -- the flight-master click, the
-- taxi map closing, a loading screen -- opens a short watch that polls UnitOnTaxi
-- until it answers. The clip is played once per flight, at the start.

local CLIP_PATH = "Interface\\AddOns\\FlightNarrator\\voice\\frFR\\ratchet.mp3"
local CLIP_CHANNEL = "Dialog"

local TAKEOFF_WATCH_SECONDS = 20
local TAKEOFF_POLL_SECONDS = 0.5

local flightAnnounced = false
local watchUntil = 0

local function Print(message)
	DEFAULT_CHAT_FRAME:AddMessage("|cff33ff99Flight Narrator:|r " .. message)
end

local function OnFlightNow()
	if UnitOnTaxi then
		local ok, onTaxi = pcall(UnitOnTaxi, "player")
		if ok then
			return onTaxi and true or false
		end
	end
	return false
end

local function PlayRatchet()
	local ok, willPlay = pcall(PlaySoundFile, CLIP_PATH, CLIP_CHANNEL)
	if ok and willPlay then
		Print("playing voice\\frFR\\ratchet.mp3")
	else
		Print("could not play " .. CLIP_PATH)
	end
end

-- The single point that decides whether a flight is happening. Announces once,
-- at the start, and re-arms when the flight ends.
local function CheckFlight()
	if OnFlightNow() then
		if not flightAnnounced then
			flightAnnounced = true
			PlayRatchet()
		end
	elseif flightAnnounced then
		flightAnnounced = false
	end
end

-- Keeps asking while the watch is open, until the taxi state answers either way
-- or the watch runs out.
local function WatchForTakeoff()
	if CheckFlight() then
		return
	end
	if flightAnnounced or GetTime() >= watchUntil then
		return
	end
	if C_Timer and C_Timer.After then
		C_Timer.After(TAKEOFF_POLL_SECONDS, WatchForTakeoff)
	end
end

local function NoteFlightSignal()
	watchUntil = GetTime() + TAKEOFF_WATCH_SECONDS
	WatchForTakeoff()
end

-- The click on the flight master's map opens the watch, but does not announce on
-- the spot: a taxi that is refused costs no flight.
local function OnTaxiClicked()
	flightAnnounced = false
	watchUntil = GetTime() + TAKEOFF_WATCH_SECONDS
	WatchForTakeoff()
end

local eventFrame = CreateFrame("Frame")
eventFrame:RegisterEvent("PLAYER_LOGIN")
eventFrame:RegisterEvent("TAXIMAP_CLOSED")
eventFrame:RegisterEvent("UNIT_FLAGS")
eventFrame:RegisterEvent("PLAYER_ENTERING_WORLD")
eventFrame:RegisterEvent("PLAYER_CONTROL_LOST")
eventFrame:RegisterEvent("PLAYER_CONTROL_GAINED")

eventFrame:SetScript("OnEvent", function(_, event, unit)
	if event == "PLAYER_LOGIN" then
		if hooksecurefunc and type(TakeTaxiNode) == "function" then
			pcall(hooksecurefunc, "TakeTaxiNode", OnTaxiClicked)
		end
		Print("loaded. The Ratchet line plays when a flight launches.")
		return
	end

	if event == "PLAYER_CONTROL_GAINED" then
		CheckFlight()
		return
	end

	if event == "UNIT_FLAGS" and unit ~= "player" then
		return
	end

	-- A flight may be starting: the taxi map closing, a unit flag, a loading
	-- screen, or a loss of control. The taxi state is what answers.
	NoteFlightSignal()
end)

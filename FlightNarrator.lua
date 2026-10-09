-- Flight Narrator
--
-- WoW Classic addon: when a flight (taxi) launches, narrates the journey by
-- playing the zone clips that match the route. The route duration is cut into
-- ~75 s slots; each slot draws one random clip from the zones overflown during
-- that slot, and every clip starts at the beginning of its own slot.
--
-- The clips travel with the addon as ordinary sound files and are played with
-- PlaySoundFile, the only way a voice can ship inside a WoW addon. Files must
-- exist when the client loads, so after rendering clips: /reload.
--
-- WoW cannot list files or read the .txt timeline at runtime, so both the clip
-- library and the per-route zone timelines ship as data (TravelData.lua),
-- regenerated offline by tools/generate_travel_data.py. A new clip or route is
-- just one more entry in that file.
--
-- Flight detection asks the client's own UnitOnTaxi instead of waiting for an
-- event, because Classic Era has no event that fires when a taxi lifts off
-- (PLAYER_CONTROL_LOST looks like one, but Era never registers it). So every
-- moment that could mean a flight is starting -- the flight-master click, the
-- taxi map closing, a loading screen -- opens a short watch that polls UnitOnTaxi
-- until it answers.

local DATA = FlightNarratorData or { Audio = {}, Travels = {} }
local CLIP_BASE = "Interface\\AddOns\\FlightNarrator\\"
local CLIP_CHANNEL = "Dialog"

-- Set to true (or type /fn in game) to trace route detection in chat.
local DEBUG = true

-- Nominal length of one narration clip. The route duration is cut into
-- floor(duration / CLIP_SECONDS) equal slots (at least one), so a 224 s flight
-- becomes two 112 s slots, each with its own clip and a little silence before
-- the next one starts.
local CLIP_SECONDS = 75

-- Silence before the narration of a flight: the griffon is still lifting and the
-- loading screen may still be fading, so the voice waits a few seconds after
-- take-off. Every clip of the schedule is pushed back by this much.
local START_DELAY_SECONDS = 3

-- A clip heard less than this long ago is not offered again, even on another
-- flight: flying somewhere and straight back does not repeat the same narration.
-- The memory lasts for the session only (it resets on /reload).
local REPLAY_COOLDOWN_SECONDS = 5 * 60

local TAKEOFF_WATCH_SECONDS = 20
local TAKEOFF_POLL_SECONDS = 0.5

local flightAnnounced = false
local watchUntil = 0

-- When each clip last started, for the replay cooldown above (file -> GetTime).
local lastPlayed = {}

-- A flat list of every shipped clip, for the fallback when a route has no zone
-- timeline yet.
local ALL_AUDIO = {}
do
	for region, subs in pairs(DATA.Audio) do
		for _, files in pairs(subs) do
			for _, file in ipairs(files) do
				ALL_AUDIO[#ALL_AUDIO + 1] = file
			end
		end
	end
end

local function Print(message)
	DEFAULT_CHAT_FRAME:AddMessage("|cff33ff99Flight Narrator:|r " .. message)
end

-- True while a clip is still on cooldown, i.e. played less than
-- REPLAY_COOLDOWN_SECONDS ago on a previous flight.
local function RecentlyPlayed(file)
	local at = lastPlayed[file]
	return at ~= nil and (GetTime() - at) < REPLAY_COOLDOWN_SECONDS
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

local function PlayFile(file)
	local path = CLIP_BASE .. file
	local ok, willPlay = pcall(PlaySoundFile, path, CLIP_CHANNEL)
	if ok and willPlay then
		lastPlayed[file] = GetTime()
		Print("playing " .. file)
	else
		Print("could not play " .. path)
	end
end

-- Fallback when a route has no zone timeline: one clip drawn from the whole
-- library, skipping the ones still on cooldown, a few seconds after take-off.
local function PlayRandomClip()
	if #ALL_AUDIO == 0 then
		Print("no clips shipped")
		return
	end
	local fresh = {}
	for _, file in ipairs(ALL_AUDIO) do
		if not RecentlyPlayed(file) then
			fresh[#fresh + 1] = file
		end
	end
	if #fresh == 0 then
		Print("every clip is on cooldown")
		return
	end
	local file = fresh[random(#fresh)]
	if C_Timer and C_Timer.After then
		C_Timer.After(START_DELAY_SECONDS, function()
			if OnFlightNow() then
				PlayFile(file)
			end
		end)
	else
		PlayFile(file)
	end
end

-- ---------------------------------------------------------------------------
-- Travel <-> audio association.
--
-- A travel is a duration (seconds) plus a list of zone intervals
-- { start, stop, region, subzone }. The duration is cut into equal slots of
-- ~75 s; a slot that overlaps a zone interval becomes a candidate clip, drawn
-- at random from the audio folders of every zone overlapping that slot.
-- ---------------------------------------------------------------------------

local function ComputeSlots(duration)
	local count = math.floor(duration / CLIP_SECONDS)
	if count < 1 then
		count = 1
	end
	local length = duration / count
	local slots = {}
	for i = 0, count - 1 do
		slots[i + 1] = { start = i * length, stop = (i + 1) * length }
	end
	return slots
end

local function ZonesOverlapping(slot, zones)
	local overlapping = {}
	for _, z in ipairs(zones) do
		if z.start < slot.stop and z.stop > slot.start then
			overlapping[#overlapping + 1] = z
		end
	end
	return overlapping
end

local function CandidatesFor(slot, zones, audio)
	local overlapping = ZonesOverlapping(slot, zones)
	local candidates = {}
	for _, z in ipairs(overlapping) do
		local subs = audio[z.region]
		local files = subs and subs[z.subzone]
		if files then
			for _, file in ipairs(files) do
				candidates[#candidates + 1] = file
			end
		end
	end
	return candidates
end

-- Picks one clip per slot, never twice the same file in a single flight and
-- never a clip still on cooldown from an earlier flight: a slot draws at random
-- among the candidates it can reach that are neither already played on this
-- flight nor recently played anywhere, and stays empty once none are left.
local function BuildSchedule(duration, zones, audio)
	local slots = ComputeSlots(duration)
	local schedule = {}
	local played = {}
	for _, slot in ipairs(slots) do
		local candidates = CandidatesFor(slot, zones, audio)
		local fresh = {}
		for _, file in ipairs(candidates) do
			if not played[file] and not RecentlyPlayed(file) then
				fresh[#fresh + 1] = file
			end
		end
		if #fresh > 0 then
			local file = fresh[random(#fresh)]
			played[file] = true
			schedule[#schedule + 1] = {
				start = slot.start,
				file = file,
			}
		end
	end
	return schedule
end

-- ---------------------------------------------------------------------------
-- Playback. Slots are scheduled relative to the flight start, plus a short
-- START_DELAY_SECONDS so the narration does not step on the take-off: each clip
-- starts at the beginning of its slot, pushed back by that delay. A token
-- invalidates pending timers the moment the flight ends or a new schedule
-- replaces the current one.
-- ---------------------------------------------------------------------------

local scheduleToken = 0

local function StopSchedule()
	scheduleToken = scheduleToken + 1
end

local function PlaySchedule(schedule)
	StopSchedule()
	local token = scheduleToken
	for _, entry in ipairs(schedule) do
		local delay = START_DELAY_SECONDS + entry.start
		local file = entry.file
		if C_Timer and C_Timer.After then
			C_Timer.After(delay, function()
				if token ~= scheduleToken then
					return
				end
				if not OnFlightNow() then
					return
				end
				PlayFile(file)
			end)
		end
	end
end

-- ---------------------------------------------------------------------------
-- Route lookup. The flight source is the taxi map's "CURRENT" node and the
-- destination is the node the player clicked. Both are cached while the taxi
-- map is open, because the node names stop being readable once it closes.
-- ---------------------------------------------------------------------------

local taxiNodeNames = {}
local taxiSourceName = nil
local pendingSource = nil
local pendingDestination = nil

local function CacheTaxiNodes()
	wipe(taxiNodeNames)
	taxiSourceName = nil
	if not NumTaxiNodes then
		return
	end
	local count = NumTaxiNodes()
	for i = 1, count do
		local name = TaxiNodeName and TaxiNodeName(i) or nil
		if name and name ~= "INVALID" then
			taxiNodeNames[i] = name
		end
		if TaxiNodeGetType and TaxiNodeGetType(i) == "CURRENT" then
			taxiSourceName = name
		end
	end
	if DEBUG then
		Print("taxi map opened: " .. count .. " nodes, source = " .. tostring(taxiSourceName))
	end
end

local function PlayerFaction()
	if not UnitFactionGroup then
		return nil
	end
	local tag = UnitFactionGroup("player")
	if tag == "Horde" or tag == "Alliance" then
		return tag:lower()
	end
	return nil
end

local function Translate(name)
	if DATA.NodeNames and DATA.NodeNames[name] then
		return DATA.NodeNames[name]
	end
	return name
end

local function LookupTravel()
	local faction = PlayerFaction()
	if not faction or not pendingSource or not pendingDestination then
		return nil
	end
	local factionTravels = DATA.Travels[faction]
	local sources = factionTravels and factionTravels[Translate(pendingSource)]
	return sources and sources[Translate(pendingDestination)]
end

local function FallbackReason(travel)
	if not pendingSource or not pendingDestination then
		return "no source/destination captured (taxi map not opened?)"
	end
	local faction = PlayerFaction()
	if not faction then
		return "unknown faction"
	end
	local factionTravels = DATA.Travels[faction]
	if not factionTravels then
		return "no travel data for faction " .. tostring(faction)
	end
	local source = Translate(pendingSource)
	local destination = Translate(pendingDestination)
	local sources = factionTravels[source]
	if not sources then
		return "unknown source " .. tostring(pendingSource) .. " (-> " .. tostring(source) .. ")"
	end
	if not sources[destination] then
		return "unknown destination " .. tostring(pendingDestination)
	end
	if not travel or not (travel.zones and #travel.zones > 0) then
		return "route has no zone timeline (only duration)"
	end
	return "no clips for route zones"
end

local function AnnounceFlight()
	local faction = PlayerFaction()
	local travel = LookupTravel()
	if DEBUG then
		Print("flight start: faction=" .. tostring(faction)
			.. ", source=" .. tostring(pendingSource) .. " -> " .. tostring(Translate(pendingSource))
			.. ", destination=" .. tostring(pendingDestination) .. " -> " .. tostring(Translate(pendingDestination)))
	end
	if travel and travel.duration and travel.duration > 0
		and travel.zones and #travel.zones > 0 then
		local schedule = BuildSchedule(travel.duration, travel.zones, DATA.Audio)
		if #schedule > 0 then
			Print(#schedule .. " clip(s) queued for " .. tostring(pendingSource)
				.. " -> " .. tostring(pendingDestination))
			PlaySchedule(schedule)
			return
		end
	end
	if DEBUG then
		Print("fallback to random clip: " .. FallbackReason(travel))
	end
	PlayRandomClip()
end

-- The single point that decides whether a flight is happening. Announces once,
-- at the start, and re-arms when the flight ends.
local function CheckFlight()
	if OnFlightNow() then
		if not flightAnnounced then
			flightAnnounced = true
			AnnounceFlight()
		end
	elseif flightAnnounced then
		flightAnnounced = false
		StopSchedule()
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
-- the spot: a taxi that is refused costs no flight. The destination node index
-- is the argument TakeTaxiNode was called with; its name was cached when the
-- taxi map opened.
local function OnTaxiClicked(destIndex)
	pendingDestination = taxiNodeNames[destIndex]
	pendingSource = taxiSourceName
	if DEBUG then
		Print("taxi clicked: index=" .. tostring(destIndex)
			.. ", source=" .. tostring(pendingSource)
			.. ", destination=" .. tostring(pendingDestination))
	end
	flightAnnounced = false
	watchUntil = GetTime() + TAKEOFF_WATCH_SECONDS
	WatchForTakeoff()
end

local eventFrame = CreateFrame("Frame")
eventFrame:RegisterEvent("PLAYER_LOGIN")
eventFrame:RegisterEvent("TAXIMAP_OPENED")
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
		Print("loaded. A route's zone clips play when a flight launches.")
		return
	end

	if event == "TAXIMAP_OPENED" then
		CacheTaxiNodes()
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

SLASH_FLIGHTNARRATOR1 = "/fn"
SlashCmdList["FLIGHTNARRATOR"] = function()
	DEBUG = not DEBUG
	Print("debug " .. (DEBUG and "on" or "off"))
end



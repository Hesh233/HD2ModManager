-- Two independent physics pipelines. Accepted skeleton code is not edited or shared with direct math.
local M = { VERSION = "1.0.0", DIRECT = "direct-v1", SKELETON = "skeleton-v1" }
local INSTALL_KEY = "__hd2physbone_routes"

-- Pure routing: no node-count/bind guessing. Missing/invalid legacy metadata stays local.
function M.classify(rig, marker)
	if type(rig) == "table" then
		if type(rig.drivers) == "table" and rig.drivers.version == 3 then return M.SKELETON end
		for _, bone in ipairs(rig.bones or {}) do
			if type(bone.name) == "string" and bone.name:match("^hd2n_%x+_") then return M.SKELETON end
		end
	end
	if marker == M.DIRECT then return M.DIRECT end
	return M.SKELETON
end

local function marker_at(compat, path)
	if type(compat._read_container_bytes) ~= "function" then return nil end
	local bytes = compat._read_container_bytes(path)
	if bytes == nil then return nil end
	local container = compat.parse_container(bytes)
	local record = container and compat.find_record(container, "hd2_physics_route.txt")
	return record and record.data or nil
end

function M.new(localCompat, skeletonRuntime, directCompat, directRuntime)
	local active
	local api = { VERSION = skeletonRuntime.VERSION, DIRECT_VERSION = directRuntime.VERSION,
		ROUTING_VERSION = M.VERSION }
	local function filtered(base, wanted)
		local view = setmetatable({}, { __index = base })
		view.load_rig = function(paths, logger)
			for _, path in ipairs(paths or localCompat.default_search_paths()) do
				local rig = localCompat.load_rig({ path })
				if rig ~= nil and M.classify(rig, marker_at(localCompat, path)) == wanted then
					-- The direct branch uses the exact upstream parser, not the local solver's objects.
					return base.load_rig({ path }, logger)
				end
			end
			return nil
		end
		return view
	end
	local skeletonView = filtered(localCompat, M.SKELETON)
	local directView = filtered(directCompat, M.DIRECT)
	local function options_for(options, compat, direct)
		local clone = {}
		for key, value in pairs(options or {}) do clone[key] = value end
		clone.compat = compat
		if type(clone.carriers) == "table" then
			local owned = {}
			for _, carrier in ipairs(clone.carriers) do
				local marker = carrier.physicsRoute
				if marker == nil and type(carrier.path) == "string" then marker = marker_at(localCompat, carrier.path) end
				local route = M.classify(carrier.rig, marker)
				if route == (direct and M.DIRECT or M.SKELETON) then owned[#owned + 1] = carrier end
			end
			clone.carriers = owned
		end
		if direct then
			-- Never install local attachment/VRD ownership in the direct pipeline.
			clone.attachmentModule, clone.attachmentProfile = nil, nil
		end
		return clone
	end
	function api.install(engine, options)
		local existing = rawget(_G, INSTALL_KEY)
		if existing ~= nil then return existing end
		-- Do not reuse an older unfiltered state and then drive its units a second time.
		if rawget(_G, "__hd2physbone_runtime") ~= nil or rawget(_G, "__hd2physbone_direct_runtime") ~= nil then
			error("Another physics runtime is installed; restart with one matching physics package", 2)
		end
		local skeleton = skeletonRuntime.install(engine, options_for(options, skeletonView, false))
		local ok, direct = pcall(directRuntime.install, engine, options_for(options, directView, true))
		if not ok then
			pcall(directRuntime.uninstall)
			skeletonRuntime.uninstall()
			error(direct, 2)
		end
		active = { skeleton = skeleton, direct = direct, installed = true }
		rawset(_G, INSTALL_KEY, active)
		return active
	end
	function api.uninstall()
		if active == nil then return false end
		-- LIFO: direct wraps skeleton wraps the pre-existing render callback.
		directRuntime.uninstall()
		skeletonRuntime.uninstall()
		active.installed = false
		active = nil
		rawset(_G, INSTALL_KEY, nil)
		return true
	end
	function api.setOptions(patch)
		if active == nil or type(patch) ~= "table" then return false end
		skeletonRuntime.setOptions(options_for(patch, skeletonView, false))
		directRuntime.setOptions(options_for(patch, directView, true))
		return true
	end
	api.install_ = api.install
	return api
end
return M

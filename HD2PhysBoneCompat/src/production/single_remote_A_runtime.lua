-- HD2 物理骨骼运行时（生产入口）
--
-- 这是**真正部署给玩家**的那一份。调试探针（tmp/lua-boot/probe.lua）保留在开发侧，
-- 两者共用同一个求解器库 `physbone_compat.lua`，区别只在"发现目标 + 调度"这一层。
--
-- 两种部署形态，同一个文件：
--
--   A. 内置 lua（独占 boot）
--      管理器的 boot 文档 `require` 本模块并调用 `install()`。此时我们**拥有** boot，
--      init/update/render 都是我们的。
--
--   B. 外置 lua 兼容（独立 patch 模块）
--      本文件作为一个普通 Lua 资源投放，由第三方加载器 `require` 或直接执行。
--      此时我们**不拥有**任何东西：`update`/`render` 可能是别人包装过的，
--      也可能被调用多次。所以：
--        · 绝不假设 `_G` 是我们的（不写全局，除一个安装标记）；
--        · 挂钩子一律"接在已有函数后面"，并把已有函数还回去；
--        · 所有状态挂在模块表上，重复 install 直接返回同一个实例。
--
-- 设计约束（都是实机踩出来的，改之前先看 docs/physbone-status.md）：
--   · 引擎调用是主要成本 ⇒ 每帧只做必要的事，姿态没变就不写；
--   · 不能缓存引擎返回的句柄（0.1 秒就变 inf）；
--   · 对已销毁 Unit 调任何方法 = 原生 AV ⇒ 每帧先 `Unit.alive`；
--   · 场景图重建只看 `num_scene_graph_items`（`has_node` 会假翻）。
--
-- 观测（v1.1.0 起）：这一层必须能自证"我到底做了什么"。
-- 2026-11-01 那次"物理完全没生效"排查了整整两轮，卡点全在"日志里没有事实"：
-- 分不清是没进驱动块、进了但没写、写了但写错骨、还是根本没挂上。
-- 所以下面每一处"静默 return"都配了一条原因日志，并且**只在原因变化时**落盘
-- （每 20 帧一条同样的等待原因是刷屏，不是信息）。

local M = {}

-- 2.0.0：**多人局**。以前整条调度只认"一个玩家 avatar"，多出来的候选一律当成尸体；
--        于是队友一出现就被判成"玩家换人了"，会话全丢、重新挂到队友身上，自己身上反而没物理。
--        现在按玩家分组：每个活动玩家各自持有自己的会话，谁死了只收谁。
--        附：`World.units_by_resource` 直接列出所有玩家 avatar（一次调用，替代扫 2290 个 unit）；
--        `World.debug_camera_pose` 给出相机位置，用来排序（最近的那个就是自己）；
--        链数超预算时非首位玩家按 2 帧一次驱动（dt 累积补偿，不丢时间）。
--
-- 1.9.1：容器扫描窗口改成"按实际部署的最大 patch 序号 + 5"（以前写死 0..63，
--        装一堆 mod 时排在 63 之后的物理 mod 会被漏掉，日志还误报成"没做 embed"）。
-- 2.1.1：外置导出声明 Chef 的 render/shutdown/on_stop，日志走加载器允许的目录。
-- 2.1.2：从独立 VPK 参考骨选择挂点姿态，保留原生瞄准控制节点。
-- 2.1.3：按最终模型布局识别护甲；配置影子链先融合再映射挂点，记录 render 回读与双手诊断。
-- 2.3.1: test06 native v2 shipped-bind / setter-frame repair; scheduling unchanged.
-- 2.3.6: stable-name lookup, fair incremental scoring, live-world membership.
-- 2.3.7: single-v3 discovery/identity/scheduler port; legacy/dual stays 2.3.6.
-- Solvers, authored parameters, bind profiles and direct-v1 remain local.
M.VERSION = "2.3.19"

--- 安装标记用的全局键。只写这一个全局，且值就是模块本身（便于外部检查是否已装）。
local INSTALL_KEY = "__hd2physbone_runtime"

local Compat          -- physbone_compat 模块（require 或注入）
local S               -- stingray 命名空间
local state = nil     -- 运行状态；nil = 未安装
local originalRender  -- 挂载前的 render（链式调用，不吞掉别人）

-- ---------------------------------------------------------------------------
-- 小工具
-- ---------------------------------------------------------------------------

--- 默认日志路径。`options.logPath` 可覆盖，`options.log == false` 可彻底静默。
--- <para>
--- 2026-11-07 多路径回退：部署的 Chef 1.4.1 包内运行时身份是 `CowboyBingusModLoader`，
--- 旧组合器只认 `'Chef Shared Loader'` 字符串 ⇒ logPath 没传 ⇒ 回退 `%LOCALAPPDATA%`
--- ⇒ **被 loader 的 io 沙箱（lock_files/WDIR 白名单）静默拦截，游戏内零日志**。
--- 现在按顺序试：options.logPath → loader.log_directory（任何 loader，只要给了）→
--- LOCALAPPDATA。哪个能打开用哪个，并把实际路径记进首行。
--- </para>
local function defaultLogPath(options)
	if options and options.log == false then return nil end
	local candidates = {}
	if options and type(options.logPath) == "string" and #options.logPath > 0 then
		candidates[#candidates + 1] = options.logPath
	end
	-- 任何提供 log_directory 的 loader（Chef / Bingus / 其它同族）都在其白名单内。
	local loader = rawget(_G, "__hd2_loader")
	if type(loader) == "table" and type(rawget(loader, "log_directory")) == "string"
		and #rawget(loader, "log_directory") > 0 then
		candidates[#candidates + 1] = rawget(loader, "log_directory") .. "/hd2physbone_compact.log"
	end
	local base = os.getenv("LOCALAPPDATA")
	if type(base) == "string" and #base > 0 then candidates[#candidates + 1] = base .. "\\hd2physbone_compact.log" end
	for _, path in ipairs(candidates) do
		local ok, handle = pcall(io.open, path, "a")
		if ok and handle ~= nil then
			pcall(function() handle:close() end)
			return path
		end
	end
	return nil
end

--- 造一个 logger。返回 `log, context`。
--- <para>
--- 最新会话独立compact文件，90秒活动驱动窗口/128KiB上限。
--- 旧hd2physbone.log不改写；逐帧求解不受录制停止影响，错误限流。
local function makeLogger(options)
	local handle = nil
	local path = defaultLogPath(options)
	if path then
		local ok, h = pcall(io.open, path, "w")
		if ok then handle = h end
	end
	local debugEnabled = options ~= nil and options.debug == true
	local context = { frame = 0, bytes = 0, suppressed = 0, active = false }
    local maxSeconds=options.logRecordSeconds or 90
    local maxBytes=options.logMaxBytes or 131072
    assert(type(maxSeconds)=='number' and maxSeconds==maxSeconds and maxSeconds>=0 and maxSeconds<=3600,'invalid_log_duration')
    assert(type(maxBytes)=='number' and maxBytes==maxBytes and maxBytes>=8192 and maxBytes<=10485760,'invalid_log_size')
    local lastError={}
    local function now()
        local ok,v=pcall(function()return S.Application.time_since_launch()end)
        return ok and type(v)=='number' and v==v and v or 0
    end
	context.activate=function()if not context.started then context.started=now() end end
    local function emit(text,tail)
        if context.bytes+#text+1>(tail and maxBytes or maxBytes-1024) then context.suppressed=context.suppressed+1;return end
        context.bytes=context.bytes+#text+1
		if handle ~= nil then
			pcall(function() handle:write(text, "\n") handle:flush() end)
		end
		if debugEnabled then
			local real = rawget(_G, "print")
			if type(real) == "function" then pcall(real, text) end
		end
	end
	-- 会话头：实际落盘路径 + 版本，一眼分清"哪次会话、写到了哪"。
	-- 保留"时间戳 + 帧号"前缀（日志格式契约：runtime-harness 首行断言 + 时序可读性）。
	emit(string.format("%s f%-7d ==== 会话开始 %s | 运行时 %s | 日志路径: %s",
		os.date("%H:%M:%S"), 0, os.date("%Y-%m-%d %H:%M:%S"), M.VERSION or "?", path or "(无——所有候选路径都打不开)"))
	local function log(fmt, ...)
		if handle == nil and not debugEnabled then return end
        local t=now()
        if context.active and not context.started then context.started=t end
        local critical=fmt:find('[错误]',1,true) or fmt:find('[失败]',1,true) or fmt:find('[警告]',1,true)
        local expired=context.started and t-context.started>=maxSeconds
        if not critical and (expired or context.bytes>maxBytes-4096) then
            context.suppressed=context.suppressed+1
            if not context.stopped then
                context.stopped=true;emit(string.format('%s f%d pb log_stop seconds=%g bytes=%d',os.date('%H:%M:%S'),context.frame,maxSeconds,context.bytes))
            end
            return
        end
        if critical then
            local last=lastError[fmt]
            if last and t>=last and t-last<(options.logErrorIntervalSeconds or 2) then context.suppressed=context.suppressed+1;return end
            lastError[fmt]=t
        end
        local body = select("#", ...) > 0 and string.format(fmt, ...) or fmt
        body=body:gsub('%[physbone%]','pb')
        if #body>2048 then body='pb long_record bytes='..#body end
        emit(string.format("%s f%d %s", os.date("%H:%M:%S"), context.frame, body))
	end
	context.close=function()
        emit(string.format('%s f%d pb log_summary bytes=%d suppressed=%d',os.date('%H:%M:%S'),context.frame,context.bytes,context.suppressed),true)
        if handle then pcall(function()handle:flush();handle:close()end);handle=nil end
    end
    return log, context
end

local function try(...)
	local ok, a, b, c = pcall(...)
	if ok then return a, b, c end
	return nil, tostring(a)
end


local function readVector(S_, vector)
	if vector == nil then return nil end
	local ok, x, y, z = pcall(function() return S_.Vector3.to_elements(vector) end)
	if ok and type(x) == "number" and x == x then return x, y, z end
	return nil
end

local function hasNamedNode(S_, unit, name)
	if type(Compat.has_named_node) == "function" then return Compat.has_named_node(S_, unit, name) end
	local ok, has = pcall(S_.Unit.has_node, unit, name)
	if ok and has == true then return true end
	local made, id = pcall(function() return S_.Application.string_to_id32(name) end)
	if not made or id == nil then return false end
	local found, value = pcall(S_.Unit.has_node, unit, id)
	return found and value == true
end

--- `Unit.debug_name` 返回形如 `#ID[a0cc3d2318d9e237]` 的**实例**标识。
--- 这是运行时唯一可靠的"是不是同一个 unit"判据（`Unit.id` 对大量 unit 返回 nil）。
--- ⚠️ 只能对活着的 unit 调：销毁之后再读就是原生 AV，所以挂载时就要记下来。
local function unit_tag(S_, unit)
	local text = try(S_.Unit.debug_name, unit)
	if type(text) ~= "string" then return "?" end
	return text
end

--- 记一条"还没挂上"的原因。
--- 只在**原因变化**时落盘，重复次数留给心跳报——这样"一直卡在同一步"和"来回变"能区分开。
--- `detail` 里的数字会变（分数、节点数…），所以只在变化时打一次，不参与去重键。
local function note_wait(runtime, reason, detail)
	if runtime.waitReason == reason then
		runtime.waitRepeat = (runtime.waitRepeat or 0) + 1
		return
	end
	runtime.logger("[physbone][等待] %s%s", reason, detail ~= nil and ("：" .. detail) or "")
	runtime.waitReason = reason
	runtime.waitRepeat = 0
end

-- ---------------------------------------------------------------------------
-- 世界发现
-- ---------------------------------------------------------------------------

--- 主世界 + 它的 unit 列表。优先用上次记住的下标（省掉遍历所有世界）。
local function pickWorld(S_, cache)
	local worlds = try(S_.Application.worlds)
	if type(worlds) ~= "table" or #worlds == 0 then return nil, nil end
	local chosen, chosenUnits, chosenIndex
	-- A world index may now refer to a different preview/mission world. Compare the
	-- actual world handle in the fresh list before ever calling World.units on it.
	if cache.world ~= nil then
		for index = 1, #worlds do
			if worlds[index] == cache.world then
				local units = try(S_.World.units, worlds[index])
				if type(units) == "table" and #units >= 64 then
					chosen, chosenUnits, chosenIndex = worlds[index], units, index
				end
				break
			end
		end
	end
	if chosen == nil then
		local bestCount = -1
		for index = 1, #worlds do
			local units = try(S_.World.units, worlds[index])
			local count = type(units) == "table" and #units or -1
			if count > bestCount then
				chosen, chosenUnits, chosenIndex, bestCount = worlds[index], units, index, count
			end
		end
	end
	if cache.world ~= chosen then
		cache.settle, cache.readyWorld = nil, nil
		cache.cameraUsable, cache.cameraLogged, cache.cameraRetryAt = nil, nil, nil
	end
	cache.world, cache.worldIndex = chosen, chosenIndex
	return chosen, chosenUnits
end

--- 玩家 avatar 的资源路径。同一个角色的所有玩家共用这一个资源，所以
--- `World.units_by_resource(world, 路径)` **一次调用**就能把场上所有玩家列出来，
--- 不必再"扫 2290 个 unit 猜谁有动画状态机"。
---
--- 这也是"多人局只给一个人挂物理"的正解：我们从来不需要知道**哪个是我**，
--- 需要的是**哪些是玩家**——这个资源名就是那个答案。谁是第一位（自己）交给相机距离。
local DEFAULT_AVATAR_RESOURCE = "content/fac_helldivers/cha_avatar/avatar_helldiver"

--- 相机位置。只用于两件事：给玩家排序（最近的那个＝自己）、给驱动预算定优先级。
--- 读不到**不影响功能**（只是"谁是第一位"退回按 unit 顺序），所以任何一步失败都安静返回 nil，
--- 并记住别再试——每帧问一次注定失败的引擎调用纯属浪费。
local function cameraPosition(S_, world, cache)
	local frame = cache.frame or 0
	if cache.cameraUsable == false and frame < (cache.cameraRetryAt or 0) then return nil end
	local function unavailable()
		cache.cameraUsable, cache.cameraRetryAt = false, frame + 60
		return nil
	end
	local matrix = S_.Matrix4x4
	if type(matrix) ~= "table" or type(matrix.translation) ~= "function" then
		return unavailable()
	end
	local pose = try(S_.World.debug_camera_pose, world)
	if pose == nil then
		return unavailable()
	end
	local ok, value = pcall(matrix.translation, pose)
	if not ok then
		return unavailable()
	end
	local x, y, z = readVector(S_, value)
	if x == nil then
		return unavailable()
	end
	cache.cameraUsable, cache.cameraRetryAt = true, nil
	return x, y, z
end

--- 场上**所有**玩家 avatar。判据两级：
---   ① `World.units_by_resource(world, avatar 资源路径)` —— 精确、一次调用。
---   ② 拿不到（老版本没这个函数 / 资源路径变了）才退回全量扫描"有动画状态机 + 带 support_mg"。
--- 两种都要求"带 support_mg"：那是玩家 avatar 的挂点骨，人台/敌人没有。
local function findAvatars(S_, world, units, count, supportMg, minNodes, options, cache)
	local resource = options.avatarResource or DEFAULT_AVATAR_RESOURCE
	local live = {}
	for index = 1, #units do live[units[index]] = true end
	local byResource = nil
	if type(S_.World) == "table" and type(S_.World.units_by_resource) == "function" then
		byResource = try(S_.World.units_by_resource, world, resource)
	end

	local function collect(candidates, requireAnim)
		local list, seen, noAnim = {}, {}, 0
		for index = 1, #candidates do
			local unit = candidates[index]
			if unit ~= nil and live[unit] and seen[unit] == nil then
				seen[unit] = true
				if Compat.unit_alive(S_, unit) then
					local nodes = try(S_.Unit.num_scene_graph_items, unit)
					local animated = try(S_.Unit.has_animation_state_machine, unit) == true
					if type(nodes) == "number" and nodes >= minNodes
						and (supportMg == nil or hasNamedNode(S_, unit, supportMg)) then
						if requireAnim and not animated then
							noAnim = noAnim + 1
						else
							list[#list + 1] = { unit = unit, nodes = nodes }
						end
					end
				end
			end
		end
		return list, noAnim
	end

	local list, dropped = nil, 0
	if type(byResource) == "table" and #byResource > 0 then
		cache.avatarSource = "units_by_resource"
		-- 先要求"有动画状态机"：载具/人台这类同资源的东西通常没有状态机，这一条把它们挡在外面。
		list, dropped = collect(byResource, true)
		-- 但绝不因为这一条把所有人都挡掉：退回"只要有 support_mg 就算"。
		if #list == 0 then list, dropped = collect(byResource, false) end
	else
		cache.avatarSource = "scan"
		local scanned = {}
		for index = 1, count do
			local unit = units[index]
			if Compat.unit_alive(S_, unit) and try(S_.Unit.has_animation_state_machine, unit) == true then
				scanned[#scanned + 1] = unit
			end
		end
		list = collect(scanned, true)
	end
	-- 把"同资源但没有动画状态机"的数量报出来：实机里"某个队友没挂上"到底是没找到、
	-- 还是被这一条挡掉了，只有这个数字能分辨。
	cache.avatarDroppedNoAnim = dropped
	return list
end

--- 一趟扫完：**所有**玩家 avatar + 候选护甲件（存活、节点数够），
--- 每个护甲件归属到"离它最近的那个玩家"，按玩家顺序排序。
--- 返回 nil + 原因 表示"还没准备好"（场景在变 / 找不到目标），调用方下一拍再来。
local function discover(S_, cache, options, logger)
	local world, units = pickWorld(S_, cache)
	if world == nil or units == nil then return nil, nil, nil, nil, "读不到世界或 unit 列表" end
	local count = #units
	-- Enemies, effects and projectiles churn continuously in a multiplayer mission.
	-- Settle the target Unit layout below, never demand a stable global Unit count.
	cache.lastUnitCount = count
	local supportMg = "support_mg"
	local minNodes = options.minNodes or 90
	local maxAvatars = options.maxAvatars or 4

	-- ① 找全所有玩家。
	local avatars = findAvatars(S_, world, units, count, supportMg, minNodes, options, cache)
	if #avatars == 0 then
		cache.worldIndex = nil   -- 可能选错了世界，下一拍重新挑
		return nil, nil, nil, nil, string.format("没找到玩家 avatar（%d 个 unit，判据=%s%s）",
			count, tostring(cache.avatarSource),
			(cache.avatarDroppedNoAnim or 0) > 0
				and string.format("，另有 %d 个同资源 unit 因没有动画状态机被跳过", cache.avatarDroppedNoAnim)
				or "")
	end
	if (cache.avatarDroppedNoAnim or 0) > 0 and cache.avatarDroppedLogged ~= true then
		cache.avatarDroppedLogged = true
		logger(string.format(
			"[physbone][玩家] 找到 %d 个玩家；另有 %d 个同资源 unit 没有动画状态机，按载具/人台处理（跳过）",
			#avatars, cache.avatarDroppedNoAnim))
	end

	-- ② 位置 + 排序。相机距离最近的那个＝自己（第一人称时相机就在自己头上）。
	local camX, camY, camZ = cameraPosition(S_, world, cache)
	if cache.cameraLogged ~= true then
		cache.cameraLogged = true
		-- 这条只打一次：实机排查时"第一个到底是不是我"完全取决于它，
		-- 而 debug_camera_pose 在某些版本上返回的是开发自由相机，那种情况下排序会退化。
		logger(string.format("[physbone] 玩家排序依据：%s",
			camX ~= nil and "相机位置（最近的那个＝自己）" or "读不到相机 ⇒ 只按节点数排（功能不受影响）"))
	end
	for index = 1, #avatars do
		local avatar = avatars[index]
		local ax, ay, az = readVector(S_, try(S_.Unit.world_position, avatar.unit, 1))
		avatar.x, avatar.y, avatar.z = ax, ay, az
		if camX ~= nil and ax ~= nil then
			local dx, dy, dz = ax - camX, ay - camY, az - camZ
			avatar.cameraDistance = dx * dx + dy * dy + dz * dz
		end
	end
	table.sort(avatars, function(a, b)
		local da, db = a.cameraDistance, b.cameraDistance
		if da ~= nil and db ~= nil then return da < db end
		if da ~= nil then return true end
		if db ~= nil then return false end
		return (a.nodes or 0) > (b.nodes or 0)
	end)
	if #avatars > maxAvatars then
		-- 上限只防"某个场景里有几十个 avatar 资源实例"把预算吃光；正常对局是 1~4。
		for index = #avatars, maxAvatars + 1, -1 do table.remove(avatars, index) end
	end
	for index = 1, #avatars do
		avatars[index].order = index
		avatars[index].tag = nil   -- 实例名等真要挂载时再读（每个 unit 一次引擎调用）
	end

	-- ③ 护甲候选：扫一遍 unit。avatar 自己不进候选（它们是骨架，不是护甲件）。
	local avatarUnits = {}
	for index = 1, #avatars do avatarUnits[avatars[index].unit] = avatars[index] end

	local withMg, withoutMg = {}, {}
	for index = 1, count do
		local unit = units[index]
		if avatarUnits[unit] == nil and Compat.unit_alive(S_, unit) then
			local nodes = try(S_.Unit.num_scene_graph_items, unit)
			if type(nodes) == "number" and nodes >= minNodes then
				if hasNamedNode(S_, unit, supportMg) then
					withMg[#withMg + 1] = { unit = unit, nodes = nodes, mg = true }
				else
					withoutMg[#withoutMg + 1] = { unit = unit, nodes = nodes, mg = false }
				end
			end
		end
	end
	local armorList = withMg
	for _, candidate in ipairs(withoutMg) do
		armorList[#armorList + 1] = candidate
	end
	if #armorList == 0 then
		return nil, nil, nil, nil, string.format("没有候选护甲件（%d 个 unit，节点数门槛 %d）", count, minNodes)
	end

	-- ④ 归属：每个候选件属于**离它最近的那个玩家**。
	--    玩家那套护甲挂在 avatar 骨架上，位置几乎重合；队友的在队友身上；尸体/人台离谁都远。
	--    这一个不等式就是全部事实来源——不需要问"谁是主件"，也不会因为"多出来一个候选"就误判换人。
	for _, candidate in ipairs(armorList) do
		local ux, uy, uz = readVector(S_, try(S_.Unit.world_position, candidate.unit, 1))
		if ux ~= nil then
			local best, bestDistance = avatars[1], math.huge
			for index = 1, #avatars do
				local avatar = avatars[index]
				if avatar.x ~= nil then
					local dx, dy, dz = ux - avatar.x, uy - avatar.y, uz - avatar.z
					local distance = dx * dx + dy * dy + dz * dz
					if distance < bestDistance then best, bestDistance = avatar, distance end
				end
			end
			candidate.owner = best
			candidate.distance = bestDistance
		else
			candidate.owner = avatars[1]
			candidate.distance = math.huge
		end
	end
	table.sort(armorList, function(a, b)
		local oa = a.owner ~= nil and a.owner.order or 99
		local ob = b.owner ~= nil and b.owner.order or 99
		if oa ~= ob then return oa < ob end
		if a.mg ~= b.mg then return a.mg end
		return (a.distance or math.huge) < (b.distance or math.huge)
	end)
	return world, units, avatars, armorList
end

--- 从部署后的 patch 尾部读物理容器。返回 { { rig = ..., path = ... }, ... }。
--- 路径是"猜"的（运行时不知道 data 的绝对路径），所以多前缀都试一遍，成功后按相对名去重。
---
--- **扫描窗口按实际部署算，不写死。** patch 序号 = 这个 mod 在配置里的载入顺序：
--- 单独装一个物理 mod 时它是 `patch_0`，装了一大堆之后它可能是 `patch_87`。
--- 以前这里写死 `0..63`，于是"装一堆 mod 就找不到任何容器"——排在 63 之后的容器全被漏掉，
--- 日志还写着"来源模型可能没做 embed"，把问题指到了完全错误的方向。
---
--- 现在：先定出能打开的前缀 → 用倍增+二分问出最大序号（O(log N) 次探测）→ 扫 `0..最大+5`。
--- 那 +5 是余量：万一部署序列中间出现空洞（理论上不会，管理器每次从 0 连续重编），
--- 二分可能低估，多探五格兜住。
-- Registered-model consumer integration. Existing discovery/owner safety stays on.
local ConsumerRuntime={}
function ConsumerRuntime.close(runtime)
 local cp=Compat and Compat.consumer_api
 if cp and runtime.consumerContext then cp.close(runtime.consumerContext)end
 runtime.consumerContext=nil;runtime.consumerSerial=nil
end
function ConsumerRuntime.reset(runtime)
 local cp=Compat and Compat.consumer_api
 if not cp or runtime.options.consumerPlans==false then return end
 ConsumerRuntime.close(runtime)
 local files={};for _,f in ipairs(runtime.cache.consumerFiles or runtime.options.consumerFiles or{})do files[#files+1]={tocPath=f.tocPath or f.path,index=f.index or 0}end
 local ctx=cp.new(files,runtime.logger);ctx.world=runtime.world;runtime.consumerContext=ctx;runtime.consumerSerial=-1
 for _,s in ipairs(runtime.sessions or{})do if s.singleMainline then cp.unapply(s);s.consumerContext=nil end end
end
function ConsumerRuntime.watch(runtime)
 if runtime.consumerContext and runtime.consumerContext.world~=runtime.world then ConsumerRuntime.close(runtime)end
end
function ConsumerRuntime.bind(runtime,s)
 if not s.singleMainline or runtime.options.consumerPlans==false or not Compat.consumer_api then return end
 if not runtime.consumerContext then ConsumerRuntime.reset(runtime)end
 local ok,why=pcall(Compat.consumer_api.bind,runtime.consumerContext,s)
 if not ok then Compat.consumer_api.unapply(s);s.consumerPending=false;s.consumerReason="bind-error";runtime.logger("[physbone][CONSUMERS] full fallback bind-error=%s",tostring(why))end
end
function ConsumerRuntime.tick(runtime)
 local cp=Compat and Compat.consumer_api;if not cp then return end
 if runtime.options.consumerPlans==false then
  if runtime.consumerContext then for _,s in ipairs(runtime.sessions or{})do if s.singleMainline then cp.unapply(s);s.consumerPending=false end end;ConsumerRuntime.close(runtime)end
  return
 end
 local ctx=runtime.consumerContext
 if not ctx then
  ConsumerRuntime.reset(runtime);ctx=runtime.consumerContext;if not ctx then return end
  for _,s in ipairs(runtime.sessions or{})do if s.singleMainline then ConsumerRuntime.bind(runtime,s)end end
 end
 local ok,why=pcall(cp.tick,ctx,runtime.options.consumerHashBytesPerFrame)
 if not ok then
  runtime.logger("[physbone][CONSUMERS] full fallback proof-error=%s",tostring(why))
  for _,s in ipairs(runtime.sessions or{})do if s.singleMainline then cp.unapply(s);s.consumerPending=false end end
  ConsumerRuntime.close(runtime);return
 end
 if runtime.consumerSerial~=ctx.serial then
  runtime.consumerSerial=ctx.serial
  for _,s in ipairs(runtime.sessions or{})do if s.singleMainline and s.consumerPending then ConsumerRuntime.bind(runtime,s)end end
 end
end
function ConsumerRuntime.legitimate(s)return s.consumerMode=="empty"or s.consumerMode=="drivers"end
function ConsumerRuntime.hasWork(s)return not Compat.consumer_api or Compat.consumer_api.hasWork(s)end

local function loadCarriers(S_, cache, options, logger)
	local archive = options.archiveId or "9ba626afa44a3aa3"
	local carriers = {}
	local seen = {}

	-- 老版本 compat 没有探测函数（外置包里两个文件总是一起生成，但玩家可能只更新了其中一个）。
	-- 缺了它就退回原来的固定窗口，至少不至于整条物理链路报错。
	local canProbe = type(Compat.detect_prefix) == "function"
		and type(Compat.find_max_patch_index) == "function"

	local prefixes = { "data/", "data\\", "./data/", "../data/", "..\\data\\" }
	local poked = {}
	local consumerFiles, consumerSeen = {}, {}
	local scannedTo = -1
	for _, prefix in ipairs(prefixes) do
		if not canProbe or Compat.detect_prefix(archive, { prefix }) ~= nil then
			local maxIndex = options.maxPatchIndex
			if maxIndex == nil then
				local last = canProbe and Compat.find_max_patch_index(prefix, archive) or -1
				if last < 0 then
					maxIndex = canProbe and 5 or 63     -- 探不到就用老的固定窗口
				else
					maxIndex = last + 5
				end
			end
			if maxIndex > scannedTo then scannedTo = maxIndex end

			for index = 0, maxIndex do
				local toc = archive .. ".patch_" .. index
				if not consumerSeen[toc] then
					local handle = io.open(prefix .. toc, "rb")
					if handle ~= nil then
						handle:close(); consumerSeen[toc] = true
						consumerFiles[#consumerFiles + 1] = { tocPath = prefix .. toc, index = index }
					end
				end
				local relative = toc .. ".gpu_resources"
				if seen[relative] == nil then
					local handle = io.open(prefix .. relative, "rb")
					if handle ~= nil then
						handle:close()
						seen[relative] = true
						poked[#poked + 1] = prefix .. relative
						if not consumerSeen[toc] then
							consumerSeen[toc] = true
							consumerFiles[#consumerFiles + 1] = { tocPath = prefix .. toc, index = index }
						end
						local rig = Compat.load_rig({ prefix .. relative })
						if rig ~= nil and type(rig.bones) == "table" and #rig.bones > 0 then
							carriers[#carriers + 1] = { rig = rig, path = prefix .. relative }
						end
					end
				end
			end
		end
	end

	cache.consumerFiles = consumerFiles
	if #carriers > 0 then
		logger(string.format("[physbone] 读到 %d 份物理容器（扫了 patch 0..%d）", #carriers, scannedTo))
	elseif scannedTo >= 0 then
		-- **把"扫了多大范围"写进日志。** 以前只有一句"可能没做 embed"，而真正的原因
		-- 往往在"扫的窗口不够大"：说了范围，下一次一眼就能分辨是哪种。
		logger(string.format(
			"[physbone] 没找到任何物理容器（扫了 patch 0..%d，%d 个 .gpu_resources 存在但都不含容器）",
			scannedTo, #poked))
	else
		logger("[physbone] 没找到任何物理容器（data 目录下没有这个归档的 patch 文件——游戏是否还没部署过？）")
	end
	return carriers
end

-- ---------------------------------------------------------------------------
-- 挂载 / 卸载
-- ---------------------------------------------------------------------------

--- 就绪采样 + 增量挂载。
---
--- "增量"是这一版的核心：**只补新 unit、只释放主人已经不在的会话**。
--- 以前是"一有变化就把全部会话丢掉重挂"，多人局里那等于每次有人加入/复活都让所有人
--- 短暂失去物理（而且会把会话挂到错误的玩家身上）。
---
--- 返回 true 表示这一趟真的跑完了（不论有没有新挂上的），false 表示还在等场景稳定。
-- Single-HD2 policy ported from AssestinaR/HD2ModManager master
-- b78e63ebc77017aa6c70d52e0bf9e06e46360b92 (runtime 2.1.45).
-- Only discovery/identity/scheduling is shared with master. Compat, complete binds,
-- test16/Source2 repairs and legacy/native/direct numerical code remain unchanged.
local function isSingleRig(rig)
	if type(rig) ~= "table" or type(rig.drivers) ~= "table" or rig.drivers.version ~= 3 then return false end
	for _, bone in ipairs(rig.bones or {}) do
		if type(bone.name) == "string" and bone.name:match("^hd2n_%x+_") then return false end
	end
	return true
end

local RemotePhysics
local Single = (function()
	local function motion_sample(runtime, S_, unit)
		local track = runtime.motion
		if track == nil then
			track = setmetatable({}, { __mode = "k" })
			runtime.motion = track
		end
		if Compat.unit_alive(S_, unit) ~= true then return nil end
		local entry = track[unit]
		if entry == nil then
			entry = { moved = 0 }
			track[unit] = entry
		end
		local x, y, z = readVector(S_, try(S_.Unit.world_position, unit, 1))
		if x ~= nil then
			local last = entry.pos
			if last ~= nil then
				local dx, dy, dz = x - last[1], y - last[2], z - last[3]
				entry.moved = entry.moved + math.sqrt(dx * dx + dy * dy + dz * dz)
			end
			entry.pos = { x, y, z }
		end
		return entry
	end

	--- 这个 unit 是不是"跟着那个玩家走"的那一件。
	--- 返回 follows（true/false/nil=还没数据）、自身位移、主人位移。
	---
	--- 判据：主人的累计位移足够大（>5 cm，说明玩家真的动过）时，
	--- 候选自己的累计位移**至少要有主人的一半**才算"跟着"。人台是 0，直接出局。
	local function motion_follows(runtime, ownerUnit, unit)
		local track = runtime.motion
		if track == nil or ownerUnit == nil then return nil, 0, 0 end
		local selfEntry, ownerEntry = track[unit], track[ownerUnit]
		if selfEntry == nil or ownerEntry == nil then return nil, 0, 0 end
		local ownerMoved = ownerEntry.moved or 0
		if ownerMoved < 0.05 then return nil, selfEntry.moved or 0, ownerMoved end
		return (selfEntry.moved or 0) >= ownerMoved * 0.5, selfEntry.moved or 0, ownerMoved
	end

	--- 身份监视：定期采"谁在动"，并把"玩家动它不动"的件放掉。
	---
	--- 为什么放在每帧入口而不是 `tryAttach`（T21 抓到的）：`tryAttach` 只在"需要补挂"时才跑；
	--- 一旦挂好了就不再调用，于是那些在**有活动量数据之前**挂上去的人台会一直挂着。
	--- 身份纠正必须持续跑到分类稳定，所以在 drive 里按固定间隔跑。
	--- 成本：每 20 帧一次，每个玩家/会话各 1 次 `world_position`（纯读）。
	local function identity_watch(S_, runtime)
		local options = runtime.options or {}
		if options.identityWatch == false then return end
		local every = math.max(2, math.floor(options.identityPollFrames or 20))
		local frame = runtime.frame or 0
		if (frame % every) ~= 0 then return end
		for index = 1, #(runtime.avatars or {}) do
			motion_sample(runtime, S_, runtime.avatars[index].unit)
		end
		local sessions = runtime.sessions or {}
		for index = 1, #sessions do if sessions[index].consumerMode ~= "empty" then motion_sample(runtime, S_, sessions[index].unit) end end
		if #sessions == 0 then return end

		local followCount = {}
		for _, session in ipairs(sessions) do
			if session.consumerMode ~= "empty" and motion_follows(runtime, session.owner, session.unit) == true then
				local key = session.owner or false
				followCount[key] = (followCount[key] or 0) + 1
			end
		end
		local survivors, released, tags = {}, 0, nil
		for _, session in ipairs(sessions) do
			local key = session.owner or false
			-- 只在"这个主人确实有跟着动的件"时才放掉静止的那些 —— 玩家还没动过时一件都不放。
			if session.consumerMode ~= "empty" and motion_follows(runtime, session.owner, session.unit) == false and (followCount[key] or 0) > 0 then
				released = released + 1
				if tags == nil then tags = {} end
				if #tags < 4 then tags[#tags + 1] = tostring(session.unitTag) end
				if Compat.unit_alive(S_, session.unit) then pcall(Compat.release, session) end
			else
				survivors[#survivors + 1] = session
			end
		end
		if released > 0 then
			runtime.sessions = survivors
			runtime.logger("[physbone][识别] 放掉 %d 件「玩家动它不动」的件（人台/预览），剩 %d 件（%s）",
				released, #survivors, tags ~= nil and table.concat(tags, ",") or "")
		end
	end

	local function session_unit_live(runtime, unit)
		local units = runtime.liveUnits
		if units == nil then return true end
		for index = 1, #units do
			if units[index] == unit then return true end
		end
		return false
	end

	--- 丢掉失效会话。任何一个失效都意味着场景变了 ⇒ 必须重扫（不能"还剩几个就继续开"）。

	local function sched_settings(runtime)
		local options = runtime.options or {}
		return {
			fallback = options.schedFallback ~= false and options.schedFallback ~= 0,
			metres = options.schedFallbackMetres or 6,
			seconds = options.schedFallbackSeconds or 1,
			minInterval = options.schedMinIntervalSeconds or 1,
			fpLock = options.fpLock ~= false and options.fpLock ~= 0,
			fpLockMetres = options.fpLockMetres or 0.35,
			fpLockFrames = math.max(1, math.floor(options.fpLockFrames or 3)),
		}
	end


	local function nearest_avatar(S_, avatars, session)
		local sx, sy, sz = readVector(S_, try(S_.Unit.world_position, session.unit, 1))
		if sx == nil then return nil end
		local best, bestDistance = nil, math.huge
		for index = 1, #avatars do
			local avatar = avatars[index]
			if avatar.x ~= nil then
				local dx, dy, dz = sx - avatar.x, sy - avatar.y, sz - avatar.z
				local distance = dx * dx + dy * dy + dz * dz
				if distance < bestDistance then best, bestDistance = avatar, distance end
			end
		end
		return best
	end

	--- 按相机距离重排玩家顺序，并把每个会话重新归属。
	---@param forcePrimary any|nil 强制排第一的 avatar unit（第一人称锁定用）
	---@return number changed 归属真正发生变化的会话数
	local function redistribute(S_, runtime, why, forcePrimary)
		local avatars = runtime.avatars
		if avatars == nil or #avatars == 0 then return 0 end
		local camX, camY, camZ = cameraPosition(S_, runtime.world, runtime.cache or {})
		local haveCamera = camX ~= nil
		for index = 1, #avatars do
			local avatar = avatars[index]
			local ax, ay, az = readVector(S_, try(S_.Unit.world_position, avatar.unit, 1))
			avatar.x, avatar.y, avatar.z = ax, ay, az
			if haveCamera and ax ~= nil then
				local dx, dy, dz = ax - camX, ay - camY, az - camZ
				avatar.cameraDistance = dx * dx + dy * dy + dz * dz
			else
				avatar.cameraDistance = nil
			end
		end
		table.sort(avatars, function(a, b)
			local da, db = a.cameraDistance, b.cameraDistance
			if da ~= nil and db ~= nil then return da < db end
			if da ~= nil then return true end
			if db ~= nil then return false end
			return (a.nodes or 0) > (b.nodes or 0)
		end)
		-- 强制置顶：第一人称锁定的证据（水平距离≈0）比"总距离最近"强得多——
		-- 队友完全可以比你离相机更近，但他的水平分量不可能≈0。
		--
		-- **学到过"哪个是自己"就一直沿用。** 第三人称的相机在你身后约 4.5 m，
		-- 队友只要站得比相机离你更近，就会把你顶到 order>1，你的护甲被按 4~8 帧节流，
		-- 看起来就是"队友有物理、我没有"。而 F8 只是重跑同一个判据，所以按了没效果
		-- （2026-11-11 实机）。身份一旦被第一人称锁定学到，就让 F8 / 兜底重排都用它，
		-- 这两条路径才真正能把你恢复成最高权。
		local forced = forcePrimary
		if forced == nil and runtime.selfUnit ~= nil then forced = runtime.selfUnit end
		if forced ~= nil then
			for index = 1, #avatars do
				if avatars[index].unit == forced and index > 1 then
					local forcedAvatar = table.remove(avatars, index)
					table.insert(avatars, 1, forcedAvatar)
					break
				end
			end
		end
		for index = 1, #avatars do avatars[index].order = index end

		-- 最高权换人时说一声（只在真正的换人时打，避免刷屏）。
		-- 这段时间的排障全靠这一行：能直接看出"最高权是队友还是自己"。
		local primary = avatars[1]
		if primary ~= nil and runtime.primaryTag ~= primary.tag then
			runtime.primaryTag = primary.tag
			runtime.logger("[physbone][调度] 最高权=%s（相机距离 %.2f m%s）",
				tostring(primary.tag or "?"),
				primary.cameraDistance ~= nil and math.sqrt(primary.cameraDistance) or -1,
				(primary.unit == runtime.selfUnit) and "，已识别为自己" or "")
		end

		local changed, moved = 0, {}
		for _, session in ipairs(runtime.sessions or {}) do
			local best = nearest_avatar(S_, avatars, session)
			if best ~= nil then
				if session.owner ~= best.unit then
					changed = changed + 1
					moved[#moved + 1] = string.format("%s→%s", tostring(session.unitTag or "?"),
						tostring(best.tag or "?"))
					session.owner = best.unit
					session.ownerTag = best.tag or unit_tag(S_, best.unit)
				end
				session.ownerOrder = best.order
			end
		end
		-- 会话顺序也按新归属排：drive 里"第一位玩家不参与分帧"，靠的就是这个顺序
		table.sort(runtime.sessions or {}, function(a, b)
			return (a.ownerOrder or 99) < (b.ownerOrder or 99)
		end)

		runtime.avatars = avatars
		runtime.schedResets = (runtime.schedResets or 0) + 1
		runtime.schedLastResetFrame = runtime.frame
		-- 只在**真变了**的时候打日志：自由相机那种"附近谁都没有"的状态下，
		-- 这条规则会每秒触发一次，每次打一行就会把日志刷满，而且那些行没有任何信息量。
		if changed > 0 then
			runtime.logger("[physbone][调度] 重新分配（%s）：%d 个会话换了主人 %s%s",
				why, changed, table.concat(moved, " "),
				haveCamera and "" or "（相机不可读 ⇒ 只按节点数排，判据退化）")
		else
			runtime.schedNoop = (runtime.schedNoop or 0) + 1
		end
		return changed
	end

	--- 第一人称锁定：相机在自己根节点的**正上方** ⇒ **水平距离 ≈ 0**。
	--- <para>
	--- 实测（2026-11-11）：第一人称下"相机到自己根节点"的总距离稳定在 1.717~1.727 m
	--- （±5 mm），第三人称是 4.50~4.52 m。但**总距离不能当判据**：
	--- 队友站在你面前 1.7 m 处，总距离也是 1.7 m（相机在眼高、他的根在地面）。
	--- 真正伪造不了的是水平分量——别人的身体不可能站在你相机的那个点上（会碰撞）。
	--- 垂直分量对所有站在同层地面的人都约等于眼高，因此没有区分能力。
	--- </para>
	--- 语义：水平 < fpLockMetres 且连续 fpLockFrames 帧 ⇒ 锁定为"自己"；
	--- 若它当前不是最高权目标，立刻重排（不等 1 秒兜底）。
	local function fp_lock_watch(S_, runtime)
		local settings = sched_settings(runtime)
		if not settings.fpLock then return end
		local avatars = runtime.avatars
		if avatars == nil or #avatars == 0 then return end
		local camX, camY = cameraPosition(S_, runtime.world, runtime.cache or {})
		if camX == nil then return end
		local lockAvatar, lockH = nil, nil
		for index = 1, #avatars do
			local avatar = avatars[index]
			if avatar.x ~= nil then
				local dx, dy = avatar.x - camX, avatar.y - camY
				local h = math.sqrt(dx * dx + dy * dy)
				if h < settings.fpLockMetres and (lockH == nil or h < lockH) then
					lockAvatar, lockH = avatar, h
				end
			end
		end
		if lockAvatar == nil then
			runtime.fpLockFrames = 0
			runtime.fpLockUnit = nil
			return
		end
		if runtime.fpLockUnit ~= lockAvatar.unit then
			runtime.fpLockUnit = lockAvatar.unit
			runtime.fpLockFrames = 1
			runtime.fpLockH = lockH
			return
		end
		runtime.fpLockFrames = (runtime.fpLockFrames or 0) + 1
		runtime.fpLockH = lockH
		-- 只在"恰好达到帧数"时动作一次；动作后清零，这样万一又被判错还能再纠正。
		if runtime.fpLockFrames ~= settings.fpLockFrames then return end
		-- 学到"自己是谁"。**即使它已经是 order==1 也要记下来**：第三人称下队友可能把你顶掉，
		-- 之后 F8 / 兜底重排要靠这个身份把你抢回来（见 redistribute 里的沿用逻辑）。
		if runtime.selfUnit ~= lockAvatar.unit then
			runtime.selfUnit = lockAvatar.unit
			runtime.logger("[physbone][调度] 记住自己=%s（水平 %.3f m）⇒ 之后 F8 与兜底重排优先它",
				tostring(lockAvatar.tag or "?"), lockH)
		end
		if (lockAvatar.order or 99) == 1 then return end
		runtime.logger("[physbone][调度] 第一人称锁定（水平 %.3f m，%s）⇒ 立即重排",
			lockH, tostring(lockAvatar.tag or "?"))
		redistribute(S_, runtime, "第一人称锁定", lockAvatar.unit)
		runtime.fpLockFrames = 0
	end

	--- 兜底：**最高物理权单位**离开相机超过 `metres` 连续 `seconds` 秒 ⇒ 立刻重排。
	--- <para>
	--- 为什么用"它离相机远"而不是"别人离相机近"：前者只需要一次距离读取，
	--- 而且它把"观战即热点"这件事变成同一条规则的自然结果（相机换目标 ⇒ 1 秒后热点换人）。
	--- </para>
	--- 限流：最短间隔 `minInterval` 秒。**不做**"连续触发就停用"——持续触发恰恰说明
	--- 附近确实没有玩家（自由相机），此时每秒重排一次的代价（约 50 次引擎调用）
	--- 远小于它带来的正确性。连续没有变化时会自动退避，见下。
	local function scheduler_watch(S_, runtime, dt)
		local settings = sched_settings(runtime)
		if not settings.fallback then return end
		local avatars = runtime.avatars
		if avatars == nil or #avatars == 0 then return end
		local primary = avatars[1]
		if primary == nil or primary.unit == nil then return end
		local camX, camY, camZ = cameraPosition(S_, runtime.world, runtime.cache or {})
		if camX == nil then return end
		local ax, ay, az = readVector(S_, try(S_.Unit.world_position, primary.unit, 1))
		if ax == nil then return end
		local dx, dy, dz = ax - camX, ay - camY, az - camZ
		local distance = math.sqrt(dx * dx + dy * dy + dz * dz)

		if distance <= settings.metres then
			if (runtime.schedFar or 0) > 0 then runtime.schedFar = 0 end
			return
		end
		runtime.schedFar = (runtime.schedFar or 0) + (dt or (1 / 60))
		-- 退避期：判据仍然有效，但降到 1/10 的频率（附近确实没人时别每秒重排）。
		local need = settings.seconds
		if runtime.schedBackoffUntil ~= nil and runtime.frame < runtime.schedBackoffUntil then
			need = need * 10
		end
		if runtime.schedFar < need then return end

		-- 到点了。限流：上一次重置太近就再等等（保留累积值，下一帧会再试）。
		local last = runtime.schedLastResetFrame
		local since = last ~= nil and (runtime.frame - last) * (dt or (1 / 60)) or math.huge
		if since < settings.minInterval then return end

		runtime.schedFar = 0
		local changed = redistribute(S_, runtime, string.format("最高权单位距相机 %.1f m > %.0f m 持续 %.1f s",
			distance, settings.metres, settings.seconds))
		if changed == 0 then
			-- 连续多次重排都没有任何变化 ⇒ 附近确实没人（自由相机/空镜头）。
			-- 退避到 10 倍间隔，既保住正确性又不做无意义的每秒重排；有变化时立刻恢复。
			if (runtime.schedNoop or 0) >= 3 then
				runtime.schedBackoffUntil = runtime.frame
					+ math.floor(settings.minInterval * 10 * 120)
			end
		else
			runtime.schedNoop = 0
		end
	end

	--- 每帧只刷新"每个玩家到相机的距离"，**不重排、不重新归属**。
	--- 为什么要单独这一步：分档要看新鲜距离（一秒钟前的距离可能差出十几米），

	local function refresh_avatar_distances(S_, runtime)
		local avatars = runtime.avatars
		if avatars == nil or #avatars == 0 then return end
		local camX, camY, camZ = cameraPosition(S_, runtime.world, runtime.cache or {})
		if camX == nil then return end
		for index = 1, #avatars do
			local avatar = avatars[index]
			-- 防御：名单可能来自 `tryAttach`（同一帧），也可能被别处复用；这里再按指针确认一次。
			if avatar.unit ~= nil and session_unit_live(runtime, avatar.unit) then
				local ax, ay, az = readVector(S_, try(S_.Unit.world_position, avatar.unit, 1))
				if ax ~= nil then
					avatar.x, avatar.y, avatar.z = ax, ay, az
					local dx, dy, dz = ax - camX, ay - camY, az - camZ
					avatar.cameraDistance = dx * dx + dy * dy + dz * dz
				end
			end
		end
	end

	--- 会话所属玩家到相机的距离平方。只查上面刷新的缓存，**不**调引擎。
	local function owner_distance_sq(runtime, session)
		local owner = session.owner
		if owner == nil then return math.huge end
		local avatars = runtime.avatars
		if avatars == nil then return math.huge end
		for index = 1, #avatars do
			if avatars[index].unit == owner then return avatars[index].cameraDistance or math.huge end
		end
		return math.huge
	end

	--- 预算 → 两档步长（纯函数，可离线单测）。
	--- <para>
	--- 语义：**自己永远每帧**（不参与节流，这一条不可协商）；
	--- 6 m 内先保证 2 帧一次，链数真的很多时才退到 3 帧一次；
	--- 6 m 外从 4 帧起，吃紧时最多 8 帧一次。
	--- 估算方式按"链数/步长"分摊到每帧，和实测的"约 3.5 次引擎调用/链"线性对应。
	--- </para>
	---@return number nearStride, number farStride
	local function schedule_budget(primaryChains, nearChains, farChains, budget)
		if primaryChains + nearChains + farChains <= budget then return 1, 1 end
		local nearStride, farStride = 2, 4
		local function cost()
			return primaryChains + nearChains / nearStride + farChains / farStride
		end
		-- 阶梯加长（2026-11-12）：原来 far 最多 8、near 最多 3。四人局里自己那条动不了
		-- （primary 不参与节流），只靠 near≤3 / far≤8 压不到预算内 —— 船上全员 6 m 内时
		-- 实测会到 ~10 ms。把阶梯放长到 near≤6 / far≤16，才能把总链数拉回预算附近，
		-- 代价是远处队友的物理更稀（他们本来就看不见）。
		while cost() > budget do
			if farStride < 16 then
				farStride = math.min(16, farStride * 2)
			elseif nearStride < 6 then
				nearStride = math.min(6, nearStride + 1)
			else
				break
			end
		end
		-- 近处本来就没几条链时不必节流：让 6 m 内的队友完全每帧（那是他们最被看见的时候）
		if nearChains <= budget * 0.25 then nearStride = 1 end
		return nearStride, farStride
	end


	--- 手动重设的两条通道。**产品路径不得依赖外部脚本**（这套物理要随管理器分发给大量玩家），
	--- 所以按"零依赖优先"排列：
	---
	---   ① 调参文件里的 `schedReset`：写成**任意一个新的数字**就等于按了一次重置。
	---      零依赖、纯 Lua（读调参文件本来就有），玩家改一个数字即可，不需要任何额外程序。
	---   ② Stingray 自带的 `Keyboard` API（如果这个版本暴露了）——真正的一键热键。
	---      是否可用只能**实机探测**，探测结果打一行日志（见 probe_input）。
	--- 外部脚本写文件那条通道**已经删除**：玩家机器上不会有我们开发用的监听器。


-- Single-only fresh index adapter. Master also checks inventory membership;
-- retain that safety invariant, but avoid O(world units * single sessions).
-- Only active single Units and their <=4 avatars are indexed. Every callback
-- validates their actual slots in the CURRENT array; moved slots are rebuilt in
-- one inventory pass. A resource ID or a cached boolean cannot
-- prove that a pointer is safe; this check never dereferences a missing Unit.
local linear_unit_live = session_unit_live
local function indexed_unit_live(runtime, unit)
	local units = runtime.liveUnits
	local lookup = runtime.singleLiveIndex or runtime.liveUnitIndex
	if units == nil or lookup == nil then return linear_unit_live(runtime, unit) end
	local index = lookup[unit]
	if index ~= nil then return units[index] == unit end
	local watched = runtime.singleLiveWanted or runtime.liveUnitWanted
	if watched and watched[unit] then return false end
	-- Newly attached/discovered units were not in this callback's watched set.
	-- Check the fresh array, never treat an unindexed pointer as alive by default.
	return linear_unit_live(runtime, unit)
end
session_unit_live = indexed_unit_live

local api = { UPSTREAM_VERSION = "2.1.45", UPSTREAM_COMMIT = "b78e63ebc77017aa6c70d52e0bf9e06e46360b92",
	is_rig = isSingleRig, schedule_budget = schedule_budget, motion_follows = motion_follows, member = indexed_unit_live }

function api.active_only(runtime)
	if runtime.options.singleMainline == false or #(runtime.sessions or {}) == 0 then return false end
	for _, session in ipairs(runtime.sessions) do if session.singleMainline ~= true then return false end end
	return true
end

function api.refresh_inventory(runtime)
	local prior = runtime.singleLiveIndex or {}
	runtime.singleLiveIndex, runtime.singleLiveWanted = nil, nil
	if runtime.singleState == nil or runtime.options.singleMainline == false or runtime.liveUnits == nil then return end
	local watched, active = {}, false
	for _, session in ipairs(runtime.sessions or {}) do
		if session.singleMainline then watched[session.unit], active = true, true end
	end
	if not active then return end
	for _, avatar in ipairs(runtime.avatars or {}) do watched[avatar.unit] = true end
	local lookup, shifted, remaining = {}, {}, 0
	for unit in pairs(watched) do
		local index = prior[unit]
		if index ~= nil and runtime.liveUnits[index] == unit then lookup[unit] = index
		else shifted[unit], remaining = true, remaining + 1 end
	end
	if remaining > 0 then
		for index = 1, #runtime.liveUnits do
			local unit = runtime.liveUnits[index]
			if shifted[unit] then
				lookup[unit], shifted[unit], remaining = index, nil, remaining - 1
				if remaining == 0 then break end
			end
		end
	end
	-- Some bindings can enumerate fresh userdata wrappers with native __eq but
	-- different table keys. Preserve master's equality-based membership check for
	-- unmatched handles rather than mistaking a hash-key miss for a dead Unit.
	if remaining > 0 then
		for unit in pairs(shifted) do
			for index = 1, #runtime.liveUnits do
				if runtime.liveUnits[index] == unit then lookup[unit] = index; break end
			end
		end
	end
	runtime.singleLiveIndex, runtime.singleLiveWanted = lookup, watched
end

-- A private scheduling projection avoids changing dual avatar order, stride or
-- mutable session fields. Only the original single session reaches Compat.update.
local function project(runtime, avatars)
	local single = runtime.singleState
	if single == nil then
		single = { matches = setmetatable({}, { __mode = "k" }),
			attemptAt = setmetatable({}, { __mode = "k" }), wrappers = {} }
		runtime.singleState = single
	end
	single.options, single.logger = runtime.options, runtime.logger
	single.frame, single.dt, single.world = runtime.frame, runtime.dt, runtime.world
	single.cache, single.liveUnits, single.liveUnitIndex = runtime.cache, runtime.liveUnits, runtime.singleLiveIndex
	single.liveUnitWanted = runtime.singleLiveWanted
	local current = {}
	for _, avatar in ipairs(avatars or runtime.avatars or {}) do current[avatar.unit] = avatar end
	local owned, seen = {}, {}
	for _, avatar in ipairs(single.avatars or {}) do
		if current[avatar.unit] then owned[#owned + 1] = avatar; seen[avatar.unit] = true end
	end
	for _, avatar in ipairs(avatars or runtime.avatars or {}) do
		if not seen[avatar.unit] then
			local clone = {}; for key, value in pairs(avatar) do clone[key] = value end
			owned[#owned + 1] = clone
		end
	end
	for index, avatar in ipairs(owned) do
		local fresh = current[avatar.unit]
		avatar.nodes, avatar.tag, avatar.order = fresh.nodes, fresh.tag or avatar.tag, index
	end
	single.avatars = owned
	if single.selfUnit ~= nil and current[single.selfUnit] == nil then
		single.selfUnit, single.fpLockUnit, single.fpLockFrames = nil, nil, 0
	end
	local present, wrappers = {}, {}
	for _, session in ipairs(runtime.sessions or {}) do
		if session.singleMainline then
			local view = single.wrappers[session]
			if view == nil then view = setmetatable({ source = session }, { __index = session }) end
			view.owner, view.ownerTag = session.owner, session.ownerTag
			view.ownerOrder = session.singleOwnerOrder or session.ownerOrder
			present[view], wrappers[session] = true, view
		end
	end
	local sessions, added = {}, {}
	for _, view in ipairs(single.sessions or {}) do
		if present[view] then sessions[#sessions + 1] = view; added[view] = true end
	end
	for _, session in ipairs(runtime.sessions or {}) do
		local view = wrappers[session]
		if view ~= nil and not added[view] then sessions[#sessions + 1] = view end
	end
	single.wrappers, single.sessions = wrappers, sessions
	return single
end

local function retry_at(single, at)
	if single.negativeRetryAt == nil or at < single.negativeRetryAt then single.negativeRetryAt = at end
end

function api.prepare(runtime, avatars, candidates, carriers)
	if runtime.options.singleMainline == false then return nil end
	local anySingle, onlySingle = false, #carriers > 0
	for _, carrier in ipairs(carriers) do
		if isSingleRig(carrier.rig) then anySingle = true else onlySingle = false end
	end
	if not anySingle then return nil end
	local single = project(runtime, avatars)
	local same = single.carrierEpoch ~= nil and #single.carrierEpoch == #carriers
	if same then
		for index, carrier in ipairs(carriers) do
			local prior = single.carrierEpoch[index]
			if prior.rig ~= carrier.rig or prior.path ~= carrier.path then same = false; break end
		end
	end
	if not same then
		single.matches, single.attemptAt = setmetatable({}, { __mode = "k" }), setmetatable({}, { __mode = "k" })
		single.carrierEpoch = {}
		ConsumerRuntime.reset(runtime)
		for index, carrier in ipairs(carriers) do single.carrierEpoch[index] = { rig = carrier.rig, path = carrier.path } end
	end
	single.onlyCarriers, single.negativeRetryAt = onlySingle, nil
	single.lastDiscoverFrame = runtime.frame
	-- As in master, sample on discovery as well as the persistent identity watch.
	for _, avatar in ipairs(avatars) do motion_sample(single, S, avatar.unit) end
	for _, candidate in ipairs(candidates) do motion_sample(single, S, candidate.unit) end
	return single
end

function api.retry(single, at) retry_at(single, at) end

function api.next_reconcile(runtime, proposed)
	local single = runtime.singleState
	local at = single and single.negativeRetryAt
	if at ~= nil and (proposed == nil or at < proposed) then proposed = at end
	if single then single.negativeRetryAt = nil end
	return proposed
end

function api.filter_plan(runtime, plan)
	local single = runtime.singleState
	if single == nil or runtime.options.singleMainline == false then return plan end
	local candidates, acceptedByOwner = {}, {}
	for _, entry in ipairs(plan) do if entry.singleMainline then candidates[#candidates + 1] = entry end end
	-- Cached already-attached units must count as evidence, too. They need not be
	-- reattached merely to keep an un-following preview from the nearest fallback.
	for _, view in ipairs(single.sessions or {}) do
		if motion_follows(single, view.owner, view.unit) ~= false and view.owner ~= nil then
			acceptedByOwner[view.owner] = (acceptedByOwner[view.owner] or 0) + 1
		end
	end
	table.sort(candidates, function(a, b)
		local da, db = a.distance2 or math.huge, b.distance2 or math.huge
		if da ~= db then return da < db end
		return tostring(a.tag) < tostring(b.tag)
	end)
	local rejected = {}
	for _, entry in ipairs(candidates) do
		local owner = entry.owner and entry.owner.unit
		local accept = motion_follows(single, owner, entry.unit) ~= false
		rejected[entry] = not accept
		if accept and owner ~= nil then acceptedByOwner[owner] = (acceptedByOwner[owner] or 0) + 1 end
	end
	-- Exact master fallback: never leave an owner with zero accepted units solely
	-- because motion data rejected every candidate. No arbitrary per-unit cap.
	for _, entry in ipairs(candidates) do
		local owner = entry.owner and entry.owner.unit
		if owner ~= nil and (acceptedByOwner[owner] or 0) == 0 and rejected[entry] then
			rejected[entry], acceptedByOwner[owner] = false, 1
		end
	end
	local kept = {}
	for _, entry in ipairs(plan) do if rejected[entry] ~= true then kept[#kept + 1] = entry end end
	return kept
end

function api.invalidate(runtime, session)
	local single = runtime.singleState
	if single ~= nil and session.singleMainline then
		single.matches[session.unit], single.attemptAt[session.unit] = nil, nil
		single.wrappers[session] = nil
	end
end

-- Read-only first-person entry proof, then an immutable per-Unit identity latch.
-- A retained FP graph, FOV, camera-nearest avatar or mouse button is NOT proof.
local FP_RESOURCE = "content/fac_helldivers/fp_cha_avatar/fp_cha_avatar"
local FP_RESOURCE_ID = "d0cf4d493ca08bed"
local function ads_pose(fn, ...)
 if type(fn) ~= "function" or not S.Matrix4x4 or type(S.Matrix4x4.to_elements) ~= "function" then return nil end
 local ok, values = pcall(function(...) return {S.Matrix4x4.to_elements(fn(...))} end, ...)
 if not ok or #values ~= 12 then return nil end
 for _, value in ipairs(values) do if type(value) ~= "number" or value ~= value or math.abs(value) >= 1e12 then return nil end end
 return values
end
local function ads_camera_match(a, b)
 local dx,dy,dz=a[10]-b[10],a[11]-b[11],a[12]-b[12]
 if dx*dx+dy*dy+dz*dz > .08*.08 then return false end
 -- Same entry proof as production native_first_person_guard 1.0.0: camera
 -- positions agree; bone/view bases may use different native camera axes.
 return true
end
local function ads_named_node(unit, name, count)
 if type(Compat.resolve_named_node)=="function" then return Compat.resolve_named_node(S, unit, name, count) end
 if try(S.Unit.has_node, unit, name)==true then
  local node=try(S.Unit.node, unit, name)
  if type(node)=="number" and node>=1 and node<=count then return node end
 end
 return nil
end
local function ads_first_person_view(runtime)
 if not S.World or type(S.World.units_by_resource)~="function" or not S.Unit or type(S.Unit.world_pose)~="function" then return nil end
 local worlds=try(S.Application.worlds)
 if type(worlds)~="table" or #worlds>64 then return nil end
 local main=ads_pose(S.World.debug_camera_pose,runtime.world)
 if main==nil then return nil end
 local seen={}
 for _,world in ipairs(worlds) do
  local graphs=try(S.World.units_by_resource,world,FP_RESOURCE)
  if type(graphs)=="table" and #graphs<=8 then
   for _,unit in ipairs(graphs) do
    if not seen[unit] and Compat.unit_alive(S,unit)==true then
     seen[unit]=true
     local resource=try(S.Unit.resource_name,unit)
     local hex=resource and S.IdString64 and try(S.IdString64.to_hex,resource)
     if type(hex)=="string" and hex:lower():gsub("^0x","")==FP_RESOURCE_ID then
      local count=try(S.Unit.num_scene_graph_items,unit)
      -- Only READ the verified native root/camera prefix. Appended Source outputs
      -- do not authorize any writes or borrow a different model's bind/profile.
      if type(count)=="number" and count>=63 and ads_named_node(unit,"root",count)==5 and ads_named_node(unit,"camera",count)==51 then
       if Compat.unit_alive(S,unit)==true then
        local camera=ads_pose(S.Unit.world_pose,unit,51)
        if camera and ads_camera_match(main,camera) then return main end
       end
      end
     end
    end
   end
  end
 end
 return nil
end
local function ads_note(runtime, status, unit, checks)
 local message=string.format("[physbone][ADS_ONCE] variant=A status=%s instance=%s checks=%d frame=%d\n",status,tostring(unit or "-"),checks or 0,runtime.frame or 0)
 runtime.logger("%s",message:gsub("\n$",""))
 if runtime.options.log==false then return end
 if runtime.adsLog==nil and not runtime.adsLogFailed then
  local path=runtime.options.logPath
  if type(path)=="string" then path=path:gsub("[^/\\]+$","hd2physbone_A_identity.log") end
  if path then local ok,handle=pcall(io.open,path,"w");if ok and handle then runtime.adsLog=handle else runtime.adsLogFailed=true end end
 end
 if runtime.adsLog and (runtime.adsLogBytes or 0)<32768 then
  runtime.adsLog:write(os.date("%Y-%m-%d %H:%M:%S")," ",message);runtime.adsLog:flush()
  runtime.adsLogBytes=(runtime.adsLogBytes or 0)+#message+21
 end
end
function api.sample_ads_once(runtime, single)
 local proof=single.adsIdentity
 if proof==nil then proof={checks=0,probes=0,consecutive=0};single.adsIdentity=proof;single.physicsEpoch=(single.physicsEpoch or 0)+1 end
 -- Single.project/prune already checks fresh avatar membership. This is only a
 -- numeric/instance latch check: no camera, FP graph, node or position queries.
 if proof.owner~=nil and single.selfUnit==proof.owner then return true end
 if proof.owner~=nil then
  ads_note(runtime,"WAIT_AIM_NEW_INSTANCE",nil,proof.checks)
  proof.owner,proof.candidate,proof.lastProbe,proof.consecutive=nil,nil,nil,0
  single.physicsEpoch=(single.physicsEpoch or 0)+1
 end
 local every=math.max(1,math.floor(runtime.options.firstPersonIdentityPollFrames or 20))
 if proof.lastProbe and runtime.frame-proof.lastProbe<every then return false end
 proof.lastProbe=runtime.frame;proof.probes=proof.probes+1
 local camera=ads_first_person_view(runtime)
 if camera==nil then proof.candidate,proof.consecutive=nil,0;return false end
 -- Owner identification happens ONLY after the real FP camera matched the main
 -- view. Require a UNIQUE current TP avatar, not nearest rank/name/resource.
 proof.checks=proof.checks+1
 local selected,matched=nil,0
 for _,avatar in ipairs(single.avatars or {}) do
  if Compat.unit_alive(S,avatar.unit)==true then
   local x,y=readVector(S,try(S.Unit.world_position,avatar.unit,1))
   if x~=nil then local dx,dy=x-camera[10],y-camera[11]
    if dx*dx+dy*dy<.35*.35 then selected,matched=avatar.unit,matched+1 end
   end
  end
 end
 if matched~=1 then proof.candidate,proof.consecutive=nil,0;return false end
 if proof.candidate==selected then proof.consecutive=proof.consecutive+1 else proof.candidate,proof.consecutive=selected,1 end
 if proof.consecutive<3 then return false end
 proof.owner,single.selfUnit=selected,selected
 single.physicsEpoch=(single.physicsEpoch or 0)+1
 redistribute(S,single,"首次第一人称瞄准确认（仅一次）",selected)
 ads_note(runtime,"LOCKED_NO_MORE_ID_CHECKS",selected,proof.checks)
 return true
end

function api.tick(runtime)
	if runtime.options.singleMainline == false then return end
	local haveSingle = false
	for _, session in ipairs(runtime.sessions or {}) do if session.singleMainline then haveSingle = true; break end end
	if not haveSingle then return end
	local single = project(runtime)
	-- Camera retry uses cache.frame. It must advance even when the single
	-- roster is stable and discovery no longer runs every 60 frames.
	single.cache.frame = runtime.frame
	local formal = runtime.options.singleFormalPolicy ~= false
	if formal then
		local scene,changed=RemotePhysics.scene(runtime,single)
		if changed then ads_note(runtime,scene=="ship" and "SHIP_VRD_ENABLED" or (scene=="mission" and "MISSION_WAIT_AIM" or "UNKNOWN_SCENE_RESTRICTED"),nil,0) end
		if scene~="ship" then api.sample_ads_once(runtime, single) end
		if scene=="ship" or RemotePhysics.DEFAULT == "remote-no-vrd" then refresh_avatar_distances(S, single) end
	else refresh_avatar_distances(S, single) end
	-- Existing preview/follower cleanup is NOT a local-player identity check.
	-- Preserve the accepted motion-based removal of stationary ship previews.
	local ok, err = pcall(identity_watch, S, single)
	if not ok and not single.identityErrorLogged then
		single.identityErrorLogged = true
		runtime.logger("[physbone][单骨架] 主线身份监视失败：%s", tostring(err))
	end
	if not formal then fp_lock_watch(S, single); scheduler_watch(S, single, runtime.dt) end
	local primaryChains, nearChains, farChains = 0, 0, 0
	local budget = runtime.options.maxChainsPerFrame or 600
	local nearMetres = sched_settings(single).metres
	local nearLimit2 = nearMetres * nearMetres
	local keep = {}
	for index, view in ipairs(single.sessions) do
		keep[view.source] = true
		local chains = #(view.sessions or {})
		if view.consumerMode == "drivers" and view.evaluateDrivers ~= false then chains = #(view.drivers or {}) end
		if formal and single.sceneMode~="ship" and RemotePhysics.DEFAULT == "self-only" and view.owner ~= single.selfUnit then
			-- Excluded remote/unknown chains are retained for lifecycle, not budget.
		elseif (view.ownerOrder or 99) <= 1 or runtime.cache.cameraUsable ~= true then primaryChains = primaryChains + chains
		elseif owner_distance_sq(single, view) <= nearLimit2 then nearChains = nearChains + chains
		else farChains = farChains + chains end
	end
	local nearStride, farStride = schedule_budget(primaryChains, nearChains, farChains, budget)
	if single.nearStride ~= nearStride or single.farStride ~= farStride then
		single.nearStride, single.farStride = nearStride, farStride
		runtime.logger("[physbone][单骨架主线预算] 自己 %d 链/帧（不分帧）；%.0f m 内 %d 链/步长 %d；远处 %d 链/步长 %d；预算 %d",
			primaryChains, nearMetres, nearChains, nearStride, farChains, farStride, budget)
	end
	for index, view in ipairs(single.sessions) do
		local source = view.source
		source.owner, source.ownerTag, source.singleOwnerOrder = view.owner, view.ownerTag, view.ownerOrder
		if formal then source.ownerOrder = view.ownerOrder; RemotePhysics.bind(single, source) end
		local stride = 1
		if (view.ownerOrder or 99) > 1 and runtime.cache.cameraUsable == true then
			stride = owner_distance_sq(single, view) <= nearLimit2 and nearStride or farStride
		end
		source.singleStride, source.singleDispatchIndex = stride, index
		source.singleDue = stride <= 1 or ((runtime.frame + index) % stride) == 0
		if single.driveHoldUntil ~= nil and runtime.frame < single.driveHoldUntil then source.singleDue = false end
		if source.singleRemotePhysicsExcluded == true then source.singleDue, source.pendingDt = false, 0 end
	end
	local survivors = {}
	for _, session in ipairs(runtime.sessions) do
		if not session.singleMainline or keep[session] then survivors[#survivors + 1] = session
		else single.wrappers[session] = nil end
	end
	runtime.sessions = survivors
	runtime.singlePrimaryChains, runtime.singleNearChains, runtime.singleFarChains = primaryChains, nearChains, farChains
end

return api
end)()

M.SINGLE_UPSTREAM_VERSION = Single.UPSTREAM_VERSION
M.SINGLE_UPSTREAM_COMMIT = Single.UPSTREAM_COMMIT
M.LEGACY_SKELETON_VERSION = "2.3.6"
-- Policy hooks for isolated tests; never install another render callback.
M.single_policy = Single

-- Formal single-skeleton policies: ship VRD bypass, mission one-time ADS identity.
-- Formal single-skeleton policies: ship VRD bypass, mission one-time ADS identity.
RemotePhysics={REVISION="ship-vrd-mission-ads-v2",DEFAULT="self-only"}
-- Positive ship/mission classification. Do not infer ship just from "not aiming".
function RemotePhysics.scene(runtime,single)
 local context=runtime.options.sceneContext
 local main=runtime.world
 local mission,worldId
 if type(context)=="table" then
  if type(context.world)=="function" then main=try(context.world) end
  if type(context.in_mission)=="function" then mission=try(context.in_mission) end
  if type(context.world_id)=="function" then worldId=try(context.world_id) end
 end
 local cache=single.sceneCache or {};single.sceneCache=cache
 local mode=cache.mode
 local frame=runtime.frame or 0
 if cache.world~=main or cache.mission~=mission or cache.worldId~=worldId or not cache.frame or frame<cache.frame or frame-cache.frame>=30 then
  local levels
  if main~=nil then
   if S.World and type(S.World.num_levels)=="function" then levels=try(S.World.num_levels,main) end
   -- Chef API revision is a NUMBER. Its documented guarded native helper is call.
   if levels==nil and type(context)=="table" and type(context.call)=="function" then levels=try(context.call,"World.num_levels",main) end
  end
  mode="unknown"
  if main~=nil and type(levels)=="number" and levels==math.floor(levels) then
   if levels>10 then mode="mission" elseif levels==1 or levels==2 then mode="ship" end
  elseif main~=nil and mission==true then mode="mission"
  elseif main~=nil and type(context)=="table" and type(context.on_ship)=="function" and try(context.on_ship)==true then mode="ship"
  elseif main~=nil and mission==false and type(worldId)=="number" and worldId>0 and cache.missionSeenId~=worldId then
   -- Missing native level API: only a stable, newly classified non-mission from
   -- the loader may be a ship. A temporary mission "checking" false is UNKNOWN.
   mode="ship"
  end
  if mode=="mission" and worldId~=nil then cache.missionSeenId=worldId end
  cache.world,cache.worldId,cache.mission,cache.frame,cache.mode=main,worldId,mission,frame,mode
 end
 local changed=single.sceneMode~=mode
 if changed then
  single.sceneMode=mode
  single.physicsEpoch=(single.physicsEpoch or 0)+1
  -- A ship is never an ADS identity source. Scene transitions must not carry a
  -- ship-wide VRD bypass or a prior scene's learned owner into a new mission.
  single.selfUnit,single.adsIdentity,single.fpLockUnit,single.fpLockFrames=nil,nil,nil,0
 end
 return mode,changed
end

function RemotePhysics.bind(single,session)
 if session.singleMainline~=true or single.options.singleFormalPolicy==false then return end
 local epoch=single.physicsEpoch or 0
 if session.singleFormalEpoch==epoch and session.singleFormalOwner==session.owner then return end
 local ship=single.sceneMode=="ship"
 local own=single.selfUnit~=nil and session.owner==single.selfUnit
 if session.singleRemoteBaseEvaluateDrivers==nil then session.singleRemoteBaseEvaluateDrivers=session.evaluateDrivers~=false end
 local springOff=not ship and RemotePhysics.DEFAULT=="self-only" and not own
 local vrdOff=not ship and not own
 if Compat.single_remote_policy_transition then
  local ok,why=pcall(Compat.single_remote_policy_transition,session,springOff and vrdOff,vrdOff)
  if not ok and not session.singleFormalErrorLogged then session.singleFormalErrorLogged=true;single.logger("[physbone][FORMAL] transition-error=%s",tostring(why)) end
 end
 session.singleRemotePhysicsExcluded=springOff and vrdOff
 session.singleRemoteVrdExcluded=vrdOff
 session.singleRemoteIsSelf,session.singleRemoteIsRemote=own,not own
 session.evaluateDrivers=session.singleRemoteBaseEvaluateDrivers and not vrdOff
 session.singleFormalEpoch,session.singleFormalOwner=epoch,session.owner
 if session.singleRemotePhysicsExcluded then session.pendingDt,session.singleDue=0,false end
end
function RemotePhysics.frame(runtime)
 runtime.remoteFrameDriverWrites,runtime.selfFrameDriverWrites=0,0
end
M.FORMAL_PHYSICS_VARIANT="A"
M.REMOTE_PHYSICS_POLICY=RemotePhysics.DEFAULT
M.IDENTITY_POLICY="first-person-aim-once-v1"
M.SCENE_POLICY=RemotePhysics.REVISION
M.remote_physics_policy=RemotePhysics


local function tryAttach(runtime)
	local options, cache = runtime.options, runtime.cache
	local frame = runtime.frame
	cache.frame = frame
	local world, units, avatars, armorList, reason = discover(S, cache, options, runtime.logger)
	if world == nil or armorList == nil or avatars == nil then
		note_wait(runtime, reason or "发现目标失败（未给出原因）")
		return false
	end
	local armor = armorList[1]

	local nodeCount = try(S.Unit.num_scene_graph_items, armor.unit)
	if type(nodeCount) ~= "number" or nodeCount < 10 then
		note_wait(runtime, "主件节点数异常", tostring(nodeCount))
		return false
	end
	local sample = readVector(S, try(S.Unit.world_position, armor.unit, 1))
	if sample == nil then
		note_wait(runtime, "主件世界坐标读不到")
		return false
	end

	-- 两次采样一致 ⇒ 加载/传送/换装已经结束。间隔太短容易在动画还没落位时就 attach。
	-- ⚠️ 采样一旦记下就**不要每帧覆盖**，否则 (frame - previous.frame) 永远是 1，永远等不到。
	-- 这一步是正常路径（10 帧内必然过去），所以不记等待原因，免得盖掉真正的卡点。
	if cache.readyWorld ~= world then
		local settleFrames = options.settleFrames or 10
		local previous = cache.settle
		if previous == nil or previous.nodes ~= nodeCount or previous.unit ~= armor.unit then
			cache.settle = { x = sample, frame = frame, nodes = nodeCount, unit = armor.unit }
			return false
		end
		if (frame - previous.frame) < settleFrames then return false end
		cache.settle, cache.readyWorld = nil, world
	end
	runtime.world = world

	-- 逐 unit 选容器：每个 unit 只认"全命中"的那一份，没有就跳过（宁可不驱动也不写错参数）。
	-- `options.carriers` 可以直接注入（测试 / 由管理器把容器内容传进来时用），省掉扫盘。
	local carriers = runtime.carriers or {}
	if #carriers == 0 and options.carriers ~= nil then
		carriers = options.carriers
		runtime.carriers = carriers
	end
	if #carriers == 0 then carriers = loadCarriers(S, cache, options, runtime.logger); runtime.carriers = carriers end
	local allowPartial = options.allowPartial == true
	-- 只挂**离它那个玩家**近的护甲件。为什么必须过滤：阵亡后尸体留在原地、unit 一直活着，
	-- 而复活点常在别处 ⇒ 不过滤的话会把尸体也一起挂上（既浪费，也让"给尸体关物理"落空）。
	-- 注意距离是"到**它自己那个玩家**"的：队友的护甲离队友近，不该因为离我远就被丢掉。
	local maxDist = options.maxArmorDistance == nil and 5.0 or options.maxArmorDistance
	local maxDist2 = maxDist > 0 and (maxDist * maxDist) or nil
	local nearCandidates, farCount = {}, 0
	for _, candidate in ipairs(armorList) do
		if maxDist2 == nil or candidate.distance == nil or candidate.distance <= maxDist2 then
			nearCandidates[#nearCandidates + 1] = candidate
		else
			farCount = farCount + 1
		end
	end
	if farCount > 0 then
		local last = runtime.farLog
		if last == nil or last.count ~= farCount or frame - last.frame >= 300 then
			runtime.farLog = { count = farCount, frame = frame }
			runtime.logger("[physbone] 跳过 %d 个离它所属玩家超过 %.1f m 的护甲件（尸体/人台）", farCount, maxDist)
		end
	end
	-- A quota bounds work, not who can ever receive physics. Skip existing sessions
	-- and rotate an integer cursor over every candidate (upstream 5e1dbc1/4236f42).
	-- No negative result is permanent: late-ready layouts are rescanned periodically.
	-- ① 先收掉"主人已经不在了"的会话（玩家退出 / 阵亡后尸体不再算玩家）。
	--
	-- 这一步取代了老版本那个 `playerChanged`：老版本把"出现一个新的 avatar 候选"当成
	-- "玩家换人了"，于是**队友一进房间就把我的会话全丢掉、重挂到队友身上**。
	-- 现在每个会话都记着自己的主人，主人还在就一律不动。
	local aliveOwners = {}
	for index = 1, #avatars do aliveOwners[avatars[index].unit] = true end
	local kept, released = {}, 0
	for _, session in ipairs(runtime.sessions or {}) do
		if session.owner ~= nil and aliveOwners[session.owner] == nil then
			released = released + 1
			if Compat.unit_alive(S, session.unit) then
				local ok, restored = pcall(Compat.release, session)
				runtime.logger("[physbone][玩家] 主人已不在，释放 unit=%s（%s）%s",
					tostring(session.unitTag or "?"), tostring(session.ownerTag or "?"),
					ok and ("已交还 " .. tostring(restored) .. " 节基准姿态") or "交还失败")
			end
		else
			kept[#kept + 1] = session
		end
	end
	if released > 0 then
		runtime.sessions = kept
		runtime.logger("[physbone][玩家] 释放了 %d 个会话（主人已离开/阵亡），剩 %d 个", released, #kept)
	end

	-- ② 再补上还没挂的 unit。已有会话的 unit 直接跳过 —— 这是增量的关键：
	--    队友加入时，我自己的会话一个字节都不该被碰。
	local attachedUnits = {}
	for _, session in ipairs(runtime.sessions or {}) do attachedUnits[session.unit] = true end

	local single = Single.prepare(runtime, avatars, nearCandidates, carriers)
	local pureSingle = single ~= nil and single.onlyCarriers
	local scoreBudget = options.scoreUnitsPerFrame or options.maxScoredCandidates or (pureSingle and 2 or 8)
	if not pureSingle and type(options.maxUnits) == "number" and options.maxUnits > 0 then
		scoreBudget = math.min(scoreBudget, options.maxUnits)
	end
	scoreBudget = math.max(1, math.floor(scoreBudget))
	local retryFrames = math.max(1, math.floor(options.negativeRetryFrames or 30))
	local plan, bestScored, scoredNow, deferred = {}, nil, 0, 0
	local candidateCount = #nearCandidates
	local cursor = candidateCount > 0 and ((runtime.fillCursor or 0) % candidateCount) or 0
	local nextCursor = cursor
	for step = 0, candidateCount - 1 do
		local index = ((cursor + step) % candidateCount) + 1
		local candidate = nearCandidates[index]
		local match = single and single.matches[candidate.unit]
		if match ~= nil and match.nodes ~= candidate.nodes then
			single.matches[candidate.unit], single.attemptAt[candidate.unit], match = nil, nil, nil
		end
		local needsScore = not attachedUnits[candidate.unit] and match == nil
		if needsScore and pureSingle then
			local last = single.attemptAt[candidate.unit]
			if last ~= nil and frame - last < retryFrames then
				Single.retry(single, last + retryFrames)
				needsScore = false
			end
		end
		if needsScore then
			if scoredNow >= scoreBudget then
				deferred = deferred + 1
			else
				scoredNow = scoredNow + 1
				nextCursor = index
				local best, scored = Compat.select_rig(S, { candidate.unit }, carriers)
				local singleMatch = best ~= nil and options.singleMainline ~= false and isSingleRig(best.rig)
				local usable = best ~= nil and (best.full or allowPartial or (singleMatch and (best.score or 0) >= 1))
				if usable then
					match = { rig = best.rig, path = best.path, nodes = candidate.nodes, singleMainline = singleMatch or nil }
					if singleMatch then single.matches[candidate.unit] = match end
				else
					if pureSingle then single.attemptAt[candidate.unit] = frame; Single.retry(single, frame + retryFrames) end
					if scored ~= nil and scored[1] ~= nil then
						if bestScored == nil or scored[1].score > bestScored.score then bestScored = scored[1] end
					end
				end
			end
		end
		if match ~= nil then
			plan[#plan + 1] = {
				unit = candidate.unit, rig = match.rig, path = match.path, mg = candidate.mg,
				tag = unit_tag(S, candidate.unit), owner = candidate.owner, distance2 = candidate.distance,
				singleMainline = match.singleMainline,
			}
		end
	end
	runtime.fillCursor, runtime.fillPending = nextCursor, deferred > 0
	runtime.lastScored, runtime.lastDeferred = scoredNow, deferred
	plan = Single.filter_plan(runtime, plan)
	-- Refresh owner priority even for already attached parts; same-resource Units
	-- belonging to different players must never share a session/state object.
	local ownersByUnit = {}
	for _, candidate in ipairs(nearCandidates) do ownersByUnit[candidate.unit] = candidate.owner end
	for _, session in ipairs(runtime.sessions or {}) do
		local owner = ownersByUnit[session.unit]
		if owner ~= nil then
			session.owner, session.ownerOrder = owner.unit, owner.order
		end
	end
	if #plan == 0 and #(runtime.sessions or {}) == 0 then
		-- Orphan cleanup can leave an empty array while respawn models are still
		-- loading. Empty is WAITING, never an active zero-chain driver: otherwise
		-- both reconciliation and the waiting poll are bypassed forever.
		runtime.sessions = nil
		runtime.rearmAt = frame + 1
		local detail
		if #carriers == 0 then detail = "没有物理容器可匹配"
		elseif bestScored ~= nil then
			detail = string.format("本拍打分 %d 件、延后 %d 件；最高命中 %d/%d 根骨（%s）",
				scoredNow, deferred, bestScored.score, bestScored.total, tostring(bestScored.path))
		else detail = string.format("%d 个候选 unit × %d 份容器，全部 0 命中", #nearCandidates, #carriers) end
		note_wait(runtime, "没有 unit 命中任何物理容器", detail)
		return false
	end

	table.sort(plan, function(a, b)
		local oa = a.owner ~= nil and a.owner.order or 99
		local ob = b.owner ~= nil and b.owner.order or 99
		if oa ~= ob then return oa < ob end
		if a.mg ~= b.mg then return a.mg end
		return false
	end)


	local attachOptions = {
		-- Original-format or unverified containers never own VRD; springs remain active.
		vrdSkeletonOnly = true,
		logger = runtime.logger,
		world = world,
		strictIdentity = options.strictIdentity == true,
		fastWrite = options.fastWrite ~= false,
		-- `solver` 只用于那条**已废弃的角度振子核**（`"angle"`，仅 A/B）；
		-- `bendBlend` 控制曲率扩散（nil ⇒ 构建时默认 1.0）。
		solver = options.solver,
		bendBlend = options.bendBlend,
	}
	local attached, emptyUnits, already = 0, 0, 0
	for index = 1, #plan do
		local entry = plan[index]
		if attachedUnits[entry.unit] then
			already = already + 1
		elseif Compat.unit_alive(S, entry.unit) then
			if entry.owner ~= nil and Compat.shared_physics_nodes ~= nil then
				local checked = runtime.physicsOwnerChecked or setmetatable({}, { __mode = "k" })
				runtime.physicsOwnerChecked = checked
				if checked[entry.owner.unit] ~= entry.rig then
					checked[entry.owner.unit] = entry.rig
					local shared = Compat.shared_physics_nodes(S, entry.owner.unit, entry.rig)
					if shared > 0 then
						runtime.logger("[physbone][绑定冲突] avatar 含 %d/%d 根同名物理骨，动画同步可能覆盖物理；请更新配套骨架动画包", shared, #entry.rig.bones)
					else
						runtime.logger("[physbone][绑定检查] avatar 同名物理骨 0/%d，物理节点可独立驱动", #entry.rig.bones)
					end
				end
			end
			local session = Compat.attach(S, entry.unit, entry.rig, attachOptions)
			session.evaluateDrivers = not (runtime.options ~= nil and runtime.options.evaluateDrivers == true)
			session.rigSource = entry.path
			session.singleMainline = entry.singleMainline
			session.unitTag = entry.tag
			session.attachFrame = frame
			session.owner = entry.owner ~= nil and entry.owner.unit or nil
			session.ownerOrder = entry.owner ~= nil and entry.owner.order or 99
			if entry.owner ~= nil then
				-- 实例名只在这里读一次：unit 一旦销毁再读就是 AV，而日志里全是 `?` 等于没有信息。
				entry.owner.tag = entry.owner.tag or unit_tag(S, entry.owner.unit)
			end
			session.ownerTag = entry.owner ~= nil and entry.owner.tag or nil
			ConsumerRuntime.bind(runtime, session)
			if #session.sessions > 0 or ConsumerRuntime.legitimate(session) then
				if session.singleMainline and not runtime.singlePolicyLogged then
					runtime.singlePolicyLogged = true
					runtime.logger("[physbone][单骨架主线] policy=master-b78e63e/2.1.45；compat=%s；双骨架调度保留2.3.6；完整bind/已验收修正不变", tostring(Compat.version or "?"))
				end
				if runtime.sessions == nil then runtime.sessions = {} end
				runtime.sessions[#runtime.sessions + 1] = session
				attached = attached + 1
			else
				-- attach 走完了却一条链都没产出：容器骨名和这个 unit 的节点名对不上，
				-- 或者锚点全缺。以前这里完全静默，等于"挂上了"和"挂出 0 条"从日志上看一样。
				if entry.singleMainline and runtime.singleState then
					runtime.singleState.matches[entry.unit] = nil
					runtime.singleState.attemptAt[entry.unit] = frame
					Single.retry(runtime.singleState, frame + retryFrames)
				end
				emptyUnits = emptyUnits + 1
				runtime.logger("[physbone][失败] unit=%s 挂载完成但产出 0 条链（容器 %s）",
					entry.tag, tostring(entry.path))
			end
		else
			runtime.logger("[physbone][失败] unit=%s 在挂载前一刻已销毁（跳过）", tostring(entry.tag))
		end
	end
	if (runtime.sessions == nil or #runtime.sessions == 0) then
		note_wait(runtime, "attach 没有产出任何链", string.format("%d 个 unit 通过容器匹配、%d 个产出 0 条链", #plan, emptyUnits))
		return false
	end

	-- 记下"这次场上有哪些玩家"。下一拍比对它的**实例同一性**（userdata，不是 debug_name：
	-- 实测那个 id 是按资源算的，拿它比"是不是同一个人"永远为真）。
	runtime.avatars = avatars
	runtime.liveUnits = units
	local first = avatars[1]
	runtime.avatar = first.unit
	runtime.avatarTag = first.tag
	runtime.attachedFrame = frame
	runtime.reArm = 0
	runtime.rearmAt = nil
	runtime.waitReason, runtime.waitRepeat = nil, nil
	if attached > 0 then runtime.zeroFrames = 0 end

	local chains, tags = 0, {}
	local perOwner = {}
	for _, session in ipairs(runtime.sessions) do
		chains = chains + #session.sessions
		tags[#tags + 1] = tostring(session.unitTag or "?")
		local key = session.ownerOrder or 99
		perOwner[key] = (perOwner[key] or 0) + 1
	end
	local ownerText = {}
	for _, order in ipairs({ 1, 2, 3, 4, 99 }) do
		if perOwner[order] ~= nil then ownerText[#ownerText + 1] = string.format("玩家%d=%d件", order, perOwner[order]) end
	end
	if attached > 0 or released > 0 then
		runtime.logger("[physbone] 已挂载 %d 个 unit / %d 条链（%d 份容器，玩家 %d 个%s）；本次新挂 %d、已挂过 %d；unit=%s",
			#runtime.sessions, chains, #carriers, #avatars,
			#ownerText > 0 and ("：" .. table.concat(ownerText, " ")) or "",
			attached, already, table.concat(tags, ","))
	end
	return true
end

-- Pointer membership must precede ALL Unit API calls (upstream ab7382f/2c5c4db).
local function unitInInventory(runtime, unit)
	if runtime.liveUnits == nil then return true end
	for index = 1, #runtime.liveUnits do
		if runtime.liveUnits[index] == unit then return true end
	end
	return false
end

local function refreshLiveUnits(runtime)
	if runtime.world == nil then return "unavailable" end
	local worlds = try(S.Application.worlds)
	if type(worlds) ~= "table" then runtime.liveUnits = nil; return "unavailable" end
	local found = false
	for index = 1, #worlds do if worlds[index] == runtime.world then found = true; break end end
	if not found then runtime.liveUnits = nil; return "world-gone" end
	local units = try(S.World.units, runtime.world)
	if type(units) ~= "table" then runtime.liveUnits = nil; return "unavailable" end
	runtime.liveUnits = units
	Single.refresh_inventory(runtime)
	return "ok"
end

local function dropHandleGroup(runtime, reason, delay)
	runtime.logger("[physbone][LIFECYCLE] %s ⇒ 整组丢弃 %d 个会话 / %d 个 avatar（不碰旧句柄）",
		reason, #(runtime.sessions or {}), #(runtime.avatars or {}))
	runtime.sessions, runtime.avatars, runtime.avatar, runtime.avatarTag = nil, nil, nil, nil
	runtime.liveUnits, runtime.world, runtime.physicsOwnerChecked = nil, nil, nil
	runtime.cache, runtime.fillCursor, runtime.fillPending = {}, 0, nil
	runtime.reconcile, runtime.reArm, runtime.rearmAt = nil, 1, runtime.frame + (delay or 1)
	runtime.singleState, runtime.singleLiveIndex, runtime.singleLiveWanted, runtime.singlePolicyLogged = nil, nil, nil, nil
	runtime.remoteTestSingle, runtime.remoteTestConfirmedSelf, runtime.remoteTestStats = nil, nil, nil
	if type(Compat.clear_attach_cache) == "function" then Compat.clear_attach_cache() end
end

--- 丢掉失效会话。任何一个失效都意味着场景变了 ⇒ 必须重扫（不能"还剩几个就继续开"）。
--- 返回丢弃总数；dead / rebuilt 分开计数并各自落日志。
local function pruneSessions(runtime)
	local kept, dead, rebuilt = {}, 0, 0
	for _, session in ipairs(runtime.sessions or {}) do
		local health
		local live
		if session.singleMainline and runtime.options.singleMainline ~= false then
			live = Single.member(runtime, session.unit)
		else
			live = unitInInventory(runtime, session.unit)
		end
		if not live then
			health = "gone"
		else
			health = Compat.session_health(session, runtime.frame)
		end
		if health == "ok" then
			kept[#kept + 1] = session
		else
			session.dead = health
			Single.invalidate(runtime, session)
			if health == "rebuilt" then rebuilt = rebuilt + 1 else dead = dead + 1 end
			-- `unitTag` 是**挂载时**记下的实例名：unit 已经死了，现在再读 debug_name 就是 AV。
			-- 这条名字是 P0.5 判"换实例（军械库 churn）还是同实例被销毁"的唯一依据。
			runtime.logger("[physbone][LIFECYCLE] 会话失效（%s）：unit=%s 存活 %d 帧 链=%d%s",
				health, tostring(session.unitTag or "?"),
				runtime.frame - (session.attachFrame or runtime.frame),
				#(session.sessions or {}),
				session.deadReason ~= nil and (" 判死原因=" .. session.deadReason) or "")
		end
	end
	runtime.sessions = kept
	if dead > 0 or rebuilt > 0 then
		runtime.logger("[physbone] 丢弃 %d 个已销毁 / %d 个已重建，剩 %d 个会话",
			dead, rebuilt, #kept)
	end
	return dead + rebuilt
end

--- 便宜的"场上有哪些玩家"扫描，供驱动中定期比对。
--- 返回 avatar unit 列表；`nil` 表示"这次扫不了"（世界/单位列表取不到）。
---
--- 现在几乎免费：`World.units_by_resource` 一次调用就列出所有玩家 avatar，
--- 之后每个候选只要 1 次 `Unit.alive`。以前这里要遍历 2000+ unit、每个两次引擎调用，
--- 所以只能 1.2 秒跑一次 —— 队友中途加入要多等一拍才接得上。
local function scanAvatars(runtime)
	local world, units = pickWorld(S, runtime.cache)
	if world == nil or units == nil then return nil end
	local supportMg = "support_mg"
	local options = runtime.options or {}
	local list = findAvatars(S, world, units, #units, supportMg,
		options.minNodes or 90, options, runtime.cache)
	local found = {}
	for index = 1, #list do
		if Compat.unit_alive(S, list[index].unit) then found[#found + 1] = list[index].unit end
	end
	return found
end

--- 玩家人数有没有变化（有人加入 / 有人退出 / 阵亡后尸体不再算玩家）。
---
--- 取代了旧版的 `playerChanged`。旧版把"出现了一个新的 avatar 候选"当成"玩家换人了"，
--- 在多人局里这是致命的：队友一进房间，我们就把**自己的**会话全丢掉、重新挂到队友身上，
--- 而自己身上从此没有物理。现在"多出一个玩家"只是一个**新玩家**，谁的会话都不该动。
---
--- ⚠️ 判据用 **userdata 同一性**（`rawequal`），不是 `debug_name`：
--- 2026-11-01 实测：丢掉 7 个 unit 之后重新挂上的还是**同一批 `#ID[...]`**，
--- 说明那个 id 是按资源/描述符算的，不是按实例 —— 拿它比"是不是同一个人"永远为真。
---@return boolean changed 需要补挂/收尾
local function avatarSetChanged(runtime)
	local live = scanAvatars(runtime)
	if live == nil then return false end
	local known = runtime.avatars or {}
	local knownSet, liveSet = {}, {}
	for index = 1, #known do knownSet[known[index].unit] = true end
	local maxAvatars = (runtime.options or {}).maxAvatars or 4
	for index = 1, #live do
		local unit = live[index]
		liveSet[unit] = true
		if knownSet[unit] == nil then
			if #known >= maxAvatars then
				-- 已经到上限了（正常对局 4 人；观战/人台可能更多）。再补会一直"发现新玩家"→
				-- 每 60 帧白跑一趟 discover，所以这里明确放弃，并留一条日志。
				if runtime.extraAvatarLogged ~= true then
					runtime.extraAvatarLogged = true
					runtime.logger("[physbone][玩家] 场上还有第 %d 个 avatar（%s），超过上限 %d，不挂它的物理",
						#known + 1, tostring(unit_tag(S, unit)), maxAvatars)
				end
			else
				runtime.logger("[physbone][玩家] 有新玩家（%s）⇒ 补挂它的护甲",
					tostring(unit_tag(S, unit)))
				return true
			end
		end
	end
	for index = 1, #known do
		if liveSet[known[index].unit] == nil then
			runtime.logger("[physbone][玩家] 有玩家离开/阵亡（%s）⇒ 收掉它的会话",
				tostring(known[index].tag or "?"))
			return true
		end
	end
	return false
end


local function drive(runtime)
	ConsumerRuntime.watch(runtime)
	local frame = runtime.frame
	local options = runtime.options
	local logger = runtime.logger
	runtime.logContext.frame = frame
    runtime.logContext.active = runtime.sessions and #runtime.sessions>0 or false
    if runtime.logContext.active then runtime.logContext.activate() end
	Compat.begin_frame(frame)
	if runtime.sessions ~= nil or runtime.avatars ~= nil then
		local live = refreshLiveUnits(runtime)
		if live == "world-gone" or live == "unavailable" then
			dropHandleGroup(runtime, live == "world-gone" and "世界已不在" or "读不到可信活体列表", 1)
			return
		elseif live == "ok" and runtime.avatars ~= nil then
			local kept = {}
			local singleOwners = Single.active_only(runtime)
			for _, avatar in ipairs(runtime.avatars) do
				local live = singleOwners and Single.member(runtime, avatar.unit)
					or (not singleOwners and unitInInventory(runtime, avatar.unit))
				if live then kept[#kept + 1] = avatar end
			end
			if #kept ~= #runtime.avatars then
				if #kept == 0 then
					-- A departed avatar may leave living armor/corpse Units in this SAME
					-- world. Restore only fresh inventory members with the old layout;
					-- never do this after a loading gap or on a removed Unit/world.
					local currentTime = try(S.Application.time_since_launch)
					local gap = type(currentTime) == "number" and runtime.lastTime ~= nil
						and currentTime - runtime.lastTime > (options.loadGapSeconds or 0.5)
					local released = 0
					if not gap then
						for _, session in ipairs(runtime.sessions or {}) do
							if unitInInventory(runtime, session.unit) then
								local count = try(S.Unit.num_scene_graph_items, session.unit)
								if session.nodeCount == nil or count == session.nodeCount then
									local ok, restored = pcall(Compat.release, session)
									if ok then
										released = released + 1
										runtime.logger("[physbone][玩家] 主人已不在，unit=%s 已交还 %s 节基准姿态",
											tostring(session.unitTag or "?"), tostring(restored))
									end
								end
							end
						end
					end
					if released > 0 then runtime.logger("[physbone][玩家] 释放了 %d 个会话（主人已离开/阵亡），剩 0 个", released) end
					dropHandleGroup(runtime, "玩家句柄已全部移除", 1)
					return
				end
				runtime.avatars, runtime.avatar, runtime.avatarTag = kept, kept[1].unit, kept[1].tag
				runtime.reconcile = frame
			end
		end
	end
	-- dt 用引擎自己的时间差，不写死 1/60。
	-- 实测回调约 120 次/秒（不是 70，也不是 375），写死 1/60 会让物理比真实时间快/慢一截，
	-- 观感是"回弹拖沓"或"甩得太开"，很容易被误判成阻尼/刚度调错了。
	--
	-- ⚠️ `Application.time_since_launch` **每帧只更新一次**，所以：
	--   ① 只能在**帧之间**做差（在一次回调内部取首尾差值恒为 0，踩过）；
	--   ② 一帧里被调用多次时，后面那几次拿到的差值是 0 —— 这时**绝不能再用上一次的 dt 积分**，
	--      否则一帧就积了 N 倍的时间，物理快 N 倍、永远停不下来（表现就是"飘逸过头"）。
	--      正确做法是：时钟没前进 ⇒ 这一拍不是新的时间步 ⇒ 什么都不做。
	local now = try(S.Application.time_since_launch)
	local advanced = true
	if type(now) == "number" and now == now then
		local previous = runtime.lastTime
		runtime.lastTime = now
		if previous == nil then
			advanced = true                      -- 首帧：没有差值可比，照常驱动
		elseif now > previous then
			local delta = now - previous
			if delta > (options.loadGapSeconds or 0.5) and (runtime.sessions ~= nil or runtime.avatars ~= nil) then
				dropHandleGroup(runtime, string.format("检测到加载空档 %.2f s", delta), options.reArmFrames or 60)
				return
			end
			-- 上限 0.25 与 compat 的稳定性闸一致：卡顿帧不该被当成"过了 0.5 秒"去积分。
			if delta > 0.25 then delta = 0.25 end
			if delta >= 0.001 then runtime.dt = delta end
			advanced = true
		else
			advanced = false                     -- 同一时间步内的重复调用
			runtime.repeatCalls = (runtime.repeatCalls or 0) + 1
			-- 兜底：引擎时钟**一直不动**（老版本没有这个量 / 被谁包了一层）时不能永远不动。
			-- 连续太多次没前进就退回"按上一次的 dt 照常积分"，并大声说一次——
			-- 宁可物理快一点，也不要静默冻住（静默失败是这一整层最贵的一类问题）。
			runtime.stuckClock = (runtime.stuckClock or 0) + 1
			if runtime.stuckClock >= (options.stuckClockLimit or 600) then
				if not runtime.stuckClockLogged then
					runtime.stuckClockLogged = true
					logger("[physbone][警告] 引擎时钟连续 %d 次没有前进（time_since_launch 不可用？）"
						.. "⇒ 退回固定 dt=%.4f 继续驱动", runtime.stuckClock, runtime.dt or (1 / 60))
				end
				runtime.stuckClock = 0
				advanced = true
			end
		end
	end
	if not advanced then return end

	if runtime.sessions ~= nil and #runtime.sessions > 0 then
		local singleBeforePrune = Single.active_only(runtime)
		local dropped = pruneSessions(runtime)
		if dropped > 0 and singleBeforePrune and runtime.singleState then
			runtime.singleState.driveHoldUntil = frame + (options.deathGraceFrames or 20)
		end
		if dropped > 0 and options.dropAllOnDeath ~= false and not singleBeforePrune then
			dropHandleGroup(runtime, "会话死亡/重建（dropAllOnDeath）", 1)
			return
		end		if #runtime.sessions == 0 then
			-- 全没了（换场景 / 全员阵亡）：退回等待，带退避（避免换甲期间每秒重挂一次）。
			-- 存活时长决定退避：刚挂上就死 = 抖动（换甲中），要越等越久；
			-- 稳定跑过 5 秒再死 = 正常换场景，下一次应当**立刻**重挂。
			local survived = frame - (runtime.attachedFrame or frame)
			runtime.sessions = nil
			runtime.reconcile = nil
			if survived >= (options.stableFrames or 600) then
				runtime.reArm = 1
			else
				runtime.reArm = (runtime.reArm or 0) + 1
			end
			local delay = math.min(options.maxReArmFrames or 600, (options.reArmFrames or 60) * runtime.reArm)
			runtime.rearmAt = frame + delay
			logger("[physbone][LIFECYCLE] 场景已变（存活 %d 帧）⇒ 退避 %d 帧后重扫", survived, delay)
		else
			-- 只掉了一部分（某个队友换甲 / 退出 / 阵亡）：**留着活着的那些**，只补缺的。
			-- 老版本在这一步是"丢掉全部会话再重扫"，多人局里那等于一个人换甲，全场人闪一下没物理。
			if dropped > 0 then
				logger("[physbone][LIFECYCLE] 掉了 %d 个会话，剩 %d 个继续跑，随后补挂缺的",
					dropped, #runtime.sessions)
				runtime.reconcile = frame
			end
			-- 会话全都还"健康"，但场上**玩家名单**可能变了（有人加入 / 有人退出 / 复活换了实体）。
			-- 这里同样**不释放任何东西**：变的是名单，谁还在谁就继续跑。
			local validateFrames = options.validateFrames == nil and 60 or options.validateFrames
			if validateFrames > 0 and (frame % validateFrames) == 0 then
				-- Also refresh camera/owner ordering and retry late-ready armor layouts.
				local changed = avatarSetChanged(runtime)
				if changed or not Single.active_only(runtime) then
					runtime.reconcile = frame
				else
					-- Master uses roster/fill/negative events rather than a full scan every
					-- 60 frames. Keep a sparse single-only safety retry for older models
					-- whose newly created unit/layout had no earlier candidate to score.
					local rescan = options.rescanFrames == nil and 300 or options.rescanFrames
					local last = runtime.singleState and runtime.singleState.lastDiscoverFrame or frame
					if rescan > 0 and frame - last >= rescan then runtime.reconcile = frame end
				end
			end
		end
	end

	-- 名单变化后的补挂/收尾。走的是同一个 `tryAttach`（**增量**：只补没挂的、只收主人不在的），
	-- 所以不需要先把自己人的会话丢掉 —— 那正是老版本多人局里"所有人闪一下没物理"的来源。
	if runtime.reconcile ~= nil and runtime.sessions ~= nil and #runtime.sessions > 0 then
		if frame >= runtime.reconcile then
			local poll = options.reconcilePollFrames or (options.pollFrames or 20)
			if tryAttach(runtime) then
				runtime.reconcile = Single.next_reconcile(runtime, runtime.fillPending and (frame + poll) or nil)
			else
				runtime.reconcile = frame + poll     -- 场景还没稳，下一拍再来
			end
		end
	end

	if runtime.sessions == nil then
		if runtime.rearmAt ~= nil and frame < runtime.rearmAt then
			note_wait(runtime, "退避等待重扫")
			return
		end
		-- 等待中的轮询会跑一趟完整的 `discover`（扫所有 unit + 给每个候选打分，几千次引擎调用），
		-- 所以**必须**随等待时长放慢：刚掉线那 2 秒要快（复活/换甲很快结束），
		-- 之后就按 3 倍间隔扫一次 —— 否则"一直等不到"会变成持续的顿卡。
		runtime.waitSince = runtime.waitSince or frame
		local waited = frame - runtime.waitSince
		local poll = options.pollFrames or 20
		if waited > (options.waitSlowAfter or 200) then poll = poll * 3 end
		if (frame % poll) ~= 0 then return end
		if not tryAttach(runtime) then return end
		runtime.reconcile = Single.next_reconcile(runtime, runtime.fillPending and (frame + (options.reconcilePollFrames or options.pollFrames or 20)) or nil)
		runtime.waitSince = nil
	else
		runtime.waitSince = nil
	end

	ConsumerRuntime.tick(runtime)
	Single.tick(runtime)
	RemotePhysics.frame(runtime)
	-- ---------- 驱动 ----------
	-- 计时不可靠（`Application.time_since_launch` 每帧只更新一次、`os.clock()` 被引擎其它
	-- 线程污染），所以性能只报**引擎调用次数**——唯一不会被环境噪声污染的口径。
	--
	-- 多人局的**预算**：一帧的驱动成本几乎正比于链数（实测单人 52 链 ≈ 180 次引擎调用/帧，
	-- 约 3.5 次/链）。四个玩家同屏就是 4 倍。真到那个量级还没问题，但"每人身上好几套 mod"
	-- 会让链数继续翻，所以这里给一条闸：**第一位玩家（离相机最近的那个，也就是自己）每帧都算；
	-- 其余玩家按 stride 分帧**，被动到的那一帧用**累积的 dt** 积分（compat 内部还会再拆子步），
	-- 所以物理速度不变，只是采样率降到 1/2。观感差别极小，成本直接对半。
	local chainTotal = 0
	for index = 1, #runtime.sessions do
		chainTotal = chainTotal + #(runtime.sessions[index].sessions or {})
	end
	local stride = 1
	if not Single.active_only(runtime) then
		local budget = options.maxChainsPerFrame or 160
		-- 首位玩家（自己）身上的链数：这部分**不参与分帧**，始终每帧算。
		local primaryChains = 0
		for _, session in ipairs(runtime.sessions) do
			if (session.ownerOrder or 1) <= 1 then primaryChains = primaryChains + #(session.sessions or {}) end
		end
		-- Until camera priority is known, do not accidentally throttle the local
		-- player merely because a teammate has a larger dual-skeleton avatar.
		if runtime.cache.cameraUsable ~= true then primaryChains = chainTotal end
		runtime.lastPrimaryChains = primaryChains
		-- ── 自适应分帧（2026-11-03 实机：四人局红色折线约是绿色两倍、掉到 40 fps）──
		-- 旧实现是**固定 stride=2**，于是四人局的实际工作量是
		--     自己 418 链/帧 + 队友 3×418/2 ≈ 1045 链/帧
		-- 完全没有被 budget 约束住 —— 每帧预算形同虚设，玩家越多越线性变慢。
		--
		-- 现在按"队友链数 / 队友预算"反推步长：队友那边每帧最多驱动 budget/2 条链。
		-- 于是总工作量被压到 (自己 + budget/2) 附近，不再随玩家人数线性增长。
		-- dt 仍然累积补偿（compat 内部会再拆子步），所以**物理速度不变，只是队友的采样率下降**。
		local otherChains = chainTotal - primaryChains
		stride = 1
		local otherBudget = math.max(math.floor(budget / 2), 24)
		-- 只有**真的超预算**才分帧：队友链数在预算内时仍按每帧驱动（别为了省而省）。
		if otherChains > otherBudget then
			stride = math.max(2, math.ceil(otherChains / otherBudget))
			local cap = options.maxOtherPlayerStride or 16
			if stride > cap then stride = cap end
		end
		if stride ~= runtime.driveStride then
			runtime.driveStride = stride
			if stride > 1 then
				logger("[physbone][预算] 自己 %d 链/帧 + 队友 %d 链 ⇒ 队友每 %d 帧驱动一次（每帧预算 %d；dt 累积补偿，速度不变）",
					primaryChains, otherChains, stride, budget)
			else
				logger("[physbone][预算] 链数 %d 在每帧预算 %d 以内 ⇒ 所有玩家恢复每帧驱动",
					chainTotal, budget)
			end
		end
	else
		runtime.driveStride = 1
		runtime.lastPrimaryChains = runtime.singlePrimaryChains
	end
	local written, skippedSame, engineCalls, staticChains = 0, 0, 0, 0
	local attempted = 0
	local dt = runtime.dt or (1 / 60)
	for index = 1, #runtime.sessions do
		local session = runtime.sessions[index]
		-- compat 只在正常返回时刷新这两个计数；先清零，免得沿用上一帧的值把看门狗骗过去。
		session.skippedSame, session.engineCalls = 0, 0

		-- 时间**永远**先累积：没被驱动的这一帧不是"时间不存在"，攒到下一次一起积。
		-- 丢了它，物理会比真实时间慢 —— 表现是"队友的头发像在水里"。
		local pending = session.singleRemotePhysicsExcluded == true and 0 or ((session.pendingDt or 0) + dt)
		local order = session.ownerOrder or 1
		local due = stride <= 1 or order <= 1 or (frame % stride) == ((order - 1) % stride)
		if session.singleMainline and options.singleMainline ~= false then
			due = session.singleDue == true and session.singleRemotePhysicsExcluded ~= true
			-- Master uses the cheap alive primitive immediately before dispatch, not
			-- another full world membership scan. Fresh membership was checked in prune.
			if due then
				local okAlive, alive = pcall(Compat.unit_alive, S, session.unit)
				if not okAlive or alive == false then due = false end
			end
		else
			if not unitInInventory(runtime, session.unit) then session.dead = "gone"; due = false end
		end
		if session.singleMainline and not ConsumerRuntime.hasWork(session) then due, pending = false, 0 end
		if not due then
			session.pendingDt = pending
		else
			session.pendingDt = 0
			attempted = attempted + 1
			local driverBefore = session.driverWrites or 0
			if session.singleMainline then session.singleRemoteHadUpdate = true end
			local ok, out = pcall(Compat.update, session, pending)
			local driverDelta = math.max(0, (session.driverWrites or 0) - driverBefore)
			if session.singleRemoteIsRemote then runtime.remoteFrameDriverWrites = runtime.remoteFrameDriverWrites + driverDelta
			elseif session.singleRemoteIsSelf then runtime.selfFrameDriverWrites = runtime.selfFrameDriverWrites + driverDelta end
			if ok then
				if type(out) == "number" then written = written + out end
			elseif not session.updateErrorLogged then
				-- 以前这里是裸 pcall：一条 unit 每帧都抛错，日志里却什么也没有。
				session.updateErrorLogged = true
				logger("[physbone][错误] unit=%s 驱动抛错：%s", tostring(session.unitTag or "?"), tostring(out))
			end
			skippedSame = skippedSame + (session.skippedSame or 0)
			engineCalls = engineCalls + (session.engineCalls or 0)
		end

		if session.singleRemotePhysicsExcluded ~= true then
		for _, item in ipairs(session.sessions) do
			if (item.staticFrames or 0) > 0 then staticChains = staticChains + 1 end
		end
		end
	end
	runtime.driveFrames = (runtime.driveFrames or 0) + 1
	runtime.callsAccum = (runtime.callsAccum or 0) + engineCalls
	runtime.staticChains = staticChains
	runtime.lastChainTotal = chainTotal
	runtime.lastAttempted = attempted
	-- 这一帧一条都没驱动（stride 分帧的正常现象）时不能让"零帧看门狗"累加，
	-- 否则分帧本身会被误判成"驱动失效"→ 重挂 → 分帧 → 再判失效，无限循环。
	local attemptedAny = attempted > 0

	-- 峰值：**偏离绑定方向**的最大角，也就是"离模型原本的形状有多远"。
	--
	-- ⚠️ 它**不是**单节转角，所以拿它跟 `angleLimit` 比是错的（上一版就这么错了）：
	-- 求解器夹的是"相对父节"的偏转，而多节链上第 k 节的"偏离绑定"会把前面每一节的偏转累加进去
	-- ——5 节 × 25° 累到 100° 完全合法。上一版把它算成"超限骨"，报了 28~77，纯属误报。
	-- 判"限位有没有生效"要看相对父节的偏转，那是求解器内部量，不在这一层。
	-- 骨名取 item.chain[index].name，尖端核限位取 item.tip.bones[index].gains。
	-- 混用过一次，于是限位永远打印 0°，看着像"限位没生效"，白查一轮。
	local framePeak, worstName, worstLimit = 0, nil, 0
	for _, session in ipairs(runtime.sessions) do
		for _, item in ipairs(session.sessions) do
			local rotations = item.lastRotations
			if rotations ~= nil then
				for index = 1, #rotations do
					local angle = rotations[index][4]
					if angle > framePeak then
						framePeak = angle
						local chainBone = item.chain and item.chain[index]
						worstName = chainBone and chainBone.name or nil
						local simBones = item.tip and item.tip.bones or item.bones
						local simBone = simBones and simBones[index]
						local gains = simBone and simBone.gains
						worstLimit = (gains and gains.limit or 0) * 180 / math.pi
					end
				end
			end
		end
	end
	local framePeakDeg = framePeak * 180 / math.pi
	if framePeakDeg > (runtime.peakAngle or 0) then runtime.peakAngle = framePeakDeg end

	-- 阶段心跳：每 N 帧一行，证明驱动块确实被进入过，并给出当帧的关键事实。
	-- 上一轮出现过"phase 明明是 live 但 update 从不执行"，没有这条就无法区分
	-- "没进块"和"进了块但走了别的分支"。
	local heartbeat = options.heartbeatFrames or 600
	if heartbeat > 0 and (runtime.driveFrames % heartbeat) == 0 then
		local chains = 0
		for _, session in ipairs(runtime.sessions) do chains = chains + #session.sessions end
		logger("[physbone] hb u=%d c=%d p=%d stride=%d run=%d dt=%.4f w=%d skip=%d calls=%d avg=%.0f static=%d peak=%.1f max=%.1f bone=%s lim=%.0f repeat=%d",
			#runtime.sessions, chains, #(runtime.avatars or {}), runtime.driveStride or 1, attempted,
			runtime.dt or 0, written, skippedSame, engineCalls,
			runtime.callsAccum / runtime.driveFrames, staticChains, framePeakDeg,
			runtime.peakAngle or 0,
			worstName ~= nil and (tostring(worstName):match("_phys_(%d+)_") or tostring(worstName)) or "-", worstLimit,
			runtime.repeatCalls or 0)
	end

	-- 逐链明细（默认关）：区分"求解器在动"和"参数算出来就是 0"——后者在画面上就是钢板。
	local detailFrames = options.debugDetailFrames or 240
	if options.debug and detailFrames > 0 and (runtime.driveFrames % detailFrames) == 0 then
		local peak, parts, shown = 0, {}, 0
		for _, session in ipairs(runtime.sessions) do
			for _, item in ipairs(session.sessions) do
				local rotations = item.lastRotations
				if rotations ~= nil and shown < 6 then
					local itemPeak = 0
					for index = 1, #rotations do
						local angle = rotations[index][4] * 180 / math.pi
						if angle > itemPeak then itemPeak = angle end
					end
					if itemPeak > peak then peak = itemPeak end
					shown = shown + 1
					parts[#parts + 1] = string.format("%s=%.1f°",
						tostring(item.chain and item.chain[1] and item.chain[1].name or "?"), itemPeak)
				end
			end
		end
		logger("[physbone][debug] 逐链峰值 %s（全体峰值 %.1f°）", table.concat(parts, " "), peak)
	end

	-- ⚠️ 判"驱动失效"不能用"这一帧写了几个骨"：加了"姿态没变就跳过"之后，
	-- 站着不动时 written 天然就是 0，用它判失效会让静止的角色每 45 帧重挂一次（踩过）。
	-- 真正的判据是"求解器有没有在处理链"：写了 + 因没变而跳过 = 处理过的骨数。
	--
	-- 多人分帧之后还要再排除一种假信号：**这一帧按 stride 谁都不该被驱动**。
	-- 那种帧一条骨都不会被处理，但这不是故障——它是节流本身。判据要挂"有没有尝试过"。
	local handled = written + skippedSame
	if not attemptedAny then
		-- 分帧跳过的帧：不算数，也不清零（清零会让"卡住"永远攒不到上限）
	elseif handled == 0 then
		runtime.zeroFrames = (runtime.zeroFrames or 0) + 1
	else
		runtime.zeroFrames = 0
	end
	local tripped = false
	for _, session in ipairs(runtime.sessions) do
		if session.singleRemotePhysicsExcluded ~= true then
		for _, item in ipairs(session.sessions) do
			if item.disabled == true then tripped = true end
		end
		end
	end
	if runtime.zeroFrames >= (options.zeroLimit or 45) or tripped then
		logger("[physbone][驱动失效] 连续 %d 帧一条骨都没处理（护栏=%s）⇒ 退回等待重挂",
			runtime.zeroFrames, tostring(tripped))
		runtime.sessions = nil
		runtime.zeroFrames = 0
		runtime.reArm = (runtime.reArm or 0) + 1
		local delay = math.min(options.maxReArmFrames or 600, (options.reArmFrames or 60) * runtime.reArm)
		runtime.rearmAt = frame + delay
	end
end

--- 安装运行时。可重复调用：第二次直接返回同一个实例。
---@param stingray table 引擎命名空间
---@param options table { compat, logPath, debug, archiveId, ... }
---@return table runtime
function M.install(stingray, options)
	local existing = rawget(_G, INSTALL_KEY)
	if existing ~= nil then return existing end

	S = stingray
	options = options or {}
	-- In the actual exported addon __hd2_loader is the lexical loader argument.
	-- Standalone source can instead inject options.sceneContext explicitly.
	local context=__hd2_loader
	if type(context)~="table" then context=rawget(_G,"__hd2_loader") end
	if options.sceneContext==nil and type(context)=="table" then options.sceneContext=context end
	local compat = options.compat
	if compat == nil then
		-- 外置模式下加载器可能把 compat 作为同名模块提供；找不到就明确报错，
		-- 而不是静默什么都不做（静默是上一轮排查最久的一类问题）。
		error("physbone runtime: 缺少 physbone_compat 模块（install 的 options.compat）", 2)
	end
	Compat = compat

	local logger, logContext = makeLogger(options)
	state = {
		options = options,
		logger = logger,
		logContext = logContext,
		cache = {},
		carriers = nil,
		sessions = nil,
		-- 场上的玩家 avatar 名单（每个玩家一项）。会话按 `session.owner` 归属到其中一项上，
		-- 名单变化只影响"补挂/收尾"，不会推翻别人的会话。
		avatars = nil,
		reconcile = nil,     -- 名单变化后待执行的补挂帧号；nil = 没有待办
		driveStride = 1,     -- 当前的分帧步长（链数超预算时 >1）
		frame = 0,
		dt = options.dt or (1 / 60),
		reArm = 0,
		rearmAt = nil,
		driveFrames = 0,
		callsAccum = 0,
		zeroFrames = 0,
		waitReason = nil,
		waitRepeat = 0,
		installed = true,
	}
	rawset(_G, INSTALL_KEY, state)

	local driver = state
	if options.attachmentModule and options.attachmentProfile then
		state.attachments = options.attachmentModule.new(S, options.attachmentProfile, logger,
			{ mode = options.attachmentsMode or "apply" })
		logger("[attachments] 实验性挂点运行时已安装；按唯一姿态对应关系匹配护甲，歧义时恢复原版")
	end
	originalRender = rawget(_G, "render")
	rawset(_G, "render", function(...)
		-- 先让原来的 render 跑完（别的 mod 可能也在包装），再写我们的姿态：
		-- 这里只确认回调顺序；盔甲节点是否收到姿态、蒙皮是否使用仍需分别验证。
		local result
		if originalRender ~= nil then result = originalRender(...) end
		if driver.installed then
			driver.frame = driver.frame + 1
			local ok, err = pcall(drive, driver)
			if not ok and not driver.driveErrorLogged then
				driver.driveErrorLogged = true
				driver.logger("[physbone][错误] 驱动失败：%s", tostring(err))
			end
			if driver.attachments then
				local good, failure = pcall(driver.attachments.tick, driver.attachments, driver.frame)
				if not good then
					pcall(driver.attachments.release, driver.attachments)
					driver.logger("[attachments] 已停止并尝试恢复原版：%s", tostring(failure))
					driver.attachments = nil
				end
			end
		end
		return result
	end)

	logger("[physbone] 运行时 %s 已安装（%s）启动于 %s",
		M.VERSION,
		options.mode == "boot" and "独占 boot" or "外置模块",
		os.date("%Y-%m-%d %H:%M:%S"))
	return state
end

--- 卸载：把 render 还回去，并尽量把姿态交还给引擎。
function M.uninstall()
	local runtime = state
	if runtime == nil then return false end
	runtime.installed = false
	ConsumerRuntime.close(runtime)
	if runtime.adsLog then pcall(function() runtime.adsLog:flush(); runtime.adsLog:close() end); runtime.adsLog=nil end
	if runtime.attachments then pcall(runtime.attachments.release, runtime.attachments) end
	local live = refreshLiveUnits(runtime)
	if live == "ok" then
		for _, session in ipairs(runtime.sessions or {}) do
			if unitInInventory(runtime, session.unit) then pcall(Compat.release, session) end
		end
	end
	runtime.sessions, runtime.avatars, runtime.avatar, runtime.liveUnits, runtime.world = nil, nil, nil, nil, nil
	runtime.singleState, runtime.singleLiveIndex, runtime.singleLiveWanted = nil, nil, nil
    if runtime.logContext and runtime.logContext.close then runtime.logContext.close() end
	rawset(_G, "render", originalRender)
	rawset(_G, INSTALL_KEY, nil)
	state = nil
	return true
end

--- 运行中改参数（热调）。
function M.setOptions(patch)
	if state == nil or type(patch) ~= "table" then return false end
	for key, value in pairs(patch) do state.options[key] = value end
	if state.attachments and (patch.attachmentsMode == "apply" or patch.attachmentsMode == "observe" or patch.attachmentsMode == "off") then
		state.attachments.mode = patch.attachmentsMode
	end
	return true
end

M.install_ = M.install

return M

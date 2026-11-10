using HD2ModCore.Infrastructure;

namespace HD2ModCore.Tests;

/// <summary>
/// 内置 Lua 功能的外置包：两种形态（lua 版 / patch 版）+ addon 约定。
///
/// 契约来自三家加载器的一手资料（2026-11-01 核对）：
/// Boot Mod Loader / Chef Shared Loader / MDL3 全都靠
/// "资源名 mods/&lt;作者&gt;/&lt;名字&gt; + 首行 -- HD2-Addon: 同名" 来识别 addon。
/// 这里把这条约定钉死，免得哪天改导出格式悄悄让所有加载器都扫不到。
/// </summary>
public sealed class LuaAddonPackageTests
{
	private static string NewTempRoot()
	{
		var dir = Path.Combine(Path.GetTempPath(), "hd2lua-pkg-" + Guid.NewGuid().ToString("N"));
		Directory.CreateDirectory(dir);
		return dir;
	}

	[Fact]
	public void Physics_SourceStartsWithTheAddonMarkerOnLineOne()
	{
		var feature = LuaAddonCatalog.Physics();
		// 首行必须是标记：Boot Mod Loader 只认第一行，前面有任何空行/注释都会漏掉。
		Assert.StartsWith("-- HD2-Addon: mods/hd2modmanager/physbone\n", feature.Source, StringComparison.Ordinal);
		// 不能有 BOM：Lua 5.1 不跳过 BOM，带 BOM 的脚本编译会直接失败。
		Assert.False(feature.Source.Length > 0 && feature.Source[0] == '\uFEFF');
	}

	[Fact]
	public void Wardrobe_SourceStartsWithTheAddonMarkerOnLineOne()
	{
		var feature = LuaAddonCatalog.Wardrobe();
		Assert.StartsWith("-- HD2-Addon: mods/hd2modmanager/wardrobe\n", feature.Source, StringComparison.Ordinal);
	}

	[Fact]
	public void AttachmentFix_SourceStartsWithTheAddonMarkerOnLineOne()
	{
		var feature = LuaAddonCatalog.AttachmentFix("return {testProfile=true}");
		Assert.StartsWith("-- HD2-Addon: mods/hd2modmanager/attachment_fix\n", feature.Source, StringComparison.Ordinal);
		Assert.False(feature.Source.Length > 0 && feature.Source[0] == '\uFEFF');
	}

	[Fact]
	public void AttachmentFix_UsesSharedRuntimeAndRequiresModelCalibration()
	{
		Assert.Throws<InvalidOperationException>(() => PhysBoneLuaSource.ComposeAttachmentFixPackage());
		var source = LuaAddonCatalog.AttachmentFix("return {testProfile=true}").Source;
		Assert.Contains("local M = {VERSION = '1.0.17'}", source, StringComparison.Ordinal);
		Assert.Contains("options.transfer.new(engine", source, StringComparison.Ordinal);
		Assert.Contains("experimentalPoseIntent", source, StringComparison.Ordinal);
        Assert.Contains("cfg.rightAttachmentEnabled", source, StringComparison.Ordinal);
        Assert.Contains("spec.sourceMount", source, StringComparison.Ordinal);
		Assert.Contains("performance.strictConsumers", source, StringComparison.Ordinal);
		Assert.Contains("return {testProfile=true}", source, StringComparison.Ordinal);
		Assert.DoesNotContain("-- INSERT ", source, StringComparison.Ordinal);
		Assert.DoesNotContain("M.GRIP_PAIRS = {}", source, StringComparison.Ordinal);
		Assert.DoesNotContain("local PhysBoneRuntime =", source, StringComparison.Ordinal);
	}

	[Fact]
	public void AttachmentFix_RangeViolationRetriesOnlyAfterVerifiedRollback()
	{
		var source = LuaAddonCatalog.AttachmentFix("return {testProfile=true}").Source;
		Assert.Contains("local recoverable=rangeFailure~=nil and why==rangeFailure", source, StringComparison.Ordinal);
		Assert.Contains("if recoverable and safe then", source, StringComparison.Ordinal);
		Assert.Contains("restore_refresh_failed", source, StringComparison.Ordinal);
		Assert.Contains("mount_range_restore_failed:", source, StringComparison.Ordinal);
		Assert.Contains("preflight_skip_or_verified_rollback_retry", source, StringComparison.Ordinal);
		Assert.Contains("emit(row,true)", source, StringComparison.Ordinal);
		Assert.DoesNotContain("assert(cfg.rightAttachmentEnabled==false or distance(desired,source)", source, StringComparison.Ordinal);
	}

	[Fact]
	public void AttachmentFix_CompactLogHasTimeAndSizeLimits()
	{
		var source = LuaAddonCatalog.AttachmentFix("return {testProfile=true}").Source;
		// 详细测试日志轮后文件名改为运行时拼接：普通会话仍是 hd2_grip_b23_compact.log，
		// 仅 testRepairs.detailed 会话换用 hd2_grip_TEST_DETAILED_<模型>_<时间>.partNN 分段。
		Assert.Contains("hd2_grip_b23_compact", source, StringComparison.Ordinal);
		Assert.Contains("..'.log'", source, StringComparison.Ordinal);
		Assert.Contains("io.open(logPath(),'w')", source, StringComparison.Ordinal);
		Assert.Contains("limits.recordSeconds or 90", source, StringComparison.Ordinal);
		Assert.Contains("limits.maxBytes or 524288", source, StringComparison.Ordinal);
		Assert.Contains("log_recording_stopped", source, StringComparison.Ordinal);
		Assert.Contains("positions-v1", source, StringComparison.Ordinal);
	}

	[Fact]
	public void AttachmentFix_AdapterAndTransferVersionsMatchInComposedEntry()
	{
		// Testing Transfer.new directly bypasses install's version gate.
		var source = LuaAddonCatalog.AttachmentFix("return {testProfile=true}").Source;
		var transfer = source.IndexOf("local Transfer=(function()", StringComparison.Ordinal);
		var adapter = source.IndexOf("local AttachmentRuntime=(function()", StringComparison.Ordinal);
		var profile = source.IndexOf("local profile=(function()", StringComparison.Ordinal);
		Assert.True(transfer >= 0 && adapter > transfer && profile > adapter);
		const string pattern = @"VERSION\s*=\s*'([^']+)'";
		var transferVersion = System.Text.RegularExpressions.Regex.Match(source[transfer..adapter], pattern);
		var adapterVersion = System.Text.RegularExpressions.Regex.Match(source[adapter..profile], pattern);
		Assert.True(transferVersion.Success && adapterVersion.Success);
		Assert.Equal(transferVersion.Groups[1].Value, adapterVersion.Groups[1].Value);
	}

	[Fact]
	public void AttachmentFix_Test07UsesChefMissionScopeAndLiveGripMarkers()
	{
		var source = LuaAddonCatalog.AttachmentFix("return {testProfile=true}").Source;
		Assert.Contains("inMission=loader.in_mission,world=loader.world", source, StringComparison.Ordinal);
        Assert.Contains("sceneContext.firstPerson=viewGuard.sample", source, StringComparison.Ordinal);
		Assert.Contains("options.armMath, options.sceneContext", source, StringComparison.Ordinal);
		Assert.Contains("ambiguous_underbarrel_link", source, StringComparison.Ordinal);
		Assert.Contains("live_right_ik_to_registered_hand", source, StringComparison.Ordinal);
		Assert.Contains("performance.snapshotPoseCache", source, StringComparison.Ordinal);
		Assert.Contains("performance.sparseMembership", source, StringComparison.Ordinal);
		Assert.DoesNotContain("self.nameIds", source, StringComparison.Ordinal);
	}

	[Fact]
	public void AttachmentFix_SidearmNativePathAndRightOutputsAreExplicit()
	{
		var source = LuaAddonCatalog.AttachmentFix("return {testProfile=true}").Source;
		Assert.Contains("preserve_native_held_path_sync_source_right_arm", source, StringComparison.Ordinal);
		Assert.Contains("right_output_contract_required", source, StringComparison.Ordinal);
		Assert.Contains("right_world_readback", source, StringComparison.Ordinal);
		Assert.Contains("record.right", source, StringComparison.Ordinal);
		Assert.Contains("native_observer", source, StringComparison.Ordinal);
		Assert.Contains("skinMatricesObserved=false", source, StringComparison.Ordinal);
		Assert.Contains("cylinder_swivel", source, StringComparison.Ordinal);
	}

	[Fact]
	public void AttachmentFix_FirstPersonBypassesAllWritesAndUsesLiveViewProof()
	{
		var source = LuaAddonCatalog.AttachmentFix("return {testProfile=true}").Source;
		Assert.Contains("fp_camera_matches_main_view", source, StringComparison.Ordinal);
		Assert.Contains("World", source, StringComparison.Ordinal);
		Assert.Contains("debug_camera_pose", source, StringComparison.Ordinal);
		Assert.Contains("if view_bypass(frame,now) then return end", source, StringComparison.Ordinal);
		Assert.Contains("self:release(members(false))", source, StringComparison.Ordinal);
		Assert.Contains("all_attachment_arm_and_body_outputs", source, StringComparison.Ordinal);
		Assert.DoesNotContain("-- INSERT FIRST PERSON GUARD", source, StringComparison.Ordinal);
	}


	[Fact]
	public void AttachmentFix_FirstPersonKeepsCacheMaintenanceSeparateFromPoseWrites()
	{
		var source = LuaAddonCatalog.AttachmentFix("return {testProfile=true}").Source;
		Assert.Contains("sceneContext.fpWorld=viewGuard.world", source, StringComparison.Ordinal);
		var start = source.IndexOf("    local function fp_presentation(", StringComparison.Ordinal);
		var end = source.IndexOf("    local function fp_visibility_restore(", start, StringComparison.Ordinal);
		Assert.True(start >= 0 && end > start);
		var maintenance = source[start..end];
		Assert.Contains("identity(item);W.update_unit(item.world,item.unit)", maintenance, StringComparison.Ordinal);
		Assert.Contains("refresh(a,'avatar')", maintenance, StringComparison.Ordinal);
		Assert.Contains("refresh(item,'model')", maintenance, StringComparison.Ordinal);
		Assert.Contains("fp_presentation", maintenance, StringComparison.Ordinal);
		Assert.Contains("mission~=true then return end", maintenance, StringComparison.Ordinal);
		Assert.Contains("visibilityWritten=false,linksChanged=false", maintenance, StringComparison.Ordinal);
		foreach (var forbidden in new[] { "set_local_pose(", "set_world_pose(", "set_visibility(", "link_unit(", "unlink_unit(", "set_animation_state_machine(" })
			Assert.DoesNotContain(forbidden, maintenance, StringComparison.Ordinal);
		Assert.True(maintenance.IndexOf("refresh(a,'avatar')", StringComparison.Ordinal) < maintenance.IndexOf("refresh(item,'model')", StringComparison.Ordinal));
	}


	[Fact]
	public void AttachmentFix_FirstPersonArmHideIsScopedAndRestoresPerMesh()
	{
		var source = LuaAddonCatalog.AttachmentFix("return {testProfile=true}").Source;
		Assert.Contains("sceneContext.fpActor=viewGuard.actor", source, StringComparison.Ordinal);
		Assert.Contains("firstPersonArmHide", source, StringComparison.Ordinal);
		Assert.Contains("selected_fp_avatar_three_native_bones", source, StringComparison.Ordinal);
		Assert.Contains("U.set_mesh_visibility(item.unit,mesh.index,false,'default')", source, StringComparison.Ordinal);
		Assert.Contains("U.set_mesh_visibility(u,mesh.index,mesh.visible,'default')", source, StringComparison.Ordinal);
		Assert.Contains("fp_visibility_restore(membership,reason or 'shutdown')", source, StringComparison.Ordinal);
		Assert.Contains("fp_visibility_restore(members(false),'third_person')", source, StringComparison.Ordinal);
		Assert.Contains("'LeftArm' or role=='RightArm'", source, StringComparison.Ordinal);
		var start = source.IndexOf("    local function fp_visibility_restore(", StringComparison.Ordinal);
		var end = source.IndexOf("    local function view_bypass(", start, StringComparison.Ordinal);
		var visibility = source[start..end];
		foreach (var forbidden in new[] { "set_local_pose(", "set_world_pose(", "link_unit(", "unlink_unit(", "set_animation_state_machine(", "set_unit_visibility(" })
			Assert.DoesNotContain(forbidden, visibility, StringComparison.Ordinal);
	}

	[Fact]
	public void Physics_SourceNoLongerInlinesTheAttachmentAdapter()
	{
		// lua 拆分：hd2physbone.lua 只负责物理；挂点修正独立成包。
		// （runtime 源码保留可选的 attachmentModule 入参不算内联——composer 不再传它。）
		var source = LuaAddonCatalog.Physics().Source;
		Assert.DoesNotContain("NativeAttachments", source, StringComparison.Ordinal);
		Assert.DoesNotContain("NativeAttachmentProfile", source, StringComparison.Ordinal);
		Assert.Contains("options = { compat = PhysBoneCompat, mode = '", source, StringComparison.Ordinal);
		Assert.Contains("local PhysBoneCompat = (function()", source, StringComparison.Ordinal);
		Assert.Contains("local PhysBoneRuntime = (function()", source, StringComparison.Ordinal);
	}

	[Fact]
	public void AttachmentFix_FeatureIsDistinctFromPhysicsAndWardrobe()
	{
		var feature = LuaAddonCatalog.AttachmentFix("return {testProfile=true}");
		Assert.NotEqual(LuaAddonCatalog.PhysicsAddonId, feature.AddonId);
		Assert.NotEqual(LuaAddonCatalog.WardrobeAddonId, feature.AddonId);
		Assert.NotEqual(LuaAddonCatalog.PhysicsModGuid, feature.ModGuid);
		Assert.NotEqual(LuaAddonCatalog.WardrobeModGuid, feature.ModGuid);
		Assert.Equal("[骨骼挂点修正] 挂点动态修正运行时", feature.Title);
	}

	[Fact]
	public void Physics_SourceCarriesInlinedCompatAndAutoInstall()
	{
		var source = LuaAddonCatalog.Physics().Source;
		Assert.Contains("local PhysBoneCompat = (function()", source, StringComparison.Ordinal);
		Assert.Contains("local PhysBoneRuntime = (function()", source, StringComparison.Ordinal);
		Assert.Contains("PhysBoneRuntime.install(", source, StringComparison.Ordinal);
		Assert.Contains("rawget(_G, 'stingray')", source, StringComparison.Ordinal);
	}

	[Fact]
	public void Export_ProducesBothLuaAndPatchVariants()
	{
		var root = NewTempRoot();
		try
		{
			var folder = LuaAddonPackageExport.Export(root, LuaAddonCatalog.Physics());

			// lua 版：一个裸脚本
			var luaFile = Path.Combine(folder, "lua版", "hd2physbone.lua");
			Assert.True(File.Exists(luaFile), luaFile);

			// 物理补丁在根：manifest + 三件套，避免 Arsenal 只选外层后复制零文件。
			var patchDir = folder;
			Assert.True(File.Exists(Path.Combine(patchDir, "manifest.json")));
			Assert.True(File.Exists(Path.Combine(patchDir, "9ba626afa44a3aa3.patch_0")));
			Assert.True(File.Exists(Path.Combine(patchDir, "9ba626afa44a3aa3.patch_0.stream")));
			Assert.True(File.Exists(Path.Combine(patchDir, "9ba626afa44a3aa3.patch_0.gpu_resources")));

			Assert.True(File.Exists(Path.Combine(folder, LuaAddonPackageExport.ReadmeFileName)));
		}
		finally
		{
			if (Directory.Exists(root)) Directory.Delete(root, recursive: true);
		}
	}

	[Fact]
	public void Export_IsIdempotentAndDropsStaleFiles()
	{
		var root = NewTempRoot();
		try
		{
			var folder = LuaAddonPackageExport.Export(root, LuaAddonCatalog.Physics());
			var stale = Path.Combine(folder, "lua版", "stale.lua");
			File.WriteAllText(stale, "-- leftover");

			LuaAddonPackageExport.Export(root, LuaAddonCatalog.Physics());
			Assert.False(File.Exists(stale), "重复导出必须整目录重建，否则残留文件会被当成要装的东西");
		}
		finally
		{
			if (Directory.Exists(root)) Directory.Delete(root, recursive: true);
		}
	}

	[Fact]
	public void Export_PatchArchiveContainsOneLuaResourceNamedAfterTheAddon()
	{
		var root = NewTempRoot();
		try
		{
			var folder = LuaAddonPackageExport.Export(root, LuaAddonCatalog.Physics());
			var path = Path.Combine(folder, "9ba626afa44a3aa3.patch_0");
			var bytes = File.ReadAllBytes(path);

			// 头部：magic + typeCount=1 + fileCount=1
			Assert.Equal(0xF0000011u, BitConverter.ToUInt32(bytes, 0));
			Assert.Equal(1u, BitConverter.ToUInt32(bytes, 4));
			Assert.Equal(1u, BitConverter.ToUInt32(bytes, 8));

			// 条目里的 fileId 必须是 addon 名的 Stingray 哈希——加载器按名字找它。
			var expected = HD2GameItemAssets.StingrayHash.Murmur64A(LuaAddonCatalog.PhysicsAddonId);
			Assert.Equal(expected, BitConverter.ToUInt64(bytes, 104));
			// 类型 id = Lua
			Assert.Equal(0xA14E8DFA2CD117E2ul, BitConverter.ToUInt64(bytes, 112));
		}
		finally
		{
			if (Directory.Exists(root)) Directory.Delete(root, recursive: true);
		}
	}

	[Fact]
	public void Export_TwoFeaturesLandInSiblingFoldersUnderTheSameRoot()
	{
		var root = NewTempRoot();
		try
		{
			LuaAddonPackageExport.Export(root, LuaAddonCatalog.Physics());
			LuaAddonPackageExport.Export(root, LuaAddonCatalog.Wardrobe());

			Assert.True(Directory.Exists(Path.Combine(root, "physbone")));
			Assert.True(Directory.Exists(Path.Combine(root, "wardrobe")));
		}
		finally
		{
			if (Directory.Exists(root)) Directory.Delete(root, recursive: true);
		}
	}

	[Fact]
	public void FeatureGuidsAreStableAndDistinct()
	{
		// GUID 固定：重复导出不能被管理器当成另一个 mod。
		Assert.NotEqual(LuaAddonCatalog.PhysicsModGuid, LuaAddonCatalog.WardrobeModGuid);
		Assert.True(Guid.TryParse(LuaAddonCatalog.PhysicsModGuid, out _));
		Assert.True(Guid.TryParse(LuaAddonCatalog.WardrobeModGuid, out _));
	}

	[Fact]
	public void PhysicsPackageCarriesFlagDrivenLinearDegreesOfFreedom()
	{
		var source = LuaAddonCatalog.Physics().Source;
		Assert.Contains("gains.freeLength = true", source, StringComparison.Ordinal);
		Assert.Contains("function M.step_base_springs", source, StringComparison.Ordinal);
		Assert.Contains("function M.reset_linear_state", source, StringComparison.Ordinal);
		Assert.Contains("flag_set(flags, M.FLAG_LENGTH_CONSTRAINED)", source, StringComparison.Ordinal);
		Assert.Contains("flag_set(flags, M.FLAG_BASE_SPRING)", source, StringComparison.Ordinal);
		Assert.Contains("baseSpringState", source, StringComparison.Ordinal);
		Assert.Contains("tip.localPositions and tip.localPositions[index]", source, StringComparison.Ordinal);
		Assert.Contains("positionEpsilon2", source, StringComparison.Ordinal);
	}

	[Fact]
	public void PhysicsPackageCarriesSingleFrontSkirtPolicyAndTipLimitDiagnostic()
	{
		var source = LuaAddonCatalog.Physics().Source;
		Assert.Contains("M.version = \"1.3.1\"", source, StringComparison.Ordinal);
		Assert.Contains("M.VERSION = \"2.3.1\"", source, StringComparison.Ordinal);
		Assert.Contains("function M.is_wrist_driver(bone)", source, StringComparison.Ordinal);
		Assert.Contains("if M.is_wrist_driver(bone) then", source, StringComparison.Ordinal);
		Assert.Contains("excludedWristDrivers = excludedWristDrivers", source, StringComparison.Ordinal);
		Assert.Contains("single-front-skirt-driver-v1", source, StringComparison.Ordinal);
		Assert.Contains("native-front-skirt-driver-v1", source, StringComparison.Ordinal);
		Assert.Contains("childNs ~= namespace", source, StringComparison.Ordinal);
		Assert.Contains("controlRole ~= \"anim\"", source, StringComparison.Ordinal);
		Assert.Contains("rig.drivers.version ~= 3", source, StringComparison.Ordinal);
		Assert.Contains("root.parentName ~= expected.helper", source, StringComparison.Ordinal);
		Assert.Contains("item.tip and item.tip.bones or item.bones", source, StringComparison.Ordinal);
		Assert.DoesNotContain("local simBone = item.bones and item.bones[index]", source, StringComparison.Ordinal);
	}

	[Fact]
	public void PhysicsPackageCarriesScopedTest06CanonicalBindRepair()
	{
		var source = LuaAddonCatalog.Physics().Source;
		Assert.Contains("function M.test06_vrd_bind_reference(rig, bone)", source, StringComparison.Ordinal);
		Assert.Contains("rig.drivers.version ~= 2", source, StringComparison.Ordinal);
		Assert.Contains("#rig.drivers.bones ~= 7", source, StringComparison.Ordinal);
		Assert.Contains("test06-native-v2-bind-v1", source, StringComparison.Ordinal);
		Assert.Contains("hd2n_e6dc84f05416_aux_073_j797554dea8d0_source_extra_73", source, StringComparison.Ordinal);
		Assert.Contains("row.test06ControlBindQ or", source, StringComparison.Ordinal);
		Assert.Contains("local bind, frame = row.test06DriverBindQ, row.test06SetterFrame", source, StringComparison.Ordinal);
		Assert.Contains("shipped_bind_frame_mismatch", source, StringComparison.Ordinal);
	}
}

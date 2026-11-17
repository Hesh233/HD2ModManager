using HD2ModCore.Infrastructure;

namespace HD2ModCore.Tests;

public sealed class PhysicsRoutePackageTests
{
	[Fact]
	public void PackageEmbedsBothPipelinesButRoutesBeforeInstallAndKeepsLocalVersions()
	{
		var source=PhysBoneLuaSource.ComposeStandalonePackage().Replace("\r\n","\n");
		Assert.Contains("M.VERSION = \"2.3.7\"",source);
		Assert.Contains("M.VERSION = \"2.1.45\"",source);
		Assert.Contains("M.version = \"1.3.7\"",source);
		Assert.Contains("local INSTALL_KEY = \"__hd2physbone_direct_runtime\"",source);
		Assert.Contains("local PhysBoneRuntime = PhysicsRoutes.new(PhysBoneCompat, SkeletonRuntime, DirectCompat, DirectRuntime)",source);
		Assert.Contains("hd2_physics_route.txt",source);
		Assert.True(source.IndexOf("directRuntime.uninstall()",StringComparison.Ordinal) < source.IndexOf("skeletonRuntime.uninstall()", source.IndexOf("function api.uninstall()",StringComparison.Ordinal),StringComparison.Ordinal));
		Assert.Contains("if marker == M.DIRECT then return M.DIRECT end\n\treturn M.SKELETON",source);
	}
	[Fact]
	public void LocalAndDirectEmbeddedResourcesResolveWithoutSuffixAmbiguity()
	{
		Assert.Contains("M.VERSION = \"2.3.7\"",PhysBoneLuaSource.LoadRuntime());
		Assert.DoesNotContain("M.VERSION = \"2.1.45\"",PhysBoneLuaSource.LoadRuntime());
		Assert.Contains("M.VERSION = \"2.1.45\"",PhysBoneLuaSource.LoadDirectRuntime());
		Assert.Contains("refresh_live_units",PhysBoneLuaSource.LoadDirectRuntime());
		Assert.Contains("if not yawSet then yawMin, yawMax = -1, 1 end",PhysBoneLuaSource.LoadDirectCompat());
	}
	[Fact]
	public void AcceptedTest16RepairKeepsStrictIdentityAndDetailedSamplingOptIn()
	{
		var source=PhysBoneLuaSource.LoadCompat();
		Assert.Contains("M.version = \"1.3.7\"",source);
		Assert.Contains("gains.freeLength and gains.test16StableAngular",source);
		Assert.Contains("axialSpan = dx*prevX + dy*prevY + dz*prevZ",source);
		Assert.Contains("result.test16Diagnostics=options and options.test16Diagnostics==true",source);
		Assert.Contains("not session.test16Diagnostics",source);
		Assert.Contains("bind-or-node-",source);
		Assert.DoesNotContain("1.3.7-test16-r1",source);
	}
	[Fact]
	public void SkeletonMultiplayerResourcesKeepFairScoringAndStableIdentity()
	{
		var runtime = PhysBoneLuaSource.LoadRuntime();
		var compat = PhysBoneLuaSource.LoadCompat();
		Assert.Contains("M.VERSION = \"2.3.7\"", runtime);
		Assert.Contains("runtime.fillCursor, runtime.fillPending", runtime);
		Assert.Contains("options.dropAllOnDeath ~= false", runtime);
		Assert.Contains("local function refreshLiveUnits(runtime)", runtime);
		Assert.Contains("local function hasNamedNode(S_, unit, name)", runtime);
		Assert.DoesNotContain("if index > maxScored then", runtime);
		Assert.DoesNotContain("if previous ~= count then", runtime);
		Assert.Contains("function M.resolve_named_node(S, unit, name, nodeCount)", compat);
		Assert.Contains("identityNode = sessions[1].chain[1].name", compat);
		Assert.DoesNotContain("identityNode = id32(", compat);
		Assert.Contains("vrdSkeletonOnly = true", runtime);
	}
	[Fact]
	public void SingleMainlinePolicyIsPositivelyGatedAndDoesNotReplaceDualOrMath()
	{
		var runtime = PhysBoneLuaSource.LoadRuntime();
		Assert.Contains("M.SINGLE_UPSTREAM_VERSION = Single.UPSTREAM_VERSION", runtime);
		Assert.Contains("b78e63ebc77017aa6c70d52e0bf9e06e46360b92", runtime);
		Assert.Contains("M.LEGACY_SKELETON_VERSION = \"2.3.6\"", runtime);
		Assert.Contains("rig.drivers.version ~= 3", runtime);
		Assert.Contains("^hd2n_%x+_", runtime);
		Assert.Contains("not singleBeforePrune", runtime);
		Assert.Contains("if not Single.active_only(runtime) then", runtime);
		Assert.Contains("local budget = options.maxChainsPerFrame or 160", runtime);
		Assert.Contains("local budget = runtime.options.maxChainsPerFrame or 600", runtime);
		Assert.Contains("pcall(Compat.update, session, pending)", runtime);
		Assert.Contains("M.version = \"1.3.7\"", PhysBoneLuaSource.LoadCompat());
	}

	[Fact]
	public void SinglePolicyKeepsIncrementalReadinessAndPrimaryFullCadence()
	{
		var runtime = PhysBoneLuaSource.LoadRuntime();
		Assert.Contains("single.matches[candidate.unit]", runtime);
		Assert.Contains("options.negativeRetryFrames or 30", runtime);
		Assert.Contains("singleMatch and (best.score or 0) >= 1", runtime);
		Assert.Contains("options.rescanFrames == nil and 300", runtime);
		Assert.Contains("single.cache.frame = runtime.frame", runtime);
		Assert.Contains("motion_follows(runtime, session.owner, session.unit) == false", runtime);
		Assert.Contains("(followCount[key] or 0) > 0", runtime);
		Assert.Contains("source.singleDue = stride <= 1 or ((runtime.frame + index) % stride) == 0", runtime);
		Assert.Contains("session.singleMainline and options.singleMainline ~= false", runtime);
		Assert.Contains("Fresh membership was checked in prune", runtime);
	}

}

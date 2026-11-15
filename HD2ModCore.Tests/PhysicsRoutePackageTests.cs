using HD2ModCore.Infrastructure;

namespace HD2ModCore.Tests;

public sealed class PhysicsRoutePackageTests
{
	[Fact]
	public void PackageEmbedsBothPipelinesButRoutesBeforeInstallAndKeepsLocalVersions()
	{
		var source=PhysBoneLuaSource.ComposeStandalonePackage().Replace("\r\n","\n");
		Assert.Contains("M.VERSION = \"2.3.4\"",source);
		Assert.Contains("M.VERSION = \"2.1.45\"",source);
		Assert.Contains("M.version = \"1.3.4\"",source);
		Assert.Contains("local INSTALL_KEY = \"__hd2physbone_direct_runtime\"",source);
		Assert.Contains("local PhysBoneRuntime = PhysicsRoutes.new(PhysBoneCompat, SkeletonRuntime, DirectCompat, DirectRuntime)",source);
		Assert.Contains("hd2_physics_route.txt",source);
		Assert.True(source.IndexOf("directRuntime.uninstall()",StringComparison.Ordinal) < source.IndexOf("skeletonRuntime.uninstall()", source.IndexOf("function api.uninstall()",StringComparison.Ordinal),StringComparison.Ordinal));
		Assert.Contains("if marker == M.DIRECT then return M.DIRECT end\n\treturn M.SKELETON",source);
	}
	[Fact]
	public void LocalAndDirectEmbeddedResourcesResolveWithoutSuffixAmbiguity()
	{
		Assert.Contains("M.VERSION = \"2.3.4\"",PhysBoneLuaSource.LoadRuntime());
		Assert.DoesNotContain("M.VERSION = \"2.1.45\"",PhysBoneLuaSource.LoadRuntime());
		Assert.Contains("M.VERSION = \"2.1.45\"",PhysBoneLuaSource.LoadDirectRuntime());
		Assert.Contains("refresh_live_units",PhysBoneLuaSource.LoadDirectRuntime());
		Assert.Contains("if not yawSet then yawMin, yawMax = -1, 1 end",PhysBoneLuaSource.LoadDirectCompat());
	}
}

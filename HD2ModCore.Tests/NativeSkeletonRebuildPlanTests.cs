using HD2ModCore.Infrastructure;
using Xunit;

namespace HD2ModCore.Tests;

public sealed class NativeSkeletonRebuildPlanTests
{
    [Theory]
    [InlineData(false, false, NativeSkeletonBuildKind.OriginalFormat, null, false)]
    [InlineData(true, false, NativeSkeletonBuildKind.DualSkeletonWithLua, "--source-skeleton", true)]
    [InlineData(false, true, NativeSkeletonBuildKind.SingleSkeleton, "--single-hd2-skeleton", true)]
    public void ExistingRouteIsPreserved(bool dual, bool single, NativeSkeletonBuildKind expected,
        string? argument, bool preparation)
    {
        var plan = NativeSkeletonRebuildPlan.Create(dual, single);
        Assert.Equal(expected, plan.Kind);
        Assert.Equal(argument, plan.ConversionArgument);
        Assert.Equal(preparation, plan.RequiresPreparation);
    }

    [Fact]
    public void AmbiguousDualAndSingleNeverFallsBackToOriginal()
        => Assert.Throws<InvalidDataException>(() => NativeSkeletonRebuildPlan.Create(true, true));

    [Theory]
    [InlineData("source-skeleton.json", NativeSkeletonBuildKind.DualSkeletonWithLua)]
    [InlineData("single-skeleton.json", NativeSkeletonBuildKind.SingleSkeleton)]
    public void PayloadManifestDeterminesRoute(string file, NativeSkeletonBuildKind expected)
    {
        var tempRoot = Path.TrimEndingDirectorySeparator(Path.GetFullPath(Path.GetTempPath()))
            + Path.DirectorySeparatorChar;
        var root = Path.GetFullPath(Path.Combine(tempRoot, "hd2-sync-rebuild-plan-" + Guid.NewGuid().ToString("N")));
        if (!root.StartsWith(tempRoot, StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("Test cleanup target is outside the intended temp directory.");
        Directory.CreateDirectory(root);
        try
        {
            File.WriteAllText(Path.Combine(root, file), "{}");
            Assert.Equal(expected, NativeSkeletonRebuildPlan.FromPayload(root).Kind);
        }
        finally { Directory.Delete(root, recursive: true); }
    }
}

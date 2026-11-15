using HD2ModManager.Services;
namespace HD2ModCore.Tests;
public sealed class VpkSkeletonDecisionTests
{
    [Fact] public void SingleMeansVpkConvertedToOnlyHd2AndFullAnimation()
    {
        var d = new VpkModelDecision(false, 1.08, true, SingleHd2Skeleton:true);
        Assert.True(d.BuildsSkeletonPackage); Assert.False(d.UseNativeSkeleton);
        Assert.True(d.SingleHd2Skeleton); Assert.True(d.GenerateAnimation);
    }
    [Fact] public void LegacySourceDecisionRemainsDualSkeleton()
    {
        var d = new VpkModelDecision(true, 1.08, true);
        Assert.True(d.BuildsSkeletonPackage); Assert.True(d.UseNativeSkeleton);
        Assert.False(d.SingleHd2Skeleton); Assert.True(d.GenerateAnimation);
    }
    [Fact] public void NonInteractiveLegacyConversionDoesNotBuildCompanions()
    {
        var d = new VpkModelDecision(false, 1, false);
        Assert.False(d.BuildsSkeletonPackage); Assert.False(d.GenerateAnimation);
    }
    [Fact] public void FullAnimationDefaultsToTwoWorkers()
    {
        Assert.Equal(2, new VpkModelDecision(true, 1, true).AnimationThreads);
        Assert.Equal(2, new VpkModelDecision(false, 1, true, SingleHd2Skeleton: true).AnimationThreads);
        Assert.Equal(4, new VpkModelDecision(true, 1, true, AnimationThreads: 4).AnimationThreads);
    }
    [Theory]
    [InlineData("1", 1)] [InlineData("2", 2)] [InlineData("16", 16)] [InlineData(" 3 ", 3)]
    public void ThreadCountAcceptsSupportedIntegers(string text, int expected)
        => Assert.Equal(expected, AnimationThreadCount.Parse(text));

    [Theory]
    [InlineData(null)] [InlineData("")] [InlineData(" ")] [InlineData("0")]
    [InlineData("-1")] [InlineData("17")] [InlineData("2.5")] [InlineData("abc")]
    [InlineData("999999999999")]
    public void ThreadCountRejectsInvalidInput(string? text)
        => Assert.ThrowsAny<ArgumentException>(() => AnimationThreadCount.Parse(text));

    [Fact] public void ModelDecisionHasNoPerModelWristWeightChoice()
    {
        Assert.Null(typeof(VpkModelDecision).GetProperty("MergeWristWeights"));
    }

    [Theory]
    [InlineData(VpkImportRoute.OriginalFormat, false, false, false)]
    [InlineData(VpkImportRoute.SingleSkeleton, false, true, true)]
    [InlineData(VpkImportRoute.DualSkeletonWithLua, true, false, true)]
    public void ImportRouteHasExplicitIndependentDecision(VpkImportRoute route,
        bool native, bool single, bool animation)
    {
        var d = VpkModelDecision.ForImportRoute(route, 1.08, 4);
        Assert.Equal(native, d.UseNativeSkeleton);
        Assert.Equal(single, d.SingleHd2Skeleton);
        Assert.Equal(animation, d.GenerateAnimation);
        Assert.Equal(native || single, d.BuildsSkeletonPackage);
        Assert.Equal(1.08, d.ModelScale);
        Assert.Equal(animation ? 4 : AnimationThreadCount.Default, d.AnimationThreads);
    }

    [Fact]
    public void InvalidImportRouteCannotFallBackToSkeletonConversion()
        => Assert.Throws<ArgumentOutOfRangeException>(() =>
            VpkModelDecision.ForImportRoute((VpkImportRoute)999, 1));
}

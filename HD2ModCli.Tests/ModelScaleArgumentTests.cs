using HD2ModCli;
using Xunit;

namespace HD2ModCli.Tests;

public sealed class ModelScaleArgumentTests
{
    [Fact]
    public void DefaultAndExplicitScale()
    {
        Assert.Equal(1,CliArgumentParser.Parse(["vpk2patch","test.vpk"]).Options.ModelScale);
        Assert.Equal(1.2,CliArgumentParser.Parse(["vpk2patch","test.vpk","--model-scale","1.2"]).Options.ModelScale);
    }

    [Fact]
    public void SingleRouteIsExplicitAndCannotMixWithSourceRig()
    {
        Assert.False(CliArgumentParser.Parse(["vpk2patch","test.vpk"]).Options.SingleHd2Skeleton);
        var o=CliArgumentParser.Parse(["vpk2patch","test.vpk","--single-hd2-skeleton"]).Options;
        Assert.True(o.SingleHd2Skeleton);Assert.False(o.SourceSkeleton);
        Assert.Throws<CliUserException>(()=>CliArgumentParser.Parse(
            ["vpk2patch","test.vpk","--single-hd2-skeleton","--source-skeleton"]));
    }

    [Theory]
    [InlineData("0")][InlineData("-1")][InlineData("11")][InlineData("NaN")][InlineData("Infinity")][InlineData("1,2")]
    public void InvalidScaleIsRejected(string scale)
        => Assert.Throws<CliUserException>(() => CliArgumentParser.Parse(["vpk2patch","test.vpk","--model-scale",scale]));
}

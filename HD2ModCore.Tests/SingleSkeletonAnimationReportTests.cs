using System.Text.Json;
using HD2ModManager.Services;
using Xunit;

namespace HD2ModCore.Tests;
public sealed class SingleSkeletonAnimationReportTests
{
    private static Dictionary<string,object> Report() => new()
    {
        ["status"]="complete", ["pipelineVersion"]="1.0.17", ["skeleton"]="hd2",
        ["sourceRigRetained"]=false, ["attachmentLua"]=false, ["attachmentSwap"]=false,
        ["boneCount"]=90, ["available_animations"]=2, ["expected_animations"]=2, ["animations"]=new[]{new{id="a"},new{id="b"}},
        ["armRetargetPolicy"]="bind-relative-arm-v1", ["armIKChains"]=new[]{"l_hand","r_hand"},
        ["armRetargetSamples"]=120,
    };
    [Fact] public void NewCompleteReportIsAccepted() => SingleSkeletonAnimationReport.Validate(JsonSerializer.Serialize(Report()));
    [Theory]
    [InlineData("pipelineVersion", "1.0.16")]
    [InlineData("armRetargetPolicy", "fk-target")]
    [InlineData("status", "failed")]
    public void OldOrWrongPolicyIsRejected(string key,string value)
    { var r=Report();r[key]=value;Assert.Throws<InvalidDataException>(()=>SingleSkeletonAnimationReport.Validate(JsonSerializer.Serialize(r))); }
    [Theory]
    [InlineData("armIKChains")]
    [InlineData("armRetargetSamples")]
    [InlineData("boneCount")]
    [InlineData("sourceRigRetained")]
    public void MissingContractIsRejected(string key)
    { var r=Report();r.Remove(key);Assert.Throws<InvalidDataException>(()=>SingleSkeletonAnimationReport.Validate(JsonSerializer.Serialize(r))); }
    [Fact] public void EmptyOrDuplicateHandsAreRejected()
    { foreach(var hands in new[]{Array.Empty<string>(),new[]{"l_hand","l_hand"}}){var r=Report();r["armIKChains"]=hands;Assert.Throws<InvalidDataException>(()=>SingleSkeletonAnimationReport.Validate(JsonSerializer.Serialize(r)));} }
    [Theory]
    [InlineData("armRetargetSamples", 0)]
    [InlineData("expected_animations", 3)]
    [InlineData("boneCount", 183)]
    public void EmptyProcessingIncompleteOrMixedIsRejected(string key,int value)
    {var r=Report();r[key]=value;Assert.Throws<InvalidDataException>(()=>SingleSkeletonAnimationReport.Validate(JsonSerializer.Serialize(r)));}
    [Fact] public void FullGuiBuildCannotAcceptASampleReport()
    {var r=Report();r["available_animations"]=3180;r["sampleOnly"]=true;Assert.Throws<InvalidDataException>(()=>SingleSkeletonAnimationReport.Validate(JsonSerializer.Serialize(r)));}
    [Fact] public void ExplicitDiagnosticSamplingIsAccepted()
    {var r=Report();r["available_animations"]=3180;r["sampleOnly"]=true;SingleSkeletonAnimationReport.Validate(JsonSerializer.Serialize(r),allowSample:true);}
    [Fact] public void TruncatedOutputCannotMasqueradeAsFullEvenWhenSamplingAllowed()
    {var r=Report();r["available_animations"]=3180;Assert.Throws<InvalidDataException>(()=>SingleSkeletonAnimationReport.Validate(JsonSerializer.Serialize(r),allowSample:true));}

}

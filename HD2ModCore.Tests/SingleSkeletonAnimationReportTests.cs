using System.Text.Json;
using HD2ModManager.Services;
using Xunit;
namespace HD2ModCore.Tests;
public sealed class SingleSkeletonAnimationReportTests
{
    private static Dictionary<string,object> Report()=>new()
    {
        ["status"]="complete",["pipelineVersion"]="1.0.20",["skeleton"]="hd2",
        ["processor"]="anim_batch_mod.batch.build_batch_entries",["processingProfile"]="standard-single-v3-normal-reference",
        ["sourceRigRetained"]=false,["attachmentLua"]=false,["attachmentSwap"]=false,
        ["preserveHandBendFrame"]=false,["preserveSourceKeyTimes"]=false,["preserveUnchangedBytes"]=true,
        ["playbackRevision"]="normal-reference-r2",["frameTimePolicy"]="user-normal-pack-template",
        ["preservePlaybackTiming"]=false,["preserveReferencePlayback"]=true,
        ["referencePlaybackSha256"]="4030765f8066141df8ecd0440322d128a4827d2cf9f5064a3a918b34eaefbf18",
        ["referencePlaybackBundleSha256"]="5df2f22b11bba8b30ffa4a231c6c56949ada67b66d56b429482e260e052ddc5a",["referencePlaybackClips"]=3180,
        ["boneCount"]=90,["available_animations"]=3180,["expected_animations"]=3180,["animations"]=Enumerable.Range(0,3180).Select(i=>new{id=i.ToString()}).ToArray(),
        ["options"]=new{ik_correction=true,source_arm_constraints=true},
        ["preserveUnmodifiedChannels"]=false,["controlMarkerPolicy"]="original-hd2-local-v1",
        ["armTargetPolicy"]="source-angle-standard-ray-v1",["armTargetProjections"]=60,["armRequestedTargetMaxDistance"]=.12,["ikEvaluations"]=120,
        ["ikChains"]=new Dictionary<string,object>{["l_hand"]=new{chain=new[]{"l_shoulder","l_elbow"},target_multiplier=new[]{.4,.4,1.0}},["r_hand"]=new{chain=new[]{"r_shoulder","r_elbow"},target_multiplier=new[]{.4,.4,1.0}},["l_foot"]=new{chain=new[]{"l_thigh","l_knee"},target_multiplier=new[]{.4,.4,1.0}},["r_foot"]=new{chain=new[]{"r_thigh","r_knee"},target_multiplier=new[]{.4,.4,1.0}}}
    };
    [Theory][InlineData("preserveSourceKeyTimes",true)][InlineData("preserveUnmodifiedChannels",true)][InlineData("preservePlaybackTiming",true)][InlineData("preserveReferencePlayback",false)]
    public void WrongPlaybackFlagsRejected(string key,bool value){var r=Report();r[key]=value;Assert.Throws<InvalidDataException>(()=>SingleSkeletonAnimationReport.Validate(JsonSerializer.Serialize(r)));}
    [Theory][InlineData("referencePlaybackSha256","wrong")][InlineData("referencePlaybackBundleSha256","bad")]
    public void UncertifiedReferenceRejected(string key,string value){var r=Report();r[key]=value;Assert.Throws<InvalidDataException>(()=>SingleSkeletonAnimationReport.Validate(JsonSerializer.Serialize(r)));}
    [Fact]public void StandardReportIsAccepted()=>SingleSkeletonAnimationReport.Validate(JsonSerializer.Serialize(Report()));
    [Theory][InlineData("pipelineVersion","1.0.19")][InlineData("playbackRevision","native-clock-r1")][InlineData("frameTimePolicy","native-duration-f32-timestamps-v1")][InlineData("pipelineVersion","1.0.18")][InlineData("pipelineVersion","1.0.17")][InlineData("processingProfile","bind-relative-arm-v1")][InlineData("processor","dual")][InlineData("status","failed")]
    public void OldOrMixedPolicyIsRejected(string key,string value){var r=Report();r[key]=value;Assert.Throws<InvalidDataException>(()=>SingleSkeletonAnimationReport.Validate(JsonSerializer.Serialize(r)));}
    [Theory][InlineData("playbackRevision")][InlineData("frameTimePolicy")][InlineData("preserveReferencePlayback")][InlineData("preservePlaybackTiming")][InlineData("referencePlaybackSha256")][InlineData("referencePlaybackBundleSha256")][InlineData("referencePlaybackClips")][InlineData("ikChains")][InlineData("ikEvaluations")][InlineData("boneCount")][InlineData("sourceRigRetained")][InlineData("preserveSourceKeyTimes")][InlineData("controlMarkerPolicy")][InlineData("preserveUnmodifiedChannels")][InlineData("armTargetProjections")][InlineData("armRequestedTargetMaxDistance")]
    public void MissingContractIsRejected(string key){var r=Report();r.Remove(key);Assert.Throws<InvalidDataException>(()=>SingleSkeletonAnimationReport.Validate(JsonSerializer.Serialize(r)));}
    [Theory][InlineData("ikEvaluations",0)][InlineData("expected_animations",3)][InlineData("boneCount",183)][InlineData("available_animations",2)][InlineData("referencePlaybackClips",2)]
    public void InvalidCountsAreRejected(string key,int value){var r=Report();r[key]=value;Assert.Throws<InvalidDataException>(()=>SingleSkeletonAnimationReport.Validate(JsonSerializer.Serialize(r)));}
    [Fact]public void MissingFootChainIsRejected(){var r=Report();((Dictionary<string,object>)r["ikChains"]).Remove("l_foot");Assert.Throws<InvalidDataException>(()=>SingleSkeletonAnimationReport.Validate(JsonSerializer.Serialize(r)));}
    [Fact]public void HandOnlyExperimentalReportIsRejected(){var r=Report();r["ikChains"]=new Dictionary<string,object>();Assert.Throws<InvalidDataException>(()=>SingleSkeletonAnimationReport.Validate(JsonSerializer.Serialize(r)));}
    [Fact]public void FullGuiCannotAcceptSample(){var r=Report();r["available_animations"]=3180;r["sampleOnly"]=true;Assert.Throws<InvalidDataException>(()=>SingleSkeletonAnimationReport.Validate(JsonSerializer.Serialize(r)));}
    [Fact]public void ExplicitDiagnosticSamplingIsAccepted(){var r=Report();r["available_animations"]=3180;r["expected_animations"]=2;r["animations"]=new[]{new{id="a"},new{id="b"}};r["sampleOnly"]=true;SingleSkeletonAnimationReport.Validate(JsonSerializer.Serialize(r),true);}
    [Fact]public void TruncationCannotMasqueradeAsFull(){var r=Report();r["available_animations"]=3180;r["expected_animations"]=2;r["animations"]=new[]{new{id="a"},new{id="b"}};Assert.Throws<InvalidDataException>(()=>SingleSkeletonAnimationReport.Validate(JsonSerializer.Serialize(r),true));}
    private static Dictionary<string,object> OptimizedReport()
    {
        var r=Report();r["pipelineVersion"]="1.0.21";
        r["outputEncodingProfile"]="single-constant-float-boundary2-v1";
        r["preserveDenseFrames"]=false;r["preserveRetainedKeyBytes"]=true;
        r["preserveOriginalScaleRecords"]=true;r["additiveBytePassthrough"]=true;r["boundaryFramesEachEnd"]=2;
        r["constantTrackEquality"]="serialized-exact-no-epsilon-no-quaternion-sign-folding";
        r["animationCompaction"]=new Dictionary<string,object>{["profile"]="single-constant-float-boundary2-v1",["verified"]=true,
            ["clips"]=3180,["normalClips"]=2993,["additiveClips"]=187,["boundaryFramesEachEnd"]=2,
            ["originalBytes"]=1109304724L,["outputBytes"]=400000000L,["removedBytes"]=709304724L,["removedKeysOneBlock"]=1000L};
        return r;
    }
    [Fact]public void AcceptedCompactionReportIsAccepted()=>SingleSkeletonAnimationReport.Validate(JsonSerializer.Serialize(OptimizedReport()));
    [Theory][InlineData("outputEncodingProfile")][InlineData("preserveDenseFrames")][InlineData("preserveRetainedKeyBytes")][InlineData("preserveOriginalScaleRecords")][InlineData("additiveBytePassthrough")][InlineData("boundaryFramesEachEnd")][InlineData("constantTrackEquality")][InlineData("animationCompaction")]
    public void IncompleteCompactionContractIsRejected(string key){var r=OptimizedReport();r.Remove(key);Assert.Throws<InvalidDataException>(()=>SingleSkeletonAnimationReport.Validate(JsonSerializer.Serialize(r)));}
    [Theory][InlineData("preserveDenseFrames",true)][InlineData("preserveRetainedKeyBytes",false)][InlineData("preserveOriginalScaleRecords",false)][InlineData("additiveBytePassthrough",false)]
    public void UnsafeCompactionFlagsRejected(string key,bool value){var r=OptimizedReport();r[key]=value;Assert.Throws<InvalidDataException>(()=>SingleSkeletonAnimationReport.Validate(JsonSerializer.Serialize(r)));}
    [Theory][InlineData("clips",3179)][InlineData("normalClips",2992)][InlineData("additiveClips",-1)][InlineData("boundaryFramesEachEnd",1)][InlineData("removedBytes",1)][InlineData("originalBytes",0)][InlineData("outputBytes",0)][InlineData("removedKeysOneBlock",-1)]
    public void InconsistentCompactionCountsRejected(string key,int value){var r=OptimizedReport();((Dictionary<string,object>)r["animationCompaction"])[key]=value;Assert.Throws<InvalidDataException>(()=>SingleSkeletonAnimationReport.Validate(JsonSerializer.Serialize(r)));}
    [Fact]public void UnverifiedCompactionRejected(){var r=OptimizedReport();((Dictionary<string,object>)r["animationCompaction"])["verified"]=false;Assert.Throws<InvalidDataException>(()=>SingleSkeletonAnimationReport.Validate(JsonSerializer.Serialize(r)));}
    [Fact]public void TestCompactionProfileRejected(){var r=OptimizedReport();r["outputEncodingProfile"]="single-size-test-constant-float-boundary2-v1";Assert.Throws<InvalidDataException>(()=>SingleSkeletonAnimationReport.Validate(JsonSerializer.Serialize(r)));}
    [Fact]public void LegacyCannotClaimOptimizedOutput(){var r=OptimizedReport();r["pipelineVersion"]="1.0.20";Assert.Throws<InvalidDataException>(()=>SingleSkeletonAnimationReport.Validate(JsonSerializer.Serialize(r)));}
    [Fact]public void NewVersionCannotOmitOutputContract(){var r=Report();r["pipelineVersion"]="1.0.21";Assert.Throws<InvalidDataException>(()=>SingleSkeletonAnimationReport.Validate(JsonSerializer.Serialize(r)));}

}

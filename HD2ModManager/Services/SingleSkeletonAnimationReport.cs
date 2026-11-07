using System.IO;
using System.Linq;
using System.Text.Json;

namespace HD2ModManager.Services;

/// <summary>Commit only the control-safe standalone single processor with real IK diagnostics.</summary>
internal static class SingleSkeletonAnimationReport
{
    internal static void Validate(string json, bool allowSample = false)
    {
        using var document = JsonDocument.Parse(json);
        var root = document.RootElement;
        bool Text(string name,string value) => root.TryGetProperty(name,out var item) && item.ValueKind==JsonValueKind.String && item.GetString()==value;
        bool Flag(string name,bool value) => root.TryGetProperty(name,out var item) && item.ValueKind==(value?JsonValueKind.True:JsonValueKind.False);
        bool Number(string name,out int value)
        {value=0;return root.TryGetProperty(name,out var item) && item.ValueKind==JsonValueKind.Number && item.TryGetInt32(out value);}
        var built=root.TryGetProperty("animations",out var animations) && animations.ValueKind==JsonValueKind.Array?animations.GetArrayLength():-1;
        var sampleOnly=root.TryGetProperty("sampleOnly",out var sample) && sample.ValueKind==JsonValueKind.True;
        var valid=Text("status","complete") && Text("pipelineVersion","1.0.20") && Text("skeleton","hd2")
            && Text("processor","anim_batch_mod.batch.build_batch_entries") && Text("processingProfile","standard-single-v3-normal-reference")
            && Text("playbackRevision","normal-reference-r2") && Text("frameTimePolicy","user-normal-pack-template")
            && Flag("preservePlaybackTiming",false) && Flag("preserveReferencePlayback",true)
            && Text("referencePlaybackSha256","4030765f8066141df8ecd0440322d128a4827d2cf9f5064a3a918b34eaefbf18")
            && Text("referencePlaybackBundleSha256","5df2f22b11bba8b30ffa4a231c6c56949ada67b66d56b429482e260e052ddc5a")
            && Number("referencePlaybackClips",out var templates) && templates==3180
            && Text("controlMarkerPolicy","original-hd2-local-v1") && Flag("preserveUnmodifiedChannels",false)
            && Flag("sourceRigRetained",false) && Flag("attachmentLua",false) && Flag("attachmentSwap",false)
            && Flag("preserveHandBendFrame",false) && Flag("preserveSourceKeyTimes",false) && Flag("preserveUnchangedBytes",true)
            && Number("boneCount",out var bones) && bones==90
            && Number("expected_animations",out var expected) && expected>0 && expected==built
            && Number("available_animations",out var available) && available==3180 && available>=expected
            && (allowSample || (!sampleOnly && available==expected)) && (available==expected || sampleOnly)
            && root.TryGetProperty("ikChains",out var chainDocument) && chainDocument.ValueKind==JsonValueKind.Object;
        var targets=new[]{"l_hand","r_hand","l_foot","r_foot"};
        if(valid)
        {
            var chains=root.GetProperty("ikChains");
            foreach(var target in targets)
            {
                if(!chains.TryGetProperty(target,out var row) || row.ValueKind!=JsonValueKind.Object
                    || !row.TryGetProperty("chain",out var chain) || chain.ValueKind!=JsonValueKind.Array || chain.GetArrayLength()!=2
                    || chain.EnumerateArray().Any(x=>x.ValueKind!=JsonValueKind.String)
                    || !row.TryGetProperty("target_multiplier",out var multiplier) || multiplier.ValueKind!=JsonValueKind.Array || multiplier.GetArrayLength()!=3
                    || multiplier.EnumerateArray().Any(x=>x.ValueKind!=JsonValueKind.Number || !x.TryGetDouble(out var n) || !double.IsFinite(n)))
                {valid=false;break;}
            }
        }
        var ikEnabled=false;
        if(!root.TryGetProperty("options",out var options) || options.ValueKind!=JsonValueKind.Object
            || !options.TryGetProperty("ik_correction",out var ik) || ik.ValueKind is not (JsonValueKind.True or JsonValueKind.False))valid=false;
        else ikEnabled=ik.GetBoolean();
        if (options.ValueKind == JsonValueKind.Object)
        {
            if (!options.TryGetProperty("source_arm_constraints", out var sourceArm)
                || sourceArm.ValueKind is not (JsonValueKind.True or JsonValueKind.False)
                || !Text("armTargetPolicy", sourceArm.ValueKind == JsonValueKind.True
                    ? "source-angle-standard-ray-v1" : "legacy-world")) valid = false;
        }
        if (!Number("armTargetProjections", out var projections) || projections < 0
            || !root.TryGetProperty("armRequestedTargetMaxDistance", out var displacement)
            || displacement.ValueKind != JsonValueKind.Number || !displacement.TryGetDouble(out var deviation) || !double.IsFinite(deviation) || deviation < 0) valid = false;
        if(!Number("ikEvaluations",out var evaluations) || evaluations<0 || (ikEnabled && evaluations==0))valid=false;
        if(!valid)throw new InvalidDataException("单骨架动画缺少1.0.20正常包R2播放模板契约、标准手脚IK或来源约束偏差记录；旧版错误绑定和不完整动画不能入库。");
    }
}

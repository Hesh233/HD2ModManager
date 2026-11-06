using System.IO;
using System.Linq;
using System.Text.Json;

namespace HD2ModManager.Services;

/// <summary>The single route must not commit an old or silently empty arm contract.</summary>
internal static class SingleSkeletonAnimationReport
{
    internal static void Validate(string json, bool allowSample = false)
    {
        using var document = JsonDocument.Parse(json);
        var root = document.RootElement;
        bool Text(string name, string value) => root.TryGetProperty(name, out var item)
            && item.ValueKind == JsonValueKind.String && item.GetString() == value;
        bool False(string name) => root.TryGetProperty(name, out var item) && item.ValueKind == JsonValueKind.False;
        bool Number(string name, out int value)
        { value = 0; return root.TryGetProperty(name, out var item) && item.ValueKind == JsonValueKind.Number && item.TryGetInt32(out value); }
        var ids = root.TryGetProperty("animations", out var animations) && animations.ValueKind == JsonValueKind.Array
            ? animations.GetArrayLength() : -1;
        var hands = root.TryGetProperty("armIKChains", out var chains) && chains.ValueKind == JsonValueKind.Array
            ? chains.EnumerateArray().Where(x => x.ValueKind == JsonValueKind.String).Select(x => x.GetString()).ToArray() : [];
        var sampleOnly = root.TryGetProperty("sampleOnly", out var sample) && sample.ValueKind == JsonValueKind.True;
        if (!Text("status", "complete") || !Text("pipelineVersion", "1.0.17") || !Text("skeleton", "hd2")
            || !Text("armRetargetPolicy", "bind-relative-arm-v1") || !False("sourceRigRetained")
            || !False("attachmentLua") || !False("attachmentSwap") || !Number("boneCount", out var bones) || bones != 90
            || !Number("expected_animations", out var expected) || expected <= 0 || expected != ids
            || !Number("available_animations", out var available) || available < expected
            || (!allowSample && (sampleOnly || available != expected))
            || (available != expected && !sampleOnly)
            || hands.Length != 2 || !hands.Contains("l_hand") || !hands.Contains("r_hand")
            || !Number("armRetargetSamples", out var samples) || samples <= 0)
            throw new InvalidDataException("单骨架动画报告缺少有效的左右手臂重定向契约；请使用新版工具重新导入模型并生成配套动画，不能入库旧版或空 IK 动画。");
    }
}


using System.Text.Json;
using System.Text;
using System.Security.Cryptography;
using System.Text.Json.Serialization;
using HD2ModAdaptation.PatchReconstruction.UnitMesh;
using HD2SourceModel;
using HD2SourceMigration.VpkConversion;

namespace HD2SourceMigration.Retarget;

/// <summary>Preserve the Source bind rig. HD2 nodes remain as animation drivers;
/// every Source node gets its own hash and its original parent, axes and weights.</summary>
public sealed record NativeSourceNode(int SourceIndex, string Name, uint Hash, int? Parent,
    string? Driver, float[] World, UnitLocalTransform Local, bool Physics = false, string? SourceName = null);

public sealed record NativeMotionLayer(string Name, uint Hash, string Driver, uint DriverHash,
    int DriverUnitIndex, uint ParentHash);

public sealed record NativeSourceManifest(int Version, string ReferenceArchive, string ReferenceUnit,
    IReadOnlyList<NativeSourceNode> Bones, IReadOnlyList<uint> DriverHashes,
    IReadOnlyList<UnitTransformMatrix> DriverWorld, double ModelScale = 1,
    double SourceGroundMetres = 0, string ScaleOrigin = "source", string BoneNamespace = "",
    [property: JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] IReadOnlyList<NativeMotionLayer>? MotionLayers = null,
    [property: JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] IReadOnlyDictionary<int, int>? MotionParentOverrides = null,
    [property: JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] IReadOnlyDictionary<int, UnitLocalTransform>? MotionLocalOverrides = null,
    [property: JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] string? RetargetHierarchy = null);

public sealed record NativeSourceConversion(RetargetResult Result, UnitTransformInfo Transforms,
    NativeSourceManifest Manifest)
{
    public void WriteManifest(string directory)
    {
        Directory.CreateDirectory(directory);
        File.WriteAllText(Path.Combine(directory, "source-skeleton.json"), JsonSerializer.Serialize(Manifest,
            new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase, WriteIndented = true }));
    }
}

public static class NativeSourceSkeleton
{
    // Source and HD2 both use Z up. No pose fitting, height normalization or regional scaling.
    private static readonly Mat4 Alignment = new(-1, 0, 0, 0, 0, -1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1);

    public static NativeSourceConversion Convert(RetargetInputs inputs, Hd2Rig rig, UnitTransformInfo avatar, double modelScale = 1)
    {
        if (!double.IsFinite(modelScale) || modelScale <= 0 || modelScale > 10)
            throw new ArgumentOutOfRangeException(nameof(modelScale), "模型大小倍率必须大于 0 且不超过 10。");
        var source = inputs.Model.Bones;
        if (source.Count == 0 || avatar.NameHashes.Count == 0)
            throw new InvalidDataException("原生骨架转换需要来源骨架与 HD2 avatar 骨架。");
        if (avatar.LocalTransforms.Count != avatar.NameHashes.Count
            || avatar.Matrices.Count != avatar.NameHashes.Count || avatar.Entries.Count != avatar.NameHashes.Count
            || avatar.NameHashes.Count + source.Count > ushort.MaxValue)
            throw new InvalidDataException("avatar 骨架表不完整或追加后超过 Unit 父下标范围。");
        foreach (var vertex in inputs.Geometry.Vertices)
        {
            var weights = new[] { vertex.Weight0, vertex.Weight1, vertex.Weight2 };
            if (weights.Any(w => !float.IsFinite(w.Weight) || w.Weight < 0
                || (w.Weight > 0 && (w.BoneIndex < 0 || w.BoneIndex >= source.Count)))
                || weights.Sum(w => w.Weight) <= 0)
                throw new InvalidDataException("来源顶点包含无效骨权重，不能静默丢弃后宣称保留骨架。");
        }
        var byIndex = source.ToDictionary(b => b.Index);
        if (!Enumerable.Range(0, source.Count).All(byIndex.ContainsKey))
            throw new InvalidDataException("来源骨架下标不连续。");
        var ordered = new List<int>();
        var visiting = new HashSet<int>();
        var visited = new HashSet<int>();
        void Visit(int index)
        {
            if (visited.Contains(index)) return;
            if (!visiting.Add(index)) throw new InvalidDataException("来源骨架父子关系有环。");
            var parent = byIndex[index].ParentIndex;
            if (parent >= 0)
            {
                if (!byIndex.ContainsKey(parent)) throw new InvalidDataException("来源骨架父下标越界。");
                Visit(parent);
            }
            visiting.Remove(index);
            visited.Add(index);
            ordered.Add(index);
        }
        foreach (var bone in source) Visit(bone.Index);
        var ranks = ordered.Select((index, rank) => (index, rank)).ToDictionary(p => p.index, p => p.rank);
        var pairs = SourceToHd2RigMap.Correspondence.ToDictionary(p => p.SourceBone, p => p.Hd2Node);
        var drivers = new Dictionary<int, int>();
        var driverNames = new Dictionary<int, string>();
        foreach (var bone in source)
        {
            var name = bone.DisplayName;
            var shortName = name.StartsWith(SourceToHd2RigMap.SourceBonePrefix, StringComparison.Ordinal)
                ? name[SourceToHd2RigMap.SourceBonePrefix.Length..] : name;
            if (pairs.TryGetValue(shortName, out var target) && rig.Find(target) is { } driver)
            {
                drivers[bone.Index] = driver.Index;
                driverNames[bone.Index] = target;
            }
        }
        if (drivers.Count == 0) throw new InvalidDataException("没有找到可驱动的 ValveBiped 骨骼。");
        var resolved = new Dictionary<int, int>(drivers); // segmentation only, never used to merge weights
        foreach (var index in ordered)
        {
            if (!resolved.ContainsKey(index))
                resolved[index] = byIndex[index].ParentIndex >= 0
                    ? resolved[byIndex[index].ParentIndex] : rig.Find("hips")?.Index ?? 0;
        }
        if (inputs.Geometry.Vertices.Count == 0)
            throw new InvalidDataException("原生骨架转换需要网格顶点来确定脚底平面。");
        var ground = inputs.Geometry.Vertices.Min(v => v.Position.Z) * RetargetConstants.InchesToMetres;
        if (!double.IsFinite(ground)) throw new InvalidDataException("模型脚底坐标不是有限值。");
        // Keep the source origin. Ground rebasing changed the authored stance;
        // scale the source geometry and bind together without an extra translation.
        var alignment = Alignment;
        var signature = string.Join("\n", source.Select(b => $"{b.Index}:{b.ParentIndex}:{b.DisplayName}"));
        var boneNamespace = "hd2n_" + ConvertHash(signature);
        var worlds = source.ToDictionary(b => b.Index,
            b => alignment * RetargetMath.ScaleTranslation(b.WorldBind, RetargetConstants.InchesToMetres * modelScale));
        var locals = avatar.LocalTransforms.ToList();
        var matrices = avatar.Matrices.ToList();
        var entries = avatar.Entries.ToList();
        var hashes = avatar.NameHashes.ToList();
        var usedHashes = hashes.ToHashSet();
        var nodes = new List<NativeSourceNode>();
        var physicsNodes = new HashSet<int>();
        var targets = new Dictionary<int, int>();
        var shipped = rig.Bones.ToDictionary(b => b.Index, b => b.WorldBind);
        foreach (var index in ordered)
        {
            var bone = byIndex[index];
            var physics = bone.Jiggle is not null || physicsNodes.Contains(bone.ParentIndex);
            if (physics)
            {
                if (driverNames.ContainsKey(index))
                    throw new InvalidDataException($"物理骨分支包含动画驱动骨：{bone.DisplayName}");
                physicsNodes.Add(index);
            }
            var role = physics ? "phys" : driverNames.ContainsKey(index) ? "anim" : "aux";
            var label = driverNames.GetValueOrDefault(index) ?? bone.DisplayName;
            label = new string(label.ToLowerInvariant().Select(c => char.IsAsciiLetterOrDigit(c) ? c : '_').ToArray());
            var exportName = $"{boneNamespace}_{role}_{index:D3}_{label}";
            var hash = Hd2NameHash.Of(exportName);
            if (!usedHashes.Add(hash))
                throw new InvalidDataException($"来源骨名重复或与 HD2 哈希冲突：{bone.DisplayName}");
            var parent = bone.ParentIndex < 0 ? 0 : avatar.NameHashes.Count + ranks[bone.ParentIndex];
            var parentWorld = bone.ParentIndex < 0 ? rig.Bones.Single(b => b.Index == 0).WorldBind : worlds[bone.ParentIndex];
            var local = ToLocal(parentWorld.Inverse() * worlds[index]);
            var world = ToRow(worlds[index]);
            targets[index] = hashes.Count;
            shipped[hashes.Count] = worlds[index];
            locals.Add(local);
            matrices.Add(new UnitTransformMatrix(world));
            entries.Add(new UnitTransformEntry(1, checked((ushort)parent)));
            hashes.Add(hash);
            nodes.Add(new NativeSourceNode(index, exportName, hash,
                bone.ParentIndex < 0 ? null : ranks[bone.ParentIndex], driverNames.GetValueOrDefault(index), world, local, physics, bone.DisplayName));
        }
        List<NativeMotionLayer>? motionLayers = null;
        Dictionary<int, int>? motionParents = null;
        Dictionary<int, UnitLocalTransform>? motionLocals = null;
        // Separate root/boss blend layers from the pelvis and lower spine. Their original
        // source metadata remains intact for retargeting; only the published hierarchy changes.
        if (rig.Find("root") is { } root && rig.Find("boss") is { } boss
            && nodes.Any(n => n.Driver == "hips") && nodes.Any(n => n.Driver == "spine1"))
        {
            if (hashes.Count + 2 > ushort.MaxValue)
                throw new InvalidDataException("追加运动层后超过 Unit 父下标范围。");
            foreach (var driver in new[] { root, boss })
                if (driver.Index < 0 || driver.Index >= avatar.NameHashes.Count
                    || avatar.NameHashes[driver.Index] != Hd2NameHash.Of(driver.Name!))
                    throw new InvalidDataException("运动层驱动骨与 avatar 变换表不一致。");
            var rootParent = avatar.Entries[root.Index].ParentIndex;
            if (rootParent >= avatar.NameHashes.Count || rootParent == root.Index)
                throw new InvalidDataException("运动层 root 必须具有独立的实体父节点。");
            motionLayers = [];
            motionParents = [];
            motionLocals = [];
            var helperStart = hashes.Count;
            foreach (var driver in new[] { root, boss })
            {
                var parent = motionLayers.Count == 0 ? rootParent : helperStart;
                var name = $"__hd2_motion__{boneNamespace}_{driver.Name}";
                var hash = Hd2NameHash.Of(name);
                if (!usedHashes.Add(hash))
                    throw new InvalidDataException($"运动层骨名与现有骨骼哈希冲突：{name}");
                motionLayers.Add(new NativeMotionLayer(name, hash, driver.Name!,
                    avatar.NameHashes[driver.Index], driver.Index, hashes[parent]));
                locals.Add(ToLocal(shipped[parent].Inverse() * driver.WorldBind));
                matrices.Add(avatar.Matrices[driver.Index]);
                entries.Add(new UnitTransformEntry(1, checked((ushort)parent)));
                shipped[hashes.Count] = driver.WorldBind;
                hashes.Add(hash);
            }
            for (var rank = 0; rank < nodes.Count; rank++)
            {
                if (nodes[rank].Driver is not ("hips" or "spine1")) continue;
                var index = avatar.NameHashes.Count + rank;
                var local = ToLocal(boss.WorldBind.Inverse() * worlds[nodes[rank].SourceIndex]);
                motionParents[rank] = 1;
                motionLocals[rank] = local;
                locals[index] = local;
                entries[index] = entries[index] with { ParentIndex = checked((ushort)(helperStart + 1)) };
            }
        }
        var transforms = new UnitTransformInfo(avatar.Reserved0, avatar.Reserved1, avatar.Reserved2,
            locals, matrices, entries, hashes);
        UnitTransformInfoAppender.AssertLocalAndWorldAgree(transforms, avatar.NameHashes.Count);
        var points = inputs.Geometry.Vertices.Select(v => v.Position * (RetargetConstants.InchesToMetres * modelScale)).ToArray();
        var output = points.Select(alignment.TransformPoint).ToArray();
        var metrics = new RetargetMetrics(1, 0, 0, 0, 0, 0, 0, 0, 0, 0, [], new Dictionary<int, int>());
        var result = new RetargetResult(points, output, output, output, shipped, shipped,
            new Dictionary<int, Mat4>(), resolved, new Dictionary<int, int>(), [], [],
            new Dictionary<string, double>(), [], targets, new Dictionary<string, string>(), metrics)
        { SourceNativeTransforms = transforms };
        return new NativeSourceConversion(result, transforms,
            new NativeSourceManifest(1, "18235e0c9ec0e636", "0x4d1c334d294dfa97", nodes,
                avatar.NameHashes, avatar.Matrices, modelScale, ground, "source", boneNamespace,
                motionLayers, motionParents, motionLocals,
                motionLayers is null ? null : "native-root-boss-layers-v7"));
    }

    private static string ConvertHash(string value) => System.Convert.ToHexString(
        SHA256.HashData(Encoding.UTF8.GetBytes(value)))[..12].ToLowerInvariant();

    internal static float[] ToRow(Mat4 m) => [(float)m.M11, (float)m.M21, (float)m.M31, 0,
        (float)m.M12, (float)m.M22, (float)m.M32, 0, (float)m.M13, (float)m.M23, (float)m.M33, 0,
        (float)m.M14, (float)m.M24, (float)m.M34, 1];

    internal static UnitLocalTransform ToLocal(Mat4 m)
    {
        var row = ToRow(m);
        if (row.Any(value => !float.IsFinite(value)))
            throw new InvalidDataException("来源 bind 包含非有限值。");
        // Source bind matrices must be rigid for the existing animation quaternion codec.
        for (var i = 0; i < 3; i++)
            for (var j = 0; j < 3; j++)
            {
                var dot = Enumerable.Range(0, 3).Sum(k => row[i * 4 + k] * row[j * 4 + k]);
                if (!float.IsFinite(dot) || Math.Abs(dot - (i == j ? 1 : 0)) > 0.002)
                    throw new InvalidDataException("来源 bind 含缩放或剪切，不能按刚性骨架无损转换。");
            }
        var determinant = row[0] * (row[5] * row[10] - row[6] * row[9])
            - row[1] * (row[4] * row[10] - row[6] * row[8])
            + row[2] * (row[4] * row[9] - row[5] * row[8]);
        if (Math.Abs(determinant - 1) > 0.002)
            throw new InvalidDataException("来源 bind 含镜像，不能编码为刚性旋转四元数。");
        return new UnitLocalTransform([row[0], row[1], row[2], row[4], row[5], row[6], row[8], row[9], row[10]],
            [row[12], row[13], row[14]], [1, 1, 1], 0);
    }
}

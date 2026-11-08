namespace HD2SourceModel;

public sealed record SourceWristWeightMergeBone(int SourceIndex, string SourceName, int TargetIndex, string TargetName);
public sealed record SourceWristWeightMergeSummary(IReadOnlyList<SourceWristWeightMergeBone> Bones, int ChangedVertices);
public sealed record SourceWristWeightMergeResult(SourceGeometry Geometry, SourceWristWeightMergeSummary Summary);

/// <summary>Opt-in geometry-only transfer of procedural wrist helper weights to their forearms.
/// Never changes source bones, native HD2 hands, bind transforms, fingers or VRD rules.</summary>
public static class SourceWristWeightMerger
{
    public static SourceWristWeightMergeResult Merge(SourceModelDocument model, SourceGeometry geometry)
    {
        ArgumentNullException.ThrowIfNull(model);
        ArgumentNullException.ThrowIfNull(geometry);
        var byIndex = model.Bones.ToDictionary(b => b.Index);
        var targets = new Dictionary<int, int>();
        var plan = new List<SourceWristWeightMergeBone>();
        foreach (var bone in model.Bones)
        {
            if (bone.QuatInterp is not { } driver || bone.Jiggle is not null
                || bone.Index == driver.ControlIndex
                || !byIndex.TryGetValue(bone.ParentIndex, out var parent)
                || !byIndex.TryGetValue(driver.ControlIndex, out var control)) continue;
            var parentName = Canonical(parent.Name);
            var controlName = Canonical(control.Name);
            if (!((parentName.Equals("L_Forearm", StringComparison.OrdinalIgnoreCase)
                    && controlName.Equals("L_Hand", StringComparison.OrdinalIgnoreCase))
                || (parentName.Equals("R_Forearm", StringComparison.OrdinalIgnoreCase)
                    && controlName.Equals("R_Hand", StringComparison.OrdinalIgnoreCase)))) continue;
            // A real hand is not an auxiliary wrist, even in an unusual procedural rig.
            var name = Canonical(bone.Name);
            if (name.Equals("L_Hand", StringComparison.OrdinalIgnoreCase)
                || name.Equals("R_Hand", StringComparison.OrdinalIgnoreCase)) continue;
            targets.Add(bone.Index, parent.Index);
            plan.Add(new(bone.Index, bone.DisplayName, parent.Index, parent.DisplayName));
        }
        if (targets.Count == 0) return new(geometry, new(plan, 0));
        var vertices = geometry.Vertices.ToArray();
        var changed = 0;
        for (var i = 0; i < vertices.Length; i++)
        {
            var vertex = vertices[i];
            if (!vertex.Influences().Any(w => targets.ContainsKey(w.BoneIndex))) continue;
            var weights = new List<SourceVertexWeight>(SourceVertex.MaxInfluences);
            foreach (var weight in vertex.Influences())
            {
                if (!float.IsFinite(weight.Weight)) throw new InvalidDataException("Non-finite source wrist weight.");
                var index = targets.GetValueOrDefault(weight.BoneIndex, weight.BoneIndex);
                var existing = weights.FindIndex(w => w.BoneIndex == index);
                if (existing < 0) weights.Add(new(index, weight.Weight));
                else weights[existing] = weights[existing] with { Weight = weights[existing].Weight + weight.Weight };
            }
            // Preserve the total; do not normalize unrelated weights or change the geometry.
            while (weights.Count < SourceVertex.MaxInfluences) weights.Add(new(0, 0));
            vertices[i] = vertex with { Weight0 = weights[0], Weight1 = weights[1], Weight2 = weights[2] };
            changed++;
        }
        return new(geometry with { Vertices = vertices }, new(plan, changed));
    }

    private static string Canonical(string? name)
    {
        var value = name ?? string.Empty;
        if (value.StartsWith("ValveBiped.", StringComparison.OrdinalIgnoreCase)) value = value["ValveBiped.".Length..];
        if (value.StartsWith("Bip01_", StringComparison.OrdinalIgnoreCase)) value = value[6..];
        return value;
    }
}

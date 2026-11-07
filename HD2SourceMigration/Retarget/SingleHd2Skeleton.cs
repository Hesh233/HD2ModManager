using System.Text.Json;
using HD2ModAdaptation.PatchReconstruction.UnitMesh;
using HD2SourceMigration.VpkConversion;
using HD2SourceModel;

namespace HD2SourceMigration.Retarget;

public sealed record SingleHd2BindManifest(int Version, string Policy, double ModelScale,
    IReadOnlyList<uint> DriverHashes, IReadOnlyList<float[]> DriverWorld,
    bool MeshOnlyPostprocessing = false, string ControlMarkerPolicy = "original-hd2-local-v1",
    string ArmSegmentPolicy = "native-axis-source-length-v1");

public sealed record SingleHd2Conversion(RetargetResult Result, SingleHd2BindManifest Manifest)
{
    public void WriteManifest(string directory) => File.WriteAllText(
        Path.Combine(directory, "single-hd2-bind.json"), JsonSerializer.Serialize(Manifest,
            new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase, WriteIndented = true }));
}

/// <summary>Use the existing snap/pose mapper, but ship the bind that actually posed the mesh.
/// No Source driver rig, per-model mesh-only fitting, or object scale survives packaging.</summary>
public static class SingleHd2Skeleton
{
    public const string Policy = "hd2-source-sized-shared-bind-v1";

    public static RetargetOptions Options(double modelScale = 1) => new()
    {
        ModelScale = modelScale,
        Scale = 1,
        AnchorAtGround = true,
        Skeleton = RetargetSkeleton.Snap,
        SnapHeadTip = false,
        SpineMap = RetargetSpineMap.Legacy,
        HeadOffset = 0,
        LegTilt = 0,
        LegSplay = 0,
        ArmScratch = false,
        ArmFit = 0,
        MeshShift = Vec3.Zero,
        GroundLift = 0,
        UpperScale = 1,
        HeadScale = 1,
        FingerPose = false,
        HandReorient = HandReorientMode.Off,
        HandTurn = 0,
        PalmScale = 1,
        PalmScaleAuto = false,
    };

    public static SingleHd2Conversion Convert(RetargetInputs inputs, Hd2Rig rig,
        UnitTransformInfo avatar, double modelScale = 1)
    {
        if (!double.IsFinite(modelScale) || modelScale <= 0 || modelScale > 10)
            throw new ArgumentOutOfRangeException(nameof(modelScale));
        if (avatar.LocalTransforms.Count != avatar.NameHashes.Count ||
            rig.Bones.Count != avatar.NameHashes.Count)
            throw new InvalidDataException("Single HD2 conversion requires the complete avatar bind.");
        // A missing head used to silently divide by 1e-6 and produce an enormous model.
        if (!inputs.Model.Bones.Any(b => b.Name == RetargetConstants.SourceBonePrefix + "Head1") ||
            inputs.Geometry.Vertices.Count == 0)
            throw new InvalidDataException("Single HD2 model has no head joint or geometry.");
        var result = SourceRetargetPipeline.Run(inputs, rig, options: Options(modelScale));
        if (!double.IsFinite(result.Metrics.SourceHeight) || result.Metrics.SourceHeight < 0.05)
            throw new InvalidDataException("Single HD2 model has an invalid head-to-sole height.");

        var driverParentRest = result.ShippedRest;
        result = NormalizeArmSegments(inputs, result, rig);
        // World/local tables must both change. Reusing the original avatar here makes
        // generated animation offsets zero while the geometry has already moved/scaled.
        var worlds = Enumerable.Range(0, avatar.NameHashes.Count)
            .Select(i => result.ShippedRest[i]).ToArray();
        PreserveControlMarkerLocals(inputs, result, rig, worlds);
        result = result with { ShippedRest = worlds.Select((world, i) => (world, i))
            .ToDictionary(x => x.i, x => x.world) };
        var locals = Enumerable.Range(0, worlds.Length).Select(i =>
        {
            var parent = rig.Bones.Single(b => b.Index == i).ParentIndex;
            var local = parent < 0 || parent == i || parent >= worlds.Length
                ? worlds[i] : worlds[parent].Inverse() * worlds[i];
            return ToLocalWithScale(local);
        }).ToArray();
        var bind = avatar with
        {
            LocalTransforms = locals,
            Matrices = worlds.Select(m => new UnitTransformMatrix(NativeSourceSkeleton.ToRow(m))).ToArray(),
        };
        result = result with { DriverFrames = FinalizeDriverFrames(result.DriverFrames, rig, driverParentRest, result.ShippedRest) };
        // Helpers follow the posed anchors; their weights/indices stay on the existing append path.
        bind = UnitTransformInfoAppender.Append(bind, result.ExtraBones)!;
        UnitTransformInfoAppender.AssertLocalAndWorldAgree(bind, tolerance: 2e-5f);
        return new SingleHd2Conversion(result with { SingleHd2Transforms = bind },
            new SingleHd2BindManifest(1, Policy, modelScale, avatar.NameHashes,
                worlds.Select(NativeSourceSkeleton.ToRow).ToArray()));
    }
    // Single-only calibration: never use an arbitrary attach/idle pose as the VRD zero.
    internal static IReadOnlyList<SourceQuatInterpDriverFact> FinalizeDriverFrames(
        IReadOnlyList<SourceQuatInterpDriverFact> facts, Hd2Rig rig,
        IReadOnlyDictionary<int, Mat4> previous, IReadOnlyDictionary<int, Mat4> final)
    {
        float[] Rotation(Mat4 m)
        {
            var x = new Vec3(m.M11, m.M21, m.M31).Normalized();
            var y = new Vec3(m.M12, m.M22, m.M32).Normalized();
            var z = new Vec3(m.M13, m.M23, m.M33).Normalized();
            return Quat.FromRotationMatrix(x.X,y.X,z.X,x.Y,y.Y,z.Y,x.Z,y.Z,z.Z);
        }
        return facts.Select(fact =>
        {
            var parent = rig.Find(fact.ParentName) ?? throw new InvalidDataException($"Unresolved VRD parent {fact.ParentName}");
            var control = rig.Find(fact.ControlName) ?? throw new InvalidDataException($"Unresolved VRD control {fact.ControlName}");
            var oldParent = Rotation(previous[parent.Index]);
            var newParent = Rotation(final[parent.Index]);
            var controlQ = Rotation(final[control.Index]);
            return fact with
            {
                FrameConjugation = Quat.Normalized(Quat.Multiply(Quat.Multiply(Quat.Conjugate(newParent), oldParent), fact.FrameConjugation)),
                RuntimeControlBind = Quat.Normalized(Quat.Multiply(Quat.Conjugate(newParent), controlQ)),
            };
        }).ToArray();
    }

    // A snapped source joint is not necessarily on the template bone's local X
    // axis. Fixed T/A rotations alone left test07 segments 40 deg off that axis.
    // Re-pose the mesh AND joint heads together, keeping source bone lengths and
    // restoring the original HD2 animation axes. No mesh-only fitting is used.
    private static RetargetResult NormalizeArmSegments(RetargetInputs inputs,
        RetargetResult result, Hd2Rig rig)
    {
        var bones = rig.Bones.ToDictionary(b => b.Index);
        var corrections = rig.Bones.ToDictionary(b => b.Index, _ => Mat4.Identity);
        bool Below(int index, int root)
        {
            var visited = new HashSet<int>();
            while (visited.Add(index))
            {
                if (index == root) return true;
                var parent = bones[index].ParentIndex;
                if (parent < 0 || parent == index || !bones.ContainsKey(parent)) return false;
                index = parent;
            }
            throw new InvalidDataException("Cyclic single HD2 skeleton.");
        }
        foreach (var side in new[] { "l", "r" })
        {
            var shoulder = rig.Find(side + "_shoulder");
            var elbow = rig.Find(side + "_elbow");
            var hand = rig.Find(side + "_hand");
            if (shoulder is null || elbow is null || hand is null) continue;
            var sp = result.ShippedRest[shoulder.Index].Origin;
            var ep = result.ShippedRest[elbow.Index].Origin;
            var hp = result.ShippedRest[hand.Index].Origin;
            var first = ep - sp; var second = hp - ep;
            var nativeFirst = elbow.WorldOrigin - shoulder.WorldOrigin;
            var nativeSecond = hand.WorldOrigin - elbow.WorldOrigin;
            if (first.Length < 1e-8 || second.Length < 1e-8 || nativeFirst.Length < 1e-8 || nativeSecond.Length < 1e-8)
                throw new InvalidDataException("Degenerate single HD2 arm segment.");
            var upperRotation = RetargetMath.MinArcRotation(first, nativeFirst);
            var upper = RetargetMath.Trans(sp) * upperRotation.ToMat4() * RetargetMath.Trans(sp * -1);
            var newElbow = upper.TransformPoint(ep);
            var lowerRotation = RetargetMath.MinArcRotation(upperRotation.Transform(second), nativeSecond);
            var lower = RetargetMath.Trans(newElbow) * lowerRotation.ToMat4() * RetargetMath.Trans(newElbow * -1) * upper;
            var newHand = lower.TransformPoint(hp);
            var wrist = RetargetMath.Trans(newHand - hp);
            var twist = rig.Find(side + "_hand_twist");
            foreach (var bone in rig.Bones)
            {
                if (!Below(bone.Index, shoulder.Index)) continue;
                corrections[bone.Index] = Below(bone.Index, hand.Index) || (twist is not null && Below(bone.Index, twist.Index))
                    ? wrist : Below(bone.Index, elbow.Index) ? lower : upper;
            }
        }
        var worlds = result.ShippedRest.ToDictionary(x => x.Key, x =>
            RetargetMath.Trans(corrections[x.Key].TransformPoint(x.Value.Origin) - x.Value.Origin) * x.Value);
        var deform = result.Deform.ToDictionary(x => x.Key, x => corrections[x.Key] * x.Value);
        Vec3[] Skin(IReadOnlyList<Vec3> points, IReadOnlyDictionary<int, Mat4> frames)
        {
            var output = new Vec3[points.Count];
            for (var i = 0; i < points.Count; i++)
            {
                var vertex = inputs.Geometry.Vertices[i]; var value = Vec3.Zero; var total = 0.0;
                foreach (var weight in new[] { vertex.Weight0, vertex.Weight1, vertex.Weight2 })
                {
                    if (weight.Weight <= 0) continue;
                    var frame = result.Resolved.TryGetValue(weight.BoneIndex, out var index) && frames.TryGetValue(index, out var mapped)
                        ? mapped : Mat4.Identity;
                    value += frame.TransformPoint(points[i]) * weight.Weight; total += weight.Weight;
                }
                output[i] = total > 0 ? value / total : points[i];
            }
            return output;
        }
        var mesh = Skin(result.Aligned, deform);
        var idle = rig.Bones.ToDictionary(b => b.Index, b => b.WorldBind * worlds[b.Index].Inverse());
        return result with
        {
            ShippedRest = worlds, Deform = deform, Output = mesh, IdleOutput = Skin(mesh, idle),
            ExtraBones = result.ExtraBones.Select(b => b with
            { WorldOrigin = b.AnchorIndex >= 0 && corrections.TryGetValue(b.AnchorIndex, out var c)
                ? c.TransformPoint(b.WorldOrigin) : b.WorldOrigin }).ToArray(),
        };
    }

    // Markers use their parent's control space, not working-pose WORLD points.
    // Preserving those points after axis roundtrip reversed test07's aim by 153.65 deg.
    private static readonly HashSet<string> ControlMarkers = new(StringComparer.Ordinal)
    { "attach_hand_l", "attach_hand_r", "weapon_aim", "attach_weapon", "aim_weapon", "head_aim", "boss_aim" };

    private static void PreserveControlMarkerLocals(RetargetInputs inputs, RetargetResult result,
        Hd2Rig rig, Mat4[] worlds)
    {
        var bones = rig.Bones.ToDictionary(b => b.Index);
        var controls = rig.Bones.Where(b => ControlMarkers.Contains(b.DisplayName) || !b.HasName)
            .Select(b => b.Index).ToHashSet();
        foreach (var vertex in inputs.Geometry.Vertices)
        foreach (var weight in new[] { vertex.Weight0, vertex.Weight1, vertex.Weight2 })
            if (weight.Weight > 0 && result.Resolved.TryGetValue(weight.BoneIndex, out var target)
                && controls.Contains(target))
                throw new InvalidDataException("Single HD2 control markers cannot carry mesh weights.");
        var locals = new Mat4[worlds.Length];
        for (var i = 0; i < worlds.Length; i++)
        {
            var bone = bones[i]; var parent = bone.ParentIndex;
            var hasParent = parent >= 0 && parent != i && parent < worlds.Length;
            locals[i] = controls.Contains(i)
                ? (hasParent ? bones[parent].WorldBind.Inverse() * bone.WorldBind : bone.WorldBind)
                : (hasParent ? worlds[parent].Inverse() * worlds[i] : worlds[i]);
        }
        var done = new HashSet<int>(); var visiting = new HashSet<int>();
        Mat4 Rebuild(int i)
        {
            if (done.Contains(i)) return worlds[i];
            if (!visiting.Add(i)) throw new InvalidDataException("Cyclic single HD2 skeleton.");
            var parent = bones[i].ParentIndex;
            worlds[i] = parent >= 0 && parent != i && parent < worlds.Length
                ? Rebuild(parent) * locals[i] : locals[i];
            visiting.Remove(i); done.Add(i); return worlds[i];
        }
        for (var i = 0; i < worlds.Length; i++) Rebuild(i);
    }

    private static UnitLocalTransform ToLocalWithScale(Mat4 matrix)
    {
        var row = NativeSourceSkeleton.ToRow(matrix);
        var scales = Enumerable.Range(0, 3).Select(i =>
            (float)Math.Sqrt(Enumerable.Range(0, 3).Sum(k => row[i * 4 + k] * row[i * 4 + k]))).ToArray();
        if (scales.Any(v => !float.IsFinite(v) || v < 1e-8))
            throw new InvalidDataException("Single HD2 bind contains a singular scale.");
        for (var i = 0; i < 3; i++)
            for (var k = 0; k < 3; k++) row[i * 4 + k] /= scales[i];
        // Original collision/volume helpers legitimately have scale (e.g. 54.43 on Y).
        // Preserve it, rather than baking it into a quaternion or scaling the character again.
        return NativeSourceSkeleton.ToLocal(Hd2RigReader.FromHd2RowVector(row)) with { Scale = scales };
    }

}

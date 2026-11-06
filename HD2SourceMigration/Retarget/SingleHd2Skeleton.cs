using System.Text.Json;
using HD2ModAdaptation.PatchReconstruction.UnitMesh;
using HD2SourceMigration.VpkConversion;
using HD2SourceModel;

namespace HD2SourceMigration.Retarget;

public sealed record SingleHd2BindManifest(int Version, string Policy, double ModelScale,
    IReadOnlyList<uint> DriverHashes, IReadOnlyList<float[]> DriverWorld,
    bool MeshOnlyPostprocessing = false);

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

        // World/local tables must both change. Reusing the original avatar here makes
        // generated animation offsets zero while the geometry has already moved/scaled.
        var worlds = Enumerable.Range(0, avatar.NameHashes.Count)
            .Select(i => result.ShippedRest[i]).ToArray();
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
        // Helpers follow the posed anchors; their weights/indices stay on the existing append path.
        bind = UnitTransformInfoAppender.Append(bind, result.ExtraBones)!;
        UnitTransformInfoAppender.AssertLocalAndWorldAgree(bind, tolerance: 2e-5f);
        return new SingleHd2Conversion(result with { SingleHd2Transforms = bind },
            new SingleHd2BindManifest(1, Policy, modelScale, avatar.NameHashes,
                worlds.Select(NativeSourceSkeleton.ToRow).ToArray()));
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

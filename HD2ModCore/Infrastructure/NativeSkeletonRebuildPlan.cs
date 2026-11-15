namespace HD2ModCore.Infrastructure;

public enum NativeSkeletonBuildKind
{
    OriginalFormat,
    SingleSkeleton,
    DualSkeletonWithLua,
}

/// <summary>Preserve a model's existing native/single route across the shared rebuild pipeline.</summary>
public sealed record NativeSkeletonRebuildPlan(NativeSkeletonBuildKind Kind)
{
    public bool RequiresPreparation => Kind != NativeSkeletonBuildKind.OriginalFormat;
    public string? ConversionArgument => Kind switch
    {
        NativeSkeletonBuildKind.SingleSkeleton => "--single-hd2-skeleton",
        NativeSkeletonBuildKind.DualSkeletonWithLua => "--source-skeleton",
        _ => null,
    };

    public static NativeSkeletonRebuildPlan Create(bool dualSkeleton, bool singleSkeleton)
    {
        if (dualSkeleton && singleSkeleton)
            throw new InvalidDataException("模型包含两条骨架路线，请重新导入；不会回退到原版格式。");
        return new(dualSkeleton ? NativeSkeletonBuildKind.DualSkeletonWithLua
            : singleSkeleton ? NativeSkeletonBuildKind.SingleSkeleton
            : NativeSkeletonBuildKind.OriginalFormat);
    }

    public static NativeSkeletonRebuildPlan FromPayload(string directory)
        => Create(File.Exists(Path.Combine(directory, "source-skeleton.json")),
            File.Exists(Path.Combine(directory, "single-skeleton.json")));
}

/// <summary>The desktop or a headless runtime prepares writable staging, never the library payload.</summary>
public sealed record NativeSkeletonStagingRequest(
    string StagingDirectory, string OriginalModelDirectory, NativeSkeletonBuildKind Kind);

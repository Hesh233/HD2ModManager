using HD2ModCore.Infrastructure;

namespace HD2ModManager.Services;

internal static class NativeSkeletonRebuildAdapter
{
    internal static Task PrepareAsync(NativeSkeletonStagingRequest request, CancellationToken cancellationToken)
        => request.Kind switch
        {
            NativeSkeletonBuildKind.DualSkeletonWithLua => VpkAnimationBuildService.PrepareStagedNativeModelAsync(
                request.StagingDirectory, cancellationToken,
                NativeSkeletonProjectService.ResolveConfig(request.OriginalModelDirectory)),
            NativeSkeletonBuildKind.SingleSkeleton => VpkAnimationBuildService.PrepareSingleModelAsync(
                request.StagingDirectory, cancellationToken),
            _ => throw new InvalidOperationException("原版格式不应请求骨架校准。"),
        };
}

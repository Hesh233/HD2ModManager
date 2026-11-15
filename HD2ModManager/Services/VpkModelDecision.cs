namespace HD2ModManager.Services;

/// <summary>VPK 导入的三条互斥路线；取消不属于任何导入路线。</summary>
public enum VpkImportRoute
{
    OriginalFormat,
    SingleSkeleton,
    DualSkeletonWithLua,
}

/// <summary>拖入 VPK 后对单个模型主体的决策：是否制作原骨架护甲、倍率、是否生成骨架动画。</summary>
public sealed record VpkModelDecision(
	bool UseNativeSkeleton,
	double ModelScale,
	bool GenerateAnimation,
    bool SingleHd2Skeleton = false,
    int AnimationThreads = AnimationThreadCount.Default)
{
    public bool BuildsSkeletonPackage => UseNativeSkeleton || SingleHd2Skeleton;
    // 仅记录倍率确认后的前置选择；模型入库后才应用，不在打包前改库。
    public HD2ModManager.ViewModels.VpkTargetArmorOption? TargetArmor { get; init; }
    /// <summary>原版格式沿用标准导入，不请求骨架动画或挂点 Lua。</summary>
    public static VpkModelDecision ForImportRoute(VpkImportRoute route, double modelScale,
        int animationThreads = AnimationThreadCount.Default) => route switch
    {
        VpkImportRoute.OriginalFormat => new(false, modelScale, false),
        VpkImportRoute.SingleSkeleton => new(false, modelScale, true,
            SingleHd2Skeleton: true, AnimationThreads: animationThreads),
        VpkImportRoute.DualSkeletonWithLua => new(true, modelScale, true,
            AnimationThreads: animationThreads),
        _ => throw new ArgumentOutOfRangeException(nameof(route), route, "未知的 VPK 导入路线。"),
    };

}


/// <summary>全量动画生成的并行度：两条骨架路线共用相同的输入约束。</summary>
public static class AnimationThreadCount
{
    public const int Default = 2;
    public const int Maximum = 16;

    public static int Parse(string? text)
    {
        if (!int.TryParse(text?.Trim(), System.Globalization.NumberStyles.None,
                System.Globalization.CultureInfo.InvariantCulture, out var count))
            throw new ArgumentException("请输入 1–16 之间的整数进程数。");
        Validate(count);
        return count;
    }

    public static void Validate(int count)
    {
        if (count < 1 || count > Maximum)
            throw new ArgumentOutOfRangeException(nameof(count), "进程数必须为 1–16 之间的整数。");
    }
}

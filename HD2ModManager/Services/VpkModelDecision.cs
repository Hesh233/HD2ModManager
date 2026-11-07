namespace HD2ModManager.Services;

/// <summary>拖入 VPK 后对单个模型主体的决策：是否制作原骨架护甲、倍率、是否生成骨架动画。</summary>
public sealed record VpkModelDecision(
	bool UseNativeSkeleton,
	double ModelScale,
	bool GenerateAnimation,
    bool SingleHd2Skeleton = false,
    int AnimationThreads = AnimationThreadCount.Default)
{
    public bool BuildsSkeletonPackage => UseNativeSkeleton || SingleHd2Skeleton;
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

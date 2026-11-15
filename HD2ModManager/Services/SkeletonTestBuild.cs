namespace HD2ModManager.Services;

/// <summary>骨架测试版的启动说明、版本展示与更新策略；后续同步上游代码时保留此分支约束。</summary>
internal static class SkeletonTestBuild
{
    public const string NoticeTitle = "骨架测试版本";
    public const string NoticeText =
        "此为全量动画转换的骨架测试版本，使用自定义骨架，有效解决体型，双开门，身高，陷地问题。\n"
        + "，物理模式暂时只兼容外置加载器兼容，物理模块需要改为安装路径文件里的“物理运行时-正式版-2.3.4.zip”\n"
        + "全量动画文件替换后只能为单个mod服务，即其他甲的形状也会变成mod甲的形状\n"
        + "相关开关按钮在设置界面，开启是否询问安装骨架动画开关即可";

    // 不接收上游程序更新，避免覆盖本地骨架扩展；停用运行时而不重写用户已保存的更新偏好。
    public static bool UpdatesEnabled => false;

    // 版本来自当前 GUI 程序集；以后同步只需更新 HD2ModManager.csproj 的 Version。
    public static string VersionText(string version) => $"基于{version} 骨架测试";
}

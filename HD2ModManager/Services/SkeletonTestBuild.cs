namespace HD2ModManager.Services;

/// <summary>骨架测试版的启动说明、版本展示与更新策略；后续同步上游代码时保留此分支约束。</summary>
internal static class SkeletonTestBuild
{
    public const string RepairVersion = "1.01";
    public const string HomeTitle = "骨架测试版本管理器：" + RepairVersion;
    public const string ReleaseNotes =
        "1.01修复：\n"
        + "1.走路动画跳变\n"
        + "2.多人物理失效情况，舰船默认全开启物理效果（不代表战斗时的帧数），战斗切换第一人称自动启动物理效果（警告，目前会有10%性能损失。裙子的物理效果战斗性能消耗比舰船高）\n"
        + "3.全护甲兼容chef加载器映射（暂不测试其他加载器兼容，12月还会炸一次）\n"
        + "4.当前最新物理包为A2.3.21，后续可能还有新的版本";

    public const string NoticeTitle = "骨架测试版本";
    public const string NoticeText =
        "此为全量动画转换的骨架测试版本，使用自定义骨架，有效解决体型，双开门，身高，陷地问题。\n"
        + "物理模式当前使用A2.3.21，请使用安装路径“运行时配套\\物理运行时.zip”，仅启用一份物理运行时\n"
        + "全量动画文件替换后只能为单个mod服务，即其他甲的形状也会变成mod甲的形状\n"
        + "相关开关按钮在设置界面，开启是否询问安装骨架动画开关即可";

    // 不接收上游程序更新，避免覆盖本地骨架扩展；停用运行时而不重写用户已保存的更新偏好。
    public static bool UpdatesEnabled => false;

    // 骨架修复版本独立于上游 GUI 的 SemVer；更新修复说明时同时维护此版本与打包元数据。
    public static string VersionText(string version) => $"骨架修复{RepairVersion}";
}

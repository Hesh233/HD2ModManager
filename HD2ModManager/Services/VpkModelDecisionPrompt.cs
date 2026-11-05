using System.Globalization;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;

namespace HD2ModManager.Services;

/// <summary>拖入 VPK 后对单个模型主体的决策：是否制作原骨架护甲、倍率、是否生成骨架动画。</summary>
public sealed record VpkModelDecision(
	bool UseNativeSkeleton,
	double ModelScale,
	bool GenerateAnimation);

/// <summary>
/// 逐模型的三段询问：原骨架护甲 → 大小倍率 → 骨架动画。
/// 任一环节取消返回 <c>null</c>，由调用方中止整批导入。
/// </summary>
internal static class VpkModelDecisionPrompt
{
    internal static async Task<VpkModelDecision?> ShowAsync(string model, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var native = await VpkChoicePrompt.ShowAsync(
            "制作原骨架护甲",
            $"模型「{model}」是否制作原骨架护甲？\n"
            + "是：保留来源骨架、按你指定的大小倍率转换，产物以 [原比例模型] 命名。\n"
            + "否：按原逻辑转换（重定向到游戏统一骨架）。",
            "是，制作原骨架护甲",
            "否，按原逻辑制作 Mod",
            cancellationToken).ConfigureAwait(false);
        if (native is null) return null;
        if (native == false) return new VpkModelDecision(false, 1, false);

        var scale = await ModelScalePrompt.ShowAsync(model, cancellationToken).ConfigureAwait(false);
        if (scale is null) return null;

        // 随包 Python 运行时缺失时不追问：动画生成不了，但原骨架模型本身仍然可以正常产出。
        if (!VpkAnimationBuildService.IsRuntimeAvailable())
            return new VpkModelDecision(true, scale.Value, false);

        var animate = await VpkChoicePrompt.ShowAsync(
            "生成骨架动画",
            $"模型「{model}」是否需要生成骨架动画？\n"
            + "需要：转换完成后会全量转换游戏第三人称动画（约数千条，耗时较长），"
            + "产出一个以 [原比例混合动画](VPK名字) 命名的独立动画 Mod。",
            "需要生成动画",
            "不需要",
            cancellationToken).ConfigureAwait(false);
        if (animate is null) return null;

        return new VpkModelDecision(true, scale.Value, animate.Value);
    }
}

/// <summary>两个按钮的是/否模态框；关闭窗口视为取消（返回 <c>null</c>）。</summary>
internal static class VpkChoicePrompt
{
    internal static async Task<bool?> ShowAsync(
        string title,
        string message,
        string yesText,
        string noText,
        CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        return await System.Windows.Application.Current.Dispatcher.InvokeAsync(() =>
        {
            cancellationToken.ThrowIfCancellationRequested();
            bool? result = null;
            var owner = System.Windows.Application.Current.MainWindow;
            var window = new Window
            {
                Title = title,
                Width = 440,
                SizeToContent = SizeToContent.Height,
                ResizeMode = ResizeMode.NoResize,
                WindowStartupLocation = WindowStartupLocation.CenterOwner,
                ShowInTaskbar = false,
                Owner = owner?.IsVisible == true ? owner : null,
            };
            var panel = new StackPanel { Margin = new Thickness(20) };
            panel.Children.Add(new TextBlock { Text = message, TextWrapping = TextWrapping.Wrap });
            var buttons = new StackPanel
            {
                Orientation = Orientation.Horizontal,
                HorizontalAlignment = HorizontalAlignment.Right,
                Margin = new Thickness(0, 16, 0, 0),
            };
            var cancel = new Button { Content = "取消", IsCancel = true, MinWidth = 70, Margin = new Thickness(8) };
            var no = new Button { Content = noText, MinWidth = 120, Margin = new Thickness(8) };
            var yes = new Button { Content = yesText, IsDefault = true, MinWidth = 120, Margin = new Thickness(8) };
            no.Click += (_, _) => { result = false; window.DialogResult = false; };
            yes.Click += (_, _) => { result = true; window.DialogResult = true; };
            buttons.Children.Add(cancel);
            buttons.Children.Add(no);
            buttons.Children.Add(yes);
            panel.Children.Add(buttons);
            window.Content = panel;
            using var registration = cancellationToken.Register(() => window.Dispatcher.BeginInvoke(new Action(window.Close)));
            window.ShowDialog();
            return result;
        });
    }
}

using System.Globalization;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;

namespace HD2ModManager.Services;

/// <summary>
/// 逐模型询问：取消 / 单 HD2 骨架 / 双骨架 + Lua，然后选择大小倍率。
/// 任一环节取消返回 <c>null</c>，由调用方中止整批导入。
/// </summary>
internal static class VpkModelDecisionPrompt
{
    internal static async Task<VpkModelDecision?> ShowAsync(string model, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var dual = await VpkChoicePrompt.ShowAsync(
            "制作原骨架护甲",
            $"模型「{model}」请选择制作流程：\n"
            + "单原骨架：VPK 骨架转为一套 HD2 骨架，动画使用原 anim_batch_mod 打包流程，不生成挂点 Lua。\n"
            + "双骨架 + Lua：保留 VPK 原骨架和 HD2 骨架，分别使用自己的挂点；生成配套动画及挂点修正 Lua。\n"
            + "取消：中止本次导入。两种制作流程均全量生成配套动画。",
            "是，制作双骨架护甲+lua",
            "是，制作单原骨架护甲",
            cancellationToken).ConfigureAwait(false);
        if (dual is null) return null;
        if (!VpkAnimationBuildService.IsRuntimeAvailable())
            throw new InvalidOperationException("制作骨架护甲需要完整随包 Python 运行时，请更新完整管理器后重试。");
        var scale = await ModelScalePrompt.ShowAsync(model, cancellationToken).ConfigureAwait(false);
        if (scale is null) return null;
        var threads = await AnimationThreadCountPrompt.ShowAsync(model, cancellationToken).ConfigureAwait(false);
        if (threads is null) return null;
        return new VpkModelDecision(dual.Value, scale.Value, true, SingleHd2Skeleton: !dual.Value,
            AnimationThreads: threads.Value);
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
                Width = yesText.Length > 12 || noText.Length > 12 ? 660 : 440,
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

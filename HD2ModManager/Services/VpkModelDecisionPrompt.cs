using System.IO;
using System.Globalization;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using HD2ModManager.ViewModels;

namespace HD2ModManager.Services;

/// <summary>可测试的逐步收集器；所有询问都在 VPK 转换之前完成。</summary>
internal sealed record VpkModelDecisionPromptSteps(
    Func<string, CancellationToken, Task<VpkImportRoute?>> ChooseRoute,
    Func<string, bool, CancellationToken, Task<double?>> ChooseScale,
    Func<string, CancellationToken, Task<VpkTargetArmorOption?>> ChooseTargetArmor,
    Func<string, CancellationToken, Task<int?>> ChooseAnimationThreads,
    Func<bool> IsRuntimeAvailable);

internal static class VpkModelDecisionPrompt
{
    internal static Task<VpkModelDecision?> ShowAsync(string model, CancellationToken cancellationToken)
        => ShowWithTargetArmorAsync(model, cancellationToken,
            (name, token) => VpkTargetArmorPrompt.RequestAsync(name, SettingsService.CreateStoragePaths(), token));

    internal static Task<VpkModelDecision?> ShowWithTargetArmorAsync(string model, CancellationToken cancellationToken,
        Func<string, CancellationToken, Task<VpkTargetArmorOption?>> requestTargetArmor)
    {
        var ask = SettingsService.GetAskToInstallSkeletonAnimation();
        var allowDual = SettingsService.GetEnableDualSkeletonAnimationVersion();
        return CollectAsync(model, ask, allowDual, new VpkModelDecisionPromptSteps(
            (name, token) => VpkChoicePrompt.ShowImportRoutesWithDualAsync(name, allowDual, token),
            (name, skeleton, token) => skeleton ? ModelScalePrompt.ShowSkeletonAsync(name, token) : ModelScalePrompt.ShowAsync(name, token),
            requestTargetArmor, AnimationThreadCountPrompt.ShowAsync, VpkAnimationBuildService.IsRuntimeAvailable), cancellationToken);
    }

    internal static async Task<VpkModelDecision?> CollectAsync(string model, bool ask, bool allowDual,
        VpkModelDecisionPromptSteps steps, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (!ask) return VpkModelDecision.ForImportRoute(VpkImportRoute.OriginalFormat, modelScale: 1.0);

        var route = await steps.ChooseRoute(model, cancellationToken).ConfigureAwait(false);
        cancellationToken.ThrowIfCancellationRequested();
        if (route is null) return null;
        if (!VpkChoicePrompt.AvailableImportRoutes(allowDual).Contains(route.Value))
            throw new InvalidOperationException("双骨架动画版本尚未启用，不能选择该导入路线。");
        var skeleton = route != VpkImportRoute.OriginalFormat;
        if (skeleton && !steps.IsRuntimeAvailable())
            throw new InvalidOperationException("制作骨架护甲需要完整随包 Python 运行时，请更新完整管理器后重试。");

        var scale = await steps.ChooseScale(model, skeleton, cancellationToken).ConfigureAwait(false);
        cancellationToken.ThrowIfCancellationRequested();
        if (scale is null) return null;
        if (!VpkModelScalePolicy.IsValid(scale.Value)) throw new InvalidDataException("模型大小倍率必须大于 0 且不超过 10。");
        if (!skeleton) return VpkModelDecision.ForImportRoute(route.Value, scale.Value);

        // 倍率确认后马上询问；这里只保存目标，绝不提前执行换甲或打包。
        var target = await steps.ChooseTargetArmor(model, cancellationToken).ConfigureAwait(false);
        cancellationToken.ThrowIfCancellationRequested();
        var threads = await steps.ChooseAnimationThreads(model, cancellationToken).ConfigureAwait(false);
        cancellationToken.ThrowIfCancellationRequested();
        if (threads is null) return null;
        AnimationThreadCount.Validate(threads.Value);
        return VpkModelDecision.ForImportRoute(route.Value, scale.Value, threads.Value) with { TargetArmor = target };
    }
}

internal static class VpkChoicePrompt
{
    internal static IReadOnlyList<VpkImportRoute> AvailableImportRoutes(bool allowDual)
    {
        var routes = new List<VpkImportRoute>();
        if (allowDual) routes.Add(VpkImportRoute.DualSkeletonWithLua);
        routes.Add(VpkImportRoute.SingleSkeleton);
        routes.Add(VpkImportRoute.OriginalFormat);
        return routes;
    }

    internal static StackPanel BuildImportRoutesPanel(string model, bool allowDual, Action<VpkImportRoute>? selected = null)
    {
        var panel = new StackPanel { Margin = new Thickness(20) };
        panel.Children.Add(new TextBlock
        {
            Text = $"模型「{model}」请选择导入流程：\n"
                + "原版格式：沿用标准 VPK→patch 导入，不制作骨架配套动画和挂点 Lua。\n"
                + "单原骨架：VPK 骨架转为一套 HD2 骨架，全量生成配套动画，不生成挂点 Lua。\n"
                + (allowDual ? "双骨架 + Lua：生成配套动画及挂点修正 Lua，当前挂点修正性能未优化。\n" : string.Empty)
                + "取消：中止本次导入。",
            TextWrapping = TextWrapping.Wrap,
        });
        var choices = new StackPanel { Margin = new Thickness(0, 12, 0, 0) };
        foreach (var route in AvailableImportRoutes(allowDual))
        {
            var (name, text) = route switch
            {
                VpkImportRoute.DualSkeletonWithLua => ("DualSkeletonImport", "是，制作双骨架护甲+lua（性能未优化）"),
                VpkImportRoute.SingleSkeleton => ("SingleSkeletonImport", "是，制作单原骨架护甲"),
                _ => ("OriginalFormatImport", "否，原版格式导入"),
            };
            var button = new Button { Name = name, Content = text, IsDefault = route == (allowDual ? VpkImportRoute.DualSkeletonWithLua : VpkImportRoute.SingleSkeleton),
                MinHeight = 34, Margin = new Thickness(0, 4, 0, 4) };
            button.Click += (_, _) => selected?.Invoke(route);
            choices.Children.Add(button);
        }
        panel.Children.Add(choices);
        panel.Children.Add(new Button { Name = "CancelVpkImport", Content = "取消", IsCancel = true,
            MinWidth = 70, Margin = new Thickness(0, 12, 0, 0), HorizontalAlignment = HorizontalAlignment.Right });
        return panel;
    }

    internal static Task<VpkImportRoute?> ShowImportRoutesAsync(string model, CancellationToken cancellationToken)
        => ShowImportRoutesWithDualAsync(model, SettingsService.GetEnableDualSkeletonAnimationVersion(), cancellationToken);

    internal static async Task<VpkImportRoute?> ShowImportRoutesWithDualAsync(string model, bool allowDual, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        return await Application.Current.Dispatcher.InvokeAsync(() =>
        {
            cancellationToken.ThrowIfCancellationRequested();
            VpkImportRoute? result = null;
            var owner = Application.Current.MainWindow;
            var window = new Window { Title = "导入 VPK 模型格式", Width = 620, SizeToContent = SizeToContent.Height,
                ResizeMode = ResizeMode.NoResize, WindowStartupLocation = WindowStartupLocation.CenterOwner,
                ShowInTaskbar = false, Owner = owner?.IsVisible == true ? owner : null };
            window.Content = BuildImportRoutesPanel(model, allowDual, route => { result = route; window.DialogResult = true; });
            using var registration = cancellationToken.Register(() => window.Dispatcher.BeginInvoke(new Action(window.Close)));
            window.ShowDialog();
            return result;
        });
    }

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

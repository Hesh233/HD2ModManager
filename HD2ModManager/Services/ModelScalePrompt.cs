using System.Globalization;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;

namespace HD2ModManager.Services;

internal static class VpkModelScalePolicy
{
    internal const double RecommendedMinimum = 0.9;
    internal const double RecommendedMaximum = 1.1;
    internal static bool IsValid(double value) => double.IsFinite(value) && value > 0 && value <= 10;
    internal static bool RequiresWarning(double value, bool skeletonVersion)
        => skeletonVersion && IsValid(value) && (value < RecommendedMinimum || value > RecommendedMaximum);
}

internal static class ModelScalePrompt
{
    internal static Task<double?> ShowAsync(string model, CancellationToken cancellationToken)
        => ShowCoreAsync(model, false, cancellationToken);
    internal static Task<double?> ShowSkeletonAsync(string model, CancellationToken cancellationToken)
        => ShowCoreAsync(model, true, cancellationToken);

    internal static StackPanel BuildScalePanel(string model, bool skeletonVersion, Action<double> accepted, Func<double, bool> confirmOutsideRange)
    {
        var input = new TextBox { Name = "ModelScaleInput", Text = "1", Margin = new Thickness(0, 12, 0, 8) };
        var error = new TextBlock { Name = "ModelScaleError", Foreground = Brushes.IndianRed, TextWrapping = TextWrapping.Wrap };
        var panel = new StackPanel { Margin = new Thickness(20) };
        panel.Children.Add(new TextBlock { Text = $"{model}\n模型大小倍率（默认 1）"
            + (skeletonVersion ? "\n骨架版本建议 0.9–1.1；超出建议范围需再次确认。" : string.Empty), TextWrapping = TextWrapping.Wrap });
        panel.Children.Add(input); panel.Children.Add(error);
        var buttons = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right };
        buttons.Children.Add(new Button { Content = "取消", IsCancel = true, MinWidth = 70, Margin = new Thickness(8) });
        var accept = new Button { Name = "ConfirmModelScale", Content = skeletonVersion ? "下一步" : "开始转换", IsDefault = true, MinWidth = 90, Margin = new Thickness(8) };
        accept.Click += (_, _) =>
        {
            if (!double.TryParse(input.Text, NumberStyles.Float, CultureInfo.InvariantCulture, out var value) || !VpkModelScalePolicy.IsValid(value))
            { error.Text = "请输入大于 0 且不超过 10 的数值，例如 1.0。"; return; }
            if (VpkModelScalePolicy.RequiresWarning(value, skeletonVersion) && !confirmOutsideRange(value))
            { error.Text = "已返回倍率输入，请修改后再次确认。"; input.Focus(); input.SelectAll(); return; }
            accepted(value); // 明确选“是”时原值继续，不夹取到建议范围。
        };
        buttons.Children.Add(accept); panel.Children.Add(buttons);
        return panel;
    }

    private static async Task<double?> ShowCoreAsync(string model, bool skeletonVersion, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        return await Application.Current.Dispatcher.InvokeAsync(() =>
        {
            cancellationToken.ThrowIfCancellationRequested();
            var owner = Application.Current.MainWindow;
            var window = new Window { Title = "导入 VPK 模型", Width = 420, SizeToContent = SizeToContent.Height,
                ResizeMode = ResizeMode.NoResize, Owner = owner?.IsVisible == true ? owner : null,
                WindowStartupLocation = WindowStartupLocation.CenterOwner, ShowInTaskbar = false };
            double value = 1;
            var panel = BuildScalePanel(model, skeletonVersion, scale => { value = scale; window.DialogResult = true; }, scale =>
                MessageBox.Show(window, $"你填写的模型大小倍率为 {scale.ToString("G", CultureInfo.InvariantCulture)}。\n"
                    + "骨架版本建议使用 0.9–1.1；当前值超出建议范围。\n"
                    + "是否仍按填写的倍率继续？\n选择“否”返回上级修改倍率；选择“是”保留当前参数。",
                    "骨架模型倍率超出建议范围", MessageBoxButton.YesNo, MessageBoxImage.Warning, MessageBoxResult.No) == MessageBoxResult.Yes);
            window.Content = panel;
            window.Loaded += (_, _) => { var input = panel.Children.OfType<TextBox>().Single(); input.Focus(); input.SelectAll(); };
            using var registration = cancellationToken.Register(() => window.Dispatcher.BeginInvoke(new Action(window.Close)));
            return window.ShowDialog() == true ? (double?)value : null;
        });
    }
}

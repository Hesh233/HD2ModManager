using System.Windows;
using System.Windows.Controls;
using HD2ModManager.ViewModels;

namespace HD2ModManager.Services;

/// <summary>
/// 导入末尾的"选择要替换的甲"弹窗：下拉候选与 Mod 详情页的护甲下拉完全同源
/// （游戏护甲 + 已注册自定义素体），点「切换」即当场执行换甲。
/// 取消或点「跳过」返回 <c>null</c>——不自动换甲是既有设计，默认必须由用户点。
/// </summary>
internal static class VpkTargetArmorPrompt
{
    internal static async Task<VpkTargetArmorOption?> ShowAsync(
        string model,
        IReadOnlyList<VpkTargetArmorOption> options,
        VpkTargetArmorOption? initial,
        CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        return await System.Windows.Application.Current.Dispatcher.InvokeAsync(() =>
        {
            cancellationToken.ThrowIfCancellationRequested();
            var owner = System.Windows.Application.Current.MainWindow;
            var window = new Window
            {
                Title = "选择替换的护甲",
                Width = 420,
                SizeToContent = SizeToContent.Height,
                ResizeMode = ResizeMode.NoResize,
                WindowStartupLocation = WindowStartupLocation.CenterOwner,
                ShowInTaskbar = false,
                Owner = owner?.IsVisible == true ? owner : null,
            };
            var panel = new StackPanel { Margin = new Thickness(20) };
            panel.Children.Add(new TextBlock
            {
                Text = $"模型「{model}」要替换哪件护甲？\n"
                    + "点「切换」立即换到所选目标；点「跳过」保持自定义素体模式，之后可在 Mod 详情页或护甲映射页再选。",
                TextWrapping = TextWrapping.Wrap,
            });
            var combo = new ComboBox
            {
                Margin = new Thickness(0, 12, 0, 8),
                ItemsSource = options,
                SelectedItem = initial,
            };
            panel.Children.Add(combo);
            var buttons = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right };
            var skip = new Button { Content = "跳过", IsCancel = true, MinWidth = 70, Margin = new Thickness(8) };
            var apply = new Button { Content = "切换", IsDefault = true, MinWidth = 90, Margin = new Thickness(8) };
            buttons.Children.Add(skip);
            buttons.Children.Add(apply);
            panel.Children.Add(buttons);
            window.Content = panel;
            apply.Click += (_, _) =>
            {
                if (combo.SelectedItem is not VpkTargetArmorOption)
                {
                    combo.Focus();
                    return;
                }
                window.DialogResult = true;
            };
            window.Loaded += (_, _) => combo.Focus();
            using var registration = cancellationToken.Register(() => window.Dispatcher.BeginInvoke(new Action(window.Close)));
            return window.ShowDialog() == true ? (VpkTargetArmorOption?)combo.SelectedItem : null;
        });
    }
}

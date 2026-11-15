using System.IO;
using System.Windows;
using System.Windows.Controls;
using HD2ModManager.ViewModels;
using HD2ModCore.Infrastructure;

namespace HD2ModManager.Services;

/// <summary>
/// 倍率确认后的"选择要替换的甲"弹窗：下拉候选与 Mod 详情页的护甲下拉完全同源
/// （游戏护甲 + 已注册自定义素体）；这里只记录目标，模型入库后才执行换甲。
/// 取消或点「跳过」返回 <c>null</c>——不自动换甲是既有设计，默认必须由用户点。
/// </summary>
internal static class VpkTargetArmorPrompt
{
    internal static async Task<VpkTargetArmorOption?> RequestAsync(string model, StoragePaths paths, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
            IReadOnlyList<VpkTargetArmorOption> options;
            try
            {
                var catalog = new EquipmentUnitCatalogService(paths);
                options = (await catalog.GetEntriesAsync().ConfigureAwait(false))
                    .Where(entry => entry.Category.Equals("Armor", StringComparison.OrdinalIgnoreCase))
                    .GroupBy(entry => entry.ArchiveId, StringComparer.OrdinalIgnoreCase)
                    .Select(group => new VpkTargetArmorOption(group.Key, group.First().DisplayName))
                    .OrderBy(option => option.DisplayName, StringComparer.CurrentCulture)
                    .ToArray();
                try
                {
                    var registry = CoreServices.CreateRuntimeArmorRegistryService(paths);
                    var customModels = (await registry.ReadCustomModelCatalogAsync().ConfigureAwait(false))
                        .Where(entry => entry.Parts.Count != 0)
                        .Select(entry => new VpkTargetArmorOption(
                            entry.ArchiveId, entry.DisplayName + "（自定义素体）", VpkTargetArmorKind.CustomModel))
                        .OrderBy(option => option.DisplayName, StringComparer.CurrentCulture)
                        .ToArray();
                    options = options.Concat(customModels).ToArray();
                }
                catch (Exception exception) when (exception is IOException or InvalidDataException or InvalidOperationException)
                {
                    // 注册表坏了不能连带把游戏护甲列表一起废掉（与详情页同样的独立降级）。
                    LogService.Warn($"读取已注册自定义素体失败，换甲候选只列游戏护甲：{exception.Message}");
                }
            }
            catch (Exception exception) when (exception is IOException or InvalidDataException or InvalidOperationException)
            {
                LogService.Warn($"读取护甲列表失败，跳过打包前的护甲选择：{exception.Message}");
                return null;
            }

        cancellationToken.ThrowIfCancellationRequested();
        return await ShowAsync(model, options, null, cancellationToken).ConfigureAwait(false);
    }

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
                    + "点「确认」记录替换目标，模型打包完成后才执行；点「跳过」不自动换甲，之后可在详情页再选。",
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
            var apply = new Button { Content = "确认", IsDefault = true, MinWidth = 90, Margin = new Thickness(8) };
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

using System.Globalization;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;

namespace HD2ModManager.Services;

internal static class ModelScalePrompt
{
    internal static async Task<double?> ShowAsync(string model, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        return await System.Windows.Application.Current.Dispatcher.InvokeAsync(() =>
        {
            cancellationToken.ThrowIfCancellationRequested();
            var input = new TextBox { Text = "1", Margin = new Thickness(0, 12, 0, 8) };
            var error = new TextBlock { Foreground = Brushes.IndianRed, TextWrapping = TextWrapping.Wrap };
            var panel = new StackPanel { Margin = new Thickness(20) };
            panel.Children.Add(new TextBlock { Text = $"{model}\n模型大小倍率（默认 1）", TextWrapping = TextWrapping.Wrap });
            panel.Children.Add(input);
            panel.Children.Add(error);
            var buttons = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right };
            var cancel = new Button { Content = "取消", IsCancel = true, MinWidth = 70, Margin = new Thickness(8) };
            var accept = new Button { Content = "开始转换", IsDefault = true, MinWidth = 90, Margin = new Thickness(8) };
            buttons.Children.Add(cancel);
            buttons.Children.Add(accept);
            panel.Children.Add(buttons);
            var owner = System.Windows.Application.Current.MainWindow;
            var window = new Window { Title = "导入 VPK 模型", Width = 380, SizeToContent = SizeToContent.Height,
                ResizeMode = ResizeMode.NoResize, Content = panel, Owner = owner?.IsVisible == true ? owner : null,
                WindowStartupLocation = WindowStartupLocation.CenterOwner, ShowInTaskbar = false };
            double value = 1;
            accept.Click += (_, _) =>
            {
                if (!double.TryParse(input.Text, NumberStyles.Float, CultureInfo.InvariantCulture, out value)
                    || !double.IsFinite(value) || value <= 0 || value > 10)
                { error.Text = "请输入大于 0 且不超过 10 的数值，例如 1.2。"; return; }
                window.DialogResult = true;
            };
            window.Loaded += (_, _) => { input.Focus(); input.SelectAll(); };
            using var registration = cancellationToken.Register(() => window.Dispatcher.BeginInvoke(new Action(window.Close)));
            return window.ShowDialog() == true ? (double?)value : null;
        });
    }
}

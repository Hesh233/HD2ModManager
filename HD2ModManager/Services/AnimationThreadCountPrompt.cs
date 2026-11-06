using System.Globalization;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;

namespace HD2ModManager.Services;

internal static class AnimationThreadCountPrompt
{
    internal static async Task<int?> ShowAsync(string model, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        return await Application.Current.Dispatcher.InvokeAsync(() =>
        {
            cancellationToken.ThrowIfCancellationRequested();
            var input = new TextBox { Text = AnimationThreadCount.Default.ToString(CultureInfo.InvariantCulture),
                Margin = new Thickness(0, 12, 0, 8) };
            var error = new TextBlock { Foreground = Brushes.IndianRed, TextWrapping = TextWrapping.Wrap };
            var panel = new StackPanel { Margin = new Thickness(20) };
            panel.Children.Add(new TextBlock { Text = $"{model}\n全量动画打包线程数（默认 2，范围 1–16）\n线程数越大，内存占用越高；填写 1 可使用单线程。",
                TextWrapping = TextWrapping.Wrap });
            panel.Children.Add(input);
            panel.Children.Add(error);
            var buttons = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right };
            var cancel = new Button { Content = "取消", IsCancel = true, MinWidth = 70, Margin = new Thickness(8) };
            var accept = new Button { Content = "确认", IsDefault = true, MinWidth = 90, Margin = new Thickness(8) };
            buttons.Children.Add(cancel);
            buttons.Children.Add(accept);
            panel.Children.Add(buttons);
            var owner = Application.Current.MainWindow;
            var window = new Window { Title = "全量动画文件打包", Width = 420, SizeToContent = SizeToContent.Height,
                ResizeMode = ResizeMode.NoResize, Content = panel, Owner = owner?.IsVisible == true ? owner : null,
                WindowStartupLocation = WindowStartupLocation.CenterOwner, ShowInTaskbar = false };
            var count = AnimationThreadCount.Default;
            accept.Click += (_, _) =>
            {
                try { count = AnimationThreadCount.Parse(input.Text); }
                catch (ArgumentException exception) { error.Text = exception.Message; return; }
                window.DialogResult = true;
            };
            window.Loaded += (_, _) => { input.Focus(); input.SelectAll(); };
            using var registration = cancellationToken.Register(() => window.Dispatcher.BeginInvoke(new Action(window.Close)));
            return window.ShowDialog() == true ? (int?)count : null;
        });
    }
}

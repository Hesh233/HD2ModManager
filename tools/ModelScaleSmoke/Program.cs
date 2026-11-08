using System.IO;
using System.Reflection;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;

internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        try { if(args.Length>1 && args[1]=="--wrist-choice") RunWristChoice(args); else Run(args); return 0; }
        catch (Exception error)
        {
            Console.Error.WriteLine(error);
            if (args.Length > 0)
                File.WriteAllText(Path.Combine(Path.GetFullPath(args[0]), "model-scale-error.log"), error.ToString());
            return 1;
        }
    }

    private static void Run(string[] args)
    {
        var output=Path.GetFullPath(args[0]); Directory.CreateDirectory(output);
        var app=new HD2ModManager.App { ShutdownMode=ShutdownMode.OnExplicitShutdown };
        app.InitializeComponent();
        // Test our dialog without putting an interactive window over the user's desktop.
        EventManager.RegisterClassHandler(typeof(Window),FrameworkElement.LoadedEvent,new RoutedEventHandler((sender,_)=>
        { if(sender is Window w) { w.Opacity=0; w.ShowInTaskbar=false; } }));
        var method=typeof(HD2ModManager.App).Assembly.GetType("HD2ModManager.Services.ModelScalePrompt")!
            .GetMethod("ShowAsync",BindingFlags.Static|BindingFlags.NonPublic)!;
        Exception? failure=null;
        using var cancel=new CancellationTokenSource();
        var timer=new DispatcherTimer { Interval=TimeSpan.FromMilliseconds(50) };
        timer.Tick+=(_,_)=>
        {
            try
            {
                var window=app.Windows.OfType<Window>().SingleOrDefault(w=>w.Title=="导入 VPK 模型");
                if(window is null) return;
                timer.Stop();
                var panel=(StackPanel)window.Content;
                var input=panel.Children.OfType<TextBox>().Single();
                if(input.Text!="1") throw new Exception("Default scale is not 1.");
                var accept=panel.Children.OfType<StackPanel>().Single().Children.OfType<Button>().Single(b=>b.IsDefault);
                input.Text="-1"; accept.RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
                if(!panel.Children.OfType<TextBlock>().Any(t=>t.Text.Contains("请输入大于"))) throw new Exception("Invalid scale accepted.");
                input.Text="1.2";
                // Remove the earlier validation label by taking the clean state in a new render below.
                panel.Children.OfType<TextBlock>().Last().Text="";
                panel.UpdateLayout();
                var bitmap=new RenderTargetBitmap((int)Math.Ceiling(panel.ActualWidth+40),(int)Math.Ceiling(panel.ActualHeight+40),96,96,PixelFormats.Pbgra32);
                var drawing=new DrawingVisual();
                using(var dc=drawing.RenderOpen())
                {
                    dc.DrawRectangle(Brushes.White,null,new Rect(0,0,bitmap.PixelWidth,bitmap.PixelHeight));
                    dc.DrawRectangle(new VisualBrush(panel),null,new Rect(20,20,panel.ActualWidth,panel.ActualHeight));
                }
                bitmap.Render(drawing);
                var encoder=new PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(bitmap));
                using(var file=File.Create(Path.Combine(output,"model-scale-input.png"))) encoder.Save(file);
                accept.RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
            }
            catch(Exception e) { failure=e; cancel.Cancel(); }
        };
        timer.Start();
        var task=(Task<double?>)method.Invoke(null,["test01",cancel.Token])!;
        var frame=new DispatcherFrame();
        task.ContinueWith(_=>app.Dispatcher.BeginInvoke(new Action(()=>frame.Continue=false)));
        Dispatcher.PushFrame(frame);
        if(failure is not null) throw failure;
        if(task.GetAwaiter().GetResult()!=1.2) throw new Exception("Dialog did not return 1.2.");
        File.WriteAllText(Path.Combine(output,"model-scale-gui.json"),JsonSerializer.Serialize(new
            { status="PASS",defaultScale=1,invalidScaleRejected=true,acceptedScale=1.2,gameTested=false }));
        app.Shutdown();
    }

    private static void RunWristChoice(string[] args)
    {
        var output=Path.GetFullPath(args[0]);Directory.CreateDirectory(output);
        var app=new HD2ModManager.App { ShutdownMode=ShutdownMode.OnExplicitShutdown };app.InitializeComponent();
        EventManager.RegisterClassHandler(typeof(Window),FrameworkElement.LoadedEvent,new RoutedEventHandler((sender,_)=>
        {if(sender is Window w){w.Opacity=0;w.ShowInTaskbar=false;}}));
        var method=typeof(HD2ModManager.App).Assembly.GetType("HD2ModManager.Services.VpkChoicePrompt")!
            .GetMethod("ShowAsync",BindingFlags.Static|BindingFlags.NonPublic)!;
        var results=new List<object>();
        for(var test=0;test<4;test++)
        {
            var choice=test==1;Exception? failure=null;
            using var cancel=new CancellationTokenSource(TimeSpan.FromSeconds(15));
            var timer=new DispatcherTimer{Interval=TimeSpan.FromMilliseconds(50)};
            timer.Tick+=(_,_)=>
            {
                try
                {
                    var window=app.Windows.OfType<Window>().SingleOrDefault(w=>w.Title=="制作原骨架护甲");if(window is null)return;
                    timer.Stop();var panel=(StackPanel)window.Content;if(panel.Children.OfType<ComboBox>().Any() || panel.Children.OfType<TextBlock>().Any(t=>t.Text.Contains("手腕权重")))
                        throw new Exception("Original workflow dialog must not contain wrist weight UI.");
                    panel.UpdateLayout();
                    if(test<2)
                    {
                        var bitmap=new RenderTargetBitmap((int)Math.Ceiling(panel.ActualWidth+40),(int)Math.Ceiling(panel.ActualHeight+40),96,96,PixelFormats.Pbgra32);
                        var drawing=new DrawingVisual();using(var dc=drawing.RenderOpen())
                        {dc.DrawRectangle(Brushes.White,null,new Rect(0,0,bitmap.PixelWidth,bitmap.PixelHeight));dc.DrawRectangle(new VisualBrush(panel),null,new Rect(20,20,panel.ActualWidth,panel.ActualHeight));}
                        bitmap.Render(drawing);var encoder=new PngBitmapEncoder();encoder.Frames.Add(BitmapFrame.Create(bitmap));
                        using(var file=File.Create(Path.Combine(output,test==0?"workflow-single-restored.png":"workflow-dual-restored.png")))encoder.Save(file);
                    }
                    if(test==3){window.Close();return;}
                    var buttons=panel.Children.OfType<StackPanel>().Single().Children.OfType<Button>().ToArray();
                    typeof(Button).GetMethod("OnClick",BindingFlags.Instance|BindingFlags.NonPublic)!
                        .Invoke(buttons[test==2?0:choice?2:1],null);
                }
                catch(Exception e){failure=e;cancel.Cancel();}
            };
            timer.Start();
            var task=(Task<bool?>)method.Invoke(null,new object?[]{"制作原骨架护甲","模型 test07：选择单骨架或双骨架制作流程。", "是，制作双骨架护甲+lua","是，制作单原骨架护甲",cancel.Token})!;
            var frame=new DispatcherFrame();task.ContinueWith(_=>app.Dispatcher.BeginInvoke(new Action(()=>frame.Continue=false)));Dispatcher.PushFrame(frame);
            if(failure is not null)throw failure;var actual=task.GetAwaiter().GetResult();
            if(test>=2){if(actual is not null)throw new Exception("Cancel must not commit a route.");}
            else if(actual!=choice)throw new Exception("Initial workflow choice lost its route.");
            results.Add(new {test,route=actual});
        }
        File.WriteAllText(Path.Combine(output,"workflow-restored-gui.json"),JsonSerializer.Serialize(new {status="PASS",wristUiRemoved=true,bothRoutes=true,cancelNoCommit=true,results},new JsonSerializerOptions{WriteIndented=true}));
        app.Shutdown();
    }
}

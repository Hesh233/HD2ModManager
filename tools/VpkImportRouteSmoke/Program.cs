using System.IO;
using System.Reflection;
using System.Reflection.Emit;
using System.Runtime.Loader;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;

internal static class Program
{
    static string Hash(string p) => Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(p))).ToLowerInvariant();
    static readonly Dictionary<ushort, OpCode> Ops = typeof(OpCodes).GetFields(BindingFlags.Public | BindingFlags.Static)
        .Select(f => (OpCode)f.GetValue(null)!).ToDictionary(o => unchecked((ushort)o.Value));
    static string Name(MemberInfo m) => m switch
    {
        Type t => t.ToString(),
        _ => m.DeclaringType + "|" + m,
    };
    static string Body(MethodBase m)
    {
        var b = m.GetMethodBody(); if (b is null) return "none";
        var il = b.GetILAsByteArray()!; var s = new StringBuilder();
        var tg = m.DeclaringType!.GetGenericArguments(); var mg = m.IsGenericMethod ? m.GetGenericArguments() : Type.EmptyTypes;
        for (int at = 0; at < il.Length;)
        {
            ushort code = il[at++]; if (code == 0xfe) code = (ushort)(0xfe00 | il[at++]); var op = Ops[code]; s.Append(op.Name).Append(':');
            int len = op.OperandType switch { OperandType.InlineNone => 0, OperandType.InlineSwitch => 4 + 4 * BitConverter.ToInt32(il, at),
                OperandType.ShortInlineBrTarget or OperandType.ShortInlineI or OperandType.ShortInlineVar => 1,
                OperandType.InlineVar => 2, OperandType.InlineI8 or OperandType.InlineR => 8, _ => 4 };
            if (op.OperandType == OperandType.InlineString) s.Append(JsonSerializer.Serialize(m.Module.ResolveString(BitConverter.ToInt32(il, at))));
            else if (op.OperandType is OperandType.InlineMethod or OperandType.InlineField or OperandType.InlineType or OperandType.InlineTok)
                s.Append(Name(m.Module.ResolveMember(BitConverter.ToInt32(il, at), tg, mg)!));
            else s.Append(Convert.ToHexString(il.AsSpan(at, len)));
            at += len; s.Append(';');
        }
        s.Append('|').Append(b.MaxStackSize).Append('|').Append(b.InitLocals);
        foreach (var v in b.LocalVariables) s.Append('|').Append(v.LocalType).Append(':').Append(v.IsPinned);
        foreach (var e in b.ExceptionHandlingClauses)
        {
            s.Append('|').Append(e.Flags).Append(':').Append(e.TryOffset).Append(':').Append(e.TryLength).Append(':').Append(e.HandlerOffset).Append(':').Append(e.HandlerLength);
            if (e.Flags == ExceptionHandlingClauseOptions.Clause) s.Append(':').Append(e.CatchType);
            if (e.Flags == ExceptionHandlingClauseOptions.Filter) s.Append(':').Append(e.FilterOffset);
        }
        return s.ToString();
    }
    static Dictionary<string, string> Methods(Assembly a) => a.GetTypes().SelectMany(t =>
        t.GetMethods(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static | BindingFlags.DeclaredOnly).Cast<MethodBase>()
        .Concat(t.GetConstructors(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static | BindingFlags.DeclaredOnly)))
        .ToDictionary(m => m.DeclaringType + "|" + m, Body);
    static bool Allowed(string key) => new[] { "HD2ModManager.Services.VpkChoicePrompt", "HD2ModManager.Services.VpkModelDecisionPrompt", "HD2ModManager.Services.VpkModelDecision", "HD2ModManager.Services.VpkImportRoute" }.Any(key.StartsWith);
    static Assembly Load(string directory, string id)
    {
        var c = new AssemblyLoadContext(id, false);
        c.Resolving += (ctx, n) => { var p = Path.Combine(directory, n.Name + ".dll"); return File.Exists(p) ? ctx.LoadFromAssemblyPath(p) : null; };
        return c.LoadFromAssemblyPath(Path.Combine(directory, "HD2ModManager.dll"));
    }
    static void Audit(string before, string after, string output)
    {
        var a = Load(before, "before-route"); var b = Load(after, "after-route");
        if (a.FullName != b.FullName) throw new Exception("GUI assembly identity changed");
        var am = Methods(a); var bm = Methods(b); var changes = am.Keys.Union(bm.Keys).Where(k => am.GetValueOrDefault(k) != bm.GetValueOrDefault(k)).ToArray();
        var unexpected = changes.Where(k => !Allowed(k)).ToArray(); if (unexpected.Length > 0) throw new Exception("Unrelated GUI changes: " + string.Join("\n", unexpected));
        var resourceNames = a.GetManifestResourceNames(); if (!resourceNames.Order().SequenceEqual(b.GetManifestResourceNames().Order())) throw new Exception("GUI resources changed");
        foreach (var n in resourceNames)
        {
            using var x = a.GetManifestResourceStream(n)!; using var y = b.GetManifestResourceStream(n)!;
            if (!SHA256.HashData(x).SequenceEqual(SHA256.HashData(y))) throw new Exception("GUI resource changed: " + n);
        }
        File.WriteAllText(output, JsonSerializer.Serialize(new { status = "PASS_SCOPED_GUI_ONLY", beforeSha256 = Hash(Path.Combine(before, "HD2ModManager.dll")),
            afterSha256 = Hash(Path.Combine(after, "HD2ModManager.dll")), beforeMethods = am.Count, afterMethods = bm.Count, changedMethods = changes,
            unchangedResources = resourceNames.Length, semanticIlTokensResolved = true }, new JsonSerializerOptions { WriteIndented = true }));
        Console.WriteLine($"PASS GUI audit: {changes.Length} scoped methods; {am.Count} before / {bm.Count} after, resources unchanged");
    }
    static IEnumerable<T> Descendants<T>(DependencyObject root) where T : DependencyObject
    {
        if (root is T t) yield return t;
        for (int i = 0; i < VisualTreeHelper.GetChildrenCount(root); i++) foreach (var child in Descendants<T>(VisualTreeHelper.GetChild(root, i))) yield return child;
    }
    static void Click(Button b) => typeof(Button).GetMethod("OnClick", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(b, null);
    static void SavePanel(FrameworkElement panel, string path)
    {
        panel.UpdateLayout(); var image = new RenderTargetBitmap((int)Math.Ceiling(panel.ActualWidth + 40), (int)Math.Ceiling(panel.ActualHeight + 40), 96, 96, PixelFormats.Pbgra32);
        var visual = new DrawingVisual(); using (var d = visual.RenderOpen()) { d.DrawRectangle(Brushes.White, null, new Rect(0, 0, image.PixelWidth, image.PixelHeight)); d.DrawRectangle(new VisualBrush(panel), null, new Rect(20, 20, panel.ActualWidth, panel.ActualHeight)); }
        image.Render(visual); var png = new PngBitmapEncoder(); png.Frames.Add(BitmapFrame.Create(image)); using var f = File.Create(path); png.Save(f);
    }
    static void Smoke(string candidate, string output)
    {
        Directory.CreateDirectory(output); var app = new Application { ShutdownMode = ShutdownMode.OnExplicitShutdown }; var assembly = Load(candidate, "route-ui");
        EventManager.RegisterClassHandler(typeof(Window), FrameworkElement.LoadedEvent, new RoutedEventHandler((sender, _) => { if (sender is Window w) { w.Opacity = 0; w.ShowInTaskbar = false; } }));
        var choice = assembly.GetType("HD2ModManager.Services.VpkChoicePrompt", true)!.GetMethod("ShowImportRoutesAsync", BindingFlags.NonPublic | BindingFlags.Static)!;
        var full = assembly.GetType("HD2ModManager.Services.VpkModelDecisionPrompt", true)!.GetMethod("ShowAsync", BindingFlags.NonPublic | BindingFlags.Static)!;
        // This suite tests the explicitly enabled legacy dialog flow. New installs now
        // default off; use only the smoke executable's settings and restore their bytes.
        var settings = assembly.GetType("HD2ModManager.Services.SettingsService", true)!;
        var optIn = settings.GetMethod("SetAskToInstallSkeletonAnimation");
        var flush = settings.GetMethod("FlushAsync");
        var settingsPath = Path.Combine(AppContext.BaseDirectory, "settings.json");
        if (optIn is not null && Path.GetFullPath(candidate).TrimEnd(Path.DirectorySeparatorChar) == AppContext.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar))
            throw new Exception("Do not write legacy smoke settings into the candidate installation.");
        var settingsBefore = File.Exists(settingsPath) ? File.ReadAllBytes(settingsPath) : null;
        var results = new List<object>();
        try
        {
            if (optIn is not null)
            {
                if (!(bool)optIn.Invoke(null, [true])!) throw new Exception("Could not enable skeleton animation prompt in the isolated smoke settings.");
                var dualOptIn = settings.GetMethod("SetEnableDualSkeletonAnimationVersion");
                if (dualOptIn is not null && !(bool)dualOptIn.Invoke(null, [true])!) throw new Exception("Could not enable legacy dual choice in smoke settings.");
                ((Task)flush!.Invoke(null, null)!).GetAwaiter().GetResult();
            }
        foreach (var test in new[] { "original", "single", "dual", "cancel", "close", "full-original", "full-scale-cancel", "token-cancel" })
        {
            Exception? failure = null; var seen = new List<string>(); using var ct = new CancellationTokenSource(TimeSpan.FromSeconds(15));
            var timer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(40) };
            timer.Tick += (_, _) =>
            {
                try
                {
                    var w = app.Windows.OfType<Window>().SingleOrDefault(); if (w is null) return;
                    if (!seen.Contains(w.Title)) seen.Add(w.Title);
                    if (w.Title == "导入 VPK 模型格式")
                    {
                        var buttons = Descendants<Button>(w).ToDictionary(b => b.Name);
                        foreach (var n in new[] { "OriginalFormatImport", "SingleSkeletonImport", "DualSkeletonImport", "CancelVpkImport" }) if (!buttons.ContainsKey(n)) throw new Exception("Missing route button " + n);
                        if (test == "original") SavePanel((FrameworkElement)w.Content, Path.Combine(output, "vpk-original-format-dialog.png"));
                        if (test == "close") w.Close();
                        else if (test == "token-cancel") ct.Cancel();
                        else Click(buttons[test switch { "single" => "SingleSkeletonImport", "dual" => "DualSkeletonImport", "cancel" => "CancelVpkImport", _ => "OriginalFormatImport" }]);
                    }
                    else if (w.Title == "导入 VPK 模型")
                    {
                        var buttons = Descendants<Button>(w).ToArray();
                        if (test == "full-scale-cancel") Click(buttons.Single(b => b.Content?.ToString() == "取消"));
                        else Click(buttons.Single(b => b.Content?.ToString() == "开始转换"));
                    }
                    else throw new Exception("Original format unexpectedly requested " + w.Title);
                }
                catch (Exception e) { failure = e; ct.Cancel(); }
            };
            timer.Start(); var task = (Task)(test.StartsWith("full-") ? full : choice).Invoke(null, ["test1201", ct.Token])!;
            var frame = new DispatcherFrame(); task.ContinueWith(_ => app.Dispatcher.BeginInvoke(new Action(() => frame.Continue = false))); Dispatcher.PushFrame(frame); timer.Stop();
            if (failure is not null) throw failure; if (ct.IsCancellationRequested && test != "token-cancel") throw new TimeoutException("Dialog action did not complete: " + test); task.GetAwaiter().GetResult(); var result = task.GetType().GetProperty("Result")!.GetValue(task);
            if (test is "cancel" or "close" or "token-cancel" or "full-scale-cancel") { if (result is not null) throw new Exception("Cancel committed a route"); }
            else if (test == "full-original")
            {
                foreach (var property in new[] { "UseNativeSkeleton", "SingleHd2Skeleton", "GenerateAnimation", "BuildsSkeletonPackage" }) if ((bool)result!.GetType().GetProperty(property)!.GetValue(result)!) throw new Exception("Original format entered a skeleton route");
                if (seen.Count != 2) throw new Exception("Original format asked for animation worker count");
            }
            else if (result?.ToString() != (test switch { "original" => "OriginalFormat", "single" => "SingleSkeleton", _ => "DualSkeletonWithLua" })) throw new Exception("Wrong route");
            results.Add(new { test, result = result?.ToString(), windows = seen });
        }
        app.Shutdown(); File.WriteAllText(Path.Combine(output, "gui-smoke.json"), JsonSerializer.Serialize(new { status = "PASS", cases = results,
            originalFormatWithoutPythonRuntime = !File.Exists(Path.Combine(AppContext.BaseDirectory, "anim_batch_mod/runtime/python.exe")), noGameOrLibraryImport = true }, new JsonSerializerOptions { WriteIndented = true }));
        Console.WriteLine("PASS hidden WPF dialog smoke: 8 cases; original route skips runtime and animation worker prompts");
        }
        finally
        {
            if (optIn is not null)
            {
                ((Task)flush!.Invoke(null, null)!).GetAwaiter().GetResult();
                if (settingsBefore is null) File.Delete(settingsPath); else File.WriteAllBytes(settingsPath, settingsBefore);
            }
        }
    }
    [STAThread] static int Main(string[] args)
    {
        try { if (args[0] == "audit") Audit(Path.GetFullPath(args[1]), Path.GetFullPath(args[2]), Path.GetFullPath(args[3])); else Smoke(Path.GetFullPath(args[1]), Path.GetFullPath(args[2])); return 0; }
        catch (Exception e) { Console.Error.WriteLine(e); return 1; }
    }
}

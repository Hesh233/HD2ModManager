using System.Collections;
using System.IO;
using System.Reflection;
using System.Reflection.Emit;
using System.Reflection.Metadata;
using System.Reflection.PortableExecutable;
using System.Resources;
using System.Runtime.CompilerServices;
using System.Runtime.Loader;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using System.Windows.Data;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;

internal static partial class Program
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
    const string Setting = "AskToInstallSkeletonAnimation";
    static readonly JsonSerializerOptions JsonOptions = new() { WriteIndented = true };
    static void Check(bool condition, string message) { if (!condition) throw new InvalidOperationException(message); }
    static Assembly Load(string directory, string id)
    {
        var context = new AssemblyLoadContext(id, false);
        context.Resolving += (ctx, name) =>
        {
            var path = Path.Combine(directory, name.Name + ".dll");
            return File.Exists(path) ? ctx.LoadFromAssemblyPath(path) : null;
        };
        return context.LoadFromAssemblyPath(Path.Combine(directory, "HD2ModManager.dll"));
    }
    static bool Allowed(string key) => new[]
    {
        "HD2ModManager.Services.SettingsService|", "HD2ModManager.Services.SettingsService+",
        "HD2ModManager.ViewModels.SettingsPageViewModel|", "HD2ModManager.ViewModels.SettingsPageViewModel+",
        "HD2ModManager.Services.VpkModelDecisionPrompt|", "HD2ModManager.Services.VpkModelDecisionPrompt+",
        "HD2ModManager.Services.VpkModelDecisionPromptSteps|", "HD2ModManager.Services.VpkModelDecisionPromptSteps+",
        "HD2ModManager.Services.VpkChoicePrompt|", "HD2ModManager.Services.VpkChoicePrompt+",
        "HD2ModManager.Services.ModelScalePrompt|", "HD2ModManager.Services.ModelScalePrompt+",
        "HD2ModManager.Services.VpkModelScalePolicy|", "HD2ModManager.Services.VpkTargetArmorPrompt|", "HD2ModManager.Services.VpkTargetArmorPrompt+",
        "HD2ModManager.Services.VpkModelDecision|", "HD2ModManager.Services.VpkProducedPackage|",
        "HD2ModManager.Services.VpkImportService|", "HD2ModManager.Services.VpkImportService+",
        "HD2ModManager.Services.ImportService|", "HD2ModManager.Services.ImportService+",
        "HD2ModManager.Views.SettingsPageView|",
    }.Any(prefix => key.StartsWith(prefix, StringComparison.Ordinal));
    static byte[] Bytes(object value)
    {
        if (value is byte[] bytes) return bytes;
        if (value is Stream stream) { using var output = new MemoryStream(); stream.CopyTo(output); return output.ToArray(); }
        return Encoding.UTF8.GetBytes(JsonSerializer.Serialize(value));
    }
    static Dictionary<string, byte[]> Resources(Assembly assembly)
    {
        var result = new Dictionary<string, byte[]>();
        foreach (var name in assembly.GetManifestResourceNames())
        {
            using var stream = assembly.GetManifestResourceStream(name)!;
            if (name.EndsWith(".g.resources", StringComparison.Ordinal))
            {
                using var reader = new ResourceReader(stream);
                foreach (DictionaryEntry entry in reader) result.Add(name + "/" + entry.Key, Bytes(entry.Value!));
            }
            else result.Add(name, Bytes(stream));
        }
        return result;
    }
    static byte[] NormalizeIdentity(byte[] data, string oldIdentity, string newIdentity)
    {
        var oldBytes = Encoding.UTF8.GetBytes(oldIdentity); var newBytes = Encoding.UTF8.GetBytes(newIdentity);
        if (oldBytes.Length != newBytes.Length) return data;
        var copy = data.ToArray();
        for (int i = 0; i <= copy.Length - oldBytes.Length; i++)
            if (copy.AsSpan(i, oldBytes.Length).SequenceEqual(oldBytes)) newBytes.CopyTo(copy, i);
        return copy;
    }
    static object ValidateSymbols(string directory)
    {
        using var image = File.OpenRead(Path.Combine(directory, "HD2ModManager.dll"));
        using var pe = new PEReader(image);
        var entry = pe.ReadDebugDirectory().Single(e => e.Type == DebugDirectoryEntryType.CodeView);
        var codeView = pe.ReadCodeViewDebugDirectoryData(entry);
        using var pdb = File.OpenRead(Path.Combine(directory, "HD2ModManager.pdb"));
        using var provider = MetadataReaderProvider.FromPortablePdbStream(pdb);
        var id = provider.GetMetadataReader().DebugMetadataHeader!.Id.ToArray();
        Check(new Guid(id.AsSpan(0, 16)) == codeView.Guid && BitConverter.ToUInt32(id, 16) == entry.Stamp, "GUI portable PDB identity does not match its assembly");
        return new { status = "PASS", guid = codeView.Guid, stamp = entry.Stamp, age = codeView.Age };
    }
    static void Audit(string before, string after, string output)
    {
        var symbols = ValidateSymbols(after);
        var a = Load(before, "prompt-before"); var b = Load(after, "prompt-after");
        Check(a.GetName().Name == b.GetName().Name, "Application assembly name changed");
        Check(a.GetReferencedAssemblies().Select(n => n.FullName).Order().SequenceEqual(b.GetReferencedAssemblies().Select(n => n.FullName).Order()), "GUI assembly references changed");
        var am = Methods(a); var bm = Methods(b);
        var changed = am.Keys.Union(bm.Keys).Where(k => am.GetValueOrDefault(k) != bm.GetValueOrDefault(k)).ToArray();
        var unexpected = changed.Where(k => !Allowed(k)).ToArray();
        var ar = Resources(a); var br = Resources(b);
        Check(ar.Keys.Order().SequenceEqual(br.Keys.Order()), "GUI resource names changed");
        var resources = ar.Keys.Where(k => !NormalizeIdentity(ar[k], a.FullName!, b.FullName!).SequenceEqual(br[k])).ToArray();
        var badResources = resources.Where(k => !k.EndsWith("/views/settingspageview.baml", StringComparison.OrdinalIgnoreCase)).ToArray();
        var report = new { status = unexpected.Length == 0 && badResources.Length == 0 ? "PASS" : "FAIL", beforeAssembly = a.FullName, afterAssembly = b.FullName,
            beforeMethods = am.Count, afterMethods = bm.Count, portablePdbIdentity = symbols, changedMethods = changed, unexpectedMethods = unexpected,
            changedResources = resources, unexpectedResources = badResources, allReferencesResolvedAgainstCandidateDependencies = true,
            beforeSha256 = Hash(Path.Combine(before, "HD2ModManager.dll")), afterSha256 = Hash(Path.Combine(after, "HD2ModManager.dll")) };
        File.WriteAllText(output, JsonSerializer.Serialize(report, JsonOptions));
        Check(unexpected.Length == 0, "Unexpected GUI changes: " + string.Join("\n", unexpected));
        Check(badResources.Length == 0, "Unexpected GUI resources: " + string.Join("\n", badResources));
        Console.WriteLine($"PASS GUI audit: {changed.Length} scoped methods; {resources.Length} settings resource; unchanged references");
    }
    static object? Invoke(MethodInfo method, object? instance, params object?[] arguments)
    {
        try { return method.Invoke(instance, arguments); }
        catch (TargetInvocationException e) when (e.InnerException is not null) { System.Runtime.ExceptionServices.ExceptionDispatchInfo.Capture(e.InnerException).Throw(); throw; }
    }
    static T Value<T>(object value, string property) => (T)value.GetType().GetProperty(property)!.GetValue(value)!;
    static IEnumerable<T> Descendants<T>(DependencyObject root) where T : DependencyObject
    {
        if (root is T found) yield return found;
        foreach (var child in LogicalTreeHelper.GetChildren(root).OfType<DependencyObject>())
            foreach (var nested in Descendants<T>(child)) yield return nested;
    }
    static void Pump(Task task, Dispatcher dispatcher)
    {
        if (task.IsCompleted) return;
        var frame = new DispatcherFrame();
        task.ContinueWith(_ => dispatcher.BeginInvoke(new Action(() => frame.Continue = false)));
        Dispatcher.PushFrame(frame);
    }
    static void Click(Button button) => button.RaiseEvent(new RoutedEventArgs(Button.ClickEvent, button));
    static void SavePanel(FrameworkElement panel, string path)
    {
        panel.UpdateLayout(); int width = Math.Max(1, (int)Math.Ceiling(panel.ActualWidth)); int height = Math.Max(1, (int)Math.Ceiling(panel.ActualHeight));
        var bitmap = new RenderTargetBitmap(width, height, 96, 96, PixelFormats.Pbgra32); bitmap.Render(panel);
        var encoder = new PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(bitmap)); using var stream = File.Create(path); encoder.Save(stream);
    }
    static void Verify(string candidate, string output, string realRuntime, bool showDialogs)
    {
        var sandbox = AppContext.BaseDirectory;
        Check(File.Exists(Path.Combine(sandbox, "SMOKE-SANDBOX.marker")), "Refuse settings tests outside an explicit smoke sandbox");
        Directory.CreateDirectory(output);
        var settingsPath = Path.Combine(sandbox, "settings.json");
        Check(!File.Exists(settingsPath), "Smoke sandbox already has settings; use a new verification directory");
        var assembly = Load(candidate, "prompt-verified-ui");
        var service = assembly.GetType("HD2ModManager.Services.SettingsService", true)!;
        var get = service.GetMethod("Get" + Setting)!; var set = service.GetMethod("Set" + Setting)!; var flush = service.GetMethod("FlushAsync")!;
        var cached = service.GetField("_cachedSettings", BindingFlags.NonPublic | BindingFlags.Static)!;
        var prompt = assembly.GetType("HD2ModManager.Services.VpkModelDecisionPrompt", true)!.GetMethod("ShowAsync", BindingFlags.NonPublic | BindingFlags.Static)!;
        var results = new List<object>();
        void Add(string name, object? detail = null) => results.Add(new { test = name, status = "PASS", detail });
        void Flush() => ((Task)Invoke(flush, null)!).GetAwaiter().GetResult();
        bool Read() => (bool)Invoke(get, null)!;
        void Set(bool enabled) { Check((bool)Invoke(set, null, enabled)!, "Setting setter failed"); Flush(); }
        void Reset(string? json)
        {
            Flush(); cached.SetValue(null, null);
            if (json is null) File.Delete(settingsPath); else File.WriteAllText(settingsPath, json);
        }
        object? Direct(CancellationToken token = default)
        {
            var task = (Task)Invoke(prompt, null, "smoke-only-model", token)!;
            Check(task.IsCompleted, "Disabled setting unexpectedly waited for a UI dialog"); task.GetAwaiter().GetResult();
            return task.GetType().GetProperty("Result")!.GetValue(task);
        }
        void Original(object? result, double scale)
        {
            Check(result is not null, "Original format returned no decision");
            foreach (var name in new[] { "UseNativeSkeleton", "SingleHd2Skeleton", "GenerateAnimation", "BuildsSkeletonPackage" }) Check(!Value<bool>(result!, name), "Original format enabled " + name);
            Check(Value<double>(result!, "ModelScale") == scale, "Wrong original model scale");
        }
        Check(!Read(), "Fresh settings must default off"); Original(Direct(), 1); Check(!File.Exists(settingsPath), "Reading default created settings.json"); Add("fresh-default-off-no-dialogs-no-settings-write");
        var legacy = new JsonObject
        {
            ["Language"] = "zh-CN", ["HeadScale"] = 1.23, ["DefaultExportPath"] = "Output/keep-user-choice", ["AutoImportToActiveProfile"] = false,
            ["BuiltInLuaEnabled"] = false, ["PhysicsMode"] = 0, ["ArmorMappingMode"] = 0, ["MappingModeSchema"] = 1,
            ["SelectedProfileKey"] = "preserved-profile", ["ModLibraryFolder"] = "preserved-library", ["GameDataFolder"] = "preserved-game-path",
            ["CustomCategories"] = new JsonArray(new JsonObject { ["Id"] = "keep", ["Name"] = "保留分类" }),
            ["CategoryOverrides"] = new JsonObject { ["preserved-mod-id"] = "keep" },
        };
        Reset(legacy.ToJsonString()); var legacyHash = Hash(settingsPath);
        Check(!Read(), "Missing legacy field must default off"); Original(Direct(), 1); Check(Hash(settingsPath) == legacyHash, "Reading legacy setting rewrote the file"); Add("legacy-missing-field-default-off-byte-preserved");
        Reset("{invalid json"); var invalidHash = Hash(settingsPath); Check(!Read(), "Corrupt settings must safely default off"); Original(Direct(), 1); Check(Hash(settingsPath) == invalidHash, "Corrupt settings were overwritten"); Add("unreadable-setting-safe-original-no-write");
        Reset(legacy.ToJsonString()); Set(false); Check(!Read(), "Explicit off was not read"); Original(Direct(), 1); Add("explicit-off-original-without-python");
        using (var canceled = new CancellationTokenSource()) { canceled.Cancel(); try { Direct(canceled.Token); throw new Exception("Canceled import committed original format"); } catch (OperationCanceledException) { } }
        Add("disabled-pre-canceled-import-remains-canceled");
        Set(true); if (showDialogs) { Invoke(service.GetMethod("SetEnableDualSkeletonAnimationVersion")!, null, true); Flush(); } cached.SetValue(null, null); Check(Read(), "On setting did not persist after cache reset");
        var saved = JsonNode.Parse(File.ReadAllText(settingsPath))!.AsObject();
        foreach (var pair in legacy) Check(JsonNode.DeepEquals(pair.Value, saved[pair.Key]), "Existing setting changed: " + pair.Key);
        Add("enabled-setting-persists-and-preserves-other-settings");
        var app = (Application)Activator.CreateInstance(assembly.GetType("HD2ModManager.App", true)!)!;
        app.ShutdownMode = ShutdownMode.OnExplicitShutdown;
        Invoke(assembly.GetType("HD2ModManager.App", true)!.GetMethod("InitializeComponent")!, app);
        EventManager.RegisterClassHandler(typeof(Window), FrameworkElement.LoadedEvent, new RoutedEventHandler((sender, _) => { if (sender is Window window) { window.Opacity = 0; window.ShowInTaskbar = false; } }));
        object? Dialog(string test, string route, bool cancelScale = false, bool cancelThreads = false, bool closeRoute = false, bool cancelToken = false, bool expectMissingRuntime = false)
        {
            var seen = new List<string>(); Exception? actionFailure = null; using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(15));
            var timer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(35) };
            timer.Tick += (_, _) =>
            {
                try
                {
                    var window = app.Windows.OfType<Window>().SingleOrDefault(); if (window is null) return;
                    if (!seen.Contains(window.Title)) seen.Add(window.Title);
                    var buttons = Descendants<Button>(window).ToArray();
                    if (window.Title == "导入 VPK 模型格式")
                    {
                        foreach (var name in new[] { "OriginalFormatImport", "SingleSkeletonImport", "DualSkeletonImport", "CancelVpkImport" }) Check(buttons.Any(b => b.Name == name), "Missing route: " + name);
                        if (cancelToken) cts.Cancel(); else if (closeRoute) window.Close(); else Click(buttons.Single(b => b.Name == route));
                    }
                    else if (window.Title == "导入 VPK 模型")
                    {
                        Descendants<TextBox>(window).Single().Text = "1.4";
                        Click(buttons.Single(b => b.Content?.ToString() == (cancelScale ? "取消" : "开始转换")));
                    }
                    else if (window.Title == "全量动画文件打包")
                    {
                        Descendants<TextBox>(window).Single().Text = "3";
                        Click(buttons.Single(b => b.Content?.ToString() == (cancelThreads ? "取消" : "确认")));
                    }
                    else throw new Exception("Unexpected import dialog: " + window.Title);
                }
                catch (Exception error) { actionFailure = error; cts.Cancel(); }
            };
            timer.Start(); var task = (Task)Invoke(prompt, null, "smoke-only-model", cts.Token)!; Pump(task, app.Dispatcher); timer.Stop();
            if (actionFailure is not null) throw actionFailure;
            Check(!cts.IsCancellationRequested || cancelToken, "Dialog timed out: " + test);
            object? result;
            try { task.GetAwaiter().GetResult(); result = task.GetType().GetProperty("Result")!.GetValue(task); }
            catch (InvalidOperationException error) when (expectMissingRuntime && error.Message.Contains("Python", StringComparison.Ordinal))
            { Check(seen.Count == 1, "Missing runtime guard should precede scale/thread prompts"); Add(test, new { windows = seen, runtimeGuard = true }); return null; }
            Check(!expectMissingRuntime, "Skeleton path unexpectedly accepted missing runtime");
            Check(app.Windows.Count == 0, "Dialog remained open");
            if (route == "CancelVpkImport" || cancelScale || cancelThreads || closeRoute || cancelToken) Check(result is null, "Canceled import returned a decision");
            else if (route == "OriginalFormatImport") { Original(result, 1.4); Check(seen.Count == 2, "Original format asked for animation threads"); }
            else
            {
                Check(result is not null && Value<bool>(result, "BuildsSkeletonPackage") && Value<bool>(result, "GenerateAnimation"), "Skeleton decision lost animation request");
                Check(Value<bool>(result!, "SingleHd2Skeleton") == (route == "SingleSkeletonImport"), "Wrong single skeleton flag");
                Check(Value<bool>(result!, "UseNativeSkeleton") == (route == "DualSkeletonImport"), "Wrong dual skeleton flag");
                Check(Value<double>(result!, "ModelScale") == 1.4 && Value<int>(result!, "AnimationThreads") == 3 && seen.Count == 3, "Scale/threads dialog behavior changed");
            }
            Add(test, new { windows = seen, result = result?.ToString() }); return result;
        }
        if (showDialogs)
        {
            Dialog("enabled-original-dialogs-without-runtime", "OriginalFormatImport");
            Dialog("enabled-single-missing-runtime-guard", "SingleSkeletonImport", expectMissingRuntime: true);
            Dialog("enabled-dual-missing-runtime-guard", "DualSkeletonImport", expectMissingRuntime: true);
            Dialog("enabled-cancel-route", "CancelVpkImport");
            Dialog("enabled-close-route", "OriginalFormatImport", closeRoute: true);
            Dialog("enabled-cancel-scale", "OriginalFormatImport", cancelScale: true);
            Dialog("enabled-cancel-token", "OriginalFormatImport", cancelToken: true);
        }
        else
        {
            // Safer fallback: inspect the unchanged prompt helpers and actual policies without
            // calling Window.Show/ShowDialog or creating any native UI window.
            VerifyImportOptions(assembly, app, output, Add);
        }
        // Real accepted files only satisfy the existing availability check; no Python process is executed.
        var pythonSource = Path.Combine(realRuntime, "runtime", "python.exe"); var scriptSource = Path.Combine(realRuntime, "main.py");
        Check(File.Exists(pythonSource) && File.Exists(scriptSource), "Missing real runtime fixture");
        var python = Path.Combine(sandbox, "anim_batch_mod", "runtime", "python.exe"); var script = Path.Combine(sandbox, "anim_batch_mod", "main.py");
        Directory.CreateDirectory(Path.GetDirectoryName(python)!); File.Copy(pythonSource, python); File.Copy(scriptSource, script);
        Check(Hash(pythonSource) == Hash(python) && Hash(scriptSource) == Hash(script), "Runtime fixture bytes changed");
        if (showDialogs)
        {
            Dialog("enabled-single-retains-scale-and-animation-threads", "SingleSkeletonImport");
            Dialog("enabled-dual-retains-scale-and-animation-threads", "DualSkeletonImport");
            Dialog("enabled-cancel-animation-threads", "SingleSkeletonImport", cancelThreads: true);
        }
        else
        {
            var decisionType = assembly.GetType("HD2ModManager.Services.VpkModelDecision", true)!;
            var routeType = assembly.GetType("HD2ModManager.Services.VpkImportRoute", true)!;
            var factory = decisionType.GetMethod("ForImportRoute")!;
            foreach (var route in new[] { "OriginalFormat", "SingleSkeleton", "DualSkeletonWithLua" })
            {
                var decision = Invoke(factory, null, Enum.Parse(routeType, route), 1.4, 3)!;
                if (route == "OriginalFormat") Original(decision, 1.4);
                else
                {
                    Check(Value<bool>(decision, "BuildsSkeletonPackage") && Value<bool>(decision, "GenerateAnimation"), "Enabled skeleton policy lost animation");
                    Check(Value<bool>(decision, "SingleHd2Skeleton") == (route == "SingleSkeleton") && Value<bool>(decision, "UseNativeSkeleton") == (route == "DualSkeletonWithLua"), "Wrong skeleton policy");
                    Check(Value<double>(decision, "ModelScale") == 1.4 && Value<int>(decision, "AnimationThreads") == 3, "Existing scale/thread policy changed");
                }
                Add("enabled-" + route + "-actual-policy-factory");
            }
            var threads = assembly.GetType("HD2ModManager.Services.AnimationThreadCount", true)!.GetMethod("Parse")!;
            foreach (var text in new[] { "1", "2", "3", "16" }) { Check((int)Invoke(threads, null, text)! == int.Parse(text), "Valid thread value rejected"); Add("thread-accept-" + text); }
            foreach (var text in new[] { "0", "17", "1.5", "" })
            { try { Invoke(threads, null, text); throw new Exception("Invalid thread value accepted"); } catch (ArgumentException) { } Add("thread-reject-" + (text.Length == 0 ? "empty" : text)); }
            Set(false); Original(Direct(), 1); Set(true); Add("off-skips-prompts-even-when-runtime-is-present");
        }
        using (var canceled = new CancellationTokenSource()) { canceled.Cancel(); try { Direct(canceled.Token); throw new Exception("Enabled canceled import committed"); } catch (OperationCanceledException) { } }
        Add("enabled-pre-canceled-import-remains-canceled");
        var vmType = assembly.GetType("HD2ModManager.ViewModels.SettingsPageViewModel", true)!;
        var vm = RuntimeHelpers.GetUninitializedObject(vmType); var property = vmType.GetProperty(Setting)!;
        property.SetValue(vm, false); Flush(); Check(!Read() && !(bool)property.GetValue(vm)!, "Viewmodel off did not persist");
        var view = (UserControl)Activator.CreateInstance(assembly.GetType("HD2ModManager.Views.SettingsPageView", true)!)!;
        var toggle = (CheckBox)view.FindName("AskToInstallSkeletonAnimationToggle"); Check(toggle is not null, "Missing actual compiled settings toggle");
        var binding = BindingOperations.GetBinding(toggle!, ToggleButton.IsCheckedProperty);
        Check(binding?.Path.Path == Setting && binding.Mode == BindingMode.TwoWay, "Toggle is not bound TwoWay to its setting");
        DependencyObject ancestor = toggle!; while (ancestor is not Border) ancestor = LogicalTreeHelper.GetParent(ancestor)!;
        var card = (Border)ancestor; ((Panel)card.Parent).Children.Remove(card); card.DataContext = vm;
        var surface = new Border { Background = Brushes.White, Padding = new Thickness(16), Child = card, Width = 780 };
        Window? host = showDialogs ? new Window { Content = surface, Width = 780, SizeToContent = SizeToContent.Height, WindowStyle = WindowStyle.None, Left = -4000, Top = -4000, ShowInTaskbar = false } : null;
        if (showDialogs) { host!.Show(); host.UpdateLayout(); }
        else { surface.Measure(new Size(780, double.PositiveInfinity)); surface.Arrange(new Rect(new Point(), new Size(780, surface.DesiredSize.Height))); surface.UpdateLayout(); }
        Check(toggle!.IsChecked == false, "Compiled UI did not show disabled setting"); SavePanel(surface, Path.Combine(output, "settings-general-default-off.png"));
        toggle.SetCurrentValue(ToggleButton.IsCheckedProperty, true); Flush(); Check(Read() && (bool)property.GetValue(vm)!, "UI toggle on did not reach the production settings service");
        SavePanel(surface, Path.Combine(output, "settings-general-enabled.png")); toggle.SetCurrentValue(ToggleButton.IsCheckedProperty, false); Flush(); Check(!Read(), "UI toggle off did not persist");
        host?.Close(); Check(app.Windows.Count == 0, "Headless verification created a native window"); Add("real-compiled-general-toggle-two-way-off-on-off-and-layout");
        cached.SetValue(null, null); Check(!Read(), "Off setting did not survive reload"); Original(Direct(), 1); Check(app.Windows.Count == 0, "Off after on opened a dialog"); Add("switch-off-again-immediate-original-import-after-reload");
        saved = JsonNode.Parse(File.ReadAllText(settingsPath))!.AsObject(); foreach (var pair in legacy) Check(JsonNode.DeepEquals(pair.Value, saved[pair.Key]), "UI test changed existing setting: " + pair.Key);
        Add("all-existing-settings-preserved-after-ui-roundtrip");
        app.Shutdown(); Flush();
        var report = new { status = "PASS", candidate, cases = results, count = results.Count, defaultOff = true, dualDefaultOff = true, verificationMode = showDialogs ? "hidden-modal-dialogs" : "headless-controls-and-policy", modalDialogsExecuted = showDialogs,
            offModelScale = 1, settingName = Setting, pythonExecuted = false, gameOrLibraryImported = false,
            realRuntimeFixture = new { pythonSha256 = Hash(python), mainSha256 = Hash(script) } };
        File.WriteAllText(Path.Combine(output, "prompt-toggle-smoke.json"), JsonSerializer.Serialize(report, JsonOptions));
        Console.WriteLine($"PASS skeleton animation prompt: {results.Count} cases; actual compiled UI; no imports, Python execution, or game changes");
    }
    [STAThread] static int Main(string[] args)
    {
        try
        {
            if (args[0] == "audit") Audit(Path.GetFullPath(args[1]), Path.GetFullPath(args[2]), Path.GetFullPath(args[3]));
            else Verify(Path.GetFullPath(args[1]), Path.GetFullPath(args[2]), Path.GetFullPath(args[3]), showDialogs: args[0] == "verify");
            return 0;
        }
        catch (Exception error) { Console.Error.WriteLine(error); return 1; }
    }
}

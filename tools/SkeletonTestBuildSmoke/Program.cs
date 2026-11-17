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

using System.Windows.Input;

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
        "HD2ModManager.App|Void OnStartup(", "HD2ModManager.App|Void <OnStartup>",
        "HD2ModManager.App|System.Windows.MessageBoxResult <OnStartup>",
        "HD2ModManager.App+<>c|", "HD2ModManager.App+<>c__DisplayClass",
        "HD2ModManager.Services.SkeletonTestBuild|",
        "HD2ModManager.Services.AppUpdateService|", "HD2ModManager.Services.AppUpdateService+",
        "HD2ModManager.ViewModels.AppUpdateSectionViewModel|", "HD2ModManager.ViewModels.AppUpdateSectionViewModel+",
        "HD2ModManager.Views.AppUpdateCard|",
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
        var a = Load(before, "test-build-before"); var b = Load(after, "test-build-after");
        Check(a.GetName().FullName == b.GetName().FullName, "GUI assembly identity/version changed");
        Check(a.GetReferencedAssemblies().Select(n => n.FullName).Order().SequenceEqual(b.GetReferencedAssemblies().Select(n => n.FullName).Order()), "GUI assembly references changed");
        var am = Methods(a); var bm = Methods(b);
        var changed = am.Keys.Union(bm.Keys).Where(k => am.GetValueOrDefault(k) != bm.GetValueOrDefault(k)).ToArray();
        var unexpected = changed.Where(k => !Allowed(k)).ToArray();
        var ar = Resources(a); var br = Resources(b);
        Check(ar.Keys.Order().SequenceEqual(br.Keys.Order()), "GUI resource names changed");
        var resources = ar.Keys.Where(k => !NormalizeIdentity(ar[k], a.FullName!, b.FullName!).SequenceEqual(br[k])).ToArray();
        var badResources = resources.Where(k => !k.EndsWith("/views/appupdatecard.baml", StringComparison.OrdinalIgnoreCase)).ToArray();
        var report = new { status = unexpected.Length == 0 && badResources.Length == 0 ? "PASS" : "FAIL", beforeAssembly = a.FullName, afterAssembly = b.FullName,
            beforeMethods = am.Count, afterMethods = bm.Count, portablePdbIdentity = symbols, changedMethods = changed, unexpectedMethods = unexpected,
            changedResources = resources, unexpectedResources = badResources, allReferencesResolvedAgainstCandidateDependencies = true,
            beforeSha256 = Hash(Path.Combine(before, "HD2ModManager.dll")), afterSha256 = Hash(Path.Combine(after, "HD2ModManager.dll")) };
        File.WriteAllText(output, JsonSerializer.Serialize(report, JsonOptions));
        Check(unexpected.Length == 0, "Unexpected GUI changes: " + string.Join("\n", unexpected));
        Check(badResources.Length == 0, "Unexpected GUI resources: " + string.Join("\n", badResources));
        Console.WriteLine($"PASS GUI audit: {changed.Length} scoped methods; {resources.Length} update-card resource; unchanged identity/references; matching PDB");
    }

    static object? Invoke(MethodInfo method, object? instance, params object?[] args)
    {
        try { return method.Invoke(instance, args); }
        catch (TargetInvocationException ex) when (ex.InnerException is not null)
        { System.Runtime.ExceptionServices.ExceptionDispatchInfo.Capture(ex.InnerException).Throw(); throw; }
    }
    static T Value<T>(object instance, string name) => (T)instance.GetType().GetProperty(name)!.GetValue(instance)!;
    static object? Field(object instance, string name) => instance.GetType().GetField(name, BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(instance);
    static IEnumerable<DependencyObject> Descendants(DependencyObject root)
    {
        yield return root;
        foreach (var child in LogicalTreeHelper.GetChildren(root).OfType<DependencyObject>())
            foreach (var descendant in Descendants(child)) yield return descendant;
    }
    static void Render(FrameworkElement panel, double width, string path)
    {
        panel.Width = width;
        panel.Measure(new Size(width, double.PositiveInfinity));
        panel.Arrange(new Rect(new Point(), new Size(width, panel.DesiredSize.Height))); panel.UpdateLayout();
        var bitmap = new RenderTargetBitmap((int)Math.Ceiling(width), (int)Math.Ceiling(panel.ActualHeight), 96, 96, PixelFormats.Pbgra32);
        bitmap.Render(panel); var encoder = new PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(bitmap));
        using var stream = File.Create(path); encoder.Save(stream);
    }

    static void Verify(string candidate, string output)
    {
        var sandbox = AppContext.BaseDirectory;
        Check(File.Exists(Path.Combine(sandbox, "SMOKE-SANDBOX.marker")), "Refuse writes outside an explicit smoke sandbox");
        Check(!Directory.Exists(Path.Combine(sandbox, "config")), "Use a fresh smoke executable directory");
        Directory.CreateDirectory(output);
        var assembly = Load(candidate, "skeleton-test-ui");
        var results = new List<object>();
        void Add(string name, object? detail = null) => results.Add(new { test = name, status = "PASS", detail });
        var build = assembly.GetType("HD2ModManager.Services.SkeletonTestBuild", true)!;
        var noticeTitle = (string)build.GetField("NoticeTitle")!.GetRawConstantValue()!;
        var noticeText = (string)build.GetField("NoticeText")!.GetRawConstantValue()!;
        const string expectedNotice = "此为全量动画转换的骨架测试版本，使用自定义骨架，有效解决体型，双开门，身高，陷地问题。\n"
            + "物理模式当前使用A2.3.21，请使用安装路径“运行时配套\\物理运行时.zip”，仅启用一份物理运行时\n"
            + "全量动画文件替换后只能为单个mod服务，即其他甲的形状也会变成mod甲的形状\n"
            + "相关开关按钮在设置界面，开启是否询问安装骨架动画开关即可";
        Check(noticeTitle == "骨架测试版本", "Wrong startup caption"); Add("startup-title-exact");
        Check(noticeText == expectedNotice, "Startup message differs from the user's exact text"); Add("startup-four-line-message-exact-including-punctuation-and-runtime-name");
        var appType = assembly.GetType("HD2ModManager.App", true)!;
        var startup = appType.GetMethod("OnStartup", BindingFlags.NonPublic | BindingFlags.Instance)!;
        var startupIl = Body(startup);
        Check(!startupIl.Contains("LastMappingModeWasMigrated", StringComparison.Ordinal), "Notice still depends on mapping migration"); Add("notice-unconditional-on-every-startup");
        Check(startupIl.Contains("InvokeAsync", StringComparison.Ordinal) && startupIl.Contains("ldc.i4.2:", StringComparison.Ordinal), "Notice is not dispatched at ApplicationIdle"); Add("notice-scheduled-after-owner-load-at-application-idle");
        var startupCallbacks = appType.GetMethods(BindingFlags.NonPublic | BindingFlags.Instance).Where(m => m.Name.StartsWith("<OnStartup>", StringComparison.Ordinal)).ToArray();
        var noticeCallbacks = startupCallbacks.Where(m => Body(m).Contains("HD2ModManager.Views.AppDialog", StringComparison.Ordinal)).ToArray();
        Check(noticeCallbacks.Length == 1, "Missing/duplicate notice callback");
        var callbackIl = Body(noticeCallbacks[0]);
        Check(callbackIl.Contains(JsonSerializer.Serialize(noticeText), StringComparison.Ordinal) && callbackIl.Contains(JsonSerializer.Serialize(noticeTitle), StringComparison.Ordinal), "Startup dialog does not use the declared notice"); Add("actual-startup-callback-uses-exact-title-and-message");
        Check(callbackIl.Contains("get_MainWindow", StringComparison.Ordinal), "Startup dialog has no main-window owner"); Add("actual-startup-callback-passes-main-window-owner");
        Check(!(bool)build.GetProperty("UpdatesEnabled")!.GetValue(null)!, "Skeleton build enables self-updates"); Add("shared-build-policy-disables-updates");
        var version = assembly.GetCustomAttribute<AssemblyInformationalVersionAttribute>()!.InformationalVersion.Split('+')[0];
        foreach (var sample in new[] { version, "1.5.18", "2.0.0", "2.1.0-test.1" })
        {
            Check((string)Invoke(build.GetMethod("VersionText")!, null, sample)! == "骨架修复1.01", "Wrong skeleton repair version");
            Add("repair-display-independent-of-base-" + sample);
        }

        // Resource-only App construction must never pump the Dispatcher: Application's queued startup would run the production Shell.
        // Also pin all fallback paths to empty sandbox directories as defense in depth against a future test-harness mistake.
        var mockGame = Path.Combine(sandbox, "mock-game-data"); var mockMods = Path.Combine(sandbox, "mock-mods");
        Directory.CreateDirectory(mockGame); Directory.CreateDirectory(mockMods);
        var settingsPath = Path.Combine(sandbox, "settings.json");
        File.WriteAllText(settingsPath, JsonSerializer.Serialize(new { GameDataFolder = mockGame, ModLibraryFolder = mockMods,
            Language = "zh-CN", MappingModeSchema = 1, ArmorMappingMode = 0, PhysicsMode = 0, BuiltInLuaEnabled = false,
            AutoImportToActiveProfile = false, AutoUpdateAssetMetadata = false, AutoCheckGameDataIndex = false,
            AskToInstallSkeletonAnimation = false, EnableDualSkeletonAnimationVersion = false }));
        var config = Path.Combine(sandbox, "config"); var run = Path.Combine(sandbox, "cache", "app-update");
        Directory.CreateDirectory(config); Directory.CreateDirectory(run);
        var prefsPath = Path.Combine(config, "app-update.json");
        File.WriteAllText(prefsPath, "{\n  \"Version\": 1, \"AutoCheck\": true, \"AutoUpdate\": true, \"Skipped\": \"1.5.16\", \"DownloadSource\": 1, \"MirrorId\": \"\", \"CustomMirror\": \"https://mirror.example.com/\"\n}\n");
        var checkPath = Path.Combine(config, "update-checks.json");
        var cache = new {
            At = "2026-11-14T08:00:00+08:00", Current = version,
            List = new[] { new { TagName = "v9.9.9", Name = "cached newer version", Body = "do not download", Draft = false, Prerelease = false,
                HtmlUrl = "https://github.com/AssestinaR/HD2ModManager/releases/tag/v9.9.9", PublishedAt = "2026-11-14T07:00:00+08:00",
                Assets = new[] { new { Name = "HD2ModManager-9.9.9-win-x64-complete.zip", Url = "https://github.com/AssestinaR/HD2ModManager/releases/download/v9.9.9/HD2ModManager-9.9.9-win-x64-complete.zip", Digest = "sha256:" + new string('a', 64), Size = 1234L } } } },
        };
        File.WriteAllText(checkPath, JsonSerializer.Serialize(cache));
        var packagePath = Path.Combine(sandbox, "update-package.json"); File.WriteAllText(packagePath, "{\"version\":\"" + version + "\",\"variant\":\"complete\"}");
        var resultPath = Path.Combine(run, "result.json"); File.WriteAllText(resultPath, "{\"ok\":true,\"version\":\"9.9.9\",\"message\":\"preserve-me\"}");
        var zipPath = Path.Combine(run, "retained.zip"); File.WriteAllText(zipPath, "preserve updater ZIP cache");
        var partPath = Path.Combine(run, "retained.zip.part"); File.WriteAllText(partPath, "preserve updater part cache");
        var sentinels = new[] { settingsPath, prefsPath, checkPath, packagePath, resultPath, zipPath, partPath }.ToDictionary(p => p, Hash);
        void PreserveSentinels()
        {
            foreach (var pair in sentinels) Check(File.Exists(pair.Key) && Hash(pair.Key) == pair.Value, "Updater altered saved preference/cache/result: " + pair.Key);
        }
        var app = (Application)Activator.CreateInstance(appType)!;
        app.ShutdownMode = ShutdownMode.OnExplicitShutdown; Invoke(appType.GetMethod("InitializeComponent")!, app);
        Check(app.StartupUri.ToString() == "MainWindow.xaml", "Startup window changed"); Add("startup-uri-remains-main-window");
        var notifications = Activator.CreateInstance(assembly.GetType("HD2ModManager.Services.NotificationService", true)!)!;
        var serviceType = assembly.GetType("HD2ModManager.Services.AppUpdateService", true)!;
        var service = Invoke(serviceType.GetMethod("Initialize")!, null, notifications, (Func<bool>)(() => true))!;
        var updater = serviceType.GetProperty("Updater")!.GetValue(service)!;
        Check((bool)Field(updater, "_stopped")!, "Updater did not enter terminal stopped state"); Add("updater-terminally-stopped-with-existing-auto-check-and-auto-install-enabled");
        Check(Field(updater, "_timer") is null && Field(updater, "_checking") is null, "Updater scheduled a timer or request"); Add("no-auto-check-timer-or-request-created");
        var snapshot = Invoke(updater.GetType().GetMethod("View")!, updater)!;
        Check(Value<string>(snapshot, "Current") == version, "Version came from the smoke executable instead of GUI assembly"); Add("current-version-read-from-actual-gui-assembly-not-entry-host");
        var prefs = snapshot.GetType().GetProperty("Prefs")!.GetValue(snapshot)!;
        Check(Value<bool>(prefs, "AutoCheck") && Value<bool>(prefs, "AutoUpdate"), "Saved preferences were forcibly reset"); Add("saved-auto-update-preferences-remain-true-but-inert");
        var check = snapshot.GetType().GetProperty("Check")!.GetValue(snapshot)!;
        Check(Value<object>(check, "Phase").ToString() == "Available", "Cached available-release scenario was not exercised"); Add("cached-newer-release-loaded-but-cannot-update");
        Check(((IEnumerable)notifications.GetType().GetProperty("Items")!.GetValue(notifications)!).Cast<object>().Count() == 0, "Updater showed a previous-result or available-release notification"); Add("no-previous-result-or-cached-release-notification");
        PreserveSentinels(); Add("initialize-does-not-consume-result-or-clean-zip-part-cache");
        Invoke(serviceType.GetMethod("OnUpdaterChanged", BindingFlags.Instance | BindingFlags.NonPublic)!, service);
        Check(((IEnumerable)notifications.GetType().GetProperty("Items")!.GetValue(notifications)!).Cast<object>().Count() == 0, "Disabled service announced a cached update");
        PreserveSentinels(); Add("actual-service-change-callback-cannot-announce-cached-update");
        var vmType = assembly.GetType("HD2ModManager.ViewModels.AppUpdateSectionViewModel", true)!;
        var vm = Activator.CreateInstance(vmType, service)!;
        Check(Value<string>(vm, "CurrentVersionText") == "骨架修复1.01", "Wrong actual version label"); Add("real-viewmodel-skeleton-version-label");
        foreach (var flag in new[] { "UpdatesEnabled", "AutoCheck", "AutoUpdate", "CanCheck", "CanDownload", "CanInstallNow", "HasRelease", "ShowDownloadButton", "IsDownloading", "IsReady" })
            Check(!Value<bool>(vm, flag), "Disabled build exposes active update state: " + flag);
        Add("all-update-actions-and-auto-switches-inactive-even-with-cached-release");
        foreach (var commandName in new[] { "CheckCommand", "DownloadCommand", "CancelCommand", "InstallCommand", "ToggleSkipCommand", "OpenReleasePageCommand" })
        {
            var command = Value<ICommand>(vm, commandName); Check(!command.CanExecute(null), "Update command enabled: " + commandName);
            // RelayCommand.Execute does not enforce CanExecute; handlers must themselves be safe.
            command.Execute(null); PreserveSentinels(); Check(app.Windows.Count == 0, "Disabled command opened a window");
            Add("disabled-command-cannot-execute-even-by-direct-invocation-" + commandName);
        }
        foreach (var (name, value) in new (string, object)[] { ("AutoCheck", false), ("AutoCheck", true), ("AutoUpdate", false), ("AutoUpdate", true), ("DownloadSourceChoice", 2), ("MirrorId", "unused"), ("CustomMirror", "https://different.example.com/") })
        {
            vmType.GetProperty(name)!.SetValue(vm, value); PreserveSentinels(); Check(Field(updater, "_timer") is null, "Preference setter scheduled auto-check");
            Add("hidden-preference-setter-preserves-file-" + name + "-" + value);
        }
        var manual = (Task)Invoke(updater.GetType().GetMethod("CheckAsync")!, updater, true, null)!;
        Check(manual.IsCompletedSuccessfully && Field(updater, "_checking") is null, "Disposed updater accepted a manual network check"); PreserveSentinels(); Add("stopped-updater-refuses-manual-network-check");
        Invoke(vmType.GetMethod("OnServiceChanged", BindingFlags.Instance | BindingFlags.NonPublic)!, vm);
        Check(app.Windows.Count == 0, "Cached update event opened a mirror dialog"); Add("cached-change-event-cannot-offer-mirror-or-dialog");

        var settingsType = assembly.GetType("HD2ModManager.Views.SettingsPageView", true)!;
        var cardType = assembly.GetType("HD2ModManager.Views.AppUpdateCard", true)!;
        var settings = (FrameworkElement)Activator.CreateInstance(settingsType)!;
        var card = (UserControl)Descendants(settings).Single(d => d.GetType() == cardType);
        Check(BindingOperations.GetBinding(card, FrameworkElement.DataContextProperty)?.Path.Path == "AppUpdate", "Settings page lost update-card viewmodel binding"); Add("actual-settings-page-contains-version-card-with-original-binding");
        var parent = (Panel)LogicalTreeHelper.GetParent(card)!; parent.Children.Remove(card); card.DataContext = vm;
        var controls = (StackPanel)card.FindName("AppUpdateControls"); var label = (TextBlock)card.FindName("CurrentVersionTextBlock");
        Check(BindingOperations.GetBinding(controls, UIElement.VisibilityProperty)?.Path.Path == "UpdatesEnabled", "Controls are not policy-bound"); Add("compiled-update-controls-visibility-bound-to-shared-policy");
        var surface = new Border { Background = Brushes.White, Padding = new Thickness(16), Child = card };
        foreach (var width in new[] { 780d, 500d, 320d })
        {
            Render(surface, width, Path.Combine(output, "settings-version-" + (int)width + ".png"));
            Check(controls.Visibility == Visibility.Collapsed && !controls.IsEnabled && controls.ActualHeight == 0, "Update region visible or occupying layout space");
            Check(label.Text == "骨架修复1.01" && label.ActualWidth > 0, "Compiled version label is not visible/bound");
            Check(Descendants(controls).OfType<Button>().All(b => !b.IsEnabled), "Hidden update button remains enabled");
            Add("actual-settings-version-render-and-all-update-controls-collapsed-width-" + width);
        }
        Check(Descendants(controls).OfType<Button>().Count() == 6 && Descendants(controls).OfType<CheckBox>().Count() == 2, "Did not cover all original update buttons/auto toggles"); Add("all-six-update-buttons-and-both-auto-toggles-hidden");
        var homeType = assembly.GetType("HD2ModManager.Views.HomePageView", true)!;
        var home = (FrameworkElement)Activator.CreateInstance(homeType)!;
        var homeTitle = (TextBlock)home.FindName("RepairTitleText");
        var homeNotes = (TextBlock)home.FindName("RepairNotesText");
        const string expectedHomeNotes = "1.01修复：\n"
            + "1.走路动画跳变\n"
            + "2.多人物理失效情况，舰船默认全开启物理效果（不代表战斗时的帧数），战斗切换第一人称自动启动物理效果（警告，目前会有10%性能损失。裙子的物理效果战斗性能消耗比舰船高）\n"
            + "3.全护甲兼容chef加载器映射（暂不测试其他加载器兼容，12月还会炸一次）\n"
            + "4.当前最新物理包为A2.3.21，后续可能还有新的版本";
        Check(homeTitle.Text == "骨架测试版本管理器：1.01" && homeNotes.Text == expectedHomeNotes,
            "Home-page repair title/notes differ from the requested exact text");
        Check(homeNotes.TextWrapping == TextWrapping.Wrap, "Long performance warning is not wrapped");
        var homeTexts = Descendants(home).OfType<TextBlock>().ToArray();
        var firstUse = Array.FindIndex(homeTexts, t => t.Text == "第一次使用？");
        Check(Array.IndexOf(homeTexts, homeTitle) < Array.IndexOf(homeTexts, homeNotes)
            && Array.IndexOf(homeTexts, homeNotes) < firstUse, "Repair notes are not before first-use help");
        Add("actual-home-exact-repair-title-four-notes-wrapping-and-first-use-order");
        foreach (var width in new[] { 900d, 1200d })
        {
            home.Height = 900;
            Render(home, width, Path.Combine(output, "home-repair-" + (int)width + ".png"));
            Check(homeTitle.ActualHeight > 0 && homeNotes.ActualHeight > 0, "Repair content is hidden");
            Check(homeNotes.ActualWidth <= home.ActualWidth && homeNotes.ActualHeight >= 5 * 21,
                "Repair notes are clipped or not laying out all five lines");
            Add("actual-home-repair-layout-width-" + width);
        }
        PreserveSentinels(); Check(app.Windows.Count == 0, "Headless verification created a Window"); Add("headless-tests-no-native-window-or-startup-execution");
        Invoke(vmType.GetMethod("Dispose")!, vm); Invoke(serviceType.GetMethod("Dispose")!, service);
        Check(Field(updater, "_timer") is null && (bool)Field(updater, "_stopped")!, "Dispose reactivated updater");
        PreserveSentinels(); Add("repeated-dispose-preserves-preferences-cache-and-stopped-state");
        // Do not Run, invoke the Dispatcher, or pump a shutdown queue. Process exit tears down this resource-only Application.
        Check(app.MainWindow is null && app.Windows.Count == 0 && !Directory.Exists(Path.Combine(sandbox, "logs")), "Production startup ran in a headless fixture");
        PreserveSentinels(); Add("no-production-startup-main-window-or-startup-log");
        var report = new { status = "PASS", candidate, count = results.Count, cases = results, noticeTitle, noticeText, version,
            verificationMode = "headless-actual-controls-and-il", startupDialogExecuted = false, updatesEnabled = false, networkRequestsStarted = false,
            previousAutoCheckAndAutoUpdatePreserved = true, nativeWindowCreated = false, gameDeployed = false, modelsOrAnimationsRegenerated = false };
        File.WriteAllText(Path.Combine(output, "skeleton-test-ui-smoke.json"), JsonSerializer.Serialize(report, JsonOptions));
        Console.WriteLine($"PASS skeleton-test UI: {results.Count} cases; actual GUI assembly/version/card; no network/native window/game writes");
    }

    [STAThread] static int Main(string[] args)
    {
        try
        {
            if (args[0] == "audit") Audit(Path.GetFullPath(args[1]), Path.GetFullPath(args[2]), Path.GetFullPath(args[3]));
            else if (args[0] == "headless") Verify(Path.GetFullPath(args[1]), Path.GetFullPath(args[2]));
            else throw new ArgumentException("Use audit <before> <after> <report.json> or headless <candidate> <output>");
            return 0;
        }
        catch (Exception error) { Console.Error.WriteLine(error); return 1; }
    }
}

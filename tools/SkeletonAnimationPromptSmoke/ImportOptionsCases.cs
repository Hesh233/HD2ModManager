using System.IO;
using Expression = System.Linq.Expressions.Expression;
using System.Reflection;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using System.Windows.Data;
using System.Windows.Media;

internal static partial class Program
{
    static Delegate AdaptCallback(Type delegateType, Func<object?[], object?> callback)
    {
        var invoke = delegateType.GetMethod("Invoke")!;
        var parameters = invoke.GetParameters().Select(p => Expression.Parameter(p.ParameterType, p.Name)).ToArray();
        var boxed = Expression.NewArrayInit(typeof(object), parameters.Select(p => Expression.Convert(p, typeof(object))));
        var call = Expression.Invoke(Expression.Constant(callback), boxed);
        return Expression.Lambda(delegateType, Expression.Convert(call, invoke.ReturnType), parameters).Compile();
    }
    static object Completed(Type taskType, object? value)
        => typeof(Task).GetMethod("FromResult")!.MakeGenericMethod(taskType.GetGenericArguments().Single()).Invoke(null, [value])!;
    static void Layout(FrameworkElement element, double width)
    {
        element.Measure(new Size(width, double.PositiveInfinity));
        element.Arrange(new Rect(new Point(), new Size(width, element.DesiredSize.Height)));
        element.UpdateLayout();
    }
    static void SavePreview(FrameworkElement child, string path, double width)
    {
        var surface = new Border { Background = Brushes.White, Child = child };
        Layout(surface, width); SavePanel(surface, path); surface.Child = null;
    }
    static void AssertOriginal(object? result, double scale)
    {
        Check(result is not null, "Original decision was null");
        foreach (var name in new[] { "UseNativeSkeleton", "SingleHd2Skeleton", "GenerateAnimation", "BuildsSkeletonPackage" }) Check(!Value<bool>(result!, name), "Original route enabled " + name);
        Check(Value<double>(result!, "ModelScale") == scale, "Original model scale changed");
    }
    static void VerifyImportOptions(Assembly assembly, Application app, string output, Action<string, object?> add)
    {
        var service = assembly.GetType("HD2ModManager.Services.SettingsService", true)!;
        var get = service.GetMethod("GetEnableDualSkeletonAnimationVersion")!;
        var set = service.GetMethod("SetEnableDualSkeletonAnimationVersion")!;
        var flush = service.GetMethod("FlushAsync")!;
        var cache = service.GetField("_cachedSettings", BindingFlags.NonPublic | BindingFlags.Static)!;
        void Flush() => ((Task)Invoke(flush, null)!).GetAwaiter().GetResult();
        void Set(bool value) { Check((bool)Invoke(set, null, value)!, "Dual setting write failed"); Flush(); }
        Check(!(bool)Invoke(get, null)!, "Missing dual version flag must default off"); add("dual-missing-field-default-off", null);
        Set(true); cache.SetValue(null, null); Check((bool)Invoke(get, null)!, "Dual on failed to persist"); Set(false); cache.SetValue(null, null); Check(!(bool)Invoke(get, null)!, "Dual off failed to persist"); add("dual-on-off-setting-reload", null);

        var choice = assembly.GetType("HD2ModManager.Services.VpkChoicePrompt", true)!;
        var panelMethod = choice.GetMethod("BuildImportRoutesPanel", BindingFlags.NonPublic | BindingFlags.Static)!;
        foreach (var enabled in new[] { false, true })
        {
            var panel = (StackPanel)Invoke(panelMethod, null, "smoke-model", enabled, null)!;
            var buttons = Descendants<Button>(panel).ToArray();
            Check(buttons.Any(b => b.Name == "DualSkeletonImport") == enabled, "Actual route panel exposed hidden dual version");
            Check(buttons.Any(b => b.Name == "SingleSkeletonImport") && buttons.Any(b => b.Name == "OriginalFormatImport") && buttons.Any(b => b.Name == "CancelVpkImport"), "Route panel lost single/original/cancel");
            Check(buttons.Single(b => b.IsDefault).Name == (enabled ? "DualSkeletonImport" : "SingleSkeletonImport"), "Enter default can select hidden dual version");
            Check(Descendants<TextBlock>(panel).Any(t => t.Text.Contains("双骨架 + Lua", StringComparison.Ordinal)) == enabled, "Dual explanatory choice remains visible while disabled");
            SavePreview(panel, Path.Combine(output, enabled ? "routes-dual-enabled.png" : "routes-dual-hidden.png"), 580);
            add(enabled ? "actual-panel-dual-visible-opt-in" : "actual-panel-dual-hidden-single-default", null);
        }

        var policy = assembly.GetType("HD2ModManager.Services.VpkModelScalePolicy", true)!;
        var warning = policy.GetMethod("RequiresWarning", BindingFlags.NonPublic | BindingFlags.Static)!;
        foreach (var value in new[] { 0.1, 0.899, 0.9, 1.0, 1.1, 1.101, 1.4, 10.0 })
        {
            Check((bool)Invoke(warning, null, value, true)! == (value < 0.9 || value > 1.1), "Wrong recommended-range warning");
            Check(!(bool)Invoke(warning, null, value, false)!, "Original format got skeleton-only warning");
            add("scale-warning-boundary-" + value.ToString(System.Globalization.CultureInfo.InvariantCulture), null);
        }
        var scaleType = assembly.GetType("HD2ModManager.Services.ModelScalePrompt", true)!;
        var scalePanel = scaleType.GetMethod("BuildScalePanel", BindingFlags.NonPublic | BindingFlags.Static)!;
        foreach (var value in new[] { "0.8", "1.2" })
        {
            double? accepted = null; var confirmations = 0; var permit = false;
            var panel = (StackPanel)Invoke(scalePanel, null, "smoke-model", true,
                new Action<double>(v => accepted = v), new Func<double, bool>(_ => { confirmations++; return permit; }))!;
            var input = Descendants<TextBox>(panel).Single(); input.Text = value;
            var accept = Descendants<Button>(panel).Single(b => b.Name == "ConfirmModelScale");
            Click(accept); Check(accepted is null && confirmations == 1 && input.Text == value, "Warning No must stay in scale input without committing");
            Check(Descendants<TextBlock>(panel).Any(t => t.Text.Contains("已返回倍率输入", StringComparison.Ordinal)), "Warning No lost return-to-parent guidance");
            SavePreview(panel, Path.Combine(output, "scale-warning-no-" + value + ".png"), 400);
            permit = true; Click(accept); Check(accepted == double.Parse(value, System.Globalization.CultureInfo.InvariantCulture) && confirmations == 2, "Warning Yes clamped or replaced the entered value");
            add("scale-warning-no-back-yes-exact-" + value, null);
        }
        foreach (var text in new[] { "0.9", "1", "1.1" })
        {
            double? accepted = null; var warnings = 0;
            var panel = (StackPanel)Invoke(scalePanel, null, "smoke-model", true, new Action<double>(v => accepted = v), new Func<double, bool>(_ => { warnings++; return false; }))!;
            Descendants<TextBox>(panel).Single().Text = text; Click(Descendants<Button>(panel).Single(b => b.Name == "ConfirmModelScale"));
            Check(accepted == double.Parse(text, System.Globalization.CultureInfo.InvariantCulture) && warnings == 0, "Recommended boundary should not warn"); add("scale-in-range-no-warning-" + text, null);
        }
        foreach (var text in new[] { "0", "-1", "11", "NaN", "Infinity", "" })
        {
            double? accepted = null; var warnings = 0;
            var panel = (StackPanel)Invoke(scalePanel, null, "smoke-model", true, new Action<double>(v => accepted = v), new Func<double, bool>(_ => { warnings++; return true; }))!;
            Descendants<TextBox>(panel).Single().Text = text; Click(Descendants<Button>(panel).Single(b => b.Name == "ConfirmModelScale"));
            Check(accepted is null && warnings == 0, "Invalid scale bypassed hard validation"); add("scale-invalid-rejected-" + (text.Length == 0 ? "empty" : text), null);
        }
        {
            double? accepted = null;
            var panel = (StackPanel)Invoke(scalePanel, null, "smoke-model", false, new Action<double>(v => accepted = v), new Func<double, bool>(_ => throw new Exception("Original scale must not show skeleton warning")))!;
            Descendants<TextBox>(panel).Single().Text = "1.4"; Click(Descendants<Button>(panel).Single(b => b.Name == "ConfirmModelScale")); Check(accepted == 1.4, "Original scale changed"); add("original-scale-no-new-warning", null);
        }

        var controller = assembly.GetType("HD2ModManager.Services.VpkModelDecisionPrompt", true)!;
        var collect = controller.GetMethod("CollectAsync", BindingFlags.NonPublic | BindingFlags.Static)!;
        var steps = assembly.GetType("HD2ModManager.Services.VpkModelDecisionPromptSteps", true)!;
        var constructor = steps.GetConstructors().Single(); var delegates = constructor.GetParameters();
        var routeType = assembly.GetType("HD2ModManager.Services.VpkImportRoute", true)!;
        var optionType = assembly.GetType("HD2ModManager.ViewModels.VpkTargetArmorOption", true)!;
        var optionKind = assembly.GetType("HD2ModManager.ViewModels.VpkTargetArmorKind", true)!;
        var target = Activator.CreateInstance(optionType, ["smoke-target-not-applied", "smoke armor", Enum.Parse(optionKind, "GameArmor")])!;
        object? Run(string test, string route, string? cancelAt = null, bool ask = true, bool allowDual = false, bool runtime = true, bool skipArmor = false, string? tokenAt = null, bool expectError = false)
        {
            var events = new List<string>(); using var ct = new CancellationTokenSource();
            Delegate Make(int index, string name, object? value) => AdaptCallback(delegates[index].ParameterType, args =>
            {
                var actualName = index == 1 ? ((bool)args[1]! ? "skeleton-scale" : "original-scale") : name; events.Add(actualName);
                if (tokenAt == name) ct.Cancel();
                var ret = delegates[index].ParameterType.GetMethod("Invoke")!.ReturnType;
                return index == 4 ? runtime : Completed(ret, cancelAt == name ? null : value);
            });
            var stepObject = constructor.Invoke([Make(0, "route", Enum.Parse(routeType, route)), Make(1, "scale", 1.2), Make(2, "armor", skipArmor ? null : target), Make(3, "threads", 3), Make(4, "runtime", runtime)]);
            var task = (Task)Invoke(collect, null, "smoke-model", ask, allowDual, stepObject, ct.Token)!; Check(task.IsCompleted, "Injected step sequence unexpectedly waited for native UI");
            object? result = null; var rejected = false;
            try { task.GetAwaiter().GetResult(); result = task.GetType().GetProperty("Result")!.GetValue(task); }
            catch (Exception error) when (expectError && (error is InvalidOperationException || error is OperationCanceledException)) { rejected = true; }
            Check(rejected == expectError, "Expected pipeline guard did not reject");
            if (!expectError)
            {
                if (!ask) { AssertOriginal(result, 1); Check(events.Count == 0, "Ask off executed prompt steps"); }
                else if (cancelAt is not null) Check(result is null, "Canceled step committed a model decision");
                else if (route == "OriginalFormat") { AssertOriginal(result, 1.2); Check(events.SequenceEqual(new[] { "route", "original-scale" }), "Original asked for skeleton/armor steps"); }
                else
                {
                    Check(events.SequenceEqual(new[] { "route", "runtime", "skeleton-scale", "armor", "threads" }), "Armor was not asked immediately after scale and before threads/packing");
                    Check(result is not null && Value<double>(result, "ModelScale") == 1.2 && Value<int>(result, "AnimationThreads") == 3, "Decision parameters were altered");
                    Check(ReferenceEquals(result!.GetType().GetProperty("TargetArmor")!.GetValue(result), skipArmor ? null : target), "Preselected armor was not carried into model decision");
                }
            }
            if (cancelAt == "scale" || tokenAt == "scale") Check(!events.Contains("armor") && !events.Contains("threads"), "Canceled scale progressed to armor/threads");
            if (tokenAt == "armor") Check(!events.Contains("threads"), "Canceled armor step progressed to threads");
            if (route == "DualSkeletonWithLua" && !allowDual && ask) Check(events.SequenceEqual(new[] { "route" }), "Hidden dual route reached build work");
            add(test, new { events, result = result?.ToString() }); return result;
        }
        Run("flow-ask-off-no-prompts-even-dual-enabled", "DualSkeletonWithLua", ask: false, allowDual: true);
        Run("flow-single-scale-armor-threads-before-packing", "SingleSkeleton");
        Run("flow-dual-opt-in-scale-armor-threads-before-packing", "DualSkeletonWithLua", allowDual: true);
        Run("flow-original-no-armor-or-animation", "OriginalFormat");
        Run("flow-hidden-dual-rejected-before-runtime-or-pack", "DualSkeletonWithLua", expectError: true);
        Run("flow-skip-armor-still-builds-skeleton", "SingleSkeleton", skipArmor: true);
        Run("flow-route-cancel-no-downstream", "SingleSkeleton", cancelAt: "route");
        Run("flow-scale-cancel-no-armor-or-pack", "SingleSkeleton", cancelAt: "scale");
        Run("flow-thread-cancel-no-decision-or-pack", "SingleSkeleton", cancelAt: "threads");
        Run("flow-missing-runtime-before-scale", "SingleSkeleton", runtime: false, expectError: true);
        Run("flow-token-cancel-at-scale-no-armor", "SingleSkeleton", tokenAt: "scale", expectError: true);
        Run("flow-token-cancel-at-armor-no-thread-or-pack", "SingleSkeleton", tokenAt: "armor", expectError: true);

        var importer = assembly.GetType("HD2ModManager.Services.ImportService", true)!;
        Check(importer.GetMethod("PromptAndApplyTargetArmorAsync", BindingFlags.NonPublic | BindingFlags.Instance) is null, "Late armor prompt still exists");
        var applyState = importer.GetNestedTypes(BindingFlags.NonPublic).Single(t => t.Name.StartsWith("<ApplyTargetArmorAsync>", StringComparison.Ordinal));
        var applyBody = Body(applyState.GetMethod("MoveNext", BindingFlags.NonPublic | BindingFlags.Instance)!);
        Check(!applyBody.Contains("VpkTargetArmorPrompt", StringComparison.Ordinal) && !applyBody.Contains("ShowAsync", StringComparison.Ordinal), "Post-conversion armor apply can prompt again");
        var conversion = assembly.GetType("HD2ModManager.Services.VpkImportService", true)!;
        var conversionBody = string.Join("\n", conversion.GetNestedTypes(BindingFlags.NonPublic).SelectMany(t => t.GetMethods(BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public | BindingFlags.DeclaredOnly)).Select(Body));
        Check(conversionBody.Split("set_TargetArmor", StringSplitOptions.None).Length >= 3, "Both new/update packages must carry armor selection");
        add("preselected-armor-new-update-handoff-no-post-conversion-prompt", null);

        var vmType = assembly.GetType("HD2ModManager.ViewModels.SettingsPageViewModel", true)!;
        var vm = System.Runtime.CompilerServices.RuntimeHelpers.GetUninitializedObject(vmType);
        var view = (UserControl)Activator.CreateInstance(assembly.GetType("HD2ModManager.Views.SettingsPageView", true)!)!;
        var askToggle = (CheckBox)view.FindName("AskToInstallSkeletonAnimationToggle");
        var dualToggle = (CheckBox)view.FindName("EnableDualSkeletonAnimationVersionToggle");
        Check(dualToggle is not null && BindingOperations.GetBinding(dualToggle, ToggleButton.IsCheckedProperty)?.Path.Path == "EnableDualSkeletonAnimationVersion", "Missing real dual toggle binding");
        var parent = (StackPanel)askToggle.Parent; Check(parent.Children.IndexOf(dualToggle) > parent.Children.IndexOf(askToggle), "Dual flag must be below skeleton prompt setting");
        Check(((TextBlock)dualToggle!.Content).Text == "是否双骨架动画版本，当前挂点修正的性能未优化，用户别开", "Dual setting warning text differs from user request");
        var card = (Border)parent.Parent; ((Panel)card.Parent).Children.Remove(card); card.DataContext = vm;
        var surface = new Border { Child = card, Background = Brushes.White, Padding = new Thickness(16) };
        Layout(surface, 780); Check(dualToggle.IsChecked == false, "Actual dual toggle must show default off"); SavePanel(surface, Path.Combine(output, "settings-import-options-default.png"));
        dualToggle.SetCurrentValue(ToggleButton.IsCheckedProperty, true); Flush(); Check((bool)Invoke(get, null)!, "Dual UI binding did not save on");
        SavePanel(surface, Path.Combine(output, "settings-import-options-dual-on.png")); dualToggle.SetCurrentValue(ToggleButton.IsCheckedProperty, false); Flush();
        Layout(surface, 500); SavePanel(surface, Path.Combine(output, "settings-import-options-narrow.png"));
        Check(!(bool)Invoke(get, null)! && app.Windows.Count == 0, "Dual UI roundtrip changed windowless/off state"); add("real-dual-setting-position-caption-two-way-narrow-layout", null);
    }
}

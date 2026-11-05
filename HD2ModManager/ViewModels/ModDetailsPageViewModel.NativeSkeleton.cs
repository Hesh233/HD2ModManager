using System.IO;
using HD2ModManager.Models;
using HD2ModManager.Services;

namespace HD2ModManager.ViewModels;

public partial class ModDetailsPageViewModel
{
    private RelayCommand? _nativeSkeletonCommand;
    public RelayCommand NativeSkeletonCommand => _nativeSkeletonCommand ??= new(_ => _ = BuildNativeSkeletonAsync());

    private async Task BuildNativeSkeletonAsync()
    {
        if (_vpkBusy) { VpkComponentStatus = "上一个操作还在跑，请等它结束。"; return; }
        if (!TryGetCurrentNode(out var node)) return;
        _vpkBusy = true;
        var task = _backgroundTasks?.Enqueue(BackgroundTaskKind.RebuildVpk, "原生骨架转换",
            node.Metadata.Name, origin: "Mod 详情", userVisibleReason: "保留 L4D2 骨架并批量制作配套动画工程。",
            suggestedAction: "完成后打开工程，按人工测试说明启用模型与配套动画。",
            retry: () => BuildNativeSkeletonAsync(), presentation: BackgroundTaskPresentation.Foreground);
        task?.MarkRunning("正在读取 config.toml");
        try
        {
            var progress = new Progress<string>(text => { if (task is not null) task.UpdateStage(text); else VpkComponentStatus = text; });
            var project = await NativeSkeletonProjectService.BuildAsync(
                Path.Combine(_library.ModsRootDirectory, node.RelativePath), SelectedVpkTargetArmor?.ArchiveId,
                text => ((IProgress<string>)progress).Report(text), task?.CancellationToken ?? CancellationToken.None);
            task?.SetOutputArtifacts(project, Path.Combine(project, "人工测试说明.txt"));
            task?.MarkCompleted();
            VpkComponentStatus = "原生骨架工程已生成：" + project;
        }
        catch (Exception error)
        {
            if (task?.CancellationToken.IsCancellationRequested == true) task.MarkCanceled();
            else task?.MarkFailed(error.Message);
            VpkComponentStatus = "原生骨架转换未完成：" + error.Message;
        }
        finally { _vpkBusy = false; }
    }
}

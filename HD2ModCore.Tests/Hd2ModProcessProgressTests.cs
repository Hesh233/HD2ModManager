using System.Collections.Concurrent;
using System.Text.Json;
using HD2ModManager.Services;

namespace HD2ModCore.Tests;

public sealed class Hd2ModProcessProgressTests
{
    private static string? Runner()
    {
        var path=Environment.GetEnvironmentVariable("HD2_PROGRESS_TEST_PYTHON");
        return path is not null && File.Exists(path) ? path : null;
    }

    private const string Producer = "import sys,time,json\nfrom pathlib import Path\n" +
        "sys.path.insert(0,str(Path(sys.executable).resolve().parents[2]))\n" +
        "from anim_batch_mod.single_skeleton import _progress\n";

    [Fact]
    public async Task ReceivesLiveSingleAnimationProgressBeforeChildExit()
    {
        var runner=Runner();if(runner is null)return;
        var first=new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var events=new ConcurrentQueue<(string Phase,int Done,int Total,string Text)>();
        var code=Producer+
            "_progress('prepare',0,0,'正在校验单骨架动画')\ntime.sleep(.4)\n"+
            "_progress('animation',1,2,'单骨架动画 1/2')\ntime.sleep(.4)\n"+
            "_progress('animation',2,2,'单骨架动画 2/2')\n"+
            "_progress('complete',1,1,'打包完成')\n"+
            "print('diagnostic',file=sys.stderr,flush=True)\nprint(json.dumps({'status':'complete'}),flush=True)";
        var task=Hd2ModProcess.RunAsync(runner,["-B","-X","utf8","-c",code],onProgress:(phase,done,total,text)=>
        { events.Enqueue((phase,done,total,text));first.TrySetResult(); });
        await first.Task.WaitAsync(TimeSpan.FromSeconds(10));
        Assert.False(task.IsCompleted); // A ReadToEnd-only reader would report everything after exit.
        var result=await task;
        Assert.Equal(0,result.ExitCode);
        Assert.Equal("complete",JsonDocument.Parse(result.Output).RootElement.GetProperty("status").GetString());
        Assert.DoesNotContain("#progress",result.Output);Assert.DoesNotContain("#progress",result.Error);
        Assert.Equal("diagnostic",result.Error.Trim());
        Assert.Equal(new[]{"prepare","animation","animation","complete"},events.Select(e=>e.Phase));
        Assert.Contains(events,e=>e.Done==1&&e.Total==2&&e.Text=="单骨架动画 1/2");
    }

    [Fact]
    public async Task FailureKeepsRealErrorAndDoesNotMasqueradeAsCompletion()
    {
        var runner=Runner();if(runner is null)return;
        var events=new ConcurrentQueue<string>();
        var code=Producer+"_progress('animation',1,2,'单骨架动画 1/2')\n"+
            "print('build failed',file=sys.stderr,flush=True)\nsys.exit(3)";
        var result=await Hd2ModProcess.RunAsync(runner,["-B","-X","utf8","-c",code],onProgress:(p,d,t,s)=>events.Enqueue(p));
        Assert.Equal(3,result.ExitCode);Assert.Equal("build failed",result.Error.Trim());
        Assert.DoesNotContain("complete",events);Assert.DoesNotContain("#progress",result.Error);
    }

    [Fact]
    public async Task CancellationStopsTheProgressProducingChild()
    {
        var runner=Runner();if(runner is null)return;
        using var cancellation=new CancellationTokenSource();
        var first=new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var code=Producer+"_progress('animation',0,2,'单骨架动画 0/2')\ntime.sleep(30)";
        var task=Hd2ModProcess.RunAsync(runner,["-B","-X","utf8","-c",code],cancellation.Token,
            (p,d,t,s)=>first.TrySetResult());
        await first.Task.WaitAsync(TimeSpan.FromSeconds(10));cancellation.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(async()=>await task);
    }
}

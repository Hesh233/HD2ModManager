using System.Reflection;
using System.Runtime.Loader;
using System.Text.Json;
using HD2ModAdaptation.PatchReconstruction;
using HD2ModAdaptation.PatchReconstruction.UnitMesh;

try
{
if(args[0]=="--audit-single-model")
{
    await SingleHd2ModelAudit.RunAsync(args);return;
}
if(args[0]=="--rekey-existing-vpk")
{
    await VpkRekeyRecovery.RunAsync(args);return;
}
if(args[0]=="--verify-vpk-reimport")
{
    await VpkImportSimulation.VerifyReimportAsync(args);return;
}
if(args[0]=="--simulate-vpk-import-target")
{
    var target = args[5];
    var forwarded = args.Take(5).Concat(args.Skip(6)).ToArray();
    await VpkImportSimulation.RunAsync(forwarded, targetArchive:target);return;
}
if(args[0]=="--simulate-vpk-import-single")
{
    await VpkImportSimulation.RunAsync(args, single:true);return;
}
if(args[0]=="--simulate-vpk-import")
{
    await VpkImportSimulation.RunAsync(args);return;
}
if(args[0]=="--simulate-vpk")
{
    var published=Path.GetFullPath(args[1]);var output=Path.GetFullPath(args[2]);
    var vpk=Path.GetFullPath(args[3]);var gameData=Path.GetFullPath(args[4]);
    var sampleCount=int.Parse(args[5]);var modelScale=double.Parse(args[6],System.Globalization.CultureInfo.InvariantCulture);
    if(Directory.Exists(output))throw new IOException("Use a new simulation output directory");
    Directory.CreateDirectory(output);
    Directory.CreateDirectory(Path.Combine(output,"isolated-manager"));
    Directory.CreateDirectory(Path.Combine(output,"isolated-library"));
    var indexSource=Path.Combine(published,"data","indexes","asset-index.sqlite");
    var indexTarget=Path.Combine(output,"isolated-manager","data","indexes","asset-index.sqlite");
    Directory.CreateDirectory(Path.GetDirectoryName(indexTarget)!);
    File.Copy(indexSource,indexTarget);
    var inputHash=Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(File.ReadAllBytes(vpk)));
    var list=Path.Combine(output,"sources.txt");File.WriteAllText(list,vpk,new System.Text.UTF8Encoding(false));
    var psi=new System.Diagnostics.ProcessStartInfo(Path.Combine(published,"hd2mod.exe"))
    {RedirectStandardOutput=true,RedirectStandardError=true,UseShellExecute=false,CreateNoWindow=true};
    foreach(var arg in new[]{"vpk2patch","--vpk-list",list,"--material-source-list",list,"--output",Path.Combine(output,"models"),
        "--manager-root",Path.Combine(output,"isolated-manager"),"--library",Path.Combine(output,"isolated-library"),
        "--game-data",gameData,"--source-skeleton","--model-scale",modelScale.ToString("R",System.Globalization.CultureInfo.InvariantCulture),"--json"})psi.ArgumentList.Add(arg);
    using(var process=System.Diagnostics.Process.Start(psi)!)
    {
        var stdout=process.StandardOutput.ReadToEndAsync();var stderr=process.StandardError.ReadToEndAsync();
        await process.WaitForExitAsync();File.WriteAllText(Path.Combine(output,"conversion.log"),await stdout+await stderr);
        if(process.ExitCode!=0)throw new InvalidDataException("Published VPK conversion failed; see conversion.log");
    }
    var manifest=Directory.GetFiles(Path.Combine(output,"models"),"source-skeleton.json",SearchOption.AllDirectories).Single();
    var model=Path.GetDirectoryName(manifest)!;
    AppContext.SetData("APP_CONTEXT_BASE_DIRECTORY",published);
    AssemblyLoadContext.Default.Resolving+=(_,name)=>
    {
        var path=Path.Combine(published,name.Name+".dll");return File.Exists(path)?AssemblyLoadContext.Default.LoadFromAssemblyPath(path):null;
    };
    var assembly=AssemblyLoadContext.Default.LoadFromAssemblyPath(Path.Combine(published,"HD2ModManager.dll"));
    var service=assembly.GetType("HD2ModManager.Services.VpkAnimationBuildService",true)!;
    // This legacy CLI-only simulation has no VpkImportService staging boundary.
    await (Task)service.GetMethod("PrepareStagedNativeModelAsync",BindingFlags.NonPublic|BindingFlags.Static)!
        .Invoke(null,[model,CancellationToken.None,null])!;
    var lua=(Task<string>)service.GetMethod("BuildAttachmentFixAsync",BindingFlags.NonPublic|BindingFlags.Static)!
        .Invoke(null,[model,Path.Combine(output,"attachment"),CancellationToken.None,null])!;
    var luaDirectory=await lua;
    var animationMethod=service.GetMethod("BuildAsync",BindingFlags.NonPublic|BindingFlags.Static)!;
    object?[] animationArguments=[model,Path.Combine(output,"animations"),null,CancellationToken.None,(int?)sampleCount];
    if(animationMethod.GetParameters().Length==6) animationArguments=[..animationArguments,2];
    var animation=(Task<string>)animationMethod.Invoke(null,animationArguments)!;
    var runtime=await animation;
    var package=Path.Combine(output,"animation-package");Directory.CreateDirectory(package);
    foreach(var file in Directory.EnumerateFiles(runtime))File.Copy(file,Path.Combine(package,Path.GetFileName(file)));
    service.GetMethod("WriteAnimationIdentity",BindingFlags.NonPublic|BindingFlags.Static)!.Invoke(null,[package,Path.GetFileNameWithoutExtension(vpk)]);
    var sameHash=Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(File.ReadAllBytes(vpk)));
    if(sameHash!=inputHash)throw new InvalidDataException("Original VPK modified");
    using var report=JsonDocument.Parse(File.ReadAllText(Path.Combine(output,"animations","build-report.json")));
    using var naming=JsonDocument.Parse(File.ReadAllText(Path.Combine(package,"manifest.json")));
    if(report.RootElement.GetProperty("animations").GetArrayLength()!=sampleCount)throw new InvalidDataException("Wrong diagnostic clip count");
    if(naming.RootElement.GetProperty("Description").GetString()!="[全量动作文件]")throw new InvalidDataException("Wrong animation description");
    File.WriteAllText(Path.Combine(output,"simulation.json"),JsonSerializer.Serialize(new {status="PASS",vpk,model,modelScale,
        animationRuntime=runtime,luaDirectory,animationName=naming.RootElement.GetProperty("Name").GetString(),
        description="[全量动作文件]",sampleCount,sourceVpkUnmodified=true,guiPublishedServiceInvoked=true,gameDeployed=false,gameTested=false},new JsonSerializerOptions{WriteIndented=true}));
    Console.WriteLine("SIMULATION PASS: "+output);return;
}
if(args[0]=="--attachment")
{
    var published=Path.GetFullPath(args[1]);
    var output=Path.GetFullPath(args[2]);
    if(Directory.Exists(output))throw new IOException("Choose a new output directory.");
    AppContext.SetData("APP_CONTEXT_BASE_DIRECTORY",published);
    AssemblyLoadContext.Default.Resolving+=(_,name)=>
    {
        var path=Path.Combine(published,name.Name+".dll");
        return File.Exists(path)?AssemblyLoadContext.Default.LoadFromAssemblyPath(path):null;
    };
    var assembly=AssemblyLoadContext.Default.LoadFromAssemblyPath(Path.Combine(published,"HD2ModManager.dll"));
    var service=assembly.GetType("HD2ModManager.Services.VpkAnimationBuildService",throwOnError:true)!;
    var build=service.GetMethod("BuildAttachmentFixAsync",BindingFlags.NonPublic|BindingFlags.Static)!;
    var work=(Task<string>)build.Invoke(null,[Path.GetFullPath(args[3]),output,CancellationToken.None,Path.GetFullPath(args[4])])!;
    Console.WriteLine(await work);return;
}
if(args[0]=="--compare-model")
{
    var oldEntries=await new PatchTocScanner().ScanEntriesAsync(args[1]);
    var newEntries=await new PatchTocScanner().ScanEntriesAsync(args[2]);
    var ratio=double.Parse(args[3],System.Globalization.CultureInfo.InvariantCulture);
    var dz=double.Parse(args[4],System.Globalization.CultureInfo.InvariantCulture);
    double maxError=0;var compared=0;
    foreach(var entry in newEntries)
    {
        var oldEntry=oldEntries.Single(e=>e.AssetKey==entry.AssetKey);
        var a=await new PatchEntryPayloadReader().ReadPayloadAsync(oldEntry);
        var b=await new PatchEntryPayloadReader().ReadPayloadAsync(entry);
        var oldModel=new UnitMeshReader().Read(a.TocData,a.GpuResourceData);
        var newModel=new UnitMeshReader().Read(b.TocData,b.GpuResourceData);
        if(oldModel.RawMeshData.Count!=newModel.RawMeshData.Count)throw new InvalidDataException("Mesh count changed.");
        foreach(var mesh in newModel.RawMeshData)
        {
            var original=oldModel.RawMeshData.Single(m=>m.MeshInfoIndex==mesh.MeshInfoIndex);
            if(!mesh.Triangles.SequenceEqual(original.Triangles) || mesh.Vertices.Count!=original.Vertices.Count)
                throw new InvalidDataException("Topology changed during scale rollback.");
            var scale=UnitGeometryFactsBuilder.HasRenderableGeometry(mesh);
            for(var i=0;i<mesh.Vertices.Count;i++)
            {
                var x=original.Vertices[i];var y=mesh.Vertices[i];
                foreach(var c in y.Components)
                {
                    var d=x.Components.Single(t=>t.Type==c.Type&&t.Index==c.Index);
                    if(c.Type==0 && scale)
                    {
                        for(var j=0;j<3;j++)maxError=Math.Max(maxError,Math.Abs(c.FloatValues[j]-(d.FloatValues[j]*ratio+(j==2?dz:0))));
                        compared++;
                    }
                    else if(!c.RawData.SequenceEqual(d.RawData))throw new InvalidDataException($"Non-position component {c.Type} changed.");
                }
            }
        }
    }
    if(compared==0 || maxError>2e-6)throw new InvalidDataException($"Scale affine error {maxError}.");
    var json=JsonSerializer.Serialize(new {status="PASS",units=newEntries.Count,comparedVertices=compared,maxPositionError=maxError,
        topologyNormalsUvWeightsUnchanged=true,ratio,zTranslation=dz,gameTested=false},new JsonSerializerOptions{WriteIndented=true});
    File.WriteAllText(args[5],json);Console.WriteLine(json);return;
}
if (args[0] == "--model")
{
    var entries = await new PatchTocScanner().ScanEntriesAsync(args[1]);
    var points = new List<float[]>();
    var degenerateMeshes = 0;
    foreach (var entry in entries)
    {
        if (entry.AssetKey.TypeId != 0xe0a48d0be9a7453f) throw new InvalidDataException("Unexpected model resource type.");
        var payload = await new PatchEntryPayloadReader().ReadPayloadAsync(entry);
        var model = new UnitMeshReader().Read(payload.TocData, payload.GpuResourceData);
        foreach(var mesh in model.RawMeshData)
        {
            // CanonicalPlaceholderMinifier creates a 0.1 mm triangle at zero.
            // Use the production classifier so it cannot become the sole bound.
            if(!UnitGeometryFactsBuilder.HasRenderableGeometry(mesh))
            { degenerateMeshes++;continue; }
            points.AddRange(mesh.Vertices.Select(v=>v.Components.Single(c=>c.Type==0).FloatValues));
        }
    }
    if (entries.Count != 7 || points.Count == 0 || points.Any(p=>p.Length<3 || p.Any(v=>!float.IsFinite(v))))
        throw new InvalidDataException("Invalid serialized mesh.");
    var minZ=points.Min(p=>p[2]);
    var expectedMinZ=args.Length>3 ? double.Parse(args[3],System.Globalization.CultureInfo.InvariantCulture) : 0;
    if (Math.Abs(minZ-expectedMinZ)>1e-5)
    {
        Console.Error.WriteLine(JsonSerializer.Serialize(new {below=points.Where(p=>p[2]<expectedMinZ-1e-5).Take(10),lowest=points.Select(p=>p[2]).Distinct().Order().Take(10)}));
        throw new InvalidDataException($"Serialized floor is {minZ}; expected {expectedMinZ}.");
    }
    var report=JsonSerializer.Serialize(new {status="PASS",units=entries.Count,vertices=points.Count,degenerateMeshes,minZ,expectedMinZ,
        maxZ=points.Max(p=>p[2]),gameTested=false},new JsonSerializerOptions{WriteIndented=true});
    File.WriteAllText(args[2],report);Console.WriteLine(report);
    return;
}

// Export from the exact published assembly, without launching a manager window.
var manager = Path.GetFullPath(args[0]);
var destination = Path.GetFullPath(args[1]);
if (Directory.Exists(destination)) throw new IOException("Choose a new output directory.");
AssemblyLoadContext.Default.Resolving += (_, name) =>
{
    var candidate = Path.Combine(manager, name.Name + ".dll");
    return File.Exists(candidate) ? AssemblyLoadContext.Default.LoadFromAssemblyPath(candidate) : null;
};
var core = AssemblyLoadContext.Default.LoadFromAssemblyPath(Path.Combine(manager, "HD2ModCore.dll"));
Console.WriteLine(core.GetType("HD2ModCore.Infrastructure.PhysBoneLuaPackageExport")!
    .GetMethod("Export", BindingFlags.Public | BindingFlags.Static)!.Invoke(null, [destination]));
}
catch(Exception error)
{
    Console.Error.WriteLine(error);Environment.ExitCode=1;
}

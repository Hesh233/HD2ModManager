using HD2SourceMigration.VpkConversion;
using System.Text.Json;
try
{
    if(args.Length!=2)throw new ArgumentException("PhysicsConsumerAudit model-directory output-json (read-only inputs)");
    var input=Path.GetFullPath(args[0]);var output=Path.GetFullPath(args[1]);
    var workspace=Path.GetFullPath(Environment.CurrentDirectory);
    if(!File.Exists(Path.Combine(workspace,"AGENTS.md"))||!Directory.Exists(Path.Combine(workspace,"HD2SourceMigration")))throw new IOException("Run in the SDK manager workspace");
    if(!output.StartsWith(Path.TrimEndingDirectorySeparator(workspace)+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase)||output.StartsWith(input+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase))throw new IOException("Output must be outside the input library and inside workspace");
    var bytes=await PhysicsConsumerManifestBuilder.BuildAsync(input);Directory.CreateDirectory(Path.GetDirectoryName(output)!);await File.WriteAllBytesAsync(output,bytes);Console.WriteLine("Read-only consumer facts written: "+output);
}
catch(Exception e)
{
    Console.Error.WriteLine(JsonSerializer.Serialize(new{status="REJECTED_READ_ONLY_CONSUMER_FACTS",reason=e.Message}));Environment.ExitCode=1;
}

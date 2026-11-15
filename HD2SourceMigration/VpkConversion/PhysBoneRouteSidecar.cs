using System.Text;
using HD2ModAdaptation.PatchReconstruction;

namespace HD2SourceMigration.VpkConversion;

/// <summary>Explicit conversion-route contract. Missing legacy metadata never opts into direct physics.</summary>
public static class PhysBoneRouteSidecar
{
	public const string FileName = "physbone-route.txt";
	public const string RecordName = "hd2_physics_route.txt";
	public const string Direct = "direct-v1";
	public const string Skeleton = "skeleton-v1";

	public static string Write(string directory, bool preserveSkeletonBind)
	{
		ArgumentException.ThrowIfNullOrWhiteSpace(directory);
		Directory.CreateDirectory(directory);
		var path = Path.Combine(directory, FileName);
		File.WriteAllText(path, preserveSkeletonBind ? Skeleton : Direct, new UTF8Encoding(false));
		return path;
	}

	public static string? Read(string modDirectory)
	{
		ArgumentException.ThrowIfNullOrWhiteSpace(modDirectory);
		string? route = null;
		// Same bounded content layers as the rig sidecar; never walk user backup folders.
		foreach (var directory in new[] { modDirectory,
			Path.Combine(modDirectory, ModContentLayerNames.Sectional),
			Path.Combine(modDirectory, ModContentLayerNames.LegacySectional),
			Path.Combine(modDirectory, ModContentLayerNames.Overwrite) }.Distinct(StringComparer.OrdinalIgnoreCase))
		{
			var path = Path.Combine(directory, FileName);
			if (!File.Exists(path)) continue;
			var value = File.ReadAllText(path, Encoding.UTF8).Trim();
			if (value != Direct && value != Skeleton)
				throw new InvalidDataException($"Invalid physics route in {path}: {value}");
			if (route is not null && route != value)
				throw new InvalidDataException("Conflicting physics routes in the same mod; rebuild its matching conversion artifacts.");
			route = value;
		}
		return route;
	}
}

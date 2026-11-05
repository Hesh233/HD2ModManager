using System.Globalization;
using System.Text.Json;
using HD2ModCore.Domain;

namespace HD2ModCore.Infrastructure;

/// <summary>Register portable native models from the files actually committed to this library.</summary>
internal static class NativeSkeletonModelImport
{
	private const ulong UnitType = 0xe0a48d0be9a7453f;
	private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);

	internal static async ValueTask<RuntimeArmorRegistryDocument?> PrepareAsync(
		RuntimeArmorRegistryService registry, IEnumerable<string> modDirectories, CancellationToken cancellationToken)
	{
		var imported = new List<RuntimeArmorRegistryModel>();
		var scanner = new PatchTocScanner();
		var parser = new PatchFileNameParser();
		foreach (var directory in modDirectories)
		{
			var manifestPath = Path.Combine(directory, "source-skeleton.json");
			var modelPath = Path.Combine(directory, VpkCustomModelFile.FileName);
			// Animation packages may contain a manifest without a model definition.
			if (!File.Exists(manifestPath) || !File.Exists(modelPath)) continue;
			cancellationToken.ThrowIfCancellationRequested();
			if (new FileInfo(manifestPath).Length > 4 * 1024 * 1024 || new FileInfo(modelPath).Length > 256 * 1024)
				throw new InvalidDataException("原生骨架或素体定义文件过大。");
			RuntimeArmorRegistryModel? model;
			try
			{
				using var manifest = JsonDocument.Parse(await File.ReadAllTextAsync(manifestPath, cancellationToken).ConfigureAwait(false));
				var root = manifest.RootElement;
				if (root.ValueKind != JsonValueKind.Object
					|| !root.TryGetProperty("version", out var version) || version.ValueKind != JsonValueKind.Number
					|| !version.TryGetInt32(out var number) || number != 1
					|| !root.TryGetProperty("bones", out var bones) || bones.ValueKind != JsonValueKind.Array || bones.GetArrayLength() == 0)
					throw new InvalidDataException("原生骨架清单需要 version=1 和非空 bones。");
				model = JsonSerializer.Deserialize<RuntimeArmorRegistryModel>(
					await File.ReadAllTextAsync(modelPath, cancellationToken).ConfigureAwait(false), JsonOptions);
			}
			catch (JsonException error)
			{
				throw new InvalidDataException($"原生素体 JSON 无效：{modelPath}", error);
			}
			if (model is null || string.IsNullOrWhiteSpace(model.Key) || model.Key != model.Key.Trim()
				|| model.SourceItemId is not null || model.Pieces is not { Count: > 0 }
				|| model.Pieces.Any(piece => piece is null || string.IsNullOrWhiteSpace(piece.Unit)))
				throw new InvalidDataException("原生素体必须提供有效 key 和自定义 Unit 件表。");
			RuntimeArmorRegistryService.ValidateWorkspaceDocument(new(0, false, [], [model]));

			var units = new HashSet<ulong>();
			var payloadDirectories = new[] { directory, Path.Combine(directory, "vpk2patch") }.Where(Directory.Exists);
			foreach (var payload in payloadDirectories)
			foreach (var path in Directory.EnumerateFiles(payload))
			{
				if (!parser.TryParse(path, out var name) || name!.SidecarKind != PatchSidecarKind.Base) continue;
				var entries = await scanner.ScanEntriesAsync(path, cancellationToken).ConfigureAwait(false);
				units.UnionWith(entries.Where(entry => entry.AssetKey.TypeId == UnitType).Select(entry => entry.AssetKey.FileId));
			}
			foreach (var piece in model.Pieces)
			{
				if (!units.Contains(ulong.Parse(piece.Unit, NumberStyles.HexNumber, CultureInfo.InvariantCulture)))
					throw new InvalidDataException($"原生素体 {model.Key} 的 Unit {piece.Unit} 不在该 Mod 的补丁中。");
			}
			imported.Add(model);
		}
		if (imported.Count == 0) return null;

		// A portable import must never adopt another library's deployed protocol.
		var current = await registry.ReadWorkspaceDocumentOrEmptyAsync(cancellationToken).ConfigureAwait(false);
		var merged = current.ModelDefinitions.ToDictionary(model => model.Key, StringComparer.Ordinal);
		var changed = false;
		foreach (var model in imported)
		{
			if (merged.TryGetValue(model.Key, out var existing))
			{
				if (!SameDefinition(existing, model))
					throw new InvalidDataException($"原生素体键 {model.Key} 已存在且件表不同；请重新转换生成新的素体标识。");
				continue;
			}
			merged.Add(model.Key, model);
			changed = true;
		}
		if (!changed) return null;
		var result = new RuntimeArmorRegistryDocument(current.Revision, current.Enabled, current.Mappings,
			merged.Values.ToArray(), current.PieceOverrideDefinitions, current.TargetModeDefinitions, current.CompositionMode);
		RuntimeArmorRegistryService.ValidateWorkspaceDocument(result);
		return result;
	}

	private static bool SameDefinition(RuntimeArmorRegistryModel first, RuntimeArmorRegistryModel second)
	{
		static IEnumerable<RuntimeArmorRegistryModelPiece> Ordered(RuntimeArmorRegistryModel model)
			=> (model.Pieces ?? []).Select(piece => piece with { Unit = piece.Unit.ToLowerInvariant() })
				.OrderBy(piece => piece.Body).ThenBy(piece => piece.Slot).ThenBy(piece => piece.PieceType);
		// Preserve the user's display name when reimporting an identical model.
		return first.SourceItemId == second.SourceItemId && Ordered(first).SequenceEqual(Ordered(second));
	}
}

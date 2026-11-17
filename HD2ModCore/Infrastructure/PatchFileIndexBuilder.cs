using HD2ModCore.Application;
using HD2ModCore.Domain;

namespace HD2ModCore.Infrastructure;

// 作用：从库目录真实扫描每个 mod 的 patch 文件，并按 hex/编号生成临时事实索引。
// Purpose: Scans real patch files for each mod and builds a temporary fact index ordered by archive hex and patch index.
public sealed class PatchFileIndexBuilder : IPatchFileIndexBuilder
{
	private readonly IPatchFileNameParser _parser;

	public PatchFileIndexBuilder(IPatchFileNameParser parser)
	{
		_parser = parser ?? throw new ArgumentNullException(nameof(parser));
	}

	public ValueTask<PatchFileIndex> BuildAsync(LibrarySnapshot snapshot, string modsRootDirectory, CancellationToken cancellationToken = default)
	{
		if (snapshot is null)
		{
			throw new ArgumentNullException(nameof(snapshot));
		}
		if (string.IsNullOrWhiteSpace(modsRootDirectory))
		{
			throw new ArgumentException("Value cannot be null or whitespace.", nameof(modsRootDirectory));
		}

		var byNode = new Dictionary<ModNodeId, IReadOnlyList<IndexedPatchFile>>();
		var issues = new List<CoreIssue>();
		foreach (var node in snapshot.Nodes.Values)
		{
			cancellationToken.ThrowIfCancellationRequested();
			var nodeDir = Path.Combine(modsRootDirectory, node.RelativePath);
			if (!Directory.Exists(nodeDir))
			{
				issues.Add(new CoreIssue(CoreIssueSeverity.Warning, "ModDirectoryMissing", $"Mod directory does not exist: {nodeDir}", nodeDir, node.Id));
				byNode[node.Id] = Array.Empty<IndexedPatchFile>();
				continue;
			}

			// 会进游戏的文件：只看"有哪一层"，不逐个 patch 判断。
			// Overwrite 有有效 patch ⇒ 只部署它；sectional 类 ⇒ 硬链接成生效层；legacy ⇒ 根目录。
			var deployable = ModDeployableFiles.Resolve(nodeDir, _parser);
			if (deployable.SkipReason is not null)
			{
				issues.Add(new CoreIssue(CoreIssueSeverity.Warning, "ModNotDeployable", deployable.SkipReason, nodeDir, node.Id));
				byNode[node.Id] = Array.Empty<IndexedPatchFile>();
				continue;
			}
			var selectedByName = deployable.FilesByName;

			// 结构文件里如果写了顺序，就以它为准（那是用户排的，代表"谁覆盖谁"的意图）。
			var orderByPatchFileName = new System.Collections.Generic.Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
			if (ModNodePayloadLayout.TryGetExistingVpkPatchDirectory(nodeDir) is { } manifestDirectory)
			{
				var manifest = SectionalPatchManifestFile
					.TryReadAsync(manifestDirectory).AsTask().GetAwaiter().GetResult();
				foreach (var entry in manifest?.Patches ?? Array.Empty<HD2ModCore.Domain.SectionalPatchGroupEntry>())
				{
					if (entry.Order is not { } order) continue;
					orderByPatchFileName[$"{entry.ArchiveHex16}.patch_{entry.PatchIndex}"] = order;
				}
			}

			var parsed = selectedByName.Values
				.Select(path => (Path: path, Name: Path.GetFileName(path), Info: TryParse(path)))
				.Where(x => x.Info is not null)
				.Select(x => (x.Path, x.Name, Info: x.Info!))
				.ToList();

			var files = new List<IndexedPatchFile>();

			// base 与 sidecar 必须来自同一个目录。
			//
			// 为什么：patch 的 TOC 里写的是 GPU 段在 sidecar 里的**偏移与长度**。拿 A 的 TOC 配 B 的
			// gpu_resources，游戏读到的是越界/错位的数据——它不会报错，只会"什么都不显示"。
			// 实测踩过一次：换甲变体只顶替了 base、sidecar 还留在 vpk2patch/，进游戏后 RE-2310 没变。
			// 这条检查把它变成一条看得见的警告，而不是一次靠猜的实机排查。
			foreach (var basePatch in parsed.Where(x => x.Info.SidecarKind == PatchSidecarKind.Base))
			{
				var baseDirectory = Path.GetDirectoryName(basePatch.Path)!;
				foreach (var suffix in new[] { ".gpu_resources", ".stream" })
				{
					var sidecarName = basePatch.Name + suffix;
					if (!selectedByName.TryGetValue(sidecarName, out var sidecarPath))
						continue;
					if (string.Equals(Path.GetDirectoryName(sidecarPath), baseDirectory, StringComparison.OrdinalIgnoreCase))
						continue;
					issues.Add(new CoreIssue(CoreIssueSeverity.Warning, "PatchSidecarFromAnotherDirectory",
						$"patch 与它的 {suffix} 来自不同目录（{baseDirectory} / {Path.GetDirectoryName(sidecarPath)}）；"
						+ "部署后游戏读到的会是错位的数据。",
						sidecarPath, node.Id));
				}
			}

			foreach (var group in parsed.GroupBy(x => x.Info.ArchiveHex16, StringComparer.OrdinalIgnoreCase))
			{
				var baseOrder = group
					.Where(x => x.Info.SidecarKind == PatchSidecarKind.Base)
					.Select(x => x.Info.PatchIndex)
					.Distinct()
					.OrderBy(x => x)
					.Select((source, normalized) => new { source, normalized })
					.ToDictionary(x => x.source, x => x.normalized);

				foreach (var file in group.OrderBy(x => x.Info.PatchIndex).ThenBy(x => x.Info.SidecarKind))
				{
					cancellationToken.ThrowIfCancellationRequested();
					if (!baseOrder.TryGetValue(file.Info.PatchIndex, out var normalizedOrder))
					{
						issues.Add(new CoreIssue(CoreIssueSeverity.Warning, "SidecarWithoutBase", $"Patch sidecar has no base patch: {file.Path}", file.Path, node.Id));
						continue;
					}

					var info = new FileInfo(file.Path);
					files.Add(new IndexedPatchFile(
						NodeId: node.Id,
						FilePath: file.Path,
						FileName: file.Name,
						ArchiveHex16: file.Info.ArchiveHex16,
						SourcePatchIndex: file.Info.PatchIndex,
						NormalizedOrder: normalizedOrder,
						SidecarKind: file.Info.SidecarKind,
						Length: info.Exists ? info.Length : 0,
						LastWriteTimeUtc: info.Exists ? info.LastWriteTimeUtc : DateTimeOffset.MinValue,
						DeployOrder: orderByPatchFileName.TryGetValue(file.Name, out var declaredOrder)
							? declaredOrder
							: normalizedOrder));
				}
			}

			PreserveCustomModelSource(nodeDir, node.Id, files, issues, cancellationToken);

			byNode[node.Id] = files
				.OrderBy(f => f.ArchiveHex16, StringComparer.OrdinalIgnoreCase)
				.ThenBy(f => f.NormalizedOrder)
				.ThenBy(f => f.SidecarKind)
				.ToList();
		}

		return ValueTask.FromResult(new PatchFileIndex(DateTimeOffset.UtcNow, byNode, issues));
	}


	// Direct rekey replaces the custom Unit IDs in Overwrite. Keep the source
	// namespace as an earlier group, not as a same-name override. The ordinary
	// effective files still win for material/section/dependency edits. This is
	// a read-only index addition: no model files or game deployment are written.
	private void PreserveCustomModelSource(string nodeDirectory, ModNodeId nodeId,
		List<IndexedPatchFile> files, List<CoreIssue> issues, CancellationToken cancellationToken)
	{
		var overwrite = ModNodePayloadLayout.GetOverwriteDirectory(nodeDirectory);
		if (!File.Exists(Path.Combine(overwrite, ".hd2-vpk-rekey-overwrite"))) return;
		var payload = ModNodePayloadLayout.TryGetExistingVpkPatchDirectory(nodeDirectory);
		var model = VpkCustomModelFile.TryReadModel(nodeDirectory);
		if (payload is null || model?.SourceItemId is not null || model?.Pieces is not { Count: > 0 }) return;
		try
		{
			var expected = model.Pieces.Select(piece => Convert.ToUInt64(piece.Unit, 16)).ToHashSet();
			var effective = RuntimeArmorResourceFilter.ReadDeployedUnitsAsync(overwrite, cancellationToken).GetAwaiter().GetResult();
			if (expected.All(effective.Contains)) return; // self-target already retains the namespace
			var source = RuntimeArmorResourceFilter.ReadDeployedUnitsAsync(payload, cancellationToken).GetAwaiter().GetResult();
			if (!expected.All(source.Contains) || source.Any(unit => !expected.Contains(unit)))
				throw new InvalidDataException("自定义素体来源 Unit 与登记不一致，不能补入映射部署载荷。");
			var parsed = Directory.EnumerateFiles(payload, "*", SearchOption.TopDirectoryOnly)
				.Select(path => (Path: path, Info: TryParse(path))).Where(item => item.Info is not null).ToArray();
			foreach (var archive in parsed.GroupBy(item => item.Info!.ArchiveHex16, StringComparer.OrdinalIgnoreCase))
			{
				var groups = archive.Where(item => item.Info!.SidecarKind == PatchSidecarKind.Base)
					.OrderBy(item => item.Info!.PatchIndex).ToArray();
				for (var index = 0; index < groups.Length; index++)
				{
					var group = groups[index];
					foreach (var file in archive.Where(item => item.Info!.PatchIndex == group.Info!.PatchIndex))
					{
						cancellationToken.ThrowIfCancellationRequested();
						var info = new FileInfo(file.Path);
						files.Add(new IndexedPatchFile(nodeId, file.Path, info.Name, file.Info!.ArchiveHex16,
							file.Info.PatchIndex, index - groups.Length, file.Info.SidecarKind,
							info.Length, info.LastWriteTimeUtc, int.MinValue + index));
					}
				}
			}
		}
		catch (Exception exception) when (exception is IOException or InvalidDataException or UnauthorizedAccessException or FormatException or OverflowException)
		{
			issues.Add(new CoreIssue(CoreIssueSeverity.Error, "CustomModelSourceDeploymentInvalid",
				$"无法保留自定义素体映射载荷：{exception.Message}", nodeDirectory, nodeId, exception.ToString()));
		}
	}

	private PatchFileNameInfo? TryParse(string path)
		=> _parser.TryParse(Path.GetFileName(path), out var info) ? info : null;

	private static bool IsPatchToc(string path)
	{
		try
		{
			using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read);
			Span<byte> header = stackalloc byte[sizeof(uint)];
			return stream.Read(header) == header.Length && BitConverter.ToUInt32(header) == 4026531857;
		}
		catch (IOException) { return false; }
		catch (UnauthorizedAccessException) { return false; }
	}
}

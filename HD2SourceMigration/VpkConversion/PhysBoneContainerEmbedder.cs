using System.Text;
using HD2ModAdaptation.PatchReconstruction;
using HD2ModAdaptation.PatchReconstruction.UnitMesh;
using HD2SourceModel;

namespace HD2SourceMigration.VpkConversion;

/// <summary>
/// 把来源模型的 jigglebone 参数（<c>HD2PBX01</c> 容器）嵌进**模型 patch** 的
/// <c>.gpu_resources</c> 末尾，让"参数跟着产物走"——换模型不必再手动换 rig 文件。
/// <para>
/// 为什么追加在末尾而不是加成一个 toc 条目：
/// 运行时要读它，而 Lua 侧只有一个 <c>io.open</c>；用协议里的 EOF footer（<c>HD2PBFT1</c>）
/// 就能从"文件长度 − 容器长度"回推起点，完全不需要解析 patch 的 toc 布局。
/// 协议明确允许这种写法：容器放在受引用的数据范围**之后**，任何重排都不会踩到它。
/// </para>
/// <para>
/// 幂等：每次先 <see cref="PhysBoneContainer.StripIfPresent"/> 再追加，所以重复导入不会层层叠加。
/// </para>
/// </summary>
public static class PhysBoneContainerEmbedder
{
	public sealed record Outcome(
		bool Embedded,
		bool AlreadyPresent,
		int BoneCount,
		int PatchCount,
		long AddedBytes,
		string? Reason)
	{
		public static Outcome Skip(string reason) => new(false, false, 0, 0, 0, reason);

		/// <summary>
		/// 这次嵌进去的 rig 是从哪来的。三种取值：
		/// 转换期产出的 <c>physbone-rig.bin</c>（**带链根锚点**，最完整）、
		/// 用户给的裸 rig 文件、来源 VPK 重读（**不带锚点**，裙摆那类链会缺锚点）。
		/// 排查"为什么某块布不晃"时，第一个要看的就是这个。
		/// </summary>
		public string? RigSource { get; init; }

		/// <summary>
		/// 同时嵌入的 QuatInterp driver 骨数（VRD 姿态驱动）；<c>null</c> = 这次没有 driver 记录
		/// （旧双链线 / 模型没有 driver 骨，容器与历史字节一致）。
		/// </summary>
		public int? DriverBoneCount { get; init; }
	}

	/// <summary>模块名常量，运行时按这个名字取容器里的记录（与协议文档一致）。</summary>
	public const string RigRecordName = "hd2_spring_rig.bin";

	/// <summary>
	/// QuatInterp driver rig 的记录名（VRD"姿态驱动"半边）。**可选项**：没有 sidecar 时
	/// 根本不写这条记录，容器与历史字节完全一致；运行时读不到它就是现状行为。
	/// </summary>
	public const string DriverRecordName = "hd2_driver_rig.bin";

	/// <summary>
	/// 给 <paramref name="modDirectory"/> 下所有**含 Unit 的** patch 嵌入容器。
	/// 没有 jiggle 骨、或者找不到模型 patch 时返回 <see cref="Outcome.Skip"/>（调用方当作正常的"不需要"）。
	/// </summary>
	/// <param name="vpkPath">
	/// 来源：一个 VPK、或一份裸 rig（<c>HD2SRG01</c>）。可以给 <c>null</c>——
	/// 那样就只按 <paramref name="modDirectory"/> 自己找（见 <see cref="ResolveSource"/>）。
	/// </param>
	public static async Task<Outcome> EmbedAsync(
		string? vpkPath,
		string modDirectory,
		CancellationToken cancellationToken = default)
	{
		ArgumentException.ThrowIfNullOrWhiteSpace(modDirectory);
		if (!Directory.Exists(modDirectory))
			return Outcome.Skip($"Mod 目录不存在：{modDirectory}");

		// 来源优先级：**转换期产出的 rig** > 显式来源 > 目录里唯一的 .vpk。
		//
		// 为什么转换期那份优先：容器里的"链根锚点名"只有重定向那一刻算得出来
		// （源骨架里有一批骨在 HD2 侧不存在，要写成它回退到的 HD2 骨名）。embed-mod 只看得到
		// 来源 VPK、看不到 HD2 骨架，重算不出来——不读这份，裙摆那类链会整条记「缺锚点」被跳过。
		byte[] rig;
		int boneCount;
		string rigSource;
		var sidecarPath = PhysBoneRigSidecar.Locate(modDirectory);
		var sidecar = sidecarPath is null ? null : PhysBoneRigSidecar.TryRead(sidecarPath);
		if (sidecar is not null)
		{
			rig = sidecar;
			boneCount = -1;   // 交回读校验把关（与裸 rig 同一口径）
			rigSource = Path.GetFileName(sidecarPath!);
		}
		else if (ResolveSource(vpkPath, modDirectory, out var sourceReason) is not { } source)
		{
			return Outcome.Skip(sourceReason!);
		}
		else if (source.EndsWith(".bin", StringComparison.OrdinalIgnoreCase))
		{
			rig = await File.ReadAllBytesAsync(source, cancellationToken).ConfigureAwait(false);
			if (rig.Length < 8 || !rig.AsSpan(0, 8).SequenceEqual(PhysBoneSpringRig.Magic))
				return Outcome.Skip($"{Path.GetFileName(source)} 不是裸 rig（应以 HD2SRG01 开头）");
			boneCount = -1;   // 裸 rig 不解析骨数，交回读校验把关
			rigSource = Path.GetFileName(source);
		}
		else
		{
			SourceModelInspection inspection;
			try
			{
				inspection = SourceModelInspector.Inspect(source);
			}
			catch (Exception exception) when (exception is IOException or InvalidDataException or InvalidOperationException)
			{
				return Outcome.Skip($"读取来源模型失败：{exception.Message}");
			}

			if (inspection.JiggleBones.Count == 0)
				return Outcome.Skip("来源模型没有 jigglebone");

			rig = PhysBoneSpringRig.Serialize(inspection.JiggleBones);
			boneCount = inspection.JiggleBones.Count;
			rigSource = "来源 VPK（未带链根锚点）";
		}
		var scanner = new PatchTocScanner();
		var embedded = 0;
		var alreadyPresent = false;
		long added = 0;
		var locked = new List<string>();

		// Driver rig（VRD 姿态驱动）是**可选**第二条记录：转换期没产出它（旧双链线 / 无 driver 骨
		// 的模型）就完全不写，容器与历史字节一致。有它才追加，且 Strip→重加保证幂等。
		byte[]? driverRig = null;
		var driverSidecarPath = PhysBoneDriverRigSidecar.Locate(modDirectory);
		if (driverSidecarPath is not null)
		{
			driverRig = PhysBoneDriverRigSidecar.TryRead(driverSidecarPath);
			if (driverRig is null)
				return new Outcome(false, alreadyPresent, boneCount, 0, 0,
					$"{Path.GetFileName(driverSidecarPath)} 不是有效的 driver rig（应以 HD2DRV01 开头）")
					{ RigSource = rigSource };
		}

		foreach (var patchPath in EnumeratePatchFiles(modDirectory))
		{
			var gpuPath = patchPath + ".gpu_resources";
			if (!File.Exists(gpuPath))
				continue;
			// 只认含 Unit 的 patch：材质 patch 里没有 unit，嵌进去只是白占地方。
			if (!await ContainsUnitAsync(scanner, patchPath, cancellationToken).ConfigureAwait(false))
				continue;

			byte[] carrier;
			try
			{
				carrier = await File.ReadAllBytesAsync(gpuPath, cancellationToken).ConfigureAwait(false);
			}
			catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
			{
				// 游戏/管理器正打开着这个文件时改不了。跳过并如实报告，不要整批失败：
				// 调用方（GUI 导入）随后会再调一次，或提示用户关掉游戏。
				locked.Add(Path.GetFileName(patchPath) + "：" + exception.Message);
				continue;
			}
			var clean = PhysBoneContainer.StripIfPresent(carrier, out var had).ToArray();
			alreadyPresent |= had;
			var entries = new List<PhysBoneContainer.Entry> { new(RigRecordName, rig) };
			if (driverRig is not null)
				entries.Add(new PhysBoneContainer.Entry(DriverRecordName, driverRig));
			var combined = PhysBoneContainer.AppendTo(clean, entries);
			if (combined.AsSpan().SequenceEqual(carrier))
				continue;   // 已经是最新内容，不写盘
			try
			{
				await File.WriteAllBytesAsync(gpuPath, combined, cancellationToken).ConfigureAwait(false);
			}
			catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
			{
				locked.Add(Path.GetFileName(patchPath) + "：" + exception.Message);
				continue;
			}

			embedded++;
			added += combined.Length - carrier.Length;

			// **写入后回读校验**：这一步是"vpk2patch → Overwrite 时参数会不会丢"的守门员。
			// 只要有一次读不回来，就当这次嵌入失败（宁可让调用方知道，也不要交付一个没有参数的 patch）。
			var verification = Verify(gpuPath, rig.Length, driverRig?.Length);
			if (verification is not null)
				return new Outcome(false, alreadyPresent, boneCount, embedded, added,
					$"{Path.GetFileName(patchPath)} 写入后校验失败：{verification}")
					{ RigSource = rigSource };
		}

		if (locked.Count > 0 && embedded == 0)
			return new Outcome(false, alreadyPresent, boneCount, 0, 0, "文件被占用：" + string.Join("；", locked.Take(3)))
				{ RigSource = rigSource };

		return embedded == 0 && !alreadyPresent
			? Outcome.Skip("没有找到含 Unit 的 patch")
			: new Outcome(true, alreadyPresent, boneCount, embedded, added,
				locked.Count > 0 ? "部分 patch 被占用未更新：" + string.Join("；", locked.Take(3)) : null)
				{ RigSource = rigSource, DriverBoneCount = driverRig is null ? null : CountDriverBones(driverRig) };
	}

	/// <summary>从 driver rig 字节里读出骨数（写容器报告用；解析交给运行时）。</summary>
	private static int CountDriverBones(byte[] rig)
		=> rig.Length >= 16 ? (int)BitConverter.ToUInt32(rig, 12) : 0;

	/// <summary>
	/// 决定这次从哪儿取参数：显式来源优先；没给就只看 mod 目录。
	/// <para>
	/// <b>为什么多 VPK 时宁可不嵌。</b>以前调用方取"目录里第一个 <c>*.vpk</c>"，
	/// 而多 VPK 的包（模型 + 贴图分包）里第一个往往<b>不是</b>模型那份——于是拿别的模型
	/// 的 jiggle 参数去驱动这套护甲，或者干脆 0 条链。猜错的代价比"没嵌上"高得多：
	/// 没嵌上会在导入报告里明说，猜错是静默的。
	/// </para>
	/// </summary>
	private static string? ResolveSource(string? explicitPath, string modDirectory, out string? reason)
	{
		reason = null;
		if (!string.IsNullOrWhiteSpace(explicitPath))
		{
			if (!File.Exists(explicitPath))
			{
				reason = $"来源 VPK 不存在：{explicitPath}";
				return null;
			}

			return explicitPath;
		}

		var found = Directory.EnumerateFiles(modDirectory, "*.vpk", SearchOption.TopDirectoryOnly).ToArray();
		if (found.Length == 1)
			return found[0];
		if (found.Length == 0)
		{
			reason = $"Mod 目录里既没有 {PhysBoneRigSidecar.FileName} 也没有 .vpk，无从取物理参数";
			return null;
		}

		reason = "Mod 目录里有多个 .vpk，判断不出哪一个是这套护甲的来源（"
			+ string.Join("、", found.Select(Path.GetFileName))
			+ "）；重新导入一次即可带上来源 rig";
		return null;
	}

	/// <summary>回读校验：容器能取出、里面有 <see cref="RigRecordName"/> 且长度一致；给了 driver 长度也一并校验。</summary>
	private static string? Verify(string gpuPath, int expectedRigBytes, int? expectedDriverBytes)
	{
		var bytes = File.ReadAllBytes(gpuPath);
		if (PhysBoneCarrier.ExtractContainer(bytes) is null)
			return "末尾取不到 HD2PBX01 容器（footer 不对或起点不是 magic）";
		var length = PhysBoneCarrier.ReadRigRecordLength(bytes);
		if (length < 0)
			return $"容器里没有 {RigRecordName}";
		if (length != expectedRigBytes)
			return $"{RigRecordName} 长度 {length} 与期望 {expectedRigBytes} 不一致";
		if (expectedDriverBytes is { } driverBytes)
		{
			// driver 记录用容器索引核对：名字对、长度对，缺了就是"嵌的时候被丢了"。
			var record = FindRecord(bytes, DriverRecordName);
			if (record is null)
				return $"容器里没有 {DriverRecordName}";
			if (record.Value.length != driverBytes)
				return $"{DriverRecordName} 长度 {record.Value.length} 与期望 {driverBytes} 不一致";
		}
		return null;
	}

	/// <summary>
	/// 在载体里按容器索引找一条命名记录（与 lua <c>parse_container</c> 同一套布局：
	/// 索引记录 0x00 nameLen u16 / 0x04 dataOffset u64 / 0x0C dataLength u64 / 0x38 名字）。
	/// 返回 (dataOffset 相对容器起点, dataLength)；找不到返回 null。
	/// </summary>
	private static (int offset, int length)? FindRecord(byte[] carrier, string recordName)
	{
		var container = PhysBoneCarrier.ExtractContainer(carrier);
		if (container is null) return null;
		var count = BitConverter.ToUInt32(container, 0x28);
		var indexOffset = (int)BitConverter.ToUInt64(container, 0x18);
		var cursor = indexOffset;
		for (var i = 0; i < count; i++)
		{
			var nameLength = BitConverter.ToUInt16(container, cursor);
			var dataOffset = (int)BitConverter.ToUInt64(container, cursor + 4);
			var dataLength = (int)BitConverter.ToUInt64(container, cursor + 12);
			var name = Encoding.UTF8.GetString(container, cursor + 0x38, nameLength);
			if (name == recordName)
				return (dataOffset, dataLength);
			cursor += 0x38 + nameLength;
		}

		return null;
	}
	private static IEnumerable<string> EnumeratePatchFiles(string modDirectory)
	{
		// 约定：根 = 来源，vpk2patch/ = 转换产物，Overwrite/ = 在产物上再改出来的变体。
		// 三处都要嵌（谁被启用取决于用户在配置里怎么排），但**不递归到底**，避免误伤用户的备份目录。
		foreach (var directory in new[]
		{
			modDirectory,
			Path.Combine(modDirectory, "vpk2patch"),
			Path.Combine(modDirectory, "Overwrite"),
		})
		{
			if (!Directory.Exists(directory))
				continue;
			foreach (var path in Directory.EnumerateFiles(directory, "*.patch_*", SearchOption.TopDirectoryOnly))
			{
				// 跳过 sidecar：*.patch_3.gpu_resources / *.stream 也会匹配到这个模式的一部分
				if (path.EndsWith(".gpu_resources", StringComparison.OrdinalIgnoreCase)
					|| path.EndsWith(".stream", StringComparison.OrdinalIgnoreCase))
					continue;
				yield return path;
			}
		}
	}

	private static async Task<bool> ContainsUnitAsync(
		PatchTocScanner scanner,
		string patchPath,
		CancellationToken cancellationToken)
	{
		try
		{
			var entries = await scanner.ScanEntriesAsync(patchPath, cancellationToken).ConfigureAwait(false);
			return entries.Any(entry => entry.AssetKey.TypeId == PatchUnitMeshReader.UnitTypeId);
		}
		catch (Exception exception) when (exception is IOException or InvalidDataException or IndexOutOfRangeException)
		{
			return false;
		}
	}
}

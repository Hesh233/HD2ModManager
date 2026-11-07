using HD2SourceModel;

namespace HD2SourceMigration.VpkConversion;

/// <summary>
/// 转换期产出的 **QuatInterp driver rig**（VRD 的"姿态驱动"半边），落在 patch 旁边，
/// 等 <c>physbone embed-mod</c> 把它作为容器里的第二条记录（<c>hd2_driver_rig.bin</c>）嵌进
/// <c>.gpu_resources</c>。布局与嵌入方式见 <see cref="PhysBoneDriverRig"/> 与
/// <see cref="PhysBoneContainerEmbedder"/>。
/// <para>
/// 为什么与弹簧 rig 一样走 sidecar：链根/控制骨的**导出节点名**只有重定向那一刻才知道
/// （单骨架路线的节点名是 <c>hd2n_&lt;ns&gt;_&lt;role&gt;_&lt;index&gt;_&lt;label&gt;</c>），
/// embed-mod 只看得到来源 VPK，映射不出来。转换期写、嵌入期读，与弹簧 rig 同一套时序。
/// </para>
/// <para>
/// <b>为什么只喂单骨架路线（native.Manifest != null）。</b>旧双链线是冻结基线：模型里虽有
/// Source 段节点，但网格蒙皮在原生骨+合成骨上，driver 骨转了也看不见——嵌一条用不上的记录
/// 只会增加运行时写入。单骨架路线把全部 Source 节点（含 driver 的 aux 骨）连权重一起保留，
/// driver 旋转才有视觉效果。
/// </para>
/// </summary>
public static class PhysBoneDriverRigSidecar
{
	/// <summary>约定文件名。放在 <c>vpk2patch/</c>（和 <c>physbone-rig.bin</c> 同级）。</summary>
	public const string FileName = "physbone-driver-rig.bin";

	/// <summary>
	/// 把"源骨显示名 → 导出节点名"映射应用到 driver 事实上，并把线性量换算成米。
	/// <para>
	/// 名字映射与 <see cref="PhysBoneRigSidecar.ForNativeSkeleton"/> 同一张表：
	/// manifest 里每根骨都带 <c>SourceName</c>（原始名）与 <c>Name</c>（导出名）。
	/// driver 骨、父骨、控制骨三者都必须换成本地能 <c>has_node</c> 到的导出名——
	/// 运行时按名字解析节点，查不到的骨会被逐根跳过并记账。
	/// </para>
	/// <para>
	/// 位置换算：英寸 → 米 × 模型倍率（与单骨架路线的统一换算一致）。
	/// 触发四元数与输出四元数是方向量，不缩放。帧映射保持单位四元数
	/// （native 路线保留完整 Source 层级，无跨帧换算）。
	/// </para>
	/// </summary>
	public static IReadOnlyList<SourceQuatInterpDriverFact> ForNativeSkeleton(
		IReadOnlyList<SourceQuatInterpDriverFact> facts, double modelScale,
		Retarget.NativeSourceManifest? manifest = null)
	{
		if (!double.IsFinite(modelScale) || modelScale <= 0 || modelScale > 10)
			throw new ArgumentOutOfRangeException(nameof(modelScale));
		var scale = Retarget.RetargetConstants.InchesToMetres * modelScale;
		// Native/multi rigs must never acquire the single-only v3 behavior.
		var scaled = ScalePositions(facts, scale).Select(f => f with { RuntimeControlBind = null }).ToArray();
		if (manifest is null) return scaled;
		var names = manifest.Bones.ToDictionary(b => b.SourceName ?? b.Name, b => b.Name);
		return scaled.Select(fact => fact with
		{
			BoneName = names.GetValueOrDefault(fact.BoneName, fact.BoneName),
			ParentName = names.GetValueOrDefault(fact.ParentName, fact.ParentName),
			ControlName = names.GetValueOrDefault(fact.ControlName, fact.ControlName),
		}).ToArray();
	}

	/// <summary>
	/// 单骨架（Snap 塌缩）路线的 driver 事实：名字三方已由 <c>RetargetResult.DriverFrames</c>
	/// 解析为最终节点名，这里把**世界 bind 位置从源英寸折算成米**（与弹簧参数同口径；
	/// 运行时只写旋转不用位置，折算只为诊断口径一致），并做名字三方校验。
	/// 烘焙由 <see cref="Write"/> 内的 <see cref="PhysBoneDriverRig.Bake"/> 统一执行。
	/// </summary>
	public static IReadOnlyList<SourceQuatInterpDriverFact> ForSingleSkeleton(
		IReadOnlyList<SourceQuatInterpDriverFact> facts, double modelScale)
	{
		if (!double.IsFinite(modelScale) || modelScale <= 0 || modelScale > 10)
			throw new ArgumentOutOfRangeException(nameof(modelScale));
		foreach (var fact in facts)
		{
			if (fact.RuntimeControlBind is not { Length: 4 })
				throw new InvalidDataException($"Single VRD {fact.BoneName} has no canonical shipped control bind; rebuild the model.");
			if (fact.BoneName.StartsWith("<") || fact.ParentName.StartsWith("<") || fact.ControlName.StartsWith("<"))
				throw new InvalidDataException(
					$"driver 骨 {fact.BoneName} 的名字三方未解析（{fact.ParentName}/{fact.ControlName}），不能写出 rig。");
		}

		return ScalePositions(facts, Retarget.RetargetConstants.InchesToMetres * modelScale);
	}

	private static IReadOnlyList<SourceQuatInterpDriverFact> ScalePositions(
		IReadOnlyList<SourceQuatInterpDriverFact> facts, double scale)
		=> facts.Select(fact => fact with
		{
			WorldPosition = fact.WorldPosition * scale,
			Triggers = fact.Triggers
				.Select(trigger => trigger with { Position = ScaleVector(trigger.Position, scale) })
				.ToArray(),
		}).ToArray();

	private static float[] ScaleVector(float[] value, double scale) =>
		[(float)(value[0] * scale), (float)(value[1] * scale), (float)(value[2] * scale)];

	/// <summary>
	/// 写出 driver rig 文件（**烘焙后**的 v2 规则）。没有 driver 骨时**不写**并返回 <c>null</c>——
	/// 与弹簧 rig 同一口径：空文件会让 embed 走"有 driver"分支，制造一条读不出内容的记录。
	/// </summary>
	public static string? Write(string directory, IReadOnlyList<SourceQuatInterpDriverFact> facts)
	{
		ArgumentException.ThrowIfNullOrWhiteSpace(directory);
		ArgumentNullException.ThrowIfNull(facts);
		if (facts.Count == 0)
			return null;

		var path = Path.Combine(directory, FileName);
		var single = facts.Any(f => f.RuntimeControlBind is not null);
		File.WriteAllBytes(path, PhysBoneDriverRig.Serialize(PhysBoneDriverRig.Bake(facts),
			single ? PhysBoneDriverRig.SingleVersion : PhysBoneDriverRig.Version));
		return path;
	}

	/// <summary>
	/// 在 mod 目录的几个约定位置找 driver rig 文件，找不到返回 <c>null</c>。
	/// 顺序与 <see cref="PhysBoneRigSidecar.Locate"/> 一致：根 → <c>vpk2patch/</c> → <c>Overwrite/</c>。
	/// </summary>
	public static string? Locate(string modDirectory)
	{
		ArgumentException.ThrowIfNullOrWhiteSpace(modDirectory);
		foreach (var directory in new[]
		{
			modDirectory,
			Path.Combine(modDirectory, "vpk2patch"),
			Path.Combine(modDirectory, "Overwrite"),
		})
		{
			var path = Path.Combine(directory, FileName);
			if (File.Exists(path))
				return path;
		}

		return null;
	}

	/// <summary>读出来并校验 magic；不是 driver rig 就返回 <c>null</c>（宁可少嵌一条记录，也不嵌坏数据）。</summary>
	public static byte[]? TryRead(string path)
	{
		if (string.IsNullOrWhiteSpace(path) || !File.Exists(path))
			return null;

		var bytes = File.ReadAllBytes(path);
		if (bytes.Length < 8 || !bytes.AsSpan(0, 8).SequenceEqual(PhysBoneDriverRig.Magic))
			return null;
		return bytes;
	}
}

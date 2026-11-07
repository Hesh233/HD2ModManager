using HD2SourceModel;

namespace HD2SourceMigration.Retarget;

/// <summary>
/// 为 jiggle 骨分配的**合成骨**：它不属于 HD2 原生骨架，是这个 Unit 自己新开的节点。
/// <para>
/// 为什么要它：以前 jiggle 骨在重定向时被回退到最近的 HD2 骨（头发落 <c>head</c>、裙摆落 <c>hips</c>），
/// 顶点权重随之被合并，于是"头发是刚性的"。合成骨让这些顶点保留在<b>自己的骨</b>上，
/// 运行时就能驱动它们。
/// </para>
/// </summary>
/// <param name="Name">节点名 = 源骨显示名（如 <c>source_extra_72</c>）；运行时按这个名字找节点。</param>
/// <param name="NameHash"><see cref="Hd2NameHash.Of"/> 算出的骨名哈希（写进 TransformInfo.NameHashes）。</param>
/// <param name="ParentIndex">父节点下标；可能是另一根合成骨（链套链）。</param>
/// <param name="WorldOrigin">对齐后的源关节位置（HD2 世界空间，米）。局部旋转按契约取单位阵。</param>
/// <param name="AnchorIndex">
/// **顶点烘焙**时该用的原生骨下标（= 插骨之前这根 jiggle 骨会落到的 HD2 骨，例如 <c>head</c>）。
/// <para>
/// 为什么必须有它：<c>SkinAll</c> 按骨下标去 `_deform` 里取形变矩阵，而合成骨没有条目，
/// 查不到就退回 <see cref="Mat4.Identity"/> —— 这些顶点会**完全绕开锚点的姿态**（A-pose、上臂缩放、头部缩放…），
/// 与相邻顶点错开，网格上就是一道折痕。2026-10-31 实测：Lilium 有 24.3% 顶点位移，最大 1.42 m。
/// </para>
/// </param>
public sealed record RetargetExtraBone(
	string Name,
	uint NameHash,
	int ParentIndex,
	Vec3 WorldOrigin,
	int AnchorIndex = -1);

public sealed partial class Retargeter
{
	/// <summary>
	/// 给每根**物理骨**（jiggle 弹簧骨 + QuatInterp driver 骨）分配合成骨，并产出
	/// "源骨下标 → 合成节点下标"的**权重目标表**与 driver 源骨清单。
	/// <para>
	/// ⚠️ **不改动 <paramref name="resolved"/> 本身**。曾经的实现直接把 jiggle 骨改写成合成骨下标，
	/// 结果几何变了：`SkinAll` 在 `_deform` 里查不到合成骨 → 退回单位矩阵，这些顶点绕开了
	/// A-pose/缩放等全部姿态处理（实测 Lilium 24.3% 顶点位移、最大 1.42 m，网格上是一道折痕）。
	/// 现在 `resolved` 保持"插骨之前"的答案，几何与不插骨时**逐位相同**，
	/// 只有写权重那一层（<c>RetargetedMeshBuilder</c>）按本表把目标换成合成节点。
	/// </para>
	/// <para>
	/// 2026-11-07：QuatInterp driver 骨（VRD 的姿态驱动半边）加入同一套 extras 机制——
	/// Snap 塌缩路线（单骨架）里它们不是独立节点，必须合成；手腕/裙骨自身携带的顶点
	/// （实测 handl 40、handr 57 个）也要跟到合成节点上，否则 driver 旋转没有视觉效果。
	/// </para>
	/// </summary>
	private (List<RetargetExtraBone> Extras, Dictionary<int, int> WeightTargets, List<SourceBone> DriverBones)
		CollectPhysicsBones(IReadOnlyDictionary<int, int> resolved)
	{
		var extras = new List<RetargetExtraBone>();
		var targets = new Dictionary<int, int>();
		if (!_options.IncludeJiggleBones)
			return (extras, targets, new List<SourceBone>());

		// 同一张 scratch 贯穿两类物理骨的规划：先写进的改写是后规划者的父级答案。
		return PlanPhysicsExtras(_model.Bones, resolved, _rig.Bones.Count, AlignedSourceJoint);
	}

	internal static (List<RetargetExtraBone> Extras, Dictionary<int, int> WeightTargets, List<SourceBone> DriverBones)
		PlanPhysicsExtras(IReadOnlyList<SourceBone> bones, IReadOnlyDictionary<int, int> resolved,
			int nativeCount, Func<int, Vec3> jointOf)
	{
		var extras = new List<RetargetExtraBone>();
		var targets = new Dictionary<int, int>();
		var scratch = new Dictionary<int, int>(resolved);

		// ---- ① 先规划 QuatInterp driver 骨（VRD 姿态驱动）------------------
		// ⚠️ 顺序是正确性的关键：裙摆 jiggle 链的父 = 裙骨 BL1（driver）。driver 先规划，
		// scratch 里 resolved[BL1] 才会指向 BL1 的**合成节点**，后规划 的裙链根才能
		// 挂到 driver 节点下——挂到回退骨（hips）上，driver 转动时链条就不跟随
		// （2026-11-07 实测："VRD 骨骼有变化，但子骨骼没有相应抬起"就是这个次序错误）。
		var driverBones = bones
			.Where(bone => bone.QuatInterp is not null)
			.OrderBy(bone => bone.Index)
			.ToList();
		extras.AddRange(PlanPhysicsBones(driverBones, scratch, nativeCount, jointOf));

		// ---- ② 再规划 jiggle 弹簧骨：链根父=driver extras（①已就位）----------
		extras.AddRange(PlanJiggleBones(bones, scratch, checked(nativeCount + extras.Count), jointOf));

		// ---- ③ 收割权重目标：所有 ≥ 原生骨数的改写（jiggle 与 driver 一张表）----
		foreach (var (sourceIndex, target) in scratch)
			if (target >= nativeCount)
				targets[sourceIndex] = target;

		// Validate semantic identity, not merely in-range indices (both batches used to overlap).
		foreach (var bone in bones.Where(b => targets.ContainsKey(b.Index)))
		{
			var slot = targets[bone.Index] - nativeCount;
			if (slot < 0 || slot >= extras.Count || extras[slot].Name != bone.DisplayName)
				throw new InvalidDataException($"Physics weight target for {bone.DisplayName} is not its own node.");
			if (extras[slot].ParentIndex >= nativeCount + slot)
				throw new InvalidDataException($"Physics parent for {bone.DisplayName} is not topologically ordered.");
		}
		return (extras, targets, driverBones);
	}

	/// <summary>
	/// 纯逻辑版：给定源骨表、已解析的映射、合成骨起始下标、以及"源骨下标 → 关节位置"的取法，
	/// 产出合成骨清单并就地改写 <paramref name="resolved"/>。
	/// <para>
	/// 顺序必须<b>父→子</b>：锚点本身也可能是 jiggle 骨（这套资产里实测有 6 条这样的"链套链"）。
	/// 这里用"反复扫到不动为止"做拓扑排序，而不是假设"源骨下标递增"—— 那个假设在别的模型上不一定成立。
	/// </para>
	/// <para>
	/// 合成骨下标从 <paramref name="baseCount"/> 往后排，因此**不会动到任何原生下标**；
	/// 上层只要按顺序把节点追加到 TransformInfo 即可。
	/// </para>
	/// </summary>
	public static List<RetargetExtraBone> PlanJiggleBones(
		IReadOnlyList<SourceBone> bones,
		Dictionary<int, int> resolved,
		int baseCount,
		Func<int, Vec3> jointOf)
	{
		var extras = new List<RetargetExtraBone>();
		var jiggle = bones.Where(bone => bone.Jiggle is not null).OrderBy(bone => bone.Index).ToList();
		if (jiggle.Count == 0)
			return extras;

		var pending = new HashSet<int>(jiggle.Select(bone => bone.Index));
		var assigned = new Dictionary<int, int>();   // 源 jiggle 下标 → 合成骨下标

		var progress = true;
		while (pending.Count > 0 && progress)
		{
			progress = false;
			foreach (var bone in jiggle)
			{
				if (!pending.Contains(bone.Index))
					continue;

				// 父必须先有答案：要么是已映射的原生骨，要么是已经分配好的合成骨。
				var parent = bone.ParentIndex;
				if (parent >= 0 && pending.Contains(parent))
					continue;

				int parentIndex;
				if (parent >= 0 && assigned.TryGetValue(parent, out var chainParent))
					parentIndex = chainParent;
				else if (parent >= 0 && resolved.TryGetValue(parent, out var nativeParent))
					parentIndex = nativeParent;
				else
					continue;   // 父既没映射也不是 jiggle：这一轮先跳过

				var index = baseCount + extras.Count;
				// **先取再改**：此刻 resolved[bone.Index] 还是"插骨之前它会落到的原生骨"（如 head），
				// 那就是这类顶点在烘焙时该用的形变来源（见 RetargetExtraBone.AnchorIndex 的说明）。
				var anchorIndex = resolved.TryGetValue(bone.Index, out var fallback) ? fallback : -1;
				extras.Add(new RetargetExtraBone(
					bone.DisplayName,
					Hd2NameHash.Of(bone.DisplayName),
					parentIndex,
					jointOf(bone.Index),
					anchorIndex));
				assigned[bone.Index] = index;
				resolved[bone.Index] = index;
				pending.Remove(bone.Index);
				progress = true;
			}
		}

		return extras;
	}

	/// <summary>
	/// QuatInterp driver 骨的合成骨计划：与 <see cref="PlanJiggleBones"/> 同一套拓扑与契约，
	/// 只是入选条件换成 <c>QuatInterp != null</c>（由调用方传入预筛好的 driver 骨表）。
	/// <para>
	/// 为什么不并成一个函数：jiggle 版是公开 API 且有既有测试锚定"只认 jiggle"的行为；
	/// driver 版的存在让两条物理骨共用 extras 机制而互不改变对方的既有输出。
	/// </para>
	/// </summary>
	public static List<RetargetExtraBone> PlanPhysicsBones(
		IReadOnlyList<SourceBone> driverBones,
		Dictionary<int, int> resolved,
		int baseCount,
		Func<int, Vec3> jointOf)
	{
		var extras = new List<RetargetExtraBone>();
		if (driverBones.Count == 0)
			return extras;

		var pending = new HashSet<int>(driverBones.Select(bone => bone.Index));
		var assigned = new Dictionary<int, int>();   // 源 driver 下标 → 合成骨下标

		var progress = true;
		while (pending.Count > 0 && progress)
		{
			progress = false;
			foreach (var bone in driverBones)
			{
				if (!pending.Contains(bone.Index))
					continue;

				var parent = bone.ParentIndex;
				if (parent >= 0 && pending.Contains(parent))
					continue;

				int parentIndex;
				if (parent >= 0 && assigned.TryGetValue(parent, out var chainParent))
					parentIndex = chainParent;
				else if (parent >= 0 && resolved.TryGetValue(parent, out var nativeParent))
					parentIndex = nativeParent;
				else
					continue;

				var index = baseCount + extras.Count;
				var anchorIndex = resolved.TryGetValue(bone.Index, out var fallback) ? fallback : -1;
				extras.Add(new RetargetExtraBone(
					bone.DisplayName,
					Hd2NameHash.Of(bone.DisplayName),
					parentIndex,
					jointOf(bone.Index),
					anchorIndex));
				assigned[bone.Index] = index;
				resolved[bone.Index] = index;
				pending.Remove(bone.Index);
				progress = true;
			}
		}

		return extras;
	}

	/// <summary>
	/// 链根的**锚点名**：源父骨显示名 → 它回退到的 HD2 原生骨名。
	/// <para>
	/// 为什么需要这一步：容器（<c>HD2SRG01</c>）里的每根骨存的是<b>源侧</b>父骨名，
	/// 运行时靠它把链根挂到 HD2 的骨名表上。但源骨架里有一批骨在 HD2 侧根本不存在
	/// （无名骨 <c>source_extra_90</c>、以及 <c>UN_Skirt_R_02</c> 这类非 Biped 命名），
	/// 运行时的映射表只认 ValveBiped，查不到就退化成"把源骨名当 HD2 骨名查"——必然查不到，
	/// 于是整条链记「缺锚点」被跳过。实测一份裙子上 25 条链死 5 条。
	/// </para>
	/// <para>
	/// 这里给出的正是<b>重定向当时</b>已经算出来的答案：<c>resolved[父骨]</c> 就是那根骨
	/// 回退到的 HD2 原生骨下标。把它的<b>名字</b>写进容器的 <c>parentName</c>，
	/// 运行时的回退分支立刻就能解析——不动协议、不动运行时、旧 rig 也照样能用。
	/// </para>
	/// <para>
	/// 父骨本身是 jiggle 骨的（链套链）不在此列：那种情况下运行时按父骨下标认链，
	/// 根本不需要锚点，写进去反而会把它当成"挂到别的骨上"。
	/// <b>2026-11-07：父骨是 QuatInterp driver 骨的同样跳过</b>——driver 骨本身会合成
	/// extras 节点（名字=源显示名），链根的 parentName 保持源名即可直接解析到 driver 节点，
	/// 裙摆链因此跟随 driver 的姿态修正。
	/// </para>
	/// </summary>
	/// <param name="bones">源骨表（下标即骨下标）。</param>
	/// <param name="resolved">**插合成骨之前**的源骨 → HD2 骨映射。</param>
	/// <param name="hd2Bones">HD2 avatar 骨架，用来把下标换回名字。</param>
	public static Dictionary<string, string> PlanJiggleAnchors(
		IReadOnlyList<SourceBone> bones,
		IReadOnlyDictionary<int, int> resolved,
		IReadOnlyList<Hd2RigBone> hd2Bones)
	{
		ArgumentNullException.ThrowIfNull(bones);
		ArgumentNullException.ThrowIfNull(resolved);
		ArgumentNullException.ThrowIfNull(hd2Bones);

		var anchors = new Dictionary<string, string>(StringComparer.Ordinal);
		foreach (var bone in bones)
		{
			if (bone.Jiggle is null)
				continue;

			var parent = bone.ParentIndex;
			if (parent < 0 || parent >= bones.Count)
				continue;                       // 根骨：没有可挂的父骨
			if (bones[parent].Jiggle is not null || bones[parent].QuatInterp is not null)
				continue;                       // 链套链 / 父是 driver 骨：parentName 保持源名=合成节点名

			if (!resolved.TryGetValue(parent, out var nativeIndex))
				continue;                       // 父骨连回退都没落到 HD2 骨上
			if (nativeIndex < 0 || nativeIndex >= hd2Bones.Count)
				continue;

			var name = hd2Bones[nativeIndex].Name;
			if (string.IsNullOrEmpty(name))
				continue;                       // HD2 侧这根骨也没名字，写进去同样解析不了

			anchors[bones[parent].DisplayName] = name!;
		}

		return anchors;
	}
}

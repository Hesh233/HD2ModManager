namespace HD2SourceModel.Tests;

/// <summary>
/// 真实 VRD 数据不变量（test01 / test07）：对**全部 16 根** QuatInterp driver 骨钉死两个
/// 帧语义锚点——这是单骨架（Snap 塌缩）路线烘焙正确性的数据层依据。
/// <para>
/// ① <c>CS0（控制骨原始局部 bind）≈ rule0 的 trigger</c>——bind 控制姿态落在第一条
/// 规则的触发区中心（作者容差内：handl 精确 1.000，wrist_L 0.988）。
/// ② <c>R_bd（driver 原始局部 bind）≈ rule0 的 rotation</c>——bind 处零校正。
/// ③ 全部触发与输出四元数已单位化。
/// 这三个锚点共同保证：烘焙后的 D 匹配在"转换后 bind"处收敛到 rule0（零校正），
/// 随姿态偏离按作者规则插值。任何帧约定改动（Mat4/四元数/局部 bind 推导）破坏语义时，
/// 这组测试会以具体 dot 值失败。
/// </para>
/// </summary>
public sealed class RealQuatInterpInvariantTests
{
	private static string? ResolveVpk(string fileName)
	{
		var dir = new DirectoryInfo(AppContext.BaseDirectory);
		while (dir is not null)
		{
			var candidate = Path.Combine(dir.FullName, "testVPK", fileName);
			if (File.Exists(candidate))
				return candidate;
			dir = dir.Parent;
		}

		return null;
	}

	public static IEnumerable<object[]> DriverVpks()
	{
		foreach (var name in new[] { "test01.vpk", "test07.vpk" })
		{
			var path = ResolveVpk(name);
			if (path is not null)
				yield return new object[] { path, name };
		}
	}

	[Theory]
	[MemberData(nameof(DriverVpks))]
	public void RealDrivers_SatisfyBindAndUnitInvariants(string vpkPath, string label)
	{
		using var archive = VpkArchive.Open(vpkPath);
		var modelStem = label.Contains("test01") ? "survivor_namvet" : "survivor_gambler";
		var files = SourceModelLocator.Resolve(archive, modelStem);
		var model = SourceModelReader.Read(archive.Read(files.Mdl));

		var facts = SourceModelInspector.QuatInterpFacts(model);
		Assert.Equal(8, facts.Count);

		foreach (var fact in facts)
		{
			Assert.True(fact.Triggers.Count >= 3, $"{fact.BoneName}: 规则数 {fact.Triggers.Count}");
			var first = fact.Triggers[0];

			// ① CS0 ≈ rule0.trigger（作者把 bind 控制姿态作为第一条规则的触发点）。
			var cs0Dot = Math.Abs(Quat.Dot(fact.ControlBindLocal, first.Trigger));
			Assert.True(cs0Dot > 0.98,
				$"{label}/{fact.BoneName}: |dot(CS0, trigger0)| = {cs0Dot:0.000}");

			// ② R_bd ≈ rule0.rotation（bind 处零校正）。
			var driverLocal = SourceModelInspector.LocalBindRotation(model, fact.BoneIndex);
			var bdDot = Math.Abs(Quat.Dot(driverLocal, first.Rotation));
			Assert.True(bdDot > 0.98,
				$"{label}/{fact.BoneName}: |dot(R_bd, rotation0)| = {bdDot:0.000}");

			// ③ 全部四元数单位化。
			foreach (var trigger in fact.Triggers)
			{
				var triggerNorm = Math.Sqrt(trigger.Trigger.Sum(v => (double)v * v));
				var rotationNorm = Math.Sqrt(trigger.Rotation.Sum(v => (double)v * v));
				Assert.True(Math.Abs(triggerNorm - 1) < 1e-3,
					$"{label}/{fact.BoneName}: |trigger| = {triggerNorm:0.000}");
				Assert.True(Math.Abs(rotationNorm - 1) < 1e-3,
					$"{label}/{fact.BoneName}: |rotation| = {rotationNorm:0.000}");
			}
		}
	}

	[Theory]
	[MemberData(nameof(DriverVpks))]
	public void RealDrivers_BakedRulesStayUnitAndBindRuleBecomesIdentity(string vpkPath, string label)
	{
		using var archive = VpkArchive.Open(vpkPath);
		var modelStem = label.Contains("test01") ? "survivor_namvet" : "survivor_gambler";
		var files = SourceModelLocator.Resolve(archive, modelStem);
		var model = SourceModelReader.Read(archive.Read(files.Mdl));

		var baked = PhysBoneDriverRig.Bake(SourceModelInspector.QuatInterpFacts(model));
		Assert.Equal(8, baked.Count);

		foreach (var fact in baked)
		{
			// 烘焙不改 invTolerance 与规则数；四元数仍然单位化（共轭与归一化保持长度）。
			foreach (var trigger in fact.Triggers)
			{
				var triggerNorm = Math.Sqrt(trigger.Trigger.Sum(v => (double)v * v));
				var rotationNorm = Math.Sqrt(trigger.Rotation.Sum(v => (double)v * v));
				Assert.True(Math.Abs(triggerNorm - 1) < 1e-3,
					$"{label}/{fact.BoneName}: 烘焙后 |trigger| = {triggerNorm:0.000}");
				Assert.True(Math.Abs(rotationNorm - 1) < 1e-3,
					$"{label}/{fact.BoneName}: 烘焙后 |rotation| = {rotationNorm:0.000}");
			}

			// rule0 的 delta：在"CS0 == trigger0"精确成立的骨上必须退化为恒等（零校正）。
			var first = fact.Triggers[0];
			var bindMatch = Math.Abs(Quat.Dot(fact.ControlBindLocal,
				SourceModelInspector.QuatInterpFacts(model)
					.First(f => f.BoneName == fact.BoneName).Triggers[0].Trigger));
			if (bindMatch > 0.999)
			{
				Assert.True(first.Rotation[3] > 0.999 && Math.Abs(first.Rotation[0]) < 0.01
					&& Math.Abs(first.Rotation[1]) < 0.01 && Math.Abs(first.Rotation[2]) < 0.01,
					$"{label}/{fact.BoneName}: bind 规则的 delta 未退化为恒等");
			}
		}
	}
}

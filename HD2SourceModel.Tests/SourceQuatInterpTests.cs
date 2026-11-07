using System.Buffers.Binary;
using System.Text;

namespace HD2SourceModel.Tests;

/// <summary>
/// QuatInterp（VRD driver 骨，proctype=2）读取与序列化测试。
/// <para>
/// 布局参考：MDL 侧与 <c>tools/prepare_native_v11.py</c> 的提取代码一致（该代码在 v11 轮
/// 实机验证过 test01 的两条手腕规则）；序列化侧是 <c>HD2DRV01</c> 的新布局，
/// lua 读取侧按同一份布局实现。
/// </para>
/// </summary>
public class SourceQuatInterpTests
{
	private static float[] Rule(
		float invTolerance,
		float tx, float ty, float tz, float tw,
		float px, float py, float pz,
		float rx, float ry, float rz, float rw) =>
	[invTolerance, tx, ty, tz, tw, px, py, pz, rx, ry, rz, rw];

	private static SourceFormatFixtures.BodyPartSpec[] OneBodyPart() =>
	[new SourceFormatFixtures.BodyPartSpec("body", [new SourceFormatFixtures.ModelSpec("model", 0, 0, [])])];

	[Fact]
	public void Read_ParsesQuatInterpControlRulesAndValues()
	{
		// 规则取值约定：第 k 个 float = k + 0.5，逐项断言。
		var rule = Rule(0.6366f, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11)
			.Select((value, k) => k == 0 ? 0.6366f : k + 0.5f).ToArray();
		var mdl = SourceFormatFixtures.BuildMdl(
			"survivor_test",
			49,
			[
				new SourceFormatFixtures.BoneSpec("ValveBiped.Bip01_L_Forearm", -1),
				new SourceFormatFixtures.BoneSpec("ValveBiped.Bip01_L_Hand", 0),
				new SourceFormatFixtures.BoneSpec("ValveBiped.handl", 0, QuatInterpControl: 1, QuatInterpRules: [rule]),
			],
			OneBodyPart());

		var document = SourceModelReader.Read(mdl);

		var driver = document.Bones[2];
		Assert.NotNull(driver.QuatInterp);
		Assert.Equal(1, driver.QuatInterp!.ControlIndex);
		var trigger = Assert.Single(driver.QuatInterp.Triggers);
		Assert.Equal(0.6366f, trigger.InvTolerance, 6);
		Assert.Equal(new[] { 1.5f, 2.5f, 3.5f, 4.5f }, trigger.Trigger);
		Assert.Equal(new[] { 5.5f, 6.5f, 7.5f }, trigger.Position);
		Assert.Equal(new[] { 8.5f, 9.5f, 10.5f, 11.5f }, trigger.Rotation);
		Assert.Empty(document.Diagnostics);
	}

	[Fact]
	public void Read_JiggleAndQuatInterpCoexistInTheSameBoneArray()
	{
		var rule = Rule(1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 1);
		var mdl = SourceFormatFixtures.BuildMdl(
			"x",
			49,
			[
				new SourceFormatFixtures.BoneSpec("j", 0, JiggleFlags: 0x31),
				new SourceFormatFixtures.BoneSpec("d", 0, QuatInterpControl: 0, QuatInterpRules: [rule, rule]),
			],
			OneBodyPart());

		var document = SourceModelReader.Read(mdl);

		Assert.NotNull(document.Bones[0].Jiggle);
		Assert.Null(document.Bones[0].QuatInterp);
		Assert.Null(document.Bones[1].Jiggle);
		Assert.Equal(2, document.Bones[1].QuatInterp!.Triggers.Count);
		Assert.Empty(document.Diagnostics);
	}

	[Fact]
	public void Read_ReportsOutOfRangeQuatInterpBlocksAsDiagnostics()
	{
		// procindex 指向文件末尾之外：读取器必须记诊断并返回 null，不能抛。
		var mdl = SourceFormatFixtures.BuildMdl(
			"x", 49,
			[new SourceFormatFixtures.BoneSpec("d", -1, QuatInterpControl: 0, QuatInterpRules: [Rule(1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 1)])],
			OneBodyPart());
		// 把 procindex 改写成越界值（+100000）。
		var entry = SourceFormatFixtures.MdlHeaderSize;
		BinaryPrimitives.WriteInt32LittleEndian(
			mdl.AsSpan(entry + SourceFormatFixtures.MdlBoneProcIndexOffset), 100000);

		var document = SourceModelReader.Read(mdl);

		Assert.Null(document.Bones[0].QuatInterp);
		Assert.Contains(document.Diagnostics, diagnostic => diagnostic.Code == "QuatInterpParametersOutOfRange");
	}

	[Fact]
	public void Read_ReportsZeroRuleCountAsDiagnostic()
	{
		// 规则数为 0：engine 侧不会出现，但坏数据必须显式拒绝而不是造出空规则表。
		var mdl = SourceFormatFixtures.BuildMdl(
			"x", 49,
			[new SourceFormatFixtures.BoneSpec("d", -1, QuatInterpControl: 0, QuatInterpRules: [])],
			OneBodyPart());

		var document = SourceModelReader.Read(mdl);

		Assert.Null(document.Bones[0].QuatInterp);
		Assert.Contains(document.Diagnostics, diagnostic => diagnostic.Code == "QuatInterpRuleCountInvalid");
	}

	[Fact]
	public void Read_ReportsUnsupportedProcTypesOnce()
	{
		var mdl = SourceFormatFixtures.BuildMdl(
			"x", 49,
			[
				new SourceFormatFixtures.BoneSpec("a", -1, RawProcType: 1),
				new SourceFormatFixtures.BoneSpec("b", 0, RawProcType: 1),
				new SourceFormatFixtures.BoneSpec("c", 0, RawProcType: 3),
			],
			OneBodyPart());

		var document = SourceModelReader.Read(mdl);

		Assert.Null(document.Bones[0].QuatInterp);
		Assert.Equal(2, document.Diagnostics.Count(diagnostic => diagnostic.Code == "UnsupportedProceduralBone"));
	}

	[Fact]
	public void Inspector_QuatInterpFactsCarryIdentityControlAndTriggers()
	{
		var rule = Rule(0.6366f, 0, 0, 0, 1, 1, 2, 3, 0, 0, 0, 1);
		var mdl = SourceFormatFixtures.BuildMdl(
			"survivor_test",
			49,
			[
				new SourceFormatFixtures.BoneSpec("ValveBiped.Bip01_L_Forearm", -1),
				new SourceFormatFixtures.BoneSpec("ValveBiped.Bip01_L_Hand", 0),
				new SourceFormatFixtures.BoneSpec("ValveBiped.handl", 0, QuatInterpControl: 1, QuatInterpRules: [rule]),
			],
			OneBodyPart());

		var document = SourceModelReader.Read(mdl);
		var facts = SourceModelInspector.QuatInterpFacts(document);

		var fact = Assert.Single(facts);
		Assert.Equal("ValveBiped.handl", fact.BoneName);
		Assert.Equal("ValveBiped.Bip01_L_Forearm", fact.ParentName);
		Assert.Equal("ValveBiped.Bip01_L_Hand", fact.ControlName);
		Assert.Equal(0, fact.WorldPosition.X, 6);
		Assert.Equal(0.6366f, fact.Triggers[0].InvTolerance, 6);
	}

	[Fact]
	public void DriverRig_RoundTripsThroughTheDocumentedLayout()
	{
		var rule = Rule(0.6366f, 0.5f, 0.5f, 0.5f, 0.5f, 0.1f, 0.2f, 0.3f, 0, 0, 0, 1);
		var facts = new[]
		{
			new SourceQuatInterpDriverFact(64, "handl", "l_forearm", "l_hand",
				new Vec3(0.1, 0.2, 0.3), [new SourceQuatInterpTrigger(0.6366f, [0.5f, 0.5f, 0.5f, 0.5f], [0.1f, 0.2f, 0.3f], [0, 0, 0, 1])],
				Quat.Identity, Quat.Identity),
			new SourceQuatInterpDriverFact(77, "BL1", "pelvis", "l_thigh",
				new Vec3(0, 0, 0), [new SourceQuatInterpTrigger(1.2732f, [0, 1, 0, 0], [0, 0, 0], [0, 0, 0, 1])],
				Quat.Identity, Quat.Identity),
		};

		var bytes = PhysBoneDriverRig.Serialize(PhysBoneDriverRig.Bake(facts));

		Assert.Equal("HD2DRV01", Encoding.ASCII.GetString(bytes, 0, 8));
		Assert.Equal(2u, BitConverter.ToUInt32(bytes, 8));
		Assert.Equal(2u, BitConverter.ToUInt32(bytes, 12));
		var nameTableOffset = (int)BitConverter.ToUInt32(bytes, 16);
		var nameTableSize = (int)BitConverter.ToUInt32(bytes, 20);
		// 总长 = 头 32 + 记录区（固定 28×2 + 规则 2×48）+ 名字表。
		Assert.Equal(nameTableOffset + nameTableSize, bytes.Length);

		// 第一条记录：名字偏移解析 + 规则字段逐项核对。
		var nameAt = nameTableOffset + (int)BitConverter.ToUInt32(bytes, 32);
		Assert.Equal("handl", Encoding.ASCII.GetString(bytes, nameAt, 5));
		Assert.Equal(1u, BitConverter.ToUInt32(bytes, 32 + 12));   // 规则数
		Assert.Equal(0.6366f, BitConverter.ToSingle(bytes, 32 + 28), 6);
		Assert.Equal(0.5f, BitConverter.ToSingle(bytes, 32 + 28 + 4), 6);   // trigger.x
		Assert.Equal(0.3f, BitConverter.ToSingle(bytes, 32 + 28 + 20 + 8), 6);  // position.z
		Assert.Equal(0f, BitConverter.ToSingle(bytes, 32 + 28 + 32), 6);    // rotation.x
		Assert.Equal(1f, BitConverter.ToSingle(bytes, 32 + 28 + 32 + 12), 6);  // rotation.w

		// 第二条记录紧跟其后：28 + 48 = 76 字节处。
		var secondAt = 32 + 28 + 48;
		var secondNameAt = nameTableOffset + (int)BitConverter.ToUInt32(bytes, secondAt);
		Assert.Equal("BL1", Encoding.ASCII.GetString(bytes, secondNameAt, 3));
		Assert.Equal(1.2732f, BitConverter.ToSingle(bytes, secondAt + 28), 6);
	}

	[Fact]
	public void DriverRig_EmptyFactListProducesHeaderOnly()
	{
		var bytes = PhysBoneDriverRig.Serialize([]);

		Assert.Equal(32, bytes.Length);
		Assert.Equal(0u, BitConverter.ToUInt32(bytes, 12));
	}
}

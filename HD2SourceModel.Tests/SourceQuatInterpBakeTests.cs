using System.Numerics;

namespace HD2SourceModel.Tests;

/// <summary>
/// QuatInterp v2 烘焙数学测试：帧共轭、bind 增量、以及"bind 处零校正"的核心不变量。
/// <para>
/// 这些不变量是单骨架（Snap 塌缩）路线正确性的全部依据——M_p 或 CS0 搞反方向时，
/// 这里的断言会以两倍校正角的方式失败。
/// </para>
/// </summary>
public class SourceQuatInterpBakeTests
{
	private static float[] Normalize(float x, float y, float z, float w)
	{
		var n = Math.Sqrt(x * x + y * y + z * z + w * w);
		return [(float)(x / n), (float)(y / n), (float)(z / n), (float)(w / n)];
	}

	private static float[] AxisAngle(float ax, float ay, float az, float degrees)
	{
		var rad = degrees * MathF.PI / 180f;
		var s = MathF.Sin(rad / 2);
		return Normalize(ax * s, ay * s, az * s, MathF.Cos(rad / 2));
	}

	private static float Dot(float[] a, float[] b) => Quat.Dot(a, b);

	[Fact]
	public void Bake_IdentityFrameAndBindMatch_ReproducesV1AbsoluteSemantics()
	{
		// native 路线：M_p=I、CS0=trigger[0]、R_bd=rule0.rotation。
		// 烘焙后按 D=I（bind 姿态）求值：C_auth = CS0 → 命中 rule0 → δ′=I → L = I·bindQ = bind。
		var cs0 = AxisAngle(0, 0, 1, 30);
		var bind = AxisAngle(1, 0, 0, 10);
		var other = AxisAngle(0, 1, 0, 45);
		var facts = new[]
		{
			new SourceQuatInterpDriverFact(1, "d", "p", "c", new Vec3(0, 0, 0),
				[
					new SourceQuatInterpTrigger(0.6366f, cs0, [0, 0, 0], bind),
					new SourceQuatInterpTrigger(0.6366f, other, [0, 0, 0], other),
				],
				cs0, Quat.Identity),
		};

		var baked = PhysBoneDriverRig.Bake(facts);

		// rule0 的烘焙 trigger = M_p (T_0 · CS0⁻¹) M_p⁻¹ = I（bind 处 D=I 精确命中）。
		var t0 = baked[0].Triggers[0].Trigger;
		Assert.Equal(1f, t0[3], 4);
		Assert.Equal(0f, t0[0], 4);
		// rule0 的烘焙 delta = M_p (bind · bind⁻¹) M_p⁻¹ = I。
		var r0 = baked[0].Triggers[0].Rotation;
		Assert.Equal(1f, r0[3], 4);
	}

	[Fact]
	public void Bake_WithFrameMapping_ConjugatesTriggersByTheFrame()
	{
		// M_p = 绕 Z 转 90°：T″ 必须是 T 的共轭（方向随帧旋转），模与 w 分量不变。
		var frame = AxisAngle(0, 0, 1, 90);
		var trigger = AxisAngle(0, 1, 0, 30);
		var facts = new[]
		{
			new SourceQuatInterpDriverFact(1, "d", "p", "c", new Vec3(0, 0, 0),
				[new SourceQuatInterpTrigger(0.6366f, trigger, [0, 0, 0], Quat.Identity)],
				Quat.Identity, frame),
		};

		var baked = PhysBoneDriverRig.Bake(facts);

		var expected = Quat.Conjugated(trigger, frame);
		var actual = baked[0].Triggers[0].Trigger;
		var dot = Math.Abs(Dot(expected, actual));
		Assert.True(dot > 0.9999, $"dot={dot}");
	}

	[Fact]
	public void Bake_DeltaIsBindRelative_ZeroAtTheBindRule()
	{
		// rotation[0] = bind 参考：烘焙后 rule0 的 delta 必须是恒等（bind 处零校正）。
		var bind = AxisAngle(1, 0, 0, 12);
		var frame = AxisAngle(0, 0, 1, 60);
		var corrected = Quat.Conjugated(AxisAngle(1, 0, 0, 40), frame); // 任意非 bind 输出
		var facts = new[]
		{
			new SourceQuatInterpDriverFact(1, "d", "p", "c", new Vec3(0, 0, 0),
				[
					new SourceQuatInterpTrigger(0.6366f, Quat.Identity, [0, 0, 0], bind),
					new SourceQuatInterpTrigger(0.6366f, Quat.Identity, [0, 0, 0], corrected),
				],
				Quat.Identity, frame),
		};

		var baked = PhysBoneDriverRig.Bake(facts);

		var r0 = baked[0].Triggers[0].Rotation;
		Assert.Equal(1f, r0[3], 4);   // δ0 = I（bind 处零校正）
		var r1 = baked[0].Triggers[1].Rotation;
		var expected1 = Quat.Conjugated(
			Quat.Multiply(corrected, Quat.Conjugate(bind)), frame);
		Assert.True(Math.Abs(Dot(expected1, r1)) > 0.9999, $"dot={Dot(expected1, r1)}");
	}

	[Fact]
	public void Bake_SkipsFactsWithoutRules()
	{
		var facts = new[]
		{
			new SourceQuatInterpDriverFact(1, "empty", "p", "c", new Vec3(0, 0, 0),
				[], Quat.Identity, Quat.Identity),
			new SourceQuatInterpDriverFact(2, "ok", "p", "c", new Vec3(0, 0, 0),
				[new SourceQuatInterpTrigger(1f, Quat.Identity, [0, 0, 0], Quat.Identity)],
				Quat.Identity, Quat.Identity),
		};

		var baked = PhysBoneDriverRig.Bake(facts);

		var fact = Assert.Single(baked);
		Assert.Equal("ok", fact.BoneName);
	}

	/// <summary>
	/// 旋转-四元数往返：Quat.FromRotationMatrix 与 System.Numerics 在同一约定下一致。
	/// （约定错位的症状是"绕同一轴角度相反"，这里用三个不同轴钉住。）
	/// </summary>
	[Theory]
	[InlineData(1, 0, 0, 33)]
	[InlineData(0, 1, 0, -47)]
	[InlineData(0, 0, 1, 71)]
	public void FromRotationMatrix_MatchesSystemNumerics(float ax, float ay, float az, float degrees)
	{
		var rad = degrees * MathF.PI / 180f;
		var axis = Vector3.Normalize(new Vector3(ax, ay, az));
		var reference = Quaternion.CreateFromAxisAngle(axis, rad);
		var m = Matrix4x4.CreateFromQuaternion(reference);
		// System.Numerics 是行向量约定（v' = v·M）：列向量约定的 R = 其 3x3 的转置。
		var q = Quat.FromRotationMatrix(m.M11, m.M21, m.M31, m.M12, m.M22, m.M32, m.M13, m.M23, m.M33);

		var dot = Math.Abs(
			q[0] * reference.X + q[1] * reference.Y + q[2] * reference.Z + q[3] * reference.W);
		Assert.True(dot > 0.99999, $"dot={dot}");
	}
}

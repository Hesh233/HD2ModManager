namespace HD2SourceModel;

/// <summary>
/// 单精度四元数的**纯数学**工具（xyzw 顺序），只服务 QuatInterp driver 骨的帧烘焙。
/// <para>
/// 为什么不用矩阵硬算：driver 的触发/输出都在四元数域里做半球对齐加权混合，
/// 烘焙（帧共轭 + bind 参考）也全在四元数域，矩阵只会多引进一层约定风险。
/// 约定与运行时 lua 完全一致：xyzw、右手系、旋转作用为 <c>v' = q · v · q*</c>。
/// </para>
/// </summary>
public static class Quat
{
	public static float[] Identity => [0f, 0f, 0f, 1f];

	/// <summary>从**列向量约定**的旋转 3x3（行主序平铺 m11..m33，见 <see cref="Mat4"/>）造四元数。</summary>
	public static float[] FromRotationMatrix(
		double m11, double m12, double m13,
		double m21, double m22, double m23,
		double m31, double m32, double m33)
	{
		var trace = m11 + m22 + m33;
		double x, y, z, w;
		if (trace > 0)
		{
			var s = Math.Sqrt(trace + 1) * 2;
			w = s / 4;
			x = (m32 - m23) / s;
			y = (m13 - m31) / s;
			z = (m21 - m12) / s;
		}
		else if (m11 > m22 && m11 > m33)
		{
			var s = Math.Sqrt(1 + m11 - m22 - m33) * 2;
			w = (m32 - m23) / s;
			x = s / 4;
			y = (m12 + m21) / s;
			z = (m13 + m31) / s;
		}
		else if (m22 > m33)
		{
			var s = Math.Sqrt(1 + m22 - m11 - m33) * 2;
			w = (m13 - m31) / s;
			x = (m12 + m21) / s;
			y = s / 4;
			z = (m23 + m32) / s;
		}
		else
		{
			var s = Math.Sqrt(1 + m33 - m11 - m22) * 2;
			w = (m21 - m12) / s;
			x = (m13 + m31) / s;
			y = (m23 + m32) / s;
			z = s / 4;
		}

		var length = Math.Sqrt(x * x + y * y + z * z + w * w);
		if (length < 1e-12)
			return Identity;
		return [(float)(x / length), (float)(y / length), (float)(z / length), (float)(w / length)];
	}

	public static float[] Multiply(float[] a, float[] b)
	{
		var (ax, ay, az, aw) = (a[0], a[1], a[2], a[3]);
		var (bx, by, bz, bw) = (b[0], b[1], b[2], b[3]);
		return [
			aw * bx + ax * bw + ay * bz - az * by,
			aw * by - ax * bz + ay * bw + az * bx,
			aw * bz + ax * by - ay * bx + az * bw,
			aw * bw - ax * bx - ay * by - az * bz,
		];
	}

	public static float[] Conjugate(float[] q) => [-q[0], -q[1], -q[2], q[3]];

	public static float Dot(float[] a, float[] b)
		=> a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3];

	/// <summary>归一化；长度退化时返回单位四元数（绝不输出 NaN）。</summary>
	public static float[] Normalized(float[] q)
	{
		var length = Math.Sqrt(q[0] * q[0] + q[1] * q[1] + q[2] * q[2] + q[3] * q[3]);
		if (length < 1e-12)
			return Identity;
		return [(float)(q[0] / length), (float)(q[1] / length), (float)(q[2] / length), (float)(q[3] / length)];
	}

	/// <summary>把旋转 R（四元数）按帧映射 M 共轭：R 在 M 目标帧下的表达 = M · R · M⁻¹。</summary>
	public static float[] Conjugated(float[] rotation, float[] frame)
		=> Normalized(Multiply(Multiply(frame, rotation), Conjugate(frame)));
}

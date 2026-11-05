from __future__ import annotations

from math import acos, atan2, cos, sin, sqrt


EPSILON = 1e-8


def vec_add(a, b):
    return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]


def vec_sub(a, b):
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def vec_mul(a, b):
    return [a[0] * b[0], a[1] * b[1], a[2] * b[2]]


def vec_div(a, b):
    result = []
    for component, divisor in zip(a, b):
        if abs(divisor) < EPSILON:
            raise ValueError("Cannot invert a transform with a zero scale component")
        result.append(component / divisor)
    return result


def vec_lerp(a, b, factor: float):
    return [a[i] + (b[i] - a[i]) * factor for i in range(3)]


def vec_close(a, b, tolerance: float = 1e-5) -> bool:
    return all(abs(a[i] - b[i]) <= tolerance for i in range(3))


def quat_normalize(q):
    length = sqrt(sum(component * component for component in q))
    if length < EPSILON:
        return [0.0, 0.0, 0.0, 1.0]
    return [component / length for component in q]


def quat_conjugate(q):
    return [-q[0], -q[1], -q[2], q[3]]


def quat_inverse(q):
    return quat_conjugate(quat_normalize(q))


def quat_multiply(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return [
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    ]


def quat_rotate(q, vector):
    q = quat_normalize(q)
    rotated = quat_multiply(
        quat_multiply(q, [vector[0], vector[1], vector[2], 0.0]),
        quat_conjugate(q),
    )
    return rotated[:3]


def quat_inverse_rotate(q, vector):
    return quat_rotate(quat_conjugate(quat_normalize(q)), vector)


def quat_slerp(a, b, factor: float):
    a = quat_normalize(a)
    b = quat_normalize(b)
    dot = sum(a[i] * b[i] for i in range(4))
    if dot < 0.0:
        b = [-component for component in b]
        dot = -dot
    if dot > 0.9995:
        return quat_normalize(
            [a[i] + (b[i] - a[i]) * factor for i in range(4)]
        )
    dot = max(-1.0, min(1.0, dot))
    angle = acos(dot)
    angle_sin = sin(angle)
    left = sin((1.0 - factor) * angle) / angle_sin
    right = sin(factor * angle) / angle_sin
    return [a[i] * left + b[i] * right for i in range(4)]


def quat_scale_angle(q, multiplier: float):
    """Scale a quaternion's shortest rotation angle while preserving its axis."""
    q = quat_normalize(q)
    if q[3] < 0.0:
        q = [-component for component in q]
    vector_length = sqrt(sum(component * component for component in q[:3]))
    if vector_length < EPSILON:
        return q
    angle = 2.0 * atan2(vector_length, q[3])
    scaled_half_angle = angle * float(multiplier) * 0.5
    axis = [component / vector_length for component in q[:3]]
    sine = sin(scaled_half_angle)
    return quat_normalize(
        [axis[0] * sine, axis[1] * sine, axis[2] * sine, cos(scaled_half_angle)]
    )


def matrix3_columns_to_quaternion(columns):
    x, y, z = columns
    m00, m01, m02 = x[0], y[0], z[0]
    m10, m11, m12 = x[1], y[1], z[1]
    m20, m21, m22 = x[2], y[2], z[2]
    trace = m00 + m11 + m22
    if trace > 0.0:
        s = sqrt(trace + 1.0) * 2.0
        q = [(m21 - m12) / s, (m02 - m20) / s, (m10 - m01) / s, 0.25 * s]
    elif m00 > m11 and m00 > m22:
        s = sqrt(1.0 + m00 - m11 - m22) * 2.0
        q = [0.25 * s, (m01 + m10) / s, (m02 + m20) / s, (m21 - m12) / s]
    elif m11 > m22:
        s = sqrt(1.0 + m11 - m00 - m22) * 2.0
        q = [(m01 + m10) / s, 0.25 * s, (m12 + m21) / s, (m02 - m20) / s]
    else:
        s = sqrt(1.0 + m22 - m00 - m11) * 2.0
        q = [(m02 + m20) / s, (m12 + m21) / s, 0.25 * s, (m10 - m01) / s]
    return quat_normalize(q)

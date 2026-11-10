"""driver 热路径假引擎测试：attach 解析 -> update_drivers 求解/写入/去重 -> release 回写 bind。

lupa 陷阱：python 函数直接赋给 lua 表后 type 是 userdata 不是 function——
compat 的能力闸（probe_fast_write 等）全靠 type=="function"，所以每个 python 回调
都包成真 lua 函数（lua_fn），并把 Vector3/Quaternion 造成可调用表。
"""
import math
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.append(str(ROOT.parents[1]))
from lupa.lua51 import LuaRuntime

os.chdir(ROOT)
lua = LuaRuntime(unpack_returned_tuples=True)
compat = lua.execute((ROOT / "HD2PhysBoneCompat/src/physbone_compat.lua").read_text(encoding="utf-8-sig"))
assert compat.version == "1.3.1"

failures = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}  {detail}")
    if not ok:
        failures.append(name)


registry = lua.table()
counter = [0]


def lua_fn(py):
    counter[0] += 1
    registry[counter[0]] = py
    return lua.eval(f'function(...) return __py_reg[{counter[0]}](...) end')


lua.globals().__py_reg = registry

rig = lua.eval('''
{
  bones = {
    { index = 1, parent = 0, name = "hd2n_0123456789ab_phys_001_hair", parentName = "hd2n_0123456789ab_anim_010_head",
      flags = 0x11, pos = {0,0,0},
      params = { length=30, tipMass=1, yawStiffness=0, yawDamping=50, pitchStiffness=7, pitchDamping=50,
                 alongStiffness=7, alongDamping=100, angleLimit=0 } },
    { index = 2, parent = 1, name = "hd2n_0123456789ab_phys_002_hair", parentName = "hd2n_0123456789ab_phys_001_hair",
      flags = 0x11, pos = {0,0,0},
      params = { length=30, tipMass=1, yawStiffness=0, yawDamping=50, pitchStiffness=7, pitchDamping=50,
                 alongStiffness=7, alongDamping=100, angleLimit=0 } },
  },
  drivers = { version = 2, bones = {
    { name = "hd2n_0123456789ab_aux_064_skirt_helper", parentName = "hd2n_0123456789ab_anim_011_hips",
      controlName = "hd2n_0123456789ab_anim_012_l_thigh", bindPos = {0,0,0},
      rules = {
        { invTolerance = 0.6366, trigger = {0.7071,0,0,0.7071}, position = {0,0,0}, rotation = {0,0,0,1} },
        { invTolerance = 0.6366, trigger = {0,0,0.7071,0.7071}, position = {0,0,0},
          rotation = (function() local s=math.sin(math.rad(10)); local c=math.cos(math.rad(10)); return {s,0,0,c} end)() },
      } },
  } },
}
''')

NODES = {
    "hd2n_0123456789ab_phys_001_hair": 91, "hd2n_0123456789ab_phys_002_hair": 92,
    "hd2n_0123456789ab_anim_010_head": 10, "hd2n_0123456789ab_aux_064_skirt_helper": 64,
    "hd2n_0123456789ab_anim_011_hips": 11, "hd2n_0123456789ab_anim_012_l_thigh": 12,
}
state = {"control_q": None, "rot_writes": [], "pose_writes": [], "updated": 0}


def vec3_new(x, y, z):
    return lua.table(x, y, z)


def quat_axis_angle(axis, angle):
    ax, ay, az = axis[1], axis[2], axis[3]
    length = math.sqrt(ax * ax + ay * ay + az * az) or 1.0
    s = math.sin(angle / 2)
    return lua.table(ax / length * s, ay / length * s, az / length * s, math.cos(angle / 2))


def mat_from_qp(q, p):
    x, y, z, w = q[1], q[2], q[3], q[4]
    n = math.sqrt(x*x + y*y + z*z + w*w) or 1.0
    x, y, z, w = x/n, y/n, z/n, w/n
    # 列主序 3x4：c0 c1 c2 各 3 个 + 平移 3 个（与 Matrix4x4.to_elements 布局一致）
    return lua.table(
        1-2*(y*y+z*z), 2*(x*y+z*w), 2*(x*z-y*w),
        2*(x*y-z*w), 1-2*(x*x+z*z), 2*(y*z+x*w),
        2*(x*z+y*w), 2*(y*z-x*w), 1-2*(x*x+y*y),
        p[1], p[2], p[3])


def to_elements(m):
    return (m[1], m[2], m[3], m[4], m[5], m[6], m[7], m[8], m[9], m[10], m[11], m[12])


S = lua.table()
S["Application"] = lua.table(**{"string_to_id32": lua_fn(lambda name: name)})
S["Vector3"] = lua.table(**{"to_elements": lua_fn(lambda v: (v[1], v[2], v[3]))})
S["Quaternion"] = lua.table(**{
    "to_elements": lua_fn(lambda q: (q[1], q[2], q[3], q[4])),
    "from_elements": lua_fn(lambda x, y, z, w: lua.table(x, y, z, w)),
    "axis_angle": lua_fn(quat_axis_angle),
})
S["Matrix4x4"] = lua.table(**{
    "to_elements": lua_fn(to_elements),
    "from_quaternion_position": lua_fn(mat_from_qp),
    "is_valid": lua_fn(lambda m: True),
})
S["World"] = lua.table(**{"update_unit": lua_fn(lambda world, unit: state.__setitem__("updated", state["updated"] + 1))})
U = lua.table(**{
    "alive": lua_fn(lambda u: True),
    "num_scene_graph_items": lua_fn(lambda u: 128),
    "has_node": lua_fn(lambda u, name: NODES.get(name) is not None),
    "node": lua_fn(lambda u, name: NODES.get(name, 0)),
    "local_pose": lua_fn(lambda u, node: lua.table(1, 0, 0, 0, 1, 0, 0, 0, 1, 0.1, 0.2, 0.3)),
    "world_position": lua_fn(lambda u, node: lua.table(0, 0, 0)),
    "world_rotation": lua_fn(lambda u, node: (
        lua.table(*state["control_q"])
        if node == NODES["hd2n_0123456789ab_anim_012_l_thigh"] and state["control_q"] is not None
        else lua.table(0, 0, 0, 1))),
    "local_rotation": lua_fn(lambda u, node: lua.table(0, 0, 0, 1)),
    "set_local_rotation": lua_fn(lambda u, node, q: state["rot_writes"].append((node, q[1], q[2], q[3], q[4]))),
    "set_local_pose": lua_fn(lambda u, node, m: state["pose_writes"].append((node, m[10], m[11], m[12]))),
    "name_hash": lua_fn(lambda u: "abc12345"),
})
S["Unit"] = U

lua.globals().__Vector3_new = lua_fn(vec3_new)
lua.globals().__S_for_mt = S
lua.eval('''
setmetatable(__S_for_mt.Vector3, { __call = function(_, x, y, z) return __Vector3_new(x, y, z) end })
''')

LOGS = lua.table()
lua.globals().compat = compat
lua.globals().rig = rig
lua.globals().S = S
lua.globals().world = lua.table()
lua.globals().LOGS = LOGS

result = lua.execute('return compat.attach(S, { unit = "u" }, rig, '
                     '{ logger = function(msg) LOGS[#LOGS+1] = tostring(msg) end, world = world })')

check("attach 完成", result is not None)
for line in LOGS.values():
    if "快路径" in line or "driver" in line:
        print("    [attach]", line)
check("弹簧链 1 条", len(list(result.sessions.values())) == 1)
check("快路径启用", compat._fastWrite is True, str(compat._fastWrite))
drivers = list(result.drivers.values()) if result.drivers else []
check("driver 解析 1 根", len(drivers) == 1, str(len(drivers)))
if drivers:
    row = drivers[0]
    check("三个节点下标正确",
          row.node == 64 and row.parentNode == 11 and row.controlNode == 12,
          f"node={row.node} parent={row.parentNode} control={row.controlNode}")

    state["control_q"] = [0.0, 0.0, 0.0, 1.0]
    state["rot_writes"].clear()
    compat.update_tip(result, 1 / 60)
    binds = [w for w in state["rot_writes"] if w[0] == 64]
    check("bind 姿态帧 driver 写入一次（bind 回退）", len(binds) == 1, f"writes={len(state['rot_writes'])}")

    state["rot_writes"].clear()
    compat.update_tip(result, 1 / 60)
    binds2 = [w for w in state["rot_writes"] if w[0] == 64]
    check("同姿态帧 driver 去重不写", len(binds2) == 0, f"writes={len(state['rot_writes'])}")

    state["control_q"] = [0.0, 0.0, 0.7071067811865476, 0.7071067811865476]
    state["rot_writes"].clear()
    compat.update_tip(result, 1 / 60)
    binds3 = [w for w in state["rot_writes"] if w[0] == 64]
    check("触发区帧 driver 写入", len(binds3) == 1, f"writes={len(state['rot_writes'])}")
    if binds3:
        _, qx, qy, qz, qw = binds3[0]
        norm = math.sqrt(qx * qx + qy * qy + qz * qz + qw * qw)
        expect = [math.sin(math.radians(10)), 0.0, 0.0, math.cos(math.radians(10))]
        dot = abs(qx * expect[0] + qy * expect[1] + qz * expect[2] + qw * expect[3])
        check("输出 = rule1.rotation（归一化后）", norm > 0.99 and dot > 0.99,
              f"q=({qx:.4f},{qy:.4f},{qz:.4f},{qw:.4f}) dot={dot:.5f}")

    state["control_q"] = None
    ok_update = True
    try:
        compat.update_tip(result, 1 / 60)
    except Exception as error:  # noqa: BLE001
        ok_update = False
        check("control 失效不崩", False, str(error)[:120])
    if ok_update:
        check("control 失效不崩", True)

    state["pose_writes"].clear()
    restored = compat.release(result)
    check("release 写回 driver bind", any(n == 64 for n, *_ in state["pose_writes"]),
          f"restored={restored}")

check("update/release 期间 update_unit 被调用", state["updated"] > 0, f"times={state['updated']}")

print()
if failures:
    print(f"FAIL：{failures}")
    sys.exit(1)
print("driver 热路径测试全部通过")

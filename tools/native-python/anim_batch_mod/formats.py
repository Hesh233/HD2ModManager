from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil, isfinite, sqrt
import struct

from .binary import BinaryFormatError, BinaryReader, BinaryWriter
from .math3d import matrix3_columns_to_quaternion


@dataclass
class BonesData:
    names: list[str]
    hashes: list[int]

    @classmethod
    def parse(cls, data: bytes | bytearray) -> "BonesData":
        reader = BinaryReader(data)
        name_count = reader.uint32()
        lod_count = reader.uint32()
        reader.read(4 * lod_count)
        hashes = [reader.uint32() for _ in range(name_count)]
        reader.read(4 * lod_count)
        raw_names = reader.read(len(data) - reader.tell()).split(b"\x00")
        names = [item.decode("utf-8") for item in raw_names if item]
        if len(names) != len(hashes):
            raise BinaryFormatError(
                f"Bones name/hash count mismatch: names={len(names)}, hashes={len(hashes)}"
            )
        return cls(names=names, hashes=hashes)


@dataclass
class LocalTransform:
    position: list[float]
    rotation: list[float]
    scale: list[float]


@dataclass
class UnitData:
    bones_ref: int
    state_machine_ref: int
    transforms: list[LocalTransform]
    parents: list[int | None]
    name_hashes: list[int]

    @classmethod
    def parse(cls, data: bytes | bytearray) -> "UnitData":
        if len(data) < 56:
            raise BinaryFormatError("Unit resource is too small")
        reader = BinaryReader(data)
        reader.uint64()
        bones_ref = reader.uint64()
        reader.uint64()
        reader.uint64()
        state_machine_ref = reader.uint64()
        reader.uint32()
        reader.uint32()
        reader.uint32()
        transform_info_offset = reader.uint32()
        if transform_info_offset == 0:
            raise BinaryFormatError("Unit has no TransformInfo section")
        reader.seek(transform_info_offset)
        transform_count = reader.uint32()
        reader.read(12)

        transforms = []
        for _ in range(transform_count):
            columns = [reader.vec3_float() for _ in range(3)]
            position = reader.vec3_float()
            scale = reader.vec3_float()
            reader.float32()
            transforms.append(
                LocalTransform(
                    position=position,
                    rotation=matrix3_columns_to_quaternion(columns),
                    scale=scale,
                )
            )

        reader.read(64 * transform_count)
        raw_parents = []
        for index in range(transform_count):
            reader.uint16()
            parent = reader.uint16()
            raw_parents.append(None if parent >= transform_count or parent == index else parent)
        name_hashes = [reader.uint32() for _ in range(transform_count)]
        return cls(
            bones_ref=bones_ref,
            state_machine_ref=state_machine_ref,
            transforms=transforms,
            parents=raw_parents,
            name_hashes=name_hashes,
        )
def patch_unit_positions(
    data: bytes | bytearray,
    unit: UnitData,
    bones: BonesData,
    offsets: dict[str, list[float]],
    distance_multipliers: dict[str, float] | None = None,
) -> bytearray:
    """Apply configured offsets and parent-child distance multipliers."""
    distance_multipliers = distance_multipliers or {}
    extra_multipliers = sorted(set(distance_multipliers) - set(offsets))
    if extra_multipliers:
        raise ValueError(
            "Distance multiplier requires a matching offset for: "
            + ", ".join(extra_multipliers)
        )
    for name, multiplier in distance_multipliers.items():
        multiplier = float(multiplier)
        if not isfinite(multiplier) or multiplier < 0.0:
            raise ValueError(
                f"Distance multiplier for {name} must be a finite non-negative number"
            )
    if not offsets:
        return bytearray(data)
    if len(unit.transforms) != len(unit.name_hashes):
        raise BinaryFormatError("Unit transform/name hash counts do not match")
    if len(data) < 56:
        raise BinaryFormatError("Unit resource is too small")
    transform_info_offset = struct.unpack_from("<I", data, 52)[0]
    if transform_info_offset == 0 or transform_info_offset + 4 > len(data):
        raise BinaryFormatError("Unit has an invalid TransformInfo offset")
    transform_count = struct.unpack_from("<I", data, transform_info_offset)[0]
    if transform_count != len(unit.transforms):
        raise BinaryFormatError(
            "Unit TransformInfo count does not match parsed Unit: "
            f"raw={transform_count}, parsed={len(unit.transforms)}"
        )
    transforms_start = transform_info_offset + 16
    transforms_end = transforms_start + transform_count * 64
    if transforms_end > len(data):
        raise BinaryFormatError("Unit TransformInfo transforms are outside the resource")

    bone_indices = {bone_hash: index for index, bone_hash in enumerate(unit.name_hashes)}
    bone_hash_by_name = dict(zip(bones.names, bones.hashes))
    result = bytearray(data)
    for name, delta in offsets.items():
        if len(delta) != 3:
            raise ValueError(f"Offset for bone {name!r} must contain 3 values")
        bone_hash = bone_hash_by_name.get(name)
        if bone_hash is None:
            raise ValueError(f"Configured bone {name!r} is missing from Bones")
        index = bone_indices.get(bone_hash)
        if index is None:
            raise ValueError(f"Configured bone {name!r} is missing from Unit TransformInfo")
        position_offset = transforms_start + index * 64 + 36
        position = unit.transforms[index].position
        position = [
            position[axis] + float(delta[axis]) for axis in range(3)
        ]
        parent = unit.parents[index]
        if parent is not None:
            multiplier = float(distance_multipliers.get(name, 1.0))
            position = [component * multiplier for component in position]
        struct.pack_into(
            "<3f",
            result,
            position_offset,
            *position,
        )
    return result


def parse_state_machine_animation_ids(data: bytes | bytearray) -> list[int]:
    reader = BinaryReader(data)
    if len(data) < 76:
        raise BinaryFormatError("State machine resource is too small")
    reader.uint32()
    layer_count = reader.uint32()
    layer_data_offset = reader.uint32()
    reader.read(64)
    reader.seek(layer_data_offset)
    stored_layer_count = reader.uint32()
    if stored_layer_count != layer_count:
        layer_count = stored_layer_count
    layer_offsets = [reader.uint32() for _ in range(layer_count)]
    animation_ids = []
    for layer_offset in layer_offsets:
        layer_start = layer_data_offset + layer_offset
        reader.seek(layer_start)
        reader.uint32()
        reader.uint32()
        state_count = reader.uint32()
        state_offsets = [reader.uint32() for _ in range(state_count)]
        for state_offset in state_offsets:
            state_start = layer_start + state_offset
            reader.seek(state_start)
            reader.uint64()
            reader.uint32()
            animation_count = reader.uint32()
            animation_offset = reader.uint32()
            reader.seek(state_start + animation_offset)
            for _ in range(animation_count):
                animation_id = reader.uint64()
                if animation_id not in animation_ids:
                    animation_ids.append(animation_id)
    return animation_ids


@dataclass
class AnimationBoneState:
    position: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    rotation: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0, 1.0])
    scale: list[float] = field(default_factory=lambda: [1.0, 1.0, 1.0])
    compress_position: bool = True
    compress_rotation: bool = True
    compress_scale: bool = True


@dataclass
class AnimationEntry:
    type: int = 0
    subtype: int = 0
    bone: int = 0
    time: float = 0.0
    data2: list[float] = field(default_factory=list)

    @property
    def is_position(self) -> bool:
        return self.type == 2 or (self.type == 0 and self.subtype == 4)

    @property
    def is_rotation(self) -> bool:
        return self.type == 3 or (self.type == 0 and self.subtype == 5)

    @property
    def is_scale(self) -> bool:
        return self.type == 1 or (self.type == 0 and self.subtype == 6)

    @classmethod
    def parse(cls, reader: BinaryReader) -> "AnimationEntry":
        start = reader.tell()
        header = list(reader.read(4))
        entry_type = (header[1] & 0xC0) >> 6
        subtype = 0
        if entry_type == 0:
            reader.seek(start)
            subtype = reader.uint16()
            if subtype == 3:
                return cls(type=0, subtype=3)
            bone = reader.uint32()
            time = reader.float32() * 1000.0
        else:
            bone = ((header[0] & 0xF0) >> 4) | ((header[1] & 0x3F) << 4)
            time = ((header[0] & 0x0F) << 16) | (header[3] << 8) | header[2]

        if entry_type == 3:
            values = decompress_rotation(reader.uint32())
        elif entry_type == 2:
            values = decompress_position([reader.uint16() for _ in range(3)])
        elif entry_type == 1:
            values = decompress_position([reader.uint16() for _ in range(3)])
        elif subtype == 4:
            values = reader.vec3_float()
        elif subtype == 5:
            values = [reader.float32() for _ in range(4)]
        elif subtype == 6:
            values = reader.vec3_float()
        elif subtype == 2:
            values = []
        else:
            raise BinaryFormatError(f"Unsupported animation entry type/subtype {entry_type}/{subtype}")
        return cls(type=entry_type, subtype=subtype, bone=bone, time=time, data2=values)

    def write(self, writer: BinaryWriter) -> None:
        if self.type == 0:
            writer.uint16(self.subtype)
            if self.subtype == 3:
                return
            writer.uint32(self.bone)
            writer.float32(self.time / 1000.0)
        else:
            time = int(round(self.time))
            if self.bone > 0x3FF or time < 0 or time > 0xFFFFF:
                raise BinaryFormatError(
                    f"Compressed animation header out of range: bone={self.bone}, time={time}"
                )
            header = [0, 0, 0, 0]
            header[1] |= (self.type << 6) & 0xC0
            header[0] |= (self.bone << 4) & 0xF0
            header[1] |= (self.bone >> 4) & 0x3F
            header[0] |= (time >> 16) & 0x0F
            header[3] = (time >> 8) & 0xFF
            header[2] = time & 0xFF
            writer.write(bytes(header))

        if self.type == 3:
            writer.uint32(compress_rotation(self.data2))
        elif self.type == 2:
            for value in compress_position(self.data2):
                writer.uint16(value)
        elif self.type == 1:
            for value in compress_position(self.data2):
                writer.uint16(value)
        elif self.subtype == 4:
            writer.vec3_float(self.data2)
        elif self.subtype == 5:
            for value in self.data2:
                writer.float32(value)
        elif self.subtype == 6:
            writer.vec3_float(self.data2)
        elif self.subtype != 2:
            raise BinaryFormatError(
                f"Unsupported animation entry type/subtype {self.type}/{self.subtype}"
            )


@dataclass
class AnimationData:
    initial_bone_states: list[AnimationBoneState] = field(default_factory=list)
    entries: list[AnimationEntry] = field(default_factory=list)
    hashes: list[int] = field(default_factory=list)
    hashes2: list[int] = field(default_factory=list)
    hashes_floats: list[float] = field(default_factory=list)
    unk: int = 0
    unk2: int = 0
    animation_length: float = 0.0
    file_size: int = 0
    is_additive: bool = False

    @classmethod
    def parse(cls, data: bytes | bytearray) -> "AnimationData":
        reader = BinaryReader(data)
        animation = cls()
        animation.unk = reader.uint32()
        bone_count = reader.uint32()
        animation.animation_length = reader.float32()
        animation.file_size = reader.uint32()
        hash_count = reader.uint32()
        hash2_count = reader.uint32()
        animation.hashes = [reader.uint64() for _ in range(hash_count)]
        animation.hashes2 = [reader.uint64() for _ in range(hash2_count)]
        animation.unk2 = reader.uint16()
        bit_byte_count = ceil(3 * bone_count / 8)
        if bit_byte_count % 2:
            bit_byte_count += 1
        bit_bytes = reader.read(bit_byte_count)
        flags = []
        for value in bit_bytes:
            reversed_value = reverse_bits(value)
            flags.extend((reversed_value >> shift) & 1 for shift in reversed(range(8)))

        for bone_index in range(bone_count):
            state = AnimationBoneState(
                compress_position=bool(flags[bone_index * 3]),
                compress_rotation=bool(flags[bone_index * 3 + 1]),
                compress_scale=bool(flags[bone_index * 3 + 2]),
            )
            if state.compress_position:
                state.position = decompress_position([reader.uint16() for _ in range(3)])
            else:
                state.position = reader.vec3_float()
            if state.compress_rotation:
                state.rotation = decompress_rotation(reader.uint32())
            else:
                state.rotation = [reader.float32() for _ in range(4)]
            if state.compress_scale:
                state.scale = decompress_position([reader.uint16() for _ in range(3)])
            else:
                state.scale = reader.vec3_float()
            animation.initial_bone_states.append(state)

        animation.hashes_floats = [reader.float32() for _ in range(hash_count)]
        while True:
            marker_position = reader.tell()
            marker = reader.uint16()
            if marker == 3:
                break
            reader.seek(marker_position)
            entry = AnimationEntry.parse(reader)
            if entry.type == 0 and entry.subtype not in (2, 4, 5, 6):
                continue
            animation.entries.append(entry)
        animation.is_additive = any(
            state.scale and state.scale[0] == 0 for state in animation.initial_bone_states
        )
        return animation

    def to_bytes(self) -> bytes:
        first = self._write(self.file_size)
        self.file_size = len(first)
        final = self._write(self.file_size)
        if len(final) != self.file_size:
            self.file_size = len(final)
            final = self._write(self.file_size)
        return final

    def _write(self, file_size: int) -> bytes:
        writer = BinaryWriter()
        self._write_block(writer, file_size, include_file_size=True)
        first_block_size = writer.tell()
        writer.uint32(first_block_size)
        self._write_block(writer, 0, include_file_size=False)
        writer.uint32(first_block_size)
        return bytes(writer.data)

    def _write_block(self, writer: BinaryWriter, file_size: int, include_file_size: bool) -> None:
        writer.uint32(self.unk)
        writer.uint32(len(self.initial_bone_states))
        writer.float32(self.animation_length)
        if include_file_size:
            writer.uint32(file_size)
        else:
            writer.seek(writer.tell() + 4)
        writer.uint32(len(self.hashes))
        writer.uint32(len(self.hashes2))
        for value in self.hashes:
            writer.uint64(value)
        for value in self.hashes2:
            writer.uint64(value)
        writer.uint16(self.unk2)

        flags = []
        for state in self.initial_bone_states:
            flags.extend(
                [state.compress_position, state.compress_rotation, state.compress_scale]
            )
        while len(flags) % 8:
            flags.append(False)
        flag_bytes = bytearray()
        for index in range(0, len(flags), 8):
            value = 0
            for flag in flags[index:index + 8]:
                value = (value << 1) | int(flag)
            flag_bytes.append(reverse_bits(value))
        writer.write(flag_bytes)
        if writer.tell() % 2:
            writer.seek(writer.tell() + 1)

        for state in self.initial_bone_states:
            if state.compress_position:
                for value in compress_position(state.position):
                    writer.uint16(value)
            else:
                writer.vec3_float(state.position)
            if state.compress_rotation:
                writer.uint32(compress_rotation(state.rotation))
            else:
                for value in state.rotation:
                    writer.float32(value)
            if state.compress_scale:
                for value in compress_position(state.scale):
                    writer.uint16(value)
            else:
                writer.vec3_float(state.scale)
        for value in self.hashes_floats:
            writer.float32(value)
        for entry in self.entries:
            entry.write(writer)
        writer.uint16(3)


def reverse_bits(value: int) -> int:
    result = 0
    for index in range(8):
        if (value >> index) & 1:
            result |= 1 << (7 - index)
    return result


def compress_position(position) -> list[int]:
    result = [int((value * 3276.7) + 32767.0) for value in position]
    if any(value < 0 or value > 0xFFFF for value in result):
        raise BinaryFormatError(
            f"Position is outside the compressed range and must be stored uncompressed: {position}"
        )
    return result


def decompress_position(position) -> list[float]:
    return [(value - 32767.0) * (10.0 / 32767.0) for value in position]


def compress_rotation(rotation) -> int:
    largest_index = max(range(4), key=lambda index: rotation[index])
    result = largest_index
    for offset, shift in ((1, 2), (2, 12), (3, 22)):
        value = rotation[(largest_index + offset) % 4]
        packed = int(((value / 0.75) * 512) + 512)
        result |= (packed & 0x3FF) << shift
    return result


def decompress_rotation(rotation: int) -> list[float]:
    first = (((rotation & 0xFFC) >> 2) - 512.0) / 512.0 * 0.75
    second = (((rotation & 0x3FF000) >> 12) - 512.0) / 512.0 * 0.75
    third = (((rotation & 0xFFC00000) >> 22) - 512.0) / 512.0 * 0.75
    largest_index = rotation & 0x3
    remainder = 1.0 - third**2 - second**2 - first**2
    largest_value = sqrt(max(0.0, remainder))
    if largest_index == 0:
        return [largest_value, first, second, third]
    if largest_index == 1:
        return [third, largest_value, first, second]
    if largest_index == 2:
        return [second, third, largest_value, first]
    return [first, second, third, largest_value]
